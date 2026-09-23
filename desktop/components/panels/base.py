# -*- coding: utf-8 -*-
"""阶段控制面板基类：标题 + 说明 + 参数表单骨架。

标题与说明都开启换行——右侧参数卡片只有 340~580px 宽，长说明不换行会
把面板撑出横向边界（原来靠各子类自己调 setWordWrap 兜着）。
"""

from __future__ import annotations

import re

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit,
    QSpinBox, QVBoxLayout, QWidget,
)
from qfluentwidgets import ComboBox, ScrollArea

from desktop.ui import theme as T
from desktop.ui.widgets import apply_to


def default_for(parameters: dict, defaults: dict, key: str):
    """取回填值：``parameters`` 里有且**不为 None** 时用它，否则回落 ``defaults[key]``。

    ⚠️ 不能写成 ``parameters.get(key, defaults[key])``——历史配置里存着
    ``{"dpi": null}`` 时，``get`` 会返回 ``None``，兜底**永不生效**，直接
    ``setValue(None)`` 就崩（这是本仓库反复踩到的 None 默认值陷阱）。
    也不能写成 ``parameters.get(key) or ...``——布尔键的合法值 ``False``
    与数值键的合法值 ``0`` 会被误判成"没值"而回落到默认。
    """
    value = parameters.get(key)
    if value is None:
        return defaults.get(key)
    return value


class _ShrinkableForm(QWidget):
    """参数表单容器：**水平方向允许被压缩到 0**。

    为什么需要它：qfluentwidgets 的滚动条是**浮在内容上**的（overlay），而
    QFormLayout 的最小宽度 = 各行 field 的 minimumSizeHint 之和，qfluent 的
    SpinBox / ComboBox 自带 170px 量级的 minimumSizeHint，很容易超过窄卡片里的
    视口宽度。容器一旦被撑宽，最右侧控件就滑到视口之外；横向滚动条又在
    ``build_form`` 里关掉了，于是看起来正像「被垂直滚动条盖住」。

    只调 ``container.setMinimumWidth(0)`` **不管用**：Qt 取 ``minimumSize`` 与
    ``minimumSizeHint`` 的**较大值**，后者由 layout 算出，改前者无效。
    所以这里直接收窄 minimumSizeHint —— 只收宽度，高度保持自然（纵向靠滚动）。
    """

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(0, hint.height())


class StagePanel(QWidget):
    """阶段控制面板：标题 + 说明 + 参数表单。子类实现 _build_form/get_args。"""

    stage: str = ""
    title: str = ""
    description: str = ""

    # 用户改动了参数（程序化回填**不算**）→ 宿主据此做「参数暂存」
    param_edited = Signal()

    def __init__(self, parent=None):
        """构建面板骨架：标题 + 说明 + 参数表单容器。

        title/description 来自子类类属性并开启换行，避免窄面板被长说明撑破；
        随后调用 build_form 生成子类表单并占满剩余垂直空间，最后统一把表单
        里输入控件的信号接到 ``param_edited``（供参数暂存）。
        """
        super().__init__(parent)
        # ⚠️ 必须在 build_form 之前置位：子类构造期会调 _apply_args 复位，
        # 那时还没接信号，但保持"回填不算用户改动"的语义始终成立
        self._applying = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_SM)

        self.title_label = QLabel(self.title)
        apply_to(self.title_label, T.SIZE_SUBTITLE, bold=True, color=T.INK)
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.desc_label = QLabel(self.description)
        apply_to(self.desc_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)

        layout.addWidget(self.build_form())
        self._connect_param_edit_signals()
        layout.addStretch()

    # ------------------------------------------------------------------ 参数变动
    def _connect_param_edit_signals(self) -> None:
        """把表单里输入控件的"值变了"信号统一接到 ``param_edited``。

        以前每个面板各自连自己的控件（print 面板那套是给「效果预览刷新」
        用的），宿主想知道"用户改过参数"就得再连一遍、还容易漏掉新控件。
        这里按控件类型连一次即可：qfluent 的 ``ComboBox`` 继承 ``QPushButton``
        、``ComboBox`` 与 ``QComboBox`` 是两回事，必须分开判。
        """
        for widget in self.findChildren(QWidget):
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._on_param_widget_changed)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.valueChanged.connect(self._on_param_widget_changed)
            elif isinstance(widget, (QComboBox, ComboBox)):
                widget.currentIndexChanged.connect(self._on_param_widget_changed)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self._on_param_widget_changed)
        for signal in self._extra_param_signals():
            signal.connect(self._on_param_widget_changed)

    def _extra_param_signals(self) -> list:
        """子类可返回额外要接 ``param_edited`` 的信号（非标准控件的自绘控件）。"""
        return []

    def _on_param_widget_changed(self, *_args) -> None:
        """控件值变了：只有"不是程序化回填"才当作用户改动转发出去。"""
        if self._applying:
            return
        self.param_edited.emit()

    def mark_params_edited(self) -> None:
        """补一次"用户改了参数"通知——给**按钮**这类不经过控件信号的入口用。

        例：「恢复默认」是把默认值 set 回控件（走 ``_apply_args``），信号会被
        ``_applying`` 挡掉，但用户确实改动了参数，得让宿主把新值暂存下来。
        """
        self.param_edited.emit()

    def build_form(self) -> QWidget:
        """参数表单容器：统一装进透明滚动区，窗口过矮时出滚动条而非压扁表单。

        控制卡片把剩余高度分给 QStackedWidget，窗口一矮表单行就被压得错位
        （rembg 的复选框会挤进表单行、说明与行间距被吞掉）。滚动区让表单
        始终保持自然高度，高度不足时纵向滚动。print 面板自带分区滚动区，
        整体覆盖本方法，不受影响。
        """
        # 用可压缩容器：否则表单最小宽度会把容器撑出视口，右侧控件被裁掉
        # （详见 _ShrinkableForm 的说明）
        container = _ShrinkableForm()
        form = QFormLayout(container)
        # 右侧留出垂直滚动条的宽度：qfluentwidgets 的滚动条是**浮在内容上**的，
        # 不留白它就会盖住最右侧控件（offset 滑块右端 + 数字框曾被压掉一截）。
        form.setContentsMargins(0, T.SPACE_XS, T.SCROLLBAR_WIDTH, 0)
        form.setSpacing(T.SPACE_SM)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        self._build_form(form)

        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 去掉滚动区自带的白底与描边：它嵌在参数卡片里，
        # 再画一层边框就成了"卡片套卡片"（同 print 面板的做法）
        scroll.enableTransparentBackground()
        scroll.setWidget(container)
        return scroll

    #: 标签列允许的最大宽度（px，用标签自身字体量出）。
    #:
    #: 为什么需要：QFormLayout 的标签列宽 = **所有行里最宽的那个标签**，所以一条
    #: 长标签会把**整张面板**的输入框一起压扁。实测（1080×720、控制卡片 364px）：
    #: 「印章最小饱和度（sealmin_sat）」一条 240px，把第三步全部字段压到 **112px**
    #: （「边距」的占位文字「留空 或 30 / 20,30 / 20,30,25,35」被截得只剩几个字，
    #: 「阈值偏移」的滑块也短得没法拖）。用户在截图上报的就是这个。
    #:
    #: 两档处理（用户 2026-09-23：「参数 label 太长了，如果太长，英文可以放在下一行，
    #: 保证输入框表单够长」）：
    #:
    #: 1. 整条标签 ≤ 140px → 原样一行；
    #: 2. 整条超了、但**折行后的两段都 ≤ 140px** → 把尾部的「（键名）」挪到第二行，
    #:    标签列于是降到 ≈「中文那行」的宽度；
    #: 3. 连「（键名）」这一行自身都超 140px（`（sealmin_sat）` 就有 156px，而
    #:    括号里的下划线英文**没法再断行**）→ 这一行改成「上标签 / 下控件」，
    #:    输入框直接吃满卡片宽度。
    #:
    #: 第三步实测：字段 112 → **232px**，只有最长的 `sealmin_sat` 那一条换成上下排
    #: （字段 364px）；第一步最长标签 132px，两条规则都不触发，一行都没动。
    LABEL_MAX_WIDTH = 140

    def _add_row(self, form: QFormLayout, label: str, widget) -> None:
        """加一行参数；标签过长时按 :data:`LABEL_MAX_WIDTH` 折行或改排法。

        ⚠️ 判据用**标签自身字体**量出的像素宽，不是字数：中文与英文宽度差一倍，
        按字数判会把「快速模式（quick）」这种其实放得下的标签也改掉。
        """
        text, stacked = self._fit_label(label)
        if stacked:
            # ⚠️ PySide6 的 addRow 没有 `addRow(str)` 这个重载（C++ 有），
            # 必须显式建 QLabel；`addRow(控件)` 会让它跨两列。
            row_label = QLabel(text)
            row_label.setWordWrap(True)
            form.addRow(row_label)  # 标签独占一行（跨两列）
            form.addRow(widget)     # 控件独占一行 → 吃满卡片宽度
            return
        form.addRow(text, widget)

    def _fit_label(self, label: str) -> tuple[str, bool]:
        """把标签调成放得下的形态 → ``(文本, 是否整行上下排)``。

        返回值里的文本可能含 ``\\n``（QLabel 会按换行渲染），标签列宽取两行里更宽
        的那一行；返回 ``(label, False)`` 表示原样即可。
        """
        if not label or "\n" in label:
            return label, False
        metrics = self.fontMetrics()

        def width(text: str) -> int:
            return metrics.horizontalAdvance(text)

        if width(label) <= self.LABEL_MAX_WIDTH:
            return label, False
        # 尾部「（键名）」：只在最末尾找一层，中间带括号的（如「边距(mm)（border）」）
        # 也能正确切出 head="边距(mm)"、key="（border）"
        match = re.search(r"[（(][^（）()]*[）)]$", label)
        if match is not None:
            head = label[: match.start()].rstrip()
            key = match.group(0)
            if head and max(width(head), width(key)) <= self.LABEL_MAX_WIDTH:
                return f"{head}\n{key}", False
        return label, True

    def _build_form(self, form: QFormLayout) -> None:  # pragma: no cover
        raise NotImplementedError

    def get_args(self) -> dict:
        """从表单收集该阶段参数（不含 input/output/clean）。"""
        raise NotImplementedError

    def apply_args(self, parameters: dict) -> None:
        """把一次历史执行/暂存的参数回填到表单（多余键忽略）。"""
        self._apply_args_guarded(parameters)

    def _apply_args_guarded(self, parameters: dict) -> None:
        """程序化回填的**唯一**入口：置 ``_applying`` 再调 ``_apply_args``。

        ⚠️ 面板里全是 setText/setValue/setChecked，与"用户改动"走同一套信号：
        不挡住的话每次回填都会反过来被当成用户改动，把回填值又写进
        「参数暂存」（`PrintPanel.reset_to_default` 曾经直接调 `_apply_args`，
        导致每进一次任务就写一份默认值暂存）。
        子类里凡是要"程序化填表"的地方都必须走这里，不要直调 `_apply_args`。
        """
        self._applying = True
        try:
            self._apply_args(parameters or {})
        finally:
            self._applying = False

    def reset_to_default(self) -> None:
        """恢复控件初始默认值。

        各子类的 ``_apply_args`` 对缺失键都取自身默认值，因此传空字典
        即可复位——用于切换任务时清掉上一个任务残留的手改参数。
        """
        self.apply_args({})

    def _apply_args(self, parameters: dict) -> None:  # pragma: no cover
        raise NotImplementedError
