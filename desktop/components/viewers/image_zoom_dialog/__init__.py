# -*- coding: utf-8 -*-
"""图片预览弹窗：拖拽平移、滚轮/按钮缩放、翻转旋转、下载、翻页。

为什么不把缩放直接做在 ``ImageView`` 上：那是**框编辑**画布——点击选中、
拖拽移动整框、四角缩放、空白拖拽手绘。再叠一层"滚轮缩放 + 拖拽平移"，
两种拖拽立刻打架（拖框 vs 拖画布），而框坐标是 detect/rembg 的实际输出依据，
误操作代价高。所以编辑仍留在原处（固定"适应窗口"），弹窗只做**只读**查看。

渲染密度由弹窗自己算（``_render_edge``：视口物理长边 × ``RENDER_HEADROOM``，
再受宿主给的 ``ZoomTarget.cap`` 与 :data:`MAX_RENDER_EDGE` 约束），宿主只提供
``render(edge) -> worker``。这样「图片按最长边解码」「PDF 按该边长渲染」
「打印效果按该边长反推 px/mm 重新排版」三种口径各归各家，弹窗不必区分。

⚠️ 缩放倍率的语义：**1.0 = 100% = 1 图片像素对 1 设备像素**（QGraphicsView 的
变换比例 = 倍率 ÷ dpr）。所以场景里的 pixmap 刻意**不设** devicePixelRatio
（1 场景单位 = 1 图片像素），否则这套换算会再叠一个 dpr。
"""
from __future__ import annotations

from .canvas import ZoomTarget, ZoomableCanvas
from .consts import (
    ICON_COLOR, JPEG_QUALITY, MAX_RENDER_EDGE, MAX_ZOOM, MIN_RENDER_EDGE,
    MIN_ZOOM, OVERWRITE_FORMATS, OVERWRITE_JPEG_QUALITY, PAN_MARGIN_RATIO,
    RENDER_HEADROOM, WHEEL_STEP, ZOOM_DIALOG_SIZE, ZOOM_STOPS,
)
from .dialog import ImageZoomDialog
from .icons import display_transform, flip_icon, mirrored_rotate_icon
from .io import overwrite_image_file, save_image
from .popup import ZoomPopupMixin

__all__ = [
    "ImageZoomDialog", "ZoomPopupMixin", "ZoomTarget", "ZoomableCanvas",
    "display_transform", "flip_icon", "mirrored_rotate_icon",
    "overwrite_image_file", "save_image",
    "ZOOM_STOPS", "MIN_ZOOM", "MAX_ZOOM", "WHEEL_STEP", "RENDER_HEADROOM",
    "MIN_RENDER_EDGE", "MAX_RENDER_EDGE", "JPEG_QUALITY", "PAN_MARGIN_RATIO",
    "ICON_COLOR", "OVERWRITE_JPEG_QUALITY", "OVERWRITE_FORMATS",
    "ZOOM_DIALOG_SIZE",
]
