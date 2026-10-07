# -*- coding: utf-8 -*-
"""大图查看控件：随控件尺寸缩放，支持叠加切割框。

坐标基准是图片原始像素坐标（_image_size），与预览显示缩放无关。

开启 boxes_editable 后：
- 点击框选中（四角出现缩放手柄），拖动框内移动整框，拖手柄缩放；
- 在空白处按下并拖动可手绘一个新框；
- Delete/Backspace 删除选中框；
- 每次修改结束通过 boxes_edited 发出全部框（仅内存与信号，不落盘）。

reference_boxes 为参考框（如按 area/border 规则推导的最终裁剪大框），
橙色虚线显示，不参与编辑。
"""
from __future__ import annotations

from .core import ImageView
from .styles import (
    BOX_COLORS, BOX_NAMES, FULL_BOX_COLOR, FULL_BOX_NAME, FULL_INDEX,
    HANDLE_RADIUS, REFERENCE_COLOR, SIDE_INDEX, box_names, box_styles,
)

__all__ = [
    "ImageView", "box_styles", "box_names", "BOX_COLORS", "BOX_NAMES",
    "SIDE_INDEX", "FULL_INDEX", "FULL_BOX_NAME", "FULL_BOX_COLOR",
    "REFERENCE_COLOR", "HANDLE_RADIUS",
]
