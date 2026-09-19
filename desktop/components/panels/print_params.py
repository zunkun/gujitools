# -*- coding: utf-8 -*-
"""生成 PDF（print）阶段的参数解析/序列化纯函数。

⚠️ 默认值（``DEFAULT_PARAMS``）与下拉候选表的**唯一事实来源**已上移到
``panels/params_spec.py``（各阶段共用一张表，避免同一参数在「控件初值 /
``_apply_args`` 兜底 / ``reset_to_default``」三处各写一遍而漂移）。本模块只保留
print 专用的解析/序列化纯函数，并把 ``DEFAULT_PARAMS`` 重新导出以兼容既有导入。

表单 UI 见 print_form.py，面板状态见 print_panel.py。
"""

from __future__ import annotations

from PySide6.QtGui import QColor

from desktop.components.panels.params_spec import (
    DIRECTIONS,
    EXCLUDED_KEYS,
    PAPER_SIZES,
    POSITIONS,
    PRINT_DEFAULTS,
    SIDES,
    TEXT_ORIENTATIONS,
)

__all__ = [
    "DEFAULT_PARAMS", "DIRECTIONS", "EXCLUDED_KEYS", "PAPER_SIZES",
    "POSITIONS", "SIDES", "TEXT_ORIENTATIONS",
    "parse_color", "parse_margin4", "margin_to_text",
    "skip_pages_to_text", "text_to_skip_pages",
]

# 桌面表单的默认参数（= params_spec.PRINT_DEFAULTS）。
# ⚠️ 这里**故意不放** title_position / title_orientation /
# page_number_position / page_number_orientation：第四步表单已不再提供
# 这四项（标题恒上、页码恒下、两者恒竖排，见 PrintFormMixin.FIXED_TEXT_LAYOUT）。
# 留着它们等于「恢复默认」时把四个界面外的值写进参数；不放，`get_args()`
# 才会真正走固定表。老任务配置里带这些键时，回填会原样回显
# （`_fixed_layout_echo`），不会被静默改成固定值——两边合起来才是
# 「界面不管、参数不动」。
#
# 注：params_spec.PRINT_DEFAULTS 引用的是 core.command_spec.PRINT_FORM_DEFAULTS，
# 其中确实带这四个键（命令行语义需要）。因此这里按**表单可见键**挑出一份，
# 既保住上面那条前提，也让「界面不管」的语义不被默认表灌回。
_FORM_KEYS = (
    "title_text", "pdf_name", "paper_size", "orientation",
    "page_margins", "left_page_margins", "right_page_margins",
    "title_printing", "title_font_size", "title_color",
    "title_margins", "title_switch_nodes",
    "page_number_printing", "page_number_start_page",
    "page_number_end_page", "page_number_base",
    "page_number_font_size", "page_number_color", "page_number_margins",
    "skip_pages", "annotate_margins",
)
DEFAULT_PARAMS: dict = {k: v for k, v in PRINT_DEFAULTS.items() if k in _FORM_KEYS}
assert set(DEFAULT_PARAMS) == set(_FORM_KEYS), "PRINT_DEFAULTS 缺少表单可见键"
del _FORM_KEYS


def parse_color(text: str) -> QColor:
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


def parse_margin4(text: str):
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


def margin_to_text(value) -> str:
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


def skip_pages_to_text(value) -> str:
    """skip_pages 参数 → 表单文本（逗号分隔的页名）。"""
    if isinstance(value, (list, tuple)):
        return ",".join(str(s) for s in value)
    return str(value or "")


def text_to_skip_pages(text: str) -> list[str]:
    """表单文本 → skip_pages 参数。"""
    return [
        p.strip()
        for p in str(text).replace("，", ",").split(",")
        if p.strip()
    ]
