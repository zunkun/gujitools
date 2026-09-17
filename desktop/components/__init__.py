# -*- coding: utf-8 -*-
"""可复用 UI 组件：步骤条、任务表格、查看器、阶段面板。"""

from desktop.components.pagination import (
    DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS, Pager, Pagination,
)
from desktop.components.panels import PANEL_CLASSES
from desktop.components.step_bar import StepBar
from desktop.components.task_table import TaskTable
from desktop.components.viewers import (
    ImageView,
    ImageViewerWidget,
    PdfViewerWidget,
    RembgPreviewWidget,
    ThumbStrip,
)

__all__ = [
    "PANEL_CLASSES",
    "Pager",
    "Pagination",
    "PAGE_SIZE_OPTIONS",
    "DEFAULT_PAGE_SIZE",
    "StepBar",
    "TaskTable",
    "ImageView",
    "ImageViewerWidget",
    "PdfViewerWidget",
    "RembgPreviewWidget",
    "ThumbStrip",
]
