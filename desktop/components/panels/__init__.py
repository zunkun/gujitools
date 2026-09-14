# -*- coding: utf-8 -*-
"""阶段控制面板集合（按 STAGES 顺序注册）。"""

from .base import StagePanel
from .detect_panel import DetectPanel
from .extract_panel import ExtractPanel
from .print_panel import PrintPanel
from .rembg_panel import RembgPanel

PANEL_CLASSES = (ExtractPanel, DetectPanel, RembgPanel, PrintPanel)

__all__ = [
    "StagePanel",
    "ExtractPanel",
    "DetectPanel",
    "RembgPanel",
    "PrintPanel",
    "PANEL_CLASSES",
]
