# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""后台应用进行中的编辑器强引用表（从 ``dialog_commit.py`` 拆出）。"""
from __future__ import annotations

#: 后台应用进行中的编辑器（「完成」关窗即返回，烘焙+写底片在工作线程）。
#: ⚠️ 必须持有**Python 强引用**：``exec()`` 返回后宿主的局部变量会释放，
#: 没有它 dialog（连同工作线程）会被 GC 掉 ⇒ ``QThread: Destroyed while
#: thread is still running`` 直接 abort 整个进程。完成/失败回调里移除。
_ACTIVE_APPLIES: list = []
