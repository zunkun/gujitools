# -*- coding: utf-8 -*-
"""与输入框同高的下拉框（自 ``desktop/ui/widgets.py`` 拆出）。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from qfluentwidgets import ComboBox

from .constants import CONTROL_HEIGHT

def combo_box(
    items: Iterable[str | Sequence[Any]] | None = None,
    width: int | None = None,
) -> ComboBox:
    """创建与输入框同高的下拉框（统一表单的行高节奏）。

    直接在表单里 ``ComboBox()`` 会比同列的 ``LineEdit``/``SafeSpinBox`` 矮
    6px（见 ``CONTROL_HEIGHT`` 的说明），所以下拉框一律用本函数建。

    ``items`` 传字符串序列时只填显示文案；传 ``(文案, 值)`` 二元组序列时
    值写进 ``itemData``，读出用 ``currentData()``。``width`` 非空则固定宽度
    （用于节点行这类需要横向对齐的窄列）。
    """

    combo = ComboBox()
    combo.setFixedHeight(CONTROL_HEIGHT)
    # 它的 minimumSizeHint 偏大，而控制列最窄只有 340px：不放开会把表单
    # 撑出横向边界。表单字段列会自动拉伸，表格单元格内则按列宽收纳。
    combo.setMinimumWidth(0)
    for item in items or ():
        if isinstance(item, str):
            combo.addItem(item)
        else:
            label, value = item
            combo.addItem(label, userData=value)
    if width is not None:
        combo.setFixedWidth(width)
    return combo
