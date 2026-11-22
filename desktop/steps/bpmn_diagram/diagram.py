# -*- coding: utf-8 -*-
"""``FlowDiagram`` 本体：字段定义 + 各职责 mixin 的组合。"""

from __future__ import annotations

from dataclasses import dataclass, field

from desktop.steps.bpmn_diagram.elements import DiagramFlow, DiagramNode, DiagramNote
from desktop.steps.bpmn_diagram.layout import _LayoutMixin
from desktop.steps.bpmn_diagram.query import _QueryMixin
from desktop.steps.bpmn_diagram.routing import _RoutingMixin
from desktop.steps.bpmn_diagram.serialization import _SerializationMixin
from desktop.steps.bpmn_diagram.slots import _SlotMixin


@dataclass
class FlowDiagram(
    _QueryMixin,
    _SlotMixin,
    _LayoutMixin,
    _SerializationMixin,
    _RoutingMixin,
):
    """一张完整的流程图：节点 + 连线 + 坐标（= bpmn 文件的全部内容）。

    ``boxes`` / ``waypoints`` 直接来自文件的 **DI 段**（``dc:Bounds`` /
    ``di:waypoint``）——这正是 bpmn.io 等编辑器存布局的地方，所以"页面上看到
    的"与"文件里存下的"是同一份坐标。文件没有 DI 段时按 :meth:`auto_layout`
    兜底排一份。
    """

    nodes: tuple[DiagramNode, ...] = ()
    flows: tuple[DiagramFlow, ...] = ()
    #: 节点旁的**文字注释**（``textAnnotation`` + ``association``，见
    #: :class:`DiagramNote`）。只显示、不参与运行，但要往返保真。
    notes: tuple[DiagramNote, ...] = ()
    #: 注释的挂接关系：注释 id → 它挂在哪个节点上（``association`` 的 sourceRef）
    note_links: dict[str, str] = field(default_factory=dict)
    boxes: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    waypoints: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    #: 流程 id（文件里的 ``bpmn:process/@id``，往返时原样写回）
    process_id: str = "guji_task"
    #: **节点号水位**（``Node_<n>`` 里已分配到的最大 ``n``，只增不减）。
    #:
    #: ⚠️ 为什么需要它：节点 id 若按"当前节点数 + 1"生成，**删掉最后一个节点
    #: 再加一个就会复用同一个 id** ⇒ 副本产物目录 / 参数草稿按 id 命名时，
    #: 新节点会读到已删节点的残留（串味）。水位保证 id **永不复用**（与任务号
    #: 水位同一思路，见 ``desktop.store.tasks`` 的 ``_bump_max_allocated``）。
    #: 落盘在 ``bpmn:process`` 的 ``guji:node_seq`` 属性；老图（默认模板/bpmn.io
    #: 画的图）没有该属性时，从现有 ``Node_<n>`` id 反推最大值兜底。
    node_seq: int = 0
