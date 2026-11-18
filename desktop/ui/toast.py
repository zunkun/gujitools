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

#: 当前**还挂着**的 toast 去重表：key = (parent 的 id, 标题, 内容)。
#: 同一条提示还活着的时候再触发一次（连点、双通道各弹一遍）就不再堆一条
#: ——重复的「还没有选择子任务」叠两层只会吵（用户 2026-11-18 报的现象）。
_LIVE: dict[tuple[int, str, str], InfoBar] = {}


def _bar_alive(bar: InfoBar) -> bool:
    """toast 是否还活着：只判 C++ 对象在不在（close 时 ``closedSignal`` 已把
    条目摘掉，不需要也不该用 ``isVisible()`` 判——宿主窗口没 show 的场景
    （离屏自测/隐藏页面）``isVisible()`` 恒假，会把活 toast 误判成已消失）。
    """
    try:
        bar.objectName()
    except RuntimeError:
        return False
    return True


def show_toast(
    parent: QWidget, kind: str, title: str, content: str
) -> None:
    """在 ``parent`` 右下角弹一条 InfoBar。

    ``kind``：``InfoBar`` 的工厂方法名（info/success/warning/error），
    未知值回落为 info。

    ⚠️ **同键去重**：同 parent + 同标题 + 同内容的 toast 还没消失时，再次
    调用直接跳过（不再叠一条）。关闭时（``closedSignal``）从去重表摘除，
    之后同样的话可以正常再弹。
    """
    factory = getattr(InfoBar, kind, InfoBar.info)
    key = (id(parent), str(title), str(content))
    old = _LIVE.get(key)
    if old is not None:
        if _bar_alive(old):
            return          # 同一条还挂着：不堆第二条
        _LIVE.pop(key, None)
    bar = factory(
        title=title,
        content=content,
        parent=parent,
        position=POSITION,
        duration=DURATION_MS,
    )
    bar.closedSignal.connect(lambda *_, k=key: _LIVE.pop(k, None))
    _LIVE[key] = bar
