# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""统一变换：覆盖层 / 焦点环 / 参考线同步。"""
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



class TransformGuidesMixin(CanvasHost):
    """统一变换：覆盖层 / 焦点环 / 参考线同步。"""


    # ------------------------------------------------------------ 覆盖层
    def _sync_transform_overlay(self) -> None:
        """变换工具的覆盖层：四边形选框 + 四类手柄（跟随矩阵变形）+ 轴心。

        ⚠️ 虚线框**只有一个**：跟着内容转的 ``_quad``。固定在原位的 ``_border``
        保留、但画成**细实线**（见 ``core._border_pen``）——它是"这张纸的边界"，
        不再是第二条虚线（用户 2026-10-09 报障「同时存在两个框的虚线、颜色还不
        一样」）。
        """
        for item in self._mask:
            item.setVisible(False)
        self._sel_border.setVisible(False)
        for item in self._edge_lines.values():
            item.setVisible(False)
        corners = self._transform_quad()
        quad = QPolygonF([corners["tl"], corners["tr"],
                          corners["br"], corners["bl"], corners["tl"]])
        self._quad.setPolygon(quad)
        self._quad.setVisible(True)
        zoom = max(self._zoom, 1e-6)
        points = self._transform_handle_points()
        square = CORNER_VIEW_PX / zoom
        for name in CORNER_HANDLES:
            point = points[name]
            self._handles[name].setRect(
                QRectF(point.x() - square / 2, point.y() - square / 2,
                       square, square))
            self._handles[name].setVisible(True)
        active = self._edge_handles_active(corners)
        side = SIDE_VIEW_PX / zoom
        for name in SIDE_HANDLES:
            point = points[name]
            self._handles[name].setRect(
                QRectF(point.x() - side / 2, point.y() - side / 2, side, side))
            self._handles[name].setVisible(active)
        shear = SHEAR_VIEW_PX / 2.0 / zoom
        for name in SHEAR_HANDLES:
            self._diamonds[name].setPolygon(_diamond(points[name], shear))
            self._diamonds[name].setVisible(active)
        persp = PERSP_VIEW_PX / 2.0 / zoom
        for name in PERSP_HANDLES:
            self._persp[name].setPolygon(_diamond(points[name], persp))
            self._persp[name].setVisible(True)
        # 节点底色：**默认中空，只有"当前节点"实心**（用户 2026-10-09：「操作
        # 节点未选中不要有背景色，拉伸方块不要用绿色，而是中空的」）。四类节点
        # 共用一套配色，形状才是语义（方框=缩放、菱形=切变/透视）。
        # ⚠️ 透视小菱形与角方框**同心**（``PERSP_INSET_VIEW_PX == 0``），两者
        # 是"同一个角"的两张脸 ⇒ 焦点在角（``tl``）或菱形（``p_tl``）上时
        # **一起实心**，否则"点亮了角、嵌在角里的菱形还是空的"看着像两个东西。
        focus = self._focus_handle
        focus_key = focus[2:] if focus and focus.startswith("p_") else focus
        for group in (self._handles, self._diamonds, self._persp):
            for name, item in group.items():
                key = name[2:] if name.startswith("p_") else name
                _style_node(item, focus_key is not None and key == focus_key)
        self._sync_focus_ring(points, active, zoom)
        pivot = self._visual_xf().map(self._xf_pivot)
        radius = PIVOT_VIEW_PX / 2.0 / zoom
        self._pivot_item.setRect(
            QRectF(pivot.x() - radius, pivot.y() - radius,
                   radius * 2, radius * 2))
        self._pivot_item.setVisible(True)
        self._sync_transform_guides(corners)

    def _sync_focus_ring(self, points: dict[str, QPointF], edges_active: bool,
                         zoom: float) -> None:
        """把"激活节点"的高亮环套到当前节点上（没激活就藏起来）。

        环按**节点自己的形状**留出余量：方框套方环（比它大一圈）、菱形/透视
        小菱形也套方环（菱形外接框再放宽一点），轴心圆点套小方环。这样无论
        哪类节点被点中都看得见"亮的是它"。
        """
        name = self._focus_handle
        if not name:
            self._focus_ring.setVisible(False)
            return
        margin = 5.0 / zoom
        if name in CORNER_HANDLES:
            size = CORNER_VIEW_PX
        elif name in SIDE_HANDLES:
            if not edges_active:
                self._focus_ring.setVisible(False)
                return
            size = SIDE_VIEW_PX
        elif name in SHEAR_HANDLES:
            if not edges_active:
                self._focus_ring.setVisible(False)
                return
            size = SHEAR_VIEW_PX
        elif name in PERSP_HANDLES:
            size = PERSP_VIEW_PX
        elif name == "pivot":
            size = PIVOT_VIEW_PX
        else:
            self._focus_ring.setVisible(False)
            return
        half = (size / max(zoom, 1e-6)) / 2.0 + margin
        point = (self._visual_xf().map(self._xf_pivot) if name == "pivot"
                 else points.get(name))
        if point is None:
            self._focus_ring.setVisible(False)
            return
        self._focus_ring.setRect(
            QRectF(point.x() - half, point.y() - half, half * 2, half * 2))
        self._focus_ring.setVisible(True)

    def _sync_transform_guides(self, corners: dict[str, QPointF]) -> None:
        """按选项画构图参考线（三分/五分/黄金分割/对角线）——跟着框一起变形。"""
        for item in self._guides:
            item.setVisible(False)
        ratios = GUIDE_RATIOS.get(self._xf_guide)
        if ratios:
            entries = ([("h", ratio) for ratio in ratios]
                       + [("v", ratio) for ratio in ratios])
        elif self._xf_guide == "diagonal":
            entries = [("d", 0.0), ("d", 1.0)]
        else:
            return
        for item, (kind, ratio) in zip(self._guides, entries):
            if kind == "h":
                start, end = (quad_point(corners, 0.0, ratio),
                              quad_point(corners, 1.0, ratio))
            elif kind == "v":
                start, end = (quad_point(corners, ratio, 0.0),
                              quad_point(corners, ratio, 1.0))
            else:
                start, end = (quad_point(corners, 0.0, ratio),
                              quad_point(corners, 1.0, 1.0 - ratio))
            item.setLine(QLineF(start, end))
            item.setVisible(True)
