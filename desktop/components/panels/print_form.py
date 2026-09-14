# -*- coding: utf-8 -*-
"""生成 PDF（print）阶段的表单构建 Mixin：控件创建、标题切换节点表、焦点策略。

参数定义/解析见 print_params.py，面板状态见 print_panel.py。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog, QFormLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    CaptionLabel, CheckBox, LineEdit, PushButton, ScrollArea, SpinBox,
    StrongBodyLabel, ToolButton,
)
from qfluentwidgets import FluentIcon as FIF

from desktop.components.panels.print_nodes import NodeListWidget
from desktop.components.panels.print_params import (
    DIRECTIONS, PAPER_SIZES, POSITIONS, TEXT_ORIENTATIONS,
    parse_color,
)


class PrintFormMixin:
    """print 面板的表单构建（由 PrintPanel 继承）。"""

    # ------------------------------------------------------------------ 构建
    def build_form(self) -> QWidget:
        """构建 print 面板表单：滚动区 + 各分区控件 + 节点表。

        用 ScrollArea 承载全部分区（输出/边距/标题/页码/过滤），顶部放恢复
        默认/重置按钮，构建后连接 pdf_name 与 title 联动信号；焦点策略延后到
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
        init_btn = PushButton(FIF.SYNC, "恢复默认")
        init_btn.setToolTip("所有参数恢复为内置默认值")
        init_btn.clicked.connect(self.reset_to_default)
        reset_btn = PushButton(FIF.CANCEL, "重置")
        reset_btn.setToolTip("撤销修改，恢复到最近一次执行的参数")
        reset_btn.clicked.connect(self.reset_edits)
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
        - SpinBox / ComboBox（含 qfluent 的 ComboBox 子类）→ ClickFocus
        - 其他 → NoFocus
        """
        from PySide6.QtWidgets import QLineEdit, QSpinBox
        from PySide6.QtWidgets import QComboBox as _PyCombo
        try:
            from qfluentwidgets import ComboBox as _QFCombo
        except ImportError:
            _QFCombo = None
        for w in root.findChildren(QWidget):
            if isinstance(w, QLineEdit):
                w.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            elif isinstance(w, QSpinBox):
                w.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            elif isinstance(w, _PyCombo) or (
                _QFCombo is not None and isinstance(w, _QFCombo)
            ):
                # qfluent ComboBox 不是 QComboBox 子类，必须单独检查
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
    def _make_combo(items: list[tuple[str, str]]) -> "object":
        """中文显示、英文值（存于 itemData）的下拉框。"""
        from qfluentwidgets import ComboBox

        combo = ComboBox()
        # qfluent 下拉默认 minimumSizeHint 偏大，会把窄面板撑出横向边界；
        # 主表单中字段列会自动拉伸，表格单元格内则按列宽收纳
        combo.setMinimumWidth(0)
        for label, value in items:
            combo.addItem(label, userData=value)
        return combo

    @staticmethod
    def _set_combo(combo, value, default: str) -> None:
        idx = combo.findData(value)
        if idx < 0:
            idx = combo.findData(default)
        combo.setCurrentIndex(max(idx, 0))

    @staticmethod
    def _line_edit(placeholder: str = "") -> LineEdit:
        """主表单用输入框：给出舒适的最小宽度，同时不超过窄面板边界。"""
        edit = LineEdit()
        if placeholder:
            edit.setPlaceholderText(placeholder)
        edit.setMinimumWidth(120)
        return edit

    @staticmethod
    def _spin_with_unit(maximum: int = 200, unit: str = "pt") -> tuple[QWidget, SpinBox]:
        """数字输入组件 + 后方单位标题，返回 (容器, SpinBox)。"""
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        spin = SpinBox()
        spin.setRange(1, maximum)
        spin.setMinimumWidth(80)
        label = QLabel(unit)
        label.setStyleSheet("color:#6b7280;")
        lay.addWidget(spin)
        lay.addWidget(label)
        lay.addStretch()
        return box, spin

    # ------------------------------------------------------------------ 分区
    def _build_output_section(self, root: QVBoxLayout) -> None:
        form = self._section(root, "输出与纸张")
        # title_text 放 PDF 文件名 上面：两者联动，挨在一起最直观
        self.title_text = self._line_edit("古籍名称（同时作为 PDF 文件名前缀）")
        self.pdf_name = self._line_edit("xxx[重制].pdf")
        from qfluentwidgets import ComboBox

        self.paper_size = ComboBox()
        self.paper_size.setMinimumWidth(0)
        self.paper_size.addItems(PAPER_SIZES)
        self.orientation = self._make_combo(DIRECTIONS)
        self._add_row(form, "古籍名称", self.title_text)
        self._add_row(form, "PDF 文件名", self.pdf_name)
        self._add_row(form, "纸张尺寸", self.paper_size)
        self._add_row(form, "纸张方向", self.orientation)

    def _build_margin_section(self, root: QVBoxLayout) -> None:
        form = self._section(root, "页边距（mm）")
        hint = CaptionLabel("格式：20（四边）/ 20,30（上下,左右）/ 20,30,25,35（上,右,下,左）")
        hint.setWordWrap(True)
        form.addRow(hint)
        self.page_margins = self._line_edit("如 20 或 20,30 或 20,30,25,35")
        self.left_margins = self._line_edit("留空则同通用边距")
        self.right_margins = self._line_edit("留空则同通用边距")
        self._add_row(form, "通用边距", self.page_margins)
        self._add_row(form, "左页边距", self.left_margins)
        self._add_row(form, "右页边距", self.right_margins)

    def _build_title_section(self, root: QVBoxLayout) -> None:
        form = self._section(root, "标题排版")
        self.title_printing = CheckBox("打印标题")
        form.addRow(self.title_printing)
        self.title_printing.toggled.connect(self._sync_enabled)

        title_size_box, self.title_font_size = self._spin_with_unit(200, "pt（磅）")
        self.title_color, title_color_btn = self._color_row()
        self.title_position = self._make_combo(POSITIONS)
        self.title_orientation = self._make_combo(TEXT_ORIENTATIONS)
        self._add_row(form, "字体大小", title_size_box)
        self._add_row(form, "颜色", title_color_btn)
        self._add_row(form, "位置", self.title_position)
        self._add_row(form, "文字方向", self.title_orientation)

        # 标题切换节点表（按页码触发不同标题）——独占整行，避免与标签列争宽度
        nodes_box = QWidget()
        nl = QVBoxLayout(nodes_box)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(4)
        nodes_hint = CaptionLabel("标题切换：页码 ≥ 触发页码 时使用对应标题；侧别默认左页")
        nodes_hint.setWordWrap(True)
        nl.addWidget(nodes_hint)
        # 逐行堆叠的普通控件：高度由行数撑开，无表头、无内部滚动条
        self.nodes_list = NodeListWidget()
        nl.addWidget(self.nodes_list)
        nbtns = QHBoxLayout()
        add_node_btn = PushButton(FIF.ADD, "添加节点")
        add_node_btn.clicked.connect(lambda: self._add_node_row(1, "", "left"))
        clear_node_btn = PushButton(FIF.DELETE, "清空")
        clear_node_btn.setToolTip("移除全部标题切换节点")
        clear_node_btn.clicked.connect(self._clear_node_rows)
        nbtns.addWidget(add_node_btn)
        nbtns.addWidget(clear_node_btn)
        nbtns.addStretch()
        nl.addLayout(nbtns)
        form.addRow(nodes_box)

    def _build_pagenum_section(self, root: QVBoxLayout) -> None:
        form = self._section(root, "页码")
        self.page_number_printing = CheckBox("打印页码")
        form.addRow(self.page_number_printing)
        self.page_number_printing.toggled.connect(self._sync_enabled)

        self.page_number_start = SpinBox()
        self.page_number_start.setRange(1, 100000)
        self.page_number_start.setMinimumWidth(80)
        self.page_number_end_to_last = CheckBox("到最后一页")
        self.page_number_end_to_last.setChecked(True)
        self.page_number_end_to_last.setToolTip("勾选后页码一直打印到最后一页")
        self.page_number_end_to_last.toggled.connect(self._sync_enabled)
        self.page_number_end = SpinBox()
        self.page_number_end.setRange(1, 100000)
        self.page_number_end.setMinimumWidth(80)
        end_row = QWidget()
        el = QHBoxLayout(end_row)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(6)
        el.addWidget(self.page_number_end_to_last)
        el.addWidget(self.page_number_end)
        el.addStretch()
        self.page_number_base = SpinBox()
        self.page_number_base.setRange(-100000, 100000)
        self.page_number_base.setMinimumWidth(80)
        self.page_number_base.setToolTip("用于跨书连续编号：实际页码 = 基数 + 当前页")
        num_size_box, self.page_number_font_size = self._spin_with_unit(200, "pt（磅）")
        self.page_number_color, page_number_color_btn = self._color_row()
        self.page_number_position = self._make_combo(POSITIONS)
        self.page_number_orientation = self._make_combo(TEXT_ORIENTATIONS)
        self._add_row(form, "起始页码", self.page_number_start)
        self._add_row(form, "结束页码", end_row)
        self._add_row(form, "页码基数", self.page_number_base)
        self._add_row(form, "字体大小", num_size_box)
        self._add_row(form, "颜色", page_number_color_btn)
        self._add_row(form, "位置", self.page_number_position)
        self._add_row(form, "文字方向", self.page_number_orientation)

    def _build_filter_section(self, root: QVBoxLayout) -> None:
        form = self._section(root, "过滤")
        self.skip_pages = self._line_edit("逗号分隔的文件名（不含扩展名），如 cover,menu")
        self._add_row(form, "跳过页面", self.skip_pages)

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
        edit.textChanged.connect(
            lambda t, b=btn: self._refresh_color_swatch(b, t)
        )

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
