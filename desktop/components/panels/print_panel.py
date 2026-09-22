# -*- coding: utf-8 -*-
"""生成 PDF（print）阶段面板：表单状态（取值/回填/重置）。

表单控件构建见 print_form.py，参数解析见 print_params.py，
默认值统一取 params_spec.DEFAULTS["print"]。
input/output/workers/clean 由系统管理，不出现在表单中。
"""

from __future__ import annotations

from PySide6.QtCore import Signal

from desktop.components.panels.base import StagePanel, default_for
from desktop.components.panels.params_spec import DEFAULTS
from core.command_spec import border_has_padding
from desktop.components.panels.print_form import PrintFormMixin
from desktop.services.font_catalog import AUTO_VALUE, catalog
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

    # 任一影响排版的控件变化 → 第四步「打印效果」预览按新参数重画
    # （只是重画内存位图，不执行生成 PDF）
    params_changed = Signal()

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
        # 「位置」「文字方向」界面已删除（见 PrintFormMixin.FIXED_TEXT_LAYOUT）。
        # 这里记住**历史参数里的原值**：桌面端不能改这两个键，但也不能把它们
        # 悄悄改掉——用户一个老任务存的是 horizontal，进第四步什么都没动，
        # 参数暂存却把它写成 vertical，属于最难查的那类漂移。没历史时才用固定值。
        self._fixed_layout_echo: dict | None = None
        # 当前任务源 PDF 的文件名（无扩展名）：用于派生默认 PDF 名与古籍名
        self._source_stem = ""
        # title_text 与 pdf_name 联动标志：True 表示 pdf_name = f"{title_text}[重制].pdf"
        # 用户直接修改 pdf_name 后自动置 False，联动解除；set_source_defaults / reset_to_default 时恢复
        self._pdf_name_auto = True
        # 上游（第三步 rembg/crop）border 级联：非 0 时第四步通用边距默认 0。
        # view 在 rembg border 变化 / 进入第四步时通过 set_upstream_border 写入。
        self._upstream_border = None
        # 用户是否手动改过通用边距；改过后上游 border 变化不再覆盖其值。
        self._margin_edited = False
        self.reset_to_default()
        # 焦点策略：必须在基类 __init__ 之后调（ScrollArea 已 addWidget 到 layout），
        # 且必须用 self 而非 container——因为只有此时 self.findChildren(QWidget)
        # 才能遍历到完整的子树；build_form 内部调的话，qfluent 控件的父级 attach
        # 会覆盖 setFocusPolicy
        self._apply_focus_policy(self)
        self._connect_preview_signals()
        self._connect_font_catalog()

    def _extra_param_signals(self) -> list:
        """节点表不是标准控件：它自己的 ``changed`` 也要算"用户改了参数"。

        标题切换节点会改变各页标题（版面随之变），漏了它就会出现
        「节点表改了、暂存里没有」这种半截状态。
        """
        return [self.nodes_list.changed]

    def _connect_font_catalog(self) -> None:
        """接上字体目录：启动后台扫描（全局只一次）+ 扫完刷新两个下拉。

        扫描在**后台线程**跑（本机约 7 秒），这里只是发起，不等待；列表先
        用静态候选（仿宋/宋体/雅黑/黑体…），扫完自动把用户自己装的字体补
        进来，用户的选择始终保留。
        """
        font_catalog = catalog()
        font_catalog.scan_finished.connect(self._refresh_font_combos)
        font_catalog.start_scan()

    def _refresh_font_combos(self, items) -> None:
        """后台扫描完成后：重建两个字体下拉，保住当前选择。"""
        for combo in (self.title_font, self.page_number_font):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for label, value in items or ():
                combo.addItem(label, userData=value)
            # 列表里没有当前值（配置来自别的机器）→ 补一项，别悄悄改回自动
            if current and combo.findData(current) < 0:
                combo.addItem(str(current), userData=current)
            combo.blockSignals(False)
            self._set_combo(combo, current, AUTO_VALUE)

    def _connect_preview_signals(self) -> None:
        """把影响排版的控件接到 params_changed（供第四步效果预览刷新）。

        只连"会改变 PDF 版面"的控件：纸张/方向/边距/标题与页码的开关、
        内容、字号、颜色、位置，以及跳过页。pdf_name 不影响版面，不入列。
        """
        def emit(*_args):
            self.params_changed.emit()

        for combo in (
            self.paper_size, self.orientation,
            self.title_font, self.page_number_font, self.page_number_format,
        ):
            combo.currentTextChanged.connect(emit)
        for edit in (
            self.page_margins, self.left_margins, self.right_margins,
            self.title_text, self.title_color,
            self.page_number_color, self.skip_pages,
            self.page_number_prefix, self.page_number_suffix,
        ):
            edit.textChanged.connect(emit)
        # 「距页边」是勾选框 + 四个距离输入（不再是"上,右,下,左"文本框）
        for block_name in ("_title_inset", "_page_number_inset"):
            block = getattr(self, block_name)
            block["enabled"].toggled.connect(emit)
            for spin in block["spins"].values():
                spin.valueChanged.connect(emit)
        for spin in (
            self.title_font_size, self.page_number_start,
            self.page_number_end, self.page_number_base,
            self.page_number_font_size,
        ):
            spin.valueChanged.connect(emit)
        for check in (
            self.title_printing, self.page_number_printing,
            self.page_number_end_to_last,
        ):
            check.toggled.connect(emit)
        # 章节节点：改变各页标题，版面随之变化
        self.nodes_list.changed.connect(emit)
        # 通用边距被用户手动改动后，上游 border 级联不再覆盖其值
        self.page_margins.textEdited.connect(self._on_margin_edited)

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
        # 上游 border 级联：第三步设了真实留白（非 0）→ 通用边距默认回落 0，
        # 避免「图片内留白 + 页面边距」双重留白。上游未设 border 则保持内置默认。
        if border_has_padding(self._upstream_border):
            params["page_margins"] = [0, 0, 0, 0]
        if self._source_stem:
            params["pdf_name"] = f"{self._source_stem}[重制].pdf"
            params["title_text"] = self._source_stem
        return params

    # ---------- 上游 border 级联 ----------
    def set_upstream_border(self, border) -> None:
        """写入上游（第三步 rembg/crop）border，并刷新通用边距默认值显示。

        仅当用户尚未手动改过通用边距时，才把表单里的边距默认值同步为级联
        结果（上游非 0 → 0，否则 20），让用户「看见」默认值已变化；
        用户一旦手动改过，上游 border 变化不再覆盖其选择。
        """
        self._upstream_border = border
        if not self._margin_edited:
            self._apply_upstream_margin_default()

    def _apply_upstream_margin_default(self) -> None:
        default = (
            "0" if border_has_padding(self._upstream_border)
            else margin_to_text(DEFAULT_PARAMS["page_margins"])
        )
        self.page_margins.blockSignals(True)
        self.page_margins.setText(default)
        self.page_margins.blockSignals(False)

    def _on_margin_edited(self, _text: str) -> None:
        """通用边距被用户手动输入 → 标记已改，上游 border 级联不再覆盖。"""
        self._margin_edited = True

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
            self.title_font, self.title_font_size, self.title_color,
            self._title_inset["enabled"], self.nodes_list,
        ):
            w.setEnabled(title_on)
        num_on = self.page_number_printing.isChecked()
        for w in (
            self.page_number_start, self.page_number_end,
            self.page_number_end_to_last, self.page_number_base,
            self.page_number_format, self.page_number_prefix,
            self.page_number_suffix,
            self.page_number_font, self.page_number_font_size,
            self.page_number_color,
            self._page_number_inset["enabled"],
        ):
            w.setEnabled(num_on)
        if num_on:
            self.page_number_end.setEnabled(
                not self.page_number_end_to_last.isChecked()
            )

    def reset_to_default(self) -> None:
        """恢复为该面板的内置默认参数（不依赖任何历史执行）。"""
        self._apply_args_guarded(self._default_params())
        self._margin_edited = False

    def reset_edits(self) -> None:
        """撤销本次修改：恢复到最近一次执行的参数。

        与 reset_to_default（恢复内置默认）不同，本方法回到 mark_applied
        记录的上一轮执行参数；若从未执行过则退化为恢复默认。
        """
        if self._last_applied is not None:
            self._apply_args_guarded(self._last_applied)
        else:
            self.reset_to_default()
        self._margin_edited = False

    def mark_applied(self, parameters: dict) -> None:
        """记录最近一次执行使用的参数（供「放弃本次修改」恢复）。"""
        clean = {
            k: v for k, v in (parameters or {}).items() if k not in EXCLUDED_KEYS
        }
        self._last_applied = clean

    # ------------------------------------------------------------------ 取值
    def set_inset(self, which: str, values) -> None:
        """程序化设置某段文字的「距页边」（which=title / page_number）。

        values = [上,右,下,左]（mm）表示启用并填值；None 表示不启用（老行为）。
        """
        self._set_inset_values(which, values)

    def inset(self, which: str) -> list | None:
        """读当前「距页边」：``[上,右,下,左]``；未勾选"自定义"时是 None。"""
        return self._inset_values(which)

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
            "pdf_name": self.pdf_name.text().strip() or DEFAULT_PARAMS["pdf_name"],
            "paper_size": self.paper_size.currentText(),
            "orientation": self.orientation.currentData(),
            "page_margins": page_margins,
            "title_printing": self.title_printing.isChecked(),
            "title_text": self.title_text.text().strip(),
            # 空串 = 「自动（仿宋优先）」：存 None，与 CLI/模板的默认值一致
            "title_font": self.title_font.currentData() or None,
            "title_font_size": self.title_font_size.value(),
            "title_color": self.title_color.text().strip(),
            "title_position": self._fixed_layout("title", "position"),
            "title_orientation": self._fixed_layout("title", "orientation"),
            "title_margins": self._inset_values("title"),
            "title_switch_nodes": self._collect_nodes(),
            "page_number_printing": self.page_number_printing.isChecked(),
            "page_number_start_page": self.page_number_start.value(),
            "page_number_base": self.page_number_base.value(),
            # ⚠️ 前缀/后缀**不能**用 `or` 兜底：空串是合法值（用户只要数字），
            # `or` 会把它悄悄变回默认的「第/頁」。
            "page_number_prefix": self.page_number_prefix.text(),
            "page_number_suffix": self.page_number_suffix.text(),
            "page_number_format": (
                self.page_number_format.currentData()
                or DEFAULT_PARAMS["page_number_format"]
            ),
            "page_number_font": self.page_number_font.currentData() or None,
            "page_number_font_size": self.page_number_font_size.value(),
            "page_number_color": self.page_number_color.text().strip(),
            "page_number_position": self._fixed_layout("page_number", "position"),
            "page_number_orientation": self._fixed_layout("page_number", "orientation"),
            "page_number_margins": self._inset_values("page_number"),
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
        # 缺键一律回落到 params_spec 的集中默认值（本面板不再自写字面量，
        # 避免「兜底 12 / 默认 18」这类同参数两套值）
        d = DEFAULTS[self.stage]
        # pdf_name / title_text 可能在 set_source_defaults 里刚派生好，
        # 这里再用 blockSignals 保护 setText，避免触发 textEdited 让联动标志错乱
        self.pdf_name.blockSignals(True)
        self.title_text.blockSignals(True)
        self.pdf_name.setText(str(p.get("pdf_name") or self._default_params()["pdf_name"]))
        self.title_text.setText(str(p.get("title_text") or default_for(p, d, "title_text") or ""))
        self.pdf_name.blockSignals(False)
        self.title_text.blockSignals(False)
        # 程序赋值结束后：若 pdf_name 恰好等于 title_text 派生值，视为自动态；
        # 否则（例如历史里存的是 print.pdf / printpdf.pdf 这种自定义值），
        # 联动暂时解除，用户后续改 title_text 不会覆盖 pdf_name
        self._refresh_pdf_name_auto()
        paper = str(default_for(p, d, "paper_size")).upper()
        self.paper_size.setCurrentText(
            paper if paper in PAPER_SIZES else DEFAULT_PARAMS["paper_size"]
        )
        self._set_combo(self.orientation, p.get("orientation"), d["orientation"])

        # 「位置」「文字方向」界面已删除（见 PrintFormMixin.FIXED_TEXT_LAYOUT）：
        # 不回填控件（也没有控件），但把历史值**原样记住**，导出时回显——
        # 桌面端不该改这两个键，老任务里的 horizontal 必须保持 horizontal。
        self._fixed_layout_echo = {
            key: p[key]
            for key in ("title_position", "title_orientation",
                        "page_number_position", "page_number_orientation")
            if p.get(key)
        }

        self.page_margins.setText(margin_to_text(p.get("page_margins")))
        self.left_margins.setText(margin_to_text(p.get("left_page_margins")))
        self.right_margins.setText(margin_to_text(p.get("right_page_margins")))

        self.title_printing.setChecked(bool(default_for(p, d, "title_printing")))
        self._set_font_combo(self.title_font, p.get("title_font"))
        self.title_font_size.setValue(int(default_for(p, d, "title_font_size")))
        self.title_color.setText(str(default_for(p, d, "title_color")))
        # ⚠️ 「位置」「文字方向」界面已删除（见 PrintFormMixin.FIXED_TEXT_LAYOUT）：
        # 这里**故意不回填、也不改写参数**。参数值原样留在 `parameters` 里，
        # 只有 `get_args()` 真正取值时才按固定表导出——否则「参数暂存」会把
        # 老任务里的 horizontal 静默改写成 vertical（用户没动过任何控件，
        # 配置却变了，属于最难查的那类漂移）。
        self._set_inset_values("title", p.get("title_margins"))
        # 重建节点行（高度由行数自适应，无需再做高度归一）
        self._clear_node_rows()
        for node in (p.get("title_switch_nodes") or []):
            if not isinstance(node, (list, tuple)) or len(node) < 2:
                continue
            side = node[2] if len(node) >= 3 else "left"
            self._add_node_row(int(node[0]), str(node[1]), str(side))

        self.page_number_printing.setChecked(
            bool(default_for(p, d, "page_number_printing"))
        )
        self.page_number_start.setValue(int(default_for(p, d, "page_number_start_page")))
        end_page = p.get("page_number_end_page")
        default_end = d["page_number_end_page"]
        if end_page is None:
            # 默认「到最后一页」= end_page 未配置；控件值退回默认表里的结束页
            # （默认也是 None，此时显示 1，仅作输入框当前值，不参与导出）
            self.page_number_end_to_last.setChecked(default_end is None)
            self.page_number_end.setValue(
                int(default_end) if default_end is not None else 1
            )
        else:
            self.page_number_end_to_last.setChecked(False)
            self.page_number_end.setValue(int(end_page))
        self.page_number_base.setValue(int(default_for(p, d, "page_number_base")))
        # 前缀/后缀用 default_for（只在缺键或 None 时回落）：用户清空输入框
        # 表示"只要数字"，不能被兜底成默认的「第/頁」
        self.page_number_prefix.setText(
            str(default_for(p, d, "page_number_prefix") or "")
        )
        self.page_number_suffix.setText(
            str(default_for(p, d, "page_number_suffix") or "")
        )
        self._set_combo(
            self.page_number_format,
            p.get("page_number_format"),
            DEFAULT_PARAMS["page_number_format"],
        )
        self._set_font_combo(self.page_number_font, p.get("page_number_font"))
        self.page_number_font_size.setValue(int(default_for(p, d, "page_number_font_size")))
        self.page_number_color.setText(str(default_for(p, d, "page_number_color")))
        # 同标题：「位置」「文字方向」已在桌面端删除，不回填、不改写。
        self._set_inset_values("page_number", p.get("page_number_margins"))

        self.skip_pages.setText(skip_pages_to_text(p.get("skip_pages")))

        self._sync_enabled()
        # 历史回填/恢复默认也要刷新第四步的效果预览（此时可能还没人监听）
        self.params_changed.emit()
