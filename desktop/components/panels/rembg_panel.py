# -*- coding: utf-8 -*-
"""图片去底色（rembg）阶段面板：area 决定裁剪方式，border 决定四周留白。"""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout
from qfluentwidgets import CheckBox, ComboBox, LineEdit, SpinBox

from .base import StagePanel


class RembgPanel(StagePanel):
    stage = "rembg"
    title = "图片去底色 (rembg)"
    description = (
        "整图 Otsu 二值化/灰度化去底，可保留印章。"
        "area/border 决定显示与裁剪区域（配合步骤二的检测框）。"
    )

    def _build_form(self, form: QFormLayout) -> None:
        self.area = ComboBox()
        self.area.addItems(["1 (左右分开)", "2 (合并单图)", "3 (整页合并)"])
        self.border = LineEdit()
        self.border.setPlaceholderText("留空 或 30 / 20,30 / 20,30,25,35")
        self.type = ComboBox()
        self.type.addItems(["1 (二值)", "2 (1bit)", "3 (灰度)"])
        self.offset = SpinBox()
        self.offset.setRange(0, 100)
        self.seal = CheckBox("保留印章 (seal)")
        self.sealcolor = CheckBox("印章彩色 (sealcolor)")
        self.sealarea = SpinBox()
        self.sealarea.setRange(1, 100000)
        self.sealarea.setValue(80)
        self.sealmin_sat = SpinBox()
        self.sealmin_sat.setRange(0, 255)
        self.sealmin_sat.setValue(50)
        self._add_row(form, "area 区域模式", self.area)
        self._add_row(form, "border 边距(mm)", self.border)
        self._add_row(form, "type 输出类型", self.type)
        self._add_row(form, "offset 阈值偏移", self.offset)
        self._add_row(form, "印章面积阈值", self.sealarea)
        self._add_row(form, "印章最小饱和度", self.sealmin_sat)
        self._add_row(form, "", self.seal)
        self._add_row(form, "", self.sealcolor)

    def get_args(self) -> dict:
        args = {
            "area": int(self.area.currentText()[0]),
            "type": int(self.type.currentText()[0]),
            "offset": self.offset.value(),
            "seal": self.seal.isChecked(),
            "sealcolor": self.sealcolor.isChecked(),
            "sealarea": self.sealarea.value(),
            "sealmin_sat": self.sealmin_sat.value(),
        }
        if self.border.text().strip():
            args["border"] = self.border.text().strip()
        return args

    def _apply_args(self, parameters: dict) -> None:
        self.area.setCurrentIndex(
            min(max(int(parameters.get("area", 1)) - 1, 0), self.area.count() - 1)
        )
        self.border.setText(str(parameters.get("border") or ""))
        self.type.setCurrentIndex(
            min(max(int(parameters.get("type", 1)) - 1, 0), self.type.count() - 1)
        )
        self.offset.setValue(int(parameters.get("offset", 0)))
        self.seal.setChecked(bool(parameters.get("seal", False)))
        self.sealcolor.setChecked(bool(parameters.get("sealcolor", False)))
        self.sealarea.setValue(int(parameters.get("sealarea", 80)))
        self.sealmin_sat.setValue(int(parameters.get("sealmin_sat", 50)))
