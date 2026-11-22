# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""统一变换：待定状态与快照捕获/恢复。"""
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



class TransformStateMixin(CanvasHost):
    """统一变换：待定状态与快照捕获/恢复。"""


    def make_transform_pending(self) -> None:
        """**挂起**这次变换：松手后保留预览，等离开工具再烘焙（GIMP 口径）。

        ⚠️ 这是"能不能实时预览"的关键（用户 2026-10-09 报障）：原来松手就把
        整幅重采样一遍（12 MP 约 11 秒），所以只能"最后才看到结果"。现在松手
        只是**记下"有东西没应用"**，内容继续由画布上的浮层实时显示——拖动中
        连像素都不重采样（见 :meth:`_apply_float_fast`），随便转多少圈都不用等。

        **例外**：选区的预览版大到连一帧都出不来时（:meth:`_realtime_budget`）
        就退回"松手即烘焙"——宁可慢一次，也不要拖不动的假实时。
        """
        if self.transform_pending() is None:
            return
        if not self._realtime_budget():
            self.transform_committed.emit()
            return
        self._xf_pending = True

    def has_pending_transform(self) -> bool:
        """有"已预览但还没烘焙"的变换？（弹窗据此在切工具/完成时收尾）"""
        return self._xf_pending and self.transform_pending() is not None

    def reset_transform_preview_flags(self) -> None:
        """取消"挂起"标记（松手后不烘焙那一支走这里），矩阵与预览都留着。"""
        self._xf_pending = False

    def capture_transform_state(self) -> dict:
        """保存当前图层的变换预览，以便切换活动图层时不必烘焙像素。"""
        image_fields = ("_xf_region", "_xf_preview_region",
                        "_xf_restore_region")
        state = {
            "_rect": None if self._rect is None else QRectF(self._rect),
            "_xf": QTransform(self._xf),
            "_xf_touched": self._xf_touched,
            "_xf_pending": self._xf_pending,
            "_xf_rect": (None if self._xf_rect is None
                         else QRectF(self._xf_rect)),
            "_xf_preview_scale": self._xf_preview_scale,
            "_xf_preview_direction": self._xf_preview_direction,
            "_xf_preview_keyframe": (
                None if self._xf_preview_keyframe is None
                else QTransform(self._xf_preview_keyframe)),
            "_xf_preview_origin": QPointF(self._xf_preview_origin),
            "_xf_base_origin": QPointF(self._xf_base_origin),
            "_xf_base_scale": (
                None if self._xf_base_scale is None
                else QPointF(self._xf_base_scale)),
            "_xf_paint_image": (
                None if self._paint_image is None else QImage(self._paint_image)),
            "_xf_base_pixmap": (
                None if self._item is None else self._item.pixmap()),
            "_xf_float_pixmap": (
                None if self._float_item is None
                else self._float_item.pixmap()),
            "_xf_restore_pending": self._xf_restore_pending,
            "_content_restore_done": getattr(
                self, "_content_restore_done", False),
            "_xf_pivot": QPointF(self._xf_pivot),
            "_xf_pivot_saved": (
                None if self._xf_pivot_saved is None
                else QPointF(self._xf_pivot_saved)),
            "_xf_direction": self._xf_direction,
            "_xf_clipping": self._xf_clipping,
            "_xf_interpolation": self._xf_interpolation,
        }
        for name in image_fields:
            value = getattr(self, name)
            state[name] = None if value is None else QImage(value)
        return state

    def restore_transform_state(self, state: dict | None) -> None:
        """恢复另一图层的挂起预览；不触发变换提交或像素重采样。"""
        if not state:
            return
        for name, value in state.items():
            setattr(self, name, value)
        self._xf_dragging = False
        if self._xf_rect is not None and self._xf_region is not None:
            assert self._item is not None
            self._paint_image = state["_xf_paint_image"]
            self._xf_base_origin = QPointF(state["_xf_base_origin"])
            self._xf_base_scale = (
                None if state["_xf_base_scale"] is None
                else QPointF(state["_xf_base_scale"]))
            base_pixmap = state["_xf_base_pixmap"]
            if base_pixmap is None:
                self._rebuild_backdrop()
            else:
                self._item.setPixmap(base_pixmap)
                self._item.setPos(self._xf_base_origin)
                self._item.setTransform(
                    QTransform() if self._xf_base_scale is None
                    else QTransform().scale(
                        self._xf_base_scale.x(), self._xf_base_scale.y()))
            self._float_item = QGraphicsPixmapItem()
            self._float_item.setTransformationMode(
                Qt.TransformationMode.SmoothTransformation)
            self._float_item.setZValue(5)
            self._scene.addItem(self._float_item)
            float_pixmap = state["_xf_float_pixmap"]
            if float_pixmap is not None:
                self._float_item.setPixmap(float_pixmap)
            self._sync_float()
        # 视图**不动**：切层不适配、不缩放、不重定位。
        self._sync_scene_rect()
        self._sync_border()
        self._sync_overlay()
