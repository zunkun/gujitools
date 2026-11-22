# -*- coding: utf-8 -*-
"""「管理图片」网格的条目自绘委托（:class:`_ThumbDelegate`）。"""

from __future__ import annotations

from desktop.components.print_manage_dialog._qt import (
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QRect,
    QSize,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    Qt,
)

from desktop.components.print_manage_dialog.constants import (
    PENDING_KEY,
    SHOWN_SIZE_ROLE,
    THUMB_SIZE,
)
from desktop.components.print_manage_dialog.helpers import (
    _check_rect,
    _close_rect,
    _image_rect,
    page_label,
)
from desktop.ui import theme as T


class _ThumbDelegate(QStyledItemDelegate):
    """网格条目自绘：选中底色 + 缩略图 + 右上角 x + 名称。

    ``QListWidget`` 原生条目没有"右上角按钮/虚线边框"这类装饰，自绘一次比
    叠一层透明控件更轻（滚动/拖动时不会有一堆子控件跟着搬）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        #: 本书的缩略图框（面板按实际长宽比算出后覆盖）；文字固定在框下方
        self.thumb_box = QSize(THUMB_SIZE)

    def paint(  # noqa: N802 - Qt 覆写
        self, painter: QPainter, option: QStyleOptionViewItem, index,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cell = option.rect.adjusted(2, 2, -2, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.setPen(QPen(QColor(T.ACCENT), 1))
            painter.setBrush(QColor(T.ACCENT_SOFT))
            painter.drawRoundedRect(cell, T.RADIUS_SM, T.RADIUS_SM)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

        entry = index.data(Qt.ItemDataRole.UserRole)
        pending = isinstance(entry, dict) and bool(entry.get(PENDING_KEY))
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        shown = index.data(SHOWN_SIZE_ROLE) or QSize()
        image = _image_rect(option.rect, shown, self.thumb_box)
        if isinstance(icon, QIcon) and not icon.isNull():
            icon.paint(painter, image, Qt.AlignmentFlag.AlignCenter)
        # 新图片：暖色虚线框（还没保存进任务目录，与已有图片区分）
        if pending:
            pen = QPen(QColor(T.WARNING), 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(image.adjusted(-3, -3, 3, 3),
                                    T.RADIUS_SM, T.RADIUS_SM)

        mark = QFont(option.font)
        mark.setBold(True)
        mark.setPixelSize(11)

        # 左上角多选框（与右键/Ctrl 多选等价；用户 2026-11-02）
        check = _check_rect(image)
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(T.ACCENT))
            painter.drawRoundedRect(check, 4, 4)
            painter.setFont(mark)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(check, Qt.AlignmentFlag.AlignCenter, "✓")
        else:
            painter.setPen(QPen(QColor(T.BORDER_STRONG), 1))
            painter.setBrush(QColor(255, 255, 255, 220))
            painter.drawRoundedRect(check, 4, 4)

        # 右上角删除 x
        close = _close_rect(image)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 130))
        painter.drawEllipse(close)
        painter.setFont(mark)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(close, Qt.AlignmentFlag.AlignCenter, "✕")

        # 名称 = **页码**（列表当前位置；拖动/删除后自动跟着变）
        text = page_label(index.row())
        font = QFont(option.font)
        painter.setFont(font)
        painter.setPen(QColor(T.WARNING if pending else T.INK_SOFT))
        # 名称紧跟**本张图**底部：文字挨着图片，不按统一框高摆放
        # （用户 2026-11-02：「文字跟图片太远了」）
        top = image.bottom() + 6
        text_rect = QRect(
            option.rect.left() + 2,
            top,
            option.rect.width() - 4,
            max(option.rect.bottom() - top, 0),
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            painter.fontMetrics().elidedText(
                text, Qt.TextElideMode.ElideMiddle, text_rect.width()
            ),
        )
        painter.restore()
