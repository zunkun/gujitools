# -*- coding: utf-8 -*-
"""纸张尺寸解析。"""

from __future__ import annotations

from typing import Tuple

from utils.page_layout.constants import PAPER_SIZES_MM


# ---------------------------------------------------------------- 纸张
def paper_size_mm(paper_size: str) -> Tuple[float, float]:
    """纸张名 → (短边, 长边) 毫米；非法纸张抛 ValueError。"""
    if not isinstance(paper_size, str):
        raise ValueError("paper_size 仅支持 A3、A4、A5、B5")
    key = paper_size.strip().lower()
    if key not in PAPER_SIZES_MM:
        raise ValueError(f"paper_size 仅支持 A3、A4、A5、B5，当前={paper_size}")
    return PAPER_SIZES_MM[key]


def print_page_size_mm(paper_size: str, orientation: str) -> Tuple[float, float]:
    """纸张 + 方向 → (页宽, 页高) 毫米。

    方向同时接受 fpdf 的 "P"/"L" 与 CLI/GUI 的 "portrait"/"landscape"：
    `functions/print.py` 在 execute() 里把后者映射成了前者再传给排版，
    两条路径都要能对上。
    """
    short_side, long_side = paper_size_mm(paper_size)
    flag = str(orientation or "landscape").strip().lower()
    if flag in ("l", "landscape"):
        return long_side, short_side
    return short_side, long_side
