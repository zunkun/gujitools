# -*- coding: utf-8 -*-
"""流程**合法性校验**：保存前回答"这条流程能不能这么跑"。

对应 ``docs/tasks/bpm测试.md``：BPM 可以任意组合，但**并非所有组合都合法**
——不合法的流程要在**创建或编辑保存时**当场判出来、拒绝保存。

## 规则从哪来

用户 2026-10-06 列了 10 条合法组合（``docs/tasks/bpm测试.md``），归纳后
**原有硬规则只有两条**，其余组合都放行：

1. **流程里必须有可运行的步骤**。只有源PDF/网关/结束事件的图什么都跑不了
   ——详情页本来就拦"流程为空"，这里把同一道闸装到保存口上；
2. **「PDF排版」（``print``）如果在流程里，必须排在最后**。它是收尾动作，
   排在它后面的步骤产出没人消费（``print → 去底色`` 这种就是用户给的
   反例；「拼版」排在「PDF排版」之后同样被这条拦住）。

其余组合（``detect`` 打头、``rembg`` 不带 ``detect``、单步流程、
``detect/rembg/imposition`` 任意顺序）都是**合法**的——运行时有
:func:`desktop.steps.ports.stage_blocking_inputs` 按图判就绪、
入口图片回落 ``stages/input/``，这些"缺上游"的流程本来就跑得通，
不能拿保存校验把它们挡死。

2026-11-04 用户补充了四条**图结构**硬规则（任务 0021 暴露的孤立节点）：

3. **只能有一个「开始节点」（源PDF）**——0 个或多个都拒绝保存；
4. **不允许孤立节点**——每个节点都要能从开始节点沿连线走到；
5. **不允许环形回路**；
6. **除 XOR 网关外，任何节点只能有一条输出连线**——多路分支只能用
   「是否拼版」那个排他网关（``exclusiveGateway``）。

## 错误与警告分两档

- **errors**（拒绝保存）：上面 2 条原有规则 + 4 条图结构规则；
- **warnings**（提示但不拦）：``extract`` 不在第一位、有 ``extract`` 却没有
  「源PDF」入口节点、图上有未接入运行的节点。这些**跑得通**，只是与习惯
  不符——拦下来会把合法操作堵死（与状态机"缺上游只提示不硬拦"同一条纪律）。

  ⚠️ 图结构规则已经是硬错误，上面"未接入运行的节点"只在节点**确实连着**
  但名字认不出阶段时才有意义（孤立节点会先在结构校验里被拒绝）。

  ⚠️ **"同一阶段画了多个节点"这条警告已于 2026-10-17 删除**：B 方案后同类型
  步骤（图片拼版 / 检测文本框 / 图片去底色 / PDF排版）可以放**多个节点**，
  它们彼此独立（各自参数、各自产物落点，见 ``docs/tasks/bpm.md``）——运行时
  按 ``node_id`` 寻址、**不再折叠成一遍**。留着这条警告等于把用户明确要的
  能力说成"有问题"。

  ⚠️ **"有「拼版」却没有判断节点"这条警告已于 2026-10-08 删除**：网关依附
  「图片拼版」（用户："其实根本就没有判断这个组件，只有「是否拼版」这个特殊
  的判断组件"），界面上的"添加判断"入口也已撤掉——留着它等于让用户去做一件
  界面上做不到的事。见 :func:`desktop.steps.ports.orphaned_gateway_ids`。

⚠️ 本模块**纯逻辑、不 import Qt**（与 ports/scheduler 同一约束）。
"""

from __future__ import annotations

from dataclasses import dataclass

from desktop.steps import ports
from desktop.steps.bpmn_diagram import (
    KIND_EXCLUSIVE,
    KIND_START,
    KIND_TASK,
    DiagramNode,
    FlowDiagram,
)


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
            "（提取/检测/去底色/拼版/PDF排版）。",))

    # ---- 硬规则 ②：print 在流程里就必须排最后 -------------------------
    steps = _step_sequence(order)
    if "print" in steps and steps[-1] != "print":
        after = [ports.stage_label(ports.STAGE_STEPS.get(s, s))
                 for s in steps[steps.index("print") + 1:]]
        errors.append(
            "「PDF排版」必须放在流程最后——"
            f"它后面还有：{'、'.join(after)}。")

    # ---- 硬规则 ③–⑥：图结构（开始节点/孤立节点/回路/多输出）-----------
    errors.extend(_structure_errors(diagram))

    warnings.extend(_habit_warnings(diagram, order))

    return FlowValidation(errors=tuple(errors), warnings=tuple(warnings))


def _step_sequence(order: tuple[str, ...]) -> list[str]:
    """拓扑序里的阶段折叠成**界面步骤**序列（同格去重、保首现位置）。

    ``detect_submit``（提交检测结果）与 ``detect`` 是同一格的两个动作——
    单独画的「提交」节点不改变步骤序列。
    """
    steps: list[str] = []
    for stage in order:
        step = ports.STAGE_STEPS.get(stage, stage)
        if step not in steps:
            steps.append(step)
    return steps


def _node_label(node: DiagramNode | None, node_id: str = "") -> str:
    """节点在错误信息里的名字：优先 ``name``，其次 id。"""
    if node is None:
        return node_id or "?"
    return (node.name or node.id or "?").strip()


def _join_labels(diagram: FlowDiagram, ids: list[str], limit: int = 3) -> str:
    """把若干节点 id 拼成可读的名字串（超过 ``limit`` 个就省略）。"""
    labels = [_node_label(diagram.node(node_id), node_id) for node_id in ids]
    text = "、".join(labels[:limit])
    if len(labels) > limit:
        text += "…"
    return text


def _structure_errors(diagram: FlowDiagram) -> list[str]:
    """硬规则 ③–⑥：图结构是否正确（孤立/回路/多输出/开始节点）。"""
    errors: list[str] = []
    errors.extend(_start_node_errors(diagram))
    errors.extend(_outgoing_errors(diagram))
    errors.extend(_cycle_errors(diagram))
    errors.extend(_isolated_errors(diagram))
    return errors


def _start_node_errors(diagram: FlowDiagram) -> list[str]:
    """必须**恰好**有一个「开始节点」（``startEvent``，即源PDF入口）。"""
    starts = [node for node in diagram.nodes if node.kind == KIND_START]
    if not starts:
        return ["流程缺少「开始节点」：请保留默认流程里的「源PDF」开始事件。"]
    if len(starts) > 1:
        return [
            f"流程只能有一个「开始节点」，当前有 {len(starts)} 个"
            f"（{_join_labels(diagram, [node.id for node in starts])}）。"
        ]
    return []


def _outgoing_errors(diagram: FlowDiagram) -> list[str]:
    """除 XOR 网关外**任何节点只能有一条输出连线**。

    多路分支只允许走「是否拼版」那个排他网关（``exclusiveGateway``，
    ``docs/tasks/bpm测试.md`` R6）；普通步骤/事件/其它网关出现第二条
    输出就是运行语义表达不了的分叉。
    """
    known = {node.id for node in diagram.nodes}
    errors: list[str] = []
    for node in diagram.nodes:
        targets = [
            flow.target for flow in diagram.flows_of(node.id)
            if flow.target in known
        ]
        if len(targets) <= 1 or node.kind == KIND_EXCLUSIVE:
            continue
        errors.append(
            f"「{_node_label(node)}」有 {len(targets)} 条输出连线"
            f"（→ {_join_labels(diagram, targets)}）——只有 XOR 网关"
            "（「是否拼版」）允许分支，其它节点只能有一条输出。"
        )
    return errors


def _cycle_errors(diagram: FlowDiagram) -> list[str]:
    """不允许环形回路（DFS 找第一条回边）。"""
    known = {node.id for node in diagram.nodes}
    adjacency: dict[str, list[str]] = {
        node.id: [
            flow.target for flow in diagram.flows_of(node.id)
            if flow.target in known
        ]
        for node in diagram.nodes
    }
    # 0=未访问 1=在递归栈上 2=已完成
    color = {node_id: 0 for node_id in adjacency}
    path: list[str] = []
    cycle: list[str] = []

    def visit(node_id: str) -> bool:
        color[node_id] = 1
        path.append(node_id)
        for target in adjacency[node_id]:
            if color[target] == 1:
                cycle.extend(path[path.index(target):])
                return True
            if color[target] == 0 and visit(target):
                return True
        path.pop()
        color[node_id] = 2
        return False

    for node_id in adjacency:
        if color[node_id] == 0 and visit(node_id):
            break

    if not cycle:
        return []
    labels = [_node_label(diagram.node(node_id), node_id) for node_id in cycle]
    labels.append(labels[0])
    return [
        f"流程里存在环形回路：{' → '.join(labels)}——请断开回流的连线。"
    ]


def _isolated_errors(diagram: FlowDiagram) -> list[str]:
    """不允许孤立节点：每个节点都要能从「开始节点」沿连线走到。

    开始节点数量异常（0 个或多个）时无法从它回溯，退化为**弱连通分量**
    判断：节点最多的那片算主流程，其余都报孤立。
    """
    if not diagram.nodes:
        return []
    known = {node.id for node in diagram.nodes}
    starts = [node.id for node in diagram.nodes if node.kind == KIND_START]
    if len(starts) == 1:
        reached = {starts[0]}
        stack = [starts[0]]
        while stack:
            node_id = stack.pop()
            for flow in diagram.flows_of(node_id):
                if flow.target in known and flow.target not in reached:
                    reached.add(flow.target)
                    stack.append(flow.target)
        detached = [node.id for node in diagram.nodes if node.id not in reached]
    else:
        adjacency = {node.id: set() for node in diagram.nodes}
        for flow in diagram.flows:
            if flow.source in known and flow.target in known:
                adjacency[flow.source].add(flow.target)
                adjacency[flow.target].add(flow.source)
        seen: set[str] = set()
        components: list[list[str]] = []
        for node in diagram.nodes:
            if node.id in seen:
                continue
            component: list[str] = []
            stack = [node.id]
            seen.add(node.id)
            while stack:
                node_id = stack.pop()
                component.append(node_id)
                for other in adjacency[node_id]:
                    if other not in seen:
                        seen.add(other)
                        stack.append(other)
            components.append(component)
        if len(components) <= 1:
            return []
        anchor = set(max(components, key=len))
        detached = [node.id for node in diagram.nodes if node.id not in anchor]
    if not detached:
        return []
    return [
        f"流程里有 {len(detached)} 个孤立节点（从开始节点走不到）："
        f"{_join_labels(diagram, detached)}——请把连线接回流程，或删掉这些节点。"
    ]


def _habit_warnings(diagram: FlowDiagram,
                    order: tuple[str, ...]) -> list[str]:
    """与习惯不符但跑得通的组合（提示，不拦保存）。"""
    warnings: list[str] = []

    if "extract" in order and order[0] != "extract":
        warnings.append(
            f"「{ports.stage_label('extract')}」要吃任务的源文件（PDF/DjVu），"
            "通常排在流程第一位。")

    if "extract" in order and not ports.source_pdf_node_ids(diagram):
        warnings.append(
            f"流程里有「{ports.stage_label('extract')}」"
            "但没有「源PDF」入口节点。")

    # ⚠️ 这里**曾经**还有一条 "有 imposition 但没有判断节点" 的警告，2026-10-08
    #    删掉了：网关不是可自由增删的独立组件（用户："其实根本就没有判断这个
    #    组件"），界面上的"添加判断"入口也已撤掉——留着这条警告等于让用户去
    #    做一件界面上做不到的事（拖进「图片拼版」后重新加回网关）。
    #    "拼版没有网关"本来就是**合法且常见**的状态：那一步无条件执行，
    #    启用与否由「图片拼版」面板的开关决定。

    # ⚠️ 这里**曾经**有一条 "同一阶段画了多个节点只会跑一遍" 的警告，
    #    2026-10-17 删掉了：B 方案（按 ``node_id`` 寻址）后同类型步骤可以放
    #    多个节点**彼此独立**，多出来的不是死节点而是另一份实例。见模块
    #    docstring 的说明。

    unmapped = [node for node in diagram.nodes
                if node.kind == KIND_TASK and not node.stage]
    if unmapped:
        names = "、".join((n.name or n.id) for n in unmapped[:3])
        warnings.append(
            f"有 {len(unmapped)} 个节点未接入运行（{names}"
            f"{'…' if len(unmapped) > 3 else ''}）——改成已知步骤名即可。")

    return warnings


__all__ = ["FlowValidation", "validate_flow"]
