# -*- coding: utf-8 -*-
"""界面字体：统一的字体族解析与构造。

从 `desktop/ui/widgets.py` 拆出（见 docs/dev/refactor-modularity.md §3.B）。
`ui_font` 跟「控件」没什么关系，却被日志面板、分段开关等多处共用；留在
widgets 里会让 `segmented_toggle` 反向 import widgets，形成循环导入。
"""

from __future__ import annotations

from PySide6.QtGui import QFont

from desktop.ui import theme as T

_FONT_FAMILY: str | None = None


def ui_font(size: int = T.SIZE_BODY, bold: bool = False) -> QFont:
    """统一的界面字体（族名 + 像素字号）。

    族名走 ``resolve_font_family()`` 解析出的系统实际字体，与
    ``apply_app_style`` 给整个应用设置的字体保持一致；否则在没有
    ``Microsoft YaHei UI`` 的机器上，这些控件会各自回退到默认字体，
    和应用其它文字对不上。
    """
    global _FONT_FAMILY
    if _FONT_FAMILY is None:
        from desktop.ui.style import resolve_font_family

        _FONT_FAMILY = resolve_font_family()
    font = QFont(_FONT_FAMILY)
    font.setPixelSize(size)
    font.setBold(bold)
    return font
