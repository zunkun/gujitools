# -*- coding: utf-8 -*-
"""生成 PDF（print）阶段面板：UI 表单参数（不直接编辑 YAML）。

input/output/workers/clean 由系统管理，不出现在表单中。
配置可恢复默认、可重置（恢复到最近一次执行的参数）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractScrollArea, QColorDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    CaptionLabel, CheckBox, ComboBox, LineEdit, PushButton,
    ScrollArea, SpinBox, StrongBodyLabel, TableWidget, ToolButton,
)
from qfluentwidgets import FluentIcon as FIF

from .base import StagePanel

# 不允许在表单中配置的键（系统管理）
_EXCLUDED_KEYS = ("input", "output", "workers", "clean", "_outpath")

# 默认参数（pdf_name 与 store.print_output_pdf 对齐）
DEFAULT_PARAMS: dict = {
    "title_text": "古籍名称",
    "pdf_name": "print.pdf",
    "paper_size": "A4",
    "orientation": "landscape",
    "page_margins": [20, 20, 20, 20],
    "left_page_margins": None,
    "right_page_margins": None,
    "title_printing": True,
    "title_font_size": 18,
    "title_color": "0,0,0",
    "title_position": "top",
    "title_orientation": "vertical",
    "title_switch_nodes": [],
    "page_number_printing": True,
    "page_number_start_page": 1,
    "page_number_end_page": None,
    "page_number_base": 0,
    "page_number_font_size": 18,
    "page_number_color": "0,0,0",
    "page_number_position": "bottom",
    "page_number_orientation": "vertical",
    "skip_pages": [],
}

_PAPER_SIZES = ["A3", "A4", "A5", "B5"]
# 下拉项：(中文显示, 实际参数值)
_DIRECTIONS = [("横版", "landscape"), ("竖版", "portrait")]
_POSITIONS = [("上边", "top"), ("下边", "bottom")]
_TEXT_ORIENTATIONS = [("竖排", "vertical"), ("横排", "horizontal")]
_SIDES = [("双面", "both"), ("左页", "left"), ("右页", "right")]


def _parse_color(text: str) -> QColor:
    """解析 'r,g,b'（0~255）颜色字符串，非法时抛出 ValueError。"""
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) != 3:
        raise ValueError(f"颜色格式应为 r,g,b（0~255），当前：{text!r}")
    try:
        r, g, b = (int(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"颜色必须为数字：{text!r}") from exc
    if not all(0 <= v <= 255 for v in (r, g, b)):
        raise ValueError(f"颜色取值范围 0~255：{text!r}")
    return QColor(r, g, b)


def _parse_margin4(text: str):
    """解析边距简写：1 值→四边；2 值→上下/左右；4 值→上右下左；空→None。"""
    text = str(text or "").strip()
    if not text:
        return None
    parts = [p.strip() for p in text.replace("，", ",").split(",") if p.strip()]
    try:
        vals = [float(p) for p in parts]
    except ValueError as exc:
        raise ValueError(f"边距必须为数字（mm）：{text!r}") from exc
    if any(v < 0 for v in vals):
        raise ValueError(f"边距不能为负数：{text!r}")
    if len(vals) == 1:
        vals = vals * 4
    elif len(vals) == 2:
        vals = [vals[0], vals[1], vals[0], vals[1]]
    elif len(vals) != 4:
        raise ValueError("边距需为 1 / 2 / 4 个值，如 20 或 20,30 或 20,30,25,35")
    return vals


class PrintPanel(StagePanel):
    stage = "print"
    title = "生成 PDF (print)"
    description = (
        "设置 PDF 纸张、边距、标题、页码等参数。"
        "左侧列表决定参与生成的图片与顺序。"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        # 表单内容较高，让滚动区占满标题以下的全部空间
        self.layout().setStretch(2, 1)
        # 基类的标题与说明文字默认不换行，长说明会把窄面板撑出横向边界
        title_label = self.layout().itemAt(0).widget()
        desc_label = self.layout().itemAt(1).widget()
        title_label.setWordWrap(True)
        desc_label.setWordWrap(True)
        self._last_applied: dict | None = None
        # 当前任务源 PDF 的文件名（无扩展名）：用于派生默认 PDF 名与古籍名
        self._source_stem = ""
        # title_text 与 pdf_name 联动标志：True 表示 pdf_name = f"{title_text}[重制].pdf"
        # 用户直接修改 pdf_name 后自动置 False，联动解除；set_source_defaults / reset_to_default 时恢复
        self._pdf_name_auto = True
        self.reset_to_default()
        # 焦点策略：必须在基类 __init__ 之后调（ScrollArea 已 addWidget 到 layout），
        # 且必须用 self 而非 container——因为只有此时 self.findChildren(QWidget)
        # 才能遍历到完整的子树；build_form 内部调的话，qfluent 控件的父级 attach
        # 会覆盖 setFocusPolicy
        self._apply_focus_policy(self)

    def set_source_defaults(self, source_stem: str) -> None:
        """切换任务时调用：以源 PDF 名派生默认值并重置表单。

        - PDF 文件名：xxx.pdf → xxx[重制].pdf
        - 古籍名称（标题文本）：xxx
        有历史执行记录时，进入第四步仍会回填最近一次配置，覆盖此默认值。
        """
        self._source_stem = str(source_stem or "").strip()
        self.reset_to_default()

    def _default_params(self) -> dict:
        params = dict(DEFAULT_PARAMS)
        if self._source_stem:
            params["pdf_name"] = f"{self._source_stem}[重制].pdf"
            params["title_text"] = self._source_stem
        return params

    # ---------- title_text ↔ pdf_name 联动 ----------
    # 用 textEdited（仅用户键盘输入触发，程序 setText 不触发）避免在
    # set_source_defaults / reset_to_default / 历史回填 这种程序赋值路径
    # 上意外断开联动或产生 setText 循环
    def _connect_title_pdf_link(self) -> None:
        self.title_text.textEdited.connect(self._on_title_text_edited)
        self.pdf_name.textEdited.connect(self._on_pdf_name_edited)

    def _on_title_text_edited(self, _text: str) -> None:
        if not self._pdf_name_auto:
            return
        self.pdf_name.setText(self._title_to_pdf_name())

    def _on_pdf_name_edited(self, _text: str) -> None:
        self._pdf_name_auto = False

    def _title_to_pdf_name(self) -> str:
        stem = self.title_text.text().strip()
        if not stem:
            return f"{self._source_stem or 'print'}[重制].pdf"
        return f"{stem}[重制].pdf"

    def _refresh_pdf_name_auto(self) -> None:
        """程序 setText 后重算联动标志：pdf_name 等于 title_text 派生值时视为自动态。"""
        self._pdf_name_auto = (self.pdf_name.text() == self._title_to_pdf_name())

    # ------------------------------------------------------------------ 构建
    def build_form(self) -> QWidget:
        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

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
    def _make_combo(items: list[tuple[str, str]]) -> ComboBox:
        """中文显示、英文值（存于 itemData）的下拉框。"""
        combo = ComboBox()
        # qfluent 下拉默认 minimumSizeHint 偏大，会把窄面板撑出横向边界；
        # 主表单中字段列会自动拉伸，表格单元格内则按列宽收纳
        combo.setMinimumWidth(0)
        for label, value in items:
            combo.addItem(label, userData=value)
        return combo

    @staticmethod
    def _set_combo(combo: ComboBox, value, default: str) -> None:
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

    def _build_output_section(self, root: QVBoxLayout) -> None:
        form = self._section(root, "输出与纸张")
        # title_text 放 PDF 文件名 上面：两者联动，挨在一起最直观
        self.title_text = self._line_edit("古籍名称（同时作为 PDF 文件名前缀）")
        self.pdf_name = self._line_edit("xxx[重制].pdf")
        self.paper_size = ComboBox()
        self.paper_size.setMinimumWidth(0)
        self.paper_size.addItems(_PAPER_SIZES)
        self.orientation = self._make_combo(_DIRECTIONS)
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
        self.title_position = self._make_combo(_POSITIONS)
        self.title_orientation = self._make_combo(_TEXT_ORIENTATIONS)
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
        self.nodes_table = TableWidget()
        self.nodes_table.setColumnCount(3)
        self.nodes_table.setHorizontalHeaderLabels(["触发页码", "标题", "侧别"])
        self.nodes_table.verticalHeader().setVisible(False)
        # 不设固定/最小高度：行数少时紧凑，行数多时自动撑高到上限，超出则滚动
        self.nodes_table.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
        )
        header = self.nodes_table.horizontalHeader()
        self.nodes_table.setColumnWidth(0, 120)
        self.nodes_table.setColumnWidth(2, 76)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        # 先给一个空表高度占位，后续 _update_nodes_table_height 会按行数算
        self.nodes_table.setFixedHeight(40)
        nl.addWidget(self.nodes_table)
        nbtns = QHBoxLayout()
        add_node_btn = PushButton(FIF.ADD, "添加节点")
        add_node_btn.clicked.connect(lambda: self._add_node_row(1, "", "left"))
        del_node_btn = PushButton(FIF.DELETE, "删除选中")
        del_node_btn.clicked.connect(self._remove_node_rows)
        nbtns.addWidget(add_node_btn)
        nbtns.addWidget(del_node_btn)
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
        self.page_number_position = self._make_combo(_POSITIONS)
        self.page_number_orientation = self._make_combo(_TEXT_ORIENTATIONS)
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
            color = _parse_color(edit.text()) if edit.text().strip() else QColor(0, 0, 0)
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
            color = _parse_color(text)
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

    # ------------------------------------------------------------------ 节点表
    def _add_node_row(self, page: int = 1, title: str = "", side: str = "left") -> None:
        row = self.nodes_table.rowCount()
        self.nodes_table.insertRow(row)
        page_spin = SpinBox()
        page_spin.setRange(1, 100000)
        page_spin.setValue(int(page))
        # 单元格内允许压缩到列宽，避免 qfluent 控件的最小尺寸把列撑宽
        page_spin.setMinimumWidth(0)
        title_edit = LineEdit()
        title_edit.setText(str(title))
        title_edit.setMinimumWidth(0)
        side_combo = self._make_combo(_SIDES)
        side_combo.setMinimumWidth(0)
        self._set_combo(side_combo, side, "left")
        # _apply_focus_policy 在 build_form 末尾调，此时表格还是空的；
        # 动态创建的 cellWidget 必须在这里单独设焦点策略
        page_spin.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        side_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        title_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.nodes_table.setCellWidget(row, 0, page_spin)
        self.nodes_table.setCellWidget(row, 1, title_edit)
        self.nodes_table.setCellWidget(row, 2, side_combo)
        self._update_nodes_table_height()

    def _remove_node_rows(self) -> None:
        rows = sorted(
            {i.row() for i in self.nodes_table.selectedIndexes()}, reverse=True
        )
        for row in rows:
            self.nodes_table.removeRow(row)
        self._update_nodes_table_height()

    # 节点表高度：按行数动态撑开，超出上限出现滚动条
    _NODE_ROW_H = 30   # 单行高度（含单元格 widget）
    _NODE_HEADER_H = 28  # 表头高度
    _NODE_MAX_ROWS = 4   # 最多可视行数（含表头 ≈ 148px），超出滚动

    def _update_nodes_table_height(self) -> None:
        rows = max(self.nodes_table.rowCount(), 1)
        visible = min(rows, self._NODE_MAX_ROWS)
        h = self._NODE_HEADER_H + visible * self._NODE_ROW_H
        self.nodes_table.setFixedHeight(h)

    def _collect_nodes(self) -> list:
        nodes = []
        for row in range(self.nodes_table.rowCount()):
            title_edit = self.nodes_table.cellWidget(row, 1)
            title = title_edit.text().strip() if title_edit else ""
            if not title:
                continue
            page_spin = self.nodes_table.cellWidget(row, 0)
            side_combo = self.nodes_table.cellWidget(row, 2)
            node = [page_spin.value(), title]
            side = side_combo.currentData() if side_combo else "left"
            # 双面（both）为缺省值，省略第三项；左页/右页显式携带
            if side and side != "both":
                node.append(side)
            nodes.append(node)
        return nodes

    # ------------------------------------------------------------------ 状态
    def _sync_enabled(self) -> None:
        title_on = self.title_printing.isChecked()
        # title_text（古籍名称）不跟着打印标题开关禁用——它挪到了输出与纸张
        # 组，还作为 pdf_name 联动的派生源，任何时候都应该可编辑
        for w in (
            self.title_font_size, self.title_color,
            self.title_position, self.title_orientation, self.nodes_table,
        ):
            w.setEnabled(title_on)
        num_on = self.page_number_printing.isChecked()
        for w in (
            self.page_number_start, self.page_number_end,
            self.page_number_end_to_last, self.page_number_base,
            self.page_number_font_size, self.page_number_color,
            self.page_number_position, self.page_number_orientation,
        ):
            w.setEnabled(num_on)
        if num_on:
            self.page_number_end.setEnabled(
                not self.page_number_end_to_last.isChecked()
            )

    def reset_to_default(self) -> None:
        self._apply_args(self._default_params())

    def reset_edits(self) -> None:
        if self._last_applied is not None:
            self._apply_args(self._last_applied)
        else:
            self.reset_to_default()

    def mark_applied(self, parameters: dict) -> None:
        """记录最近一次执行使用的参数（供「重置」恢复）。"""
        clean = {
            k: v for k, v in (parameters or {}).items() if k not in _EXCLUDED_KEYS
        }
        self._last_applied = clean

    # ------------------------------------------------------------------ 取值
    def get_args(self) -> dict:
        # 颜色先校验，非法直接报错阻止执行
        _parse_color(self.title_color.text())
        _parse_color(self.page_number_color.text())
        # 边距先校验（非法直接报错）；通用边距缺省回落到内置默认
        page_margins = _parse_margin4(self.page_margins.text())
        if page_margins is None:
            page_margins = list(DEFAULT_PARAMS["page_margins"])
        args: dict = {
            "pdf_name": self.pdf_name.text().strip() or "print.pdf",
            "paper_size": self.paper_size.currentText(),
            "orientation": self.orientation.currentData(),
            "page_margins": page_margins,
            "title_printing": self.title_printing.isChecked(),
            "title_text": self.title_text.text().strip(),
            "title_font_size": self.title_font_size.value(),
            "title_color": self.title_color.text().strip(),
            "title_position": self.title_position.currentData(),
            "title_orientation": self.title_orientation.currentData(),
            "title_switch_nodes": self._collect_nodes(),
            "page_number_printing": self.page_number_printing.isChecked(),
            "page_number_start_page": self.page_number_start.value(),
            "page_number_base": self.page_number_base.value(),
            "page_number_font_size": self.page_number_font_size.value(),
            "page_number_color": self.page_number_color.text().strip(),
            "page_number_position": self.page_number_position.currentData(),
            "page_number_orientation": self.page_number_orientation.currentData(),
            "skip_pages": [
                p.strip()
                for p in self.skip_pages.text().replace("，", ",").split(",")
                if p.strip()
            ],
        }
        if not self.page_number_end_to_last.isChecked():
            args["page_number_end_page"] = self.page_number_end.value()
        left = _parse_margin4(self.left_margins.text())
        if left is not None:
            args["left_page_margins"] = left
        right = _parse_margin4(self.right_margins.text())
        if right is not None:
            args["right_page_margins"] = right
        return args

    def _apply_args(self, parameters: dict) -> None:
        p = parameters or {}
        # pdf_name / title_text 可能在 set_source_defaults 里刚派生好，
        # 这里再用 blockSignals 保护 setText，避免触发 textEdited 让联动标志错乱
        self.pdf_name.blockSignals(True)
        self.title_text.blockSignals(True)
        self.pdf_name.setText(str(p.get("pdf_name") or self._default_params()["pdf_name"]))
        self.title_text.setText(str(p.get("title_text", "") or ""))
        self.pdf_name.blockSignals(False)
        self.title_text.blockSignals(False)
        # 程序赋值结束后：若 pdf_name 恰好等于 title_text 派生值，视为自动态；
        # 否则（例如历史里存的是 print.pdf / printpdf.pdf 这种自定义值），
        # 联动暂时解除，用户后续改 title_text 不会覆盖 pdf_name
        self._refresh_pdf_name_auto()
        paper = str(p.get("paper_size", "A4")).upper()
        self.paper_size.setCurrentText(
            paper if paper in _PAPER_SIZES else "A4"
        )
        self._set_combo(self.orientation, p.get("orientation"), "landscape")

        self.page_margins.setText(self._margin_to_text(p.get("page_margins")))
        self.left_margins.setText(self._margin_to_text(p.get("left_page_margins")))
        self.right_margins.setText(self._margin_to_text(p.get("right_page_margins")))

        self.title_printing.setChecked(bool(p.get("title_printing", True)))
        self.title_font_size.setValue(int(p.get("title_font_size", 18)))
        self.title_color.setText(str(p.get("title_color", "0,0,0")))
        self._set_combo(self.title_position, p.get("title_position"), "top")
        self._set_combo(self.title_orientation,
                        p.get("title_orientation"), "vertical")
        # 重建节点表
        while self.nodes_table.rowCount():
            self.nodes_table.removeRow(0)
        for node in (p.get("title_switch_nodes") or []):
            if not isinstance(node, (list, tuple)) or len(node) < 2:
                continue
            side = node[2] if len(node) >= 3 else "left"
            self._add_node_row(int(node[0]), str(node[1]), str(side))
        # 空表或非空表的最终高度归一（_add_node_row 内部已调，这里兜底空表）
        self._update_nodes_table_height()

        self.page_number_printing.setChecked(
            bool(p.get("page_number_printing", True))
        )
        self.page_number_start.setValue(int(p.get("page_number_start_page", 1)))
        end_page = p.get("page_number_end_page")
        if end_page is None:
            self.page_number_end_to_last.setChecked(True)
            self.page_number_end.setValue(1)
        else:
            self.page_number_end_to_last.setChecked(False)
            self.page_number_end.setValue(int(end_page))
        self.page_number_base.setValue(int(p.get("page_number_base", 0)))
        self.page_number_font_size.setValue(
            int(p.get("page_number_font_size", 12))
        )
        self.page_number_color.setText(str(p.get("page_number_color", "0,0,0")))
        self._set_combo(self.page_number_position,
                        p.get("page_number_position"), "bottom")
        self._set_combo(self.page_number_orientation,
                        p.get("page_number_orientation"), "vertical")

        skip = p.get("skip_pages")
        if isinstance(skip, (list, tuple)):
            self.skip_pages.setText(",".join(str(s) for s in skip))
        else:
            self.skip_pages.setText(str(skip or ""))

        self._sync_enabled()

    @staticmethod
    def _margin_to_text(value) -> str:
        """边距列表转简写文本：四边相等→单值；上下/左右相等→两值；否则四值。"""
        if not value:
            return ""
        if not isinstance(value, (list, tuple)):
            return str(value)
        vals = [int(float(v)) for v in value]
        if len(vals) == 4:
            if vals[0] == vals[1] == vals[2] == vals[3]:
                return str(vals[0])
            if vals[0] == vals[2] and vals[1] == vals[3]:
                return f"{vals[0]},{vals[1]}"
        return ",".join(str(v) for v in vals)
