# -*- coding: utf-8 -*-
"""提取图片阶段面板。"""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout
from qfluentwidgets import CheckBox, LineEdit, SpinBox

from desktop.components.panels.base import StagePanel
from desktop.ui.widgets import combo_box


class ExtractPanel(StagePanel):
    """提取图片阶段面板：设置缩放、格式与页码范围。

    extract 阶段把源 PDF 每页渲染为图片；参数经 get_args 收集后由 runner
    写入子进程配置，input/output 由系统接管。
    """

    stage = "extract"
    title = "提取图片 (extract)"
    description = "将源 PDF 每页渲染为图片。左侧可切换「PDF 预览 / 提取结果」两个标签页。"

    def _build_form(self, form: QFormLayout) -> None:
        self.zoom = SpinBox()
        self.zoom.setRange(1, 8)
        self.ext = combo_box(["jpg", "png"])
        self.quick = CheckBox("优先取内嵌图 (quick)")
        self.quick.setChecked(True)
        self.quick.setToolTip(
            "直接取 PDF 内嵌的 jpg/png 图，通常更快且分辨率更高。\n"
            "一页有多张图、内嵌格式是 jp2/jbig2 等、或内嵌图偏小时，"
            "会自动降级为整页渲染。"
        )
        self.pages_edit = LineEdit()
        self.pages_edit.setPlaceholderText("留空=全部页，示例：1,2,5-7")
        self._add_row(form, "缩放因子 zoom", self.zoom)
        self._add_row(form, "输出格式 ext", self.ext)
        self._add_row(form, "快速模式 quick", self.quick)
        self._add_row(form, "页码范围 pages", self.pages_edit)

    def get_args(self) -> dict:
        """收集提取参数：zoom/ext/quick/pages（不含 input/output）。

        pages 留空表示全部页；非法页码由 runner 在取参时以 ValueError 拦截。
        """
        args = {
            "zoom": self.zoom.value(),
            "ext": self.ext.currentText(),
            "quick": self.quick.isChecked(),
        }
        if self.pages_edit.text().strip():
            args["pages"] = self.pages_edit.text().strip()
        return args

    def _apply_args(self, parameters: dict) -> None:
        self.zoom.setValue(int(parameters.get("zoom", 1)))
        self.ext.setCurrentText(parameters.get("ext", "jpg"))
        self.quick.setChecked(bool(parameters.get("quick", True)))
        self.pages_edit.setText(str(parameters.get("pages") or ""))
