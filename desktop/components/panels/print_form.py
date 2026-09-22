# -*- coding: utf-8 -*-
"""生成 PDF（print）阶段的表单构建 Mixin：编排、通用控件工厂、节点表、焦点策略。

本类是**编排层**，按依赖从少到多继承三个专职 Mixin：

* :mod:`desktop.components.panels.print_text_layout` —— 「位置/文字方向」固定取值
* :mod:`desktop.components.panels.print_inset` —— 「距页边」控件组
* :mod:`desktop.components.panels.print_sections` —— 五个分区的控件

参数定义/解析见 print_params.py，面板状态见 print_panel.py。

⚠️ 拆分只改**代码落在哪个文件**，不改任何行为：四个类的成员名对外一律从
``PrintFormMixin`` 可见（``PrintPanel`` 只继承它一个），
``tests/selftests/print_form_split.py`` 钉住这条不变量。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    ComboBox,
    LineEdit,
    PushButton,
    ScrollArea,
    StrongBodyLabel,
    ToolButton,
)
from qfluentwidgets import FluentIcon as FIF

from desktop.components.common.safecomment import SafeSpinBox
from desktop.components.panels.print_params import parse_color
from desktop.components.panels.print_sections import PrintSectionsMixin
from desktop.components.panels.print_text_layout import PrintTextLayoutMixin
from desktop.ui.widgets import combo_box


class PrintFormMixin(PrintSectionsMixin, PrintTextLayoutMixin):
    """print 面板的表单构建（由 PrintPanel 继承）。

    MRO：``PrintFormMixin → PrintSectionsMixin → PrintInsetMixin →
    PrintTextLayoutMixin``。前三者都只依赖 ``self`` 上的成员，最终由
    ``PrintPanel(PrintFormMixin, StagePanel)`` 线性化到 ``StagePanel``
    提供的 ``_add_row`` 等基础能力。
    """

    # ------------------------------------------------------------------ 构建
    def build_form(self) -> QWidget:
        """构建 print 面板表单：滚动区 + 各分区控件 + 节点表。

        用 ScrollArea 承载全部分区（输出/边距/标题/页码/过滤），顶部放恢复
        默认配置/放弃修改按钮，构建后连接 pdf_name 与 title 联动信号；焦点策略延后到
        面板 __init__ 末尾统一设置。
        """
        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 去掉滚动区自带的白底与描边：它现在嵌在参数卡片里，
        # 再画一层边框就成了"卡片套卡片"
        scroll.enableTransparentBackground()

        container = QWidget()
        # 关键：允许内部内容收缩到比 sizeHint 更窄，防止横向超出/被裁剪
        container.setMinimumWidth(0)
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 8, 0)
        root.setSpacing(10)

        # 顶部操作按钮
        btns = QHBoxLayout()
        init_btn = PushButton(FIF.SYNC, "恢复默认配置")
        init_btn.setToolTip("所有参数恢复为内置默认值")
        init_btn.clicked.connect(self._reset_default_clicked)
        reset_btn = PushButton(FIF.CANCEL, "放弃本次修改")
        reset_btn.setToolTip("撤销本次修改，回到最近一次执行时的参数")
        reset_btn.clicked.connect(self._reset_edits_clicked)
        btns.addWidget(init_btn)
        btns.addWidget(reset_btn)
        btns.addStretch()
        root.addLayout(btns)

        self._build_output_section(root)
        self._build_margin_section(root)
        self._build_title_section(root)
        self._build_pagenum_section(root)
        self._build_filter_section(root)
        root.addStretch()

        scroll.setWidget(container)
        self._scroll = scroll
        # pdf_name 和 title_text 均已创建完，连接联动信号
        self._connect_title_pdf_link()
        # 焦点策略延后到 __init__ 末尾再设——build_form 返回后基类
        # StagePanel.__init__ 才把 scroll addWidget 到 layout，期间
        # qfluent 控件的父级 attach 可能会覆盖 setFocusPolicy
        return scroll

    def _apply_focus_policy(self, root: QWidget) -> None:
        """遍历 root 下所有控件，按类型设焦点策略。

        - LineEdit → StrongFocus：点击可聚焦，也支持 Tab 键切换
        - SafeSpinBox / ComboBox → ClickFocus
        - 其他 → NoFocus
        """

        from PySide6.QtWidgets import QComboBox, QLineEdit

        # 注意 qfluent 的 ComboBox 继承 QPushButton（不是 QComboBox），
        # 必须单独判定，否则会落到 else 分支被设成 NoFocus。
        for w in root.findChildren(QWidget):
            if isinstance(w, QLineEdit):
                w.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            elif isinstance(w, (SafeSpinBox, QComboBox, ComboBox)):
                w.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            else:
                w.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _section(self, root: QVBoxLayout, text: str) -> QFormLayout:
        root.addWidget(StrongBodyLabel(text))
        form = QFormLayout()
        form.setSpacing(6)
        # 标签列不强制占宽，字段列吃掉剩余空间
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignLeft)
        root.addLayout(form)
        return form

    @staticmethod
    def _make_combo(items: list[tuple[str, str]]) -> "ComboBox":
        """中文显示、英文值（存于 itemData）的下拉框。"""
        return combo_box(items)

    @staticmethod
    def _set_combo(combo, value, default: str) -> None:
        idx = combo.findData(value)
        if idx < 0:
            idx = combo.findData(default)
        combo.setCurrentIndex(max(idx, 0))

    def _set_font_combo(self, combo, value) -> None:
        """回填字体下拉；列表里没有这个字体时**临时加一项**保住选择。

        列表未含该项有两种可能：后台扫描还没跑完，或者这份配置来自另一台
        机器（那台有这个字体）。两种都不该把用户的设置悄悄改回"自动"——
        字体选择是显式配置，静默回落属于最难查的那类漂移。
        """
        from desktop.services.font_catalog import AUTO_VALUE

        text = str(value or "").strip()
        if not text:
            self._set_combo(combo, AUTO_VALUE, AUTO_VALUE)
            return
        if combo.findData(text) < 0:
            combo.addItem(text, userData=text)
        self._set_combo(combo, text, AUTO_VALUE)

    def _reset_default_clicked(self) -> None:
        """「恢复默认配置」按钮：复位后补一次用户改动通知（参数要暂存新值）。"""
        self.reset_to_default()
        self.mark_params_edited()

    def _reset_edits_clicked(self) -> None:
        """「放弃本次修改」按钮：回到最近一次执行的参数，同样要暂存这次改动。"""
        self.reset_edits()
        self.mark_params_edited()

    # ------------------------------------------------------------ 通用控件工厂
    @staticmethod
    def _line_edit(placeholder: str = "") -> LineEdit:
        """主表单用输入框：给出舒适的最小宽度，同时不超过窄面板边界。"""
        edit = LineEdit()
        if placeholder:
            edit.setPlaceholderText(placeholder)
        edit.setMinimumWidth(120)
        return edit

    @staticmethod
    def _spin_with_unit(
        maximum: int = 200, unit: str = "pt"
    ) -> tuple[QWidget, SafeSpinBox]:
        """数字输入组件 + 后方单位标题，返回 (容器, SafeSpinBox)。"""

        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        spin = SafeSpinBox()
        spin.setRange(1, maximum)
        spin.setMinimumWidth(80)
        label = QLabel(unit)
        label.setStyleSheet("color:#6b7280;")
        lay.addWidget(spin)
        lay.addWidget(label)
        lay.addStretch()
        return box, spin

    def _color_row(self):
        """颜色输入框 + 取色按钮；返回 (LineEdit, 容器widget)。"""
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        edit = self._line_edit("r,g,b（0~255）")
        btn = ToolButton()
        btn.setText("取色")
        btn.setFixedWidth(64)
        edit.textChanged.connect(lambda t, b=btn: self._refresh_color_swatch(b, t))

        def choose():
            color = parse_color(edit.text()) if edit.text().strip() else QColor(0, 0, 0)
            chosen = QColorDialog.getColor(color, self, "选择颜色")
            if chosen.isValid():
                edit.setText(f"{chosen.red()},{chosen.green()},{chosen.blue()}")

        btn.clicked.connect(choose)
        self._refresh_color_swatch(btn, edit.text())
        lay.addWidget(edit, 1)
        lay.addWidget(btn)
        return edit, box

    @staticmethod
    def _refresh_color_swatch(btn: ToolButton, text: str) -> None:
        try:
            color = parse_color(text)
            rgb = f"rgb({color.red()},{color.green()},{color.blue()})"
        except ValueError:
            rgb = "#f3f3f3"
        # 不加 ToolButton 选择器——qfluent 的 ToolButton 自定义控件样式表解析器
        # 不识别类选择器形式，会输出 "Could not parse stylesheet" 警告；
        # 直接设属性让它继承 QToolButton 的通用样式即可。
        btn.setStyleSheet(
            f"background-color:{rgb}; border:1px solid #d0d0d0; "
            "border-radius:4px; padding:2px;"
        )

    # ------------------------------------------------------------------ 节点行
    # 节点行是普通控件（见 print_nodes.NodeListWidget）：高度由行数自然撑开，
    # 不需要任何高度计算，也不会出现内部滚动条
    def _add_node_row(self, page: int = 1, title: str = "", side: str = "left") -> None:
        self.nodes_list.add_row(page, title, side)

    def _clear_node_rows(self) -> None:
        self.nodes_list.clear()

    def _collect_nodes(self) -> list:
        return self.nodes_list.collect()
