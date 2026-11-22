# -*- coding: utf-8 -*-
"""阶段执行的装配点（由 ``runner.py`` 拆出，只搬不改）。

- progress_ui：进度/日志/统计的界面节流器
- launch：run_stage 入口与输入就绪判据
- stage_exec：一次完整阶段执行（参数校验 / effects / 写运行配置）
- process_io：启动子进程、输出落点、取消与暂存回收
- worker_events：worker 事件消费（stdout/progress/page_done）
- worker_output：尺寸/页框落盘、统计刷新、stderr 错误采集
- finish：收尾（runs.json 落盘、结果识别、后续状态）
- constants：``STATUS_LABELS``"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, cast

from .finish import StageFinishMixin
from .launch import StageLaunchMixin
from .process_io import StageProcessMixin
from .progress_ui import ProgressUiMixin
from .stage_exec import StageExecMixin
from .worker_events import WorkerEventsMixin
from .worker_output import WorkerOutputMixin


class StageRunnerMixin(ProgressUiMixin, StageLaunchMixin, StageExecMixin, StageProcessMixin, WorkerEventsMixin, WorkerOutputMixin, StageFinishMixin):
    """阶段执行（worker 子进程编排）。"""
