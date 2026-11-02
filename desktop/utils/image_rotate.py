# -*- coding: utf-8 -*-
"""逐页图片的旋转（Qt 侧）。

旋转角口径统一由 ``utils.page_layout.normalize_page_rotation`` 决定
（(-180, 180]，顺时针为正）——版面编辑器、效果预览、单页导出都调这里，
避免各自 `QTransform` 转出不同方向。

PDF 侧（``functions/print.py``）用 PIL 的 ``rotate`` 实现同一套角度，
两边都是"绕中心转、按外接框扩图"，只是位图后端不同。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QTransform

from utils.page_layout import normalize_page_rotation


def rotate_image(image: QImage, degrees) -> QImage:
    """按顺时针 ``degrees`` 旋转位图；0° 或空图原样返回。

    ``QImage.transformed`` 会按旋转后的包围盒自动调整尺寸/平移，不会裁掉
    角上的像素（与 PIL 的 ``expand=True`` 同一语义）；SmoothTransformation
    只在非直角角度才真正插值，直角转置是无损的。
    """
    angle = normalize_page_rotation(degrees)
    if angle == 0 or image is None or image.isNull():
        return image
    return image.transformed(
        QTransform().rotate(angle),
        Qt.TransformationMode.SmoothTransformation,
    )
