# -*- coding: utf-8 -*-
"""预览弹窗的**图标与朝向变换**（自绘翻转/旋转图标 + 显示矩阵）。

从 ``image_zoom_dialog.py`` 拆出（2026-10-07）。方法体逐字未改。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import (
    QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF, QTransform,
)
from qfluentwidgets import FluentIcon as FIF

from .consts import ICON_COLOR

def display_transform(rotation: int = 0, flip_h: bool = False,
                      flip_v: bool = False) -> QTransform:
    """翻转/旋转的变换矩阵——**屏幕与导出必须共用这一个**。

    ⚠️ 屏幕侧走 ``QGraphicsPixmapItem.setTransform``、导出侧走
    ``QImage.transformed``。两处若各写一份，改一处就会出现「看到的和下载的
    不一样」（翻转轴或旋转方向不一致）。
    """
    transform = QTransform()
    if flip_h or flip_v:
        transform = transform.scale(
            -1.0 if flip_h else 1.0, -1.0 if flip_v else 1.0
        )
    return transform * QTransform().rotate(float(rotation) % 360.0)


def mirrored_rotate_icon() -> QIcon:
    """``FIF.ROTATE`` 的水平镜像 = **逆时针（左旋）**。

    qfluentwidgets 只提供一个旋转图标：ROTATE 的箭头在弧线底部**指向左**，
    即顺时针（右旋）。左旋用它的镜像，两颗按钮的笔触天然一致、只差方向。

    多档位 pixmap 是为了高分屏下不掉清晰度（图标源是 SVG，按需渲染）。
    """
    source = FIF.ROTATE.icon()
    icon = QIcon()
    for edge in (16, 20, 24, 32, 48):
        icon.addPixmap(
            source.pixmap(QSize(edge, edge)).transformed(
                QTransform().scale(-1.0, 1.0)
            )
        )
    return icon


def _flip_pixmap(size: int, horizontal: bool, color: QColor) -> QPixmap:
    """画一个"镜像轴 + 两个相对三角"的翻转图标（水平/垂直只差 90° 旋转）。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(size / 2.0, size / 2.0)
    if not horizontal:
        painter.rotate(90)
    painter.translate(-size / 2.0, -size / 2.0)
    margin, center, gap = size * 0.10, size / 2.0, size * 0.07
    pen = QPen(color, max(1.0, size * 0.055), Qt.PenStyle.DashLine)
    pen.setDashPattern([1.6, 1.4])   # 默认虚线在这个尺寸下太碎，改长一点
    painter.setPen(pen)
    painter.drawLine(QPointF(center, margin), QPointF(center, size - margin))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF([
        QPointF(margin, margin), QPointF(center - gap, center),
        QPointF(margin, size - margin),
    ]))
    painter.drawPolygon(QPolygonF([
        QPointF(size - margin, margin), QPointF(center + gap, center),
        QPointF(size - margin, size - margin),
    ]))
    painter.end()
    return pixmap


def flip_icon(horizontal: bool = True, color: QColor | None = None) -> QIcon:
    """翻转按钮的图标（水平/垂直 = 同一个图形转 90°）。

    qfluentwidgets 没有可用的翻转图标：``SEARCH_MIRROR`` 是"带镜子的放大镜"，
    语义不对；``SYNC`` 是循环箭头。自绘还有个好处——一对图标笔触完全一致，
    且按需渲染，任意 dpr 下都锐利。
    """
    icon = QIcon()
    for edge in (16, 20, 24, 32, 48):
        icon.addPixmap(_flip_pixmap(edge, horizontal, color or ICON_COLOR))
    return icon
