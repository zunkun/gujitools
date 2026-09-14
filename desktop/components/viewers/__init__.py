# -*- coding: utf-8 -*-
"""预览查看器组件：PDF 查看器、图片查看器、去底色/生成PDF 预览。"""

from desktop.components.viewers.image_view import ImageView
from desktop.components.viewers.image_viewer import ImageViewerWidget
from desktop.components.viewers.pdf_viewer import PdfViewerWidget
from desktop.components.viewers.print_preview import PrintPreviewWidget
from desktop.components.viewers.rembg_viewer import RembgPreviewWidget
from desktop.components.viewers.thumb_strip import ThumbStrip

__all__ = [
    "ImageView",
    "ImageViewerWidget",
    "PdfViewerWidget",
    "PrintPreviewWidget",
    "RembgPreviewWidget",
    "ThumbStrip",
]
