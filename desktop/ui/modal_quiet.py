# -*- coding: utf-8 -*-
"""模态弹窗期间的「宿主窗口点击静音」。

Qt 对**被模态阻塞的窗口**上的鼠标按下会 ``QApplication::beep()``——Windows
上就是一声"当"。实机表现（2026-11-15 用户报）：拼版页勾选多页后点
「批量删除」，确认框弹出的那一瞬间再点一下（连点、或习惯性的第二下确认），
那一下就落在弹窗**外面**的宿主窗口上：功能没坏，但"当当"响。

本模块按 **HWND** 精确判断一条鼠标消息落在谁身上：
``GetAncestor(hwnd, GA_ROOT)`` 命中「宿主顶层窗口」就吞掉这条消息——不响、
也不动作，与系统原生「禁用窗口」的行为一致。确认框自己是另一个顶层窗口，
不在名单里，点它照常生效。

⚠️ 只吞**按下/抬起/双击**，不动 ``WM_MOUSEMOVE``：移动照常，弹窗的悬停态
才不失灵。

⚠️ 非 Windows 平台（以及 offscreen 平台）根本不会有原生事件经过这里，
本模块等价于空操作，调用侧不必按平台分支。

用法（宿主窗口在整个弹窗生命周期内静音）::

    self._mute = HostClickMute(parent)
    # 弹窗 show 时
    self._mute.start()
    # 弹窗 hide / 关闭时（幂等，可重复调用）
    self._mute.stop()
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication
from PySide6.QtWidgets import QWidget

#: 需要静音的消息：左右键的按下 / 抬起 / 双击
_CLICK_MESSAGES = frozenset(
    (
        0x0201,  # WM_LBUTTONDOWN
        0x0202,  # WM_LBUTTONUP
        0x0203,  # WM_LBUTTONDBLCLK
        0x0204,  # WM_RBUTTONDOWN
        0x0205,  # WM_RBUTTONUP
        0x0206,  # WM_RBUTTONDBLCLK
    )
)

#: ``GetAncestor`` 的 ``gaFlags``：取最顶层祖先（顶层窗口）
_GA_ROOT = 2

#: 弹窗自己的原生事件类型（Qt 在 Windows 上只吐这两个）
_NATIVE_MSG_TYPES = (b"windows_generic_MSG", b"windows_dispatcher_MSG")


class _RootHwndMuteFilter(QAbstractNativeEventFilter):
    """吞掉落在 ``host_root`` 这棵窗口树上的鼠标点击。

    弹窗自己的点击是**另一个顶层窗口**，``GetAncestor`` 不命中，原样放行。
    """

    def __init__(self, host_root: int):
        super().__init__()
        self._host_root = int(host_root)
        self._msg_type = None
        self._user32 = None
        try:
            from ctypes import wintypes

            import ctypes

            self._msg_type = wintypes.MSG
            self._user32 = ctypes.windll.user32
        except Exception:
            # 拿不到 Win32 就没法判 hwnd：静默退化成空过滤器
            self._user32 = None

    def nativeEventFilter(self, eventType, message):  # noqa: N802
        if self._user32 is None or self._msg_type is None:
            return False
        try:
            # eventType 是 QByteArray：优先转 bytes（兼容旧版比较语义），
            # 转不动就用原对象比（QByteArray == bytes 也有重载）。
            try:
                kind = bytes(eventType)
            except Exception:
                kind = eventType
            if kind not in _NATIVE_MSG_TYPES:
                return False
            msg = self._msg_type.from_address(int(message))
        except Exception:
            return False
        if msg.message not in _CLICK_MESSAGES:
            return False
        try:
            root = int(self._user32.GetAncestor(int(msg.hWnd), _GA_ROOT))
        except Exception:
            return False
        return root == self._host_root


class HostClickMute:
    """让 ``host`` 这棵窗口在弹窗期间「点了不出声」。

    ``host`` 传哪个 widget 都行——内部取它的**顶层窗口**（真窗口）hwnd；
    宿主还没上屏（``winId()`` 拿不到）时 :meth:`start` 直接跳过，不报错。
    """

    def __init__(self, host: QWidget | None):
        self._host = host
        self._filter: _RootHwndMuteFilter | None = None
        self._app: QCoreApplication | None = None

    # ------------------------------------------------------------------ 开关
    def start(self) -> None:
        """开始静音（幂等；非 Windows / 无宿主时什么都不做）。"""
        if self._filter is not None or sys.platform != "win32":
            return
        if self._host is None:
            return
        app = QCoreApplication.instance()
        if app is None:
            return
        try:
            # window() 一定是顶层窗口；宿主本身就是顶层时返回它自己
            root = self._host.window() or self._host
            hwnd = int(root.winId())
        except Exception:
            return
        if not hwnd:
            return
        mute_filter = _RootHwndMuteFilter(hwnd)
        app.installNativeEventFilter(mute_filter)
        self._filter, self._app = mute_filter, app

    def stop(self) -> None:
        """结束静音（幂等，可重复调用）。"""
        if self._filter is None:
            return
        app, mute_filter = self._app, self._filter
        self._filter = None
        self._app = None
        if app is None:
            return
        try:
            app.removeNativeEventFilter(mute_filter)
        except Exception:
            pass
