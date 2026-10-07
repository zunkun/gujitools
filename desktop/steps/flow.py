# -*- coding: utf-8 -*-
"""任务**流程定义**：把「这条任务走哪些步骤、谁喂谁」从硬编码搬进一份 BPMN 文件。

用户 2026-10-05 的口径（``docs/tasks/bpm.md``）：

> 按照现有流程，生成默认 task_default.bpmn 文件, bpm 驱动节点

定位（与 :mod:`desktop.steps.ports` 的分工）：

- **ports 是"步骤怎么连"的静态事实来源**——:data:`~desktop.steps.ports.SUPPLIERS`
  写死了默认流程的每条边；落点表 :data:`~desktop.steps.ports.STAGE_LOCATIONS`
  写死了产物放在任务目录哪里。它们**不会**被本模块替代；
- **flow 是"这一次任务按什么流程跑"的运行时载体**——默认从 ports 派生
  （``FlowDefinition.default()``，两者逐边相等，自测钉死），序列化成
  BPMN 2.0 兼容子集存进 ``tasks/<任务号>/flow.bpmn``（建任务时生成）；
  自定义流程 = 换这份文件，算法、落点、界面代码全都不动。

BPMN 子集（只取表达本仓库流程所需的最小面，不做完整 BPMN 引擎）：

.. code-block:: xml

    <bpmn:definitions xmlns:bpmn="…" xmlns:guji="…">
      <bpmn:process id="guji_task" isExecutable="false">
        <bpmn:startEvent id="start" name="源 PDF"/>
        <bpmn:task id="extract" name="提取PDF图片" guji:stage="extract"/>
        …
        <bpmn:endEvent id="end" name="完成"/>
        <bpmn:sequenceFlow id="f0" sourceRef="start" targetRef="extract"
                           guji:port="pdf"/>
        <bpmn:sequenceFlow id="f5" sourceRef="imposition" targetRef="print"
                           guji:port="pages" guji:condition="imposition"/>
      </bpmn:process>
    </bpmn:definitions>

- **task 节点 = 运行阶段**（``STAGE_STEPS`` 的键，含 ``rembg_submit`` 这个
  二段动作；不是步骤 key——BPM 驱动的是"跑什么动作"）。节点 ``id`` 即阶段名，
  ``guji:stage`` 冗余存一份做显式标记；界面文案用 ``name``，仅作展示、
  不作解析依据（解析只认 ``guji:stage``）。
- **sequenceFlow = 一条边**：``sourceRef`` 供给方（``start`` 事件映射回
  :data:`~desktop.steps.ports.SUPPLY_TASK_SOURCE` 哨兵），``guji:port``
  标注喂的是消费方哪个端口——**端口级连线必须显式**，因为同一个上游可能
  产出多种产物（extract 出 pages，rembg 也出 pages），只靠节点序列推不出来。
- **条件连线**用 ``guji:condition`` 表达（BPMN 标准做法是在连线上挂条件表达式，
  这里用仓库自己的命名空间存条件**名**）：解析时按上下文标志位选边——
  名字对应的标志为真时走这条，否则走无条件边。现有唯一一条是
  「拼版生效 → print 改吃 imposition」（由
  :func:`desktop.steps.ports.print_input_overrides` 派生，不另写一份）。

⚠️ 本模块**纯逻辑、不 import 任何 Qt**（与 ports/spec 同一约束），可以被
自测、CLI 与将来的 BPM 编辑面板安全导入。
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from desktop.steps import ports

#: BPMN 2.0 标准命名空间（写文件用前缀 ``bpmn:``，读文件按命名空间解析）。
BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
#: BPMN 2.0 **图形交换**（DI）命名空间：节点框坐标与连线折点都在这一段里。
#: 这是 BPMN 2.0 存布局的标准位置——流程图编辑器拖出来的节点位置就该落在
#: ``bpmndi:BPMNShape/dc:Bounds`` 上，而不是我们自造一个旁挂的 JSON。
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
#: OMG DC（Drawing Canvas）命名空间：``dc:Bounds`` / ``dc:Point``。
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
#: OMG DI（Diagram Interchange）命名空间：``di:waypoint``（连线的折点）。
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
#: 本仓库的 BPMN 扩展命名空间（``guji:stage`` / ``guji:port`` / ``guji:condition``）。
GUJI_NS = "https://guji.tools/bpmn/2025"

#: BPMN 2.0 XSD 位置（写进 ``xsi:schemaLocation``，让校验器/编辑器知道按哪版校验）
BPMN_XSD = "http://www.omg.org/spec/BPMN/20100524/MODEL/BPMN20.xsd"

#: 任务目录里流程定义文件的固定名（``tasks/<任务号>/flow.bpmn``）。
FLOW_FILENAME = "flow.bpmn"

#: ``guji:condition`` 现有唯一的条件名：拼版是否生效（用户在详情页的
#: 「启用拼版」开关）。:meth:`TaskStore.stage_input` 按它传上下文。
CONDITION_IMPOSITION = "imposition"


def _q(ns: str, tag: str) -> str:
    """命名空间限定名（ElementTree 需要 ``{ns}tag`` 形状）。"""
    return f"{{{ns}}}{tag}"


def _local(tag: str) -> str:
    """剥掉 ``{ns}`` 前缀取局部名（读文件时不用关心命名空间具体串）。"""
    return tag.rsplit("}", 1)[-1]


# ---------------------------------------------------------------- 节点与边
@dataclass(frozen=True)
class FlowEdge:
    """一条连线：``supplier`` 阶段的 ``port`` 端口产物喂给 ``consumer`` 阶段。

    ``condition`` 为 ``None`` 表示**无条件边**（默认路径）；否则是条件名
    （如 ``"imposition"``），解析时按上下文标志位决定走不走它。
    """

    supplier: str
    consumer: str
    port: str
    condition: str | None = None


@dataclass(frozen=True)
class StageSlot:
    """**界面槽位**：BPMN 节点折叠到界面步骤条上的一格。

    ⚠️ 为什么要这层折叠——BPMN 的节点是**运行阶段**，界面步骤条上的格子是
    **界面步骤**，两者不是一一对应：

    - ``rembg_submit`` 是第三步「图片去底色」面板上的第二个动作（提交），
      进度也显示在第三步 ⇒ 折叠进 ``rembg`` 那一格，不单独占格；
    - ``imposition`` 是**条件伪步骤**（``StepSpec.role == "optional"``），
      流程里有它，但界面上是否出现由运行态决定（第三步区域模式为 1 才出现）。

    两个下标各管一件事，别混：

    - ``bar_index``：在**步骤条上**的显示次序（自定义流程换顺序就变它）；
    - ``stack_index``：在 ``control_stack`` / ``preview_stack`` 里的页号。
      真实步骤按流程顺序排名，可选节点统一排在真实步骤之后（沿用既有的
      「伪步骤占最后一位」约定），这样两个栈的**建页顺序不用动**。
    """

    step: str
    stage: str
    optional: bool = False
    bar_index: int = 0
    stack_index: int = 0
    #: 这一格**有没有接上真实功能**（2026-10-05）。
    #:
    #: ``False`` = 用户在流程图上画了一个本程序**还没有对应实现**的节点
    #: （例如 bpmn.io 里随手加的「OCR 识别」）。这类节点**不再被静默丢掉**：
    #: 它在步骤条上占一格、显示为**灰节点**、标着"未接入"，点它会告诉用户
    #: 怎么接上（改名成已有步骤名）或怎么删掉。
    #:
    #: ⚠️ 之前它们被 ``continue`` 直接跳过 ⇒ 图上画了、界面上却找不到
    #: （"流程节点不能完全映射"最明显的一条）。
    mapped: bool = True
    #: 该格在步骤条上的**显示名**（只有未接入的节点用它；已接入的仍走
    #: ``ports.stage_label``，不另写一份文案）。
    name: str = ""

    @property
    def label(self) -> str:
        """步骤条上显示的中文名（已接入的走 :func:`ports.stage_label`）。"""
        if not self.mapped:
            # 未接入的节点没有官方中文名，显示用户自己在图上写的那个
            return self.name or self.step
        return ports.stage_label(self.stage)


@dataclass
class FlowLayout:
    """流程的**图形布局**：节点框位置 + 连线折点（BPMN DI 段的来源）。

    坐标单位是 BPMN ``dc:Bounds`` 的用户单位（1 ≈ 1px，本项目不缩放）。

    ⚠️ **纯数据、纯计算，不 import Qt**（与本模块其余部分同一约束）：它既是
    :meth:`FlowDefinition.to_xml` 写 DI 段的数据源，也是 GUI 画布（需要
    ``QPointF``）的换算依据。GUI 侧只做类型转换，几何算法**只有这一份**。

    - ``boxes``：``节点 id → (x, y, w, h)``，缺节点按 :meth:`auto` 补；
    - :meth:`node_box` 返回矩形 :meth:`auto` 生成的节点，:meth:`edge_points`
      返回 :meth:`route` 生成的折点。
    """

    boxes: dict[str, tuple[float, float, float, float]] = field(
        default_factory=dict
    )
    #: 排了几行（:meth:`auto` 填）。**不参与序列化**——它能从 ``boxes`` 算出来，
    #: 只是给"绕行留白/行距"用，省得每次都重算 max。
    _row_count: int = field(default=1, repr=False)
    #: 事件圆直径 / 任务框尺寸 / 节点间距 / 画布留白（与 GUI 画布共用口径）
    EVENT_SIZE = 36.0
    NODE_SIZE = (148.0, 56.0)
    GAP = 56.0
    PADDING = 22.0
    #: 条件边绕行那一行的额外高度
    BYPASS_ROW = 44.0
    #: 折行时**行与行之间**的垂直间距（比行内间距大，让两条连线不粘在一起）
    ROW_GAP = 40.0

    @classmethod
    def auto(cls, flow: "FlowDefinition", max_width: float | None = None
             ) -> "FlowLayout":
        """默认排布：``start → 节点… → end``。

        :param max_width:
            ``None``（默认）= 强制**一行到底**，落进 ``flow.bpmn`` 的 DI 段
            用这个——文件里的坐标要稳定可预期，不能随打开它的窗口宽度变。

            给定宽度时**超宽就折行**：默认流程 8 个节点一字排开约 1400px，
            弹窗/面板通常只有 1000 出头，不折行的话右侧节点被横向滚动条
            挡住——用户在"创建任务"弹窗里一眼看不完整个流程，这正是
            入口该做到的事。

        有条件边时底部**多留一行** ``BYPASS_ROW``——条件边要从节点底下绕
        过去，留白不够那条线会被裁掉（现象是"虚线条件边看不见"）。
        折行时每行都按需留绕行空间（绕行路径按行数逐层下移）。
        """
        layout = cls()
        nodes = _diagram_nodes(flow)
        limit = max_width if max_width and max_width > 0 else None
        # 折行时先算每行能放几个：按"节点宽 + 间距"贪心装，装不下的换行。
        per_row = len(nodes)
        if limit is not None:
            per_row = cls._nodes_per_row(nodes, limit)

        y = cls.PADDING
        x = cls.PADDING
        row = 0
        index = 0
        while index < len(nodes):
            # 本行节点：按 per_row 切一段
            chunk = nodes[index:index + per_row]
            # ⚠️ 每行**按实际节点数居中**：末行往往只有两三个节点，若一律
            # 从左边起排，右边会空一大块、整张图看着"歪向左上"（折行只解决
            # 装不下的问题，观感问题得靠居中）。
            row_width = sum(
                cls.EVENT_SIZE if n in ("start", "end") else cls.NODE_SIZE[0]
                for n in chunk
            ) + cls.GAP * (len(chunk) - 1)
            x = cls.PADDING + max(
                0.0, (cls.widest_row(nodes, per_row) - row_width) / 2
            )
            for node_id in chunk:
                if node_id in ("start", "end"):
                    size = cls.EVENT_SIZE
                    top = y + (cls.NODE_SIZE[1] - size) / 2
                else:
                    size = None
                    top = y
                box = layout.boxes.get(node_id)
                if box is None:
                    layout.boxes[node_id] = (
                        x, top,
                        size if size is not None else cls.NODE_SIZE[0],
                        size if size is not None else cls.NODE_SIZE[1],
                    )
                else:
                    # 已有坐标：保留用户拖的位置，只补尺寸
                    layout.boxes[node_id] = (box[0], box[1], box[2], box[3])
                x += (size or cls.NODE_SIZE[0]) + cls.GAP
            index += per_row
            if index < len(nodes):
                # 换行：y 下移一整行（含上一行可能需要的绕行留白）
                y += cls.NODE_SIZE[1] + cls.BYPASS_ROW + cls.ROW_GAP
                row += 1
        layout._row_count = row + 1
        return layout

    @classmethod
    def widest_row(cls, nodes: list[str], per_row: int) -> float:
        """折行后**最宽那一行**的节点带宽度（不含留白，用来把各行居中）。"""
        widest = 0.0
        for start in range(0, len(nodes), per_row):
            chunk = nodes[start:start + per_row]
            widest = max(widest, sum(
                cls.EVENT_SIZE if n in ("start", "end") else cls.NODE_SIZE[0]
                for n in chunk
            ) + cls.GAP * (len(chunk) - 1))
        return widest

    @classmethod
    def _nodes_per_row(cls, nodes: list[str], max_width: float) -> int:
        """给定宽度，一行最多放几个节点（贪心装，至少 2 个）。

        ⚠️ 至少 2：只有 1 个/行的折行比不折还难看（每个节点独占一整行，
        竖向拉得极长）。宁可让那一行稍微超宽、出横向滚动条。
        """
        total = 0.0
        count = 0
        for node_id in nodes:
            w = cls.EVENT_SIZE if node_id in ("start", "end") else cls.NODE_SIZE[0]
            need = w if count == 0 else cls.GAP + w
            if count and total + need > max_width and count >= 2:
                break
            total += need
            count += 1
        return max(count, 2)

    # ------------------------------------------------------------ 查询
    def node_box(self, node_id: str) -> tuple[float, float, float, float]:
        """节点矩形 ``(x, y, w, h)``；没有就按默认排布补一个。"""
        if node_id not in self.boxes:
            raise KeyError(f"布局里没有节点 {node_id!r}")
        return self.boxes[node_id]

    def has(self, node_id: str) -> bool:
        return node_id in self.boxes

    def move(self, node_id: str, x: float, y: float) -> None:
        """拖动节点：只改左上角坐标，**尺寸不变**（拖拽不改语义）。"""
        if node_id in self.boxes:
            box = self.boxes[node_id]
            self.boxes[node_id] = (float(x), float(y), box[2], box[3])

    def remove(self, node_id: str) -> None:
        self.boxes.pop(node_id, None)

    # ------------------------------------------------------------ 连线折点
    def edge_points(self, source: str, consumer: str,
                    landing: int = 0, total: int = 1
                    ) -> list[tuple[float, float]]:
        """一条无条件连线的折点（``di:waypoint`` 序列）。

        源点取源框**右缘中点**，终点取目标框**左缘中点**——与 GUI 画布
        (:mod:`desktop.components.flow_view`) 的画法一致，两边不会画出
        两条不一样的线。

        - ``landing`` / ``total``：这条边在"进 ``consumer`` 的所有边"里排第
          几、共几条。**必须错开落点**（纵向均分），否则多条边画成同一条线，
          只看得出最后画的那条（默认流程 ``rembg``/``print`` 都有多条入边）。
        """
        src = self.boxes.get(source)
        dst = self.boxes.get(consumer)
        if src is None or dst is None:
            return []
        start = (src[0] + src[2], src[1] + src[3] / 2)
        end = (dst[0], dst[1] + dst[3] / 2 + self._landing_offset(landing, total))
        if abs(start[1] - end[1]) < 1.0:
            return [start, end]
        row_y = self.bypass_y()
        if end[0] <= start[0]:
            return [start, (start[0], row_y), (end[0], row_y), end]
        mid = (start[0] + end[0]) / 2
        return [start, (mid, start[1]), (mid, end[1]), end]

    def bypass_points(self, source: str, consumer: str,
                      landing: int = 0, total: int = 1
                      ) -> list[tuple[float, float]]:
        """条件边的折点：**永远绕行**（不因同行就直连）。"""
        src = self.boxes.get(source)
        dst = self.boxes.get(consumer)
        if src is None or dst is None:
            return []
        start = (src[0] + src[2], src[1] + src[3] / 2)
        end = (dst[0], dst[1] + dst[3] / 2 + self._landing_offset(landing, total))
        row_y = self.bypass_y()
        return [start, (start[0], row_y), (end[0], row_y), end]

    #: 同目标多条边的落点纵向间距（px）
    LANDING_GAP = 16.0

    def _landing_offset(self, landing: int, total: int) -> float:
        """第 ``landing`` 条（共 ``total`` 条）入边的纵向偏移：整体居中均分。"""
        if total <= 1:
            return 0.0
        return (landing - (total - 1) / 2) * self.LANDING_GAP

    def bypass_y(self) -> float:
        """条件边绕行那一行的 y（所有节点下方、留白之内）。"""
        if not self.boxes:
            return self.PADDING
        bottom = max(box[1] + box[3] for box in self.boxes.values())
        return bottom + self.BYPASS_ROW / 2

    # ------------------------------------------------------------ 序列化
    def to_dict(self) -> dict[str, list[float]]:
        return {key: list(box) for key, box in self.boxes.items()}

    @classmethod
    def from_dict(cls, raw: dict | None) -> "FlowLayout":
        """从 :meth:`to_dict` 的结构还原；**忽略尺寸为 0 的坏数据**。"""
        layout = cls()
        for key, value in (raw or {}).items():
            try:
                numbers = tuple(float(v) for v in value)
            except (TypeError, ValueError):
                continue
            if len(numbers) == 4 and numbers[2] > 0 and numbers[3] > 0:
                layout.boxes[key] = numbers  # type: ignore[assignment]
        return layout


def _diagram_nodes(flow: "FlowDefinition") -> list[str]:
    """图形段里该画哪些节点：``start`` + 运行阶段 + ``end``。"""
    return ["start", *flow.stages, "end"]


@dataclass
class FlowDefinition:
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

    def suppliers(self) -> list[FlowEdge]:
        """全部边（扁平化，节点编辑器/自测遍历用）。"""
        return [edge for group in self.edges.values() for edge in group]

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

        1. ``rembg_submit`` 折叠进 ``rembg`` 格（它是第三步的第二个动作，
           进度也归第三步）⇒ 运行阶段 6 个、界面格子 4 个 + 拼版 1 个；
        2. 同一格重复出现时**保留第一次**的位置（``rembg_submit`` 紧跟
           ``rembg`` 时不会把它顶到后面去）；
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
                continue  # 折叠：rembg_submit 并进 rembg，保持首次出现的位置
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
        位插到最后"处理，拼版被排到了「生成PDF」后面（任务 #0027）。
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

    # ------------------------------------------------------------ 序列化
    def to_xml(self, layout: "FlowLayout | None" = None) -> bytes:
        """序列化成 BPMN 2.0 文件（``flow.bpmn`` 的内容）。

        结构分两段，**都是 BPMN 2.0 标准件**，不是自定义格式：

        - ``bpmn:process``——语义段：``startEvent`` / ``task`` / ``endEvent``
          与 ``sequenceFlow``。连线带**双向引用**：``sourceRef``/``targetRef``
          属性给解析用，``<bpmn:incoming>``/``<bpmn:outgoing>`` 子元素给
          图形工具用（缺了它们，标准 BPMN 渲染器画不出箭头）；
        - ``bpmndi:BPMNDiagram``——**图形段（DI）**：每个节点一个
          ``bpmndi:BPMNShape`` 带 ``dc:Bounds``（x/y/width/height），
          每条连线一个 ``bpmndi:BPMNEdge`` 带若干 ``di:waypoint``。

        ⚠️ 节点坐标**存在 DI 段的 ``dc:Bounds`` 里**，这正是流程编辑器
        （含本项目 M4 的拖拽画布）读写布局的标准位置。``layout`` 缺省时给
        一份默认横向排布，���证文件在任何工具里打开都有完整图形。
        """
        ET.register_namespace("bpmn", BPMN_NS)
        ET.register_namespace("bpmndi", BPMNDI_NS)
        ET.register_namespace("dc", DC_NS)
        ET.register_namespace("di", DI_NS)
        ET.register_namespace("guji", GUJI_NS)
        definitions = ET.Element(
            _q(BPMN_NS, "definitions"),
            {
                "id": "guji-definitions",
                "targetNamespace": GUJI_NS,
                "exporter": "guji",
                "exporterVersion": "1.0",
            },
        )
        process = ET.SubElement(
            definitions,
            _q(BPMN_NS, "process"),
            {"id": "guji_task", "isExecutable": "false"},
        )

        edges = self.suppliers()
        # 连线 id 要**先**定下来：节点的 <incoming>/<outgoing> 得引用它们
        flow_ids = {id(edge): f"flow{index}" for index, edge in enumerate(edges)}
        incoming: dict[str, list[str]] = {}
        outgoing: dict[str, list[str]] = {}
        for edge in edges:
            source = (
                "start"
                if edge.supplier == ports.SUPPLY_TASK_SOURCE
                else edge.supplier
            )
            outgoing.setdefault(source, []).append(flow_ids[id(edge)])
            incoming.setdefault(edge.consumer, []).append(flow_ids[id(edge)])

        def _refs(parent, tag: str, values: list[str]) -> None:
            for value in values:
                ET.SubElement(parent, _q(BPMN_NS, tag)).text = value

        start = ET.SubElement(
            process, _q(BPMN_NS, "startEvent"),
            {"id": "start", "name": "源 PDF"},
        )
        _refs(start, "outgoing", outgoing.get("start", []))

        nodes: list[tuple[str, str]] = [("start", "源 PDF")]
        for stage in self.stages:
            # ⚠️ 走 ports.stage_label 而不是 spec.stage_name()：后者对
            #    ``rembg_submit`` 会回落到 ``rembg`` 的名字，流程图上就出现
            #    **两个「图片去底色」**节点，用户分不清哪个是提交定稿。
            name = ports.stage_label(stage)
            task = ET.SubElement(
                process, _q(BPMN_NS, "task"),
                {"id": stage, "name": name, _q(GUJI_NS, "stage"): stage},
            )
            _refs(task, "incoming", incoming.get(stage, []))
            _refs(task, "outgoing", outgoing.get(stage, []))
            nodes.append((stage, name))

        ET.SubElement(
            process, _q(BPMN_NS, "endEvent"), {"id": "end", "name": "完成"}
        )
        # ⚠️ end 事件也要进 DI 段：漏了它，BPMN 工具打开时流程图**没有终点**
        # （语义段有、图形段没有——这类"两段不一致"最难查，标准渲染器只读 DI）。
        nodes.append(("end", "完成"))

        for edge in edges:
            source = (
                "start"
                if edge.supplier == ports.SUPPLY_TASK_SOURCE
                else edge.supplier
            )
            attrs = {
                "id": flow_ids[id(edge)],
                "sourceRef": source,
                "targetRef": edge.consumer,
                _q(GUJI_NS, "port"): edge.port,
            }
            if edge.condition:
                attrs[_q(GUJI_NS, "condition")] = edge.condition
            ET.SubElement(process, _q(BPMN_NS, "sequenceFlow"), attrs)

        if layout is None:
            layout = FlowLayout.auto(self)
        self._append_di(definitions, nodes, edges, flow_ids, layout)

        ET.indent(definitions, space="  ")
        return ET.tostring(definitions, encoding="utf-8", xml_declaration=True)

    def _append_di(self, definitions, nodes, edges, flow_ids,
                   layout: "FlowLayout") -> None:
        """补上 ``bpmndi:BPMNDiagram`` 图形段（坐标 + 连线折点）。"""
        diagram = ET.SubElement(
            definitions, _q(BPMNDI_NS, "BPMNDiagram"), {"id": "guji-diagram"}
        )
        plane = ET.SubElement(
            diagram, _q(BPMNDI_NS, "BPMNPlane"),
            {"id": "guji-plane", "bpmnElement": "guji_task"},
        )
        for node_id, _name in nodes:
            box = layout.node_box(node_id)
            shape = ET.SubElement(
                plane, _q(BPMNDI_NS, "BPMNShape"),
                {
                    "id": f"{node_id}_di",
                    "bpmnElement": node_id,
                    # 事件是圆、任务是圆角矩形：isMarkerVisible 之外的形状由
                    # 渲染器按元素类型自己定，这里只给几何。
                    "isHorizontal": "true",
                },
            )
            ET.SubElement(
                shape, _q(DC_NS, "Bounds"),
                {
                    "x": f"{box[0]:.0f}",
                    "y": f"{box[1]:.0f}",
                    "width": f"{box[2]:.0f}",
                    "height": f"{box[3]:.0f}",
                },
            )
        # 每条边在"进其消费方的所有边"里的序号（落点纵向错开，见 edge_points）
        grouped: dict[str, list] = {}
        for edge in edges:
            grouped.setdefault(edge.consumer, []).append(edge)
        landing_index: dict[int, int] = {}
        landing_total: dict[str, int] = {}
        for consumer, group in grouped.items():
            for order, edge in enumerate(group):
                landing_index[id(edge)] = order
            landing_total[consumer] = len(group)
        for edge in edges:
            source = (
                "start"
                if edge.supplier == ports.SUPPLY_TASK_SOURCE
                else edge.supplier
            )
            order = landing_index[id(edge)]
            total = landing_total[edge.consumer]
            # ⚠️ 条件边**永远绕行**（与 GUI 画布 ``_bypass_points`` 同一口径）：
            # 它是"命中才走"的备选路径，画成与主路径重合的直线就等于没画。
            if edge.condition:
                points = layout.bypass_points(source, edge.consumer, order, total)
            else:
                points = layout.edge_points(source, edge.consumer, order, total)
            edge_el = ET.SubElement(
                plane, _q(BPMNDI_NS, "BPMNEdge"),
                {"id": f"{flow_ids[id(edge)]}_di", "bpmnElement": flow_ids[id(edge)]},
            )
            for x, y in points:
                ET.SubElement(
                    edge_el, _q(DI_NS, "waypoint"),
                    {"x": f"{x:.0f}", "y": f"{y:.0f}"},
                )

    def save(self, path: Path | str, layout: "FlowLayout | None" = None) -> Path:
        """原子落盘（写 ``.part`` 再 ``os.replace``，防半截文件）。

        ``layout`` 缺省给默认排布——文件在任何 BPMN 工具里打开都有完整图形。
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, part_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=path.name + ".", suffix=".part"
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(self.to_xml(layout))
            os.replace(part_name, path)
        except BaseException:
            try:
                os.unlink(part_name)
            except OSError:
                pass
            raise
        return path

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

    @staticmethod
    def load_layout(path: Path | str) -> FlowLayout:
        """从 ``flow.bpmn`` 的 **DI 段**读回节点坐标（拖拽结果）。

        读不到 / 文件坏 / 缺 DI 段时**回默认排布**并按实际节点集合补全——
        布局是"锦上添花"，缺了不该让流程定义整个打不开（:meth:`load` 才负责
        语义校验）。
        """
        path = Path(path)
        if not path.is_file():
            return FlowLayout()
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            return FlowLayout()
        layout = FlowLayout()
        for shape in root.iter(_q(BPMNDI_NS, "BPMNShape")):
            node_id = shape.get("bpmnElement", "")
            bounds = shape.find(_q(DC_NS, "Bounds"))
            if not node_id or bounds is None:
                continue
            try:
                layout.boxes[node_id] = (
                    float(bounds.get("x", 0)),
                    float(bounds.get("y", 0)),
                    float(bounds.get("width", 0)),
                    float(bounds.get("height", 0)),
                )
            except (TypeError, ValueError):
                continue
        return layout


def default_flow_path(task_dir: Path | str) -> Path:
    """任务目录里流程定义文件的标准位置（``tasks/<任务号>/flow.bpmn``）。"""
    return Path(task_dir) / FLOW_FILENAME


__all__ = [
    "BPMNDI_NS",
    "BPMN_NS",
    "CONDITION_IMPOSITION",
    "DC_NS",
    "DI_NS",
    "FLOW_FILENAME",
    "FlowDefinition",
    "FlowEdge",
    "FlowLayout",
    "GUJI_NS",
    "StageSlot",
    "default_flow_path",
]
