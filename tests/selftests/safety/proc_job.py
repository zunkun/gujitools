# -*- coding: utf-8 -*-
"""进程组看护（Job Object）自测（2026-11-21）。

现场：拼版崩溃后留下 9 个孤儿进程（常驻 YOLO 服务 306MB + 8 个
multiprocessing 子进程），父进程早已退出，只能手工杀。Windows 不会替
"父进程已死"的子进程收尾，得靠作业对象。

断言线：

1. 装配成功且幂等；装好之后当前进程确实在作业里；
2. **真实回收**：另起一个父进程（自己装作业）→ 它派生一个长命子进程 →
   硬杀父进程（等同崩溃/任务管理器结束）→ 子进程必须跟着消失；
3. 「要活过父进程」的子进程（安装器 / 重启出来的新实例）拿到
   ``CREATE_BREAKAWAY_FROM_JOB``，否则装更新和重启会静默失败；
4. 接线（静态契约）：GUI 入口装了看护，那两处派生用了脱离标志。
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

NAME = "proc_job"
DEPENDS: list[str] = []
TITLE = "进程组看护（父进程崩溃不留孤儿）"


def _alive(pid: int) -> bool:
    """进程是否还活着（不用 tasklist / psutil：前者在受限环境里不可用）。"""
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    code = wintypes.DWORD()
    ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel32.CloseHandle(handle)
    return bool(ok) and code.value == STILL_ACTIVE


def _wait_dead(pid: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return False


def run(ctx) -> None:
    from tests.selftests._context import ok

    if sys.platform != "win32":
        ok("非 Windows：无此问题，跳过（POSIX 由进程组/服务管理器收）", True)
        return

    from utils.proc_job import (
        CREATE_BREAKAWAY_FROM_JOB, breakaway_flags, detached_creationflags,
        in_job, job_active, kill_children_on_exit,
    )

    root = Path(__file__).resolve().parents[3]

    # ---------------- 1. 装配 ----------------
    ok("装配成功（当前进程进作业）", kill_children_on_exit() is True)
    ok("幂等：重复调用不回退、不重建", kill_children_on_exit() is True)
    ok("装配后 job_active 为真", job_active() is True)
    ok("装配后进程确实处在作业里", in_job() is True)
    ok("脱离标志 = 分离进程 + 新进程组 + 逃出作业",
       detached_creationflags()
       == (0x00000008 | 0x00000200 | CREATE_BREAKAWAY_FROM_JOB),
       hex(detached_creationflags()))
    ok("breakaway 标志只含逃出作业那一位",
       breakaway_flags() in (0, CREATE_BREAKAWAY_FROM_JOB),
       hex(breakaway_flags()))

    # ---------------- 2. 真回收：父进程被硬杀，子进程跟着死 ----------------
    if getattr(sys, "frozen", False):
        ok("打包环境：跳过派生回收实测（--worker 分支不跑 GUI 入口）", True)
    else:
        parent_src = (
            "import subprocess, sys, time\n"
            f"sys.path.insert(0, r'{root}')\n"
            "from utils.proc_job import kill_children_on_exit\n"
            "assert kill_children_on_exit()\n"
            "child = subprocess.Popen([sys.executable, '-c',\n"
            "                          'import time; time.sleep(120)'])\n"
            "print(child.pid, flush=True)\n"
            "time.sleep(120)\n"
        )
        parent = subprocess.Popen(
            [sys.executable, "-c", parent_src],
            stdout=subprocess.PIPE, text=True, errors="replace",
        )
        child_pid = 0
        try:
            line = parent.stdout.readline().strip() if parent.stdout else ""
            child_pid = int(line or 0)
            ok("派生探针：父进程报出了子进程 pid", child_pid > 0, line[:40])
            time.sleep(0.4)
            ok("硬杀之前：子进程确实活着", _alive(child_pid), str(child_pid))
            parent.kill()          # 等同崩溃 / 任务管理器结束进程
            parent.wait(timeout=10)
            ok("父进程被硬杀后：子进程**跟着退出**（不留孤儿）",
               _wait_dead(child_pid, 10.0), f"pid={child_pid}")
        finally:
            if parent.poll() is None:
                parent.kill()
                parent.wait(timeout=5)
            if child_pid and _alive(child_pid):
                # 兜底清理：用例失败时也别把野进程留在机器上
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(child_pid)],
                    capture_output=True,
                )

    # ---------------- 3. 接线（静态契约）----------------
    app_src = (root / "desktop/app.py").read_text(encoding="utf-8")
    menu_src = (root / "desktop/ui/menu.py").read_text(encoding="utf-8")
    settings_src = (root / "desktop/settings/page.py").read_text(encoding="utf-8")
    ok("GUI 入口装了看护（main() 里、窗口构造之前）",
       "kill_children_on_exit" in app_src
       and app_src.index("kill_children_on_exit") < app_src.index("window = MainWindow()"))
    ok("更新安装器：派生时用脱离标志（否则退出时被作业收走）",
       "detached_creationflags" in menu_src)
    ok("「重启程序」：派生新实例时用脱离标志",
       "detached_creationflags" in settings_src)
