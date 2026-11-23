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
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QFormLayout,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QWidget,
)
from qfluentwidgets import CheckBox, LineEdit, Slider

from desktop.components.panels.base import StagePanel, default_for
from desktop.components.panels.params_spec import (
    DEFAULTS,
    REMBG_ALGORITHM_GROUPS,
    REMBG_TYPES,
)
from desktop.components.panels.rembg_params_memory import (
    load as load_param_memory,
    remember as remember_params,
)
from desktop.ui import theme as T
from desktop.ui.widgets import SectionTitle, combo_box
from utils.rembg_algorithms import LOCAL_ALGORITHM_KEYS, recommended_params

#: 印章面积阈值的滑块上限。参数本身允许 1~100000，但常用值就在默认 80、
#: 文档示例 120 这一带；滑块只覆盖常用段，更大的精确值在右侧数值框直接输入
#: （取值以数值框为准，见 ``_sealarea_value``）。
SEAL_AREA_SLIDER_MAX = 2000


class RembgPanel(StagePanel):
    """图片去底色阶段面板：算法 / 局部窗口 / type / offset / 印章参数。

    整图阈值去底（11 种算法可选，每种带一套推荐窗口/灵敏度）；参数经 get_args
    收集后传给子进程。阶段默认值取 ``params_spec.DEFAULTS["rembg"]``；算法变化时
    **窗口/灵敏度**跟着换——优先用「该算法自己调过的值」（:mod:`rembg_params_memory`
    跨会话记在 ``ui.json``），没有才用推荐值（见 :meth:`_apply_recommended_params`）。
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
        "按框裁图是第二步「检测文本框」的「分割图片」做的事。"
    )

    def _build_form(self, form: QFormLayout) -> None:
        d = DEFAULTS[self.stage]
        #: 用户**手调过**的窗口/灵敏度（按算法分账，跨会话）：切回该算法时用这份，
        #: 没有条目才用推荐值。见 ``rembg_params_memory`` 的说明。
        #: ⚠️ 必须在下面填初值**之前**读，否则重开程序后面板开头不认自己的记忆。
        self._param_memory: dict[str, dict] = load_param_memory()
        # 面板初始值：该算法自己调过的值优先，否则阶段默认（Otsu 的 25 / 0.2）。
        initial = self._param_memory.get(str(d["algorithm"])) or {
            "window": int(d["window"]),
            "k": float(d["k"]),
        }
        # ⚠️ 行距比默认紧一档（默认 SPACE_SM=8）：加了「算法/印章/输出」三个
        #    分区标题后表单明显变高，窄卡里已经压到滚动（用户 2026-11-16：
        #    "控制面板区域现在跟底部大段空白，导致出现滚轮"）。参数名与它
        #    下面的控件本来就该贴紧，4px 行距与检测面板同款。
        form.setVerticalSpacing(T.SPACE_XS)
        # 阈值算法（全局默认；任务流程里改它会记到**当前这张图**上，
        # 与 offset 同一套逐张落盘规则）。值存 itemData，取值走 _combo_value。
        # 用户 2026-11-24 口径：算法**分类摆放**——每个分类先插一条灰显、不可选
        # 的组标题（qfluent 的 ComboBox 是自绘的，``setItemEnabled(False)`` 会让
        # 该项变灰且点不动、也挡掉程序化 setCurrentIndex），再排该组的算法。
        # ⚠️ 组标题的 itemData 是 None ⇒ 绝不能用「第 0 项」当兜底（见 _index_of）。
        self.algorithm = combo_box()
        #: 组标题的下标集合（``_index_of`` 回落时跳过它们）。
        self._group_header_indexes: set[int] = set()
        for _category, _items in REMBG_ALGORITHM_GROUPS:
            self._group_header_indexes.add(self.algorithm.count())
            self.algorithm.addItem(_category)
            self.algorithm.setItemEnabled(self.algorithm.count() - 1, False)
            for _label, _key in _items:
                self.algorithm.addItem(_label, userData=_key)
        self.algorithm.setCurrentIndex(self._index_of(self.algorithm, d["algorithm"]))
        self.algorithm.setToolTip(
            "阈值算法；默认 Otsu。任务流程里修改只影响当前这张图，"
            "全量执行时面板上的值作为其余图片的默认算法。"
        )
        # 局部算法的窗口与灵敏度：全局算法（目前只剩 Otsu）不需要，置灰。
        # ⚠️ 不能叫 ``self.window``：QWidget.window() 是方法，同名会把方法影子化
        # （运行期能用，但类型检查会报"给方法赋值"）。
        # 用户 2026-11-22 口径：与「阈值偏移」同款组件——滑块 + 数值输入框。
        self.local_window = Slider(Qt.Orientation.Horizontal)
        self.local_window.setRange(3, 201)
        self.local_window.setSingleStep(2)
        self.local_window.setValue(int(initial["window"]))
        self.local_window.setToolTip(
            "局部算法窗口边长（像素），越大越平滑但更慢；全局算法忽略。"
            "切算法会跟着换：自己调过的值会被记住，否则用该算法的推荐值；"
            "页面长边超过 4000px 时按比例放大"
        )
        self.local_window_input = self._number_input()
        self.local_window_input.setValidator(QIntValidator(3, 201, self))
        self.local_window_input.setText(str(int(initial["window"])))
        self.local_window_input.setToolTip("可直接输入 3 ~ 201，与滑块联动")

        # 灵敏度滑块用整数百分比（0~100），显示成两位小数；取值范围与
        # command_spec 的 0~1 一致。
        self.k = Slider(Qt.Orientation.Horizontal)
        self.k.setRange(0, 100)
        self.k.setValue(round(float(initial["k"]) * 100))
        self.k.setToolTip(
            "局部算法灵敏度（0~1）：Niblack 内部取负号，"
            "Bernsen 映射为局部对比度下限；切算法会跟着换（自己调过的值会被记住）"
        )
        self.k_input = self._number_input()
        self.k_input.setValidator(QDoubleValidator(0.0, 1.0, 2, self))
        self.k_input.setText(f"{float(initial['k']):.2f}")
        self.k_input.setToolTip("可直接输入 0 ~ 1（两位小数），与滑块联动")
        self.algorithm.currentIndexChanged.connect(self._sync_local_controls)
        self.algorithm.currentIndexChanged.connect(self._apply_recommended_params)
        self.algorithm.currentIndexChanged.connect(self._on_algorithm_changed)
        # ⚠️ 「记住手调值」不能挂在 ``param_edited`` 上：切算法本身也会发那个
        #    信号，且早于本面板换值 ⇒ 会把**上一个算法的窗口/灵敏度**记到新算法
        #    名下（实测把 su 记成 115、gatos 记成 k=0.96）。只认这两条控件自己的
        #    变化信号（自动换值时 ``_set_local_params`` 已挡掉信号）。
        self.local_window.valueChanged.connect(self._remember_params)
        self.k.valueChanged.connect(self._remember_params)
        # ⚠️ type 的下拉**必须**把参数值存进 itemData，取值走 `_combo_value()`。
        # 旧实现是解析显示文本的首字符，改一个字就把取值弄挂。
        self.type = combo_box(REMBG_TYPES)
        self.type.setCurrentIndex(self._index_of(self.type, d["type"]))
        # offset 用「**滑块 + 可输入数字框**」：范围 -100~100、默认 0。
        # 允许为负，是因为最终阈值 = Otsu 自动阈值 + offset（再夹到 30~240）：
        # 负数让文字变细变淡，正数变粗变深。改完点「图片去底色」即按新参数出图。
        # 两者双向同步——setValue 在值相同时不发信号，所以不会来回循环。
        self.offset = Slider(Qt.Orientation.Horizontal)
        self.offset.setRange(-100, 100)
        self.offset.setValue(int(d["offset"]))
        self.offset.setToolTip(
            "只对全局算法（Otsu）生效，选局部算法时置灰；"
            "只影响当前这张图片，正数文字更粗更深，负数更细更淡，默认 0"
        )
        # 用**文本框**而不是 SpinBox：控制卡片只有 340~580px 宽，表单 field 列
        # 被挤窄后，qfluent SpinBox 的输入区会被它自带的上下按钮压成 0 宽——
        # 只剩 ^ v 两个按钮、数值根本看不见（实测截图）。文本框没有这层内部
        # 结构，再窄也能读全数值。范围由 QIntValidator 兜住。
        self.offset_input = self._number_input()
        self.offset_input.setValidator(QIntValidator(-100, 100, self))
        self.offset_input.setText(str(int(d["offset"])))
        self.offset_input.setToolTip("可直接输入 -100 ~ 100，与滑块联动")
        self.seal = CheckBox("保留印章")
        self.seal.setChecked(bool(d["seal"]))
        self.sealcolor = CheckBox("印章彩色")
        self.sealcolor.setChecked(bool(d["sealcolor"]))
        # 印章面积/饱和度同样改成「滑块 + 数值框」（用户 2026-11-22 口径）。
        # 面积阈值参数范围是 1~100000，滑块只覆盖常用段；更大的精确值直接
        # 输入右侧数值框（取值以数值框为准，见 ``_sealarea_value``）。
        self.sealarea = Slider(Qt.Orientation.Horizontal)
        self.sealarea.setRange(1, SEAL_AREA_SLIDER_MAX)
        self.sealarea.setSingleStep(10)
        self.sealarea.setValue(
            min(max(int(d["sealarea"]), 1), SEAL_AREA_SLIDER_MAX)
        )
        self.sealarea.setToolTip(
            "印章最小连通域面积（像素），越大越能过滤小噪点；"
            f"滑块范围 1~{SEAL_AREA_SLIDER_MAX}，更大值可在右侧直接输入"
        )
        self.sealarea_input = self._number_input()
        self.sealarea_input.setValidator(QIntValidator(1, 100000, self))
        self.sealarea_input.setText(str(int(d["sealarea"])))
        self.sealarea_input.setToolTip("可直接输入 1 ~ 100000，与滑块联动")
        self.sealmin_sat = Slider(Qt.Orientation.Horizontal)
        self.sealmin_sat.setRange(0, 255)
        self.sealmin_sat.setValue(int(d["sealmin_sat"]))
        self.sealmin_sat.setToolTip("红色识别最低饱和度（0~255），越大越严格")
        self.sealmin_sat_input = self._number_input()
        self.sealmin_sat_input.setValidator(QIntValidator(0, 255, self))
        self.sealmin_sat_input.setText(str(int(d["sealmin_sat"])))
        self.sealmin_sat_input.setToolTip("可直接输入 0 ~ 255，与滑块联动")
        # 滑块 ↔ 数值框双向同步：数值框是 QLineEdit，基类会自动接到
        # param_edited；滑块不在基类识别的控件类型里，由 _extra_param_signals
        # 补登记（否则「参数暂存」会静默失效）。
        self._bind_slider_input(
            self.offset, self.offset_input, str, self._parse_int
        )
        self._bind_slider_input(
            self.local_window, self.local_window_input, str, self._parse_int,
            on_change=self._remember_params,
        )
        self._bind_slider_input(
            self.k, self.k_input, lambda value: f"{value / 100:.2f}",
            self._parse_percent, on_change=self._remember_params,
        )
        self._bind_slider_input(
            self.sealarea, self.sealarea_input, str, self._parse_int
        )
        self._bind_slider_input(
            self.sealmin_sat, self.sealmin_sat_input, str, self._parse_int
        )
        # 标签格式（用户 2026-11-17 口径）：纯中文、不带英文参数键名。
        # 用户 2026-10-24 口径：阈值偏移紧跟阈值算法（它是对算法结果的微调），
        # 不再放到面板最后一行、也不再画分隔线。
        # 用户 2026-11-16 口径：分三个小分类（算法 / 印章 / 输出），标题用
        # 统一的 ``SectionTitle``（主色短竖线 + 加粗）。
        form.addRow(SectionTitle("算法"))
        self._add_row(form, "阈值算法", self.algorithm)
        # ⚠️ qfluentwidgets 的 Slider **自己不画禁用态**（paintEvent 不读
        # isEnabled），只 setEnabled(False) 的话用户看不出变化、以为没生效。
        # 每行返回的不透明度效果就是"置灰"的可见实现；标签走 QLabel 的禁用调色板。
        self._offset_label, self._offset_effect = self._add_slider_row(
            form, "阈值偏移", self.offset, self.offset_input
        )
        self._window_label, self._window_effect = self._add_slider_row(
            form, "窗口大小", self.local_window, self.local_window_input
        )
        self._k_label, self._k_effect = self._add_slider_row(
            form, "灵敏度", self.k, self.k_input
        )

        form.addRow(SectionTitle("印章"))
        # 两个开关**靠左**（用户 2026-11-16：不需要跟上面输入区对齐）——
        # addRow(控件) 跨两列；_add_row(form, "", …) 会把开关挤进右列字段位。
        form.addRow(self.seal)
        form.addRow(self.sealcolor)
        self._add_slider_row(
            form, "印章面积阈值", self.sealarea, self.sealarea_input
        )
        self._add_slider_row(
            form, "印章最小饱和度", self.sealmin_sat, self.sealmin_sat_input
        )

        form.addRow(SectionTitle("输出"))
        self._add_row(form, "输出类型", self.type)
        self._sync_local_controls()

    def _index_of(self, combo, value) -> int:
        """按 itemData 找下标；找不到时回落到**第一个可选算法**。

        ⚠️ 不能回落第 0 项：算法下拉的第 0 项是分组标题（灰显、itemData=None），
        落到它上面 ``_combo_value`` 会返回组名，参数就带着一个非法算法跑出去了
        （历史参数里写着已下线的 fixed/mean 时正是这条路径）。
        """
        idx = combo.findData(value)
        if idx >= 0:
            return idx
        headers = (
            self._group_header_indexes
            if combo is getattr(self, "algorithm", None)
            else set()
        )
        for index in range(combo.count()):
            if index not in headers:
                return index
        return 0

    def _combo_value(self, combo):
        """读下拉的参数值（itemData），缺失时退回显示文本。

        ⚠️ 算法下拉里夹着灰显的分组标题（itemData=None）。用户点不动它们，但
        程序化 ``setCurrentIndex`` 能落上去（qfluent 不拦）——真落上去就按阶段
        默认算法返回，绝不让组名（"全局阈值"）当成算法值跑到产物里。
        """
        data = combo.currentData()
        if data is None and combo is getattr(self, "algorithm", None):
            return str(DEFAULTS[self.stage]["algorithm"])
        return data if data is not None else combo.currentText()

    @staticmethod
    def _number_input() -> LineEdit:
        """滑块右侧的数值框：64px、居中（窄卡片里也能读全数值）。"""
        line = LineEdit()
        line.setFixedWidth(64)
        line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return line

    def _add_slider_row(self, form: QFormLayout, label: str, slider, line_edit):
        """加一行「滑块 + 数值框」，返回（标签控件, 置灰用的不透明度效果）。"""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(slider, 1)
        layout.addWidget(line_edit)
        self._add_row(form, label, row)
        effect = QGraphicsOpacityEffect(row)
        effect.setOpacity(1.0)
        row.setGraphicsEffect(effect)
        return form.labelForField(row), effect

    def _bind_slider_input(
        self, slider, line_edit, to_text, from_text, on_change=None
    ) -> None:
        """滑块 ↔ 数值框双向同步。

        ⚠️ 滑块 → 数值框要 ``blockSignals``：否则一次拖动会经 ``textChanged``
        再上报一遍（数值框是 QLineEdit，基类已把它接到 ``param_edited``）。
        数值框 → 滑块同样挡住滑块信号：滑块因范围夹紧而发出 valueChanged 时，
        不能反过来覆盖用户刚输入的数字（印章面积阈值允许输入超过滑块上限的值）。

        ``on_change``：**用户真的改了值**时的回调（滑块拖动走 valueChanged，
        数值框输入因为挡了滑块信号，得在这里显式叫一声）。窗口/灵敏度的「记住
        手调值」就靠它——不能用 ``param_edited``，那个信号切算法时也会发。
        """
        def on_slider(value: int) -> None:
            blocked = line_edit.blockSignals(True)
            line_edit.setText(to_text(int(value)))
            line_edit.blockSignals(blocked)

        def on_text(text: str) -> None:
            parsed = from_text(text)
            if parsed is None:
                return
            blocked = slider.blockSignals(True)
            slider.setValue(int(parsed))
            slider.blockSignals(blocked)
            if on_change is not None:
                on_change()

        slider.valueChanged.connect(on_slider)
        line_edit.textChanged.connect(on_text)

    @staticmethod
    def _parse_int(text: str):
        """数值框文本 → int；空串 / 中间态（只有负号）→ None（忽略这次输入）。"""
        text = text.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None

    @staticmethod
    def _parse_percent(text: str):
        """灵敏度文本（0~1，两位小数）→ 滑块百分比整数；非法 → None。"""
        text = text.strip()
        if not text:
            return None
        try:
            return round(float(text) * 100)
        except ValueError:
            return None

    def _sealarea_value(self) -> int:
        """印章面积阈值：以数值框为准（滑块只覆盖常用段，更大值只能输入）。"""
        try:
            return max(1, int(self.sealarea_input.text().strip()))
        except ValueError:
            return self.sealarea.value()

    def _extra_param_signals(self) -> list:
        """把面板里的滑块补进 ``param_edited``。

        ⚠️ **必须补**：基类 ``_connect_param_edit_signals`` 只识别 QLineEdit /
        QSpinBox / QDoubleSpinBox / QComboBox / qfluent.ComboBox / QCheckBox，
        而 ``qfluentwidgets.Slider`` 继承的是 ``QSlider``，一种都不沾。不登记
        的话**「参数暂存」会静默失效**——拖动滑块不再被当成用户改动。
        """
        return [
            self.offset.valueChanged,
            self.local_window.valueChanged,
            self.k.valueChanged,
            self.sealarea.valueChanged,
            self.sealmin_sat.valueChanged,
        ]

    def _on_algorithm_changed(self, *_args) -> None:
        """算法下拉变了：程序化回填不算，用户手改才发 ``algorithm_edited``。"""
        if not self._applying:
            self.algorithm_edited.emit()

    def _apply_recommended_params(self, *_args) -> None:
        """切算法时把「窗口/灵敏度」换成该算法的最优值（**无条件跟随**）。

        取值的优先级（用户 2026-11-24 口径）：

        1. 这个算法**自己手调过**的值（``_param_memory``，跨会话记在 ``ui.json``）——
           "自己改过的最优"优先，切走再切回来还是自己那组；
        2. 否则用 :func:`utils.rembg_algorithms.recommended_params` 的推荐值。

        ⚠️ 程序化回填（``apply_args``，``_applying`` 为真）期间**不改控件**：
        历史参数必须原样生效，老任务才复现得出原来的结果；那时由
        :meth:`_apply_args` 自己按「有存值用存值、缺键用推荐值」写值。
        """
        if self._applying:
            return
        key = str(self._combo_value(self.algorithm))
        target = self._param_memory.get(key) or recommended_params(key)
        self._set_local_params(target["window"], target["k"])

    def _remember_params(self, *_args) -> None:
        """用户手调窗口/灵敏度后，按当前算法记账（只记与推荐值不同的组合）。

        * 值等于该算法的推荐值 ⇒ **删掉**这条记忆（回到"跟推荐值走"，避免把
          默认值当成"用户的最优"存一屋子）；
        * 写盘失败只影响下次启动的恢复，静默即可（:mod:`rembg_params_memory`
          内部吞异常）。
        """
        if self._applying:
            return
        key = str(self._combo_value(self.algorithm))
        current = {
            "window": int(self.local_window.value()),
            "k": round(self.k.value() / 100.0, 2),
        }
        target = None if current == recommended_params(key) else current
        if self._param_memory.get(key) == target:
            return
        if target is None:
            self._param_memory.pop(key, None)
        else:
            self._param_memory[key] = target
        remember_params(key, target)

    def _set_local_params(self, window: int, k: float) -> None:
        """写窗口/灵敏度（整条同步链挡信号：这不是用户手改，不该发 param_edited）。

        ⚠️ 必须连数值框一起挡：``_bind_slider_input`` 会由滑块 setValue 触发
        ``textChanged``，而数值框是基类认定的"用户改动"控件。
        """
        blocked = [
            (self.local_window, self.local_window.blockSignals(True)),
            (self.local_window_input, self.local_window_input.blockSignals(True)),
            (self.k, self.k.blockSignals(True)),
            (self.k_input, self.k_input.blockSignals(True)),
        ]
        try:
            self.local_window.setValue(int(window))
            self.local_window_input.setText(str(self.local_window.value()))
            self.k.setValue(round(float(k) * 100))
            self.k_input.setText(f"{self.k.value() / 100:.2f}")
        finally:
            for widget, state in blocked:
                widget.blockSignals(state)

    def _sync_local_controls(self, *_args) -> None:
        """两组控件按算法类型对称置灰。

        - 局部算法（除 Otsu 以外的全部）需要窗口与 k；
        - 全局算法（目前只剩 Otsu）需要阈值偏移 offset——局部算法是逐像素
          阈值，全局常量偏移没有意义（用户 2026-10-24 口径），因此置灰并归零。
        """
        local = str(self._combo_value(self.algorithm)) in LOCAL_ALGORITHM_KEYS
        self.local_window.setEnabled(local)
        self.local_window_input.setEnabled(local)
        self.k.setEnabled(local)
        self.k_input.setEnabled(local)
        self.offset.setEnabled(not local)
        self.offset_input.setEnabled(not local)
        # Slider 不自绘禁用态，用不透明度让"置灰"真的看得见（0.36 与
        # qfluentwidgets SpinBox 的禁用不透明度一致）；标签走 QLabel 的禁用调色板。
        for label, effect, enabled in (
            (self._window_label, self._window_effect, local),
            (self._k_label, self._k_effect, local),
            (self._offset_label, self._offset_effect, not local),
        ):
            if label is not None:
                label.setEnabled(enabled)
            effect.setOpacity(1.0 if enabled else 0.36)
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
            "k": round(self.k.value() / 100.0, 2),
            "type": int(self._combo_value(self.type)),
            "offset": self.offset.value(),
            "seal": self.seal.isChecked(),
            "sealcolor": self.sealcolor.isChecked(),
            "sealarea": self._sealarea_value(),
            "sealmin_sat": self.sealmin_sat.value(),
        }

    def _apply_args(self, parameters: dict) -> None:
        d = DEFAULTS[self.stage]
        self.algorithm.setCurrentIndex(
            self._index_of(self.algorithm, default_for(parameters, d, "algorithm"))
        )
        # 窗口/灵敏度：历史参数里有就用存的（老任务按原参数复现）；**没有才**用
        # 当前算法的推荐值——阶段默认表里的 25/0.2 只是 Otsu 的，拿它回填
        # niblack/bernsen 会偏低（推荐 0.40）。
        fallback = recommended_params(str(self._combo_value(self.algorithm)))
        window = parameters.get("window")
        if window is None:
            window = fallback["window"]
        k_value = parameters.get("k")
        if k_value is None:
            k_value = fallback["k"]
        self.local_window.setValue(int(window))
        self.local_window_input.setText(str(self.local_window.value()))
        self.k.setValue(round(float(k_value) * 100))
        self.k_input.setText(f"{self.k.value() / 100:.2f}")
        self.type.setCurrentIndex(
            self._index_of(self.type, default_for(parameters, d, "type"))
        )
        self.offset.setValue(int(default_for(parameters, d, "offset")))
        # 显式同步文本框：值相同时 setValue 不发信号，靠同步链路兜底更稳
        self.offset_input.setText(str(self.offset.value()))
        self.seal.setChecked(bool(default_for(parameters, d, "seal")))
        self.sealcolor.setChecked(bool(default_for(parameters, d, "sealcolor")))
        # 印章面积阈值允许超出滑块上限：滑块夹到区间内，数值框保留原值，
        # get_args 以数值框为准。
        sealarea = int(default_for(parameters, d, "sealarea"))
        self.sealarea.setValue(min(max(sealarea, 1), SEAL_AREA_SLIDER_MAX))
        self.sealarea_input.setText(str(sealarea))
        self.sealmin_sat.setValue(int(default_for(parameters, d, "sealmin_sat")))
        self.sealmin_sat_input.setText(str(self.sealmin_sat.value()))
        self._sync_local_controls()
