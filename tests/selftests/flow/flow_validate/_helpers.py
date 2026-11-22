# -*- coding: utf-8 -*-
"""``flow_validate`` 包的无状态助手：按阶段串链。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from desktop.steps import ports

if TYPE_CHECKING:
    # _chain 里是函数内延迟导入（保持自测启动轻），但返回注解引它 —— 类型侧声明。
    from desktop.steps.bpmn_diagram import FlowDiagram


def _chain(*stages: str, gateway: bool = False, source: bool = True,
           end: bool = True) -> "FlowDiagram":
    """按阶段 key 串一条链（带可选的源PDF事件 / 网关 / 结束事件）。

    ⚠️ 节点带显式 ``stage``：:func:`stage_of_name` 只在 ``load`` 解析时调用，
    手造节点必须自己接上阶段，否则 ``stage_order()`` 是空的、断言假红。
    """
    from desktop.steps.bpmn_diagram import (
        KIND_END, KIND_EXCLUSIVE, KIND_START, KIND_TASK,
        DiagramFlow, DiagramNode, FlowDiagram,
    )

    nodes: list[DiagramNode] = []
    flows: list[DiagramFlow] = []
    if source:
        nodes.append(DiagramNode("src", KIND_START, "源PDF"))
    previous = "src" if source else None
    for index, stage in enumerate(stages):
        node_id = f"n{index}"
        nodes.append(DiagramNode(node_id, KIND_TASK, ports.stage_label(stage),
                                 stage=stage))
        if previous is not None:
            flows.append(DiagramFlow(f"f{len(flows)}", previous, node_id))
        previous = node_id
        if gateway and stage == "rembg":
            nodes.append(DiagramNode("gw", KIND_EXCLUSIVE, "是否拼版"))
            flows.append(DiagramFlow(f"f{len(flows)}", node_id, "gw"))
            previous = "gw"
    if end and previous is not None:
        nodes.append(DiagramNode("end", KIND_END, "完成"))
        flows.append(DiagramFlow(f"f{len(flows)}", previous, "end"))
    return FlowDiagram(nodes=tuple(nodes), flows=tuple(flows))
