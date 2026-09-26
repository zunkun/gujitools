# -*- coding: utf-8 -*-
"""进程相关的通用小工具。

只放"跨模块都要用、但不值得各自写一遍"的东西。目前是 `pid_alive`——本项目有两处
都要判断"某个 pid 的属主进程是不是已经死了"（清理效果图暂存目录、清理常驻服务
的发现文件），逻辑一样，抽出来只留一份。
"""

from __future__ import annotations

import os


def pid_alive(pid: int) -> bool:
    """pid 对应的进程是否还活着。

    ⚠️ **保守优先**：任何"说不清"的情况（权限不足、psutil 不可用、平台差异）
    都返回 True（当作活着）。调用方是拿它做**删除判据**的（删暂存目录、删发现
    文件），把"不确定"当成"已死"就会误删正在用的东西；反过来只是少清一点垃圾。
    """
    if not pid or pid <= 0:
        return False
    try:
        import psutil
    except Exception:  # noqa: BLE001 - 没有 psutil 就退回 os.kill 探测
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except (PermissionError, OSError):
            return True
        return True
    try:
        return bool(psutil.pid_exists(pid))
    except Exception:  # noqa: BLE001
        return True
