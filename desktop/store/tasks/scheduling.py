# -*- coding: utf-8 -*-
"""可选步骤开关、状态机装配与"最近的 boxes.json"查询。

从 ``desktop/store/tasks.py`` 拆出（2026-11-22）：顺序/跳过由
``desktop.steps.scheduler.Scheduler`` 决定，这里只把本任务的开关表喂给它。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from desktop.store.json_io import read_json
from desktop.store.tasks.base import TaskMixinBase


class TaskSchedulerMixin(TaskMixinBase):
    """可选步骤开关与本任务状态机的查询面。"""

    if TYPE_CHECKING:
        task_diagram: Callable[[str], Any]
        node_output: Callable[..., Path]

    def step_enabled(self, task_id: str, step: str) -> bool:
        """某个**可选步骤**的用户开关（``drafts/<步骤>.json`` 的 ``enabled``）。
        ⚠️ 这是"条件开关"的**通用读法**：以前只有拼版有开关（读
        ``drafts/imposition.json`` 的 ``enabled``），`store.imposition_enabled`
        与详情页的 ``imposition_active()`` 各读各的。再加一个可选步骤就要
        第三份读法——现在统一走这里（同一文件、同一键，行为一字不变，
        见 :meth:`scheduler_flags`）。

        ⚠️ 开关查询**永不抛错**：任务号非法/目录没了/文件坏了，一律当"没开"。
        调用方（列表后台线程、状态机）不能因为一个开关读不出来就崩。

        ⚠️ 命中缓存的条件是**文件指纹没变**（mtime_ns + size）：这个方法在
        第三步刷新时会被**每页**问一次（``imposition_effective`` 在里面），
        每次都完整读 JSON 纯属白花；拨开关会重写该文件，指纹一变立刻失效。
        文件不存在时**不缓存**（否则它后来被建出来会被旧结论挡住）。
        """
        cache = self._step_flags_map()
        cache_key = (task_id, step)
        try:
            path = self.drafts_dir(task_id) / f"{step}.json"
            stat = path.stat()
            fingerprint = (stat.st_mtime_ns, stat.st_size)
        except (OSError, ValueError):
            # ⚠️ 任务号非法时 ``drafts_dir`` 抛 ValueError：也归到"没开"这一档，
            #    与本方法"永不抛错"的契约一致（调用方有列表后台线程）。
            cache.pop(cache_key, None)
            return False
        cached = cache.get(cache_key)
        if cached is not None and cached[0] == fingerprint:
            return cached[1]
        try:
            data = read_json(path, None)
        except (OSError, ValueError):
            cache.pop(cache_key, None)
            return False
        enabled = bool(data.get("enabled")) if isinstance(data, dict) else False
        cache[cache_key] = (fingerprint, enabled)
        return enabled

    def scheduler_flags(self, task_id: str,
                        imposition_active: bool = False) -> dict[str, bool]:
        """本任务传给状态机的条件开关表（key = 可选步骤 key）。

        ⚠️ 键集合从 ``role == "optional"`` 派生（与
        :data:`desktop.steps.scheduler.CONDITIONS` 同源），**不是手写表**：
        以后加第二个可选步骤，这里的键自动多一个，调用方不用改。

        ⚠️ ``imposition`` 这一键**用调用方传进来的值覆盖**，不用
        :meth:`step_enabled` 的读数——调用方传的是 ``imposition_effective()``
        （= 在流程里 ＋ 开关两道闸），而 ``step_enabled`` 只读开关。
        图里没有这一格时，拼版产物根本不存在，必须让状态机跳过它、
        下游退回走去底色——只传开关会把流程指去一个空目录。
        """
        from desktop.steps.spec import OPTIONAL_STEPS

        flags = {step: self.step_enabled(task_id, step)
                 for step in OPTIONAL_STEPS}
        if "imposition" in flags:
            flags["imposition"] = bool(imposition_active)
        return flags

    def task_scheduler(self, task_id: str, imposition_active: bool = False):
        """本任务的**状态机**（``Scheduler``）——"下一步跑谁 / 能不能跑 / 跳谁"
        的唯一入口。

        ⚠️ 这是"后端按图驱动"的查询面：调用方不该再自己拼
        ``STAGES`` / ``SUPPLIERS`` 的静态知识去推断顺序或可运行性，一律问它。
        顺序来自本任务流程图（**节点**拓扑序，B 方案后同阶段可有多个节点各占
        一个状态单元，见 :meth:`~desktop.steps.scheduler.Scheduler.nodes`），跳过看
        :meth:`scheduler_flags`（可选步骤的开关表，键从 spec 派生）。

        与 :meth:`stage_input` 的分工：那个回答**"去哪个目录取产物"**，
        这个回答**"什么时候该跑、还差什么"**。
        """
        from desktop.steps.scheduler import Scheduler

        return Scheduler.from_diagram(
            self.task_diagram(task_id),
            self.scheduler_flags(task_id, imposition_active),
        )

    def nearest_boxes_path(self, task_id: str, node_id: str | None,
                           imposition_active: bool = False) -> Path | None:
        """当前节点**沿流程往前最近的** ``boxes.json`` 路径（没有则 ``None``）。

        用户 2026-10-25 口径：去底色合并左右裁图阈值时，要用「执行链上面当前
        去底色节点之前最近的 detect 节点」写出的提交计划，而不是靠文件名猜
        占位/左右归属。

        ``boxes`` 不是 rembg 声明的输入端口（它只吃 ``pages``），所以不能走
        :meth:`node_input`（那会因为没有声明而返回 ``None``）——这里直接问
        流程图：最近产出 ``boxes`` 的节点是谁，再取它的端口落点。
        """
        if not node_id:
            return None
        diagram = self.task_diagram(task_id)
        active = set(self.task_scheduler(task_id, imposition_active).stages)
        producer = diagram.nearest_producer_node(node_id, "boxes", active)
        if producer is None:
            return None
        try:
            path = self.node_output(task_id, producer, "boxes")
        except KeyError:
            return None
        # 「查看其是否有 boxes.json 数据」：最近节点还没跑过/没落盘时不要拿
        # 不存在的路径去当提交计划，调用方据此回落逐图计算。
        return path if path.is_file() else None
