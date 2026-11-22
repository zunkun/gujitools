# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""统一变换：语义操作入口（移动/旋转/缩放/切变/透视/翻转）。"""
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



class TransformOperationsMixin(CanvasHost):
    """统一变换：语义操作入口（移动/旋转/缩放/切变/透视/翻转）。"""


    # ---- 变换操作（拖拽处理器与自测共用的语义级入口） ----
    def transform_move(self, dx: float, dy: float) -> None:
        """整体平移 ``dx, dy``（图片像素，**视觉方向**）。"""
        self._ensure_transform_preview()
        # 先已有的变换，再平移：(T * Move) 先 T 后 Move
        self._apply_visual(
            self._visual_xf() * QTransform().translate(dx, dy))

    def transform_rotate(self, degrees: float) -> None:
        """绕**轴心当前视觉位置**旋转（轴心保持不动）。

        ⚠️ 在**视觉空间**里叠旋转：校正（向后）模式下内容与框也同向转
        （旧版直接转 ``_xf`` ⇒ 图片和操作框方向相反，用户 2026-10-09 报障）。
        """
        self._ensure_transform_preview()
        visual = self._visual_xf()
        center = visual.map(self._xf_pivot)
        self._apply_visual(visual * rotate_about(center, degrees))

    def transform_scale(self, sx: float, sy: float,
                        anchor: QPointF | None = None) -> None:
        """缩放（局部空间，锚点缺省=轴心；sx/sy 是相对当前内容的倍率）。"""
        self._ensure_transform_preview()
        point = QPointF(anchor) if anchor is not None else self._xf_pivot
        sx = sx if abs(sx) > 1e-6 else 1.0
        sy = sy if abs(sy) > 1e-6 else 1.0
        # 局部操作发生在视觉矩阵**之前**：(S * V) 先 S 后 V
        self._apply_visual(scale_about(point, sx, sy) * self._visual_xf())

    def transform_scale_axis(self, edge: str, factor: float,
                             anchor: QPointF | None = None) -> None:
        """**单轴**缩放：抓 ``edge``（l/r/t/b）方向的边，只改这一个轴。

        这是统一变换相对"只能整体放大缩小"的关键补充：横拉左边=只改宽度、
        竖拉上边=只改高度。锚点缺省 = 对边中点（拖动时锚在轴心）。
        """
        rect = self._transform_local_rect()
        if rect is None:
            return
        if edge not in _SIDE_ANCHOR:
            edge = "r"
        point = (QPointF(anchor) if anchor is not None
                 else _SIDE_ANCHOR[edge](rect))
        factor = factor if abs(factor) > 1e-3 else 1e-3
        if edge in ("l", "r"):
            self.transform_scale(factor, 1.0, point)
        else:
            self.transform_scale(1.0, factor, point)

    def transform_shear(self, edge: str, k: float) -> None:
        """拖边切变：``edge`` 是被抓的边（l/r/t/b），``k`` 是切变系数，
        对边为锚（抓右边往下拖 = 内容随 x 增大而下斜）。"""
        self._ensure_transform_preview()
        self._apply_visual(self._apply_shear(
            edge, k, self._visual_xf(),
            self._pivot_ops().get("shear", False)))

    def transform_perspective(self, corner: str, point: QPointF) -> None:
        """把 ``corner`` 这个角拖到 ``point``（图片坐标）——投影（透视）。

        四个角各自可动 ⇒ 平面不再是平行四边形：扫描件拍歪、书页中间鼓起
        这类"四条边对不上"的情况靠它掰正（GIMP 的透视手柄同款）。

        ⚠️ 拖成自交 / 塌陷（把角推到对角附近）的那一步会被
        :func:`_perspective_step` 判为病态并**丢弃**——保持原样，绝不把
        "把内容放大百万倍"的矩阵交给重采样（那会崩，见该函数）。
        """
        self._ensure_transform_preview()
        if self._xf_rect is None or corner not in CORNER_HANDLES:
            return
        visual = self._visual_xf()
        quad = [visual.map(p) for p in self._transform_local_corners()]
        index = CORNER_HANDLES.index(corner)
        step = _perspective_step(visual, quad, index, QPointF(point),
                                 self._xf_rect)
        if step is None:
            return
        # 投影重映射发生在**画布坐标**里：先视觉矩阵，再补这一步 A ⇒ `visual * A`
        self._apply_visual(visual * step)

    def transform_flip(self, horizontal: bool = True) -> None:
        """绕选区中心翻转（内容镜像；提交时由弹窗烘焙成一步）。

        ⚠️ 在**视觉空间**里叠镜像（``F * 视觉矩阵``）：正向与旧版完全一致；
        校正（向后）模式下旧版直接叠 ``_xf``，视觉上变成"先转再绕**原位**
        中心镜像"，与拖拽/旋转的视觉口径不一致。
        """
        self._ensure_transform_preview()
        rect = self._transform_local_rect()
        if rect is None:
            return
        self._apply_visual(
            flip_transform(rect, horizontal) * self._visual_xf())
