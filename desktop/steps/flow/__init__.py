# -*- coding: utf-8 -*-
"""流程定义（BPMN 2.0）：``tasks/<任务号>/flow.bpmn`` 的读写与运行语义。

设计口径（用户 2026-10-03）：

> 任务管理的每个步骤组件有先后关系…我想用 bpmn 的流程来做我们任务流程的定义。

所以现阶段的**唯一真源**不是一张代码里的常量表，而是任务目录里真实的
``flow.bpmn``（默认模板见 ``desktop/static/task_default.bpmn``）：

- ``bpmn:process`` 段——``startEvent`` → ``task``（每步一个，``guji:stage``
  扩展属性带阶段名）→ ``endEvent``；``sequenceFlow`` 带 ``guji:port``（哪个
  端口的产物）与可选的 ``guji:condition``（条件边的条件名）；
- ``bpmndi:BPMNDiagram`` 段——节点坐标（``dc:Bounds``）与连线折点
  （``di:waypoint``），即标准的 BPMN 图形交换格式。

于是"换顺序 / 多步 / 条件分叉"都能用任意 BPMN 工具画，程序照文件执行；
本模块只负责**解析、校验与落盘**，不在这里重写一份流程。

⚠️ 只依赖标准库（``xml.etree``）与 ``desktop.steps.ports``，不 import Qt——
任务存储、状态机与界面都要能安全导入它。

本包按职责拆成五个子模块（2026-11-22）：

- :mod:`desktop.steps.flow.constants`：命名空间 / 文件名 / 限定名工具；
- :mod:`desktop.steps.flow.model`：:class:`FlowEdge` / :class:`StageSlot`；
- :mod:`desktop.steps.flow.layout`：:class:`FlowLayout` 图形几何；
- :mod:`desktop.steps.flow.serialization`：BPMN 序列化；
- :mod:`desktop.steps.flow.definition`：:class:`FlowDefinition` 运行语义。

⚠️ 本 ``__init__`` 只做重导出：既有 ``from desktop.steps.flow import X`` 全部
不变，子模块之间不要反过来导入本包（会形成循环）。
"""

from desktop.steps.flow.constants import (
    BPMNDI_NS,
    BPMN_NS,
    BPMN_XSD,
    CONDITION_IMPOSITION,
    DC_NS,
    DI_NS,
    FLOW_FILENAME,
    GUJI_NS,
    _local,
    _q,
)
from desktop.steps.flow.definition import FlowDefinition, default_flow_path
from desktop.steps.flow.layout import FlowLayout, _diagram_nodes
from desktop.steps.flow.model import FlowEdge, StageSlot

__all__ = [
    "BPMNDI_NS",
    "BPMN_NS",
    "BPMN_XSD",
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
