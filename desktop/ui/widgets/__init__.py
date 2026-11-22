# -*- coding: utf-8 -*-
"""基础视觉控件：卡片、分区标题、状态胶囊、空状态、页头。

统一用自绘而非样式表：Qt 的样式表引擎会在子树里有任何 ``setStyleSheet``
时把 QFrame 底色刷成白色，之前步骤条的卡片底就因此被整片盖掉过。自绘
（``paintEvent``）不受此影响，颜色完全可控，也不会污染子控件。

表单控件则相反，一律用 qfluentwidgets 的现成控件（它们自带绘制与焦点
动画），只把高度对齐到 ``CONTROL_HEIGHT``——见 ``combo_box()``。
"""

from __future__ import annotations

from desktop.ui.check_group import CheckBoxGroup
from desktop.ui.fonts import ui_font
from desktop.ui.segmented_toggle import SegmentedToggle

from .combobox import combo_box
from .constants import CONTROL_HEIGHT, HELP_BUBBLE_WIDTH, HELP_TOOLTIP_WIDTH
from .cursor import _ButtonCursorFilter, install_button_pointer_cursor
from .frames import Card, Divider, RedDashFrame, SurfacePanel, set_red_frame
from .header import PageHeader, PanelTitle
from .help import HelpButton, _WrapFlyoutView, _wrap_help_text
from .indicators import EmptyState, Pill, ProgressLine, StatusChip, icon_pixmap
from .text import SectionTitle, apply_to, bold_button, mark_input_entry

__all__ = [
    "CONTROL_HEIGHT",
    "Card",
    "CheckBoxGroup",
    "Divider",
    "EmptyState",
    "HelpButton",
    "PageHeader",
    "PanelTitle",
    "Pill",
    "ProgressLine",
    "RedDashFrame",
    "SectionTitle",
    "SegmentedToggle",
    "StatusChip",
    "SurfacePanel",
    "apply_to",
    "bold_button",
    "combo_box",
    "icon_pixmap",
    "install_button_pointer_cursor",
    "set_red_frame",
    "ui_font",
]
