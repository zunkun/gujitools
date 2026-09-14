# -*- coding: utf-8 -*-
"""垂直缩略图条控件。"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem


class ThumbStrip(QListWidget):
    """垂直缩略图条：图标在上、标签在下，加载完成前显示占位图。"""

    ICON_SIZE = QSize(96, 128)  # 条目图标统一尺寸

    current_path_changed = Signal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(132)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.TopToBottom)
        self.setWrapping(False)
        self.setMovement(QListWidget.Movement.Static)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setGridSize(QSize(120, 160))
        self.setIconSize(ThumbStrip.ICON_SIZE)
        self.setSpacing(2)
        self.setStyleSheet("QListWidget::item { padding: 0px; }")
        self._placeholder = self._make_placeholder()
        self.itemClicked.connect(
            lambda item: self.current_path_changed.emit(
                self.row(item), item.data(Qt.UserRole) or ""
            )
        )

    @staticmethod
    def _make_placeholder() -> QIcon:
        """占位缩略图：浅灰底 + 边框，避免出现"加载中"文字。"""
        pixmap = QPixmap(96, 128)
        pixmap.fill(QColor("#e8ecf1"))
        painter = QPainter(pixmap)
        pen = QPen(QColor("#b8c0cc"), 1, Qt.DashLine)
        painter.setPen(pen)
        painter.drawRect(2, 2, 91, 123)
        painter.end()
        return QIcon(pixmap)

    def add_placeholder(self, text: str) -> None:
        self.addItem(QListWidgetItem(text))

    def add_page_item(self, label: str, path: str = "") -> None:
        """新增一个带占位图的条目，缩略图就绪后由 set_item_icon 替换。"""
        item = QListWidgetItem(self._placeholder, label)
        item.setData(Qt.UserRole, path)
        self.addItem(item)

    def set_item_icon(self, index: int, image, path: str, label: str) -> None:
        if index >= self.count():
            return
        item = self.item(index)
        item.setIcon(QIcon(QPixmap.fromImage(image)))
        item.setText(label)
        item.setData(Qt.UserRole, path)
