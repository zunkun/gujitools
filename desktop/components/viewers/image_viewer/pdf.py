# -*- coding: utf-8 -*-
"""``ImageViewerWidget`` Mixin：**PDF 页源**。

把 PDF 页当图片源（懒渲染 + 缓存）。（从 ``image_viewer.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt
from desktop.workers import PreviewWorker, connect_queued
from desktop.components.viewers.thumb_strip import ThumbStrip
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import ImageViewerHost
else:
    ImageViewerHost = object


class PdfSourceMixin(ImageViewerHost):
    """把 PDF 页当图片源（懒渲染 + 缓存）。"""

    def set_pdf_source(
        self, pdf: Path | str, cache_dir: Path | None = None, gen: int = 0,
    ) -> None:
        """源是一本 **PDF**：左栏显示它的页缩略图，右侧大图按需渲高清页。

        这是「图片提取」页未提取时的形态（用户 2026-10-03：「在未提取图片之前
        是按照缩略图，单独图片显示」）——选完 PDF 就能翻页看，不必先跑一遍提取。

        ⚠️ 缩略图条显示的是 256px 缓存小图，但**右侧大图不是拿小图放大**：
        点哪页就按需从 PDF 渲那一页（``_select_image`` 见 ``_page_source``），
        所以放大事先看得清。缩略图由宿主用
        :class:`~desktop.modules.thumb_source.ThumbSourceMixin` 起 pass 填充，
        本方法只负责建条目（:meth:`begin_pdf_pages`）。

        ``gen`` 是代际号：换书时宿主递增，本控件据此丢弃旧书迟到的缩略图信号。
        """
        self._clear_page_source()
        self._page_source = (Path(pdf), gen)
        self._page_source_cache = Path(cache_dir) if cache_dir else None
        self._thumb_provider = None
        self._thumb_cache_dir = None
        self._thumb_cache_ready = {}
        self._thumb_cache_names = None
        self._paths = []
        self.close_zoom_popup()
        self.view.clear_image("正在加载缩略图…")
        self.strip.clear()
        self.strip.add_placeholder("缩略图生成中…")
        self.info_label.setText("")


    def begin_pdf_pages(self, count: int, path: str = "") -> None:
        """PDF 页数已known：按「第 N 页」建缩略图条目并选中第一页。

        ⚠️ 与 ``PdfViewerWidget._metadata_ready`` 同一道护栏：后续轮次
        （回扫/补缺页）页数没变时**不能清空重建**——那会把已经加载好的图标
        全丢掉，只剩占位符。
        """
        if self._page_source is None or count <= 0:
            return
        if self.strip.count() == count:
            return
        self.strip.clear()
        self._paths = []
        for page in range(count):
            self.strip.add_page_item(f"第 {page + 1} 页", str(page))
        self.strip.setCurrentRow(0)
        self._select_pdf_page(0)


    def set_pdf_thumb(self, gen: int, index: int, image) -> None:
        """PDF 第 index 页的缩略图就绪：填进缩略图条第 index 条。

        ``gen`` 与 :meth:`set_pdf_source` 传的一致才算数——旧书那个还在跑的
        worker 迟到时会被丢弃，否则**旧书的页会画进新书的缩略图条**。
        """
        if self._page_source is None or gen != self._page_source[1]:
            return
        if not (0 <= index < self.strip.count()):
            return
        if image is None or getattr(image, "isNull", lambda: True)():
            return
        scaled = image.scaled(
            ThumbStrip.ICON_SIZE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.strip.set_item_icon(
            index, scaled, str(index), f"第 {index + 1} 页"
        )


    def _clear_page_source(self) -> None:
        """退出 PDF 页模式（提取完成 → 换成提取出的图片）。"""
        self._page_source = None
        self._page_source_cache = None


    def _select_pdf_page(self, index: int) -> None:
        """按需渲 PDF 第 index 页的高清大图（未命中页间缓存时）。"""
        if self._page_source is None:
            return
        if not (0 <= index < self.strip.count()):
            return
        self.strip.setCurrentRow(index)
        self._load_token += 1
        token = self._load_token
        pdf = self._page_source[0]
        self.view.clear_image(f"正在渲染第 {index + 1} 页...")
        # ⚠️ 渲染密度在 GUI 线程先算好：worker 线程里碰 QWidget 是越界的
        edge = self.view.preview_edge()
        self.run_worker(
            lambda: PreviewWorker(pdf, page=index, longest_edge=edge),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.finished,
                    lambda page, image, _p, t=token: (
                        self._pdf_page_ready(t, image)
                    ),
                    thread,
                ),
                connect_queued(
                    self,
                    worker.failed,
                    lambda _p, msg, t=token: self._pdf_page_failed(t, msg),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )
        self.current_changed.emit(index, str(index))


    def _pdf_page_ready(self, token: int, image) -> None:
        """PDF 高清页就绪：只有最新一次选页的结果允许上屏。"""
        if token != self._load_token:
            return  # 用户已经点了别的页：迟到的旧页不上屏
        self.view.set_image(image)
        row = max(self.strip.currentRow(), 0)
        total = self.strip.count()
        self.info_label.setText(
            f"第 {row + 1}/{total} 页 · 缩略图预览"
            if total else ""
        )


    def _pdf_page_failed(self, token: int, message: str) -> None:
        if token != self._load_token:
            return
        self.view.clear_image(f"渲染失败：{message}")
