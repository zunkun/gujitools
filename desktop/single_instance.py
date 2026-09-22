# -*- coding: utf-8 -*-
"""desktop 单例守卫：**同一个构建**同时只允许一个 GUI 实例。

用户原则：开发版（源码 / hupper 启动）与正式版（安装的 guji-desktop.exe）是
两个不同的程序，**可以同时存在**——所以互斥体按「构建身份」区分：

- 同一个构建第二次启动 → 检测到已有实例，把已有窗口带到前台、自己退出；
- 两个构建各跑各的，互不阻拦（即便它们共用 `~/Documents/guji` 数据区）。

实现（win32）：
- **互斥体**判定"是否已有本构建实例"：`CreateMutexW`，若 `GetLastError` 返回
  ERROR_ALREADY_EXISTS 则说明已有。句柄必须**存进模块级变量**——句柄被垃圾回收
  互斥体就销毁了，守卫随之失效（活到进程退出，正合需求）。
- **把已有窗口带到前台**：`FindWindowW` 按窗口标题找，`ShowWindow(SW_RESTORE)`
  + `SetForegroundWindow`。不做跨进程消息通道，够用且零依赖。

⚠️ 仅 win32 生效；其它平台直接放行（本项目只在 Windows 打包发行）。
"""

from __future__ import annotations

import hashlib
import sys

_MUTEX_PREFIX = "Local\\GujiZhiZuo-Desktop-"
_ERROR_ALREADY_EXISTS = 183
_SW_RESTORE = 9

#: 持有的互斥体句柄。**必须**被模块级引用持有：句柄一旦被回收，互斥体即销毁，
#: 单例守卫随之失效（直到进程退出才释放，正合需求）。
_held_mutex: object | None = None


def mutex_name(identity: str) -> str:
    """由构建身份推出互斥体名。

    identity 用 **desktop 包目录**（`desktop.utils.files.package_dir()`）：
    源码是 `D:\\...\\desktop`，打包是 `...\\guji\\_internal\\desktop`——同一构建
    稳定不变，两个构建互不相同。
    """
    suffix = hashlib.md5(identity.encode("utf-8")).hexdigest()[:10]
    return f"{_MUTEX_PREFIX}{suffix}"


def acquire(identity: str) -> bool:
    """尝试持有本构建的单例互斥体。False = 已有本构建实例（调用方应退出）。"""
    global _held_mutex
    if sys.platform != "win32":
        return True  # 非 Windows 打包目标：不做限制
    if _held_mutex is not None:
        return True  # 本进程已持有（理论上只会调一次）

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [
        wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR,
    ]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    handle = kernel32.CreateMutexW(None, False, mutex_name(identity))
    if not handle:
        # 连句柄都拿不到：宁可拒绝启动，也不能放第二个实例进来
        return False
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _held_mutex = handle
    return True


def activate_existing_window(title: str) -> bool:
    """把已有实例的窗口恢复并带到前台。找不到（返回 False）也不影响退出。"""
    if sys.platform != "win32":
        return False

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, wintypes.INT]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]

    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, _SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    return True
