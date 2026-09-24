# -*- coding: utf-8 -*-
"""print 表单 Mixin 拆分的不变量守卫。

`PrintFormMixin` 拆成了四层（编排 / 分区 / 距页边 / 固定排版方向）。拆分的
前提是「**只挪代码位置，不改行为**」，而 Mixin 之间靠 `self._xxx` 共享状态，
挪错一个方法不会报错、只会让某个控件悄悄失效——所以这里把三个不变量钉死：

1. **成员归属**：每个成员仍在它该在的类里，且 `PrintFormMixin` 全都能看到
   （`PrintPanel` 只继承 `PrintFormMixin` 一个，缺一个就是 AttributeError）；
2. **方法名不重叠**：四个类之间同名方法会被 MRO 静默遮蔽（子类赢），
   一旦重叠就等于"改了行为"，必须显式登记；
3. **跨类 `self.` 依赖在白名单内**：Mixin 调本类没有的成员是允许的（这正是
    Mixin 的用法），但**得是登记过的**——新加一个没登记的隐式契约，
   说明拆分边界被捅穿了。

⚠️ 第 3 条是**元守卫**意义上的：白名单不是为了"允许一切"，而是为了让
「新增跨类依赖」这件事**必须有人看一眼**。
"""

import ast
from pathlib import Path

NAME = "print_form_split"
DEPENDS: list[str] = []
TITLE = "print 表单 Mixin 拆分"

_ROOT = Path(__file__).resolve().parents[2]
_PANELS = _ROOT / "desktop" / "components" / "panels"

#: 拆分后的四个类（模块文件 → 类名）。顺序 = MRO 顺序。
_MODULES = [
    ("print_form.py", "PrintFormMixin"),
    ("print_sections.py", "PrintSectionsMixin"),
    ("print_inset.py", "PrintInsetMixin"),
    ("print_text_layout.py", "PrintTextLayoutMixin"),
]

#: 每个成员**应当**归属的类（成员名 → 类名）。改了落点就要同步改这里——
#: 这正是本守卫存在的意义：让"挪动"变成一次显式决定。
_EXPECTED_HOME = {
    # print_form：编排 + 通用控件工厂 + 节点行 + 按钮
    "build_form": "PrintFormMixin",
    "_apply_focus_policy": "PrintFormMixin",
    "_section": "PrintFormMixin",
    "_make_combo": "PrintFormMixin",
    "_set_combo": "PrintFormMixin",
    "_line_edit": "PrintFormMixin",
    "_spin_with_unit": "PrintFormMixin",
    "_color_row": "PrintFormMixin",
    "_refresh_color_swatch": "PrintFormMixin",
    "_add_node_row": "PrintFormMixin",
    "_clear_node_rows": "PrintFormMixin",
    "_collect_nodes": "PrintFormMixin",
    "_reset_default_clicked": "PrintFormMixin",
    "_reset_edits_clicked": "PrintFormMixin",
    # print_sections：五个分区
    "_build_output_section": "PrintSectionsMixin",
    "_build_margin_section": "PrintSectionsMixin",
    "_build_title_section": "PrintSectionsMixin",
    "_build_pagenum_section": "PrintSectionsMixin",
    "_build_filter_section": "PrintSectionsMixin",
    # print_inset：距页边
    "_make_inset": "PrintInsetMixin",
    "_inset_key": "PrintInsetMixin",
    "_inset_side_label": "PrintInsetMixin",
    "_inset_cross": "PrintInsetMixin",
    "_add_inset_rows": "PrintInsetMixin",
    "_inset_block": "PrintInsetMixin",
    "_inset_values": "PrintInsetMixin",
    "_set_inset_values": "PrintInsetMixin",
    "_inset_what": "PrintInsetMixin",
    "_refresh_inset_hint": "PrintInsetMixin",
    # print_text_layout：固定排版方向
    "_fixed_layout_default": "PrintTextLayoutMixin",
    "_fixed_layout": "PrintTextLayoutMixin",
}

#: 常量（同一套规则）
_EXPECTED_CONST_HOME = {
    "FIXED_TEXT_LAYOUT": "PrintTextLayoutMixin",
    "INSET_SIDES": "PrintInsetMixin",
    "INSET_VISIBLE": "PrintInsetMixin",
}

#: Mixin 调用**本类没有**的 self 成员 —— 登记的隐式契约。
#: 「类 → 允许依赖的 self 成员集合」。新增一条 = 拆分边界变松，要看一眼。
_CROSS_DEPS = {
    "PrintFormMixin": {
        "_add_row",              # base.StagePanel
        "_connect_title_pdf_link",  # PrintPanel（pdf_name ↔ title 联动）
        "mark_params_edited",    # base.StagePanel
        "reset_edits",           # PrintPanel
        "reset_to_default",      # PrintPanel
        "nodes_list",            # print_sections 建的控件，节点行方法在这
        "_scroll",               # 存给 PrintPanel/基类用的滚动区
        # build_form 是编排者，五个分区 builder 住在**子类** PrintSectionsMixin
        # （MRO 上排在后面），静态扫不到——这是编排层唯一允许的"向下调用"
        "_build_output_section", "_build_margin_section",
        "_build_title_section", "_build_pagenum_section",
        "_build_filter_section",
    },
    "PrintSectionsMixin": {
        "_add_row",              # base.StagePanel
        "_section",              # PrintFormMixin
        "_line_edit",            # PrintFormMixin
        "_make_combo",           # PrintFormMixin
        "_spin_with_unit",       # PrintFormMixin
        "_color_row",            # PrintFormMixin
        "_add_node_row",         # PrintFormMixin
        "_clear_node_rows",      # PrintFormMixin
        "_sync_enabled",         # PrintPanel
        "title_text", "pdf_name", "paper_size", "orientation", "keep_ratio",
        "page_margins", "left_margins", "right_margins",
        "title_printing", "title_font", "title_font_size", "title_color",
        "_title_inset",
        "nodes_list",
        "page_number_printing", "page_number_start", "page_number_end",
        "page_number_end_to_last", "page_number_base",
        "page_number_font", "page_number_font_size",
        "page_number_color", "_page_number_inset",
        # 页码样式与前后缀（PAGE_NUMBER_FORMATS 的下拉 + 两个输入框）
        "page_number_format", "page_number_prefix", "page_number_suffix",
        "skip_pages",
        # 本类继承 PrintInsetMixin，这两个是本类的"自己人"，但静态扫不到
        "_make_inset", "_add_inset_rows",
    },
    "PrintInsetMixin": {
        "_add_row",              # base.StagePanel
        "_title_inset",          # print_sections 建的控件组
        "_page_number_inset",
        "INSET_SIDES", "INSET_VISIBLE",  # 本类常量，但读取点是 self.X
    },
    "PrintTextLayoutMixin": {
        "_fixed_layout_echo",    # PrintPanel.__init__ 初始化
        "FIXED_TEXT_LAYOUT",     # 本类常量，读取点是 self.X
    },
}


def _load_classes() -> dict[str, ast.ClassDef]:
    out: dict[str, ast.ClassDef] = {}
    for fname, cname in _MODULES:
        tree = ast.parse((_PANELS / fname).read_text(encoding="utf-8"))
        cls = next(
            n for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == cname
        )
        out[cname] = cls
    return out


def _members(cls: ast.ClassDef) -> tuple[dict[str, str], dict[str, str]]:
    """返回 (方法名 → 定义模块, 常量名 → 定义模块)。"""
    meths: dict[str, str] = {}
    consts: dict[str, str] = {}
    for node in cls.body:
        if isinstance(node, ast.FunctionDef):
            meths[node.name] = ""
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    consts[t.id] = ""
    return meths, consts


def run(ctx) -> None:
    from tests.selftests._context import ok

    classes = _load_classes()

    # ---- 1. 成员归属 + PrintFormMixin 全能看到 ----
    home_of: dict[str, str] = {}
    for cname, cls in classes.items():
        meths, consts = _members(cls)
        for name in list(meths) + list(consts):
            home_of.setdefault(name, cname)

    expected = {**_EXPECTED_HOME, **_EXPECTED_CONST_HOME}
    ok("守卫覆盖了拆分后的全部成员（不是空跑）",
       len(expected) >= 30, f"只登记了 {len(expected)} 个成员")

    wrong = {
        n: (expected[n], home_of.get(n))
        for n in expected
        if home_of.get(n) != expected[n]
    }
    ok("每个成员都停在拆分时指定的类里", not wrong, f"落点漂移={wrong}")

    missing = sorted(set(expected) - set(home_of))
    ok("没有成员在拆分中丢失", not missing, f"丢失={missing}")

    from desktop.components.panels.print_form import PrintFormMixin

    invisible = [n for n in expected if not hasattr(PrintFormMixin, n)]
    ok("PrintFormMixin 仍能看到全部成员（PrintPanel 只继承它一个）",
       not invisible, f"看不到={invisible}")

    # ---- 2. 四个类之间方法名不重叠（重叠 = MRO 静默遮蔽 = 改了行为）----
    overlap: dict[str, list[str]] = {}
    seen: dict[str, str] = {}
    for cname, cls in classes.items():
        meths, consts = _members(cls)
        for name in list(meths) + list(consts):
            if name in seen:
                overlap.setdefault(name, [seen[name]]).append(cname)
            else:
                seen[name] = cname
    ok("四个 Mixin 之间没有同名成员（否则 MRO 会静默遮蔽）",
       not overlap, f"重叠={overlap}")

    # ---- 3. 跨类 self. 依赖全在白名单内 ----
    bad: dict[str, list[str]] = {}
    for cname, cls in classes.items():
        meths, consts = _members(cls)
        own = set(meths) | set(consts)
        allowed = _CROSS_DEPS.get(cname, set())
        foreign: set[str] = set()
        for node in ast.walk(cls):
            if (isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "self"):
                foreign.add(node.attr)
        unknown = sorted(foreign - own - allowed)
        if unknown:
            bad[cname] = unknown
    ok("Mixin 之间的 self 共享状态全部登记在案",
       not bad, f"未登记的隐式契约={bad}")
