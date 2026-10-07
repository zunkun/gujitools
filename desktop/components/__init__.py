# -*- coding: utf-8 -*-
"""可复用 UI 组件：步骤条、任务表格、查看器、阶段面板。

⚠️ **一律惰性导出**（PEP 562 模块级 ``__getattr__``）。

本包同时装着两类东西：

- **列表页要用的**：``TaskTable`` / ``Pagination`` / ``StepBar``；
- **详情页专属的**：四个阶段面板、PDF/图片/去底色/打印预览、第四步版面编辑画布。

Python 在导入子模块前一定会先执行父包的 ``__init__``，所以只要有人写
``from desktop.components.pagination import Pager``，本文件就会整体跑一遍、
把详情页那一大批控件全拉进启动——实测启动期因此多加载 30+ 个模块。

改成惰性后 ``from desktop.components import TaskTable`` 这类写法照旧可用，
只是推迟到真正取用它的那一刻。
"""

from typing import TYPE_CHECKING

#: 惰性导出的**类型**侧声明（见模块 docstring）：类型检查器看不见 PEP 562 的
#: ``__getattr__``，缺这一段会把本包的导出全当成未定义。**只影响类型检查**，
#: 运行时的惰性加载照旧（启动期不会因此多加载组件）。
if TYPE_CHECKING:
    from desktop.components.detect_stats import DetectStatsWidget
    from desktop.components.pagination import (
        DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS, Pager, Pagination,
    )
    from desktop.components.panels import PANEL_CLASSES
    from desktop.components.progress_row import ProgressRow
    from desktop.components.step_bar import StepBar
    from desktop.components.task_table import TaskTable
    from desktop.components.viewers import (
        ImageView, ImageViewerWidget, PdfViewerWidget, RembgPreviewWidget,
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
    "DetectStatsWidget",
    "ImageView",
    "ImageViewerWidget",
    "ProgressRow",
    "PdfViewerWidget",
    "RembgPreviewWidget",
    "ThumbStrip",
]

_LAZY = {
    "Pager": ("desktop.components.pagination", "Pager"),
    "Pagination": ("desktop.components.pagination", "Pagination"),
    "PAGE_SIZE_OPTIONS": ("desktop.components.pagination", "PAGE_SIZE_OPTIONS"),
    "DEFAULT_PAGE_SIZE": ("desktop.components.pagination", "DEFAULT_PAGE_SIZE"),
    "StepBar": ("desktop.components.step_bar", "StepBar"),
    "TaskTable": ("desktop.components.task_table", "TaskTable"),
    "DetectStatsWidget": ("desktop.components.detect_stats", "DetectStatsWidget"),
    "PANEL_CLASSES": ("desktop.components.panels", "PANEL_CLASSES"),
    "ImageView": ("desktop.components.viewers", "ImageView"),
    "ImageViewerWidget": ("desktop.components.viewers", "ImageViewerWidget"),
    "ProgressRow": ("desktop.components.progress_row", "ProgressRow"),
    "PdfViewerWidget": ("desktop.components.viewers", "PdfViewerWidget"),
    "RembgPreviewWidget": ("desktop.components.viewers", "RembgPreviewWidget"),
    "ThumbStrip": ("desktop.components.viewers", "ThumbStrip"),
}


def __getattr__(name: str):
    """按需导入组件（PEP 562），并缓存进 globals 以免重复走导入系统。"""
    entry = _LAZY.get(name)
    if entry is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(entry[0]), entry[1])
    globals()[name] = value
    return value
