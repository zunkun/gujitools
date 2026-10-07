# -*- coding: utf-8 -*-
"""画布 Mixin：**覆盖层装配**（选中框/手柄/橡皮圈等场景项的建与同步）。

从 ``EditorCanvas`` 拆出（2026-10-07）。方法体逐字未改。
"""
from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPathItem,
    QGraphicsPolygonItem, QGraphicsRectItem,
)

from desktop.ui import theme as T

from ..consts import HANDLE_VIEW_PX
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import CanvasHost
else:
    CanvasHost = object


class OverlayMixin(CanvasHost):
    """覆盖层：选中框/手柄/橡皮圈/整幅虚线框的创建与同步。"""

    def _build_overlay(self) -> None:
        """遮罩 4 块 + 选区边框 + 8 手柄，建好藏起来，按需显示。"""
        self._border = None  # 纸边框（set_image 建）
        mask_brush = QBrush(QColor(0, 0, 0, 110))
        self._mask: list[QGraphicsRectItem] = []
        for _ in range(4):
            item = QGraphicsRectItem()
            item.setBrush(mask_brush)
            item.setPen(QPen(Qt.PenStyle.NoPen))
            item.setZValue(10)
            item.hide()
            self._scene.addItem(item)
            self._mask.append(item)
        self._sel_border = QGraphicsRectItem()
        self._sel_border.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._sel_border.setPen(QPen(QColor(T.ACCENT), 0, Qt.PenStyle.DashLine))
        self._sel_border.setZValue(11)
        self._sel_border.hide()
        self._scene.addItem(self._sel_border)
        # 变换工具的**四边形**选框（跟随累计矩阵变形，虚线同款样式）
        self._quad = QGraphicsPolygonItem()
        self._quad.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._quad.setPen(QPen(QColor(T.ACCENT), 0, Qt.PenStyle.DashLine))
        self._quad.setZValue(11)
        self._quad.hide()
        self._scene.addItem(self._quad)
        self._handles: dict[str, QGraphicsRectItem] = {}
        handle_pen = QPen(QColor("#ffffff"), 0)
        handle_brush = QBrush(QColor(T.ACCENT))
        for name in ("tl", "t", "tr", "l", "r", "bl", "b", "br"):
            item = QGraphicsRectItem()
            item.setBrush(handle_brush)
            item.setPen(handle_pen)
            item.setZValue(12)
            item.hide()
            self._scene.addItem(item)
            self._handles[name] = item
        # 悬停/拖动中的**边界高亮线**（每条选区边一根；可见性由
        # _apply_hover_highlight 管，几何在 _sync_overlay 里跟选区走）
        self._edge_lines: dict[str, QGraphicsLineItem] = {}
        edge_pen = QPen(QColor(T.ACCENT), 0)
        edge_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        for name in ("l", "r", "t", "b"):
            item = QGraphicsLineItem()
            item.setPen(edge_pen)
            item.setZValue(13)
            item.hide()
            self._scene.addItem(item)
            self._edge_lines[name] = item
        # 变换**轴心**圆点（画在最上层，可拖动）
        self._pivot_item = QGraphicsEllipseItem()
        self._pivot_item.setBrush(QBrush(QColor(T.ACCENT)))
        self._pivot_item.setPen(QPen(QColor("#ffffff"), 0))
        self._pivot_item.setZValue(14)
        self._pivot_item.hide()
        self._scene.addItem(self._pivot_item)
        # 橡皮擦**光标圈**：直径恒等于实际擦除直径（场景坐标 = 图片像素，
        # 缩放天然跟随），圈到哪里擦到哪里（用户 2026-10-01：光标大小要和
        # 划线一致）。外圈深色 3 设备像素 + 内圈白 1 设备像素，白纸黑底都
        # 看得见；pen 用 cosmetic——线宽按设备像素，任何缩放下都是恒定细线。
        self._eraser_ring: list[QGraphicsEllipseItem] = []
        for color, width in (("#3a3f4b", 3.0), ("#ffffff", 1.0)):
            item = QGraphicsEllipseItem()
            pen = QPen(QColor(color))
            pen.setCosmetic(True)
            pen.setWidthF(width)
            item.setPen(pen)
            item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            item.setZValue(15)
            item.hide()
            self._scene.addItem(item)
            self._eraser_ring.append(item)
        # 文字块**边界虚线框**：悬停在块上/拖动中显示"这一块的范围"，
        # 松手即消失（用户 2026-10-01 手机作图式文字）
        self._text_outline = QGraphicsRectItem()
        self._text_outline.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._text_outline.setPen(QPen(QColor(T.ACCENT), 0, Qt.PenStyle.DashLine))
        self._text_outline.setZValue(18)
        self._text_outline.hide()
        self._scene.addItem(self._text_outline)
        # 「变形」的**图钉**：每个图钉一根"钉子"（原点→当前位置的细线，
        # 拖远时看得出内容被从哪儿扯过来）+ 一个圆点。钉子用区分色，
        # 拖远时不会和图片内容糊在一起。
        self._pin_tail = QGraphicsPathItem()
        self._pin_tail.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        tail_pen = QPen(QColor(T.INK_FAINT), 0, Qt.PenStyle.DotLine)
        tail_pen.setCosmetic(True)
        self._pin_tail.setPen(tail_pen)
        self._pin_tail.setZValue(11)
        self._pin_tail.hide()
        self._scene.addItem(self._pin_tail)
        #: 图钉圆点（数量随用户增删，按需增删）
        self._pin_dots: list[QGraphicsEllipseItem] = []
        # 「校正」的**四角手柄**：一个四边形轮廓 + 4 个方块角点。
        # 轮廓画源四边形（要摆正的区域），方块是抓点。
        self._rect_poly = QGraphicsPathItem()
        self._rect_poly.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        quad_pen = QPen(QColor(T.ACCENT), 0, Qt.PenStyle.DashLine)
        quad_pen.setCosmetic(True)
        self._rect_poly.setPen(quad_pen)
        self._rect_poly.setZValue(13)
        self._rect_poly.hide()
        self._scene.addItem(self._rect_poly)
        #: 四个方块角点
        self._rect_dots: list[QGraphicsRectItem] = []
        for _ in range(4):
            item = QGraphicsRectItem()
            item.setPen(QPen(QColor("#ffffff"), 0))
            item.setBrush(QBrush(QColor(T.ACCENT)))
            item.setZValue(14)
            item.hide()
            self._scene.addItem(item)
            self._rect_dots.append(item)
        # 「变换笼」的**边框**：闭合折线（原位实线 + 当前位置虚线）。
        # 原位实线让人看见"笼本来贴在哪"，当前位置虚线是拖到的地方。
        self._cage_src_poly = QGraphicsPathItem()
        self._cage_src_poly.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        src_pen = QPen(QColor(T.INK_FAINT), 0, Qt.PenStyle.DotLine)
        src_pen.setCosmetic(True)
        self._cage_src_poly.setPen(src_pen)
        self._cage_src_poly.setZValue(11)
        self._cage_src_poly.hide()
        self._scene.addItem(self._cage_src_poly)
        self._cage_dst_poly = QGraphicsPathItem()
        self._cage_dst_poly.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        dst_pen = QPen(QColor(T.ACCENT), 0, Qt.PenStyle.DashLine)
        dst_pen.setCosmetic(True)
        self._cage_dst_poly.setPen(dst_pen)
        self._cage_dst_poly.setZValue(12)
        self._cage_dst_poly.hide()
        self._scene.addItem(self._cage_dst_poly)
        #: 笼把手圆点（数量随密度档位变，按需增删）
        self._cage_dots: list[QGraphicsEllipseItem] = []


    def _move_eraser_ring(self, pos: QPointF, show: bool = True) -> None:
        """橡皮擦圈挪到 ``pos``（图片坐标，圈心 = 笔刷中心 = 光标处）。"""
        self._eraser_pos = QPointF(pos)
        radius = self._erase_size / 2.0
        rect = QRectF(pos.x() - radius, pos.y() - radius,
                      self._erase_size, self._erase_size)
        for item in self._eraser_ring:
            item.setRect(rect)
            item.setVisible(show and self._item is not None)


    def _hide_eraser_ring(self) -> None:
        for item in self._eraser_ring:
            item.hide()


    def _handle_boxes(self, rect: QRectF) -> dict[str, QRectF]:
        """8 个手柄的图片坐标框（视觉尺寸 = 视图像素 ÷ 当前倍率）。"""
        hs = HANDLE_VIEW_PX / max(self._zoom, 1e-6)
        cx, cy = rect.center().x(), rect.center().y()
        anchors = {
            "tl": rect.topLeft(), "t": QPointF(cx, rect.top()),
            "tr": rect.topRight(), "l": QPointF(rect.left(), cy),
            "r": QPointF(rect.right(), cy), "bl": rect.bottomLeft(),
            "b": QPointF(cx, rect.bottom()), "br": rect.bottomRight(),
        }
        return {
            name: QRectF(point.x() - hs / 2, point.y() - hs / 2, hs, hs)
            for name, point in anchors.items()
        }


    def _sync_overlay(self) -> None:
        """按当前选区刷新遮罩/边框/手柄几何与可见性。"""
        if (self._tool == "transform" and self._rect is not None
                and self._image is not None):
            self._sync_transform_overlay()
            return
        if self._tool == "deform" and self._image is not None:
            self._sync_pin_overlay()
            return
        if self._tool == "cage" and self._image is not None:
            self._sync_cage_overlay()
            return
        if self._tool == "rectify" and self._image is not None:
            self._sync_quad_overlay()
            return
        visible = (
            self._tool == "crop"
            and self._rect is not None and self._image is not None
        )
        if not visible:
            for item in self._mask:
                item.setVisible(False)
            self._sel_border.setVisible(False)
            self._quad.setVisible(False)
            self._pivot_item.setVisible(False)
            self._cage_src_poly.setVisible(False)
            self._cage_dst_poly.setVisible(False)
            for item in self._cage_dots:
                item.setVisible(False)
            for item in self._handles.values():
                item.setVisible(False)
            for item in self._edge_lines.values():
                item.setVisible(False)
            return
        # ⚠️ 上面那道 ``visible`` 判据里已经含 _rect/_image 非空，但类型检查器
        #    不会跟着 boolean 中间变量收窄 self._rect，这里显式再收一次。
        #    运行时是纯空操作（不 visible 的分支已经 return 了）。
        if self._rect is None or self._image is None:
            return
        rect = self._rect.normalized()
        full = self.image_rect()
        # 遮罩 = 选区外的四块（夹一下防越界出负宽）
        self._mask[0].setRect(QRectF(
            full.left(), full.top(), full.width(),
            max(0.0, rect.top() - full.top())))
        self._mask[1].setRect(QRectF(
            full.left(), rect.bottom(), full.width(),
            max(0.0, full.bottom() - rect.bottom())))
        self._mask[2].setRect(QRectF(
            full.left(), rect.top(), max(0.0, rect.left() - full.left()),
            rect.height()))
        self._mask[3].setRect(QRectF(
            rect.right(), rect.top(),
            max(0.0, full.right() - rect.right()), rect.height()))
        for item in self._mask:
            item.setVisible(True)
        self._sel_border.setRect(rect)
        self._sel_border.setVisible(True)
        self._quad.setVisible(False)
        self._pivot_item.setVisible(False)
        for name, box in self._handle_boxes(rect).items():
            self._handles[name].setRect(box)
            self._handles[name].setVisible(True)
        # 边缘高亮线的几何跟着选区走（可见性由悬停/拖动状态管）
        lines = {
            "l": QLineF(rect.topLeft(), rect.bottomLeft()),
            "r": QLineF(rect.topRight(), rect.bottomRight()),
            "t": QLineF(rect.topLeft(), rect.topRight()),
            "b": QLineF(rect.bottomLeft(), rect.bottomRight()),
        }
        for name, line in lines.items():
            item = self._edge_lines[name]
            pen = item.pen()
            pen.setWidthF(3.0 / max(self._zoom, 1e-6))  # 恒 ≈3 视图像素
            item.setPen(pen)
            item.setLine(line)
        self._apply_hover_highlight()
