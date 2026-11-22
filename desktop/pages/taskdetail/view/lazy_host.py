# -*- coding: utf-8 -*-
"""阶段面板的惰性宿主 ``LazyPanelHost``（从原 ``view.py`` 拆出）。"""

from __future__ import annotations

from typing import Callable

from desktop.pages.taskdetail.view._qt import QVBoxLayout, QWidget


class LazyPanelHost(QWidget):
    """阶段面板的**惰性宿主**：真正被取用时才构造内部面板。

    为什么需要：详情页一进来停在第一步，而第四步的 ``PrintPanel`` 构造要
    ~128 ms（占整个详情页构造的**一半**——它那张参数表单 ``build_form`` 单项
    就 106 ms）。用户可能从头到尾都不点第四步，却每次进详情页都在为它买单。

    属性访问一律转发给内部面板，所以 ``control_stack.widget(3).get_args()``
    这类既有写法照常工作。Qt 自己的 ``sizeHint`` / ``paintEvent`` 等由 C++
    层调用，**不走 Python 的 __getattr__**，不会误触发构造。
    """

    def __init__(self, factory: Callable[[], QWidget], hooks=(), parent=None):
        """factory() 造真面板；hooks 是"内部面板构造完成"后的回调（接线用）。"""
        super().__init__(parent)
        self._factory = factory
        self._hooks = list(hooks)
        self._inner: QWidget | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._host_layout = layout

    def add_created_hook(self, fn) -> None:
        """注册"内部面板构造完成"回调；**若已构造则立刻执行**。

        ⚠️ 必须支持挂多个回调：视图层要接预览刷新、暂存层要接 param_edited，
        它们分属不同 Mixin，各自只知道自己的接线，不能互相覆盖。
        """
        if self._inner is not None:
            fn(self._inner)
        else:
            self._hooks.append(fn)

    def peek(self) -> QWidget | None:
        """**不触发构造**地看内部面板；尚未构造时返回 None。"""
        return self._inner

    @property
    def panel(self) -> QWidget:
        """内部真面板，首次访问时构造（并把挂着的回调全部执行一遍）。"""
        inner = self._inner
        if inner is None:
            inner = self._factory()
            self._inner = inner
            self._host_layout.addWidget(inner)
            hooks, self._hooks = self._hooks, []
            for hook in hooks:
                hook(inner)
        return inner

    def __getattr__(self, name: str):
        # 只有在类上找不到该属性时才会走到这里；_factory/_inner 都在 __dict__
        factory = self.__dict__.get("_factory")
        if factory is None:
            raise AttributeError(name)
        return getattr(self.panel, name)
