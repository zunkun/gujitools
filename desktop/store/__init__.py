# -*- coding: utf-8 -*-
"""任务持久化：全部以 JSON 文件存储（无数据库）。

任务索引在数据根目录 tasks.json；任务目录内 pages.json（页面清单）、
runs.json（阶段运行状态）、boxes.json（检测框）、sizes.json（页面尺寸）。
"""

from desktop.store.store import TaskStore
from desktop.store.tasks import STAGE_LABELS, STAGE_SHORT, STAGE_STEP, STAGES

__all__ = ["TaskStore", "STAGES", "STAGE_LABELS", "STAGE_SHORT", "STAGE_STEP"]
