# -*- coding: utf-8 -*-
"""启动下载好的安装器（自 ``desktop/ui/menu.py`` 拆出）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from desktop.ui.toast import show_toast

from .actions import quit_app


def install_and_restart(window, pending) -> None:
    """启动安装器（分离进程）后退出本程序，让安装器接管文件替换。

    ⚠️ 安装器是 **Inno Setup**（见 ``guji_setup.iss``）：不传静默参数——向导里
    由用户自己点「下一步」，比程序替他决定稳；Inno 默认 ``CloseApplications``
    会用 Restart Manager 处理仍占着 ``{app}`` 文件的进程（本程序正在退出，
    交给它兜底）。
    ⚠️ 用**分离**进程（DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP）：本进程
    退出、或用户在终端 Ctrl+C，都不会把安装器一起带走（同 yolo_service 的拉起）。
    """
    path = Path(str((pending or {}).get("path") or ""))
    if not path.is_file():
        show_toast(window, "error", "安装包不见了",
                   "请重新点「检查更新」下载。")
        return
    try:
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if sys.platform == "win32":
            # ⚠️ 必须**脱离本进程的作业**（见 utils/proc_job.py）：本进程
            #    退出时作业会把成员进程一并终止，安装器得活下来继续装。
            from utils.proc_job import detached_creationflags

            kwargs["creationflags"] = detached_creationflags()
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen([str(path)], **kwargs)
    except OSError as exc:
        show_toast(window, "error", "安装程序启动失败", str(exc))
        return
    quit_app(window)
