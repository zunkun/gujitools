# -*- coding: utf-8 -*-
"""图片去底色（rembg）阶段面板：只有去底色自己的参数。

⚠️ 2026-10-22 用户口径：**去底色直接整个图片去底色**——这里没有 ``border``，
项目里也已没有 ``area``。按检测框裁图挪到了第二步「检测文本框」的
「提交本次任务」（参数与落地都在那边，见 ``detect_panel`` 与
``stages/detect_stage.run_detect_submit_stage``）。

由此一并删掉的还有 ``whole_page_only``：那套锁是给旧模型用的，
现在去底色压根不看框。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QFormLayout,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QWidget,
)
from qfluentwidgets import CheckBox, LineEdit, Slider

from desktop.components.common.safecomponents import SafeDoubleSpinBox, SafeSpinBox
from desktop.components.panels.base import StagePanel, default_for
from desktop.components.panels.params_spec import (
    DEFAULTS,
    REMBG_ALGORITHM_CHOICES,
    REMBG_TYPES,
)
from desktop.ui.widgets import combo_box
from utils.rembg_algorithms import LOCAL_ALGORITHM_KEYS


class RembgPanel(StagePanel):
    """图片去底色阶段面板：算法 / 局部窗口 / type / offset / 印章参数。

    整图阈值去底（7 种算法可选，可保留印章）；参数经 get_args 收集后传给
    子进程。默认值统一取 ``params_spec.DEFAULTS["rembg"]``。
    """

    #: 用户**单独改了算法**（程序化回填不算）。与 ``param_edited`` 分开：
    #: 逐张算法表只在算法真的被切过时记录，改 offset/type 不会把算法"钉死"在
    #: 某一页上（否则全量换算法时那张图会一直用旧算法）。
    algorithm_edited = Signal()

    stage = "rembg"
    title = "图片去底色"
    description = (
        "整图自动去底色/二值化/灰度化，可保留印章。"
        "去底色直接处理输入图片（整张图），不再按检测框裁剪——"
        "按框裁图是第二步「检测文本框」的「提交本次任务」做的事。"
    )

    def _build_form(self, form: QFormLayout) -> None:
        d = DEFAULTS[self.stage]
        # 阈值算法（全局默认；任务流程里改它会记到**当前这张图**上，
        # 与 offset 同一套逐张落盘规则）。值存 itemData，取值走 _combo_value。
        self.algorithm = combo_box(REMBG_ALGORITHM_CHOICES)
        self.algorithm.setCurrentIndex(
            self._index_of(self.algorithm, d["algorithm"])
        )
        self.algorithm.setToolTip(
            "阈值算法；默认 Otsu。任务流程里修改只影响当前这张图，"
            "全量执行时面板上的值作为其余图片的默认算法。"
        )
        # 局部算法的窗口与灵敏度：全局算法（otsu/fixed/mean）不需要，置灰。
        # ⚠️ 不能叫 ``self.window``：QWidget.window() 是方法，同名会把方法影子化
        # （运行期能用，但类型检查会报"给方法赋值"）。
        self.local_window = SafeSpinBox()
        self.local_window.setRange(3, 201)
        self.local_window.setSingleStep(2)
        self.local_window.setValue(int(d["window"]))
        self.local_window.setToolTip(
            "局部算法窗口边长（像素），越大越平滑但更慢；全局算法忽略"
        )
        self.k = SafeDoubleSpinBox()
        self.k.setRange(0.0, 1.0)
        self.k.setDecimals(2)
        self.k.setSingleStep(0.05)
        self.k.setValue(float(d["k"]))
        self.k.setToolTip(
            "局部算法灵敏度（0~1，默认 0.2）：Niblack 内部取负号，"
            "Bernsen 映射为局部对比度下限；全局算法忽略"
        )
        self.algorithm.currentIndexChanged.connect(self._sync_local_controls)
        self.algorithm.currentIndexChanged.connect(self._on_algorithm_changed)
        # ⚠️ type 的下拉**必须**把参数值存进 itemData，取值走 `_combo_value()`。
        # 旧实现是解析显示文本的首字符，改一个字就把取值弄挂。
        self.type = combo_box(REMBG_TYPES)
        self.type.setCurrentIndex(self._index_of(self.type, d["type"]))
        # offset 用「**滑块 + 可输入数字框**」：范围 -100~100、默认 0。
        # 允许为负，是因为最终阈值 = Otsu 自动阈值 + offset（再夹到 30~240）：
        # 负数让文字变细变淡，正数变粗变深。改完点「执行去底色」即按新参数出图。
        # 两者双向同步——setValue 在值相同时不发信号，所以不会来回循环。
        self.offset = Slider(Qt.Orientation.Horizontal)
        self.offset.setRange(-100, 100)
        self.offset.setValue(int(d["offset"]))
        self.offset.setToolTip(
            "只对全局算法（固定/均值/Otsu）生效，选局部算法时置灰；"
            "只影响当前这张图片，正数文字更粗更深，负数更细更淡，默认 0"
        )
        # 用**文本框**而不是 SpinBox：控制卡片只有 340~580px 宽，表单 field 列
        # 被挤窄后，qfluent SpinBox 的输入区会被它自带的上下按钮压成 0 宽——
        # 只剩 ^ v 两个按钮、数值根本看不见（实测截图）。文本框没有这层内部
        # 结构，再窄也能读全数值。范围由 QIntValidator 兜住。
        self.offset_input = LineEdit()
        self.offset_input.setFixedWidth(64)
        self.offset_input.setValidator(QIntValidator(-100, 100, self))
        self.offset_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.offset_input.setText(str(int(d["offset"])))
        self.offset_input.setToolTip("可直接输入 -100 ~ 100，与滑块联动")
        offset_row = QWidget()
        offset_layout = QHBoxLayout(offset_row)
        offset_layout.setContentsMargins(0, 0, 0, 0)
        offset_layout.setSpacing(8)
        offset_layout.addWidget(self.offset, 1)
        offset_layout.addWidget(self.offset_input)
        self.seal = CheckBox("保留印章（seal）")
        self.seal.setChecked(bool(d["seal"]))
        self.sealcolor = CheckBox("印章彩色（sealcolor）")
        self.sealcolor.setChecked(bool(d["sealcolor"]))
        self.sealarea = SafeSpinBox()
        self.sealarea.setRange(1, 100000)
        self.sealarea.setValue(int(d["sealarea"]))
        self.sealmin_sat = SafeSpinBox()
        self.sealmin_sat.setRange(0, 255)
        self.sealmin_sat.setValue(int(d["sealmin_sat"]))
        # 滑块 ↔ 输入框双向同步；「用户改了参数」的通知统一走基类的 param_edited
        # —— 滑块不在基类自动识别的控件类型里，由 _extra_param_signals() 补登记
        # （输入框是 QSpinBox 子类，基类会自动连上）。
        self.offset.valueChanged.connect(self._on_offset_changed)
        self.offset_input.textChanged.connect(self._on_offset_input_changed)
        # 标签格式（用户 2026-09-23 口径）：中文在前、键名放括号里。
        # 用户 2026-10-24 口径：阈值偏移紧跟阈值算法（它是对算法结果的微调），
        # 不再放到面板最后一行、也不再画分隔线。
        self._add_row(form, "阈值算法（algorithm）", self.algorithm)
        self._add_row(form, "阈值偏移（offset）", offset_row)
        # ⚠️ qfluentwidgets 的 Slider **自己不画禁用态**（paintEvent 不读
        # isEnabled），只 setEnabled(False) 的话用户看不出变化、以为没生效。
        # 这一层不透明度效果是"置灰"的可见实现；标签走 QLabel 的禁用调色板。
        self._offset_label = form.labelForField(offset_row)
        self._offset_effect = QGraphicsOpacityEffect(offset_row)
        self._offset_effect.setOpacity(1.0)
        offset_row.setGraphicsEffect(self._offset_effect)
        self._add_row(form, "窗口大小（window）", self.local_window)
        self._add_row(form, "灵敏度（k）", self.k)
        self._add_row(form, "输出类型（type）", self.type)
        self._add_row(form, "印章面积阈值（sealarea）", self.sealarea)
        self._add_row(form, "印章最小饱和度（sealmin_sat）", self.sealmin_sat)
        self._add_row(form, "", self.seal)
        self._add_row(form, "", self.sealcolor)
        self._sync_local_controls()

    @staticmethod
    def _index_of(combo, value) -> int:
        """按 itemData 找下标；找不到时回落 0（下拉第一项）。"""
        idx = combo.findData(value)
        return idx if idx >= 0 else 0

    def _combo_value(self, combo):
        """读下拉的参数值（itemData），缺失时退回显示文本。"""
        data = combo.currentData()
        return data if data is not None else combo.currentText()

    def _on_offset_changed(self, value: int) -> None:
        """滑块拖动：把值同步到右侧文本框。

        ⚠️ 拖动期间 ``valueChanged`` 会**连续发射**。这里做两件事降低噪音：

        1. **用 blockSignals 包住 setText**：否则 setText 会再走一圈
           ``textChanged`` → 本面板的输入处理 **＋** 基类的 ``param_edited``，
           一次拖动就把"用户改了参数"上报两遍（参数暂存会各自再防抖一次）。
        2. **不做节流**：面板只管如实上报；数值框同步是纯文本更新，成本可忽略。
        """
        blocked = self.offset_input.blockSignals(True)
        self.offset_input.setText(str(int(value)))
        self.offset_input.blockSignals(blocked)

    def _on_offset_input_changed(self, text: str) -> None:
        """在文本框里敲数值：夹到 [-100, 100] 后同步回滑块。

        输入中途（空串、只有负号）直接忽略——否则会被 ``int()`` 判非法或被
        当成 0，用户没法正常输入负数。
        """
        text = text.strip()
        if not text or text in ("-", "+"):
            return
        try:
            value = int(text)
        except ValueError:
            return
        self.offset.setValue(max(-100, min(100, value)))

    def _extra_param_signals(self) -> list:
        """把 offset 滑块补进 ``param_edited``。

        ⚠️ **必须补**：基类 ``_connect_param_edit_signals`` 只识别
        QLineEdit / QSpinBox / QDoubleSpinBox / QComboBox, qfluent.ComboBox /
        QCheckBox，而 ``qfluentwidgets.Slider`` 继承的是 ``QSlider``，一种都
        不沾。offset 若不登记，**「参数暂存」会静默失效**——改 offset 不再被
        当成用户改动。
        """
        return [self.offset.valueChanged]

    def _on_algorithm_changed(self, *_args) -> None:
        """算法下拉变了：程序化回填不算，用户手改才发 ``algorithm_edited``。"""
        if not self._applying:
            self.algorithm_edited.emit()

    def _sync_local_controls(self, *_args) -> None:
        """两组控件按算法类型对称置灰。

        - 局部算法（niblack/sauvola/bernsen/wolf）需要窗口与 k；
        - 全局算法（otsu/fixed/mean）需要阈值偏移 offset——局部算法是逐像素
          阈值，全局常量偏移没有意义（用户 2026-10-24 口径），因此置灰并归零。
        """
        local = str(self._combo_value(self.algorithm)) in LOCAL_ALGORITHM_KEYS
        self.local_window.setEnabled(local)
        self.k.setEnabled(local)
        self.offset.setEnabled(not local)
        self.offset_input.setEnabled(not local)
        if getattr(self, "_offset_label", None) is not None:
            self._offset_label.setEnabled(not local)
        # Slider 不自绘禁用态，用不透明度让"置灰"真的看得见（0.36 与
        # qfluentwidgets SpinBox 的禁用不透明度一致）。
        if getattr(self, "_offset_effect", None) is not None:
            self._offset_effect.setOpacity(0.36 if local else 1.0)
        if local and self.offset.value() != 0:
            # 归零时挡住信号：这次变化由"切算法"引起，不该再冒充一次用户改 offset
            blocked_slider = self.offset.blockSignals(True)
            blocked_input = self.offset_input.blockSignals(True)
            try:
                self.offset.setValue(0)
                self.offset_input.setText("0")
            finally:
                self.offset.blockSignals(blocked_slider)
                self.offset_input.blockSignals(blocked_input)

    def get_args(self) -> dict:
        """收集去底色参数（算法/窗口/k/type/offset/印章）。"""
        return {
            "algorithm": str(self._combo_value(self.algorithm)),
            "window": self.local_window.value(),
            "k": float(self.k.value()),
            "type": int(self._combo_value(self.type)),
            "offset": self.offset.value(),
            "seal": self.seal.isChecked(),
            "sealcolor": self.sealcolor.isChecked(),
            "sealarea": self.sealarea.value(),
            "sealmin_sat": self.sealmin_sat.value(),
        }

    def _apply_args(self, parameters: dict) -> None:
        d = DEFAULTS[self.stage]
        self.algorithm.setCurrentIndex(
            self._index_of(self.algorithm, default_for(parameters, d, "algorithm"))
        )
        self.local_window.setValue(int(default_for(parameters, d, "window")))
        self.k.setValue(float(default_for(parameters, d, "k")))
        self.type.setCurrentIndex(self._index_of(self.type, default_for(parameters, d, "type")))
        self.offset.setValue(int(default_for(parameters, d, "offset")))
        # 显式同步文本框：值相同时 setValue 不发信号，靠同步链路兜底更稳
        self.offset_input.setText(str(self.offset.value()))
        self.seal.setChecked(bool(default_for(parameters, d, "seal")))
        self.sealcolor.setChecked(bool(default_for(parameters, d, "sealcolor")))
        self.sealarea.setValue(int(default_for(parameters, d, "sealarea")))
        self.sealmin_sat.setValue(int(default_for(parameters, d, "sealmin_sat")))
        self._sync_local_controls()
