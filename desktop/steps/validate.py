# -*- coding: utf-8 -*-
"""流程**合法性校验**：保存前回答"这条流程能不能这么跑"。

对应 ``docs/tasks/bpm测试.md``：BPM 可以任意组合，但**并非所有组合都合法**
——不合法的流程要在**创建或编辑保存时**当场判出来、拒绝保存。

## 规则从哪来

用户 2026-10-06 列了 10 条合法组合（``docs/tasks/bpm测试.md``），归纳后
**硬规则只有两条**，其余组合都放行：

1. **流程里必须有可运行的步骤**。只有源PDF/网关/结束事件的图什么都跑不了
   ——详情页本来就拦"流程为空"，这里把同一道闸装到保存口上；
2. **「生成 PDF」（``print``）如果在流程里，必须排在最后**。它是收尾动作，
   排在它后面的步骤产出没人消费（``print → 去底色`` 这种就是用户给的
   反例；「拼版」排在「生成 PDF」之后同样被这条拦住）。

其余组合（``detect`` 打头、``rembg`` 不带 ``detect``、单步流程、
``detect/rembg/imposition`` 任意顺序）都是**合法**的——运行时有
:func:`desktop.steps.ports.stage_blocking_inputs` 按图判就绪、
入口图片回落 ``stages/input/``，这些"缺上游"的流程本来就跑得通，
不能拿保存校验把它们挡死。

## 错误与警告分两档

- **errors**（拒绝保存）：上面两条硬规则；
- **warnings**（提示但不拦）：``extract`` 不在第一位、有 ``extract`` 却没有
  「源PDF」入口节点、有「拼版」却没有判断节点（文档"特殊"节说二者一般
  同在）、同一阶段画了多个节点、图上有未接入运行的节点。这些**跑得通**，
  只是与习惯不符——拦下来会把合法操作堵死（与状态机"缺上游只提示不硬拦"
  同一条纪律）。

⚠️ 本模块**纯逻辑、不 import Qt**（与 ports/scheduler 同一约束）。
"""

from __future__ import annotations

from dataclasses import dataclass

from desktop.steps import ports
from desktop.steps.bpmn_diagram import KIND_TASK, FlowDiagram


@dataclass(frozen=True)
class FlowValidation:
    """一次校验的结果：``errors`` 拒绝保存，``warnings`` 只提示。"""

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """没有硬错误（有警告也算合法）。"""
        return not self.errors


def validate_flow(diagram: FlowDiagram | None) -> FlowValidation:
    """校验一张流程图；返回 :class:`FlowValidation`。

    ⚠️ 判"顺序"用的是 :meth:`FlowDiagram.stage_order`（拓扑序）——与状态机
    同一份答案，别在这里另写一份顺序推导。网关/事件/认不出阶段的节点都不
    进拓扑序，天然不参与校验（结束事件常叫「生成PDF」，但它不是 ``print``，
    见 ``bpmn_diagram.load`` 的说明）。
    """
    if diagram is None:
        return FlowValidation(errors=("流程图是空的。",))
    order = diagram.stage_order()
    errors: list[str] = []
    warnings: list[str] = []

    # ---- 硬规则 ①：得有可运行的步骤 ----------------------------------
    if not order:
        return FlowValidation(errors=(
            "流程里没有可执行的步骤：至少要保留一个功能节点"
            "（提取/检测/去底色/拼版/生成 PDF）。",))

    # ---- 硬规则 ②：print 在流程里就必须排最后 -------------------------
    steps = _step_sequence(order)
    if "print" in steps and steps[-1] != "print":
        after = [ports.stage_label(ports.STAGE_STEPS.get(s, s))
                 for s in steps[steps.index("print") + 1:]]
        errors.append(
            "「生成 PDF」必须放在流程最后——"
            f"它后面还有：{'、'.join(after)}。")

    warnings.extend(_habit_warnings(diagram, order))

    return FlowValidation(errors=tuple(errors), warnings=tuple(warnings))


def _step_sequence(order: tuple[str, ...]) -> list[str]:
    """拓扑序里的阶段折叠成**界面步骤**序列（同格去重、保首现位置）。

    ``rembg_submit``（提交去底色结果）与 ``rembg`` 是同一格的两个动作——
    单独画的「提交」节点不改变步骤序列。
    """
    steps: list[str] = []
    for stage in order:
        step = ports.STAGE_STEPS.get(stage, stage)
        if step not in steps:
            steps.append(step)
    return steps


def _habit_warnings(diagram: FlowDiagram,
                    order: tuple[str, ...]) -> list[str]:
    """与习惯不符但跑得通的组合（提示，不拦保存）。"""
    warnings: list[str] = []

    if "extract" in order and order[0] != "extract":
        warnings.append(
            f"「{ports.stage_label('extract')}」要吃任务的源 PDF，"
            "通常排在流程第一位。")

    if "extract" in order and not ports.source_pdf_node_ids(diagram):
        warnings.append(
            f"流程里有「{ports.stage_label('extract')}」"
            "但没有「源PDF」入口节点。")

    if "imposition" in order and not any(
            node.is_gateway for node in diagram.nodes):
        warnings.append(
            f"流程里有「{ports.stage_label('imposition')}」但没有判断节点"
            "——是否拼版在「图片拼版」参数面板里开关。")

    # 同一**运行阶段**画了多个节点：运行时按 stage_order 去重只跑一遍，
    # 多出来的那个是死节点（「去底色」+「提交去底色结果」不算，那是两个阶段）
    counts: dict[str, int] = {}
    for node in diagram.nodes:
        if node.kind == KIND_TASK and node.stage:
            counts[node.stage] = counts.get(node.stage, 0) + 1
    duplicated = [stage for stage, count in counts.items() if count > 1]
    for stage in duplicated:
        warnings.append(
            f"「{ports.stage_label(stage)}」在图上有 "
            f"{counts[stage]} 个节点，运行时只会跑一遍。")

    unmapped = [node for node in diagram.nodes
                if node.kind == KIND_TASK and not node.stage]
    if unmapped:
        names = "、".join((n.name or n.id) for n in unmapped[:3])
        warnings.append(
            f"有 {len(unmapped)} 个节点未接入运行（{names}"
            f"{'…' if len(unmapped) > 3 else ''}）——改成已知步骤名即可。")

    return warnings


__all__ = ["FlowValidation", "validate_flow"]
