# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""统一变换：轴心 / 限制 / 锚点计算。"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QLineF, QPointF, QRect, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QColor, QImage, QPainter, QPainterPath, QPixmap, QPolygonF, QTransform,
)
from PySide6.QtWidgets import QApplication, QGraphicsPixmapItem

from ...consts import (
    CLIPPINGS, CORNER_HANDLES, CORNER_HIT_VIEW_PX, CORNER_VIEW_PX, DIRECTIONS,
    EDGE_BAND_VIEW_PX, EDGE_HANDLE_MIN_VIEW_PX, GUIDE_RATIOS, GUIDES,
    HANDLE_HIT_VIEW_PX, INTERPOLATIONS, PERSP_HANDLES, PERSP_HIT_VIEW_PX,
    PERSP_INSET_VIEW_PX, PERSP_VIEW_PX, PIVOT_VIEW_PX, ROTATE_SNAP_DEG,
    SHEAR_AT, SHEAR_HANDLES, SHEAR_HIT_VIEW_PX, SHEAR_VIEW_PX, SIDE_HANDLES,
    SIDE_VIEW_PX, TRANSFORM_PREVIEW_PIXELS,
)
from ...geometry import (
    _dist_to_segment, clamp_rect, flip_transform, mapped_bounds, quad_point,
    quad_to_quad_transform, rotate_about, scale_about, shear_about,
    transform_region, warp_placement,
)
from ..overlay import _style_node
from .constants import (
    _CONSTRAIN_KEYS, _CORNER_NEIGHBOURS, _CORNER_UV, _EDGE_CORNERS, _EDGE_UV,
    _HANDLE_HITS, _PIVOT_KEYS, _SIDE_ANCHOR,
)
from .helpers import (
    _axis_ratio, _blank_image, _center_crop_rect, _diamond, _on_diagonal,
    _perspective_step, _snap_45,
)

if TYPE_CHECKING:
    from .._host import CanvasHost
else:
    CanvasHost = object



class TransformPivotMixin(CanvasHost):
    """统一变换：轴心 / 限制 / 锚点计算。"""


    def _pivot_ops(self) -> dict[str, bool]:
        """「从轴心」的三个开关（含旧的 ``_xf_about_pivot`` 总开关）。"""
        ops = dict(self._xf_pivot_ops)
        if self._xf_about_pivot:
            for op in _PIVOT_KEYS:
                ops[op] = True
        return ops

    def _constrain(self, op: str, modifiers) -> bool:
        """「限制」是否生效：勾选态 **异或** 按着 Shift（GIMP 口径）。

        GIMP 原文是"按住 Shift = 把没勾的勾上、勾了的取消"，所以这里必须
        用异或而不是"或"——勾了「缩放等比」时按住 Shift 反而要自由缩放。
        """
        return bool(self._xf_constraints.get(op, False)) != bool(
            modifiers & Qt.KeyboardModifier.ShiftModifier)

    def _from_pivot(self, op: str, modifiers) -> bool:
        """「从轴心」是否生效（Ctrl 同理：异或 ⇒ Ctrl 是临时取反）。"""
        return self._pivot_ops().get(op, False) != bool(
            modifiers & Qt.KeyboardModifier.ControlModifier)

    def _transform_side_anchor(self, edge: str) -> QPointF:
        """抓某条边做**单轴缩放**时的锚点 = 对边中点（选区局部坐标）。"""
        rect = self._transform_local_rect()
        assert rect is not None
        return _SIDE_ANCHOR[edge if edge in _SIDE_ANCHOR else "r"](rect)

    def _shear_anchor(self, edge: str) -> QPointF:
        """抓某条边上的**切变菱形**时的不动点（选区局部坐标）。

        正好对应用户给的切变口径「被抓的边不离开原边线」：抓左边时**右边整条
        不动**、抓上边时**下边整条不动**（GIMP 默认那档）。锚点取对边的
        **起点角一侧**——与 ``_EDGE_UV`` 的参数化起点同侧，菱形往哪边偏都
        不会让锚点跟着漂（锚点只由 "对边 + 该边起点角" 决定）。
        """
        rect = self._transform_local_rect()
        assert rect is not None
        if edge in ("l", "r"):
            anchor_x = rect.right() if edge == "l" else rect.left()
            return QPointF(anchor_x, rect.top())
        anchor_y = rect.bottom() if edge == "t" else rect.top()
        return QPointF(rect.left(), anchor_y)

    def _snap_pivot(self, point: QPointF) -> QPointF:
        """轴心吸附（「轴心 · 吸附」）：靠近中心/四角就贴上去。

        阈值按**视图像素**折算——缩得越小越容易吸附，与"眼睛看着差不多
        就吸上去"的直觉一致。
        """
        rect = self._xf_rect.normalized()
        threshold = PIVOT_VIEW_PX / max(self._zoom, 1e-6) * 1.5
        targets = [rect.center(), rect.topLeft(), rect.topRight(),
                   rect.bottomRight(), rect.bottomLeft()]
        nearest = min(targets, key=lambda t: QLineF(t, point).length())
        if QLineF(nearest, point).length() <= threshold:
            return QPointF(nearest)
        return point
