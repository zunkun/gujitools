# -*- coding: utf-8 -*-
"""画布 Mixin：**覆盖层装配**（选中框/手柄/橡皮圈等场景项的建与同步）。

从 ``EditorCanvas`` 拆出（2026-10-07）。方法体逐字未改。
"""
from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsLineItem,
    QGraphicsPolygonItem, QGraphicsRectItem,
)

from desktop.ui import theme as T

from ..consts import (
    HANDLE_VIEW_PX, PERSP_HANDLES, SHEAR_HANDLES,
)
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import CanvasHost
else:
    CanvasHost = object


#: 节点**中空**时用的描边（主题色、1.5 设备像素——不随缩放变粗）。
_HOLLOW_PEN = QPen(QColor(T.ACCENT))
_HOLLOW_PEN.setCosmetic(True)
_HOLLOW_PEN.setWidthF(1.5)
#: 节点**被点中**时：填主题色 + 白描边（在白纸/彩图上都分得出来）。
_FILLED_PEN = QPen(QColor("#ffffff"))
_FILLED_PEN.setCosmetic(True)
_FILLED_PEN.setWidthF(1.5)
_FILL_BRUSH = QBrush(QColor(T.ACCENT))
_EMPTY_BRUSH = QBrush(Qt.BrushStyle.NoBrush)


def _style_node(item, filled: bool) -> None:
    """给一个手柄图元上色：**只有"当前节点"有底色，其余一律中空**。

    用户 2026-10-09 口径：「操作节点**未选中**不要有背景色——拉伸方块不要用
    绿色，而是**中空**的」。所以默认是"主题色描边、不填色"；被点/悬停的那一个
    才填主题色（另有 ``_focus_ring`` 的高亮环兜底，小尺寸节点也看得见）。

    ⚠️ 方框（缩放）、菱形（切变/透视）共用这一套——形状才是语义，底色只表示
    "是不是当前这个"。⚠️ 改这里必须同时想清楚裁剪模式：那 8 个方框是**同一批
    图元**（见 :meth:`OverlayMixin._sync_overlay`），所以裁剪下由
    ``_apply_hover_highlight`` 传 ``_hover_handle`` 进来，不会变成"全是空的、
    没有任何反馈"。
    """
    item.setBrush(_FILL_BRUSH if filled else _EMPTY_BRUSH)
    item.setPen(_FILLED_PEN if filled else _HOLLOW_PEN)


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
        for name in ("tl", "t", "tr", "l", "r", "bl", "b", "br"):
            item = QGraphicsRectItem()
            _style_node(item, False)
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
        # 统一变换的**切变菱形**（每条边 1 个）与**透视小菱形**（角上）：
        # 方框=缩放、菱形=切变/透视——形状本身就是语义（GIMP 同款），
        # 所以用多边形图元而不是方块（见 consts.py 的手柄词汇表）。
        # ⚠️ 底色一律**中空**（用户 2026-10-09：「操作节点未选中不要有背景色」），
        #    只有"当前节点"被点/悬停时才填主题色（``_style_node``）。
        self._diamonds: dict[str, QGraphicsPolygonItem] = {}
        for name in SHEAR_HANDLES:
            item = QGraphicsPolygonItem()
            _style_node(item, False)
            item.setZValue(12)
            item.hide()
            self._scene.addItem(item)
            self._diamonds[name] = item
        self._persp: dict[str, QGraphicsPolygonItem] = {}
        for name in PERSP_HANDLES:
            item = QGraphicsPolygonItem()
            _style_node(item, False)
            item.setZValue(13)
            item.hide()
            self._scene.addItem(item)
            self._persp[name] = item
        # "激活节点"的**高亮环**：套在当前节点外面的一圈（比手柄本身大一圈、
        # 画在最上层）。用户要求"点哪个节点哪个节点就亮"——环而不是换色，
        # 是为了在白色/彩色页面上都看得见，也不影响节点本身的形状语义。
        self._focus_ring = QGraphicsRectItem()
        self._focus_ring.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        ring_pen = QPen(QColor(T.ACCENT))
        ring_pen.setCosmetic(True)          # 线宽按设备像素，缩放不变粗
        ring_pen.setWidthF(2.0)
        self._focus_ring.setPen(ring_pen)
        self._focus_ring.setZValue(16)
        self._focus_ring.hide()
        self._scene.addItem(self._focus_ring)
        # 构图**参考线**（三分/五分/黄金分割/对角线）：固定 8 根，按选项显示。
        # ⚠️ 2026-10-09 用户报「参考线不显眼，太细了看不清」：由 1px 点线
        #    （width=0 的 cosmetic 点线）改成 **2 设备像素虚线**（cosmetic ⇒
        #    任何缩放下粗细恒定），且默认开五分构图（见 consts.GUIDE_DEFAULT）。
        self._guides: list[QGraphicsLineItem] = []
        guide_pen = QPen(QColor(T.ACCENT))
        guide_pen.setCosmetic(True)
        guide_pen.setWidthF(2.0)
        guide_pen.setStyle(Qt.PenStyle.DashLine)
        for _ in range(8):
            item = QGraphicsLineItem()
            item.setPen(guide_pen)
            item.setZValue(9)
            item.hide()
            self._scene.addItem(item)
            self._guides.append(item)
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


    def _move_eraser_ring(self, pos: QPointF, show: bool = True) -> None:
        """笔刷圈挪到 ``pos``（图片坐标，圈心 = 笔刷中心 = 光标处）。"""
        self._eraser_pos = QPointF(pos)
        size = (self._distort_size if self._tool == "distort"
                else self._erase_size)
        radius = size / 2.0
        rect = QRectF(pos.x() - radius, pos.y() - radius, size, size)
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


    def _hide_transform_extras(self) -> None:
        """藏起统一变换独有的图元（切变/透视菱形、参考线、轮廓虚线、高亮环）。

        裁剪与「调整范围」用的是"矩形 + 8 个方框"那套覆盖层，菱形/参考线/
        原图轮廓虚线在那两个模式下没有意义——不显式藏的话，切回裁剪还会留着
        上一次的残影（它们是场景项，不会随工具切换自动消失）。
        """
        for item in self._diamonds.values():
            item.setVisible(False)
        for item in self._persp.values():
            item.setVisible(False)
        for item in self._guides:
            item.setVisible(False)
        self._focus_ring.setVisible(False)

    def _sync_overlay(self) -> None:
        """按当前工具刷新覆盖层：变换画自己的，其余只留裁剪选框或全藏。

        ⚠️「调整范围」下走**裁剪那套**（整条边命中带 + 8 个方框）：收边与
        裁剪是同一件事，共用一份覆盖层就不会出现"两种模式下手柄长得不一样"。
        """
        if (self._tool == "transform" and not self._xf_reshape
                and self._rect is not None and self._image is not None):
            self._sync_transform_overlay()
            return
        self._hide_transform_extras()
        visible = (
            self._tool in ("crop", "transform")
            and self._rect is not None and self._image is not None
        )
        if not visible:
            for item in self._mask:
                item.setVisible(False)
            self._sel_border.setVisible(False)
            self._quad.setVisible(False)
            self._pivot_item.setVisible(False)
            self._focus_ring.setVisible(False)
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
