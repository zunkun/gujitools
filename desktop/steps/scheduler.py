# -*- coding: utf-8 -*-
"""流程**状态机**：把"下一步跑什么"从端口级依赖图简化成有序阶段表。

## 为什么不用旧的边表

旧做法（:class:`desktop.steps.flow.FlowDefinition`）把流程表达成**端口级
依赖图** ``(consumer, port) → supplier``，回答"这一步去谁那儿取产物"。它能
表达任意拓扑，但代价是：推出"下一步该跑谁"要走一堆图算法，判"能不能跳过"
还要看每个端口的供给方就位没有——用户 2026-10-05 的原话：

> 后端驱动可以使用状态机来实现，bpm 流程引擎太复杂

所以这里换一条更简单的路：

- **顺序**由 BPMN 图的拓扑序给定（:meth:`FlowDiagram.stage_order`）；
- **跳过**只看两件事：这一步在不在图里、它的条件是否满足；
- **分支**用一张极小的条件表（``CONDITIONS``），不引入表达式引擎。

产物路径仍走 :data:`desktop.steps.ports` 的落点表（那是"文件放哪儿"的
事实，与"谁先谁后"无关），所以状态机不需要自己算路径。

## 状态与迁移

::

    PENDING --can_run--> READY --进入--> RUNNING --完成--> DONE
                                          |
                                          +--失败--> FAILED --重试--> READY

**跳过**（SKIP）只发生在"这一步不在流程图里"或"条件不满足"两种情况；
其余阶段即使上游没跑，也允许**单独重跑**（用户常要改完参数只重做一步），
所以 :meth:`Scheduler.missing_inputs` 只做**提示**，不做硬拦截。

⚠️ 纯逻辑、**不 import Qt**——可以被 worker 子进程与自测导入。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from desktop.steps import ports
from desktop.steps.bpmn_diagram import FlowDiagram
from desktop.steps.spec import OPTIONAL_STEPS

#: 阶段状态
PENDING = "pending"     # 还没轮到
READY = "ready"         # 轮到了，可以跑
RUNNING = "running"     # 正在跑
DONE = "done"           # 跑完了
SKIPPED = "skipped"     # 本流程不含这一步（或条件不满足）
FAILED = "failed"       # 跑挂了

#: 需要"条件满足"才执行的阶段 → 条件名。
#:
#: ⚠️ 从 :data:`desktop.steps.spec.SPECS` 的 ``role == "optional"`` 派生，
#: **不是手写表**。以前这里写死 ``{"imposition": "imposition"}``——再加一个
#: 可选步骤（比如未来的"人工校对"），就得同时改这张表、store 的 flags 构造、
#: 调用方的传参三处，还没有任何守卫能发现漏改（"默认流程逻辑"的标准配方）。
#: 现在条件名恒等于步骤 key：开关状态由调用方按同名 key 传进 ``flags``。
#: 没给的条件按 **False** 处理（可选步骤默认不跑）。
CONDITIONS: dict[str, str] = {step: step for step in OPTIONAL_STEPS}

#: 默认流程模板文件名（放在 ``desktop/static/``，随打包进 ``_internal/``）。
DEFAULT_TEMPLATE = "task_default.bpmn"


def default_template_path():
    """默认流程模板文件的标准位置。

    用 :func:`desktop.utils.files.package_dir` 而非 ``project_root``：打包后
    ``desktop`` 在 PYZ 里、磁盘上没有真实目录，模板由 spec 的 ``datas``
    落到 ``_internal/desktop/static/``，正是这里的返回值。
    """
    from desktop.utils.files import package_dir

    return package_dir() / "static" / DEFAULT_TEMPLATE


def load_default_diagram() -> FlowDiagram:
    """读默认流程模板 → :class:`FlowDiagram`；读不到返回**空图**。

    ⚠️ 读不到**不抛异常**：没有模板时程序该照常启动（界面少几个步骤而已），
    不该整个打不开。调用方用 ``not diagram.nodes`` 判空。
    """
    try:
        return FlowDiagram.load(default_template_path())
    except (OSError, ValueError):
        return FlowDiagram()


@dataclass(frozen=True)
class StageState:
    """一个阶段在状态机里的当前状态。"""

    stage: str
    state: str = PENDING

    @property
    def is_finished(self) -> bool:
        """这一步**不用再跑了**（跑完或跳过）。"""
        return self.state in (DONE, SKIPPED)


@dataclass
class Scheduler:
    """按 BPMN 图的顺序推进阶段的小状态机。

    用法::

        sched = Scheduler.from_diagram(diagram, flags={"imposition": True})
        sched.stages                 # 本流程要跑的阶段（有序）
        sched.next_stage("detect")   # -> "imposition"
        sched.mark("extract", DONE)

    ``flags`` 是条件开关表（如 ``{"imposition": True}``）；没给的条件按
    **False** 处理——条件分支默认不走（拼版是可选步骤，默认不做）。
    """

    stages: tuple[str, ...] = ()
    #: 阶段 → 状态
    states: dict[str, str] = field(default_factory=dict)
    #: 条件开关
    flags: dict[str, bool] = field(default_factory=dict)
    #: 本流程**排除**掉的阶段（图里没有，但程序认识的）——界面据此隐藏
    excluded: tuple[str, ...] = ()

    # ------------------------------------------------------------ 构造
    @classmethod
    def from_diagram(cls, diagram: FlowDiagram,
                     flags: dict[str, bool] | None = None) -> "Scheduler":
        """从流程图建状态机：顺序取拓扑序，条件不满足的阶段直接剔除。"""
        flags = dict(flags or {})
        order = diagram.stage_order()
        active: list[str] = []
        skipped: list[str] = []
        for stage in order:
            condition = CONDITIONS.get(stage)
            if condition and not flags.get(condition, False):
                skipped.append(stage)
                continue
            active.append(stage)
        known = set(ports.STAGE_STEPS)
        excluded = tuple(
            s for s in known if s not in order and s not in active
        )
        scheduler = cls(
            stages=tuple(active),
            states={s: PENDING for s in active},
            flags=flags,
            excluded=excluded,
        )
        for stage in skipped:
            # 条件不满足的记 SKIPPED，界面能区分"没有这步"与"这步被跳过"
            scheduler.states[stage] = SKIPPED
        return scheduler

    @classmethod
    def default(cls, flags: dict[str, bool] | None = None) -> "Scheduler":
        """默认流程的状态机（没有任务 / 读不到文件时的兜底）。

        读 :func:`default_template_path` 指向的模板文件——**默认流程也是
        一份 bpmn 文件**，不在这里用代码写第二份顺序（否则"文件是真源"
        就成了空话：改文件、默认流程却不变）。

        模板缺失/损坏时返回**空状态机**（``stages=()``），调用方按"没有
        流程"处理；不在这里编一份顺序兜底，免得又变成第二份事实。
        """
        return cls.from_diagram(load_default_diagram(), flags)

    # ------------------------------------------------------------ 查询
    def __contains__(self, stage: str) -> bool:
        return stage in self.stages

    def state_of(self, stage: str) -> str:
        """阶段状态；不在本流程里返回 :data:`SKIPPED`。"""
        return self.states.get(stage, SKIPPED)

    def mark(self, stage: str, state: str) -> None:
        """置状态（未知阶段不写：它本来就不在流程里）。"""
        if stage in self.states:
            self.states[stage] = state

    def is_runnable(self, stage: str) -> bool:
        """这一步**当前**能不能跑（在流程里、且没跑完/没跳）。"""
        return self.state_of(stage) in (PENDING, READY, FAILED)

    def next_stage(self, current: str | None = None) -> str | None:
        """``current`` 之后**第一个还没完成**的阶段；没有了返回 ``None``。

        ⚠️ 不看"依赖就位没有"——那是 :meth:`missing_inputs` 的提示职责。
        用户改完参数常要只重跑一步，硬拦会挡住合法操作。
        """
        if current is None:
            candidates = self.stages
        else:
            if current not in self.stages:
                candidates = self.stages
            else:
                index = self.stages.index(current)
                candidates = self.stages[index + 1:]
        for stage in candidates:
            if not self.state_of(stage) in (DONE, SKIPPED):
                return stage
        return None

    def first_pending(self) -> str | None:
        """从头找第一个还没完成的阶段（"该从哪儿开始跑"）。"""
        return self.next_stage(None)

    def progress(self) -> tuple[int, int]:
        """``(已完成数, 总数)``——含跳过（跳过的算已完成，进度条才会满）。"""
        total = len(self.stages) + sum(
            1 for s, st in self.states.items() if st == SKIPPED
        )
        done = sum(1 for st in self.states.values() if st in (DONE, SKIPPED))
        return done, total

    def missing_inputs(self, task_dir, stage: str,
                       port_names: dict[str, str] | None = None
                       ) -> list[str]:
        """这一步的哪些输入还没就位（**只用于提示**，不拦执行）。

        ``port_names`` 是端口 → 落点目录/文件名的映射（默认查 ports 的
        ``PORT_ARTIFACTS``）。返回空列表 = 都齐了。

        ⚠️ **别拿它当"能不能跑"的判据**（它现在没有生产调用方，只剩自测在碰）：
        它把 ``PORT_ARTIFACTS`` 的**产物类型**（``"pages"``/``"boxes"``）当成
        相对目录直接拼到任务目录上，跟 ports 的落点表（``STAGE_LOCATIONS``）
        和按图求解的 :func:`~desktop.store.tasks.TaskMixin.stage_input` 对不上，
        两者永远不会一致。真正的就绪判据是
        :func:`desktop.steps.ports.stage_blocking_inputs`（经
        :meth:`~desktop.store.tasks.TaskMixin.required_stage_inputs`）。
        """
        from pathlib import Path

        names = port_names or {}
        missing: list[str] = []
        for port in ports.stage_inputs(stage):
            artifact = names.get(port) or ports.PORT_ARTIFACTS.get(port)
            if not artifact:
                continue
            path = Path(task_dir) / artifact
            if not (any(path.iterdir()) if path.is_dir() else path.exists()):
                missing.append(ports.PORT_LABELS.get(port, port))
        return missing

    def to_dict(self) -> dict:
        """给界面用的快照（JSON 友好）。"""
        return {
            "stages": list(self.stages),
            "states": dict(self.states),
            "flags": dict(self.flags),
            "excluded": list(self.excluded),
        }


__all__ = [
    "CONDITIONS", "DEFAULT_TEMPLATE", "DONE", "FAILED", "PENDING", "READY",
    "RUNNING", "SKIPPED", "Scheduler", "StageState", "default_template_path",
    "load_default_diagram",
]
