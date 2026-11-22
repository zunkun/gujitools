# -*- coding: utf-8 -*-
"""阶段执行的状态中文标签（与 ``desktop.ui.theme.STATUS_LABELS`` 同源）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, cast


STATUS_LABELS = {
    "pending": "未执行",
    "running": "执行中",
    "success": "成功",
    "failed": "失败",
    "cancelled": "已中断",
}

