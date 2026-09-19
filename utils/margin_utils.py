"""
File: utils/margin_utils.py
边距（margin）标准化：CSS 简写 → [上, 右, 下, 左]。

放在 utils 层（最低层）以便 core 与 functions 双方复用而不产生循环依赖：
    utils  ←  core  ←  functions / cli / desktop

支持（与 CSS margin 简写一致）:
    - 单值 "20"        → [20, 20, 20, 20]   （四边相等）
    - 两值 "20,30"     → [20, 30, 20, 30]   （上下, 左右）
    - 三值 "20,30,25"  → [20, 30, 25, 30]   （上, 左右, 下）
    - 四值 "20,30,25,35" → 原样              （上, 右, 下, 左）

本模块统一了原先散落在三处的实现（core.command_spec.normalize_margin、
utils.pdf_utils.parse_margins（已废弃）、desktop 面板 parse_margin4），消除了
「三值在 A 处补成四值、在 B 处静默丢弃、在 C 处报错」的行为分叉。
"""

from __future__ import annotations

from typing import Any, List, Optional

# 默认页边距（上右下左，mm）
DEFAULT_PAGE_MARGINS: List[float] = [20.0, 20.0, 20.0, 20.0]


def _to_float_list(value: Any) -> Optional[List[float]]:
    """把字符串/序列转成浮点列表；无法解析或为空时返回 None。"""
    if isinstance(value, str):
        # 容忍中文全角逗号与全角空格
        normalized = value.replace("，", ",").replace("　", " ").strip()
        if not normalized:
            return None
        parts = [p.strip() for p in normalized.split(",") if p.strip()]
        if not parts:
            return None
        try:
            return [float(p) for p in parts]
        except ValueError:
            return None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        try:
            return [float(v) for v in value]
        except (ValueError, TypeError):
            return None
    if isinstance(value, (int, float)):
        return [float(value)]
    return None


def normalize_margin(
    value: Any,
    default: Optional[List[float]] = None,
) -> Optional[List[float]]:
    """把 CSS 风格的 margin 简写标准化为 [上, 右, 下, 左] 四元素列表。

    参数:
        value: 待解析值，支持字符串 / 列表 / 元组 / 数字 / None。
        default: 值为空或非法时返回的兜底值（默认 None）。

    返回:
        四元素浮点列表，或 default。
    """
    if value is None:
        return default
    vals = _to_float_list(value)
    if vals is None:
        return default
    vals = vals[:4]
    if len(vals) == 1:
        return vals * 4
    if len(vals) == 2:
        return [vals[0], vals[1], vals[0], vals[1]]
    if len(vals) == 3:
        return [vals[0], vals[1], vals[2], vals[1]]
    return list(vals)


def format_margin(value: Any) -> str:
    """[上,右,下,左] → 最简 CSS 简写文本（与 normalize_margin 互逆）。

    四边相等 → 单值；上下/左右分别相等 → 两值；否则四值。
    空值返回空字符串。
    """
    vals = normalize_margin(value, default=None)
    if not vals:
        return ""
    ints = [int(float(v)) for v in vals]
    if ints[0] == ints[1] == ints[2] == ints[3]:
        return str(ints[0])
    if ints[0] == ints[2] and ints[1] == ints[3]:
        return f"{ints[0]},{ints[1]}"
    return ",".join(str(v) for v in ints)
