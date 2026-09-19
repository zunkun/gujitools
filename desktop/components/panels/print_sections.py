# -*- coding: utf-8 -*-
"""print 表单的五个分区（输出与纸张 / 页边距 / 标题 / 页码 / 过滤）。

从 ``print_form.PrintFormMixin`` 拆出。每个 ``_build_xxx_section`` 只负责
"往 root 里加一节的控件并把控件挂到 self 上"，**取值与回填不在这里**
（见 print_panel）。

* 依赖（均来自 ``PrintFormMixin`` / ``PrintPanel``）：
  ``_section`` ``_add_row`` ``_line_edit`` ``_make_combo`` ``_spin_with_unit``
  ``_color_row`` ``_add_node_row`` ``_clear_node_rows`` ``_sync_enabled``
* 被依赖：``PrintFormMixin.build_form`` 依次调用本模块的五个 builder

⚠️ 控件在**本模块**创建、却在 ``PrintPanel`` 里读写（``get_args`` /
``_apply_args`` / ``_connect_preview_signals``）——这条跨模块的隐式契约由
``tests/selftests/print_form_split.py`` 钉住：新增分区必须同时登记它挂到
self 上的控件名，否则漏挂没人会发现。
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, CheckBox, PushButton
from qfluentwidgets import FluentIcon as FIF

from desktop.components.common.safecomment import SafeSpinBox
from desktop.components.panels.print_inset import PrintInsetMixin
from desktop.components.panels.print_nodes import NodeListWidget
from desktop.components.panels.print_params import DIRECTIONS, PAPER_SIZES
from desktop.ui.widgets import combo_box


class PrintSectionsMixin(PrintInsetMixin):
    """print 面板的分区构建（由 PrintFormMixin 继承）。

    继承 ``PrintInsetMixin`` 是因为标题节/页码节都要调 ``_make_inset`` /
    ``_add_inset_rows``；MRO 上它排在 ``PrintFormMixin`` 之后，通用工具
    （``_section`` 等）由最终类 ``PrintPanel`` 的线性化解析到，无需再继承。
    """

    def _build_output_section(self, root: QVBoxLayout) -> None:
        form = self._section(root, "输出与纸张")
        # title_text 放 PDF 文件名 上面：两者联动，挨在一起最直观
        self.title_text = self._line_edit("古籍名称（同时作为 PDF 文件名前缀）")
        self.pdf_name = self._line_edit("xxx[重制].pdf")
        self.paper_size = combo_box(PAPER_SIZES)
        self.orientation = self._make_combo(DIRECTIONS)
        self._add_row(form, "古籍名称", self.title_text)
        self._add_row(form, "PDF 文件名", self.pdf_name)
        self._add_row(form, "纸张尺寸", self.paper_size)
        self._add_row(form, "纸张方向", self.orientation)

    def _build_margin_section(self, root: QVBoxLayout) -> None:
        form = self._section(root, "页边距（mm）")
        hint = CaptionLabel(
            "格式：20（四边）/ 20,30（上下,左右）/ 20,30,25,35（上,右,下,左）"
        )
        hint.setWordWrap(True)
        form.addRow(hint)
        self.page_margins = self._line_edit("如 20 或 20,30 或 20,30,25,35")
        self.left_margins = self._line_edit("留空则同通用边距")
        self.right_margins = self._line_edit("留空则同通用边距")
        self._add_row(form, "通用边距", self.page_margins)
        self._add_row(form, "左页边距", self.left_margins)
        self._add_row(form, "右页边距", self.right_margins)
        # 预览辅助：勾选后在「打印效果」预览里用虚线框出图片位置，并在四边
        # 标注边距（mm）。只画在预览、不进入成品 PDF（交付书保持干净）。
        self.annotate_margins = CheckBox("预览标注图框与边距")
        self.annotate_margins.setToolTip(
            "仅在第四步效果预览里用虚线标出图片边框、并在四边标注边距毫米数；"
            "不影响生成的 PDF"
        )
        form.addRow(self.annotate_margins)

    def _build_title_section(self, root: QVBoxLayout) -> None:
        form = self._section(root, "标题排版")
        self.title_printing = CheckBox("打印标题")
        form.addRow(self.title_printing)
        self.title_printing.toggled.connect(self._sync_enabled)

        title_size_box, self.title_font_size = self._spin_with_unit(200, "pt（磅）")
        self.title_color, title_color_btn = self._color_row()
        self._title_inset = self._make_inset("标题")
        # ⚠️ 「位置」「文字方向」两个下拉**已从桌面端删除**（用户要求）：
        # 标题恒在纸张**上边**、恒**竖排**。取值由 `FIXED_TEXT_LAYOUT` 兜底，
        # 界面不摆控件也就没有"两个下拉互相矛盾"的余地（用户原话：
        # 「有位置：上面/下面，如果是上面，只能有上面距离」——与其做动态
        # 联动，不如直接不给选：古籍书名在版框之上、竖排，本就是定式）。
        # 命令行/YAML 仍可用这两个键（默认值不变，见 core.command_spec）。
        self._add_row(form, "字体大小", title_size_box)
        self._add_row(form, "颜色", title_color_btn)
        self._add_inset_rows(form, self._title_inset)

        # 标题切换节点表（按页码触发不同标题）——独占整行，避免与标签列争宽度
        nodes_box = QWidget()
        nl = QVBoxLayout(nodes_box)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(4)
        nodes_hint = CaptionLabel(
            "标题切换：页码 ≥ 触发页码 时使用对应标题；侧别默认左页"
        )
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

        self.page_number_start = SafeSpinBox()
        self.page_number_start.setRange(1, 100000)
        self.page_number_start.setMinimumWidth(80)
        self.page_number_end_to_last = CheckBox("到最后一页")
        self.page_number_end_to_last.setChecked(True)
        self.page_number_end_to_last.setToolTip("勾选后页码一直打印到最后一页")
        self.page_number_end_to_last.toggled.connect(self._sync_enabled)
        self.page_number_end = SafeSpinBox()
        self.page_number_end.setRange(1, 100000)
        self.page_number_end.setMinimumWidth(80)
        end_row = QWidget()
        el = QHBoxLayout(end_row)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(6)
        el.addWidget(self.page_number_end_to_last)
        el.addWidget(self.page_number_end)
        el.addStretch()
        self.page_number_base = SafeSpinBox()
        self.page_number_base.setRange(-100000, 100000)
        self.page_number_base.setMinimumWidth(80)
        self.page_number_base.setToolTip("用于跨书连续编号：实际页码 = 基数 + 当前页")
        num_size_box, self.page_number_font_size = self._spin_with_unit(200, "pt（磅）")
        self.page_number_color, page_number_color_btn = self._color_row()
        self._page_number_inset = self._make_inset("页码")
        self._add_row(form, "起始页码", self.page_number_start)
        self._add_row(form, "结束页码", end_row)
        self._add_row(form, "页码基数", self.page_number_base)
        self._add_row(form, "字体大小", num_size_box)
        self._add_row(form, "颜色", page_number_color_btn)
        # 「位置」「文字方向」同标题：已在桌面端删除，页码恒在纸张**下边**、
        # 恒**竖排**（见 `FIXED_TEXT_LAYOUT`）。命令行/YAML 仍可用这两个键。
        self._add_inset_rows(form, self._page_number_inset)

    def _build_filter_section(self, root: QVBoxLayout) -> None:
        form = self._section(root, "过滤")
        self.skip_pages = self._line_edit(
            "逗号分隔的文件名（不含扩展名），如 cover,menu"
        )
        self._add_row(form, "跳过页面", self.skip_pages)
