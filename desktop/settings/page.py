# -*- coding: utf-8 -*-
"""设置页（左侧栏底部「设置」进的那一页）。

用户 2026-10-16：

> 1. 左侧栏开启设置菜单；2. 菜单里面有「启用开发者模式」胶囊；
>    开发者模式下有各种选项（目前只有 a. 是否启用YOLO标注）。

界面照 qfluentwidgets 的设置页范式（用户给的 SettingCard 参考）：一张
``SettingCard`` = 一行「图标 + 标题 + 说明 + 右侧控件」，多张归进一个
``SettingCardGroup``。开关用 ``SwitchSettingCard``，它**直接绑配置项**
（``configItem=…``）——勾选即落盘，本页不自己存值。

⚠️ **「启用YOLO标注」是开发者模式的下级选项**：开发者模式关着时它整张卡
藏起来（``SettingCardGroup`` 的 ``ExpandLayout`` 会跳过隐藏项，但**组自己的
高度**是算好的，所以藏完必须补一次 ``adjustSize()``，否则卡片下方留一块
空白）。
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    FluentIcon as FIF,
    SettingCardGroup,
    SmoothScrollArea,
    SwitchSettingCard,
)

from desktop.services.detect_export import (
    YOLO_IMAGES_DIRNAME,
    YOLO_LABELS_DIRNAME,
)
from desktop.settings.config import AppConfig, app_config
from desktop.ui import theme as T
from desktop.ui.widgets import PageHeader, apply_to
from utils.box_geometry import YOLO_CLASS_NAMES


class SettingsPage(QWidget):
    """设置页：目前只有「开发者模式」与它下面的开发选项。

    ⚠️ 页面**没有**自己的导航条目概念——它由壳层（``desktop/shell.py``）
    挂在导航栏底部并切页，与各步骤的独立模块页是两回事（模块页来自
    ``MODULES`` 注册表，那一条链不许被本页污染）。
    """

    TITLE = "设置"
    SUBTITLE = "开发者模式与训练/标注相关选项"

    def __init__(self, parent=None):
        """建页头 + 设置卡片组（配置项绑在卡片上，本页不另存值）。"""
        super().__init__(parent)
        self.cfg: AppConfig = app_config()

        root = QVBoxLayout(self)
        root.setContentsMargins(T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG)
        root.setSpacing(T.SPACE_MD)
        self.header = PageHeader(self.TITLE, self.SUBTITLE)
        root.addWidget(self.header)

        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # 底色交给窗口/页面根（见 desktop/ui/style.py 的全局 QSS）：不关掉
        # 视口底色的话，这一页会在卡片区外露出一块与其它页不同的灰。
        scroll.enableTransparentBackground()

        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(T.SPACE_MD)

        self.group = SettingCardGroup("开发者", container)
        self.dev_card = SwitchSettingCard(
            FIF.DEVELOPER_TOOLS,
            "启用开发者模式",
            "打开后才显示开发/训练相关的功能选项（普通使用请保持关闭）",
            configItem=self.cfg.developerMode,
            parent=self.group,
        )
        self.yolo_card = SwitchSettingCard(
            FIF.TAG,
            "启用YOLO标注",
            "在「检测文本框」的右栏底部显示「导出YOLO标注」按钮",
            configItem=self.cfg.yoloAnnotation,
            parent=self.group,
        )
        self.group.addSettingCards([self.dev_card, self.yolo_card])
        column.addWidget(self.group)

        # 文案里的目录与类别顺序都取自**唯一来源**（不在这里重抄字符串）
        self.yolo_hint = CaptionLabel(
            "打开「启用YOLO标注」后，「检测文本框」右栏底部会多出「导出YOLO标注」："
            "点它弹窗填名称（b1 → b1-1.jpg / b1-1.txt，序号按页序）并选导出目录，"
            "导出到 <导出目录>/<名称>/"
            + YOLO_IMAGES_DIRNAME
            + "/ 与 "
            + YOLO_LABELS_DIRNAME
            + "/；类别顺序为 "
            + "、".join(YOLO_CLASS_NAMES)
            + "（左框与右框都算半幅）；没有框的页面写空标签当负样本。"
        )
        self.yolo_hint.setWordWrap(True)
        apply_to(self.yolo_hint, T.SIZE_CAPTION, color=T.INK_FAINT)
        column.addWidget(self.yolo_hint)
        column.addStretch(1)

        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        # 开发者模式变化 → YOLO 卡片跟着显隐（配置项是长期存活的 QObject，
        # 本页被销毁时 Qt 会自动断开，不必手动收）
        self.cfg.developerMode.valueChanged.connect(self.sync_dev_options)
        self.sync_dev_options()

    def sync_dev_options(self, *_args) -> None:
        """按「开发者模式」开关显隐下级选项（并重算卡片组高度）。"""
        shown = bool(self.cfg.developerMode.value)
        self.yolo_card.setVisible(shown)
        self.yolo_hint.setVisible(shown)
        # ⚠️ 必须补这一句：SettingCardGroup 的高度是 adjustSize() 时算好的，
        #    只 setVisible 的话组还留着藏起来那张卡的高度（下方一块空白）。
        self.group.adjustSize()


__all__ = ["SettingsPage"]
