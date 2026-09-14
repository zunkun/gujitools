# -*- coding: utf-8 -*-
"""阶段控制面板集合（按 STAGES 顺序注册）。"""

from desktop.components.panels.base import StagePanel
from desktop.components.panels.detect_panel import DetectPanel
from desktop.components.panels.extract_panel import ExtractPanel
from desktop.components.panels.print_panel import PrintPanel
from desktop.components.panels.rembg_panel import RembgPanel

PANEL_CLASSES = (ExtractPanel, DetectPanel, RembgPanel, PrintPanel)

__all__ = [
    "StagePanel",
    "ExtractPanel",
    "DetectPanel",
    "RembgPanel",
    "PrintPanel",
    "PANEL_CLASSES",
]
