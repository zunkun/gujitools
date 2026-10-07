# -*- coding: utf-8 -*-
"""画布 Mixin：**校正**（四角透视校正 + 目标宽高比）。

从 ``EditorCanvas`` 拆出（2026-10-07）。方法体逐字未改。
"""
from __future__ import annotations

import time

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem

from desktop.ui import theme as T
from utils.perspective import quad_moved, rectify_qimage, rectify_region

from ..consts import (
    DEFORM_PREVIEW_INTERVAL, DEFORM_PREVIEW_PIXELS, DEFORM_PREVIEW_SETTLE_PIXELS,
    QUAD_HANDLE_VIEW_PX, QUAD_HIT_VIEW_PX,
)
from ..geometry import cage_preview_scale
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import CanvasHost
else:
    CanvasHost = object


class RectifyMixin(CanvasHost):
    """校正工具：四角手柄/命中/拖动/预览/覆盖层。"""

    # ---- 「校正」（四点透视摆正） ----
    def _ensure_quad(self) -> None:
        """（不发信号）没四边形时按当前整幅图建一个（四角 = 图四角）。"""
        if self._image is None or self._image.isNull():
            self._rect_quad = []
            return
        if self._rect_quad:
            return
        rect = self.image_rect()
        self._rect_quad = [QPointF(rect.left(), rect.top()),
                      QPointF(rect.right(), rect.top()),
                      QPointF(rect.right(), rect.bottom()),
                      QPointF(rect.left(), rect.bottom())]


    def reset_quad(self) -> None:
        """「重置」：四角回到整幅图四角（丢掉未应用的校正）。"""
        self._clear_deform_preview()
        self._rect_quad = []
        self._rect_drag = None
        self._rect_hover = None
        self._ensure_quad()
        self._sync_quad_overlay()
        self._sync_cursor()


    def quad(self) -> list:
        """当前四边形四角副本（``QPointF`` 列表）——给自测与外部读。"""
        self._ensure_quad()
        return [QPointF(p) for p in self._rect_quad]


    def rectify_ratio(self) -> str:
        """目标矩形宽高比口径（见 RECTIFY_RATIO_CHOICES）。"""
        return self._rectify_ratio


    def set_rectify_ratio(self, mode: str) -> None:
        """改目标矩形口径：只影响**之后的**预览，不必丢掉当前四角。"""
        self._rectify_ratio = mode
        self._refresh_deform_preview(force=True)
        self._sync_quad_overlay()


    def quad_move(self, index: int, pos: QPointF) -> None:
        """把第 ``index`` 个角拖到 ``pos``（图片坐标）。

        ⚠️ **允许拖到图片外面**（四角要能框住"拍摄时把纸张也拍进来了"的
        边界）。只留一个"一张图那么远"的宽松上限，免得角点被甩丢。
        """
        self._ensure_quad()
        if not 0 <= index < 4:
            return
        limit = self.image_rect()
        off_x, off_y = limit.width(), limit.height()
        clamped = QPointF(
            max(limit.left() - off_x, min(pos.x(), limit.right() + off_x)),
            max(limit.top() - off_y, min(pos.y(), limit.bottom() + off_y)))
        self._rect_quad[index] = clamped
        self._rect_hover = index
        self._sync_quad_overlay()
        self._refresh_deform_preview()


    def _hit_quad(self, view_pos: QPointF) -> int | None:
        """命中四角手柄（视图像素口径，不随缩放变）。"""
        self._ensure_quad()
        for index, point in enumerate(self._rect_quad):
            spot = QPointF(self.mapFromScene(point))
            if QLineF(view_pos, spot).length() <= QUAD_HIT_VIEW_PX:
                return index
        return None


    def quad_pending(self):
        """未应用的校正 ``(quad, mode)``；四角没动过则 None。"""
        self._ensure_quad()
        if len(self._rect_quad) != 4:
            return None
        rect = self.image_rect()
        rest = [(rect.left(), rect.top()), (rect.right(), rect.top()),
                (rect.right(), rect.bottom()), (rect.left(), rect.bottom())]
        if not quad_moved(rest, [(p.x(), p.y()) for p in self._rect_quad]):
            return None
        return ([(p.x(), p.y()) for p in self._rect_quad], self._rectify_ratio)


    def _sync_quad_overlay(self) -> None:
        """四角手柄的显隐与位置刷新（只在「校正」工具下显示）。"""
        show = (self._tool == "rectify" and self._item is not None
                and len(self._rect_quad) == 4)
        if not show:
            self._rect_poly.hide()
            for item in self._rect_dots:
                item.hide()
            return
        self._rect_poly.show()
        path = QPainterPath()
        path.moveTo(self._rect_quad[0])
        for point in self._rect_quad[1:]:
            path.lineTo(point)
        path.closeSubpath()
        self._rect_poly.setPath(path)
        half = QUAD_HANDLE_VIEW_PX / max(self._zoom, 1e-6)
        for index, item in enumerate(self._rect_dots):
            point = self._rect_quad[index]
            item.setRect(QRectF(point.x() - half, point.y() - half,
                                half * 2, half * 2))
            big = index == self._rect_hover
            item.setBrush(QBrush(QColor(T.ACCENT_HOVER if big else T.ACCENT)))
            item.show()


    def _refresh_rectify_preview(self, force: bool = False) -> None:
        """重算「校正」的像素预览：把四角框住的区域透视摆正后贴回原位置。

        ⚠️ 与「变形」的预览不同：校正会**改变尺寸**（摆正后是目标矩形），
        所以浮层不是"贴原尺寸的框"，而是"贴在源四边形的框里、显示摆正后的
        内容"——所见即应用后那块的去向（应用后整图会被换成摆正图）。
        """
        if self._image is None:
            self._clear_deform_preview()
            return
        pending = self.quad_pending()
        if pending is None:
            self._clear_deform_preview()
            return
        now = time.monotonic()
        if not force and now - self._deform_painted_at < DEFORM_PREVIEW_INTERVAL:
            return
        quad, mode = pending
        width, height = self._image.width(), self._image.height()
        x0, y0, _out_w, _out_h = rectify_region(quad, width, height, mode=mode)
        # 同 deform：预算按**整幅图**面积算（rectify_qimage 也是拿整张降采样
        # 图去重的映射，真实工作量 = width×height×scale²，见上方说明）。
        scale = cage_preview_scale(
            width, height,
            self._zoom * max(1.0, self.devicePixelRatioF()),
            DEFORM_PREVIEW_SETTLE_PIXELS if force else DEFORM_PREVIEW_PIXELS)
        if scale >= 1.0:
            source = self._image
            quad_scaled = quad
        else:
            source = self._image.scaled(
                max(1, int(round(width * scale))),
                max(1, int(round(height * scale))),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            quad_scaled = [(px * scale, py * scale) for px, py in quad]
        try:
            warped = rectify_qimage(source, quad_scaled, out_size=None,
                                    mode=mode)
        except ValueError:
            self._clear_deform_preview()
            return
        pixmap = QPixmap.fromImage(warped)
        pixmap.setDevicePixelRatio(1.0)
        if self._deform_item is None:
            self._deform_item = QGraphicsPixmapItem()
            self._deform_item.setZValue(4)
            self._deform_item.setTransformationMode(
                Qt.TransformationMode.SmoothTransformation)
            self._scene.addItem(self._deform_item)
        self._deform_item.setPixmap(pixmap)
        self._deform_item.setPos(x0, y0)
        self._deform_item.setScale(1.0 / scale)
        self._deform_painted_at = now
