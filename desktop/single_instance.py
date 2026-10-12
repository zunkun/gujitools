# -*- coding: utf-8 -*-
"""desktop 单例守卫：**同一个构建**同时只允许一个 GUI 实例。

用户原则：开发版（源码 / hupper 启动）与正式版（安装的 guji-desktop.exe）是
两个不同的程序，**可以同时存在**——所以守卫按「构建身份」区分：

- 同一个构建第二次启动 → 检测到已有实例，把**那个**窗口带到前台、自己退出；
- 两个构建各跑各的，互不阻拦（即便它们共用 `~/Documents/guji` 数据区）。

实现分两层：

- **互斥体**判定"是否已有本构建实例"：`CreateMutexW`，若 `GetLastError` 返回
  ERROR_ALREADY_EXISTS 则说明已有。句柄必须**存进模块级变量**——句柄被垃圾
  回收互斥体就销毁了，守卫随之失效（活到进程退出，正合需求）。
- **定向激活**（QLocalServer/QLocalSocket，按构建身份命名）：第二实例连上
  本构建专属的命名管道，请求"报出你的主窗口 HWND"，再由**自己**（刚被用户
  双击、握有前台权限的新进程）对该 HWND 做 ShowWindow/SetForegroundWindow。
  既有实例这边收到请求也会顺手 showNormal/raise/activateWindow 兜底。

⚠️ **绝不能按窗口标题找窗口**（旧行为 `FindWindowW(None, "古籍重製")`）：
开发版与正式版的窗口标题一模一样，两个窗口**同时开着**时再点一次图标，
按标题找会命中 Z 序里随便哪一个——把另一个构建的窗口带到前台、而自己退出，
用户看到的是"点 A 图标、弹出 B 窗口"。命名管道按构建身份命名（package_dir
的哈希），从机制上保证激活的永远是本构建自己的窗口。

⚠️ 仅 win32 有互斥体/前台 API；其它平台互斥体直接放行（本项目只在 Windows
打包发行），socket 激活通道跨平台可用。
"""

from __future__ import annotations

import hashlib
import sys

_MUTEX_PREFIX = "Local\\GujiZhiZuo-Desktop-"
_CHANNEL_PREFIX = "GujiZhiZuo-Desktop-"
_ERROR_ALREADY_EXISTS = 183
_SW_RESTORE = 9
#: 原样显示（不改尺寸/状态），用于"已经最大化或普通状态"的已有窗口。
_SW_SHOW = 5
#: 连接/读回执的超时（ms）。双击场景下 1 秒足够；超时不影响"退出"这个决定。
_CONNECT_TIMEOUT_MS = 1000

#: 持有的互斥体句柄。**必须**被模块级引用持有：句柄一旦被回收，互斥体即销毁，
#: 单例守卫随之失效（直到进程退出才释放，正合需求）。
_held_mutex: object | None = None
#: 持有的激活通道服务。同上：被 GC 监听就断了，第二实例再也连不上。
_server: object | None = None


def _suffix(identity: str) -> str:
    return hashlib.md5(identity.encode("utf-8")).hexdigest()[:10]


def mutex_name(identity: str) -> str:
    """由构建身份推出互斥体名。

    identity 用 **desktop 包目录**（`desktop.utils.files.package_dir()`）：
    源码是 `D:\\...\\desktop`，打包是 `...\\guji\\_internal\\desktop`——同一构建
    稳定不变，两个构建互不相同。
    """
    return f"{_MUTEX_PREFIX}{_suffix(identity)}"


def channel_name(identity: str) -> str:
    """激活通道（QLocalServer）名，与互斥体同一套身份哈希、前缀不同。"""
    return f"{_CHANNEL_PREFIX}{_suffix(identity)}"


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


def _foreground_hwnd(hwnd: int) -> None:
    """把指定 HWND 的窗口恢复并带到前台（win32 前台 API）。

    ⚠️ **只在窗口被最小化时才用 SW_RESTORE**。``SW_RESTORE`` 的语义是"把最小化
    **或最大化**的窗口还原到原始尺寸"，主窗口默认就是最大化（见 app.py 的
    WINDOW_START_MAXIMIZED），一律 SW_RESTORE 会让"再点一次快捷方式"变成
    "把窗口缩回去"——用户会以为程序自己变小了。非最小化一律 SW_SHOW。
    """
    if sys.platform != "win32" or not hwnd:
        return

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ShowWindow.argtypes = [wintypes.HWND, wintypes.INT]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL

    user32.ShowWindow(hwnd, _SW_RESTORE if user32.IsIconic(hwnd) else _SW_SHOW)
    user32.SetForegroundWindow(hwnd)


def try_activate_existing(identity: str) -> bool:
    """已有本构建实例在监听 → 让它报出主窗口 HWND，并把**那个**窗口带到前台。

    返回 False = 没连上（没有实例，或它的通道没架起来）；调用方无论如何都
    应该退出——互斥体已经判过"本构建只能有一个实例"。

    ⚠️ 客户端用**信号驱动 + 嵌套 QEventLoop**，不要用 ``waitFor*`` 阻塞式：
    实测（2026-10-13 offscreen 探针）"工作线程里 waitFor*"形态下，客户端
    报告已写出、服务端却一个字节都收不到、readyRead 永不触发；纯事件循环
    形态全链路通。第二实例走到这里时 QApplication 已建好、exec() 还没跑，
    嵌套 loop 正好把双方事件都转起来。
    ⚠️ 前台调用由**本进程**做：它是刚被用户双击启动的进程，握有 Windows 的
    前台设置权限；既有实例在后台调 SetForegroundWindow 通常会被系统拦下
    （只闪任务栏）。
    """
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    from PySide6.QtNetwork import QLocalSocket

    if QApplication.instance() is None:
        # 连 QApplication 都没有（不该发生）：无从跑事件循环，只好放弃激活。
        return False

    sock = QLocalSocket()
    loop = QEventLoop()
    result = {"hwnd": 0}

    def _on_connected() -> None:
        sock.write(b"hwnd\n")

    def _on_ready_read() -> None:
        try:
            result["hwnd"] = int(bytes(sock.readAll()).strip() or b"0")
        except ValueError:
            result["hwnd"] = 0
        loop.quit()

    def _quit() -> None:
        loop.quit()

    sock.connected.connect(_on_connected)
    sock.readyRead.connect(_on_ready_read)
    sock.errorOccurred.connect(_quit)
    # 兜底超时：连接失败若不产 errorOccurred 也不能挂死 main()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(_quit)
    timer.start(_CONNECT_TIMEOUT_MS * 2)

    sock.connectToServer(channel_name(identity))
    loop.exec()
    sock.disconnectFromServer()
    if not result["hwnd"]:
        return False
    _foreground_hwnd(result["hwnd"])
    return True


def start_activation_server(identity: str, window_provider) -> bool:
    """为本构建架起激活通道。第二实例连上来时报出主窗口 HWND。

    ``window_provider`` 是惰性取窗口的回调（启动期通道要先于主窗口架起来，
    占住"第一个实例"的位置；等第二实例真连上来时窗口早已建好）。回 None
    时只回 "0"，客户端不去动前台。

    返回 False = 监听失败（极少见；此时第二实例只能安静退出，无伤大雅）。
    """
    global _server
    if _server is not None:
        return bool(getattr(_server, "isListening", lambda: False)())

    from PySide6.QtNetwork import QLocalServer

    name = channel_name(identity)
    # 上次异常退出（崩溃/强杀）可能留下尸体管道：先清再听。
    QLocalServer.removeServer(name)
    server = QLocalServer()
    if not server.listen(name):
        return False

    def _on_new_connection() -> None:
        while True:
            sock = server.nextPendingConnection()
            if sock is None:
                break
            # 一次请求只答一次：用动态属性做一次性闸门（readyRead 可能多次触发）
            sock.setProperty("_served", False)

            def _serve(s=sock) -> None:
                if s.property("_served"):
                    return
                s.setProperty("_served", True)
                req = bytes(s.readAll()).strip()
                if req != b"hwnd":
                    s.disconnectFromServer()
                    return
                window = None
                try:
                    window = window_provider()
                except Exception:  # noqa: BLE001 —— 取窗口失败不该炸事件循环
                    window = None
                hwnd = 0
                if window is not None:
                    try:
                        hwnd = int(window.winId())
                    except Exception:  # noqa: BLE001
                        hwnd = 0
                s.write(f"{hwnd}\n".encode("ascii"))
                # 双保险：客户端 win32 前台失败时，自己这边也抬一下
                # （showNormal 只在最小化时动尺寸，与 _foreground_hwnd 同一口径）
                if window is not None:
                    if window.isMinimized():
                        window.showNormal()
                    window.raise_()
                    window.activateWindow()

            sock.readyRead.connect(_serve)
            # ⚠️ 客户端可能在我们接上 readyRead 之前就已把请求写进缓冲
            #（readyRead 不会对"已到达的数据"补发）：接完先主动查一次。
            if sock.bytesAvailable() > 0:
                _serve()

    server.newConnection.connect(_on_new_connection)
    _server = server  # 模块级持强引用，防 GC 断监听
    return True
