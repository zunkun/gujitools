# -*- coding: utf-8 -*-
"""图片去底色（rembg）阶段面板：area 决定裁剪方式，border 决定四周留白。"""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout
from qfluentwidgets import CheckBox, LineEdit

from core.command_spec import effective_border_default
from desktop.components.common.safecomment import SafeSpinBox
from desktop.components.panels.base import StagePanel, default_for
from desktop.components.panels.params_spec import DEFAULTS, REMBG_AREAS, REMBG_TYPES
from desktop.ui.widgets import combo_box


class RembgPanel(StagePanel):
    """图片去底色阶段面板：area/border/印章等参数。

    整图 Otsu 二值化/灰度化去底（可保留印章）；area 决定裁剪方式、
    border 决定四周留白，参数经 get_args 收集后传给子进程。默认值统一取
    ``params_spec.DEFAULTS["rembg"]``。
    """

    stage = "rembg"
    title = "图片去底色 (rembg)"
    description = (
        "整图 Otsu 二值化/灰度化去底，可保留印章。"
        "area/border 决定显示与裁剪区域（配合步骤二的检测框）。"
    )

    def _build_form(self, form: QFormLayout) -> None:
        d = DEFAULTS[self.stage]
        # 用户是否手填过 border：手填过就不再被 area 的默认值覆盖
        # （与 print 面板「用户改过边距就不级联」同一套路）
        self._border_edited = False
        # ⚠️ area/type 的下拉**必须**把参数值存进 itemData，取值走 `_combo_value()`。
        # 旧实现是 `int(self.area.currentText()[0])`——解析显示文本的首字符，
        # 改一个字（如「1 (左右分开)」→「一、左右分开」）就把取值弄挂。
        self.area = combo_box(REMBG_AREAS)
        self.area.setCurrentIndex(self._index_of(self.area, d["area"]))
        self.area.setToolTip(
            "4 = 整页：把整页当作唯一文本框（不调用 YOLO），边框画在页面边界，"
            "仍可在第二步拖动/重画；适合普通文档或古籍检测失败时整页去底色"
        )
        self.border = LineEdit()
        self.border.setPlaceholderText("留空 或 30 / 20,30 / 20,30,25,35")
        # 初值 = 当前 area 的 border 默认（area=1/2/3 → 0、area=4 → 空）
        self.border.setText(self._border_default_for(d["area"]))
        self.type = combo_box(REMBG_TYPES)
        self.type.setCurrentIndex(self._index_of(self.type, d["type"]))
        self.offset = SafeSpinBox()
        # offset 允许为负：最终阈值 = Otsu 自动阈值 + offset（再夹到 30~240），
        # 负数让文字变细变淡，正数变粗变深，因此下界必须是负数。
        self.offset.setRange(-100, 100)
        self.offset.setValue(int(d["offset"]))
        self.offset.setToolTip("正数文字更粗更深，负数更细更淡；默认 0（自动阈值）")
        self.seal = CheckBox("保留印章 (seal)")
        self.seal.setChecked(bool(d["seal"]))
        self.sealcolor = CheckBox("印章彩色 (sealcolor)")
        self.sealcolor.setChecked(bool(d["sealcolor"]))
        self.sealarea = SafeSpinBox()
        self.sealarea.setRange(1, 100000)
        self.sealarea.setValue(int(d["sealarea"]))
        self.sealmin_sat = SafeSpinBox()
        self.sealmin_sat.setRange(0, 255)
        self.sealmin_sat.setValue(int(d["sealmin_sat"]))
        # area 一变就按新 area 刷 border 默认值（用户手填过则保留其输入）
        self.area.currentIndexChanged.connect(self._on_area_changed)
        self.border.textEdited.connect(self._on_border_edited)
        self.border.setToolTip(
            "留空时按 area 取默认：area=1/2/3 → 0（不加留白，第四步会在 A4 "
            "上重新排版）；area=4（整页）→ 不设 border"
        )
        self._add_row(form, "area 区域模式", self.area)
        self._add_row(form, "border 边距(mm)", self.border)
        self._add_row(form, "type 输出类型", self.type)
        self._add_row(form, "offset 阈值偏移", self.offset)
        self._add_row(form, "印章面积阈值", self.sealarea)
        self._add_row(form, "印章最小饱和度", self.sealmin_sat)
        self._add_row(form, "", self.seal)
        self._add_row(form, "", self.sealcolor)

    @staticmethod
    def _index_of(combo, value) -> int:
        """按 itemData 找下标；找不到时回落 0（下拉第一项）。"""
        idx = combo.findData(value)
        return idx if idx >= 0 else 0

    def _combo_value(self, combo):
        """读下拉的参数值（itemData），缺失时退回显示文本。"""
        data = combo.currentData()
        return data if data is not None else combo.currentText()

    @staticmethod
    def _border_default_for(area) -> str:
        """area 对应的 border 默认显示值（area=4 无 border → 空串）。"""
        value = effective_border_default(area)
        return "" if value is None else str(value)

    def _on_area_changed(self, _index: int = 0) -> None:
        """area 切换：把 border 刷成该 area 的默认值（用户手填过则不动）。"""
        if getattr(self, "_applying", False) or self._border_edited:
            return
        self.border.setText(self._border_default_for(self._combo_value(self.area)))

    def _on_border_edited(self, _text: str = "") -> None:
        """用户手改 border：记下来，之后 area 变化不再覆盖它。"""
        self._border_edited = True

    def get_args(self) -> dict:
        """收集去底色参数：area/type/offset/seal/border 等。

        border 留空时按 area 取默认（area=1/2/3 → 0、area=4 → 不设），
        由 runner 在续跑时与 detect 框坐标实时合成裁剪区域。
        """
        area = int(self._combo_value(self.area))
        args = {
            "area": area,
            "type": int(self._combo_value(self.type)),
            "offset": self.offset.value(),
            "seal": self.seal.isChecked(),
            "sealcolor": self.sealcolor.isChecked(),
            "sealarea": self.sealarea.value(),
            "sealmin_sat": self.sealmin_sat.value(),
        }
        border_text = self.border.text().strip() or self._border_default_for(area)
        if border_text:
            args["border"] = border_text
        return args

    def _apply_args(self, parameters: dict) -> None:
        d = DEFAULTS[self.stage]
        area_value = default_for(parameters, d, "area")
        self.area.setCurrentIndex(self._index_of(self.area, area_value))
        # border 留空（含"没这个键"）→ 按 area 取默认；显式给的值原样回填，
        # 且与默认值不同就视为"用户手填过"，后续 area 切换不覆盖
        border_text = str(parameters.get("border") or "").strip()
        default_text = self._border_default_for(area_value)
        if not border_text:
            border_text = default_text
        self.border.setText(border_text)
        self._border_edited = bool(border_text) and border_text != default_text
        self.type.setCurrentIndex(self._index_of(self.type, default_for(parameters, d, "type")))
        self.offset.setValue(int(default_for(parameters, d, "offset")))
        self.seal.setChecked(bool(default_for(parameters, d, "seal")))
        self.sealcolor.setChecked(bool(default_for(parameters, d, "sealcolor")))
        self.sealarea.setValue(int(default_for(parameters, d, "sealarea")))
        self.sealmin_sat.setValue(int(default_for(parameters, d, "sealmin_sat")))
