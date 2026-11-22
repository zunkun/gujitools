# -*- coding: utf-8 -*-
"""输入/产物"是否已就绪"的判据（目录有货 + 上游动作真的跑过）。

从 ``desktop/store/tasks.py`` 拆出（2026-11-22）：路径怎么找见 ``inputs.py``，
这里只管"这份输入现在算不算数"。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from desktop.steps import ports
from desktop.store.tasks.base import TaskMixinBase


class TaskReadinessMixin(TaskMixinBase):
    """就绪判据（阶段粒度与节点粒度）。"""

    if TYPE_CHECKING:
        task_diagram: Callable[[str], Any]
        node_input: Callable[..., Path | None]
        node_supplier: Callable[..., str | None]
        stage_input: Callable[..., Path | None]
        stage_supplier: Callable[..., str | None]
        _primary_of_stage: Callable[[Any, str], str | None]
        detect_submit_fresh: Callable[[str, str | None], bool]
        node_action_executed: Callable[[str, str | None, str], bool]

    #: 产物**不经 runs.json 记录**的阶段：拼版成品由版面**合成**落盘
    #: （见 ``imposition_layout._compose_imposition_now``），没有"执行"动作。
    _COMPOSED_STAGES = frozenset({"imposition"})

    def node_action_executed(self, task_id: str, node_id: str | None,
                             stage: str) -> bool:
        """某**节点实例**的某个动作是否成功执行过。

        ⚠️ ``detect`` 与 ``detect_submit`` 是同一个节点的两个动作，各有各的
        执行记录：只跑了检测、还没提交时，``detect_submit`` 必须为 False，
        否则「图片去底色」会提前把未裁好的图当成上游产物（用户 2026-11-03）。
        """
        records = (
            self.list_node_runs(task_id, node_id, stage)
            if node_id
            else self.list_stage_runs(task_id, stage)
        )
        return any(record.get("status") == "success" for record in records)

    @staticmethod
    def _latest_success_record(records) -> dict | None:
        """一组运行记录里**最近一次成功**的那条（按 ``finished_at`` 取最大）。"""
        best: dict | None = None
        best_at = -1.0
        for record in records or ():
            if not isinstance(record, dict) or record.get("status") != "success":
                continue
            try:
                at = float(record.get("finished_at") or 0.0)
            except (TypeError, ValueError):
                at = 0.0
            if best is None or at >= best_at:
                best, best_at = record, at
        return best

    def detect_submit_fresh(self, task_id: str, node_id: str | None = None) -> bool:
        """「提交检测结果」的裁图是否对应**最近一次成功的「检测文本框」**。

        用户规则（2026-11-03）：检测文本框是**两个动作**（检测 + 提交），
        两次都执行了下一步才有数据。检测又成功跑过一次而没重新提交时，
        ``stages/detect``（提交产物）里的裁图还是旧框裁出来的——它是去底色的
        **输入**，不该继续生效（否则用户看到"改了框、还没提交，去底色
        却已经有图"）。

        ``_preview_run_id`` 是提交时写进执行记录的检测 run_id（见
        ``submit.py::_run_detect_submit_unchecked``）。老记录没有该字段时
        **不判过期**——宁可少拦一次，也不误伤改造前跑过的任务。
        """
        submits = (
            self.list_node_runs(task_id, node_id, "detect_submit")
            if node_id else self.list_stage_runs(task_id, "detect_submit")
        )
        detects = (
            self.list_node_runs(task_id, node_id, "detect")
            if node_id else self.list_stage_runs(task_id, "detect")
        )
        latest_submit = self._latest_success_record(submits)
        latest_detect = self._latest_success_record(detects)
        if latest_submit is None:
            return False
        if latest_detect is None:
            # 没有可对账的检测记录（历史任务 / runs.json 被裁剪）：不误判过期。
            return True
        recorded = (latest_submit.get("parameters") or {}).get("_preview_run_id")
        if not recorded:
            return True
        return str(recorded) == str(latest_detect.get("run_id"))

    def node_input_effective(self, task_id: str, node_id: str, port: str = "pages",
                             imposition_active: bool = False) -> bool:
        """本节点某端口的输入**现在该不该有数据**。

        判据 = **目录里有东西** 且 **上游产出该端口的动作已成功执行**。
        ⚠️ 只看目录不够：预览落图、历史残留、手工拷图都会让目录"看起来有货"，
        但上游若没成功执行过就不能算正式输入；检测与提交是两步，还要对账
        （见 :meth:`detect_submit_fresh`）。
        """
        return self._input_effective(
            task_id,
            self.node_input(task_id, node_id, port, imposition_active),
            self.node_supplier(task_id, node_id, port, imposition_active),
            port,
            0,
        )

    def stage_input_effective(self, task_id: str, stage: str, port: str = "pages",
                              imposition_active: bool = False) -> bool:
        """:meth:`node_input_effective` 的**阶段粒度**版本（没有节点信息时用）。"""
        return self._input_effective(
            task_id,
            self.stage_input(task_id, stage, port, imposition_active),
            self.stage_supplier(task_id, stage, port, imposition_active),
            port,
            0,
        )

    def _is_composed_ref(self, task_id: str, ref: str | None, port: str) -> bool:
        """供给方是不是**合成型**阶段（拼版）。

        拼版产物由版面合成落盘（没有 run 记录），且**空目录是合法状态**
        ——「已启用但还没拼页」要由下游自己给专属提示，不能在这里判成
        「输入没就位」（用户 2026-10-03 踩过：提示会把人引去第三步）。
        """
        if not ref or ref in (ports.SUPPLY_TASK_SOURCE, ports.SUPPLY_TASK_INPUT):
            return False
        diagram = self.task_diagram(task_id)
        item = diagram.node(ref)
        stage = (
            item.stage
            if item is not None and item.stage
            else ports.STAGE_STEPS.get(ref, ref)
        )
        return ports.fold_forward(stage, port) in self._COMPOSED_STAGES

    def _input_effective(self, task_id: str, path: Path | None, ref: str | None,
                         port: str, depth: int) -> bool:
        """路径有内容 + 供给方已生效 ⇒ 这份输入才算数。"""
        if not self._is_composed_ref(task_id, ref, port):
            if path is None or not path.exists():
                return False
            try:
                if path.is_dir() and not any(path.iterdir()):
                    return False
            except OSError:
                return False
        return self._producer_effective(task_id, ref, port, depth)

    def _producer_effective(self, task_id: str, ref: str | None, port: str,
                            depth: int) -> bool:
        """产出方是否**已经生效**（真的跑过，产出的东西可以给下游看）。

        - 任务自身供给（源 PDF / 入口图片）⇒ 天然生效，它们不靠谁先跑；
        - 普通阶段 ⇒ 查 ``runs.json`` 里**该动作**的 success 记录
          （``detect`` 要折到 ``detect_submit``，见 :func:`ports.fold_forward`）；
        - 拼版 ⇒ 没有执行记录，退一步看**它自己的输入**是否生效（递归有深度上限）。
        """
        if ref is None or ref in (ports.SUPPLY_TASK_SOURCE, ports.SUPPLY_TASK_INPUT):
            return True
        if depth >= 3:
            # 图坏了/成环：别再往下追，按"有东西就算有效"收场，避免无限递归。
            return True
        diagram = self.task_diagram(task_id)
        item = diagram.node(ref)
        if item is not None and item.stage:
            stage = item.stage
            producer: str | None = ref
        else:
            stage = ports.STAGE_STEPS.get(ref, ref)
            producer = self._primary_of_stage(diagram, stage)
        effective = ports.fold_forward(stage, port)
        if effective in self._COMPOSED_STAGES:
            inner_path = (
                self.node_input(task_id, producer, port, True)
                if producer else None
            )
            inner_ref = (
                self.node_supplier(task_id, producer, port, True)
                if producer else None
            )
            return self._input_effective(
                task_id, inner_path, inner_ref, port, depth + 1
            )
        if effective == "detect_submit":
            # 两步动作（检测 + 提交）：只查"提交成功过"不够——检测又跑过一次
            # 而没重新提交时，磁盘上的裁图是旧框裁的（用户 2026-11-03）。
            return self.detect_submit_fresh(task_id, producer)
        return self.node_action_executed(task_id, producer, effective)
