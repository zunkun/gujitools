# -*- coding: utf-8 -*-
"""顶部子任务步骤条：当前步骤高亮显示。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import PushButton

_CURRENT_STYLE = """
PushButton {
    background-color: #0078d4;
    color: white;
    border: 1px solid #0078d4;
    border-radius: 4px;
    font-weight: 600;
}
PushButton:hover { background-color: #1a86d9; }
PushButton:pressed { background-color: #005a9e; }
"""

_COMPLETED_STYLE = """
PushButton {
    background-color: rgba(0, 120, 212, 0.12);
    color: #0078d4;
    border: 1px solid rgba(0, 120, 212, 0.35);
    border-radius: 4px;
}
"""


class StepBar(QWidget):
    """横向步骤条：点击切换子任务；当前步骤蓝色高亮，已完成步骤淡蓝标记。"""

    current_changed = Signal(int)

    def __init__(self, steps: list[str], parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.buttons: list[PushButton] = []
        self._completed: set[int] = set()
        for index, label in enumerate(steps):
            button = PushButton(f"{index + 1}. {label}")
            button.setCheckable(True)
            button.clicked.connect(lambda _=False, i=index: self._on_click(i))
            layout.addWidget(button)
            self.buttons.append(button)
        layout.addStretch()
        self._current = 0
        self._sync()

    def _on_click(self, index: int) -> None:
        self.set_current(index)
        self.current_changed.emit(index)

    def set_current(self, index: int) -> None:
        self._current = index
        self._sync()

    def mark_completed(self, index: int) -> None:
        """标记某步骤已完成（淡蓝样式，与当前高亮区分）。"""
        self._completed.add(index)
        self._sync()

    def _sync(self) -> None:
        for index, button in enumerate(self.buttons):
            button.setChecked(index == self._current)
            if index == self._current:
                button.setStyleSheet(_CURRENT_STYLE)
            elif index in self._completed:
                button.setStyleSheet(_COMPLETED_STYLE)
            else:
                button.setStyleSheet("")

    def set_steps(self, texts: list[str]) -> None:
        for button, text in zip(self.buttons, texts):
            button.setText(text)
