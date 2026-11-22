# -*- coding: utf-8 -*-
"""BPMN 2.0 流程图的**忠实模型**：文件是唯一真源，页面照着它渲染与编辑。

## 为什么另起一个模型（与 :mod:`desktop.steps.flow` 的分工）

:mod:`~desktop.steps.flow` 的 ``FlowDefinition`` 是**运行语义**模型：它把流程
表达成「端口级边表」``(consumer, port) → supplier``——那是为了回答"这一步该去
谁那儿取产物"。它**不是**流程图，页面拿它渲染只能自己算坐标、自己猜图形。

本模块是**图形模型**：节点带 BPMN 元素类型（task / exclusiveGateway /
startEvent / …）、带文件里 DI 段的真实坐标，连线带折点。页面（
:class:`desktop.components.bpmn_view.BpmnView`）照着它画，**看到的就是文件里
画的**——用 bpmn.io 画的图，进页面长得一样。

## 为什么不做完整 BPMN 引擎

用户 2026-10-05 的口径：

> 后端驱动可以使用状态机来实现，bpm 流程引擎太复杂

所以这里**只做"读得懂、画得出、改得动"**：认识本工具用得到的元素类型，
不认识的原样保留（``kind`` 存原始标签名，绘图时按类型降级成矩形）。语义
（谁先谁后、跳过谁）由运行时的状态机负责，不在这里推导。

⚠️ 本模块**纯数据 + 纯 XML，不 import Qt**（与 ports/spec/flow 同一约束），
可以被子进程、CLI、自测安全导入。

2026-11-22 起按职责拆成子包（原文件 1530 行）：常量在 :mod:`.constants`、
数据类在 ``elements``、纯函数助手在 ``helpers``、``FlowDiagram`` 的查询/排布/
序列化/走线/界面投影分别在 ``query`` / ``layout`` / ``serialization`` /
``routing`` / ``slots``，类本体在 ``diagram``。本 ``__init__`` 只做重导出，
既有 ``from desktop.steps.bpmn_diagram import X`` 全部不变；子模块之间不要
反过来导入本包（会形成循环）。
"""

from desktop.steps.bpmn_diagram.constants import (
    AUTO_GAP_X,
    AUTO_GAP_Y,
    AUTO_PADDING,
    BPMNDI_NS,
    BPMN_NS,
    CORNER_CELL_EPS,
    DC_NS,
    DEFAULT_SIZE,
    DI_NS,
    EVENT_KINDS,
    FALLBACK_SIZE,
    GATEWAY_KINDS,
    GUJI_NS,
    KIND_END,
    KIND_EXCLUSIVE,
    KIND_INCLUSIVE,
    KIND_INTERMEDIATE,
    KIND_PARALLEL,
    KIND_START,
    KIND_TASK,
    KNOWN_KINDS,
    LAYOUT_GAP_X,
    LAYOUT_GAP_Y,
    LAYOUT_NOTE_GAP,
    LAYOUT_NOTE_STEP,
    NOTE_CHAR_W,
    NOTE_CHROME_W,
    NOTE_LINE_H,
    NOTE_MAX_W,
    NOTE_MIN_H,
    NOTE_MIN_W,
    NO_PAGE,
    ROUTE_ALIGN_TOLERANCE,
    STAGE_ALIASES,
)
from desktop.steps.bpmn_diagram.diagram import FlowDiagram
from desktop.steps.bpmn_diagram.elements import DiagramFlow, DiagramNode, DiagramNote
from desktop.steps.bpmn_diagram.helpers import (
    _is_note_id,
    _local,
    _note_size,
    _overlaps,
    _q,
    _read_node_seq,
    default_size,
    stage_of_name,
)
from desktop.steps.ports import fold_forward

__all__ = [
    "AUTO_GAP_X",
    "AUTO_GAP_Y",
    "AUTO_PADDING",
    "BPMNDI_NS",
    "BPMN_NS",
    "DC_NS",
    "DI_NS",
    "GUJI_NS",
    "DEFAULT_SIZE",
    "DiagramFlow",
    "DiagramNode",
    "DiagramNote",
    "EVENT_KINDS",
    "FlowDiagram",
    "GATEWAY_KINDS",
    "KIND_END",
    "KIND_EXCLUSIVE",
    "KIND_INCLUSIVE",
    "KIND_INTERMEDIATE",
    "KIND_PARALLEL",
    "KIND_START",
    "KIND_TASK",
    "KNOWN_KINDS",
    "LAYOUT_GAP_X",
    "LAYOUT_GAP_Y",
    "NO_PAGE",
    "STAGE_ALIASES",
    "default_size",
    "fold_forward",
    "stage_of_name",
]
