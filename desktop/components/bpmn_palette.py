# -*- coding: utf-8 -*-
"""BPMN **固定步骤表**：「添加步骤」的候选名单与命名规则。

用户 2026-10-05 的口径：

> 编辑呢，我希望能够有 BPMN.js 那种（bpmn.io）可以编辑的节点。或许我们不需要
> 那么多节点，**我们的节点是固定的**，拖拖拽拽就行了。

所以这里**不提供"任意节点类型"**：条目就是本工具认识的步骤
（提取图片 / 检测文本框 / 图片去底色 / PDF 排版 / 图片拼版）。
「添加步骤」弹窗（:meth:`BpmnEditor.ask_add_node`）的方块直接照这份表摆。

⚠️ **没有「判断」这一项**（用户 2026-10-08）：

> 其实根本就没有判断这个组件，只有「是否拼版」这个特殊的判断组件，
> 也就是说是否拼版依附拼版，因此删除左侧的判断 gateway、顶部的添加判断按钮

图上那个排他网关是「图片拼版」的**附属图形**（它问的问题只对那一步成立），
不是可自由增删的独立组件——它只能随模板文件来，删掉「图片拼版」时跟着删
（:func:`desktop.steps.ports.orphaned_gateway_ids`）。

## 命名规则

节点名**沿用流程图里已有的叫法**：``print`` 那格在默认模板里叫「PDF排版」
（与 :attr:`StepSpec.stage_title` 一致），再加一个就叫「PDF排版」——
不要凭空长出一个新名字，更别和结束事件「生成PDF」重名。

## 历史

⚠️ 原来的拖拽面板（``NodePalette``，摆在画布左侧）已撤（用户 2026-11-17：
"左側這塊區域不需要了"）——加步骤统一走工具栏「添加步骤」的方块弹窗，
拖放 MIME（``NODE_MIME``）随之删除。本模块保留为**步骤表 + 命名规则**。
"""

from __future__ import annotations

from desktop.steps import ports
from desktop.steps.spec import FLOW_STAGES, OPTIONAL_STEPS, spec_by_key


def palette_steps() -> list[str]:
    """**步骤 key** 名单（顺序 = 静态步骤表：主链 + 可选节点）。"""
    return list(tuple(FLOW_STAGES) + tuple(OPTIONAL_STEPS))


def step_stage(step: str) -> str | None:
    """步骤 key → 拿它当节点名时要写的**运行阶段**。

    ``detect`` 那一格下挂着两个阶段（``detect`` 与 ``detect_submit``），这里取
    **同名那个**（``detect``）——它就是这一格的代表。
    """
    if step in ports.STAGE_STEPS:
        return step
    for stage in ports.STAGE_STEPS:
        if ports.STAGE_STEPS[stage] == step:
            return stage
    return None


def palette_name(step: str, *diagrams) -> str:
    """这一格该叫什么名字。

    优先沿用**已有流程图**里的叫法（用户的词汇），其次 ``ports.stage_label``。
    ⚠️ 一定要沿用：``print`` 那格现在正式叫「PDF排版」，若另起一个
    「生成PDF」，加进去就会与**结束事件**同名（渲染与自检都会炸）。
    """
    for diagram in diagrams:
        if diagram is None:
            continue
        for node in diagram.nodes:
            if node.stage and ports.STAGE_STEPS.get(node.stage, node.stage) == step:
                return node.name
    stage = step_stage(step)
    return ports.stage_label(stage) if stage else step


def is_optional_step(step: str) -> bool:
    spec = spec_by_key(step)
    return bool(spec and spec.role == "optional")


__all__ = [
    "is_optional_step", "palette_name", "palette_steps", "step_stage",
]
