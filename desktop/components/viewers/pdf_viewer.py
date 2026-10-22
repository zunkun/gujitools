# -*- coding: utf-8 -*-
"""PDF 查看器：左侧页面缩略图 + 右侧大图。"""

from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QHBoxLayout, QWidget

from desktop.workers import PreviewWorker, WorkerHost, connect_queued
from desktop.components.viewers.image_view import ImageView
from desktop.components.viewers.image_zoom_dialog import (
    ZoomPopupMixin, ZoomTarget,
)
from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.utils.files import PRODUCING_MARKER


class PdfViewerWidget(QWidget, WorkerHost, ZoomPopupMixin):
    """PDF 查看器：左侧页面缩略图 + 右侧大图。"""

    page_count_changed = Signal(int)

    #: 缓存目录「正被别人填」的判据：最近这么多秒内有缩略图落盘。
    #: 导入后台任务就是那个生产者（复制完之后逐页写 thumbnails/source）。
    CACHE_ACTIVE_WINDOW_S = 8.0
    #: 别人在填时，每隔多久回扫一次缓存目录，把新出现的缩略图捡回来
    RESCAN_INTERVAL_MS = 1000
    #: 连续多少轮回扫都没有新文件 → 认为生产者已经不干了，自己接手补缺页
    RESCAN_STALL_ROUNDS = 6
    #: 页间缓存上限（条数）。每页只存 JPEG 字节（约 311KB），24 条 ≈ 7.5MB，
    #: 换来「切回看过的页 / 顺序翻阅预取命中」时 25ms 出图（重渲是 187ms）。
    PAGE_CACHE_MAX = 24
    #: 预取延迟：用户停手这么久之后才发预取渲染请求（见 _prefetch_neighbors）
    PREFETCH_IDLE_MS = 250
    #: **按可见窗口补缩略图**：视口上下各多补几行（用户来回滚一点不用等）
    FILL_WINDOW_MARGIN = 12
    #: 滚动停下多久之后才补（连续滚轮时不派活）
    FILL_DEBOUNCE_MS = 180
    #: 视口还没算出来（离屏/未 show）时的兜底行数
    FALLBACK_VISIBLE = 16

    def __init__(self, placeholder: str = "暂无 PDF", parent=None):
        """初始化 PDF 查看器：左侧页缩略图条 + 右侧大图。

        placeholder 为无 PDF 时的占位文案；缩略图/大图经 WorkerHost 异步
        加载，并用缓存目录避免重复渲染。
        """
        super().__init__(parent)
        self._init_worker_host()
        self._pdf_path: Path | None = None
        self._cache_dir: Path | None = None
        self._thumb_received: set[int] = set()
        self._thumb_total = 0
        self._thumb_retried = False
        #: 当前这一轮缩略图是「只读缓存」还是「自己渲染缺页」
        self._pass_kind = "fill"
        #: 回扫状态：只在「别人正在填缓存」时用
        self._watching = False
        self._stall_rounds = 0
        #: 页间缓存：(页号, 目标边长) → 渲染好的 JPEG 字节；LRU 淘汰
        self._page_cache: dict[tuple[int, int], bytes] = {}
        self._page_order: list[tuple[int, int]] = []
        self._prefetch_busy = False
        self._prefetch_target: tuple[int, int] = (0, 0)
        self._prefetch_timer = QTimer(self)
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.timeout.connect(self._start_prefetch)
        #: 大图点击请求的递增序号：只有**最新**一次点击的渲染结果才上屏。
        #: 连点多页时，陈旧请求在 worker 侧（is_stale）就不渲染了，就算已
        #: 渲完也不许覆盖用户当前看的页（2026-09-25 修「多点几下卡死」）。
        self._page_req_seq = 0
        #: 缩略图 pass 的代际号：每次 set_pdf 递增。旧文档的整本缩略图 worker
        #: 可能还要跑几十秒，它的迟到信号（metadata/thumbnail_ready/completed）
        #: 一律按代际丢弃——否则旧书的页会画进新书缩略条，metadata 还会用
        #: **旧书页数**重建条目、污染 pdf_page_count（2026-09-26 第二轮审计 M1）。
        self._thumb_gen = 0
        #: 上一轮回扫看到的缓存文件数（用来判断"有没有新缩略图落盘"）
        self._last_cache_count = 0
        self._rescan_timer = QTimer(self)
        self._rescan_timer.setInterval(self.RESCAN_INTERVAL_MS)
        self._rescan_timer.timeout.connect(self._on_rescan)
        # 按可见窗口补缩略图：滚动停下后补当前窗口（见 _fill_window）
        self._fill_timer = QTimer(self)
        self._fill_timer.setSingleShot(True)
        self._fill_timer.timeout.connect(self._fill_window)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.strip = ThumbStrip()
        self.strip.current_path_changed.connect(self._select_page)
        # 滚动 → 停手后补**当前可见窗口**的缩略图（不再整本预渲染）
        self.strip.verticalScrollBar().valueChanged.connect(self._on_thumb_scroll)
        layout.addWidget(self.strip)
        self.view = ImageView(placeholder)
        layout.addWidget(self.view, 1)
        # 双击大图 → 图片预览弹窗（只读查看）
        self._init_zoom_popup(self.view)

    def set_pdf(
        self,
        path: Path | None,
        placeholder: str | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        """cache_dir：页缩略图缓存目录（如 thumbnails/source、thumbnails/print），
        命中则直接使用，缺失的页渲染后补写。

        ⚠️ **缺页渲不渲要看缓存目录有没有别的生产者在填**（判据见
        `_cache_is_being_filled`）：导入后台任务正在逐页写同一份缓存，
        这里再跑一遍全量渲染 = 工作量翻倍 + 两个 PyMuPDF 循环互相抢 GIL，
        界面直接冻住（2026-09-25 实测）。所以那时只做「只读 + 每秒回扫」，
        生产者停手了才自己接手。
        """
        self._pdf_path = path
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._thumb_received = set()
        self._thumb_total = 0
        self._thumb_retried = False
        # 换文档 = 旧文档的所有在飞请求作废：单页渲染按序号、整本缩略图按代际
        self._page_req_seq += 1
        self._thumb_gen += 1
        for worker in list(getattr(self, "_workers", [])):
            cancel = getattr(worker, "cancel", None)
            if callable(cancel) and (
                hasattr(worker, "thumb_gen") or hasattr(worker, "is_stale")
            ):
                try:
                    cancel()
                except Exception:  # noqa: BLE001 - 收尾尽力而为
                    pass
        self._rescan_timer.stop()
        self._stall_rounds = 0
        self._prefetch_busy = False
        self._prefetch_timer.stop()  # 换文档了：上一本的预取请求作废
        self._page_cache.clear()  # 换文档了：缓存的页全作废
        self._page_order.clear()
        self._watching = self._cache_is_being_filled()
        self.strip.clear()
        self.close_zoom_popup()  # 换 PDF 了：弹窗里那页是旧文档
        text = placeholder or (path.name if path else "暂无 PDF")
        if path is None or not Path(path).exists():
            self.view.clear_image(text)
            self.strip.add_placeholder(text)
            return
        self.view.clear_image("正在加载 PDF...")
        self.strip.add_placeholder("缩略图加载中...")
        # ⚠️ 第一轮**只读**：只为拿到页数（metadata）与已经存在的缓存文件。
        #    缺页改为"滚到可见窗口时再补"（``_fill_window``）——一本 2000 页的
        #    书，用户只看前几十页，没必要把整本渲完（用户 2026-10-21：
        #    "我就是想提取图片"）。
        self._start_thumb_pass(render_missing=False)

    def _fill_window(self) -> None:
        """**只补当前可见窗口**（首末行 ± ``FILL_WINDOW_MARGIN``）的缺图。

        ⚠️ 为什么不再整本补（2026-10-21）：缩略图以前是"整本一次性渲完"，
        2000 页的书要渲 2000 次（即使有 JPX 快速通道也要几分钟后台 CPU），
        而用户通常只看开头几十页就想直接提取。现在按窗口补：滚到哪补到哪，
        补一页只要 ~170ms（JPX 快速通道），滚动手感上是"顿一下就有图"。

        ⚠️ ``_watching``（有别的生产者在填同一份缓存）时**一页都不渲**：
        重复渲染等于工作量翻倍，交给回扫捡现成的（见 ``_on_rescan``）。
        """
        if not self._pdf_path or self._watching:
            return
        total = self._thumb_total or self.strip.count()
        if total <= 0:
            return
        first, last = self.strip.visible_row_range()
        if last < first:
            # 视口还没算出来（离屏/未 show）：按兜底行数从头补
            first, last = 0, min(total - 1, self.FALLBACK_VISIBLE - 1)
        lo = max(0, first - self.FILL_WINDOW_MARGIN)
        hi = min(total - 1, last + self.FILL_WINDOW_MARGIN)
        missing = [i for i in range(lo, hi + 1) if i not in self._thumb_received]
        if missing:
            self._start_thumb_pass(pages=missing, render_missing=True)

    def _on_thumb_scroll(self, *_args) -> None:
        """滚动条动了：停手一小会儿再补窗口（连续滚动时不派活）。"""
        if self._watching or not self._pdf_path:
            return
        self._fill_timer.start(self.FILL_DEBOUNCE_MS)

    def _start_thumb_pass(self, pages: list[int] | None = None,
                         render_missing: bool = True) -> None:
        """跑一轮缩略图：``pages`` 限定页号，``render_missing`` 决定缺页渲不渲。"""
        self._pass_kind = "fill" if render_missing else "read"
        assert self._pdf_path is not None  # 仅在装入 PDF 后调用
        worker_path = Path(self._pdf_path)
        worker_cache = self._cache_dir
        self.run_worker(
            lambda: PreviewWorker(
                worker_path, thumbnails=True, cache_dir=worker_cache,
                render_missing=render_missing, pages=pages,
            ),
            self._wire_thumbnails,
        )

    def _cache_scan(self) -> tuple[int, float]:
        """一次 readdir 拿到（缩略图数量, 最新落盘那张的 mtime）。

        ⚠️ 只 stat **文件名最大的那一张**：导入任务按页码升序写（0001→0320），
        名字最大的就是最新落盘的那张，一次 stat 足以判断"缓存还在不在被填"。

        ⚠️ 为什么连"逐个 endswith 过滤"都省掉：320 次 Python 级操作在**导入
        后台攥着 GIL** 时要花 ~180ms（每个字节码都可能排队等 GIL，实测进详情
        页白卡一下）；空闲时只要 4ms。`os.listdir` 是单个 C 调用，`max()` 是 C
        层循环，`.meta` 以 '.' 开头（ASCII 46 < '0' 48）永远排在 jpg 前面，
        所以不会抢走 max。
        """
        if not self._cache_dir or not self._cache_dir.is_dir():
            return 0, 0.0
        try:
            names = os.listdir(self._cache_dir)
        except OSError:
            return 0, 0.0
        if not names:
            return 0, 0.0
        try:
            newest = os.stat(os.path.join(self._cache_dir, max(names))).st_mtime
        except OSError:
            newest = 0.0
        return len(names), newest

    def _cache_is_being_filled(self) -> bool:
        """缓存目录里最近有缩略图落盘、**或**有生产者在场 → 导入后台任务在填它。

        ⚠️ 两道判据缺一不可（2026-10-21）：

        - **在场标记**（``.producing``）：刚导入完的那一刻目录还是空的，光看
          mtime 判据看不到生产者，于是查看器自己又渲一遍整本 —— 与导入任务
          **各渲一遍**（28 页 JPX = 56 次 ~850ms 解码，用户看到的正是"缩略图
          老半天不齐"）。标记在生产者一开始渲染就写、结束即删。
        - **mtime**：生产者被杀/崩溃时标记会残留，也可能有**别的**东西在写
          这个目录（老任务、外部脚本）；一旦 8 秒没有新文件也算"没人干了"，
          由 ``_on_rescan`` 的回扫兜底接手。
        """
        if self._cache_dir and (self._cache_dir / PRODUCING_MARKER).exists():
            return True
        _count, newest = self._cache_scan()
        return bool(newest) and (time.time() - newest) < self.CACHE_ACTIVE_WINDOW_S

    def _wire_thumbnails(self, worker: PreviewWorker, thread) -> None:
        # 迟到信号按代际丢弃（见 _thumb_gen）；thumb_gen 是 PreviewWorker 的
        # 运行期动态属性（_thumb_worker_is_stale 用 getattr 读取），类里未声明。
        worker.thumb_gen = self._thumb_gen  # type: ignore[attr-defined]
        worker.metadata.connect(self._metadata_ready)
        worker.thumbnail_ready.connect(self._thumb_ready)
        worker.completed.connect(self._thumbs_completed)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)

    def _thumb_worker_is_stale(self) -> bool:
        """sender() 的代际号 ≠ 当前代际 → 旧文档的迟到信号，丢弃。"""
        gen = getattr(self.sender(), "thumb_gen", None)
        return gen is not None and gen != self._thumb_gen

    def _metadata_ready(self, page_count: int, _path: str) -> None:
        if self._thumb_worker_is_stale():
            return
        if self._thumb_total == page_count and self.strip.count() == page_count:
            # 后续轮次（回扫/补缺页）：页面项已经建好了，**不能清空重建**——
            # 那会把已经加载好的图标全丢掉，只剩占位符。
            return
        self.strip.clear()
        self._thumb_received = set()
        self._thumb_total = page_count
        self._last_cache_count = self._cached_thumbnail_count()
        for page in range(page_count):
            self.strip.add_page_item(f"第 {page + 1} 页", str(page))
        self.page_count_changed.emit(page_count)
        if page_count > 0:
            self._select_page(0, "0")

    def _thumb_ready(self, index: int, image) -> None:
        if self._thumb_worker_is_stale():
            return  # 旧文档的迟到页：绝不能画进新书的缩略条
        self._thumb_received.add(index)
        # 磁盘缓存为 256px；条目显示按图标尺寸降采样，控制大文档内存
        scaled = image.scaled(
            ThumbStrip.ICON_SIZE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.strip.set_item_icon(index, scaled, str(index), f"第 {index + 1} 页")

    def _missing_pages(self) -> list[int]:
        """还没拿到缩略图的页号，**离当前页近的排前面**（用户先看到先补上）。"""
        current = max(self.strip.currentRow(), 0)
        missing = [i for i in range(self._thumb_total) if i not in self._thumb_received]
        return sorted(missing, key=lambda i: (abs(i - current), i))

    def _on_rescan(self) -> None:
        """「别人在填缓存」期间每秒回扫一次：只把**新出现**的页读进来。

        连续 `RESCAN_STALL_ROUNDS` 轮没有新文件，就认为生产者已经不干了
        （导入失败/被取消/老任务），这一轮改成自己渲染缺页——渲染是按耗时
        让出 GIL 的（见 PreviewWorker），不会再把界面冻住。
        """
        if not self._pdf_path:
            self._rescan_timer.stop()
            return
        missing = self._missing_pages()
        if not missing:
            self._rescan_timer.stop()
            self._watching = False
            return
        count = self._cached_thumbnail_count()
        if count != self._last_cache_count:
            # 有新缩略图落盘 → 只读把它们读进来（不渲染、不抢 GIL）
            self._last_cache_count = count
            self._stall_rounds = 0
            self._start_thumb_pass(pages=missing, render_missing=False)
            return
        self._stall_rounds += 1
        if self._stall_rounds >= self.RESCAN_STALL_ROUNDS:
            self._rescan_timer.stop()
            self._watching = False
            # 生产者不干了：**只补当前可见窗口**，别把整本渲一遍
            self._fill_window()

    def _cached_thumbnail_count(self) -> int:
        """缓存目录里已有的缩略图数量（走 _cache_scan：一次 readdir，不解码）。"""
        return self._cache_scan()[0]

    def _thumbs_completed(self) -> None:
        """一轮跑完：只读 → 交给回扫；自己补 → 再核对一次窗口（防漏）。"""
        if self._thumb_worker_is_stale() or not self._pdf_path:
            return
        if self._pass_kind == "read":
            # 只读通道跑完：有人在填就回扫等新文件；没人填就自己补当前窗口
            if self._watching:
                if not self._rescan_timer.isActive():
                    self._rescan_timer.start()
            else:
                self._fill_window()
            return
        # 自己补完一轮：窗口里若还有漏（并发写/事件丢失），只重试一次
        if self._thumb_retried:
            return
        first, last = self.strip.visible_row_range()
        if last < first:
            first, last = 0, min(self._thumb_total - 1, self.FALLBACK_VISIBLE - 1)
        lo = max(0, first - self.FILL_WINDOW_MARGIN)
        hi = min(self._thumb_total - 1, last + self.FILL_WINDOW_MARGIN)
        if all(i in self._thumb_received for i in range(lo, hi + 1)):
            self._thumb_retried = False
            return
        self._thumb_retried = True
        self._fill_window()

    def _select_page(self, page: int, _path: str) -> None:
        if not self._pdf_path:
            return
        # ⚠️ 渲染密度在 GUI 线程先算好（worker 线程不得碰 QWidget）
        edge = self.view.preview_edge()
        cached = self._page_cache.get((page, edge))
        if cached is not None:
            # 缓存命中：QImage.fromData 实测 25ms，而重渲一页要 187ms 且**渲染
            # 途中攥着 GIL 105ms**（用户每点一次缩略图就卡一下）。顺序翻阅时
            # 由预取把邻居页填进缓存，点击就是"立刻出图"。
            self.view.set_image(QImage.fromData(cached))
            self._touch_page_cache(page, edge)
            self._prefetch_neighbors(page, edge)
            return
        self.view.clear_image(f"正在渲染第 {page + 1} 页...")
        # 连点多页：只有最后一次点击该上屏。序号跟着请求走——过期请求在
        # worker 拿到渲染锁后自己跳过（不渲染、不抢 GIL），就算抢在取消前
        # 渲完了，结果回主线程时也要过 seq 这一关，不许覆盖当前页。
        self._page_req_seq += 1
        seq = self._page_req_seq
        worker_path = self._pdf_path
        self.run_worker(
            lambda: self._make_page_worker(worker_path, page, edge, seq),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.finished,
                    lambda p, image, _s, w=worker, e=edge, q=seq: self._on_page_rendered(
                        w, p, image, e, q
                    ),
                    thread,
                ),
                connect_queued(
                    self,
                    worker.failed,
                    lambda _p, msg: self.view.clear_image(f"渲染失败：{msg}"),
                    thread,
                ),
                worker.skipped.connect(thread.quit),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _make_page_worker(self, path: Path, page: int, edge: int, seq: int):
        """造一条带过期判定的大图渲染请求。"""
        worker = PreviewWorker(path, page, longest_edge=edge)
        worker.is_stale = lambda s=seq: s != self._page_req_seq
        return worker

    # -------------------------------------------------------------- 页间缓存
    def _on_page_rendered(self, worker, page: int, image, edge: int,
                          seq: int = -1) -> None:
        """渲染完成：上屏、写缓存，并预取邻居页。

        ``seq`` 是发起这次渲染时的点击序号：对不上当前序号说明用户已经点了
        别的页——结果只进缓存（回看还有用），**不许上屏**覆盖当前页。
        """
        if seq != -1 and seq != self._page_req_seq:
            raw = getattr(worker, "last_jpeg", None)
            if raw:
                self._store_page_cache(page, edge, raw)
            return
        self.view.set_image(image)
        raw = getattr(worker, "last_jpeg", None)
        if raw:
            self._store_page_cache(page, edge, raw)
        self._prefetch_neighbors(page, edge)

    def _touch_page_cache(self, page: int, edge: int) -> None:
        """把刚命中的页挪到 LRU 队尾（最近使用）。"""
        key = (page, edge)
        if key in self._page_order:
            self._page_order.remove(key)
        self._page_order.append(key)

    def _store_page_cache(self, page: int, edge: int, raw: bytes) -> None:
        """写入页间缓存并按 LRU 上限淘汰（只存 JPEG 字节，约 300KB/页）。"""
        key = (page, edge)
        self._page_cache[key] = raw
        self._touch_page_cache(page, edge)
        while len(self._page_order) > self.PAGE_CACHE_MAX:
            old = self._page_order.pop(0)
            self._page_cache.pop(old, None)

    def _prefetch_neighbors(self, page: int, edge: int) -> None:
        """请邻居页（前后各一）进缓存，但**等用户停手 250ms 再开渲**。

        为什么不在页面上屏后立刻渲：预取也要拿单飞锁（渲染全程攥 GIL ~105ms），
        用户连点时会排在**他自己的下一次点击**前面——本该"点了就出图"，反而
        变成"先等预取渲完再渲染这一页"，比不预取还慢。等停手再渲，连点期间
        一次都不抢锁；停下来了才补缓存，顺序翻阅下一次点击就是缓存命中（25ms）。
        """
        self._prefetch_target = (page, edge)
        self._prefetch_timer.start(self.PREFETCH_IDLE_MS)

    def _start_prefetch(self) -> None:
        """真正发起预取：只渲**还没缓存**的邻居，且**同时最多一个**在飞。"""
        page, edge = self._prefetch_target
        if not self._pdf_path or self._prefetch_busy:
            return
        for candidate in (page + 1, page - 1):
            if not (0 <= candidate < self._thumb_total):
                continue
            if (candidate, edge) in self._page_cache:
                continue
            self._prefetch_busy = True
            worker_path = self._pdf_path
            self.run_worker(
                lambda p=candidate, e=edge: PreviewWorker(worker_path, p, longest_edge=e),
                lambda worker, thread, p=candidate, e=edge: (
                    connect_queued(
                        self,
                        worker.finished,
                        lambda _p, _image, _s, w=worker, pp=p, ee=e: self._prefetch_done(
                            w, pp, ee
                        ),
                        thread,
                    ),
                    connect_queued(
                        self,
                        worker.failed,
                        lambda *_a: self._prefetch_failed(),
                        thread,
                    ),
                    worker.finished.connect(thread.quit),
                    worker.failed.connect(thread.quit),
                ),
            )
            return

    def _prefetch_done(self, worker, page: int, edge: int) -> None:
        """预取完成：只进缓存，不动界面（用户看的那页已经上屏了）。"""
        raw = getattr(worker, "last_jpeg", None)
        if raw:
            self._store_page_cache(page, edge, raw)
        self._prefetch_busy = False

    def _prefetch_failed(self) -> None:
        self._prefetch_busy = False

    # -------------------------------------------------------------- 图片预览
    def _zoom_index(self) -> int:
        """放大弹窗当前页 = 缩略图条的当前行。"""
        return max(self.strip.currentRow(), 0)

    def _zoom_target(self, index: int) -> ZoomTarget | None:
        """第 index 页的图片预览来源。

        PDF 是矢量的，所以这里**不设 cap**：放大弹窗按视口密度反推渲染边长，
        密度越高越清晰（文字/线条不会像位图那样到顶）。
        """
        count = self.strip.count()
        pdf_path = self._pdf_path
        if not pdf_path or count <= 0 or not (0 <= index < count):
            return None
        return ZoomTarget(
            render=lambda edge: PreviewWorker(
                pdf_path, index, longest_edge=edge
            ),
            note=f"第 {index + 1}/{count} 页 · {pdf_path.name}",
            stem=f"{pdf_path.stem}_{index + 1}",
            count=count,
        )
