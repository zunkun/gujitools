# -*- coding: utf-8 -*-
"""PDF 查看器：左侧页面缩略图 + 右侧大图。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
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
        self._thumb_retried = False
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
        命中则直接使用，缺失的页渲染后补写。"""
        self._pdf_path = path
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._thumb_received = set()
        self._thumb_retried = False
        self.strip.clear()
        self.close_zoom_popup()  # 换 PDF 了：弹窗里那页是旧文档
        text = placeholder or (path.name if path else "暂无 PDF")
        if path is None or not Path(path).exists():
            self.view.clear_image(text)
            self.strip.add_placeholder(text)
            return
        self.view.clear_image("正在加载 PDF...")
        self.strip.add_placeholder("缩略图加载中...")
        worker_path = Path(path)
        worker_cache = self._cache_dir
        self.run_worker(
            lambda: PreviewWorker(worker_path, thumbnails=True, cache_dir=worker_cache),
            self._wire_thumbnails,
        )

    def _wire_thumbnails(self, worker: PreviewWorker, thread) -> None:
        worker.metadata.connect(self._metadata_ready)
        worker.thumbnail_ready.connect(self._thumb_ready)
        worker.completed.connect(self._thumbs_completed)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)

    def _metadata_ready(self, page_count: int, _path: str) -> None:
        self.strip.clear()
        self._thumb_received = set()
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

    def _thumbs_completed(self) -> None:
        """完成后核对：如有页面没收到缩略图（缓存被并发写入/事件丢失），重跑一次。"""
        if self._thumb_retried or not self._pdf_path:
            return
        missing = [
            i for i in range(self.strip.count()) if i not in self._thumb_received
        ]
        if not missing:
            return
        self._thumb_retried = True
        self.run_worker(
            lambda: PreviewWorker(
                self._pdf_path, thumbnails=True, cache_dir=self._cache_dir
            ),
            self._wire_thumbnails,
        )

    def _select_page(self, page: int, _path: str) -> None:
        if not self._pdf_path:
            return
        self.view.clear_image(f"正在渲染第 {page + 1} 页...")
        # ⚠️ 渲染密度在 GUI 线程先算好（worker 线程不得碰 QWidget）
        edge = self.view.preview_edge()
        self.run_worker(
            lambda: PreviewWorker(self._pdf_path, page, longest_edge=edge),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.finished,
                    lambda p, image, _s: self.view.set_image(image),
                    thread,
                ),
                connect_queued(
                    self,
                    worker.failed,
                    lambda _p, msg: self.view.clear_image(f"渲染失败：{msg}"),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

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
