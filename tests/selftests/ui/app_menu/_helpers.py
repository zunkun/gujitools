# -*- coding: utf-8 -*-
"""本包共享的常量、夹具与检查函数（由原大模块拆出）。"""

from __future__ import annotations

# -*- coding: utf-8 -*-

from __future__ import annotations

import time

from tests.selftests._context import ok, pump, wait_until

NAME = "app_menu"
TITLE = "顶部菜单栏（文件/独立功能/帮助）"
DEPENDS: list[str] = ["tasklist"]


def _menu_of(window, title: str):
    """按文案取顶级菜单——读 ``window.menu_bar``（**不是** ``window.menuBar()``）。

    ⚠️ 千万别在自测里碰 ``window.menuBar()``：``QMainWindow.menuBar()`` 会**就地
    造出**标题栏下面的一整行空菜单栏（这正是用户不要的"另起一行"），一碰就把
    被测窗口的布局改掉了。菜单栏现在的家在**标题栏里**（见 menu.py 的说明）。

    ⚠️ 顺带把菜单"还活着、还有内容"钉住：PySide6 里 ``addMenu("文案")`` 造出的
    ``QMenu`` 归 **Python** 持有，包装对象一被回收 C++ 菜单就销毁，而菜单栏上的
    action 只剩悬空指针——症状正是"菜单条还在、点开没有内容"（真踩过）。
    所以这里只认"**从菜单栏能读出动作**"这条路，而不是直接读 ``window.menus``。
    """
    for action in window.menu_bar.actions():
        if action.text() == title:
            menu = action.menu()
            assert menu is not None, f"菜单 {title} 没有实体"
            assert menu.actions(), f"菜单「{title}」读不到任何动作（QMenu 可能已被回收）"
            return menu
    raise AssertionError(f"没有找到顶级菜单：{title}")


def _action_of(menu, text: str):
    """按文案取菜单项（跳过分隔线）。"""
    for action in menu.actions():
        if not action.isSeparator() and action.text() == text:
            return action
    raise AssertionError(f"菜单里没有动作：{text}")


class _FakeDialog:
    """假弹窗实体：``exec()/show()`` 直接返回、``close()`` 只记一笔（自测里不弹真窗）。

    ⚠️ ``closed`` 要真的记下来：检查更新是"**先弹检查窗、结果回来再关掉它**"，
    "关没关"本身就是被断言的行为。
    """

    def __init__(self) -> None:
        self.closed = False

    def exec(self) -> int:
        return 1

    def show(self) -> None:
        return None

    def adjustSize(self) -> None:
        return None

    def done(self, _result: int = 0) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _DialogRecorder:
    """假弹窗外壳：替 ``menu.shell_dialog``，把每次调用的内容记下来。

    签名与真 ``shell_dialog`` 对齐（含关键字参数），并且**照真货的口径**从内容
    面板里读正文——``_MessagePanel`` / ``_AboutPanel`` 都是真控件，所以断言的是
    "用户真会看到什么"，而不是"传进去什么"。按钮文案/回调也一并记下（「换条线路」
    「取消」这类交互要能点）；``dialogs`` 留着创建出来的实体，好断言"关没关"。
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.dialogs: list[_FakeDialog] = []

    def __call__(self, title, panel, parent=None, **kwargs) -> _FakeDialog:
        from qfluentwidgets import BodyLabel

        labels = panel.findChildren(BodyLabel)
        self.calls.append({
            "title": title,
            "body": "\n".join(label.text() for label in labels),
            "ok_text": kwargs.get("ok_text"),
            "cancel_text": kwargs.get("cancel_text"),
            "show_cancel": kwargs.get("show_cancel"),
            "on_ok": kwargs.get("on_ok"),
            "on_cancel": kwargs.get("on_cancel"),
        })
        dialog = _FakeDialog()
        self.dialogs.append(dialog)
        return dialog


#: 仓库根（分片比原模块深一层，深两层，不能用 parents[2]/[3]）
import pathlib as _pathlib
ROOT = _pathlib.Path(__file__).resolve().parents[4]
