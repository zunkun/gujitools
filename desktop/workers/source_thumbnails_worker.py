# -*- coding: utf-8 -*-
"""导入后的一次性后台准备：**保住源文件副本 + 逐页渲染缩略图**。

命名与 PDF 预览查看器的页缩略图缓存一致（{page}.jpg，0 起始），
预览打开时直接命中缓存，不再重复渲染；该目录永不清理。

⚠️ 顺序：**缩略图先行、复制并行**（2026-09-25 改）
    原先「先复制 802MB、再从副本渲染缩略图」是串行的。复制本身不慢
    （SSD 实测 0.73s / 794MB），但慢盘上它可能是几十秒；而这段时间里
    用户已经点进详情页、要看的就是缩略图——他等的是**缩略图**，不是副本。
    现在：复制丢进独立线程（纯 I/O，不占 GIL），缩略图**立刻从源文件**
    开渲，首批（一屏可见量）先出；首批做完再等副本落地，后续页改从副本
    继续渲染（源文件之后被挪走/删掉也不影响剩下的页）。

⚠️ 为什么要每页让出 GIL
    PyMuPDF 渲染一页扫描件（5000×4400 的内嵌 JPEG）要 ~160ms，而且这
    160ms 里几乎一直持有 GIL：实测另一线程每 1ms 的心跳被拖到 175ms，
    只让 3ms 的话主线程只拿到 ~2% 的时间片——用户看到的正是「导入期间
    整个界面卡住」。现在让出量**按刚花掉的耗时成比例**（×0.5，上限 60ms），
    界面拿到约 1/3 的时间片；代价是整本渲染慢约 50%，而它是纯后台活。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from desktop.utils.files import (
    THUMBNAIL_EDGE, copy_file_atomic, set_producing_marker,
    task_extract_pages_dir,
)
from utils.file_utils import write_bytes_atomic

#: 首批渲染的页数（约一屏可见量）：进详情页后马上要看的就是这几张，
#: 必须"立刻"出来，不能排在整本 320 页后面。
FIRST_SCREEN_PAGES = 16

#: 导入时**最多**预渲染多少页缩略图（= 首屏 + 一屏余量）。
#:
#: ⚠️ 为什么不再整本预渲染（2026-10-21，用户：「我就是想提取图片」）：
#: 一本 2000 页的书，整本预渲染即使有 JPX 快速通道也要几分钟后台 CPU，
#: 而用户多半只看开头几十页、然后直接点「执行提取」。现在只把首屏备好，
#: 剩下的**滚到可见窗口时按需补**（`PdfViewerWidget._fill_window`，单页
#: ~170ms），导入立刻结束、CPU 不再和提取抢核。
PREFETCH_PAGES = 24

#: 首批之后每批页数 + 批间空隙（让 GUI 把这一批的图标画完、把点击处理掉）
BATCH_PAGES = 8
BATCH_GAP_MS = 120

#: 每页让出 GIL 的比例与上下限（见模块文档：不让出 = 界面卡死）
GIL_YIELD_RATIO = 0.5
GIL_YIELD_MIN_MS = 3
GIL_YIELD_MAX_MS = 60

#: 缩略图缓存的最小合理体积（字节）。
#: ⚠️ 缓存命中判据是「mtime 不比源 PDF 旧」，而**截断**的文件 mtime 也是新的。
#: 正常一页 256px JPEG 有几千字节到几十 KB，几百字节的必然是写坏/截断的。
#: 加这条下界让历史遗留的坏缓存能自愈（新写入已改为原子写，不会再产生）。
MIN_THUMB_BYTES = 512



#: **全部页渲完之后**才短暂等一等副本：让常见的快盘场景（0.7s 复制完）
#: 在"导入完成"提示之前真正落地。等不到也不阻塞——复制线程是 daemon，
#: 继续在后台把它拷完。
#: ⚠️ 渲染过程中**一秒都不等副本**（页间只做一次 is_alive() 检查，不 join）：
#: 慢盘上复制 700MB 可能要几十秒，join 会把后面的页全停住——那正是用户
#: 抱怨的"导入是串行的"。
FINAL_COPY_WAIT_S = 5.0


class SourceThumbnailsWorker(QObject):
    """导入 PDF 后渲染全部页面缩略图（256px，与预览查看器缓存一致）。"""

    finished = Signal(str)  # 缩略图目录路径

    #: 请求被取消（删任务/关程序）：**终态信号**。串行队列把它接到
    #: ``thread.quit``——没有它，取消路径的 return 会让线程事件循环永不退出
    #: （队列卡死、任务删不掉）。
    cancelled = Signal()
    #: 非致命问题：例如副本保存失败，但仍从原文件渲染成功
    warning = Signal(str)
    failed = Signal(str)
    #: 渲染进度 (已完成页数, 总页数)；整本渲染可能要几十秒，界面靠它报进度
    progress = Signal(int, int)

    def __init__(
        self,
        pdf_path: Path,
        out_dir: Path,
        edge: int = THUMBNAIL_EDGE,
        copy_to: Path | None = None,
    ):
        """构造源 PDF 页缩略图 worker。

        pdf_path 为源文件；out_dir 为 thumbnails/source/；edge 最长边
        （默认 256）。缩略图命名 {page+1:04d}.jpg，与预览缓存一致。

        copy_to 给了就**另起一个线程**把它复制成任务目录里的源文件副本
        （原子落地）；缩略图不等它——先用源文件渲首批，副本落地后剩下的页
        再从副本渲。源文件随后被移动/删除都不影响已落地的副本。
        """
        super().__init__()
        self.pdf_path = pdf_path
        self.out_dir = out_dir
        self.edge = edge
        self.copy_to = copy_to
        self._cancelled = False
        #: 复制线程是否成功（失败只在删任务时无副本，不影响缩略图）
        self._copied = False
        #: 源 PDF 的 mtime（run() 里填）：缩略图比它新就算缓存可用
        self._pdf_mtime = 0.0
        #: 当前渲染用的是哪份文档："source"（源文件）/"copy"（任务目录副本）。
        #: 排障与复现脚本靠它证明"缩略图先跑、副本落地后接管"。
        self.document_kind = "source"
        self._document = None
        #: **渲染用的路径**：起初是源文件，副本落地后换成副本（见
        #: :meth:`_maybe_switch_to_copy`）。渲染在子进程里做，所以这里给的是
        #: **路径**而不是文档对象。
        self._render_path = self.pdf_path
        self._copy_thread: threading.Thread | None = None

    def cancel(self) -> None:
        """请求中止：渲染循环在下一页之前退出（关程序用，不必等整本跑完）。"""
        self._cancelled = True

    def wait_copy(self, timeout: float) -> bool:
        """等复制线程收手，最多 `timeout` 秒；返回是否已结束。

        ⚠️ 为什么需要（2026-09-26 审计）：复制是在**独立 daemon 线程**里做的，
        `cancel()` 只置渲染循环的中止标志，打不断正在写的复制。而复制中的
        `.part` 文件是**打开的句柄**——删任务时 `rmtree` 会一直
        `PermissionError`（Windows）。所以删任务前必须给复制一个收手的机会。
        """
        thread = self._copy_thread
        if thread is None:
            return True
        thread.join(timeout=max(0.0, timeout))
        if thread.is_alive():
            return False
        self._copy_thread = None
        return True

    # ------------------------------------------------------------ 复制（并行）
    def _copy_source(self) -> None:
        """把源文件复制成任务目录里的副本（原子落地）。失败只告警，不中断。"""
        assert self.copy_to is not None
        try:
            copy_file_atomic(self.pdf_path, self.copy_to)
            self._copied = True
        except OSError as exc:
            self.warning.emit(str(exc))

    @Slot()
    def run(self) -> None:
        """并行复制 + 逐页渲染缩略图；任务目录被删时中止并报 failed。

        ⚠️ **顺序：缩略图一秒都不等复制**。复制丢进独立线程，缩略图立刻从
        **源文件**开渲、首批（一屏）先出；页间只顺路看一眼复制好了没
        （`is_alive()`，**不 join**），好了就换成从副本继续——源文件之后被
        挪走/删掉也不影响剩下的页。慢盘上复制 700MB 要几十秒，任何"等它"
        都会把整本缩略图停住，用户看到的就是"导入是串行的"。

        ⚠️ **每页先查缓存**：命名与预览查看器的缓存一致（``0001.jpg``），
        已存在且不比源 PDF 旧的直接跳过。否则重复导入同一份 PDF（或把任务
        目录复制过来）时，80 页的书要白渲染 80 页——用户看到的正是「明明
        已经有缩略图了还在重新生成」。
        """
        if self.copy_to is not None:
            # 复制只读盘、不占 GIL，但**绝不能排在渲染前面**（见模块文档）
            self._copy_thread = threading.Thread(
                target=self._copy_source, name="guji-source-copy", daemon=True
            )
            self._copy_thread.start()
        try:
            import fitz

            source = self.pdf_path
            self._pdf_mtime = _stat_mtime(source)
            self._document = fitz.open(str(source))
            try:
                if self._document.page_count == 0:
                    raise ValueError("PDF 没有任何页面")
                self.out_dir.mkdir(parents=True, exist_ok=True)
                # ⚠️ 原子写：缓存可用性判据是 mtime，非原子写留下的截断 JPEG
                #    mtime 更新 → 会被永久当成有效缓存且不自愈（见
                #    utils/file_utils.write_bytes_atomic 的说明）。
                write_bytes_atomic(self.out_dir / ".meta", str(self.edge).encode("utf-8"))
                # 在场标记：告诉查看器"这个目录有人在填，别自己再渲一遍"
                # （见 PRODUCING_MARKER 的说明）。失败不影响渲染。
                self._mark_producing(True)
                total = self._document.page_count
                # 只备首屏（见 PREFETCH_PAGES）：其余页滚到可见窗口时按需补
                planned = min(total, PREFETCH_PAGES)
                self.progress.emit(0, planned)  # 开始渲染

                done = 0
                cancelled = False

                def on_page(page_number: int, _data=None) -> None:
                    """单页**一落地**就报进度（不等整批）——查看器靠回扫捡新文件。"""
                    nonlocal done, cancelled
                    done += 1
                    self.progress.emit(done, planned)
                    if self._cancelled:
                        cancelled = True

                for index, batch in enumerate(self._batches(planned)):
                    if index:
                        # 批间空隙：让 GUI 把上一批的图标画完、把点击处理掉
                        time.sleep(BATCH_GAP_MS / 1000)
                    self._render_batch(batch, on_page)
                    if cancelled:
                        break
                if planned < total and not cancelled:
                    self.progress.emit(planned, planned)
                    print(
                        f"[缩略图] 已备好前 {planned} 页；其余 {total - planned} 页"
                        "在浏览到可见窗口时按需生成（不再整本预渲染）"
                    )
            finally:
                if self._document is not None:
                    self._document.close()
                    self._document = None
                # 无论正常结束/取消/异常，都要撤掉在场标记：留着会让查看器
                # 一直以为"有人在填"（虽然回扫 6 轮后会自己接手，但那是兜底）
                self._mark_producing(False)
            # ⚠️ 取消也是终态：必须发信号让串行队列的 thread.quit 真正执行。
            #    裸 return 时线程事件循环永不退出 → cancel_tag 的 wait 超时 →
            #    任务永远删不掉、队列 busy() 恒 True、后续导入全部堵死
            #    （2026-09-26 第二轮审计 H1）。
            if cancelled:
                self.cancelled.emit()
                return
            # 全部页渲完：给副本一小段落地时间（快盘 0.7s 就够，让"导入完成"
            # 提示名副其实）。等不到也不阻塞——复制线程是 daemon，会在后台拷完。
            if self._copy_thread is not None:
                self._copy_thread.join(timeout=FINAL_COPY_WAIT_S)
                self._copy_thread = None
            self.finished.emit(str(self.out_dir))
        except Exception as exc:
            self.failed.emit(str(exc))

    def _maybe_switch_to_copy(self) -> None:
        """副本落地了就把渲染源从「源文件」换成「任务目录副本」。

        ⚠️ 页间调用，**只做一次 ``is_alive()`` 检查，绝不等待**：慢盘上复制
        700MB 要几十秒，任何 join 都会把整本缩略图停在那儿。
        """
        thread = self._copy_thread
        if thread is None or thread.is_alive():
            return
        thread.join()  # 已结束，瞬间返回；收割线程并拿到结果
        self._copy_thread = None
        # ⚠️ 真正决定后续页从哪渲的是 ``_render_path``（子进程按路径开文档）；
        #    下面那个文档对象只用于"副本能不能打开"的探测，打不开就继续用源文件。
        if self._copied and self.copy_to is not None:
            probe = self._open_copy()
            if probe is None:
                return
            probe.close()
            self._render_path = Path(self.copy_to)
        else:
            return
        self.document_kind = "copy"

    @staticmethod
    def _batches(total: int) -> list[list[int]]:
        """分批计划：**首批一屏**（进详情页立刻要看的那几页），其余每批 BATCH_PAGES。

        顺序即优先级：首批先渲完，用户点进详情页马上有图；后续批次之间留空隙，
        避免整本渲染把 GIL 占满（本机 320 页扫描件要 ~50s）。
        """
        first = list(range(min(FIRST_SCREEN_PAGES, total)))
        rest = list(range(len(first), total))
        return [first] + [
            rest[start : start + BATCH_PAGES]
            for start in range(0, len(rest), BATCH_PAGES)
        ]

    def _open_copy(self):
        """打开任务目录里的副本继续渲染；打不开就返回 None（继续用源文件）。

        ⚠️ 调用方负责先把**源文档** close 再换用返回值——这里绝不碰传入的
        文档（旧实现在这里把同一文档 close 了两次、还把副本开了两份只关一份）。
        """
        if not self._copied or self.copy_to is None:
            return None
        try:
            import fitz

            return fitz.open(str(self.copy_to))
        except Exception:  # noqa: BLE001 - 换副本失败不影响已渲的页
            return None

    def _render_batch(self, pages: list[int], on_page) -> None:
        """渲**一批**页：子进程并行，**每页一落地就写盘并回调** ``on_page(page)``。

        ⚠️ 为什么"一落地就写"而不是"整批回来再写"（2026-10-21 实测）：
        首批 16 页 × ~1s ÷ 3 个进程 = **5 秒多一张缩略图都不出现**，而查看器
        正是靠"目录里冒出新文件"来逐张上屏的——用户看到的是"缩略图半天不出来"。
        改成流式交付后，头 3 张约 1s 就落地，之后一张一张往外冒。

        ⚠️ 为什么成批而不是一页一 submit：单个子进程渲一页 JPX 要 ~700ms~1s，
        逐页提交时池里另外两个进程全程闲着。成批提交 + 流式回调两者兼得。

        ⚠️ 任务目录被删时**立刻**抛 FileNotFoundError 中止，别往残留目录里写。
        """
        import time

        from desktop.workers import pdf_render_service as svc

        # 副本落地了就换成从副本渲（非阻塞检查，见 _maybe_switch_to_copy）
        self._maybe_switch_to_copy()
        task_root = self.out_dir.parent.parent
        pending: list[tuple[int, Path]] = []
        for page_number in pages:
            if not task_root.is_dir():
                raise FileNotFoundError("任务目录已不存在，中止缩略图生成")
            target = self.out_dir / f"{page_number + 1:04d}.jpg"
            if self._cache_usable(target):
                on_page(page_number)  # 命中缓存：不付渲染钱，但照常报进度
                continue
            pending.append((page_number, target))
        if not pending:
            return
        targets = dict(pending)
        started = time.perf_counter()

        def deliver(page_number: int, data: bytes) -> None:
            if data:
                write_bytes_atomic(targets[page_number], data)
            on_page(page_number)

        svc.render_stream(
            self._render_path, [page for page, _target in pending], self.edge, 80,
            on_page=deliver,
            # 已提取的页直接从产物 jpg 缩（21ms），不回 PDF 解 JPX（850ms）
            pages_dir=task_extract_pages_dir(self._render_path),
        )
        if not svc.offloaded():
            # 进程内兜底：按耗时成比例让出 GIL（出进程时**一秒都别睡**，
            # 那时卡的是子进程，睡只会让整本缩略图白慢一倍）
            spent_ms = (time.perf_counter() - started) * 1000 / len(pending)
            yield_ms = min(GIL_YIELD_MAX_MS, max(GIL_YIELD_MIN_MS,
                                               spent_ms * GIL_YIELD_RATIO))
            time.sleep(yield_ms / 1000)

    def _render_page(self, document, page_number: int) -> float:
        """渲染一页缩略图并落盘，返回耗时（秒）；缓存可用时返回 0 且不渲染。

        ⚠️ **真正的渲染在子进程里做**（``pdf_render_service``）：PyMuPDF 的
        ``get_pixmap`` 整段持 GIL，扫描古籍常见的内嵌格式是 JPX（JPEG2000），
        渲一张 4285×5736 的页要 **~850ms 且这 850ms GUI 线程拿不到时间片**——
        这就是"导入一本 28 页的书，界面卡成 28 个 0.85 秒的块"的真因。
        ``document`` 参数只为兼容旧调用（命令行测试直接传文档进来），
        渲染走的是 **PDF 路径**，子进程自己开文档。

        渲染段仍走**单飞锁**——但只对**进程内兜底**那条路有效（服务内部自己
        拿锁）；出进程时锁是空转，多个子进程可以真并行。
        """
        target = self.out_dir / f"{page_number + 1:04d}.jpg"
        if self._cache_usable(target):
            return 0.0  # 缓存可用（不比源 PDF 旧且不像截断），跳过
        from desktop.workers import pdf_render_service as svc

        started = time.perf_counter()
        data = svc.render_jpeg(self._render_path, page_number, self.edge, 80)
        if data:
            write_bytes_atomic(target, data)  # 写盘在锁外（I/O 不需要占着渲染锁）
        return time.perf_counter() - started

    def _mark_producing(self, on: bool) -> None:
        """设置/清除「本目录正有人在填」的在场标记（语义见 ``set_producing_marker``）。"""
        set_producing_marker(self.out_dir, on)

    def _cache_usable(self, target: Path) -> bool:
        """这张缩略图缓存能不能直接用（mtime 不旧 + 体积不像截断）。"""
        if not target.exists():
            return False
        try:
            stat = target.stat()
        except OSError:
            return False
        return stat.st_mtime >= self._pdf_mtime and stat.st_size >= MIN_THUMB_BYTES


def _stat_mtime(path) -> float:
    """文件 mtime；取不到返回 0（拿不到就当"缓存都是新的"→ 不重渲）。"""
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0.0
