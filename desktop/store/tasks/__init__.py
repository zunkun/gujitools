# -*- coding: utf-8 -*-
"""任务索引（tasks.json）与任务目录布局。

2026-11-22 起按职责拆成子包（与本仓 ``utils/pdf_extract/`` 同一模式）：

1. ``constants``：运行阶段清单与界面文案（``STAGES`` / ``STAGE_LABELS`` …）；
2. ``base``     ：共享状态与流程图/开关读盘缓存；
3. ``records``  ：任务索引、任务号水位、任务 CRUD 与聚合任务；
4. ``paths``    ：任务目录布局、产物落点、缩略图缓存、源文件副本；
5. ``diagram``  ：``flow.bpmn`` 解析、槽位投影与降级提示；
6. ``inputs``   ：按图解析阶段/节点的输入供给方与落点；
7. ``readiness``：输入/产物是否已就绪；
8. ``scheduling``：可选步骤开关与状态机装配。

⚠️ 本 ``__init__`` 只做重导出：既有 ``from desktop.store.tasks import X``
全部不变，子模块之间不要反过来导入本包（会形成循环）。
"""

from desktop.store.tasks.constants import (
    IMPOSITION_LABEL,
    IMPOSITION_STAGE,
    STAGE_LABELS,
    STAGE_SHORT,
    STAGE_STEP,
    STAGES,
)
from desktop.store.tasks.diagram import TaskDiagramMixin
from desktop.store.tasks.inputs import TaskInputMixin
from desktop.store.tasks.paths import TaskLayoutMixin
from desktop.store.tasks.readiness import TaskReadinessMixin
from desktop.store.tasks.records import TaskRecordMixin
from desktop.store.tasks.scheduling import TaskSchedulerMixin


class TaskMixin(
    TaskRecordMixin, TaskLayoutMixin, TaskDiagramMixin,
    TaskInputMixin, TaskReadinessMixin, TaskSchedulerMixin,
):
    """任务索引读写与任务目录/阶段输出目录的路径推导。"""


__all__ = [
    "TaskMixin",
    "STAGES",
    "STAGE_LABELS",
    "STAGE_SHORT",
    "STAGE_STEP",
    "IMPOSITION_STAGE",
    "IMPOSITION_LABEL",
]
