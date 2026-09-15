# -*- coding: utf-8 -*-
"""检测文本框（detect）阶段面板：本阶段只识别坐标，不生成文件。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout
from qfluentwidgets import BodyLabel, PrimaryPushButton

from desktop.components.panels.base import StagePanel
from desktop.ui.widgets import CONTROL_HEIGHT


class DetectPanel(StagePanel):
    """检测文本框阶段面板：仅识别坐标，不生成文件。

    YOLO 检测每张图的左右文本框坐标，供预览标注与去底色/裁剪使用；
    本阶段无表单参数，get_args 返回空字典，手动检测经信号触发。
    """

    stage = "detect"
    title = "检测文本框 (detect)"
    description = (
        "YOLO 检测每张图的左右文本框坐标（detect_left_right_boxes），"
        "用于预览标注与去底色/裁剪区域。本阶段只识别坐标，不生成文件。"
    )

    # 手动触发当前页检测（重负载：YOLO 子进程，不自动执行）
    detect_page_requested = Signal()

    def _build_form(self, form: QFormLayout) -> None:
        button = PrimaryPushButton("检测本页")
        # 与其它阶段面板的表单控件同高（qfluent 按钮默认只有 27px）
        button.setFixedHeight(CONTROL_HEIGHT)
        button.setToolTip("对当前选中的页面执行一次文本框检测（加载 YOLO 模型，耗时较长）")
        button.clicked.connect(self.detect_page_requested.emit)
        form.addRow(button)

    def get_args(self) -> dict:
        """返回空参数字典（detect 阶段无表单参数）。"""
        return {}

    def _apply_args(self, parameters: dict) -> None:
        pass
