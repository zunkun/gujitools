# -*- coding: utf-8 -*-
"""图片去底色（rembg）阶段面板：area 决定裁剪方式，border 决定四周留白。"""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout
from qfluentwidgets import CheckBox, LineEdit, SpinBox

from desktop.components.panels.base import StagePanel
from desktop.ui.widgets import combo_box


class RembgPanel(StagePanel):
    """图片去底色阶段面板：area/border/印章等参数。

    整图 Otsu 二值化/灰度化去底（可保留印章）；area 决定裁剪方式、
    border 决定四周留白，参数经 get_args 收集后传给子进程。
    """

    stage = "rembg"
    title = "图片去底色 (rembg)"
    description = (
        "整图 Otsu 二值化/灰度化去底，可保留印章。"
        "area/border 决定显示与裁剪区域（配合步骤二的检测框）。"
    )

    def _build_form(self, form: QFormLayout) -> None:
        self.area = combo_box(["1 (左右分开)", "2 (合并单图)", "3 (整页合并)"])
        self.border = LineEdit()
        self.border.setPlaceholderText("留空 或 30 / 20,30 / 20,30,25,35")
        self.type = combo_box(["1 (二值)", "2 (1bit)", "3 (灰度)"])
        self.offset = SpinBox()
        # offset 允许为负：最终阈值 = Otsu 自动阈值 + offset（再夹到 30~240），
        # 负数让文字变细变淡，正数变粗变深，因此下界必须是负数。
        self.offset.setRange(-100, 100)
        self.offset.setToolTip(
            "正数文字更粗更深，负数更细更淡；默认 0（自动阈值）"
        )
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
        """收集去底色参数：area/type/offset/seal/border 等。

        area/type 取下拉首字符数字；border 留空表示 0，由 runner 在续跑时
        与 detect 框坐标实时合成裁剪区域。
        """
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
