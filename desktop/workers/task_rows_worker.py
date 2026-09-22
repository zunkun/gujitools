# -*- coding: utf-8 -*-
"""任务列表行的读取（后台线程）。

列表页刷新要遍历全部任务、逐个读它的 ``runs.json`` 才能拿到四个阶段的状态。
任务一多、或单个任务的 runs 记录一多，这串读盘就会把 **UI 线程**占住——窗口
明明已经画出来了，内容却要再等一截才出现。

放到这里在后台线程读，读完一次性把整批行回传主线程渲染。只读不写，因此
与主线程的 store 访问不冲突。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from desktop.store import STAGES, STAGE_LABELS, STAGE_SHORT
from desktop.ui import theme as T


class TaskRowsWorker(QObject):
    """读全量任务行（只读，不落任何盘）。"""

    #: 读取完成，携带完整行列表
    completed = Signal(list)
    #: 读取失败（携带错误信息）
    failed = Signal(str)

    def __init__(self, store) -> None:
        """store 只用于读（list_tasks / stage_states），不写。"""
        super().__init__()
        self.store = store

    @Slot()
    def run(self) -> None:
        """遍历任务生成摘要行；异常回传 failed，不抛到线程外。"""
        try:
            status_labels = T.STATUS_LABELS
            rows = []
            for task in self.store.list_tasks():
                states = self.store.stage_states(task["id"])
                stages = []
                for stage in STAGES:
                    state = states[stage]
                    status = state["status"]
                    progress = (
                        f" {state['done']}/{state['total']}" if state["total"] else ""
                    )
                    stages.append(
                        {
                            "short": STAGE_SHORT[stage],
                            "status": status,
                            "tip": (
                                f"{STAGE_LABELS[stage]}："
                                f"{status_labels.get(status, status)}{progress}"
                            ),
                        }
                    )
                rows.append(
                    {
                        "id": task["id"],
                        "name": task["name"],
                        "source_path": task["source_path"],
                        "created_at": task["created_at"],
                        "stages": stages,
                    }
                )
            self.completed.emit(rows)
        except Exception as exc:  # noqa: BLE001 — 子线程异常必须回传主线程
            self.failed.emit(f"{type(exc).__name__}: {exc}")
