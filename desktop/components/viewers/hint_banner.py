# -*- coding: utf-8 -*-
"""画布顶部的**红框提示条**（用户 2026-11-12）。

需求："检测文本框区域，可以红线提示用户可以手动调整框类型和画框，可以放在
中间图片顶部"。

它解决的问题是**可发现性**：预览上能拖动/缩放/手绘框、右栏能改框类型，这些
能力此前只写在面板的长 tooltip 里，用户根本不知道有。提示条**常驻**在图片
上方（不是转瞬即逝的 InfoBar），用户点 × 认为学会了就永久关掉（本控件实例内
一直关着，换文案也不会再冒出来）。

⚠️ 底色/描边走 ``paintEvent`` 自绘（项目硬规则：界面控件不用样式表），
与 :class:`desktop.components.update_banner.UpdateBanner` 同一套做法。
⚠️ 文案不写在这里：业务层按"这页有没有框 / 是不是保留框外空白"现算后传进来
（唯一实现在 ``desktop/components/box_kinds.py::manual_hint_text``）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget
from qfluentwidgets import BodyLabel, FluentIcon as FIF, TransparentToolButton

from desktop.ui import theme as T
from desktop.ui.widgets import apply_to


class HintBanner(QWidget):
    """一行红字提示 + 右侧关闭按钮；没有文案时自动隐藏。"""

    #: 圆角（与控件档一致）
    RADIUS = T.RADIUS_SM
    #: 描边粗细：比常规 1px 粗一档，才像"红笔圈出来的提示"而不是普通分隔线
    BORDER = 1.5

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        layout = QHBoxLayout(self)
        # 右边留窄一点：关闭按钮自己带内边距
        layout.setContentsMargins(T.SPACE_MD, 6, 4, 6)
        layout.setSpacing(T.SPACE_SM)

        self.label = BodyLabel("", self)
        self.label.setWordWrap(True)
        apply_to(self.label, T.SIZE_BODY, color=T.DANGER)
        layout.addWidget(self.label, 1)

        self.close_button = TransparentToolButton(FIF.CLOSE, self)
        self.close_button.setToolTip("知道了，不再提示")
        self.close_button.setFixedSize(24, 24)
        self.close_button.clicked.connect(self._on_close)
        layout.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        #: 用户点过 ×：此后 ``set_hint`` 只更新文案、**不再显示**（见类注释）
        self._dismissed = False
        self.hide()

    # ------------------------------------------------------------------ 接口
    def text(self) -> str:
        """当前提示文案（空串 = 没有提示）。"""
        return self.label.text()

    def set_hint(self, text: str) -> None:
        """换一条提示；``text`` 为空则隐藏。

        ⚠️ 用户关掉过（``_dismissed``）就只记文案不上屏：调用方（每次都跟着
        "上屏一页框"重算文案）**不应该**把用户的关闭动作顶掉。
        """
        if not text:
            self.hide()
            return
        self.label.setText(text)
        if self._dismissed:
            return
        self.show()

    def reset_dismiss(self) -> None:
        """恢复"可以再提示"（宿主若要"每换一本书重新提示一次"就调它）。"""
        self._dismissed = False

    # ------------------------------------------------------------------ 内部
    def _on_close(self, *_args) -> None:
        self._dismissed = True
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """自绘淡红底 + 红色圆角描边。"""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # 描边画在**半个线宽内缩**的矩形上，否则右/下边会被控件边界裁掉半条
        inset = self.BORDER / 2.0
        rect = self.rect().adjusted(
            int(inset), int(inset), -int(inset + 0.5), -int(inset + 0.5)
        )
        painter.setBrush(QColor(T.DANGER_SOFT))
        painter.setPen(QPen(QColor(T.DANGER), self.BORDER))
        painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)


__all__ = ["HintBanner"]
