# -*- coding: utf-8 -*-
"""阶段控制面板基类：标题 + 说明 + 参数表单骨架。"""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, SubtitleLabel


class StagePanel(QWidget):
    """阶段控制面板：标题 + 说明 + 参数表单。子类实现 _build_form/get_args。"""

    stage: str = ""
    title: str = ""
    description: str = ""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(SubtitleLabel(self.title))
        layout.addWidget(BodyLabel(self.description))
        layout.addWidget(self.build_form())
        layout.addStretch()

    def build_form(self) -> QWidget:
        container = QWidget()
        form = QFormLayout(container)
        form.setContentsMargins(0, 0, 0, 0)
        self._build_form(form)
        return container

    def _add_row(self, form: QFormLayout, label: str, widget) -> None:
        form.addRow(label, widget)

    def _build_form(self, form: QFormLayout) -> None:  # pragma: no cover
        raise NotImplementedError

    def get_args(self) -> dict:
        """从表单收集该阶段参数（不含 input/output/clean）。"""
        raise NotImplementedError

    def apply_args(self, parameters: dict) -> None:
        """把一次历史执行的参数回填到表单（多余键忽略）。"""
        self._apply_args(parameters or {})

    def _apply_args(self, parameters: dict) -> None:  # pragma: no cover
        raise NotImplementedError
