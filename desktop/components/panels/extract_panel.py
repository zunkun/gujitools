# -*- coding: utf-8 -*-
"""提取图片阶段面板。"""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout
from qfluentwidgets import CheckBox, LineEdit

from desktop.components.common.safecomment import SafeSpinBox
from desktop.components.panels.base import StagePanel, default_for
from desktop.components.panels.params_spec import DEFAULTS, EXTRACT_EXTS
from desktop.ui.widgets import combo_box


class ExtractPanel(StagePanel):
    """提取图片阶段面板：设置缩放、目标 DPI、格式与页码范围。

    extract 阶段把源 PDF 每页渲染为图片；参数经 get_args 收集后由 runner
    写入子进程配置，input/output 由系统接管。默认值统一取
    ``params_spec.DEFAULTS["extract"]``（控件初值与回填兜底同一份）。
    """

    stage = "extract"
    title = "提取图片 (extract)"
    description = (
        "将源 PDF 每页渲染为图片。左侧可切换「PDF 预览 / 提取结果」两个标签页。"
    )

    def _build_form(self, form: QFormLayout) -> None:
        d = DEFAULTS[self.stage]
        self.zoom = SafeSpinBox()
        self.zoom.setRange(1, 8)
        self.zoom.setValue(int(d["zoom"]))
        self.dpi = SafeSpinBox()
        self.dpi.setRange(72, 1200)
        self.dpi.setSingleStep(50)
        self.dpi.setValue(int(d["dpi"]))
        self.dpi.setToolTip(
            "整页渲染的 DPI 下限，默认 300。\n"
            "PDF 的 1pt 在 zoom=1 时只渲染成 1px（=72 DPI），矢量文档这样\n"
            "提取出来一放大就糊；补到 300 DPI 才能保证打印清晰。\n"
            "取内嵌图（quick）时按原图字节落盘，这个值不生效。\n"
            "想要旧的 72 DPI 行为，就把它设成 72。"
        )
        self.ext = combo_box(list(EXTRACT_EXTS))
        self.ext.setCurrentText(str(d["ext"]))
        self.quick = CheckBox("优先取内嵌图 (quick)")
        self.quick.setChecked(bool(d["quick"]))
        self.quick.setToolTip(
            "直接取 PDF 内嵌的 jpg/png 图，通常更快且分辨率更高。\n"
            "一页有多张图、内嵌格式是 jp2/jbig2 等、或内嵌图偏小时，"
            "会自动降级为整页渲染。"
        )
        self.pages_edit = LineEdit()
        self.pages_edit.setPlaceholderText("留空=全部页，示例：1,2,5-7")
        self._add_row(form, "缩放因子 zoom", self.zoom)
        self._add_row(form, "目标 DPI dpi", self.dpi)
        self._add_row(form, "输出格式 ext", self.ext)
        self._add_row(form, "快速模式 quick", self.quick)
        self._add_row(form, "页码范围 pages", self.pages_edit)

    def get_args(self) -> dict:
        """收集提取参数：zoom/dpi/ext/quick/pages（不含 input/output）。

        pages 留空表示全部页；非法页码由 runner 在取参时以 ValueError 拦截。
        dpi 默认 300，是**整页渲染**的 DPI 下限（内嵌图路径不生效）。
        """
        args = {
            "zoom": self.zoom.value(),
            "dpi": self.dpi.value(),
            "ext": self.ext.currentText(),
            "quick": self.quick.isChecked(),
        }
        if self.pages_edit.text().strip():
            args["pages"] = self.pages_edit.text().strip()
        return args

    def _apply_args(self, parameters: dict) -> None:
        d = DEFAULTS[self.stage]
        self.zoom.setValue(int(default_for(parameters, d, "zoom")))
        # ⚠️ dpi 的默认值是 300，用 default_for 的「None 也回落」语义：
        # 历史里存着 dpi: null 时不能把 None 塞进 setValue
        self.dpi.setValue(int(default_for(parameters, d, "dpi")))
        self.ext.setCurrentText(str(default_for(parameters, d, "ext")))
        self.quick.setChecked(bool(default_for(parameters, d, "quick")))
        self.pages_edit.setText(str(parameters.get("pages") or ""))

