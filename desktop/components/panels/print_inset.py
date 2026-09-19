# -*- coding: utf-8 -*-
"""「距页边」控件组：标题 / 页码两段文字各自的两行输入框。

从 ``print_form.PrintFormMixin`` 拆出。这一段是**完整内聚**的一块：
造控件 → 加行 → 取值 → 回填 → 刷新释义，都只围着 ``block`` 字典转。

* 依赖：`self._add_row`（``base.StagePanel``）、
  `self._title_inset` / `self._page_number_inset`（由 ``print_sections`` 创建）
* 被依赖：``PrintSectionsMixin``（造行）、``PrintPanel``（取值 / 回填）

⚠️ **拆出后仍然靠 `self._xxx` 共享状态**——这是 Mixin 拆分的固有代价，
不要为了"看起来独立"去加构造参数：面板的 MRO 是线性的，共享 self
反而是这里最简单正确的做法。共享点全部登记在
``tests/selftests/print_form_split.py`` 的白名单里。
"""

from __future__ import annotations

from qfluentwidgets import CaptionLabel, CheckBox

from desktop.components.common.safecomment import SafeDoubleSpinBox
from desktop.components.panels.params_spec import INSET_SPIN_VIEW_VALUE


class PrintInsetMixin:
    """print 面板「距页边」控件组（由 PrintFormMixin 继承）。"""

    # ------------------------------------------------------------------ 距页边
    # 界面就是**两行、每行一个通栏输入框**（用户明确要求，别再摊成一排小格子）：
    #   第一行「左右边距：」→ 一个框，同时管左页（贴左纸边）和右页（贴右纸边）；
    #   第二行「上边距：」/「下边距：」→ 一个框（标题贴纸张上边、页码贴下边）。
    # 纵向只取用得上的那一个——与 `utils.page_layout._text_anchor` 的
    # `side` / `is_top` 分支一一对应。
    #
    # ⚠️ 参数值仍是**四元素** [上,右,下,左]（`title_margins` 契约见
    # utils.page_layout），界面只是不摆用不到的分量；未启用「自定义」时
    # 导出 None，与不带这两个键的老任务完全一致（老行为不是 2mm 字面量，
    # 而是由 page_margins 推导，见 `_text_anchor`）。
    INSET_SIDES = (("top", "上"), ("right", "右"), ("bottom", "下"), ("left", "左"))
    # 每段文字界面的两行：side = 横向那一行（代表 左+右 两个分量）；
    # cross = 纵向那一行 (方向键, 行标签)
    INSET_VISIBLE = {
        "title": {"side": "左右边距", "cross": ("top", "上边距")},
        "page_number": {"side": "左右边距", "cross": ("bottom", "下边距")},
    }

    def _make_inset(self, what: str) -> dict:
        """构建「距页边」的一组控件（**不加进行布局**，行由调用方按序加）。

        界面只有**两行、每行一个通栏输入框**（用户指定形态）：

        * 第一行「左右边距：」——一个框，横向那份距离（左页贴左纸边、右页贴右纸边）；
        * 第二行「上边距：」/「下边距：」——一个框，纵向那份距离
          （标题贴纸张上边 → 「上边距」；页码贴下边 → 「下边距」）。

        两个输入框都**不设固定宽度**，由 `QFormLayout` 拉到与「古籍名称」
        「PDF 文件名」等输入框一样的通栏宽度，视觉整齐、数字也看得清。

        `spins` 按方向名装框：横向那行的框**同时登记为 left 与 right**
        （它一个值代表两边），纵向那行登记 cross_key，导出时补全成四元素。

        ⚠️ 只造控件、由调用方在**正确的行位置**加进 form。若在这里顺手加行，
        距页边会跑到「字体大小」前面去。
        """
        which = "title" if what == "标题" else "page_number"
        cross_key, cross_label = self._inset_cross(which)
        side_label = self._inset_side_label(which)
        enabled = CheckBox(f"自定义{what}距页边")
        enabled.setToolTip(
            f"不勾选 = 老行为（{what}横向贴页边距中缝、纵向内缩 2mm）。\n"
            f"勾选后按下面的距离画**距离纸张边界**（mm）：\n"
            f"  · {side_label}：一个值同时管两边"
            "（左页贴左纸边、右页贴右纸边，所以左右是对称的）；\n"
            f"  · {cross_label}：只填这一个纵向距离"
            f"（{'标题贴纸张上边' if cross_key == 'top' else '页码贴纸张下边'}）。\n"
            "⚠️ 填了之后图片**不会**再收窄让位：文字就画在你设的距离上，\n"
            "   即使压在图片上也是你的选择。"
        )
        spins: dict[str, object] = {}
        widgets: dict[str, object] = {}
        for key in ("side", "cross"):
            spin = SafeDoubleSpinBox()
            spin.setRange(0.0, 3000.0)
            spin.setDecimals(1)
            spin.setSingleStep(0.5)
            spin.setValue(INSET_SPIN_VIEW_VALUE)  # 仅输入框显示初值，未启用时不入参数
            spin.setSuffix(" mm")
            spin.setMinimumWidth(120)
            # 横向那一个框**就是**左+右两个分量：按方向名登记两次，
            # 导出/回填都走 `spins` 的键，不必再写「跟随另一边」的特例。
            if key == "side":
                spins["left"] = spin
                spins["right"] = spin
            else:
                spins[cross_key] = spin
            widgets[key] = spin

        hint = CaptionLabel("")
        hint.setWordWrap(True)
        for spin in set(spins.values()):
            spin.valueChanged.connect(lambda *_a, w=what: self._refresh_inset_hint(w))
        for spin in widgets.values():
            spin.setEnabled(False)

        def _toggle(on: bool) -> None:
            for box in widgets.values():
                box.setEnabled(on)

        enabled.toggled.connect(_toggle)

        block = {
            "enabled": enabled,
            "widgets": widgets,
            "spins": spins,
            "hint": hint,
            "what": what,
        }
        return block

    def _inset_key(self, block: dict) -> str:
        """控件组 → title / page_number 键名。"""
        return "title" if block["what"] == "标题" else "page_number"

    def _inset_side_label(self, which: str) -> str:
        """横向那一行的行标签（「左右边距」）。"""
        return str(self.INSET_VISIBLE.get(which, {}).get("side", "左右边距"))

    def _inset_cross(self, which: str) -> tuple:
        """纵向那一行：返回 (方向键, 行标签)。

        标题贴纸张上边 → (top, 「上边距」)；页码贴下边 → (bottom, 「下边距」)。
        """
        pair = self.INSET_VISIBLE.get(which, {}).get("cross", ("top", "上边距"))
        return pair[0], pair[1]

    def _add_inset_rows(self, form, block: dict) -> None:
        """把「距页边」的勾选框 + 两行参数 + 释义行按顺序加进表单。

        两行都是**一个通栏输入框**：

        * 第一行「左右边距：」→ 横向那份距离（一个值管左页+右页）；
        * 第二行「上边距：」/「下边距：」→ 纵向那份距离。

        输入框不设固定宽度，交给 `QFormLayout` 拉到与「古籍名称」等一致的
        通栏宽度（这是与"一排小格子"最明显的区别）。

        依赖 `self._add_row`（``base.StagePanel``）。
        """
        form.addRow(block["enabled"])
        which = self._inset_key(block)
        _, cross_label = self._inset_cross(which)
        self._add_row(
            form, f"{self._inset_side_label(which)}：", block["widgets"]["side"]
        )
        self._add_row(form, f"{cross_label}：", block["widgets"]["cross"])
        form.addRow(block["hint"])
        self._refresh_inset_hint(block["what"])  # 首帧先按"未启用"填一次释义

    def _inset_block(self, which: str) -> dict:
        """取某段文字（title / page_number）的距页边控件组。"""
        return getattr(self, f"_{which}_inset")

    def _inset_values(self, which: str) -> list | None:
        """距页边两行控件 → [上,右,下,左]；未勾选"自定义"时返回 None（= 老行为）。

        ⚠️ 与 `_text_anchor` 的读取口径**保持一致**：
        * 界面没摆的那个纵向分量（标题的「下」/ 页码的「上」）在底层**永远读不到**，
          这里就按 0 导出——**绝不能把输入框的显示初值 2.0 混进参数**，
          否则导出的配置里会躺着一个用户从没设过、也没人能看到的数
          （旧实现四个框全摆，看不出这个毛病；收成两行以后就暴露了）；
        * 横向那**一个**框同时充当「左」与「右」两个分量（左页贴左纸边、
          右页贴右纸边），所以两边的值必然相同——界面就一个值，语义如此。
        """
        block = self._inset_block(which)
        if not block["enabled"].isChecked():
            return None
        return [
            float(block["spins"].get(key).value()) if key in block["spins"] else 0.0
            for key, _label in self.INSET_SIDES
        ]

    def _set_inset_values(self, which: str, values) -> None:
        """把 [上,右,下,左]（或 None）填回控件；None = 不勾选"自定义"。

        也接受 1/2/3 值的简写（同页边距的 CSS 填法，如 `[2, 14]` = 上下 2、左右 14）：
        手写配置/历史记录里可能有这种写法，先补全成四值再填，否则"只填了前两个、
        后两个还留着上一个配置的值"，用户看到的是个拼接出来的怪配置。

        ⚠️ 横向只有一个框，但它对应 left/right 两个方向键（同一个控件对象）：
        直接按 `spins` 的键回填会让**后写的覆盖先写的**（左 10 / 右 14 最终
        显示 14）。横向框按 `_text_anchor` 的真实读取口径取**左页值**，
        纵向框取该段文字真正会用的那个值。
        """
        from utils.margin_utils import normalize_margin

        resolved = normalize_margin(values, default=None) if values else None
        block = self._inset_block(which)
        block["enabled"].setChecked(bool(resolved))
        for spin in block["widgets"].values():
            spin.setEnabled(bool(resolved))
        if resolved:
            by_key = dict(zip((k for k, _ in self.INSET_SIDES), resolved))
            # 横向：恒取「左」（= 距离左纸边的值；它同时代表右纸边）
            block["widgets"]["side"].setValue(float(by_key["left"]))
            cross_key, _ = self._inset_cross(which)
            block["widgets"]["cross"].setValue(float(by_key[cross_key]))
        self._refresh_inset_hint(self._inset_what(which))

    @staticmethod
    def _inset_what(which: str) -> str:
        """控件组名 → 给用户看的名字。"""
        return "标题" if which == "title" else "页码"

    def _refresh_inset_hint(self, what: str) -> None:
        """刷新「距页边」的释义行：把当前设置翻成人话。

        ⚠️ 程序化回填也会走到这里，任何异常都要吞掉——释义只是提示，
        不能让它打断输入或回填。
        """
        which = "title" if what == "标题" else "page_number"
        block = self._inset_block(which)
        if not block["enabled"].isChecked():
            block["hint"].setText(f"{what}未启用 → 贴着页边距中缝画（老行为）")
            return
        cross = block["widgets"]["cross"].value()
        side = block["widgets"]["side"].value()
        cross_label = "距上" if which == "title" else "距下"
        # ⚠️ 「距左右」说的是**文字轮廓边缘**到纸边的距离（不是落点/字格左缘）：
        # 右页的文字往右占一个块宽，落点会自动往左退一格来兑现这个值，
        # 所以左、右两页看到的是**对称**的白边（见 page_layout._text_anchor）。
        block["hint"].setText(
            f"文字轮廓距左右纸边各 {side:g}mm｜{cross_label} {cross:g}mm"
            "（可直接压在图片上）"
        )
