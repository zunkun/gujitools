# -*- coding: utf-8 -*-
"""给无边框窗口补回原生「最小化/最大化」样式位，修两个 Windows 老毛病：

**现象**（2026-11-18 用户报障）：

1. 主窗口点「最小化」后，屏幕**左下角**（任务栏正上方）残留一小块窗口
   ——那是整个窗口被 Windows 缩成的"老式最小化瓦片"，自绘标题栏那一截
   被原样画在里面；
2. 最小化后**任务栏上没有这个窗口的按钮**，用户没法从任务栏把它还原。

**根因**：主窗口基类是 ``qframelesswindow.FramelessMainWindow``（Qt 的
``FramelessWindowHint``），Win32 层是 ``WS_POPUP`` 窗口，**没有
``WS_MINIMIZEBOX`` 样式位**。Windows 对没有 ``WS_MINIMIZEBOX`` 的窗口执行
最小化时不走"最小化动画 + 收进任务栏"那套现代流程，而是退回 Win 3.x 时代
的图标瓦片行为：把窗口缩小成一小块画在屏幕左下角。任务栏自然也就没有按钮
可点。``qframelesswindow`` 0.8.2 没有补回这个样式位（它的标题栏
``minBtn`` 直接调 ``showMinimized()``，原生层没有任何补偿）。

**修复**：窗口构造后用 ``SetWindowLongPtrW`` 给原生样式补上
``WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU``（MSDN 要求 MINIMIZEBOX
必须与 SYSMENU 同给），再 ``SetWindowPos(SWP_FRAMECHANGED)`` 让样式生效。
副作用全是正面的：最小化动画恢复、任务栏按钮正常、Win11 悬停最大化按钮的
Snap Layout 也能弹出来。

⚠️ 只在**真有原生 HWND** 时动手：离屏自测（``QT_QPA_PLATFORM=offscreen``）
拿到的 winId 不是真窗口句柄，``GetWindowLong`` 会失败——函数原样返回
``False``，绝不抛异常，调用点无脑一行即可。
"""

from __future__ import annotations

import ctypes
import sys

#: Win32 常量（winuser.h）；这里手抄而不是 import win32con——省 pywin32
#: 这个导入面，也方便在拿到 ctypes 的任何环境复用。
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_SYSMENU = 0x0008_0000
WS_MINIMIZEBOX = 0x0002_0000
WS_MAXIMIZEBOX = 0x0001_0000
WS_EX_APPWINDOW = 0x0004_0000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020


def _long_style_fns():
    """取 GetWindowLongPtrW/SetWindowLongPtrW；32 位 Python 没有.Ptr 后缀
    就退回 GetWindowLongW/SetWindowLongW。返回 (get_fn, set_fn)，拿不到
    （非 Windows）返回 (None, None)。⚠️ 必须把 restype/argtypes 设成
    ``c_ssize_t``：LONG_PTR 是指针宽度，默认的 c_int 在 64 位上会截断
    返回值（WS_POPUP = 0x80000000 那一位正是雷区）。"""
    if sys.platform != "win32":
        return None, None
    user32 = ctypes.windll.user32
    get_fn = getattr(user32, "GetWindowLongPtrW", None)
    set_fn = getattr(user32, "SetWindowLongPtrW", None)
    if get_fn is None or set_fn is None:  # 32 位 Python
        get_fn, set_fn = user32.GetWindowLongW, user32.SetWindowLongW
    get_fn.restype = ctypes.c_ssize_t
    get_fn.argtypes = [ctypes.c_ssize_t, ctypes.c_int]
    set_fn.restype = ctypes.c_ssize_t
    set_fn.argtypes = [ctypes.c_ssize_t, ctypes.c_int, ctypes.c_ssize_t]
    return get_fn, set_fn


def enable_native_minimize(window) -> bool:
    """给 ``window`` 的原生窗口补回最小化/最大化样式位。

    返回 ``True`` = 样式已具备（本来就够位或这次改成功）；
    返回 ``False`` = 环境（非 Windows / 离屏无真句柄 / API 失败）不允许改，
    调用方不需要也不能拿它做分支——宁可维持旧行为，也不抛异常打断启动。
    """
    try:
        hwnd = int(window.winId())
    except Exception:  # noqa: BLE001 —— 非 QWidget / C++ 对象已销毁
        return False
    if not hwnd:
        return False

    get_fn, set_fn = _long_style_fns()
    if get_fn is None:
        return False

    style = get_fn(hwnd, GWL_STYLE)
    if not style:  # 假句柄（离屏平台）读出 0：别把垃圾样式写回去
        return False

    want = WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU
    if style & want == want:
        return True  # 已经具备，无需再动

    if not set_fn(hwnd, GWL_STYLE, style | want):
        return False
    # 样式位要配一次 FRAMECHANGED 的 SetWindowPos 才真正生效（无尺寸变化）
    ctypes.windll.user32.SetWindowPos(
        hwnd, 0, 0, 0, 0, 0, SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
    )
    return True


def enable_taskbar_button(window) -> bool:
    """给**子窗口**（被主窗口拥有的对话框）补 ``WS_EX_APPWINDOW``。

    背景（2026-11-18 用户报障）：图片预览/编辑这类弹窗在 Win32 层是
    **owned window**——Windows 默认不给被拥有的窗口任务栏按钮，于是它们
    在任务栏上是隐形的：悬停主程序图标看不到它们，最小化后也没有按钮可点。
    补上 ``WS_EX_APPWINDOW`` 后强制获得自己的任务栏按钮（Alt+Tab 同步可见），
    且父子关系原样保留——居中、置顶、模态行为都不变。

    ⚠️ 必须在该窗口**最后一次 ``setWindowFlags`` 之后**调用：那会重建原生
    窗口，先打的样式位会丢。返回值语义与 :func:`enable_native_minimize` 一致。
    """
    try:
        hwnd = int(window.winId())
    except Exception:  # noqa: BLE001
        return False
    if not hwnd:
        return False

    get_fn, set_fn = _long_style_fns()
    if get_fn is None:
        return False

    ex_style = get_fn(hwnd, GWL_EXSTYLE)
    if not ex_style:  # 假句柄（离屏平台）：读不出真样式就别瞎写
        return False
    if ex_style & WS_EX_APPWINDOW:
        return True  # 已经具备
    if not set_fn(hwnd, GWL_EXSTYLE, ex_style | WS_EX_APPWINDOW):
        return False
    ctypes.windll.user32.SetWindowPos(
        hwnd, 0, 0, 0, 0, 0, SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
    )
    return True
