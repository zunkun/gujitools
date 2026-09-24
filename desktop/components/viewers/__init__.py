# -*- coding: utf-8 -*-
"""预览查看器组件：PDF 查看器、图片查看器、去底色/生成PDF 预览。

⚠️ **一律惰性导出**（PEP 562 模块级 ``__getattr__``）。

这里的查看器**全是详情页的**：PDF 预览（第一步）、图片查看器（第二步）、
去底色对比（第三步）、第四步效果预览与版面编辑画布。启动时用户看到的只是
任务列表页，一个都不需要。

Python 在导入子模块前一定会先执行父包的 ``__init__``，所以只要有人写
``from desktop.components.viewers.image_view import ImageView``，本文件就会
整体跑一遍、把这些重控件全部拖进启动。改成惰性后
``from desktop.components.viewers import ImageView`` 照旧可用，只是推迟到
真正取用的那一刻。
"""

__all__ = [
    "ImageView",
    "ImageZoomDialog",
    "ImageViewerWidget",
    "PdfViewerWidget",
    "PrintPreviewWidget",
    "RembgPreviewWidget",
    "ThumbStrip",
]

_LAZY = {
    "ImageView": ("desktop.components.viewers.image_view", "ImageView"),
    "ImageZoomDialog": (
        "desktop.components.viewers.image_zoom_dialog", "ImageZoomDialog",
    ),
    "ImageViewerWidget": (
        "desktop.components.viewers.image_viewer", "ImageViewerWidget",
    ),
    "PdfViewerWidget": ("desktop.components.viewers.pdf_viewer", "PdfViewerWidget"),
    "PrintPreviewWidget": (
        "desktop.components.viewers.print_preview", "PrintPreviewWidget",
    ),
    "RembgPreviewWidget": (
        "desktop.components.viewers.rembg_viewer", "RembgPreviewWidget",
    ),
    "ThumbStrip": ("desktop.components.viewers.thumb_strip", "ThumbStrip"),
}


def __getattr__(name: str):
    """按需导入查看器（PEP 562），并缓存进 globals 以免重复走导入系统。"""
    entry = _LAZY.get(name)
    if entry is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(entry[0]), entry[1])
    globals()[name] = value
    return value
