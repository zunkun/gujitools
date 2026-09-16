"""
File: utils/color_utils.py
颜色解析：'r,g,b' 字符串 / 元组 → 整数三元组。

放在 utils 层（最低层）以便 core 与 functions 双方复用而不产生循环依赖：
    utils  ←  core  ←  functions / cli / desktop

设计取舍：非法输入**一律抛 ValueError**，不静默降级为黑色。
静默降级会让用户把 "0,0" 写错时只看到一张黑字 PDF 却毫无提示；
而超范围分量（如 300）写进 PDF 会产生损坏输出。
"""

from __future__ import annotations

from typing import Any, Tuple


def parse_color(value: Any) -> Tuple[int, int, int]:
    """解析颜色为 (r, g, b) 整数元组，分量取值域 [0, 255]。

    接受:
        - 字符串 "r,g,b"：半角或全角逗号、全角空格均可；
        - 列表 / 元组 (r, g, b)。

    异常:
        ValueError: 分量数不为 3、含非数字、或超出 0~255 范围。
    """
    if isinstance(value, (tuple, list)):
        parts = list(value)
    elif isinstance(value, str):
        # 容忍中文全角逗号与全角空格（中文输入法下极易误输）
        normalized = value.replace("，", ",").replace("　", " ")
        parts = [p.strip() for p in normalized.split(",") if p.strip()]
    else:
        raise ValueError(f"颜色格式应为 r,g,b（0~255）或三元组，当前：{value!r}")

    if len(parts) != 3:
        raise ValueError(f"颜色格式应为 r,g,b（0~255），当前：{value!r}")
    try:
        rgb = tuple(int(p) for p in parts)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"颜色必须为数字：{value!r}") from exc
    if not all(0 <= c <= 255 for c in rgb):
        raise ValueError(f"颜色取值范围 0~255：{value!r}")
    return rgb  # type: ignore[return-value]


def format_color(rgb: Tuple[int, int, int]) -> str:
    """整数三元组 → "r,g,b" 文本（与 parse_color 互逆）。"""
    r, g, b = rgb
    return f"{int(r)},{int(g)},{int(b)}"
