# -*- coding: utf-8 -*-
"""拼版控制器的模块级小工具。"""

from __future__ import annotations


def _rect_of(entry: dict) -> list[float] | None:
    """条目的**逐页坐标**（mm）；没有就 ``None``。

    只服务"清单结构变了没有"的比对（见 ``_refresh_print_source``）：文件顺序一样
    但某页的坐标被换掉/失效时，也得走整列重建把新坐标灌进去。
    """
    rect = (entry or {}).get("rect")
    if rect is None:
        return None
    try:
        return [float(value) for value in rect[:4]]
    except (TypeError, ValueError):
        return None
