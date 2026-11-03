# -*- coding: utf-8 -*-
"""主窗口顶部的新版本提示条（用户 2026-11-02）。

需求：启动时检查到新版本后，在窗口**顶部**提示，并且用户能**关掉**这条提示。

它是常驻控件而不是 ``InfoBar`` 那种自动消失的浮层——"有新版本"需要一直看得见，
直到用户自己关闭。关闭只影响本次会话，下次启动仍会按检查结果重新提示。

⚠️ 底色/描边走 ``paintEvent`` 自绘（项目硬规则：界面控件不用样式表）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy
from qfluentwidgets import BodyLabel, FluentIcon as FIF, TransparentToolButton

from desktop.ui import theme as T
from desktop.ui.widgets import apply_to


class UpdateBanner(QFrame):
    """顶部提示条：一行文案 + 右侧关闭按钮；无文案时自动隐藏。"""

    #: 用户点了关闭（供窗口决定是否要记住这类提示）
    closed = Signal()

    #: 固定高度（px）：只放一行正文，不挤压正文区
    HEIGHT = 36

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(T.SPACE_XL, 0, T.SPACE_SM, 0)
        layout.setSpacing(T.SPACE_SM)

        self.label = BodyLabel("", self)
        apply_to(self.label, T.SIZE_BODY, color=T.INK)
        layout.addWidget(self.label, 1)

        self.close_button = TransparentToolButton(FIF.CLOSE, self)
        self.close_button.setToolTip("关闭这条提示")
        self.close_button.setFixedSize(28, 28)
        self.close_button.clicked.connect(self._on_close)
        layout.addWidget(
            self.close_button, 0, Qt.AlignmentFlag.AlignVCenter
        )
        self.hide()

    def message(self) -> str:
        """当前提示文案（空串 = 没有提示）。"""
        return self.label.text()

    def show_message(self, text: str) -> None:
        """显示一条提示；``text`` 为空则隐藏。"""
        if not text:
            self.hide()
            return
        self.label.setText(text)
        self.show()

    def _on_close(self, *_args) -> None:
        """关闭按钮：隐藏自己并通知外部。"""
        self.hide()
        self.closed.emit()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """自绘浅色底 + 一条主色分隔线（与正文区灰底区分开）。"""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(T.ACCENT_SOFT))
        painter.setPen(QPen(QColor(T.ACCENT), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


__all__ = ["UpdateBanner"]
