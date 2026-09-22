# -*- coding: utf-8 -*-
"""导入后的一次性后台准备：**保住源文件副本 + 逐页渲染缩略图**。

命名与 PDF 预览查看器的页缩略图缓存一致（{page}.jpg，0 起始），
预览打开时直接命中缓存，不再重复渲染；该目录永不清理。

⚠️ 为什么两件事合在一个 worker 里
    它们都要读同一本大 PDF，且都必须与主线程隔离。拆成两个线程/两次任务
    只是多付一次线程与读盘成本；合在一起还能天然共用「刚复制好的副本」，
    不必再去打开用户磁盘上的原文件（原文件可能随时被移走/改名）。

⚠️ 为什么要每页 ``time.sleep(GIL_YIELD_MS)``
    PyMuPDF 渲染会长时间持有 GIL。多个渲染线程并行时，主线程的每一次文件
    操作都要排到 GIL 队列后面：实测主线程读一个 3KB 文件从 0.08ms 涨到
    111ms、``create_task`` 从 5ms 涨到 929ms（连导 16 次的中位）。
    每页让出一小段后回到 16ms；代价是整本渲染慢约 10%（2400 页多 7 秒），
    而这是纯后台任务，用户看不到。详见 ``.workbuddy/perf/``。
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from desktop.utils.files import THUMBNAIL_EDGE, copy_file_atomic

#: 每渲染一页后让出 GIL 的时长（毫秒）：给主线程留出连续执行的窗口。
#: 实测折中值（0 → 929ms、3ms → 16ms），别随手调大或删掉。
GIL_YIELD_MS = 3


class SourceThumbnailsWorker(QObject):
    """导入 PDF 后渲染全部页面缩略图（256px，与预览查看器缓存一致）。"""

    finished = Signal(str)  # 缩略图目录路径
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

        copy_to 给了就先把它复制成任务目录里的源文件副本（原子落地），**再从
        副本渲染**——源文件随后被移动/删除都不影响已导入的任务。
        """
        super().__init__()
        self.pdf_path = pdf_path
        self.out_dir = out_dir
        self.edge = edge
        self.copy_to = copy_to
        self._cancelled = False

    def cancel(self) -> None:
        """请求中止：渲染循环在下一页之前退出（关程序用，不必等整本跑完）。"""
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        """先落副本、再逐页渲染缩略图；任务目录被删时中止并报 failed。

        ⚠️ **每页先查缓存**：命名与预览查看器的缓存一致（``0001.jpg``），
        已存在且不比源 PDF 旧的直接跳过。否则重复导入同一份 PDF（或把任务
        目录复制过来）时，80 页的书要白渲染 80 页——用户看到的正是「明明
        已经有缩略图了还在重新生成」。
        """
        try:
            import fitz

            source = self.pdf_path
            if self.copy_to is not None:
                try:
                    source = copy_file_atomic(self.pdf_path, self.copy_to)
                except OSError as exc:
                    # 副本没落地不算失败：还能直接从原文件渲染缩略图
                    self.warning.emit(str(exc))
            try:
                pdf_mtime = source.stat().st_mtime
            except OSError:
                pdf_mtime = 0.0
            document = fitz.open(str(source))
            try:
                if document.page_count == 0:
                    raise ValueError("PDF 没有任何页面")
                self.out_dir.mkdir(parents=True, exist_ok=True)
                (self.out_dir / ".meta").write_text(str(self.edge))
                total = document.page_count
                self.progress.emit(0, total)  # 副本已落地、开始渲染
                for page_number in range(total):
                    if self._cancelled:
                        return
                    # 任务可能中途被删除，此时停止写盘，避免残留目录
                    if not self.out_dir.parent.parent.is_dir():
                        raise FileNotFoundError("任务目录已不存在，中止缩略图生成")
                    # 1 起始、四位补零：与预览查看器缓存命名一致，资源管理器自然排序
                    target = self.out_dir / f"{page_number + 1:04d}.jpg"
                    if target.exists():
                        try:
                            if target.stat().st_mtime >= pdf_mtime:
                                continue  # 缓存可用，跳过渲染
                        except OSError:
                            pass
                    page = document.load_page(page_number)
                    rect = page.rect
                    scale = self.edge / max(rect.width, rect.height)
                    pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(scale, scale), alpha=False
                    )
                    data = pixmap.tobytes("jpg", jpg_quality=80)
                    target.write_bytes(data)
                    self.progress.emit(page_number + 1, total)
                    # 让出 GIL：否则主线程（列表回程、点按钮）会被拖住
                    if GIL_YIELD_MS:
                        time.sleep(GIL_YIELD_MS / 1000)
            finally:
                document.close()
            self.finished.emit(str(self.out_dir))
        except Exception as exc:
            self.failed.emit(str(exc))
