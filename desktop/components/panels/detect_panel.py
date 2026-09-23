# -*- coding: utf-8 -*-
"""检测文本框（detect）阶段面板：本阶段只识别坐标，不生成文件。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout
from qfluentwidgets import CheckBox, PrimaryPushButton

from desktop.components.panels.base import StagePanel
from desktop.ui.widgets import CONTROL_HEIGHT


class DetectPanel(StagePanel):
    """检测文本框阶段面板：仅识别坐标，不生成文件。

    YOLO 检测每张图的左右文本框坐标，供预览标注与去底色/裁剪使用；
    本阶段无表单参数，get_args 返回空字典，手动检测经信号触发。

    「整页模式」是第三步 area=4 的入口开关：勾选后整页即唯一文本框，
    **不加载也不调用 YOLO**，预览里框画在页面边界，仍可手动拖动/重画。
    """

    stage = "detect"
    title = "检测文本框"
    description = (
        "自动检测每张图的左右文本框坐标，"
        "用于预览标注与去底色/裁剪区域。本阶段只识别坐标，不生成文件。"
        "普通文档/检测失败可勾选「整页模式」，整页作为一个文本框，跳过检测。"
    )

    # 手动触发当前页检测（重负载：检测子进程，不自动执行）
    detect_page_requested = Signal()
    # 整页模式开关（等价于第三步的「整页」区域）
    whole_page_toggled = Signal(bool)

    def _build_form(self, form: QFormLayout) -> None:
        self.whole_page = CheckBox("整页模式：不做检测")
        self.whole_page.setToolTip(
            "整页作为一个文本框（与第三步「区域模式」里的整页是同一件事）："
            "跳过检测，预览里的框画在页面边界，可继续拖动/重画。"
            "适合普通文档或古籍检测失败时"
        )
        self.whole_page.toggled.connect(self.whole_page_toggled.emit)
        form.addRow(self.whole_page)

        button = PrimaryPushButton("检测本页")
        # 与其它阶段面板的表单控件同高（qfluent 按钮默认只有 27px）
        button.setFixedHeight(CONTROL_HEIGHT)
        button.setToolTip("对当前选中的页面执行一次文本框检测（需加载检测模型，耗时较长）")
        button.clicked.connect(self.detect_page_requested.emit)
        form.addRow(button)

    def get_args(self) -> dict:
        """返回空参数字典（detect 阶段无表单参数）。

        整页模式不在这里上报：area 归第三步 rembg 面板所有，本开关只负责
        把 area 切到 4 / 切回 1（见宿主的 _set_whole_page_mode）。
        """
        return {}

    def _apply_args(self, parameters: dict) -> None:
        pass

    def set_whole_page(self, on: bool) -> None:
        """外部（第三步 area）回填勾选状态；blockSignals 避免回抛造成循环。"""
        if self.whole_page.isChecked() == bool(on):
            return
        self.whole_page.blockSignals(True)
        self.whole_page.setChecked(bool(on))
        self.whole_page.blockSignals(False)
