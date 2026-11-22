# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""统一变换的纯函数工具（从 ``canvas/transform.py`` 拆出）。"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QImage, QPolygonF, QTransform

from ...geometry import mapped_bounds, quad_to_quad_transform


def _axis_ratio(current: float, origin: float, anchor: float) -> float:
    """一维缩放比：``anchor`` 不动，``origin`` 跟到 ``current`` 时的倍率。

    ``|origin - anchor|`` 太小时给 1.0（抓在锚点上没法定义倍率）；
    倍率夹在 ±1e-3 之外——放到 0 会让矩阵不可逆，预览与烘焙一起消失。
    """
    span = origin - anchor
    if abs(span) < 1e-6:
        return 1.0
    ratio = (current - anchor) / span
    if abs(ratio) < 1e-3:
        return 1e-3 if ratio >= 0 else -1e-3
    return ratio


def _snap_45(delta: QPointF) -> QPointF:
    """把位移吸附到 45° 的整数倍（「限制」里的移动约束）。"""
    length = math.hypot(delta.x(), delta.y())
    if length < 1e-6:
        return delta
    angle = math.degrees(math.atan2(delta.y(), delta.x()))
    snapped = round(angle / 45.0) * 45.0
    radians = math.radians(snapped)
    return QPointF(length * math.cos(radians), length * math.sin(radians))


def _blank_image() -> QImage:
    """1×1 的**全透明**图 —— 「整幅选区」的底图就是这么一片"空"。

    配 ``_xf_base_scale`` 用图元缩放拉成目标大小：换尺寸只是改个矩阵，
    不会为了每个新尺寸新建一张 12 MP 的白图（那正是"旋转卡"的来源之一）。

    ⚠️ 它**曾经是纯白**的：整幅选区时它就是那张"白纸"，也就是用户 2026-10-09
    报的「旋转后白底一直涨、还在漂」。现在整幅选区 = 内容整块被搬走 = 原位**空**，
    所以填透明，露出的画布条纹格才说得通（口径：不再有任何白色区域）。
    """
    image = QImage(1, 1, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    return image


def _center_crop_rect(rect: QRectF, width: int, height: int) -> QRectF:
    """:func:`geometry.center_crop_aspect` 的**矩形版**（预览与烘焙裁同一块）。

    取整必须与那边一致（``int(round(...))`` + ``//2``），否则预览的"纸"和
    烘焙出来的画布会差一两个像素，边缘看着像抖了一下。
    """
    if rect.isEmpty() or width <= 0 or height <= 0:
        return rect
    target = width / height
    if rect.width() / rect.height() > target:
        new_w = float(max(1, min(int(round(rect.height() * target)),
                                 int(rect.width()))))
        return QRectF(rect.x() + math.floor((rect.width() - new_w) / 2),
                      rect.y(), new_w, rect.height())
    new_h = float(max(1, min(int(round(rect.width() / target)),
                             int(rect.height()))))
    return QRectF(rect.x(),
                  rect.y() + math.floor((rect.height() - new_h) / 2),
                  rect.width(), new_h)


def _on_diagonal(quad: list[QPointF], index: int, target: QPointF) -> QPointF:
    """把 ``target`` 拉到"对角 → 本角"这条直线上（透视的 Shift 约束）。

    GIMP 口径：勾了「限制 · 透视」时手柄**只能沿边或对角线走**，于是拖动
    只会改变单方向的透视强度，不会同时把两条边一起拽歪。
    """
    opposite = quad[(index + 2) % 4]
    origin = quad[index]
    span = QPointF(origin.x() - opposite.x(), origin.y() - opposite.y())
    length_sq = span.x() * span.x() + span.y() * span.y()
    if length_sq < 1e-9:
        return target
    step = QPointF(target.x() - opposite.x(), target.y() - opposite.y())
    ratio = max(0.05, (step.x() * span.x() + step.y() * span.y()) / length_sq)
    return QPointF(opposite.x() + span.x() * ratio,
                   opposite.y() + span.y() * ratio)


def _perspective_step(xf_start: QTransform, quad: list[QPointF], index: int,
                      target: QPointF, rect: QRectF) -> QTransform | None:
    """"把 ``quad`` 的第 ``index`` 个角挪到 ``target``"这一步的矩阵。

    **病态的一步返回 ``None``**（调用方当"这一步没发生"，手柄就此停住——
    同 GIMP：透视手柄拖不过对角）。

    ⚠️⚠️ 旧版只靠 ``quad_to_quad_transform`` 拦"四点**共线**"，可**近**共线
    （把 tl 拖到 br 附近、或拖成自交的蝴蝶结）时 ``quadToQuad`` 照样返回一个
    "可逆"的矩阵——它把内容放大百万倍以上，外框实测 4.8e17。后果是
    ``warp_region`` 拒绝（>40 MP）后预览**回落到 QPainter 兜底**，
    ``QImage(2.18e9, 1.49e9)`` 直接 OverflowError，整个编辑器崩掉
    （用户 2026-10-09 报的正是这个）。所以这里补一道**几何合理性**判据：
    这一步算完，选区必须还被映在一个"人能用"的外框里
    （``geometry.mapped_bounds``，与重采样同一道闸）。
    """
    new_quad = list(quad)
    new_quad[index] = QPointF(target)
    step = quad_to_quad_transform(quad, new_quad)
    if step is None:
        return None                        # 四点共线 / 重合：本来就不动
    if mapped_bounds(xf_start * step, rect) is None:
        return None                        # 自交 / 塌陷 ⇒ 外框天文数字：不动
    return step


def _diamond(center: QPointF, radius: float) -> QPolygonF:
    """以 ``center`` 为中心、半对角线为 ``radius`` 的菱形（切变/透视手柄）。"""
    return QPolygonF([
        QPointF(center.x(), center.y() - radius),
        QPointF(center.x() + radius, center.y()),
        QPointF(center.x(), center.y() + radius),
        QPointF(center.x() - radius, center.y()),
    ])
