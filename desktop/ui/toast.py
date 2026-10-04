# -*- coding: utf-8 -*-
"""全局统一的 InfoBar 弹出工厂。

桌面端两套页面宿主——任务流程页（``pages/taskdetail``）与独立任务页
（``modules``）——都会弹「右下角、2.5 秒自动消失」的 qfluentwidgets InfoBar。
此前 ``TaskDetailPage._toast`` 与 ``ModulePage.toast`` 各写了一份逐字相同的
工厂，这里收成唯一实现：位置、时长、``kind`` 到 InfoBar 工厂方法的映射
只在这一处调，两边只是薄薄一层转发。

``kind`` 取 ``InfoBar`` 的类方法名（info/success/warning/error）；未知
``kind`` 兜底为 ``info``，调用侧不必先校验。
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget
from qfluentwidgets import InfoBar, InfoBarPosition

#: 弹出位置与停留时长：全桌面端统一口径，不要在调用侧自定
POSITION = InfoBarPosition.BOTTOM_RIGHT
DURATION_MS = 2500


def show_toast(
    parent: QWidget, kind: str, title: str, content: str
) -> None:
    """在 ``parent`` 右下角弹一条 InfoBar。

    ``kind``：``InfoBar`` 的工厂方法名（info/success/warning/error），
    未知值回落为 info。
    """
    factory = getattr(InfoBar, kind, InfoBar.info)
    factory(
        title=title,
        content=content,
        parent=parent,
        position=POSITION,
        duration=DURATION_MS,
    )
