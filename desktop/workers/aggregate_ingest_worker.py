# -*- coding: utf-8 -*-
"""**聚合任务汇集**的后台 worker（绝不在主线程复制几百张图）。

聚合任务创建后要把它所有成员在起始节点上的产物按顺序复制进自己的任务
目录（见 :mod:`desktop.services.aggregate_ingest`）。一本古籍 300~600 页、
每页几百 KB，同步复制就是几十秒的界面冻结——所以固定放后台线程。

⚠️ ``store`` 是纯 Python（不 import Qt），可安全在子线程里用；``boxes.json``
/ ``sizes.json`` 的进程内缓存带 RLock（``store.annotations._DocCache``），
与界面线程并发读不会写坏。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from desktop.services.aggregate_ingest import run_ingest, set_pending_marker


class AggregateIngestWorker(QObject):
    """把成员产物按成员顺序汇集进聚合任务（后台线程里跑）。"""

    #: (任务号, 页数, 复制成功文件数, 跳过/降级的原因)
    finished = Signal(str, int, int, list)
    #: (任务号, 失败原因)
    failed = Signal(str, str)
    #: 复制进度 (done, total)
    progress = Signal(int, int)

    def __init__(self, store, task_id: str):
        super().__init__()
        self.store = store
        self.task_id = str(task_id)

    @Slot()
    def run(self) -> None:
        task_dir = None
        try:
            task_dir = self.store.task_dir(self.task_id)
            set_pending_marker(task_dir, True)  # 幂等：主线程起线程前已立过一次
            result = run_ingest(self.store, self.task_id, progress=self.progress.emit)
            self.finished.emit(
                self.task_id, result.pages, result.copied, list(result.notes)
            )
        except Exception as exc:  # noqa: BLE001 - 兜底：别让线程静默死掉
            self.failed.emit(self.task_id, str(exc))
        finally:
            # ⚠️ **必须撤**：标记留着，详情页会永远说"正在汇集"，
            #    用户也永远点不动执行。
            if task_dir is not None:
                set_pending_marker(task_dir, False)


__all__ = ["AggregateIngestWorker"]
