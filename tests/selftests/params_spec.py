# -*- coding: utf-8 -*-
"""阶段参数默认值的**集中管理**自测（desktop/components/panels/params_spec.py）。

背景：同一个参数的默认值原先散在三处——「构建控件时的 setValue」「``_apply_args``
里的 ``p.get(key, 字面量)`` 兜底」「``reset_to_default``」。改一处漏两处，
`page_number_font_size` 就真的漂成了两套值（兜底 12 / 默认 18）：用户点
「恢复默认」得到 18，而历史配置里缺这个键时回填成 12——同一个参数两个默认值。

本模块的守卫分三层：

1. **源码层**：面板的 ``_apply_args`` 里不许再出现 ``p.get("键", 字面量)``
   这种自带默认值兜底的写法（缺键必须回落到 ``DEFAULTS``）。这条最能防回归：
   以后谁再往面板里塞一个硬编码默认，这里立刻红。
2. **覆盖层**：面板 ``get_args()`` 产出的每个键，必须在 ``DEFAULTS[stage]``
   里登记（或在豁免表里说明理由）。防止「表单加了新参数却没登记默认值」。
3. **行为层**：``reset_to_default()`` 之后 ``get_args()`` 的值必须等于
   ``DEFAULTS[stage]``；且 ``_apply_args({})``（空回填）与恢复默认等价。
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

NAME = "params_spec"
DEPENDS: list[str] = []
TITLE = "阶段参数默认值集中管理"

_ROOT = Path(__file__).resolve().parents[2]
_PANELS_DIR = _ROOT / "desktop" / "components" / "panels"

# 面板源码里「自带默认值兜底」的写法：p.get("键", 字面量) / parameters.get("键", 字面量)
# 只匹配**两个参数**的 get（第二个即默认兜底）——单参数 get 是正常取值。
_HARDCODED_GET = re.compile(
    r"\b(?:p|parameters)\s*\.\s*get\(\s*[\"'][A-Za-z_][A-Za-z0-9_]*[\"']\s*,"
)

# 各阶段 get_args() 产出的键里，**刻意**不在 DEFAULTS 登记的（附理由）：
# - print：位置/文字方向由 FIXED_TEXT_LAYOUT 固定导出（界面不提供、默认表也不能带，
#   否则「恢复默认」会把固定值灌进 _fixed_layout_echo，让固定表这条路径走不到）；
#   page_number_end_page 未配置时 =「到最后一页」，是**三态**而非默认值问题。
_EXEMPT: dict[str, set[str]] = {
    "print": {
        "title_position", "title_orientation",
        "page_number_position", "page_number_orientation",
        "page_number_end_page",
    },
    "extract": set(),
    "rembg": set(),
    "detect": set(),
}


def _panel_source(stage: str) -> str:
    """读面板源码（用于「不许再写硬编码兜底」的守卫）。"""
    path = _PANELS_DIR / f"{stage}_panel.py"
    return path.read_text(encoding="utf-8")


def run(ctx) -> None:
    from desktop.components.panels import PANEL_CLASSES
    from desktop.components.panels.params_spec import DEFAULTS
    from tests.selftests._context import ok

    # ---------------------------------------------------------------- 1. 源码层
    # 「缺键回落到默认值」必须由 DEFAULTS 统一给，不许在面板里再写一份字面量。
    for stage in ("extract", "rembg", "print"):
        src = _panel_source(stage)
        # 只查 _apply_args 的函数体：get_args 里的 or 兜底是另一码事
        body = src.split("def _apply_args", 1)
        ok(f"{stage} 面板存在 _apply_args（守卫前提）", len(body) == 2,
           "找不到 def _apply_args")
        tail = body[1] if len(body) == 2 else ""
        hits = _HARDCODED_GET.findall(tail)
        ok(f"{stage} 的 _apply_args 不再自带硬编码默认兜底",
           not hits, f"仍有 {len(hits)} 处：{hits}")

    # 面板必须**引用**集中表（而不是自己抄一份字典）
    for stage in ("extract", "rembg", "print"):
        src = _panel_source(stage)
        ok(f"{stage} 面板从 params_spec 取默认值",
           "params_spec" in src and "DEFAULTS" in src,
           "源码里没有引用 params_spec.DEFAULTS")

    # 三层一致：desktop 的 print 默认表**就是** CLI 的表单默认值，不是抄一份。
    # 用户要求「所有参数默认值只保留一份地方」，这条钉住的是 desktop 侧不另起炉灶。
    from core.command_spec import PRINT_FORM_DEFAULTS as _cli_form
    from desktop.components.panels.params_spec import DEFAULTS as _gui_defaults

    diff = {
        k: (_gui_defaults["print"].get(k), v)
        for k, v in _cli_form.items()
        if _gui_defaults["print"].get(k) != v
    }
    ok("print 默认表与 CLI 的 PRINT_FORM_DEFAULTS 逐键一致（不再各写一份）",
       not diff, f"差异={diff}")

    # ---------------------------------------------------------------- 2. 覆盖层
    panels = {cls.stage: cls() for cls in PANEL_CLASSES}
    for stage, panel in panels.items():
        defaults = DEFAULTS.get(stage) or {}
        produced = set(panel.get_args())
        missing = produced - set(defaults) - _EXEMPT.get(stage, set())
        ok(f"{stage}：get_args 的键都在 DEFAULTS 里登记",
           not missing, f"未登记：{sorted(missing)}")

    # ---------------------------------------------------------------- 3. 行为层
    # 「恢复默认」之后表单导出的值 == 集中默认表（这正是 12/18 冲突的落点）
    print_panel = panels["print"]
    d_print = DEFAULTS["print"]
    print_panel.reset_to_default()
    args = print_panel.get_args()
    ok("恢复默认后 page_number_font_size == 默认表的值",
       args["page_number_font_size"] == d_print["page_number_font_size"],
       f"表单 {args['page_number_font_size']} / 默认表 {d_print['page_number_font_size']}")
    # ⚠️ 别把 18 这类数字写进断言：默认值一旦调整（本项目就把字号从 18 调到
    # 20），写死的断言就会红，而且是"看起来像代码错了"的那种假失败。
    # 真正的契约是「标题与页码字号同源」，具体数值由 command_spec 说了算。
    ok("默认表的页码字号与标题字号同源（数值不写死）",
       d_print["page_number_font_size"] == d_print["title_font_size"],
       f"页码 {d_print['page_number_font_size']} / 标题 {d_print['title_font_size']}")
    ok("恢复默认后 title_font_size == 默认表的值",
       args["title_font_size"] == d_print["title_font_size"],
       f"表单 {args['title_font_size']} / 默认表 {d_print['title_font_size']}")
    ok("恢复默认后纸张/方向取默认表",
       args["paper_size"] == d_print["paper_size"]
       and args["orientation"] == d_print["orientation"],
       f"{args['paper_size']}/{args['orientation']}")
    ok("恢复默认后标题与页码都开",
       args["title_printing"] is True and args["page_number_printing"] is True,
       f"{args['title_printing']}/{args['page_number_printing']}")

    # 空回填（{}）与恢复默认等价——两者都该落到同一份默认表
    print_panel._apply_args_guarded({})
    empty_args = print_panel.get_args()
    ok("空回填 {} 与恢复默认导出同一套字号",
       empty_args["page_number_font_size"] == args["page_number_font_size"]
       and empty_args["title_font_size"] == args["title_font_size"],
       f"空回填 {empty_args['page_number_font_size']}/{empty_args['title_font_size']}")

    # extract / rembg：恢复默认后取到的值 == 默认表
    for stage in ("extract", "rembg"):
        panel = panels[stage]
        d = DEFAULTS[stage]
        panel.reset_to_default()
        got = panel.get_args()
        bad = {k: (got.get(k), v) for k, v in d.items()
               if k in got and got[k] != v and k != "border"}
        ok(f"{stage}：恢复默认后表单值与默认表一致", not bad, f"偏离：{bad}")

    # ------------------------------------------------------- 4. rembg 下拉取值
    # 旧实现是 int(area.currentText()[0])——解析显示文本首字符：只要有人把
    # 文案从「1 (左右分开)」改成「一、左右分开」，取值直接 ValueError。
    # 现在值存在 itemData 里。
    #
    # ⚠️ 断言必须走 ``get_args()``（真实契约），不能只读 ``currentData()``：
    # 只读 currentData 的话，把 get_args 改回旧写法**这条也不会红**——因为旧
    # 写法在**当前**文案下恰好也解析得出正确数字。只有改掉文案、再看
    # ``get_args()`` 会不会炸，才真正区分两种实现（双向验证时实测踩到）。
    rembg = panels["rembg"]
    rembg.reset_to_default()
    ok("rembg 的 area 下拉取值走 itemData（不是解析显示文本首字符）",
       rembg.get_args()["area"] == DEFAULTS["rembg"]["area"],
       f"get_args={rembg.get_args()['area']!r}")
    ok("rembg 的 type 下拉取值走 itemData",
       rembg.get_args()["type"] == DEFAULTS["rembg"]["type"],
       f"get_args={rembg.get_args()['type']!r}")
    # 改掉中文文案 → 取值不变（旧实现这里会 ValueError）
    _text = rembg.area.currentText()
    rembg.area.setItemText(rembg.area.currentIndex(), "一、左右分开")
    try:
        _got = rembg.get_args()["area"]
    except Exception as exc:  # noqa: BLE001 —— 旧实现在这里必炸
        _got = f"{type(exc).__name__}: {exc}"
    ok("改掉下拉的中文文案不影响取值（旧的首字符解析会炸）",
       _got == DEFAULTS["rembg"]["area"], f"改文案后取值={_got!r}")
    rembg.area.setItemText(rembg.area.currentIndex(), _text)

    # 回填历史值（含缺键）都走默认表
    rembg._apply_args_guarded({"area": 4, "type": 3})
    ok("rembg 回填 area=4 / type=3",
       rembg.get_args()["area"] == 4 and rembg.get_args()["type"] == 3,
       f"{rembg.get_args()['area']}/{rembg.get_args()['type']}")
    rembg._apply_args_guarded({})
    ok("rembg 空回填回到默认 area=1 / type=1",
       rembg.get_args()["area"] == 1 and rembg.get_args()["type"] == 1,
       f"{rembg.get_args()['area']}/{rembg.get_args()['type']}")

    # ------------------------------------------------- 5. default_for 的语义
    # ⚠️ None 默认值陷阱：p.get(key, default) 在值是 None 时兜底永不生效；
    # 而 `p.get(key) or default` 会把合法的 False / 0 也吃掉。两者都不能用。
    from desktop.components.panels.base import default_for

    d = {"flag": True, "num": 7}
    ok("default_for：False 是合法值，不会被回落",
       default_for({"flag": False}, d, "flag") is False,
       f"{default_for({'flag': False}, d, 'flag')!r}")
    ok("default_for：0 是合法值，不会被回落",
       default_for({"num": 0}, d, "num") == 0,
       f"{default_for({'num': 0}, d, 'num')!r}")
    ok("default_for：None 视作没填，回落默认",
       default_for({"num": None}, d, "num") == 7,
       f"{default_for({'num': None}, d, 'num')!r}")
    ok("default_for：缺键回落默认",
       default_for({}, d, "num") == 7, f"{default_for({}, d, 'num')!r}")

    # print 面板的 _apply_args 用 default_for，而非裸 p.get
    src = inspect.getsource(print_panel._apply_args)
    ok("print 的 _apply_args 走 default_for（不是裸 get）",
       "default_for" in src and "default_for(" in src,
       "找不到 default_for( 调用")

    # ------------------------------------------------- 6. 文档默认值不漂移
    # `page_number_font_size` 的 12/18 两套值，源头就是
    # docs/functions/print.md 的参数表写着 12（面板照抄了文档，command_spec 是 18）。
    # 文档与代码各写一份数字 → 迟早再漂一次，所以这里钉住。
    # 只比对**数值型**键：字符串/None 在文档里有 `` `""` ``/``None`` 等写法，
    # 表示差异会造成假失败，而数值正是最容易悄悄改错的那类。
    from core.command_spec import PRINT_DEFAULTS as _cli_print

    doc = (_ROOT / "docs" / "functions" / "print.md").read_text(encoding="utf-8")
    table = {}
    for m in re.finditer(r"^\|\s*`([a-z_]+)`\s*\|\s*([^|]+?)\s*\|", doc, re.M):
        table[m.group(1)] = m.group(2).strip()
    drift = {}
    for key in ("title_font_size", "page_number_font_size",
                "page_number_start_page", "page_number_base"):
        doc_val = table.get(key)
        if doc_val is None:
            continue
        try:
            doc_num = int(doc_val)
        except ValueError:
            continue
        if doc_num != _cli_print[key]:
            drift[key] = (doc_num, _cli_print[key])
    ok("print.md 的数值默认值与 command_spec 一致（文档不再自己写一份）",
       not drift, f"漂移：{drift}")

    for panel in panels.values():
        panel.deleteLater()
