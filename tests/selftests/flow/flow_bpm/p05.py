# -*- coding: utf-8 -*-
"""``flow_bpm`` 第 5 章：栈页号静态表 / 未接入节点 / 列表胶囊。"""

from __future__ import annotations


def run(st) -> None:
    _check_stack_pages_use_static_table(st.ok)
    _check_unmapped_nodes(st.ok)
    _check_list_chips_follow_diagram(st.ctx, st.ok)
    _check_chips_status_by_node(st.ctx, st.ok)


# ------------------------------------------------- 10. 栈页号必须查静态表
def _check_stack_pages_use_static_table(ok) -> None:
    """⚠️⚠️ **栈页号（``stack_index``）必须"查静态表"，不能"数当前有几格"**。

    两个栈（``control_stack`` / ``preview_stack``）是**按静态步骤表一次建好
    固定页数**的（``FLOW_STAGES`` 各一页 + ``OPTIONAL_STEPS`` 追加在末尾），
    与流程图文件无关。若页号按"本图里实际有几步"顺序编号，文件里**少一步**时
    后面每一步的页号都会**整体前移**——点「生成 PDF」会翻到「图片去底色」
    那一页。用户 2026-10-05 报的"改了 task_default.bpmn 程序没跟着变"就是它。

    这里用两种图各验一遍：**少一步**的、**全都有**的。
    """
    from desktop.steps.bpmn_diagram import (
        KIND_TASK, DiagramFlow, DiagramNode, FlowDiagram, stage_of_name,
    )
    from desktop.steps.spec import FLOW_STAGES, OPTIONAL_STEPS

    static_page = {
        step: index
        for index, step in enumerate(tuple(FLOW_STAGES) + tuple(OPTIONAL_STEPS))
    }
    ok("静态步骤表里认得出 print / imposition（前提成立）",
       "print" in static_page and "imposition" in static_page,
       str(static_page))

    def chain(*names) -> FlowDiagram:
        """按名字串成一条链。⚠️ 手造的节点不会自动接运行阶段（那是 `load`
        解析时才做的），所以这里显式走一次 :func:`stage_of_name`——否则
        ``stage_order()`` 是空的，断言会以 KeyError 的形式假红。"""
        nodes, flows = [], []
        for index, name in enumerate(names):
            nodes.append(DiagramNode(f"n{index}", KIND_TASK, name,
                                     stage=stage_of_name(name)))
            if index:
                flows.append(DiagramFlow(f"f{index}", f"n{index - 1}",
                                         f"n{index}"))
        return FlowDiagram(nodes=tuple(nodes), flows=tuple(flows))

    # ① 少了「图片去底色」的图（曾把 print 的页号算成 2）
    short = chain("提取图片", "检测文本框", "PDF排版").stage_slots()
    by_step = {slot.step: slot for slot in short}
    ok("少一步时 print 的栈页号仍是静态页号（不是被数出来的 2）",
       by_step["print"].stack_index == static_page["print"],
       f"print -> {by_step['print'].stack_index}，静态表说是 {static_page['print']}")
    ok("少一步时 bar 序号仍按本图顺序数（print 在第 3 格 = 2）",
       by_step["print"].bar_index == 2, str(by_step["print"].bar_index))

    # ② 全都有（含可选拼版）——页号必须与旧的硬编码口径一致
    full = chain("提取图片", "检测文本框", "图片去底色",
                 "图片拼版", "PDF排版").stage_slots()
    pages = {slot.step: slot.stack_index for slot in full}
    ok("全流程下页号与旧口径逐值相等"
       "（提取0/检测1/去底色2/生成PDF3/拼版4）",
       pages.get("extract") == 0 and pages.get("detect") == 1
       and pages.get("rembg") == 2 and pages.get("print") == 3
       and pages.get("imposition") == 4,
       str(pages))
    ok("拼版是可选节点（不占真实步骤区）",
       full[-1].step == "imposition" or any(
           s.step == "imposition" and s.optional for s in full),
       str([(s.step, s.optional) for s in full]))


# ------------------------------ 11. 图上"画了但没功能"的节点不许消失
def _check_unmapped_nodes(ok) -> None:
    """⚠️ 流程图里**画了但本程序没有实现**的节点，必须在界面上**看得见**。

    用户在 bpmn.io 里可以随手加一个「OCR 识别」。以前
    :meth:`FlowDiagram.stage_slots` 遇到认不出阶段的节点直接 ``continue``，
    那一格在界面上**凭空消失**——用户视角就是"我改了流程图，程序没反应"，
    也就是"任务流程节点不能完全映射到 bpm 流程"最明显的一条。

    现在它占一格、标 ``mapped=False``、``stack_index = NO_PAGE``（两个栈里
    没有它的页，点它由页面拦下并解释怎么接上）。这里钉住形状。

    ⚠️ 顺带钉住"**未接入的节点不挤掉已有步骤的页号**"：它排在真实步骤之后，
    已接入那些的 ``stack_index`` 必须与静态表逐值一致。
    """
    from desktop.steps.bpmn_diagram import (
        KIND_TASK, NO_PAGE, DiagramFlow, DiagramNode, FlowDiagram, stage_of_name,
    )

    def node(node_id: str, name: str) -> DiagramNode:
        return DiagramNode(node_id, KIND_TASK, name, stage=stage_of_name(name))

    diagram = FlowDiagram(
        nodes=(node("n0", "提取图片"), node("n1", "检测文本框"),
               node("n2", "OCR 识别"), node("n3", "图片去底色"),
               node("n4", "图片拼版"), node("n5", "PDF排版")),
        flows=(DiagramFlow("f1", "n0", "n1"), DiagramFlow("f2", "n1", "n2"),
               DiagramFlow("f3", "n2", "n3"), DiagramFlow("f4", "n3", "n4"),
               DiagramFlow("f5", "n3", "n5"), DiagramFlow("f6", "n4", "n5")),
    )
    slots = diagram.stage_slots()
    by_step = {s.step: s for s in slots}
    ok("图上认不出阶段的节点**没有消失**（仍占一格）",
       "OCR 识别" in by_step, str(list(by_step)))
    ghost = by_step.get("OCR 识别")
    ok("它标 mapped=False（界面据此画灰节点并标注「未接入」）",
       ghost is not None and ghost.mapped is False)
    ok("它的栈页号是哨兵 NO_PAGE（两个栈里没有它的页）",
       ghost is not None and ghost.stack_index == NO_PAGE,
       str(getattr(ghost, "stack_index", None)))
    ok("它排在真实步骤之后（不挤掉已有步骤的格序）",
       ghost is not None
       and ghost.bar_index == max(s.bar_index for s in slots),
       f"ghost={getattr(ghost, 'bar_index', None)} "
       f"max={max(s.bar_index for s in slots)}")
    ok("它的显示名就是用户自己在图上写的那个节点名",
       ghost is not None and ghost.label == "OCR 识别",
       str(getattr(ghost, "label", None)))
    pages = {s.step: s.stack_index for s in slots if s.mapped}
    ok("已接入槽位的页号不受影响（提取0/检测1/去底2/生成PDF3/拼版4）",
       pages.get("extract") == 0 and pages.get("detect") == 1
       and pages.get("rembg") == 2 and pages.get("print") == 3
       and pages.get("imposition") == 4, str(pages))
    ok("未接入的节点**不进**运行阶段（状态机不会去跑它）",
       "OCR 识别" not in diagram.stage_order()
       and all("OCR" not in stage for stage in diagram.stage_order()),
       str(diagram.stage_order()))


# ------------------------------------- 12. 列表页的节点胶囊按流程图给
def _check_list_chips_follow_diagram(ctx, ok) -> None:
    """任务列表每行的节点胶囊必须**跟着该任务的流程图**走。

    ⚠️ 2026-10-05 之前它是硬编码 ``for stage in STAGES``（四个固定阶段），
    改流程图列表也不变：图上删掉「图片去底色」照样显示"去底"，图上加了新
    步骤不显示——用户看到的"这条任务有几个节点"与实际流程对不上。

    判据 = :meth:`TaskStore.task_slots`（图的界面投影，唯一真源）。
    """
    from desktop.store import TaskStore

    from desktop.steps.bpmn_diagram import (
        KIND_TASK, DiagramFlow, DiagramNode, FlowDiagram, stage_of_name,
    )
    from desktop.workers.task_rows_worker import TaskRowsWorker

    def node(node_id: str, name: str) -> DiagramNode:
        return DiagramNode(node_id, KIND_TASK, name, stage=stage_of_name(name))

    repo = TaskStore(ctx.tmp / "chips_store")
    pdf = ctx.pdf

    def chips_of(task_id: str) -> list[str]:
        worker = TaskRowsWorker(repo)
        try:
            return [c["short"] for c in
                    worker._stage_chips(task_id, repo.stage_states(task_id),
                                        repo.node_states(task_id))]
        finally:
            worker.deleteLater()

    # ① 默认流程：四个
    full = repo.create_task(pdf, "chips-full", "胶囊-完整流程")
    ok("默认流程：四个节点胶囊",
       chips_of(full) == ["提取", "检测", "去底", "PDF"], str(chips_of(full)))
    ok("默认流程的胶囊个数 = 槽位里的真实步骤数",
       len(chips_of(full)) == len([s for s in repo.task_slots(full)
                                   if not s.optional]))

    # ② 图里删掉「图片去底色」→ 胶囊跟着少一枚（不再显示"去底"）
    short = FlowDiagram(
        nodes=(node("s0", "提取图片"), node("s1", "检测文本框"),
               node("s2", "PDF排版")),
        flows=(DiagramFlow("g1", "s0", "s1"), DiagramFlow("g2", "s1", "s2")),
    )
    task = repo.create_task(pdf, "chips-short", "胶囊-无去底色", diagram=short)
    shorts = chips_of(task)
    ok("图里删掉一步 → 列表胶囊跟着少一枚（不再显示「去底」）",
       shorts == ["提取", "检测", "PDF"], str(shorts))
    ok("胶囊顺序按步骤条格序（不是写死的四步顺序）",
       shorts == ["提取", "检测", "PDF"], str(shorts))

    # ③ 图里有"没功能"的节点 → 胶囊**不含**它（不能执行的不占节点）
    ghosty = FlowDiagram(
        nodes=(node("h0", "提取图片"), node("h1", "OCR 识别"),
               node("h2", "PDF排版")),
        flows=(DiagramFlow("k1", "h0", "h1"), DiagramFlow("k2", "h1", "h2")),
    )
    task = repo.create_task(pdf, "chips-ghost", "胶囊-带未知节点",
                            diagram=ghosty)
    ok("图里没功能的节点不进胶囊（不可执行的不占节点名额）",
       chips_of(task) == ["提取", "PDF"], str(chips_of(task)))

    # ④ stage_states 仍保留全部静态键（调用方大量硬索引），另给 in_flow 标记
    states = repo.stage_states(full)
    ok("stage_states 保留全部四个静态键（硬索引调用方不能 KeyError）",
       set(states) == {"extract", "detect", "rembg", "print"}, str(set(states)))
    flag_task = repo.create_task(pdf, "chips-flag", "胶囊-in_flow 标记",
                                 diagram=short)
    states_short = repo.stage_states(flag_task)
    ok("in_flow 标记：不在图里的阶段被标 False",
       states_short["rembg"]["in_flow"] is False
       and states_short["extract"]["in_flow"] is True,
       str({k: v["in_flow"] for k, v in states_short.items()}))
    # ⚠️ ``stage_states`` 的键是**界面步骤**（四个），不含 detect_submit 那种
    #    "同格内的第二个动作"——它要问 flow_stages（按格摊开后的运行阶段）。
    ok("flow_stages 按**界面格**摊开：同格的提交动作跟着检测一起去掉",
       repo.flow_stages(flag_task) == {"extract", "detect", "detect_submit", "print"},
       str(repo.flow_stages(flag_task)))
    ok("默认流程里 flow_stages 含同格的 detect_submit（共存亡）",
       "detect_submit" in repo.flow_stages(full),
       str(repo.flow_stages(full)))

    # ⑤ 读不到流程 ⇒ 诚实地给空，不伪造默认胶囊
    # 以前两处兜底都会伪造"四个默认阶段"：``flow_stages`` 异常回 ``set(STAGES)``、
    # ``_stage_chips`` 读不到槽位就地编四个。流程图坏了的任务在列表里显示四个
    # 默认胶囊——"自定义流程里总是冒出默认流程"的观感来源之一。
    # ⚠️ 拿"删掉任务目录"测不到这条：``task_diagram`` 对缺失文件会回落默认模板
    # （那是另一条有告警的降级），根本走不到 except。这里直接让 ``task_slots``
    # 抛错，验的就是 except 里的 honesty。
    _real_slots = repo.task_slots
    try:
        def _boom(task_id: str):
            raise RuntimeError("磁盘坏了（自测模拟）")
        repo.task_slots = _boom
        ok("task_slots 抛错 ⇒ flow_stages 给空集（不伪造四个默认阶段）",
           repo.flow_stages(full) == set(), str(repo.flow_stages(full)))
        _states_boom = repo.stage_states(full)
        ok("task_slots 抛错 ⇒ stage_states 的键还在（硬索引不崩）"
           "，in_flow 全 False",
           set(_states_boom) == {"extract", "detect", "rembg", "print"}
           and all(not v["in_flow"] for v in _states_boom.values()),
           str({k: v["in_flow"] for k, v in _states_boom.items()}))
        ok("task_slots 抛错 ⇒ 列表胶囊是空（不伪造）",
           chips_of(full) == [], str(chips_of(full)))
    finally:
        repo.task_slots = _real_slots
    for task_id in (full, task, flag_task):
        try:
            repo.delete_task(task_id)
        except Exception:  # noqa: BLE001 - 清理失败不该让自测失败
            pass


def _check_chips_status_by_node(ctx, ok) -> None:
    """列表胶囊的**颜色**按"节点"取，不按"阶段"取（2026-11-17 用户报 0011）。

    现象：某任务的「检测文本框」胶囊一直是灰色「未执行」，可它的裁图产物明明
    已经产出、下游去底/拼版/PDF 全跑完了（用户截图 0011 一行）。

    根因：「检测文本框」这一格在 ``runs.json`` 里对应**两个动作**——
    ``detect``（YOLO 出框）与 ``detect_submit``（提交裁图）。沿用上一页 /
    全部手工标注时不跑 ``detect``，``runs["detect"]`` 压根没有记录；
    按``stage``取 ``stage_states()`` 就只会读到"没有记录 ⇒ pending"。

    用户口径：「只要这个节点执行过，那么就应当是生效的」。判据 = 详情页步骤条
    同一条：``store.node_states()`` 按节点 id 归并同格内的全部动作。

    同时守住反向：**节点没跑过**就是灰的（不能因为"同阶段的另一个节点跑过"
    而点亮——那是多节点任务里最容易造假的一种绿）。
    """
    from desktop.steps.bpmn_diagram import (
        KIND_END, KIND_START, KIND_TASK, DiagramFlow, DiagramNode, FlowDiagram,
    )
    from desktop.store import TaskStore
    from desktop.workers.task_rows_worker import TaskRowsWorker

    repo = TaskStore(ctx.tmp / "chips_status_store")
    pdf = ctx.pdf

    def chips(task_id: str) -> list[dict]:
        worker = TaskRowsWorker(repo)
        try:
            return worker._stage_chips(
                task_id, repo.stage_states(task_id), repo.node_states(task_id)
            )
        finally:
            worker.deleteLater()

    def chip_of(chips_: list[dict], short: str, nth: int = 0) -> dict:
        hits = [c for c in chips_ if c["short"] == short]
        return hits[nth] if len(hits) > nth else {}

    def mark(task_id: str, stage: str, node: str, done: int = 3) -> None:
        """直接往 runs.json 里记一条成功记录（不真跑 worker）。"""
        run_id = repo.create_stage_run(task_id, stage, {}, node_id=node)
        repo.finish_stage(task_id, run_id, "success", progress=(done, done))

    created: list[str] = []
    try:
        # ① 全新任务：四个胶囊都在，且全是灰色「未执行」
        fresh = repo.create_task(pdf, "chips-status-fresh", "胶囊-全新任务")
        created.append(fresh)
        fresh_chips = chips(fresh)
        ok("全新任务：四个胶囊照旧画出来（不是空）",
           [c["short"] for c in fresh_chips] == ["提取", "检测", "去底", "PDF"],
           str([c["short"] for c in fresh_chips]))
        ok("全新任务：胶囊全是「未执行」（pending），一个都不许绿",
           all(c["status"] == "pending" for c in fresh_chips),
           str([c["status"] for c in fresh_chips]))

        # ② 只跑了「提交检测结果」（detect_submit），没跑 YOLO 检测（detect）
        #    ⇒ 检测胶囊必须是绿的，进度取提交那次的数量。
        only_submit = repo.create_task(pdf, "chips-status-submit",
                                       "胶囊-只提交裁图")
        created.append(only_submit)
        de_node = next(
            s.node_id for s in repo.task_slots(only_submit)
            if s.step == "detect"
        )
        mark(only_submit, "detect_submit", de_node, done=7)
        ok("只提交过裁图（没有 detect 记录）⇒ 阶段级状态仍是 pending",
           repo.stage_states(only_submit)["detect"]["status"] == "pending",
           str(repo.stage_states(only_submit)["detect"]))
        de_chip = chip_of(chips(only_submit), "检测")
        ok("只提交过裁图 ⇒ 检测胶囊是「成功」（节点执行过就生效）",
           de_chip.get("status") == "success", str(de_chip))
        ok("检测胶囊的提示带提交那次的进度",
           "7/7" in str(de_chip.get("tip")), str(de_chip.get("tip")))

        # ③ 多节点反向：同阶段有两个节点，只跑了第一个 ⇒ 第二个仍是灰的
        #    （按阶段取会把"另一个节点的成功"借过来，正是 B 方案要防的）
        twin = FlowDiagram(
            nodes=(
                DiagramNode("s0", KIND_START, "源PDF"),
                DiagramNode("e1", KIND_TASK, "提取图片", stage="extract"),
                DiagramNode("d1", KIND_TASK, "检测文本框", stage="detect"),
                DiagramNode("d2", KIND_TASK, "检测文本框2", stage="detect"),
                DiagramNode("p1", KIND_TASK, "PDF排版", stage="print"),
                DiagramNode("s9", KIND_END, "完成"),
            ),
            flows=(
                DiagramFlow("t0", "s0", "e1"),
                DiagramFlow("t1", "e1", "d1"),
                DiagramFlow("t2", "d1", "d2"),
                DiagramFlow("t3", "d2", "p1"),
                DiagramFlow("t4", "p1", "s9"),
            ),
        )
        two = repo.create_task(pdf, "chips-status-two", "胶囊-两个检测节点",
                              diagram=twin)
        created.append(two)
        mark(two, "detect", "d1")
        two_chips = chips(two)
        ok("两个检测节点：胶囊也画两枚「检测」",
           len([c for c in two_chips if c["short"] == "检测"]) == 2,
           str([c["short"] for c in two_chips]))
        ok("两个检测节点：跑过的那个绿、没跑的那个灰（不借邻节点状态）",
           chip_of(two_chips, "检测", 0).get("status") == "success"
           and chip_of(two_chips, "检测", 1).get("status") == "pending",
           str([c["short"] + "=" + c["status"] for c in two_chips]))
    finally:
        for task_id in created:
            try:
                repo.delete_task(task_id)
            except Exception:  # noqa: BLE001 - 清理失败不该让自测失败
                pass
