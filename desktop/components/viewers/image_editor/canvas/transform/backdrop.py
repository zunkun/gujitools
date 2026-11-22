# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""统一变换：底图 / 纸面 / 剪裁矩形。"""
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



class TransformBackdropMixin(CanvasHost):
    """统一变换：底图 / 纸面 / 剪裁矩形。"""


    def _realtime_budget(self) -> bool:
        """选区（预览版）够不够小到能实时出画面？够 = 可以挂起不烘焙。

        ⚠️ 拖动本身已经不受这条约束了（拖动中不重采样，见
        :meth:`_apply_float_fast`）；它现在管的是**松手那一帧**的精确重采样
        成本——预览版按 ``TRANSFORM_PREVIEW_PIXELS`` 缩过，所以正常恒为真，
        留作"预算被改小 / 选区异常大"时的兜底。
        """
        if self._xf_preview_region is None:
            return False
        pixels = (self._xf_preview_region.width()
                  * self._xf_preview_region.height())
        return pixels <= TRANSFORM_PREVIEW_PIXELS * 1.05

    def _placed_xf(self) -> QTransform:
        """烘焙矩阵的**摆位部分**：选区局部坐标 → 图片坐标。

        就是 ``geometry.compose_transform`` 里的 ``placed``（
        ``translate(选区左上角) * 真正会被烘焙的那个矩阵``），预览的底图范围、
        精确浮层的像素矩阵、拖动中的图元矩阵全部从它派生——**一处定义**，
        免得三个地方各写一遍 ``translate * preview_xf`` 而其中一处忘了跟方向走。
        """
        rect = self._xf_rect
        assert rect is not None
        return (QTransform().translate(rect.x(), rect.y())
                * self._preview_xf(self._xf))

    def _bake_canvas_rect(self) -> QRectF:
        """**烘焙画布**的矩形 = 提交后那张图占多大（与 ``compose_transform`` 同块）。

        ⚠️ 它现在**只**用来决定"越界内容裁到哪"（:meth:`_plane_clip_rect`），
        **不再**是预览底图的范围（底图已恒定，见 :meth:`_base_target_rect`）。
        ``geometry.transform_region`` 给出的正是「调整」档烘焙结果的外框（变换后
        内容的外框 ∪ 选区之外的原图残余）；「裁剪到原画布」保持原尺寸；「裁剪到
        原比例」是先长再居中裁回原始长宽比（与 ``center_crop_aspect`` 同一套取整）。
        """
        if self._xf_rect is None or self._image is None:
            return QRectF()
        if self._xf_clipping == "clip":
            return QRectF(self.image_rect())
        x0, y0, width, height = transform_region(
            self._image, self._xf_rect.normalized(), self._placed_xf())
        grown = QRectF(x0, y0, width, height)
        if self._xf_clipping == "aspect":
            return _center_crop_rect(grown, self._image.width(),
                                     self._image.height())
        return grown

    def _base_target_rect(self) -> QRectF:
        """底图覆盖的矩形 = **原图矩形，恒定不动**。

        ⚠️ 用户 2026-10-09 口径：「白底不应该扩大，应该是图片初始位置和大小」
        ——旧版把它跟着**旋转外框**（= 烘焙画布，见 :meth:`_bake_canvas_rect`）
        每帧重算：整幅旋转 30° 就涨到 920×992、原点还跑到 (-160,-96)，再叠上
        ``setSceneRect`` 一起变 ⇒ 看着就是"白底和图片位置一直在漂"。

        现在它**恒定**：旋转只换上方浮层的内容，底下这块"地盘"永远钉在图片当初
        的位置和尺寸上（也不再外扩余量——不会长大就不需要余量）。
        """
        if self._image is None:
            return QRectF()
        return QRectF(self.image_rect())

    def _plane_clip_rect(self) -> QRectF | None:
        """浮层内容要按哪块裁（图片坐标）；``None`` = 不裁（「调整」档）。

        烘焙在 ``clip`` 档是"保持原画布、超出的内容裁掉"，``aspect`` 档是
        "先长再居中裁回原比例"——两种都会把越界内容切掉，预览不跟着切就是
        "预览比烘焙多出一块"。
        """
        if self._xf_clipping == "adjust":
            return None
        return self._bake_canvas_rect()

    def _base_current_rect(self) -> QRectF:
        """底图图元**此刻**盖住的矩形（图片坐标；含 1×1 空图的缩放）。"""
        if self._paint_image is None:
            return QRectF()
        scale = self._xf_base_scale
        if scale is None:
            size = QSizeF(self._paint_image.width(), self._paint_image.height())
        else:
            size = QSizeF(self._paint_image.width() * scale.x(),
                          self._paint_image.height() * scale.y())
        return QRectF(self._xf_base_origin, size)

    def _backdrop_needs_resize(self) -> bool:
        """底图还要不要再铺一次？—— 拖动中**恒为 False**。

        ⚠️ 底图范围已**恒定**＝原图矩形（见 :meth:`_base_target_rect`），旋转不再
        让它长大，所以拖动中一次都不用重铺——这正是"白底不再漂"的来源；旧版
        每帧拿旋转外框比一次、涨出余量就重铺 12 MP，既是卡顿来源也是漂移来源。

        留这个判断只为兜住"选区被换掉"这一种情形：整幅 ↔ 局部会切换"1×1 空图"
        那条捷径，残影必须按新选区重画。拖动期间 ``_xf_rect`` 是冻住的，不会走到。
        """
        if self._paint_image is None or self._xf_rect is None:
            return True
        return (self._xf_base_scale is not None) != self._backdrop_is_whole()

    def _backdrop_is_whole(self) -> bool:
        """选区是不是覆盖全部可见内容（此时没有原图残余要画）？"""
        if self._image is None or self._xf_rect is None:
            return False
        if self._xf_restore_region is not None:
            # 恢复会话：整个画布的内容（PA1）都被"搬上浮层"了，纸＝纯透明。
            # PB1 的四角本来就是透明的，视觉与打开时完全一致（零跳变）。
            return True
        content = self._content_rect()
        if content is None:
            content = QRectF(0, 0, self._image.width(), self._image.height())
        rect = self._xf_rect.normalized()
        return (abs(rect.left() - content.left()) < 0.5
                and abs(rect.top() - content.top()) < 0.5
                and abs(rect.width() - content.width()) < 0.5
                and abs(rect.height() - content.height()) < 0.5)

    def _rebuild_backdrop(self) -> None:
        """重铺底图：内容被搬走的选区那块**擦成透明**，选区之外保留原图。

        **两个方向共用这一套**：「校正（向后）」那边 ``_preview_xf`` 给的是
        **反向**矩阵，底图与内容的位置自动跟着反向走。

        范围**恒定**＝原图矩形（:meth:`_base_target_rect`，不再外扩余量、也不跟
        变换走）。整幅选区时"选区之外"为空 ⇒ 底下什么都没有，用一张 1×1 透明图
        + 图元缩放表示：换尺寸只是改个矩阵，12 MP 上也是零成本。

        ⚠️ 与 ``_ensure_transform_preview`` 的区别是**不重建浮层**：只换底图像素。
        """
        assert self._image is not None and self._xf_rect is not None
        target = self._base_target_rect().toAlignedRect()
        self._xf_base_origin = QPointF(target.x(), target.y())
        if self._backdrop_is_whole():
            self._paint_image = _blank_image()
            self._xf_base_scale = QPointF(float(target.width()),
                                          float(target.height()))
        else:
            self._paint_image = self._paper_image(target)
            self._xf_base_scale = None
        self._set_base_pixmap()

    def _paper_image(self, target: QRect) -> QImage:
        """底图：**原图残余**（选区那块擦成透明），画布 = ``target``（图片坐标）。

        ⚠️ 擦除必须走 ``CompositionMode_Clear``：直接"填一个透明色"只是盖上一层
        全透明像素、底下的原图照旧（``SourceOver`` 不会替换），选区那块就擦不掉。
        擦完露出下层画布条纹格 —— 那就是"这里已经空了"。
        """
        assert self._image is not None and self._xf_rect is not None
        frame = QImage(target.size(), QImage.Format.Format_ARGB32)
        frame.fill(QColor(0, 0, 0, 0))
        painter = QPainter(frame)
        painter.drawImage(QPointF(-target.x(), -target.y()), self._image)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(self._xf_rect.normalized().translated(
            -target.x(), -target.y()), QColor(0, 0, 0, 0))
        painter.end()
        return frame
