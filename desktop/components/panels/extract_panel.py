# -*- coding: utf-8 -*-
"""提取图片阶段面板。"""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout
from qfluentwidgets import ComboBox, LineEdit, SpinBox

from .base import StagePanel


class ExtractPanel(StagePanel):
    stage = "extract"
    title = "提取图片 (extract)"
    description = "将源 PDF 每页渲染为图片。左侧可切换「PDF 预览 / 提取结果」两个标签页。"

    def _build_form(self, form: QFormLayout) -> None:
        self.zoom = SpinBox()
        self.zoom.setRange(1, 8)
        self.ext = ComboBox()
        self.ext.addItems(["jpg", "png"])
        self.pages_edit = LineEdit()
        self.pages_edit.setPlaceholderText("留空=全部页，示例：1,2,5-7")
        self._add_row(form, "缩放因子 zoom", self.zoom)
        self._add_row(form, "输出格式 ext", self.ext)
        self._add_row(form, "页码范围 pages", self.pages_edit)

    def get_args(self) -> dict:
        args = {"zoom": self.zoom.value(), "ext": self.ext.currentText()}
        if self.pages_edit.text().strip():
            args["pages"] = self.pages_edit.text().strip()
        return args

    def _apply_args(self, parameters: dict) -> None:
        self.zoom.setValue(int(parameters.get("zoom", 1)))
        self.ext.setCurrentText(parameters.get("ext", "jpg"))
        self.pages_edit.setText(str(parameters.get("pages") or ""))
