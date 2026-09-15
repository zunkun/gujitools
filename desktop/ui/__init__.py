# -*- coding: utf-8 -*-
"""界面层公共模块：设计令牌（theme）、应用样式（style）、基础视觉控件（widgets）。

页面与组件统一从这里取色值/间距/控件，不要再在各处写魔法数字与硬编码色值。
"""

from desktop.ui import theme
from desktop.ui.style import apply_app_style, resolve_font_family
from desktop.ui.widgets import (
    CONTROL_HEIGHT, Card, Divider, EmptyState, PageHeader, Pill, ProgressLine,
    SectionTitle, SegmentedToggle, StatusChip, apply_to, combo_box, icon_pixmap,
    ui_font,
)

__all__ = [
    "theme",
    "apply_app_style",
    "resolve_font_family",
    "CONTROL_HEIGHT",
    "Card",
    "Divider",
    "EmptyState",
    "PageHeader",
    "Pill",
    "ProgressLine",
    "SectionTitle",
    "SegmentedToggle",
    "StatusChip",
    "apply_to",
    "combo_box",
    "icon_pixmap",
    "ui_font",
]
