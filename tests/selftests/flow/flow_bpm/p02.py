# -*- coding: utf-8 -*-
"""``flow_bpm`` 第 2 章：任务流程 / 自定义流程 / 坏文件回落。"""

from __future__ import annotations

from ._helpers import _CUSTOM_WIRING


def run(st) -> None:
    _check_task_flow(st.ctx, st.ok)
    _check_custom_flow(st.ctx, st.ok)
    _check_broken_flow(st.ctx, st.ok)


# ---------------------------------------------------------------- 3. 任务流程
def _check_task_flow(ctx, ok) -> None:
    """③ 建任务即落 flow.bpmn；stage_input 与 ports.resolve_input 逐端口相等。"""
    from desktop.steps import ports
    from desktop.steps.flow import FlowDefinition, default_flow_path
    from desktop.store import TaskStore

    repo = TaskStore(ctx.tmp / "flow_store")
    tid = repo.create_task(ctx.pdf, "hash-flow", "流程样本")
    try:
        flow_path = default_flow_path(repo.task_dir(tid))
        ok("建任务后 flow.bpmn 存在", flow_path.is_file(), str(flow_path))
        # ⚠️ 口径：**模板文件才是默认流程**（用户 2026-10-05："默认流程必须跟
        #    task_default.bpmn 一样……不要你自己设计默认流程"）。
        #    以前这里比的是 `FlowDefinition.default()`——那份是**端口级依赖
        #    边表**派生的，与流程图不是一回事（端口边表达"取谁的文件"，流程
        #    连线表达"先做哪一步"）。拿它当默认流程，文件里就长出
        #    `extract --pages--> rembg` 这种非流程连线。
        from desktop.steps.bpmn_diagram import FlowDiagram
        from desktop.steps.scheduler import load_default_diagram

        on_disk = FlowDiagram.load(flow_path)
        template = load_default_diagram()
        ok("落盘的流程 = 默认模板文件（逐节点/逐连线一致）",
           [n.name for n in on_disk.nodes] == [n.name for n in template.nodes]
           and [(f.source, f.target) for f in on_disk.flows]
           == [(f.source, f.target) for f in template.flows],
           f"{[n.name for n in on_disk.nodes]}")
        ok("落盘后运行步骤与默认模板一致",
           on_disk.stage_order() == template.stage_order(),
           f"{on_disk.stage_order()} vs {template.stage_order()}")

        # 逐端口对照，**两条契约分开验**（混在一起会误判，2026-10-05 踩过）：
        #
        # A. 声明的上游**在**本流程里 ⇒ 必须与旧实现（ports 静态表 + overrides）
        #    逐值相等——这是"没换流程时零行为变化"的保证；
        # B. 声明的上游**不在**本流程里 ⇒ 必须落到图上最近的、**在本流程里**的
        #    产出者，**绝不能指向流程外的阶段**（那会去取一个永远不会产生的
        #    目录，现象是"生成 PDF 报找不到输入"而不是流程报错）。
        in_flow = set(template.stage_order())
        # ⚠️ "在流程里"要按**界面格**判，不能按节点判：`detect_submit`（提交
        #    检测结果）是第二步内的第二个动作，图上通常不给它单独开节点——
        #    它跟着 `detect` 那一格一起活着。折叠关系在 `ports.STAGE_STEPS`。
        live_steps = {ports.STAGE_STEPS.get(s, s) for s in in_flow}

        def is_live(name: str) -> bool:
            return name in in_flow or ports.STAGE_STEPS.get(name, name) in live_steps

        checked_a = checked_b = 0
        for consumer, wiring in ports.SUPPLIERS.items():
            for port in wiring:
                for active in (False, True):
                    got = repo.stage_input(tid, consumer, port,
                                           imposition_active=active)
                    declared = ports.supplier_of(consumer, port)
                    if consumer == "print" and port == "pages":
                        declared = ports.print_pages_supplier(bool(active))
                    if declared is None or declared == ports.SUPPLY_TASK_SOURCE:
                        continue
                    if is_live(declared):
                        want = ports.resolve_input(
                            repo.task_dir(tid), consumer, port,
                            ports.print_input_overrides(active),
                        )
                        ok(f"声明的上游在流程里 ⇒ {consumer}.{port}"
                           f"(active={active}) 与旧实现一致",
                           got == want, f"{got} vs {want}")
                        checked_a += 1
                    else:
                        supplier = repo.stage_supplier(tid, consumer, port,
                                                       active)
                        ok(f"声明的上游不在流程里 ⇒ {consumer}.{port}"
                           f"(active={active}) 回退到图上最近的流程内阶段",
                           supplier is None or supplier in in_flow,
                           f"declared={declared} -> supplier={supplier}")
                        checked_b += 1
        # A 必须被覆盖到（否则这条断言等于没跑）。B 在默认模板下可能一条都没有
        # ——默认流程的声明上游全都在流程里；"回退"那条契约由 `_check_custom_flow`
        # 用一张**真的少了去底色**的图来钉。
        ok("契约 A 真的被覆盖到（不是空循环）", checked_a > 0,
           f"在流程里 {checked_a} 条 / 不在 {checked_b} 条")

        # 没有流程文件的"老任务"（手工删掉 flow.bpmn 模拟）走默认流程。
        flow_path.unlink()
        ok("老任务（无 flow.bpmn）回落默认流程",
           repo.task_diagram(tid).stage_order()
           == ports.ports_stage_order(load_default_diagram()),
           str(repo.task_diagram(tid).stage_order()))
    finally:
        repo.delete_task(tid)


# ---------------------------------------------------------------- 4. 自定义
def _check_custom_flow(ctx, ok) -> None:
    """④ 换文件就换流程：写入自定义 ``flow.bpmn``，**步骤/顺序/取产物**全跟着变。

    新契约（2026-10-05）：

    - **步骤与顺序**看文件（``stage_order`` / ``stage_slots``）；
    - **取谁的产物**仍看 ``ports`` 的声明表；声明的上游**不在本流程里**时，
      沿图往前找最近的产出者。
    """
    from pathlib import Path

    from desktop.steps import ports
    from desktop.steps.bpmn_diagram import FlowDiagram
    from desktop.store import TaskStore

    repo = TaskStore(ctx.tmp / "flow_store")
    tid = repo.create_task(ctx.pdf, "hash-flow", "流程样本")
    try:
        flow_path = Path(repo.task_dir(tid)) / "flow.bpmn"
        flow_path.write_text(_CUSTOM_WIRING, encoding="utf-8")
        # mtime 缓存要能察觉外部修改：若两次写入时间戳相同，强制失效。
        getattr(repo, "_flow_cache", {}).clear()

        task_dir = repo.task_dir(tid)
        diagram = repo.task_diagram(tid)
        ok("自定义图读得到（步骤 = 文件里的）",
           diagram.stage_order() == ("extract", "detect", "print"),
           str(diagram.stage_order()))
        ok("去掉的步骤确实不在流程里（去底色整条都没了）",
           "rembg" not in diagram.stage_order())
        ok("步骤条槽位也跟着文件变（不再有 5 格）",
           [s.step for s in repo.task_slots(tid)] == ["extract", "detect", "print"],
           str([s.step for s in repo.task_slots(tid)]))

        # 关键：声明的上游 `rembg` **不在本流程里** ⇒ 沿图往前找，落到
        # detect（本流程里真正产出 pages 的最近一步；它的 pages 由同格
        # 的 detect_submit 兑现成 stages/detect）。
        ok("声明的上游不在流程里时，按图回退到最近的产出者",
           repo.stage_input(tid, "print", "pages")
           == ports.artifact_path(task_dir, "detect_submit", "pages"),
           str(repo.stage_input(tid, "print", "pages")))
        ok("开拼版也回退（imposition 同样不在流程里）",
           repo.stage_input(tid, "print", "pages", imposition_active=True)
           == ports.artifact_path(task_dir, "detect_submit", "pages"))
        # 声明的上游**在**流程里时，仍按声明表走（不受文件连线影响）。
        ok("声明上游在流程里时仍按声明表取（rembg.pages ← detect_submit）",
           repo.stage_input(tid, "rembg", "pages")
           == ports.artifact_path(task_dir, "detect_submit", "pages"))
        ok("未声明的端口解析为 None（print 不吃 boxes）",
           repo.stage_input(tid, "print", "boxes") is None,
           str(repo.stage_input(tid, "print", "boxes")))

        # 图里**有**「图片去底色」时，print.pages 必须取去底色的成品目录
        # （``stages/rembg``），而不是沿图回退到提取原图。
        from desktop.steps.scheduler import load_default_diagram

        tid2 = repo.create_task(ctx.pdf, "hash-flow-2", "默认流程样本",
                                diagram=load_default_diagram())
        try:
            _rembg_dir = ports.artifact_path(
                repo.task_dir(tid2), "rembg", "pages")
            ok("图里有去底色 ⇒ print 取的是去底色成品目录",
               repo.stage_input(tid2, "print", "pages") == _rembg_dir,
               str(repo.stage_input(tid2, "print", "pages")))
            ok("去底色成品路径就是 stages/rembg",
               _rembg_dir == repo.task_dir(tid2) / "stages" / "rembg",
               str(_rembg_dir))
        finally:
            repo.delete_task(tid2)

        # 坏图不拖死任务：读不到 <process> 时回落**默认模板**（页面对缺失/坏
        # 文件一律宽容，否则整个详情页打不开）。
        from desktop.steps.scheduler import load_default_diagram

        flow_path.write_text("<bpmn:definitions/>", encoding="utf-8")
        getattr(repo, "_flow_cache", {}).clear()
        ok("没有 <process> 的坏文件回落默认模板",
           repo.task_diagram(tid).stage_order()
           == load_default_diagram().stage_order())
    finally:
        repo.delete_task(tid)


# ---------------------------------------------------------------- 5. 坏文件
def _check_broken_flow(ctx, ok) -> None:
    """⑤ 手编坏文件不拖死任务：回落默认流程。"""
    from pathlib import Path

    from desktop.steps import ports
    from desktop.steps.scheduler import load_default_diagram
    from desktop.store import TaskStore

    repo = TaskStore(ctx.tmp / "flow_store")
    tid = repo.create_task(ctx.pdf, "hash-flow", "流程样本")
    try:
        flow_path = Path(repo.task_dir(tid)) / "flow.bpmn"
        flow_path.write_text("<bpmn:definitions><不是XML", encoding="utf-8")
        getattr(repo, "_flow_cache", {}).clear()
        ok("非法 XML 回落默认流程",
           repo.task_diagram(tid).stage_order()
           == ports.ports_stage_order(load_default_diagram()),
           str(repo.task_diagram(tid).stage_order()))

        flow_path.write_text(
            '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"'
            ' xmlns:guji="https://guji.tools/bpmn/2025"><bpmn:process id="p">'
            '<bpmn:task id="ghost" guji:stage="ghost"/></bpmn:process>'
            "</bpmn:definitions>",
            encoding="utf-8",
        )
        getattr(repo, "_flow_cache", {}).clear()
        ok("未知阶段回落默认流程",
           repo.task_diagram(tid).stage_order()
           == ports.ports_stage_order(load_default_diagram()),
           str(repo.task_diagram(tid).stage_order()))
        # 回落后的解析必须与 ports 声明表一致（用**回落流程里存在**的那一步：
        # 默认模板不含 rembg，问它的 boxes 会得到 None——那是"这一步不在流程
        # 里、没有这个输入"，不是不一致）。
        ok("回落后的解析结果与 ports 一致",
           repo.stage_input(tid, "detect", "pages")
           == ports.resolve_input(repo.task_dir(tid), "detect", "pages"))
    finally:
        repo.delete_task(tid)
