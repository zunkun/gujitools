# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""统一变换：命中测试。"""
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



class TransformHitMixin(CanvasHost):
    """统一变换：命中测试。"""


    # ------------------------------------------------------------ 命中
    def _hit_transform(self, view_pos: QPointF) -> str:
        """统一变换的命中测试（视图像素口径，不随缩放变）。

        **节点优先、绝不冒泡**（用户 2026-10-09 明确要求：点节点就必须是那个
        节点，不能掉进"移动图片"或"旋转"）。优先级：

        轴心 → **透视小菱形** → **四角大方框** → **四边中方框** →
        **切变菱形** → 整条边（顺手抓边＝单轴缩放）→ 框内（移动）→ 框外（旋转）。

        ⚠️ 两个"必须"：
        1. 透视小菱形排在角方框**之前**——它嵌在角方框里。两类手柄**同心**
           （用户 2026-10-09 口径：「四个边角的菱形要在方块正中心」）之后，
           "角点归谁"改由**半径**分：离角点 ≤ ``PERSP_HIT_VIEW_PX`` ⇒ 透视，
           再往外到 ``CORNER_HIT_VIEW_PX`` 的方形环带 ⇒ 双轴缩放（方框描边
           那一圈仍点得着缩放，两类手柄互不抢）；
        2. 切变菱形排在**整条边命中带之前**——边带是 8px 的带状区域，菱形正好
           落在带内，顺序反了切变就永远点不着。
        """
        if self._rect is None:
            return "outside"
        corners = self._transform_quad()
        pivot_view = QPointF(self.mapFromScene(
            self._visual_xf().map(self._xf_pivot)))
        if QLineF(view_pos, pivot_view).length() <= PIVOT_VIEW_PX / 2.0 + 3.0:
            return "pivot"
        if not self._xf_reshape:
            points = self._transform_handle_points()
            keys = {name: QPointF(self.mapFromScene(point))
                    for name, point in points.items()}
            radius = HANDLE_HIT_VIEW_PX
            for name in PERSP_HANDLES:
                if QLineF(view_pos, keys[name]).length() <= PERSP_HIT_VIEW_PX:
                    return name
            for name in CORNER_HANDLES:
                point = keys[name]
                if abs(view_pos.x() - point.x()) <= CORNER_HIT_VIEW_PX \
                        and abs(view_pos.y() - point.y()) <= CORNER_HIT_VIEW_PX:
                    return name
            if self._edge_handles_active(corners):
                for name in SIDE_HANDLES:
                    if QLineF(view_pos, keys[name]).length() <= radius + 2.0:
                        return name
                for name in SHEAR_HANDLES:      # 必须先于下面的整条边命中带
                    if QLineF(view_pos, keys[name]).length() \
                            <= SHEAR_HIT_VIEW_PX:
                        return name
                # 整条边都在命中带里（抓边 = 单轴缩放，与裁剪的手感一致）
                for name, (a, b) in _EDGE_CORNERS.items():
                    if _dist_to_segment(view_pos, keys[a], keys[b]) \
                            <= EDGE_BAND_VIEW_PX:
                        return name
        scene = self.mapToScene(view_pos.toPoint())
        quad = QPolygonF([corners["tl"], corners["tr"],
                          corners["br"], corners["bl"]])
        if quad.containsPoint(scene, Qt.FillRule.OddEvenFill):
            return "inside"
        return "outside"
