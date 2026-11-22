# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""统一变换：选项 / 轴心 / 限制 / 重塑开关。"""
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



class TransformOptionsMixin(CanvasHost):
    """统一变换：选项 / 轴心 / 限制 / 重塑开关。"""


    # ------------------------------------------------------------ 选项
    def set_transform_options(self, **options) -> None:
        """改统一变换的选项；认不出的键直接忽略（同 ``set_distortion_options``）。

        可用的键与取值范围见 ``consts.py``：``interpolation`` / ``clipping`` /
        ``direction`` / ``guide`` / ``show_preview`` / ``compose_preview`` /
        ``opacity``（0–100）/ ``constrain``+``value`` / ``pivot_op``+``value`` /
        ``snap_pivot`` / ``lock_pivot`` / ``auto_fit_canvas``。
        """
        interpolation = options.get("interpolation")
        if interpolation in {value for _label, value in INTERPOLATIONS}:
            self._xf_interpolation = interpolation
        clipping = options.get("clipping")
        if clipping in {value for _label, value in CLIPPINGS}:
            self._xf_clipping = clipping
        direction = options.get("direction")
        if direction in {value for _label, value in DIRECTIONS}:
            self._xf_direction = direction
        guide = options.get("guide")
        if guide in {value for _label, value in GUIDES}:
            self._xf_guide = guide
        if "show_preview" in options:
            self._xf_show_preview = bool(options["show_preview"])
        if "compose_preview" in options:
            self._xf_compose_preview = bool(options["compose_preview"])
        if "opacity" in options:
            self._xf_preview_opacity = max(
                0, min(100, int(options["opacity"])))
        if "snap_pivot" in options:
            self._xf_snap_pivot = bool(options["snap_pivot"])
        if "lock_pivot" in options:
            self._xf_lock_pivot = bool(options["lock_pivot"])
        if "auto_fit_canvas" in options:
            self._xf_auto_fit_canvas = bool(options["auto_fit_canvas"])
        op = options.get("constrain")
        if op in _CONSTRAIN_KEYS:
            self._xf_constraints[op] = bool(options.get("value", True))
        op = options.get("pivot_op")
        if op in _PIVOT_KEYS:
            self._xf_pivot_ops[op] = bool(options.get("value", True))
        self._sync_float()
        self._sync_overlay()

    def set_transform_about_pivot(self, about: bool) -> None:
        """「从轴心」总开关：三个动作（缩放/切变/透视）一起切。

        保留旧入口（自测与老调用方在用它）；面板上是**三个独立复选框**，
        走 :meth:`set_transform_pivot_op`。
        """
        self._xf_about_pivot = bool(about)
        if about:
            for op in _PIVOT_KEYS:
                self._xf_pivot_ops[op] = True

    def set_transform_pivot_op(self, op: str, on: bool) -> None:
        """「从轴心 (Ctrl)」单个动作：勾上后该动作以轴心为锚。"""
        if op in _PIVOT_KEYS:
            self._xf_pivot_ops[op] = bool(on)

    def set_transform_constraint(self, op: str, on: bool) -> None:
        """「限制 (Shift)」单个动作：移动 45° / 缩放等比 / 旋转 15° /
        切变贴边 / 透视沿对角线。"""
        if op in _CONSTRAIN_KEYS:
            self._xf_constraints[op] = bool(on)

    def set_transform_reshape(self, on: bool) -> None:
        """「调整范围」模式：拖手柄/边 = 收小变换区域，而不是缩放内容。

        进入时必须丢掉未应用的变换预览——浮层与填白底都是按**旧区域**
        快照做的，区域一变它们就与画布对不上了。退出（收边完成/取消
        勾选）后保留收小的区域，下一次拖动即以它为变换对象。
        """
        on = bool(on)
        if on and (self._xf_touched or self._float_item is not None):
            self._clear_transform_preview()
            self._xf = QTransform()
            self._xf_touched = False
        self._xf_reshape = on
        self._sync_overlay()
        self._sync_cursor()
