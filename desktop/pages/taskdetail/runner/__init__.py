# -*- coding: utf-8 -*-
"""任务详情页的阶段执行控制器：构建参数、启动 worker 子进程、解析进度日志。

纯业务派生规则见 desktop/services/print_plan.py，
检测提交控制器见 desktop/pages/taskdetail/submit.py，
历史配置回填见 desktop/pages/taskdetail/history.py。

2026-11-22 按职责拆成子包（只搬不改）：
- widget.py
- progress_ui.py
- launch.py
- stage_exec.py
- process_io.py
- worker_events.py
- worker_output.py
- finish.py
- constants.py
"""

from desktop.pages.taskdetail.runner.widget import (
    StageRunnerMixin,
)
from desktop.pages.taskdetail.runner.progress_ui import (
    ProgressUiMixin,
)
from desktop.pages.taskdetail.runner.launch import (
    StageLaunchMixin,
)
from desktop.pages.taskdetail.runner.stage_exec import (
    StageExecMixin,
)
from desktop.pages.taskdetail.runner.process_io import (
    StageProcessMixin,
)
from desktop.pages.taskdetail.runner.worker_events import (
    WorkerEventsMixin,
)
from desktop.pages.taskdetail.runner.worker_output import (
    WorkerOutputMixin,
)
from desktop.pages.taskdetail.runner.finish import (
    StageFinishMixin,
)
from desktop.pages.taskdetail.runner.constants import (
    STATUS_LABELS,
)

__all__ = ["StageRunnerMixin", "ProgressUiMixin", "StageLaunchMixin", "StageExecMixin", "StageProcessMixin", "WorkerEventsMixin", "WorkerOutputMixin", "StageFinishMixin", "STATUS_LABELS"]
