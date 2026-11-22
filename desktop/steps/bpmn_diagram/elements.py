# -*- coding: utf-8 -*-
"""图的元素数据模型：节点 / 连线 / 注释。"""

from __future__ import annotations

from dataclasses import dataclass

from desktop.steps.bpmn_diagram.constants import EVENT_KINDS, GATEWAY_KINDS


@dataclass(frozen=True)
class DiagramNode:
    """流程图上的一个**节点**（图形意义上的，不是运行阶段）。

    ``kind`` 是 BPMN 元素类型（:data:`KIND_TASK` 等）；``stage`` 是它对应的
    运行阶段 key（接不上就是 ``None``，照样画）。
    """

    id: str
    kind: str
    name: str = ""
    stage: str | None = None

    @property
    def is_gateway(self) -> bool:
        return self.kind in GATEWAY_KINDS

    @property
    def is_event(self) -> bool:
        return self.kind in EVENT_KINDS


@dataclass(frozen=True)
class DiagramFlow:
    """一条**连线**（BPMN ``sequenceFlow``）。

    ``label`` 是边上写的字（如网关分支的「否」）。它**只是显示文案**——
    运行语义由状态机管，这里不解释它。
    """

    id: str
    source: str
    target: str
    label: str = ""


@dataclass(frozen=True)
class DiagramNote:
    """节点旁边的一条**文字注释**（BPMN ``textAnnotation`` + ``association``）。

    用户在 bpmn.io 里给节点挂的说明（例如「图片拼版」→「古籍图片拼版」）。
    它**不参与运行**，但必须**显示出来**——那是作者写在图上的话，丢了等于
    把图的信息删了一半。

    :attr:`attached_to` 是它挂在哪张节点上（``association`` 的 ``sourceRef``）；
    空串表示没挂（图上孤立的一条注释）。
    """

    id: str
    text: str = ""
    attached_to: str = ""
