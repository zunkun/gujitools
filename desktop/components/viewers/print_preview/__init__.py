# -*- coding: utf-8 -*-
"""PDF排版（print）预览：左侧缩略图条 + 右侧单页效果预览。

布局与前三步保持一致（``ImageViewerWidget`` / ``RembgPreviewWidget`` 的
「左缩略图 + 右大图」），右侧不再是网格瀑布流：

- **打印效果**：按右侧表单参数（纸张/方向/边距/标题/页码）把图片排进一
  张纸里给用户在屏幕上看到——**只是效果，不执行、不提交、不生成 PDF**；
- **原图**：待打印图片本身（第三步「提交本次任务」的最终图）。

几何全部来自 ``utils.page_layout.plan_print_page``，而真正生成 PDF 的
``functions/print.py`` 用的是同一个函数，所以预览与成品不会漂移。

缩略图默认用条目图片本身（``ImageListWorker`` 走 QImageReader 缩放解码，
等于现算缩略图）；传入 ``thumb_provider`` 时改用它给出的预生成小图。
"""
from __future__ import annotations

from .widget import PrintPreviewWidget

__all__ = ["PrintPreviewWidget"]
