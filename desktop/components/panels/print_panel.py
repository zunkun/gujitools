# -*- coding: utf-8 -*-
"""生成 PDF（print）阶段面板：表单状态（取值/回填/重置）。

表单控件构建见 print_form.py，参数定义/解析见 print_params.py。
input/output/workers/clean 由系统管理，不出现在表单中。
"""

from __future__ import annotations

from desktop.components.panels.base import StagePanel
from desktop.components.panels.print_form import PrintFormMixin
from desktop.components.panels.print_params import (
    DEFAULT_PARAMS, EXCLUDED_KEYS, PAPER_SIZES,
    margin_to_text, parse_color, parse_margin4,
    skip_pages_to_text, text_to_skip_pages,
)


class PrintPanel(PrintFormMixin, StagePanel):
    """生成 PDF 阶段面板：纸张/边距/标题/页码等参数与状态。

    input/output/workers/clean 由系统管理；表单构建见 print_form，取值/
    回填/重置等状态见本类（含标题切换节点与 pdf_name/title 联动）。
    """

    stage = "print"
    title = "生成 PDF (print)"
    description = (
        "设置 PDF 纸张、边距、标题、页码等参数。"
        "左侧列表决定参与生成的图片与顺序。"
    )

    def __init__(self, parent=None):
        """构建 print 面板：设滚动拉伸、联动标志并复位到默认。

        基类 __init__ 构建滚动表单后，这里开启标题/说明换行、初始化
        pdf_name 联动标志、记录最近应用参数占位，并调 reset_to_default 复位。
        """
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

    # ------------------------------------------------------------------ 状态
    def _sync_enabled(self) -> None:
        title_on = self.title_printing.isChecked()
        # title_text（古籍名称）不跟着打印标题开关禁用——它挪到了输出与纸张
        # 组，还作为 pdf_name 联动的派生源，任何时候都应该可编辑
        for w in (
            self.title_font_size, self.title_color,
            self.title_position, self.title_orientation, self.nodes_list,
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
        """恢复为该面板的内置默认参数（不依赖任何历史执行）。"""
        self._apply_args(self._default_params())

    def reset_edits(self) -> None:
        """撤销本次修改：恢复到最近一次执行的参数。

        与 reset_to_default（恢复内置默认）不同，本方法回到 mark_applied
        记录的上一轮执行参数；若从未执行过则退化为恢复默认。
        """
        if self._last_applied is not None:
            self._apply_args(self._last_applied)
        else:
            self.reset_to_default()

    def mark_applied(self, parameters: dict) -> None:
        """记录最近一次执行使用的参数（供「重置」恢复）。"""
        clean = {
            k: v for k, v in (parameters or {}).items() if k not in EXCLUDED_KEYS
        }
        self._last_applied = clean

    # ------------------------------------------------------------------ 取值
    def get_args(self) -> dict:
        """收集 PDF 生成参数（校验颜色/边距，缺省回落内置默认）。

        input/output/workers/clean 不在此列；颜色或边距非法会抛 ValueError
        阻止执行；title_switch_nodes 取节点行、skip_pages 解析为文件名列表。
        """
        # 颜色先校验，非法直接报错阻止执行
        parse_color(self.title_color.text())
        parse_color(self.page_number_color.text())
        # 边距先校验（非法直接报错）；通用边距缺省回落到内置默认
        page_margins = parse_margin4(self.page_margins.text())
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
            "skip_pages": text_to_skip_pages(self.skip_pages.text()),
        }
        if not self.page_number_end_to_last.isChecked():
            args["page_number_end_page"] = self.page_number_end.value()
        left = parse_margin4(self.left_margins.text())
        if left is not None:
            args["left_page_margins"] = left
        right = parse_margin4(self.right_margins.text())
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
            paper if paper in PAPER_SIZES else "A4"
        )
        self._set_combo(self.orientation, p.get("orientation"), "landscape")

        self.page_margins.setText(margin_to_text(p.get("page_margins")))
        self.left_margins.setText(margin_to_text(p.get("left_page_margins")))
        self.right_margins.setText(margin_to_text(p.get("right_page_margins")))

        self.title_printing.setChecked(bool(p.get("title_printing", True)))
        self.title_font_size.setValue(int(p.get("title_font_size", 18)))
        self.title_color.setText(str(p.get("title_color", "0,0,0")))
        self._set_combo(self.title_position, p.get("title_position"), "top")
        self._set_combo(self.title_orientation,
                        p.get("title_orientation"), "vertical")
        # 重建节点行（高度由行数自适应，无需再做高度归一）
        self._clear_node_rows()
        for node in (p.get("title_switch_nodes") or []):
            if not isinstance(node, (list, tuple)) or len(node) < 2:
                continue
            side = node[2] if len(node) >= 3 else "left"
            self._add_node_row(int(node[0]), str(node[1]), str(side))

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

        self.skip_pages.setText(skip_pages_to_text(p.get("skip_pages")))

        self._sync_enabled()
