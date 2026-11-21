# -*- coding: utf-8 -*-
"""进程组收尾：Windows Job Object —— 父进程退出（含崩溃/被强杀）时带走全部子进程。

为什么需要（2026-11-21 现场）：拼版崩溃后任务管理器里留下 9 个孤儿——常驻
YOLO 服务（306MB）+ 8 个 multiprocessing 子进程，父进程早已退出。Windows
不像 Linux 会把孤儿挂到 init 下，父进程一死，子进程就是"没人管的野进程"：
不吃 CPU、也不自己退出，只能手工杀（重启程序还会复用那个旧服务）。

做法：建一个 Job Object，打开 ``KILL_ON_JOB_CLOSE`` 与 ``BREAKAWAY_OK``，
把**当前进程**放进去。之后所有子进程（``subprocess`` / ``multiprocessing`` /
PyInstaller bootloader 链）默认继承这个作业；本进程一退出——正常关闭、崩溃、
任务管理器结束进程都一样——作业句柄随进程关闭，系统把作业里的进程一并终止。

⚠️ **必须带 BREAKAWAY_OK**：有两类子进程是"要活过父进程"的——
   安装器（``desktop/ui/menu.py::_install_and_restart``）与「重启程序」
   （``desktop/settings/page.py::_restart_app``）。它们用
   :func:`breakaway_flags` 显式申请脱离作业；不给这个权限的话，"检查更新装
   新版"和"重启"会变成**静默失败**（新进程刚起来就被作业收走）。

⚠️ 句柄必须活到进程结束（模块级 ``_JOB_HANDLE`` 持有）：主动 CloseHandle 等于
   立刻杀死自己和所有子进程。

⚠️ 作业**匿名创建**（``CreateJobObjectW(None, None)``）：命名作业会被同机另一个
   实例的 ``CreateJobObject`` 复用同一个作业对象，那样关掉开发版会把正式版的
   子进程一起带走（两个构建是允许同时开的，见 ``desktop/single_instance.py``）。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

#: 作业关闭时终止作业内的所有进程
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
#: 允许子进程用 ``CREATE_BREAKAWAY_FROM_JOB`` 显式脱离（安装器/重启用）
_JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
#: ``SetInformationJobObject`` 的信息类：扩展限制信息
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
#: ``CreateProcess`` 的脱离标志（给要活过父进程的子进程用）
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

#: 已安装的作业句柄（**故意不关**，见模块说明）。0 / None = 未安装。
_JOB_HANDLE = None


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _kernel32():
    """取 kernel32（显式声明参数/返回类型：句柄是 64 位指针，默认 int 会被截断）。"""
    lib = ctypes.WinDLL("kernel32", use_last_error=True)
    lib.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    lib.CreateJobObjectW.restype = wintypes.HANDLE
    lib.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
    ]
    lib.SetInformationJobObject.restype = wintypes.BOOL
    lib.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    lib.AssignProcessToJobObject.restype = wintypes.BOOL
    lib.GetCurrentProcess.restype = wintypes.HANDLE
    lib.IsProcessInJob.argtypes = [
        wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL),
    ]
    lib.IsProcessInJob.restype = wintypes.BOOL
    return lib


def job_active() -> bool:
    """当前进程是否已装进本模块建的作业（``breakaway_flags`` 的判据）。"""
    return _JOB_HANDLE is not None


def kill_children_on_exit() -> bool:
    """把**当前进程**装进"关闭即杀子进程"的作业；成功返回 True。

    幂等：重复调用只回 True，不会再建一个作业。非 Windows 平台直接返回 False
    （POSIX 下没有这个问题，进程组由终端/服务管理器收）。

    失败也不影响程序运行——最坏情况回到旧行为（子进程可能残留），因此所有
    调用点都只记一行日志，绝不因为装不上作业而中断启动。
    """
    global _JOB_HANDLE
    if sys.platform != "win32":
        return False
    if _JOB_HANDLE is not None:
        return True
    try:
        kernel32 = _kernel32()
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            return False
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = (
            _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | _JOB_OBJECT_LIMIT_BREAKAWAY_OK
        )
        ok = kernel32.SetInformationJobObject(
            handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            return False
        if not kernel32.AssignProcessToJobObject(
            handle, kernel32.GetCurrentProcess()
        ):
            # 已经在一个不允许嵌套的作业里（Win7/某些启动器）：退回旧行为。
            # 句柄不再持有——留着反而会在退出时杀掉外层作业管不到的东西。
            return False
        _JOB_HANDLE = handle  # 故意不关：见模块说明
        return True
    except (OSError, AttributeError):
        return False


def breakaway_flags() -> int:
    """要脱离作业的子进程该叠加的 ``creationflags``（没装作业时返回 0）。

    用于"必须活过本进程"的子进程：安装器、重启出来的新实例。没装作业时返回
    0，调用点可以无脑 ``|=``，不必判断平台/状态。
    """
    return CREATE_BREAKAWAY_FROM_JOB if job_active() else 0


def detached_creationflags() -> int:
    """「脱离本进程也要活」的子进程的完整 ``creationflags``（Windows 专用）。

    口径与既有两类调用点一致：``DETACHED_PROCESS``（不共用控制台）+
    ``CREATE_NEW_PROCESS_GROUP``（不接父进程的 Ctrl+C / 信号），再叠加
    :func:`breakaway_flags` 让它逃出本进程的作业——否则安装器/新实例会在本
    进程退出的那一刻被作业一起收走。
    """
    return 0x00000008 | 0x00000200 | breakaway_flags()


def in_job() -> bool:
    """当前进程是否**处在任何**作业里（自测/排障用，不改变状态）。"""
    if sys.platform != "win32":
        return False
    try:
        kernel32 = _kernel32()
        result = wintypes.BOOL()
        if not kernel32.IsProcessInJob(
            kernel32.GetCurrentProcess(), None, ctypes.byref(result)
        ):
            return False
        return bool(result.value)
    except (OSError, AttributeError):
        return False


__all__ = [
    "CREATE_BREAKAWAY_FROM_JOB",
    "breakaway_flags",
    "detached_creationflags",
    "in_job",
    "job_active",
    "kill_children_on_exit",
]
