# -*- coding: utf-8 -*-
"""图到界面步骤条的投影：步骤槽位、可选节点插入位、按格反查。"""

from __future__ import annotations

from desktop.steps import ports
from desktop.steps.bpmn_diagram.constants import KIND_TASK, NO_PAGE


class _SlotMixin:
    """``FlowDiagram`` 的界面投影部分（步骤条格序）。"""

    # ------------------------------------------------------------ 界面投影
    def stage_slots(self) -> tuple:
        """把本图投影成**界面步骤条上的格子序列**（与 ``FlowDefinition``
        的同名方法语义一致，但顺序来自**本图**而不是代码里的阶段表）。

        ⚠️ 这是"页面按文件渲染"的关键一步：详情页的步骤条与阶段寻址都走
        它，所以**换文件即换界面**。旧实现走 ``FlowDefinition.stage_slots()``
        ——那读的是 `FlowDefinition.load()`，而它不认 ``exclusiveGateway`` 与
        bpmn.io 生成的 id，解析失败就**静默回落到默认流程** ⇒ 用户无论选
        默认还是自定义，详情页永远显示 ``task_default.bpmn``。

        折叠规则（与 ``FlowDefinition.stage_slots`` 保持一致）：

        1. **同一步骤的其他节点各占一格**（B 方案，2026-10-17：图片拼版 /
           检测文本框 / 图片去底色 / PDF排版都可以有多个节点，它们彼此独立）；
        2. ``bar_index`` 只数**本图里有**的格子（步骤条上就这么多格）；
        3. **图上画了、但本程序还没有对应功能的 task 节点**（例如随手加的
           「OCR 识别」）也**占一格**，排在真实步骤之后，标 ``mapped=False``
           且 ``stack_index = NO_PAGE``——界面据此画灰节点并在点它时解释
           （改成已有步骤名即可接上）。这类节点不会进 ``stage_order()``
           （那里只收认得出阶段的），所以是单独扫节点表挑出来的。

        每个真实步骤格都带 ``node_id``（:attr:`~desktop.steps.flow.StageSlot.node_id`）
        ——界面据此**按节点**寻址产物与参数（单节点时它就是主节点）。

        ⚠️⚠️ **``stack_index`` 不是"数出来的"，而是"查出来的"**——这是最容易
        写错的一处（2026-10-05 实测踩中）：

        两个栈（``control_stack`` / ``preview_stack``）是**按静态步骤表**一次
        建好的固定页数（``FLOW_STAGES`` 各一页 + ``OPTIONAL_STEPS`` 追加在末尾），
        **与流程图文件无关**。所以页号必须查"这一步在静态表里的位置"：

        - 文件里**少了**某一步（例如默认流程改成不含「图片去底色」）时，若还
          按"数当前有几格"来编号，后面每一步的页号都会**整体前移**——
          点「PDF排版」会翻到「图片去底色」那一页（用户报的"改了文件程序
          没跟着变"就是这个）。
        - 文件里**多了/调换了顺序**也一样：页号只认静态位置，步骤条上哪一格
          对应哪一页由 :meth:`slot_of` / ``_select_stage`` 查出来。

        ⚠️ 同一步骤的**多个节点共用同一页**（静态表里同一步骤只有一个位置）：
        页面在切到某一格时把该格对应的**节点**记下来（``node_id``），按节点
        重定向数据（产物目录 / 参数暂存 / 状态）。这样两个栈的建页数仍与静态
        表一致，不必为每个节点各建一页昂贵的预览控件。
        """
        from desktop.steps.flow import StageSlot
        from desktop.steps.spec import FLOW_STAGES, OPTIONAL_STEPS

        # 栈页号 = 静态面板顺序里的位置（两个栈就是这么建的）
        page_of: dict[str, int] = {
            step: index
            for index, step in enumerate(tuple(FLOW_STAGES) + tuple(OPTIONAL_STEPS))
        }

        slots: list[StageSlot] = []
        #: 已出现的界面步骤/节点名：只用于给"图上有、程序没有"的节点去重。
        seen_steps: set[str] = set()
        # ⚠️ 按**节点**拓扑序（``node_order``，不折叠同阶段）走：同一步骤的每个
        #    节点各占一格（B 方案）。
        for node_id, stage in self.node_order():
            spec = ports.spec_for_stage(stage)
            if spec is None:
                continue
            step = ports.STAGE_STEPS.get(stage, stage)
            seen_steps.add(step)
            slots.append(
                StageSlot(
                    step=step, stage=stage, optional=spec.role == "optional",
                    node_id=node_id,
                )
            )
        # ⚠️ 图上"画了但本程序没有对应功能"的 task 节点：**不静默丢掉**
        #    （2026-10-05）。它们**不会**出现在 ``stage_order()`` 里——那里只收
        #    "认得出运行阶段"的节点——所以要单独扫一遍节点表。
        #    它们排在真实步骤**之后**、``stack_index`` 记 :data:`NO_PAGE`
        #    （两个栈里没有它们的页，点它们由页面负责拦下并解释）。
        for node in self.nodes:
            if node.kind != KIND_TASK or node.stage is not None:
                continue
            label = (node.name or "").strip() or node.id
            if label in seen_steps:
                continue
            seen_steps.add(label)
            slots.append(
                StageSlot(
                    step=label,
                    stage="",
                    optional=False,
                    mapped=False,
                    name=label,
                    stack_index=NO_PAGE,
                )
            )
        return tuple(
            StageSlot(
                step=slot.step,
                stage=slot.stage,
                optional=slot.optional,
                bar_index=bar_index,
                # 已接入的查静态表拿页号（同一步骤的多个节点共用一页）；未接入的
                # 两个栈里没有它的页
                stack_index=(
                    page_of.get(slot.step, bar_index) if slot.mapped else NO_PAGE
                ),
                mapped=slot.mapped,
                name=slot.name,
                node_id=slot.node_id,
            )
            for bar_index, slot in enumerate(slots)
        )

    def optional_after(self, step: str | None = None) -> int | None:
        """可选节点插在**真实步骤数组的第几位之后**（喂 ``StepBar``）。

        语义抄自 ``FlowDefinition.optional_after``（那里有详细推演，别重推）：
        ``after`` 指的是**最后一个左邻居的下标**，不是左邻居的个数。

        ⚠️ 返回值三态（2026-10-07，任务 #0027 踩坑）：``None`` 只表示**本图
        没有可选节点**；图里有拼版但它排在**最前**（没有任何左邻居）时返回
        ``-1``——早先这种情况也回 ``None``，``StepBar`` 把 ``None`` 当"按默认
        位插到最后"，于是「拼版→PDF排版」的流程在步骤条上显示成
        「生成PDF → 图片拼版」，与图相反。
        """
        slots = self.stage_slots()
        optional = [s for s in slots if s.optional]
        if not optional:
            return None
        target = None
        if step is not None:
            target = next((s for s in optional if s.step == step), None)
        node = target or optional[0]
        after = -1
        position = 0
        for slot in slots:
            if slot.optional:
                continue
            if slot.bar_index < node.bar_index:
                after = position
            position += 1
        return after

    def slot_of(self, step: str):
        """按**界面步骤 key** 找槽位；不在流程里返回 ``None``。"""
        for slot in self.stage_slots():
            if slot.step == step:
                return slot
        return None

    def bar_index_of(self, step: str) -> int | None:
        slot = self.slot_of(step)
        return None if slot is None else slot.bar_index

    def step_at(self, bar_index: int) -> str | None:
        """步骤条格序 → 界面步骤 key（点节点后反查）。"""
        for slot in self.stage_slots():
            if slot.bar_index == bar_index:
                return slot.step
        return None

    def contains(self, stage: str) -> bool:
        """这个运行阶段在**本图**里吗。"""
        return stage in self.stage_order()
