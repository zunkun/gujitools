# -*- coding: utf-8 -*-
"""任务详情页的 detect 检测控制器（子包入口，只做重导出）。

框坐标持久化在任务目录的 `boxes.json`（键为页面 stem）：
- 选中图片时优先读已有结果（命中则不再检测，手动框不被自动结果覆盖）；
- 子进程检测到的框写回（origin=auto）；
- 预览区拖动线框后写回（origin=manual），全程不生成新文件。

2026-11-22 起由单文件拆成子包（原因：原文件 1417 行），对外导入路径
``desktop.pages.taskdetail.detect`` 与名字完全不变。
"""

from __future__ import annotations

from desktop.components.yolo_export_dialog import ask_yolo_export
from desktop.pages.taskdetail.detect.box_cache import DetectBoxCacheMixin
from desktop.pages.taskdetail.detect.boxes import DetectBoxesMixin
from desktop.pages.taskdetail.detect.cache import VersionedBoxCache
from desktop.pages.taskdetail.detect.constants import ORIGIN_SUFFIX
from desktop.pages.taskdetail.detect.modes import DetectModesMixin
from desktop.pages.taskdetail.detect.process import DetectProcessMixin
from desktop.pages.taskdetail.detect.stats import DetectStatsMixin
from desktop.pages.taskdetail.detect.yolo import YoloExportMixin

__all__ = [
    "ORIGIN_SUFFIX",
    "VersionedBoxCache",
    "DetectMixin",
    "ask_yolo_export",
]


class DetectMixin(
    DetectBoxesMixin,
    DetectBoxCacheMixin,
    DetectStatsMixin,
    DetectModesMixin,
    DetectProcessMixin,
    YoloExportMixin,
):
    """依赖宿主页面提供的属性：store/task_id、detect_viewer、log_view、
    detect_process/detect_cache、current_stage()。"""
