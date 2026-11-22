# -*- coding: utf-8 -*-
"""一条流程的**运行语义** :class:`FlowDefinition`（阶段序列 + 端口边表）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from desktop.steps import ports
from desktop.steps.flow.constants import (
    CONDITION_IMPOSITION,
    FLOW_FILENAME,
    GUJI_NS,
    _local,
    _q,
)
from desktop.steps.flow.model import FlowEdge, StageSlot
from desktop.steps.flow.serialization import FlowSerializationPart


@dataclass
class FlowDefinition(FlowSerializationPart):
    """一条流程：运行阶段节点序列 + 端口级连线表。

    - ``stages``：运行阶段名（``STAGE_STEPS`` 的键）按流程顺序排列，**不含**
      start/end 事件（它们只是文件里的图形符号，入口由哨兵连线表达）；
    - ``edges``： ``(consumer, port) → [FlowEdge, …]``。同一端口可以同时有
      一条无条件边和若干条条件边（条件命中者优先），但**无条件边至多一条**。
    """

    stages: tuple[str, ...] = ()
    edges: dict[tuple[str, str], list[FlowEdge]] = field(default_factory=dict)

    # ------------------------------------------------------------ 查询
    def supplier_of(self, stage: str, port: str,
                    context: dict[str, bool] | None = None) -> str | None:
        """按连线解析 ``(stage, port)`` 该由谁供给；没连线返回 ``None``。

        选边规则：**条件命中**（``condition`` 在 ``context`` 里为真）的边
        优先；否则取无条件边；再没有就 ``None``。与
        :func:`desktop.steps.ports.resolve_input` 的 ``overrides`` 语义对齐
        （默认流程下两者逐端口相等，自测钉死）。
        """
        context = context or {}
        candidates = self.edges.get((stage, port), [])
        for edge in candidates:
            if edge.condition and context.get(edge.condition):
                return edge.supplier
        for edge in candidates:
            if edge.condition is None:
                return edge.supplier
        return None

    # ------------------------------------------------------------ 解析
    def resolve_input(self, task_dir: Path | str, stage: str, port: str,
                      context: dict[str, bool] | None = None) -> Path | None:
        """按连线解析输入**绝对路径**（落点仍查 ports 的表，不另写一份）。

        上游是 :data:`~desktop.steps.ports.SUPPLY_TASK_SOURCE` 哨兵时返回
        ``None``——入口的 PDF 由任务自己供给（``TaskStore.source_copy_path``），
        不是任何阶段的产物，与 ports 现状保持一致。
        """
        supplier = self.supplier_of(stage, port, context)
        if supplier is None or supplier == ports.SUPPLY_TASK_SOURCE:
            return None
        return ports.artifact_path(task_dir, supplier, port)

    def input_ready(self, task_dir: Path | str, stage: str, port: str,
                    context: dict[str, bool] | None = None) -> bool:
        """这个端口的输入**已经就位**吗（落点存在且非空）。"""
        path = self.resolve_input(task_dir, stage, port, context)
        if path is None:
            return False
        if path.is_dir():
            return any(path.iterdir())
        return path.exists()

    def missing_stages(self, order: list[str] | None = None,
                       *, start: str | None = None) -> list[str]:
        """给定顺序，返回**输入还缺上游**的阶段（纯逻辑，不读磁盘）。

        ``order`` 缺省用本流程自己的 :attr:`stages`。语义与
        :func:`desktop.steps.ports.missing_stages` 一致，但按**本流程**的
        连线判断——自定义流程里换过的连线在这里如实生效。
        """
        order = list(self.stages) if order is None else list(order)
        done = {start} if start else set()
        waiting: list[str] = []
        for stage in order:
            if stage in done:
                continue
            for port, _ in self._inputs_of(stage):
                supplier = self.supplier_of(stage, port)
                if supplier in (None, ports.SUPPLY_TASK_SOURCE) or supplier in done:
                    continue
                waiting.append(stage)
                break
            done.add(stage)
        return waiting

    def _inputs_of(self, stage: str) -> tuple[tuple[str, str], ...]:
        """``(端口, 供给方)`` 对——从**连线表**反推这一步吃什么。

        ⚠️ 不走 :func:`desktop.steps.ports.stage_inputs`（那是 spec 静态声明）：
        自定义流程可能少连一个端口（那一步就是不该跑），连线表才是本流程
        的事实。
        """
        return tuple(
            (port, edge.supplier)
            for (consumer, port), group in self.edges.items()
            if consumer == stage
            for edge in group
        )

    def describe(self, stage: str) -> str:
        """一行可读描述（日志/编辑器提示用），产物名走 ports 的中文表。"""
        ins = " + ".join(
            ports.PORT_LABELS.get(port, port) for port, _ in self._inputs_of(stage)
        ) or "—"
        outs = " + ".join(
            ports.PORT_LABELS.get(p, p) for p in ports.stage_outputs(stage)
        ) or "—"
        return f"{stage}：{ins} → {outs}"

    # ------------------------------------------------------------ 界面投影
    def stage_slots(self) -> tuple[StageSlot, ...]:
        """把本流程的节点序列投影成**界面步骤条上的格子序列**。

        这是 BPM 驱动界面的唯一入口（``docs/tasks/bpm.md`` 的 M2）：详情页
        不再按 ``STAGES`` 四步硬索引寻址，而是查本流程投影出来的槽位表——
        自定义流程换了顺序/增删了节点，步骤条与寻址一起跟着变。

        折叠规则（**唯一一处**，界面别再自己判断）：

        1. ``detect_submit`` 折叠进 ``detect`` 格（它是第二步的第二个动作，
           进度也归第二步）；
        2. 同一格重复出现时**保留第一次**的位置；
        3. 可选节点（``StepSpec.role == "optional"``，当前只有
           ``imposition``）**不占** ``stack_index`` 的真实步骤区，统一排在
           真实步骤之后，延续既有「伪步骤占最后一位」的约定。

        ⚠️ 节点里出现未知阶段时跳过而不是炸——流程文件可能来自外部编辑，
        界面宁可少一格也不能整页打不开（:meth:`load` 已经拦过一道，这里是
        第二道，供运行期绕过 ``load`` 的调用方兜底）。
        """
        slots: list[StageSlot] = []
        seen: set[str] = set()
        for stage in self.stages:
            spec = ports.spec_for_stage(stage)
            if spec is None:
                continue
            step = ports.STAGE_STEPS.get(stage, stage)
            if step in seen:
                continue  # 折叠：detect_submit 并进 detect，保持首次出现的位置
            seen.add(step)
            slots.append(
                StageSlot(step=step, stage=stage, optional=spec.role == "optional")
            )
        #两个下标在这里一次算清（StageSlot 是 frozen，构造后不可改）：
        # - ``bar_index`` = **流程顺序**（可选节点留在它该在的位置）；
        # - ``stack_index`` = 真实步骤区排名，可选节点顺延到真实步骤之后
        #   （延续既有「伪步骤占最后一位」约定，两个栈的建页顺序就不用动）。
        real = [s for s in slots if not s.optional]
        optional = [s for s in slots if s.optional]
        stack_offset = len(real)
        stack_of: dict[str, int] = {s.step: i for i, s in enumerate(real)}
        for i, slot in enumerate(optional):
            stack_of[slot.step] = stack_offset + i
        return tuple(
            StageSlot(
                step=slot.step,
                stage=slot.stage,
                optional=slot.optional,
                bar_index=bar_index,
                stack_index=stack_of[slot.step],
            )
            for bar_index, slot in enumerate(slots)
        )

    def optional_after(self, step: str | None = None) -> int | None:
        """可选节点插在**真实步骤数组的第几位之后**（喂 :class:`StepBar`）。

        ⚠️ 这与 :attr:`StageSlot.bar_index` **不是一回事**，别混：

        - ``bar_index`` 是**步骤条上的格子序号**，含可选节点自己占的那一格
          （默认流程：extract=0/detect=1/rembg=2/imposition=3/print=4）；
        - 本方法返回的是**真实步骤列表里的下标**——``StepBar`` 拿到的是
          去掉可选节点的标题序列，它要在这个序列的第 N 项**后面**插入节点。

        默认流程：真实步骤 [extract, detect, rembg, print]，可选节点
        ``imposition`` 在格序里排在 rembg(2) 与 print(4) 之间 ⇒ 插在真实
        步骤里下标 2（rembg）之后 ⇒ 返回 **2**。

        ⚠️ 直接数"``bar_index`` 比可选节点小的真实步骤**个数**"会得 3
        （extract/detect/rembg），插到那儿就跑到 print 后面去了——因为
        ``after`` 指的是**最后一个左邻居的下标**，不是左邻居的个数。

        ⚠️ 返回值三态（2026-10-07，与 ``FlowDiagram.optional_after`` 同步）：
        ``None`` = 本流程**没有**可选节点；图里有拼版但它排在**最前**、没有
        左邻居时返回 ``-1``——早先这种情况也回 ``None``，``StepBar`` 按"默认
        位插到最后"处理，拼版被排到了「PDF排版」后面（任务 #0027）。
        """
        slots = self.stage_slots()
        optional = [s for s in slots if s.optional]
        if not optional:
            return None
        node = next((s for s in optional if s.step == step), optional[0])
        after = -1
        position = 0
        for slot in slots:
            if slot.optional:
                continue
            if slot.bar_index < node.bar_index:
                after = position  # 真实步骤里的下标（每过一个真实步骤 +1）
            position += 1
        return after

    def slot_of(self, step: str) -> StageSlot | None:
        """按**界面步骤 key** 找它在本流程里的槽位；不在流程里返回 ``None``。"""
        for slot in self.stage_slots():
            if slot.step == step:
                return slot
        return None

    def bar_index_of(self, step: str) -> int | None:
        """界面步骤 → 步骤条上的格序（``bar_index``）；不在流程里返回 ``None``。"""
        slot = self.slot_of(step)
        return None if slot is None else slot.bar_index

    def step_at(self, bar_index: int) -> str | None:
        """步骤条格序 → 界面步骤 key（点节点后的反查）。"""
        for slot in self.stage_slots():
            if slot.bar_index == bar_index:
                return slot.step
        return None

    def contains(self, stage: str) -> bool:
        """这个运行阶段在**本流程**里吗（详情页判断该不该显示某一步用）。"""
        return stage in self.stages

    # ------------------------------------------------------------ 构造
    def with_edges(self, edges: list[FlowEdge]) -> "FlowDefinition":
        """以本流程为底、替换连线表，返回**新**对象（编辑器改线用）。"""
        grouped: dict[tuple[str, str], list[FlowEdge]] = {}
        for edge in edges:
            grouped.setdefault((edge.consumer, edge.port), []).append(edge)
        return FlowDefinition(self.stages, grouped)

    @classmethod
    def default(cls) -> "FlowDefinition":
        """默认流程：**从 ports 的静态表派生**，不在这里另写一份连线。

        - 无条件边逐条抄 :data:`~desktop.steps.ports.SUPPLIERS`；
        - 条件边从 :func:`desktop.steps.ports.print_input_overrides` 派生：
          覆盖表里哪个端口的供给方和静态表不一样，哪条就是条件边
          （条件名 :data:`CONDITION_IMPOSITION`）——「拼版生效换上游」在
          ports 里已有唯一声明，这里只把它翻译成边；
        - 节点顺序 = 消费方在 ``SUPPLIERS`` 里的声明顺序做拓扑稳定排序
          （默认表本身就是依赖序，派生结果与其一致）。
        """
        edges: list[FlowEdge] = []
        for consumer, wiring in ports.SUPPLIERS.items():
            for port, supplier in wiring.items():
                edges.append(FlowEdge(supplier, consumer, port))
        for (stage, port), supplier in ports.print_input_overrides(True).items():
            if supplier != ports.supplier_of(stage, port):
                edges.append(
                    FlowEdge(supplier, stage, port, CONDITION_IMPOSITION)
                )
        flow = cls((), {}).with_edges(edges)

        stages: list[str] = []
        appearing = list(ports.SUPPLIERS) + [
            e.supplier for e in flow.suppliers()
            if e.supplier != ports.SUPPLY_TASK_SOURCE
        ]
        for stage in appearing:
            if stage not in stages and stage in ports.STAGE_STEPS:
                stages.append(stage)
        flow.stages = cls._topo(stages, flow)
        return flow

    @staticmethod
    def _topo(candidates: list[str], flow: "FlowDefinition") -> tuple[str, ...]:
        """稳定拓扑排序：每次取"上游都已排好"的第一个候选（默认表天然满足）。"""
        remaining = [s for s in candidates]
        placed: list[str] = []
        placed_set: set[str] = set()
        while remaining:
            for stage in remaining:
                upstreams = {
                    supplier
                    for port, supplier in flow._inputs_of(stage)
                    if supplier != ports.SUPPLY_TASK_SOURCE
                }
                if upstreams <= placed_set:
                    placed.append(stage)
                    placed_set.add(stage)
                    remaining.remove(stage)
                    break
            else:
                # 有环/缺上游也把剩下的按声明顺序兜底放进去（不丢节点）。
                placed.extend(remaining)
                break
        return tuple(placed)

    @classmethod
    def load(cls, path: Path | str) -> "FlowDefinition":
        """从 ``flow.bpmn`` 读回流程定义；文件缺失/结构不对抛 :class:`ValueError`。

        ⚠️ 宿主（如 :class:`desktop.store.TaskMixin`）对**手编坏文件**应有
        兜底（回落默认流程），别让一个写坏的 XML 拖死整个任务。
        """
        path = Path(path)
        if not path.is_file():
            raise ValueError(f"流程定义文件不存在：{path}")
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            raise ValueError(f"流程定义不是合法 XML：{path}（{exc}）") from exc

        process = next(
            (el for el in root if _local(el.tag) == "process"), None
        )
        if process is None:
            raise ValueError(f"流程定义里没有 <process>：{path}")

        stages: list[str] = []
        edges: list[FlowEdge] = []
        for element in process:
            kind = _local(element.tag)
            if kind == "task":
                stage = element.get(_q(GUJI_NS, "stage")) or element.get("id", "")
                if stage not in ports.STAGE_STEPS:
                    raise ValueError(
                        f"流程定义里有未知阶段 {stage!r}（不在 STAGE_STEPS）：{path}"
                    )
                stages.append(stage)
            elif kind == "sequenceFlow":
                port = element.get(_q(GUJI_NS, "port")) or "pages"
                if port not in ports.PORT_ARTIFACTS:
                    raise ValueError(
                        f"连线 {element.get('id')!r} 用了未知端口 {port!r}：{path}"
                    )
                supplier = element.get("sourceRef", "")
                if supplier == "start":
                    supplier = ports.SUPPLY_TASK_SOURCE
                edges.append(
                    FlowEdge(
                        supplier,
                        element.get("targetRef", ""),
                        port,
                        element.get(_q(GUJI_NS, "condition")) or None,
                    )
                )
        if not stages:
            raise ValueError(f"流程定义里一个步骤节点都没有：{path}")
        return cls(tuple(stages), {}).with_edges(edges)


def default_flow_path(task_dir: Path | str) -> Path:
    """任务目录里流程定义文件的标准位置（``tasks/<任务号>/flow.bpmn``）。"""
    return Path(task_dir) / FLOW_FILENAME
