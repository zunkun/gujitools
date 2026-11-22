# -*- coding: utf-8 -*-
"""``flow_bpm`` 第 3 章：界面投影（槽位）与自定义顺序。"""

from __future__ import annotations

from ._helpers import _CUSTOM_ORDER_WIRING


def run(st) -> None:
    _check_stage_slots(st.ok)
    _check_slots_drive_ui(st.ctx, st.ok)


def _check_stage_slots(ok) -> None:
    """⑥ 投影层：6 个运行阶段 → 界面格子（折叠 detect_submit + 标可选节点）。"""
    from desktop.steps import ports
    from desktop.steps.flow import FlowDefinition
    from desktop.steps.spec import FLOW_STAGES

    flow = FlowDefinition.default()
    slots = flow.stage_slots()

    # detect_submit 是第二步的第二个动作 ⇒ 折叠掉，不单独占格
    ok("detect_submit 不单独占格（折叠进第二步）",
       "detect_submit" not in [s.step for s in slots],
       str([s.step for s in slots]))
    ok("格数 = 真实步骤 4 + 可选节点 1",
       len(slots) == len(FLOW_STAGES) + 1, str(len(slots)))

    by_step = {s.step: s for s in slots}
    ok("第二步的 stage 是 detect（不是 detect_submit）",
       by_step["detect"].stage == "detect", by_step["detect"].stage)
    ok("拼版被标成可选节点",
       by_step["imposition"].optional is True)
    ok("真实步骤都不是可选节点",
       all(not s.optional for s in slots if s.step != "imposition"))

    # 默认流程的等价性：bar_index 是**步骤条上的格子序号**（含可选节点
    # 自己占的那一格），真实步骤恰好等于旧下标；可选节点那一格插在第三步
    # 与第四步之间 ⇒ 3（旧口径下它是"伪步骤 4"，但那是stack 下标，不是
    # 格子序号——两者别混，见 flow.optional_after 的警示）。
    bar_of = {s.step: s.bar_index for s in slots}
    for i, step in enumerate(FLOW_STAGES):
        if step == "print":
            continue  # print 前面多了可选节点占的那一格 ⇒ bar_index 顺延
        ok(f"默认流程 {step} 的 bar_index = 旧下标 {i}",
           bar_of[step] == i, str(bar_of))
    ok("默认流程 print 的 bar_index顺延一格（前面有可选节点）",
       bar_of["print"] == len(FLOW_STAGES), str(bar_of))
    ok("默认流程拼版排在第三步与第四步之间",
       bar_of["imposition"] == bar_of["rembg"] + 1
       and bar_of["imposition"] < bar_of["print"], str(bar_of))

    # stack_index：真实步骤按流程排名，可选节点顺延到最后（两个栈的建页不动）
    stack_of = {s.step: s.stack_index for s in slots}
    for i, step in enumerate(FLOW_STAGES):
        ok(f"默认流程 {step} 的 stack_index = {i}",
           stack_of[step] == i, str(stack_of))
    ok("可选节点 stack_index 排在真实步骤之后",
       stack_of["imposition"] == len(FLOW_STAGES), str(stack_of))

    # 可选节点插在**第几个真实步骤之后**（StepBar 的布局参数）
    ok("默认流程可选节点插在第2 个真实步骤之后",
       flow.optional_after("imposition") == 2,
       str(flow.optional_after("imposition")))

    # 反查接口自洽
    for slot in slots:
        ok(f"bar_index_of({slot.step}) 与投影一致",
           flow.bar_index_of(slot.step) == slot.bar_index)
        ok(f"step_at({slot.bar_index}) 反查回 {slot.step}",
           flow.step_at(slot.bar_index) == slot.step)
    ok("不存在的步骤反查为 None",
       flow.bar_index_of("ghost") is None and flow.slot_of("ghost") is None)
    ok("越界格序反查为 None", flow.step_at(99) is None)


def _check_slots_drive_ui(ctx, ok) -> None:
    """⑦ 自定义流程：步骤条顺序与两个下标都跟着流程变（纯逻辑，不建页面）。"""
    from pathlib import Path

    from desktop.steps import ports
    from desktop.steps.scheduler import load_default_diagram
    from desktop.store import TaskStore

    repo = TaskStore(ctx.tmp / "flow_store")
    tid = repo.create_task(ctx.pdf, "hash-slots", "槽位样本")
    try:
        # 一份"摘掉 detect、拼版排最前"的流程（源Ref 写错也不影响：
        # 投影只看节点序列，坏连线会在解析层报，不在这里）。
        path = Path(repo.task_dir(tid)) / "flow.bpmn"
        path.write_text(_CUSTOM_ORDER_WIRING, encoding="utf-8")
        getattr(repo, "_flow_cache", {}).clear()

        flow = repo.task_diagram(tid)
        slots = flow.stage_slots()
        order = [s.step for s in sorted(slots, key=lambda s: s.bar_index)]

        ok("自定义流程：detect 已从步骤条上消失",
           "detect" not in order, str(order))
        # ⚠️ extract 是流程入口（源PDF 由任务供给），BPMN 里必然排在最前，
        #    所以"拼版排最前"这种流程压根不合法。这里验证的是**异位**：
        #    拼版从"第三步之后"挪到了"第一步之后"（默认流程它在 rembg 之后）。
        ok("自定义流程：拼版从第三步之后挪到第一步之后（异位生效）",
           order[:2] == ["extract", "imposition"], str(order))
        ok("自定义流程：同一步骤的第二个动作不单独占格",
           "detect_submit" not in order and "rembg" in order, str(order))

        # 拼版左侧只有 extract ⇒ optional_after = 0（不是 None，
        # None 只在拼版排第一格、连左邻居都没有时出现）。
        ok("拼版左侧只有一步 → optional_after = 0",
           flow.optional_after("imposition") == 0,
           str(flow.optional_after("imposition")))
        # 可选节点的 stack_index 仍排在真实步骤之后（两个栈的建页顺序不变）
        # ⚠️⚠️ 判据是**静态表位置**（``len(FLOW_STAGES)``），**不是**"本流程里
        #    真实步骤有几个"。两个栈按 ``FLOW_STAGES + OPTIONAL_STEPS`` 一次
        #    建好**固定页数**，与流程图无关：这条流程摘掉了 detect（真实步骤只剩
        #    3 个），但拼版那一页仍然是**第 5 页**（index 4）——若按"数出来的
        #    位置"编号，后面每一步的页号都会整体前移，点「生成 PDF」就会翻到
        #    去底色页（MEMORY「三套下标」）。
        #    ⚠️ 这条断言此前是拿 ``task_flow``（旧模型 ``FlowDefinition``）算的，
        #    旧模型用"数当前有几个阶段"⇒摘掉 detect 后给出 3，与真源不同。
        from desktop.steps.spec import FLOW_STAGES

        by_step = {s.step: s for s in slots}
        ok("可选节点 stack_index = 静态表位置（不随流程里少几步而前移）",
           by_step["imposition"].stack_index == len(FLOW_STAGES),
           f"imposition={by_step['imposition'].stack_index} "
           f"FLOW_STAGES={len(FLOW_STAGES)} "
           f"{ {s.step: s.stack_index for s in slots} }")
        # 摘掉 detect 后格子前移：默认流程 rembg 在第 2 格（extract/detect/rembg），
        # 现在 detect 没了、拼版插在 extract 之后 ⇒ rembg 仍落第 2 格，但它
        # 左边换成了"extract + 拼版"。重点是 detect 整格消失、rembg 不越位。
        ok("摘掉 detect 后 rembg 的 bar_index 仍为 2（左边换成 extract+拼版）",
           by_step["rembg"].bar_index == 2,
           str({s.step: s.bar_index for s in slots}))
        ok("流程外的步骤 bar_index_of 为 None",
           flow.bar_index_of("detect") is None)

        # store 的两个转发入口与流程一致
        ok("store.task_slots 与流程投影一致",
           [s.step for s in repo.task_slots(tid)] == [s.step for s in slots])
        ok("store.task_stage_of 按格序反查运行阶段",
           repo.task_stage_of(tid, by_step["imposition"].bar_index) == "imposition",
           str(repo.task_stage_of(tid, by_step["imposition"].bar_index)))
        ok("store.task_stage_of 对越界格序返回 None",
           repo.task_stage_of(tid, 99) is None)
        # 折叠后的节点反查仍拿到真实阶段（界面查 spec 用它）
        ok("rembg 格的运行阶段是 rembg",
           repo.task_stage_of(tid, by_step["rembg"].bar_index) == "rembg")
        # 取输入仍按连线（与顺序无关）
        ok("自定义顺序下取输入照旧按连线",
           repo.stage_input(tid, "print", "pages")
           == ports.artifact_path(repo.task_dir(tid), "rembg", "pages"))
    finally:
        repo.delete_task(tid)
