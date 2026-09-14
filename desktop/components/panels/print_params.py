# -*- coding: utf-8 -*-
"""生成 PDF（print）阶段的参数定义与解析/序列化纯函数。

表单 UI 见 print_form.py，面板状态见 print_panel.py。
"""

from __future__ import annotations

from PySide6.QtGui import QColor

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

# 不允许在表单中配置的键（系统管理）
EXCLUDED_KEYS = ("input", "output", "workers", "clean", "_outpath")

PAPER_SIZES = ["A3", "A4", "A5", "B5"]
# 下拉项：(中文显示, 实际参数值)
DIRECTIONS = [("横版", "landscape"), ("竖版", "portrait")]
POSITIONS = [("上边", "top"), ("下边", "bottom")]
TEXT_ORIENTATIONS = [("竖排", "vertical"), ("横排", "horizontal")]
SIDES = [("双面", "both"), ("左页", "left"), ("右页", "right")]


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
