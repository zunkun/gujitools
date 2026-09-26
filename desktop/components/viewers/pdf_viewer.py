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
        #: 上一轮回扫看到的缓存文件数（用来判断"有没有新缩略图落盘"）
        self._last_cache_count = 0
        self._rescan_timer = QTimer(self)
        self._rescan_timer.setInterval(self.RESCAN_INTERVAL_MS)
        self._rescan_timer.timeout.connect(self._on_rescan)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.strip = ThumbStrip()
        self.strip.current_path_changed.connect(self._select_page)
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
        self._start_thumb_pass(render_missing=not self._watching)

    def _start_thumb_pass(self, pages: list[int] | None = None,
                         render_missing: bool = True) -> None:
        """跑一轮缩略图：``pages`` 限定页号，``render_missing`` 决定缺页渲不渲。"""
        self._pass_kind = "fill" if render_missing else "read"
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
        """缓存目录里最近有缩略图落盘 → 导入后台任务正在填它。

        判据只看 **mtime**，不看数量：导入任务是「先复制、再逐页写缩略图」，
        文件会持续变新；一旦它结束/失败/被取消，8 秒内不再有新文件，我们就
        接手补缺页（老任务、导入失败的场景都靠这条兜住）。
        """
        _count, newest = self._cache_scan()
        return bool(newest) and (time.time() - newest) < self.CACHE_ACTIVE_WINDOW_S

    def _wire_thumbnails(self, worker: PreviewWorker, thread) -> None:
        worker.metadata.connect(self._metadata_ready)
        worker.thumbnail_ready.connect(self._thumb_ready)
        worker.completed.connect(self._thumbs_completed)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)

    def _metadata_ready(self, page_count: int, _path: str) -> None:
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
        self._thumb_received.add(index)
        # 磁盘缓存为 256px；条目显示按图标尺寸降采样，控制大文档内存
        scaled = image.scaled(
            ThumbStrip.ICON_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
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
            self._start_thumb_pass(pages=missing, render_missing=True)

    def _cached_thumbnail_count(self) -> int:
        """缓存目录里已有的缩略图数量（走 _cache_scan：一次 readdir，不解码）。"""
        return self._cache_scan()[0]

    def _thumbs_completed(self) -> None:
        """一轮跑完：看是「只读」还是「自己补」，分别决定下一步。"""
        if not self._pdf_path:
            return
        if self._pass_kind == "read":
            # 只读通道跑完：交给回扫定时器（新文件会陆续出现）
            if self._watching and not self._rescan_timer.isActive():
                self._rescan_timer.start()
            return
        # 自己渲染缺页的那一轮：核对有没有漏（缓存被并发写入/事件丢失）
        if self._thumb_retried:
            return
        missing = [
            i for i in range(self.strip.count()) if i not in self._thumb_received
        ]
        if not missing:
            return
        self._thumb_retried = True
        self._start_thumb_pass(pages=self._missing_pages(), render_missing=True)

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
        if not self._pdf_path or count <= 0 or not (0 <= index < count):
            return None
        return ZoomTarget(
            render=lambda edge: PreviewWorker(
                self._pdf_path, index, longest_edge=edge
            ),
            note=f"第 {index + 1}/{count} 页 · {self._pdf_path.name}",
            stem=f"{self._pdf_path.stem}_{index + 1}",
            count=count,
        )
