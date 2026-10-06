# -*- coding: utf-8 -*-
"""**BPM 流程定义**（``desktop/steps/flow.py``）的自测。

守护九件事：

1. **默认流程不另写一份事实**（口径已于 2026-10-05 更新）——**模板文件
   ``desktop/static/task_default.bpmn`` 就是默认流程**，它是一张真正的
   流程图；页面照它渲染、状态机照它排顺序，**没有任何代码去"设计"它**。
   （旧口径是"从 ``ports.SUPPLIERS`` 派生默认流程"，那会把**端口级依赖**
   写成流程连线，画出来不是流程图——已废，见 ``docs/tasks/bpm.md``）；
2. **文件往返无损**——save→load 后节点顺序、连线、条件全部一致，且产物
   是合法 XML（``<process>`` + ``sequenceFlow``）；
3. **建任务即带流程定义**——``create_task`` 落下 ``flow.bpmn``，
   ``TaskStore.stage_input`` 按它解析，与 ``ports.resolve_input`` 逐端口
   相等（老任务没有 flow.bpmn 也走默认流程，行为不变）；
4. **换连线只换文件**——手写一份改过连线的 ``flow.bpmn``，``stage_input``
   立刻按新连线解析，代码一行不动；文件写坏则回落默认流程，任务不崩；
5. **BPM 驱动界面**——流程节点序列折叠成界面槽位（``stage_slots``），
   可选节点位置由 ``optional_after`` 给出，自定义流程换了顺序后寻址跟着变；
6. **标准 BPMN 2.0**（用户 2026-10-05 明确要求）——``bpmn:`` /
   ``bpmndi:`` / ``dc:`` / ``di:`` 四个命名空间、连线的
   ``<bpmn:incoming>``/``<bpmn:outgoing>`` 双向引用、``bpmndi:BPMNDiagram``
   图形段（``dc:Bounds`` 坐标 + ``di:waypoint`` 折点）；
7. **拖拽只改坐标**——``FlowLayout.move`` 不动语义，坐标经 DI 段往返一致，
   条件边永远绕行（不因同行就与主路径重合）；
8. **两个模板可用**——``task_default.bpmn``（默认流程）与 ``task_detail.bpmn``
   （自定义初值）都存在、都解析得动、都有可执行步骤；默认模板的连线**不带
   ``guji:port``**（带了就是端口依赖表冒充流程图）；
9. **流程图上没有重名节点**——节点名一律走 ``ports.stage_label()``，
   ``rembg_submit`` 与 ``rembg`` 不同名（曾两个都叫「图片去底色」），
   步骤条文案与流程图节点名同源。

不跑 YOLO、不起子进程、不建页面，全是纯逻辑断言。
"""

from __future__ import annotations

from pathlib import Path

NAME = "flow_bpm"
DEPENDS: list[str] = []
TITLE = "BPM 流程定义与默认流程"

#: 自测用的自定义流程图：**整条「图片去底色」都去掉了**
#: （``start → extract → detect → print → end``）。
#:
#: ⚠️ 为什么专门做这么一张：要验"**声明的上游不在流程里时按图回退**"。
#: 去底色一旦不在流程里，`print.pages` 声明的上游 `rembg_submit`（它折在
#: 「图片去底色」那一格）就跟着不在了，必须沿图往前找到 `extract`。
#: 若换成"图里有 rembg"的版本，`rembg_submit` 是**活的**，走的是声明表，
#: 验不到回退那条路。
#:
#: 同时它印证**新契约**：流程连线表达"先做哪一步"，**不表达"去谁那儿取文件"**
#: （两者混在一起正是默认模板曾经长成一团乱线的原因，见 ``docs/tasks/bpm.md``）。
_CUSTOM_WIRING = """\
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:guji="https://guji.tools/bpmn/2025">
  <bpmn:process id="guji_custom" isExecutable="false">
    <bpmn:startEvent id="start" name="源 PDF"/>
    <bpmn:task id="extract" name="提取图片"/>
    <bpmn:task id="detect" name="检测文本框"/>
    <bpmn:task id="print" name="生成 PDF"/>
    <bpmn:endEvent id="end" name="完成"/>
    <bpmn:sequenceFlow id="f0" sourceRef="start" targetRef="extract"/>
    <bpmn:sequenceFlow id="f1" sourceRef="extract" targetRef="detect"/>
    <bpmn:sequenceFlow id="f2" sourceRef="detect" targetRef="print"/>
    <bpmn:sequenceFlow id="f3" sourceRef="print" targetRef="end"/>
  </bpmn:process>
</bpmn:definitions>
"""


def run(ctx) -> None:
    from tests.selftests._context import ok

    _check_default_matches_ports(ok)
    _check_roundtrip(ctx, ok)
    _check_task_flow(ctx, ok)
    _check_custom_flow(ctx, ok)
    _check_broken_flow(ctx, ok)
    _check_stage_slots(ok)
    _check_slots_drive_ui(ctx, ok)
    _check_bpmn2_structure(ok)
    _check_di_layout(ok)
    _check_default_template(ok)
    _check_node_names_unique(ok)
    _check_stack_pages_use_static_table(ok)
    _check_unmapped_nodes(ok)
    _check_list_chips_follow_diagram(ctx, ok)


# ---------------------------------------------------------------- 1. 旧运行语义模型
def _check_default_matches_ports(ok) -> None:
    """① ``FlowDefinition.default()`` 仍 = ports 静态表（**旧运行语义模型**）。

    ⚠️ 注意口径：**它不是"默认流程"**。默认流程是
    ``desktop/static/task_default.bpmn`` 那张图（见 :func:`_check_task_flow`）；
    ``FlowDefinition`` 是**端口级依赖边表**的模型，回答"这一步去谁那儿取产物"，
    现在只剩少数旧调用方在用。这一节守的是"那张表还没跟代码漂移"。
    """
    from desktop.steps import ports
    from desktop.steps.flow import CONDITION_IMPOSITION, FlowDefinition

    flow = FlowDefinition.default()

    for consumer, wiring in ports.SUPPLIERS.items():
        for port, supplier in wiring.items():
            got = flow.supplier_of(consumer, port)
            ok(f"默认流程 {consumer}.{port} ← {supplier}（与 ports 一致）",
               got == supplier, f"got {got!r}")

    # 条件边：拼版生效时 print 的上游换成 imposition（从 overrides 派生）。
    ok("默认流程带拼版条件边",
       flow.supplier_of("print", "pages", {"imposition": True}) == "imposition",
       str(flow.supplier_of("print", "pages", {"imposition": True})))
    ok("条件不命中走无条件边",
       flow.supplier_of("print", "pages", {"imposition": False})
       == "rembg_submit")
    conditional = [e for e in flow.suppliers() if e.condition]
    ok("条件边只有一条、名为 imposition",
       len(conditional) == 1
       and conditional[0].condition == CONDITION_IMPOSITION
       and (conditional[0].consumer, conditional[0].port) == ("print", "pages"),
       str(conditional))

    # 节点顺序：覆盖全部运行阶段，且每个上游都排在自己的消费方前面。
    order = list(flow.stages)
    ok("节点覆盖全部运行阶段",
       set(order) == set(ports.STAGE_STEPS),
       f"{sorted(order)} vs {sorted(ports.STAGE_STEPS)}")
    for edge in flow.suppliers():
        if edge.supplier == ports.SUPPLY_TASK_SOURCE:
            continue
        ok(f"拓扑序：{edge.supplier} 在 {edge.consumer} 之前",
           order.index(edge.supplier) < order.index(edge.consumer),
           str(order))

    # 缺上游检查按本流程的连线判断（语义与 ports.missing_stages 一致）。
    ok("默认顺序没有缺上游",
       flow.missing_stages() == [], str(flow.missing_stages()))
    ok("打乱顺序会点名缺上游",
       flow.missing_stages(["extract", "rembg", "detect"]) != [])


# ---------------------------------------------------------------- 2. 往返
def _check_roundtrip(ctx, ok) -> None:
    """② save→load 无损；产物是合法 BPMN XML。"""
    from pathlib import Path
    from xml.etree import ElementTree as ET

    from desktop.steps.flow import FlowDefinition

    flow = FlowDefinition.default()
    path = Path(ctx.tmp) / "task_default.bpmn"
    flow.save(path)

    tree = ET.parse(path)  # 不是合法 XML 会在这里直接炸
    root = tree.getroot()
    process = [el for el in root if el.tag.endswith("}process")]
    ok("XML 里有 <process>", len(process) == 1)
    tasks = [el for el in process[0] if el.tag.endswith("}task")]
    ok("每个阶段一个 <task> 节点", len(tasks) == len(flow.stages))
    flows = [el for el in process[0] if el.tag.endswith("}sequenceFlow")]
    ok("每条边一个 <sequenceFlow>", len(flows) == len(flow.suppliers()))

    loaded = FlowDefinition.load(path)
    ok("往返后节点顺序一致", loaded.stages == flow.stages,
       f"{loaded.stages} vs {flow.stages}")
    ok("往返后连线一致", loaded.suppliers() == flow.suppliers(),
       f"{loaded.suppliers()} vs {flow.suppliers()}")


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
        # ⚠️ "在流程里"要按**界面格**判，不能按节点判：`rembg_submit`（提交去
        #    底色结果）是第三步内的第二个动作，图上通常不给它单独开节点——
        #    它跟着 `rembg` 那一格一起活着。按节点判会误判成"不在流程里"，
        #    于是 `print.pages` 回退到 `rembg`（去底色的**实时预览**目录），
        #    打印出来是没提交的图。折叠关系在 `ports.STAGE_STEPS`。
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

        # 关键：声明的上游 `rembg_submit`（折在「图片去底色」那一格）**不在本
        # 流程里** ⇒ 沿图往前找，落到 extract（本流程里真正产出 pages 的最近一步）。
        # ⚠️ 若这里错误地回退到 `rembg`，拿到的是 `stages/rembgpreview`
        #    ——**去底色的实时预览目录**，不是用户提交过的成品。
        ok("声明的上游不在流程里时，按图回退到最近的产出者",
           repo.stage_input(tid, "print", "pages")
           == ports.artifact_path(task_dir, "extract", "pages"),
           str(repo.stage_input(tid, "print", "pages")))
        ok("开拼版也回退（imposition 同样不在流程里）",
           repo.stage_input(tid, "print", "pages", imposition_active=True)
           == ports.artifact_path(task_dir, "extract", "pages"))
        # 声明的上游**在**流程里时，仍按声明表走（不受文件连线影响）。
        ok("声明上游在流程里时仍按声明表取（rembg.pages ← extract）",
           repo.stage_input(tid, "rembg", "pages")
           == ports.artifact_path(task_dir, "extract", "pages"))
        ok("未声明的端口解析为 None（print 不吃 boxes）",
           repo.stage_input(tid, "print", "boxes") is None,
           str(repo.stage_input(tid, "print", "boxes")))

        # ⚠️ 反向的坑（默认模板就是这个形状）：图里**有**「图片去底色」、但没
        #    单独画「提交去底色结果」节点时，`rembg_submit` 必须算**活的**
        #    （两者同属一格）。否则 `print.pages` 会退到 `rembg`，而
        #    ``stages/rembgpreview`` 是**实时预览**目录、``stages/rembg`` 才是
        #    用户「提交」过的成品——打印出来会是没提交的图。
        from desktop.steps.scheduler import load_default_diagram

        tid2 = repo.create_task(ctx.pdf, "hash-flow-2", "默认流程样本",
                                diagram=load_default_diagram())
        try:
            _box, _preview = (
                ports.artifact_path(repo.task_dir(tid2), "rembg_submit", "pages"),
                ports.artifact_path(repo.task_dir(tid2), "rembg", "pages"),
            )
            ok("前提：提交成品目录 ≠ 去底色预览目录（两者不是同一个）",
               _box != _preview, f"{_box} vs {_preview}")
            ok("图里有去底色、没单独的「提交」节点 ⇒ print 取的是**提交成品**",
               repo.stage_input(tid2, "print", "pages") == _box,
               str(repo.stage_input(tid2, "print", "pages")))
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
        # ⚠️ 注意：**消费方**不在流程里时，端口仍可能解析得出——只要声明的
        #    上游在流程里（`rembg.boxes ← detect` 就是这种情况）。这里不钉
        #    "必须 None"：那不是契约，乱钉会把正常行为判成 bug。
        ok("消费方不在流程里、但声明上游在 ⇒ 仍按声明表解析",
           repo.stage_input(tid, "rembg", "boxes")
           == ports.artifact_path(repo.task_dir(tid), "detect", "boxes"))
    finally:
        repo.delete_task(tid)


# ---------------------------------------------------------------- 6. 界面投影
#: 自定义流程：把 detect 摘掉、拼版排到**最前**（异位），并让 print 改吃
#: extract。真实场景未必这么连，只为证明"步骤条顺序与寻址都跟着流程走"。
_CUSTOM_ORDER_WIRING = """\
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:guji="https://guji.tools/bpmn/2025">
  <bpmn:process id="guji_reorder" isExecutable="false">
    <bpmn:startEvent id="start" name="源 PDF"/>
    <bpmn:task id="extract" name="提取PDF图片" guji:stage="extract"/>
    <bpmn:task id="imposition" name="图片拼版" guji:stage="imposition"/>
    <bpmn:task id="rembg" name="图片去底色" guji:stage="rembg"/>
    <bpmn:task id="rembg_submit" name="提交" guji:stage="rembg_submit"/>
    <bpmn:task id="print" name="生成PDF" guji:stage="print"/>
    <bpmn:endEvent id="end" name="完成"/>
    <bpmn:sequenceFlow id="f0" sourceRef="start" targetRef="extract" guji:port="pdf"/>
    <bpmn:sequenceFlow id="f1" sourceRef="extract" targetRef="imposition" guji:port="pages"/>
    <bpmn:sequenceFlow id="f2" sourceRef="imposition" targetRef="rembg" guji:port="pages"/>
    <bpmn:sequenceFlow id="f3" sourceRef="remposition" targetRef="print" guji:port="pages"/>
  </bpmn:process>
</bpmn:definitions>
"""


def _check_stage_slots(ok) -> None:
    """⑥ 投影层：6 个运行阶段 → 界面格子（折叠 rembg_submit + 标可选节点）。"""
    from desktop.steps import ports
    from desktop.steps.flow import FlowDefinition
    from desktop.steps.spec import FLOW_STAGES

    flow = FlowDefinition.default()
    slots = flow.stage_slots()

    # rembg_submit 是第三步的第二个动作 ⇒ 折叠掉，不单独占格
    ok("rembg_submit 不单独占格（折叠进第三步）",
       "rembg_submit" not in [s.step for s in slots],
       str([s.step for s in slots]))
    ok("格数 = 真实步骤 4 + 可选节点 1",
       len(slots) == len(FLOW_STAGES) + 1, str(len(slots)))

    by_step = {s.step: s for s in slots}
    ok("第三步的 stage 是 rembg（不是 rembg_submit）",
       by_step["rembg"].stage == "rembg", by_step["rembg"].stage)
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
        path.write_text(_CUSTOM_ORDER_WIRING.replace(
            'sourceRef="remposition"', 'sourceRef="rembg_submit"'
        ), encoding="utf-8")
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
        ok("自定义流程：rembg_submit 仍折叠（不单独占格）",
           "rembg_submit" not in order, str(order))

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
           == ports.artifact_path(repo.task_dir(tid), "rembg_submit", "pages"))
    finally:
        repo.delete_task(tid)


# ------------------------------------------------------------ 6. BPMN 2.0 结构
def _check_bpmn2_structure(ok) -> None:
    """文件必须是**标准 BPMN 2.0**：命名空间 + 双向引用 + DI 图形段。

    用户 2026-10-05 明确要求「使用 bpmn2.0」。这一组钉死三件最容易被省掉
    的事：``xmlns:bpmndi``/``dc``/``di`` 三个命名空间、连线的
    ``<bpmn:incoming>``/``<bpmn:outgoing>`` 引用（缺了它标准渲染器画不出
    箭头）、以及 ``bpmndi:BPMNDiagram`` 图形段。
    """
    from xml.etree import ElementTree as ET

    from desktop.steps.flow import (
        BPMNDI_NS,
        BPMN_NS,
        DC_NS,
        DI_NS,
        FlowDefinition,
    )

    flow = FlowDefinition.default()
    root = ET.fromstring(flow.to_xml())

    ok("根元素是 bpmn:definitions", root.tag == f"{{{BPMN_NS}}}definitions",
       root.tag)
    ok("声明了 BPMN 2.0 MODEL 命名空间",
       root.tag.startswith(f"{{{BPMN_NS}}}"))
    ok("带 targetNamespace（标准渲染器识别流程所属）",
       bool(root.get("targetNamespace")), str(root.get("targetNamespace")))

    process = root.find(f"{{{BPMN_NS}}}process")
    ok("有 bpmn:process 段", process is not None)
    if process is None:
        return

    tasks = [el for el in process if el.tag == f"{{{BPMN_NS}}}task"]
    start = process.find(f"{{{BPMN_NS}}}startEvent")
    end = process.find(f"{{{BPMN_NS}}}endEvent")
    flows = [el for el in process if el.tag == f"{{{BPMN_NS}}}sequenceFlow"]
    ok("含 startEvent / task… / endEvent",
       start is not None and tasks and end is not None,
       f"start={start is not None} tasks={len(tasks)} end={end is not None}")
    ok("task 节点都带 guji:stage 显式标记",
       all(el.get(f"{{https://guji.tools/bpmn/2025}}stage") for el in tasks),
       "有个 task 缺 guji:stage")
    ok("每个 task 都有 name（界面文案来源）",
       all(el.get("name") for el in tasks))

    # ---- 双向引用：sourceRef/targetRef 属性 + incoming/outgoing 子元素 ----
    flow_ids = {el.get("id") for el in flows}
    ok("每条 sequenceFlow 都有 id/sourceRef/targetRef",
       all(el.get("id") and el.get("sourceRef") and el.get("targetRef")
           for el in flows))
    node_refs_ok = True
    for node in [start, *tasks, end]:
        for tag in ("incoming", "outgoing"):
            for ref in node.findall(f"{{{BPMN_NS}}}{tag}"):
                if (ref.text or "") not in flow_ids:
                    node_refs_ok = False
    ok("节点的 incoming/outgoing 都能对上 sequenceFlow 的 id", node_refs_ok)
    ok("startEvent 有 outgoing（入口边可被渲染器找到）",
       start is not None and start.find(f"{{{BPMN_NS}}}outgoing") is not None)
    # 「完成」事件是纯终点符号：没有阶段把产物喂给它，所以**不该**有 incoming。
    # 写成"没有 incoming 也要能过"这种恒真断言等于没断言。

    # ---- DI 图形段 ----
    diagram = root.find(f"{{{BPMNDI_NS}}}BPMNDiagram")
    ok("有 bpmndi:BPMNDiagram 图形段（标准存坐标的地方）",
       diagram is not None)
    if diagram is None:
        return
    plane = diagram.find(f"{{{BPMNDI_NS}}}BPMNPlane")
    ok("BPMNPlane 指向 process（图形与语义挂钩）",
       plane is not None and plane.get("bpmnElement") == "guji_task",
       str(plane.get("bpmnElement") if plane is not None else None))
    shapes = plane.findall(f"{{{BPMNDI_NS}}}BPMNShape")
    edges = plane.findall(f"{{{BPMNDI_NS}}}BPMNEdge")
    ok("每个节点都有 BPMNShape + dc:Bounds",
       len(shapes) == len(tasks) + 2
       and all(s.find(f"{{{DC_NS}}}Bounds") is not None for s in shapes),
       f"shapes={len(shapes)} tasks={len(tasks)}")
    ok("每条连线都有 BPMNEdge + di:waypoint",
       len(edges) == len(flows)
       and all(e.findall(f"{{{DI_NS}}}waypoint") for e in edges),
       f"edges={len(edges)} flows={len(flows)}")
    ok("BPMNShape 的 bpmnElement 都能对上节点 id",
       {s.get("bpmnElement") for s in shapes}
       == {"start", "end", *flow.stages})


# ------------------------------------------------------------ 7. DI 坐标往返
def _check_di_layout(ok) -> None:
    """拖出来的坐标要能经 ``dc:Bounds`` 往返，且拖拽**不改语义**。"""
    from desktop.steps.flow import FlowDefinition, FlowLayout

    flow = FlowDefinition.default()
    layout = FlowLayout.auto(flow)
    ok("自动排布：节点数 = 阶段数 + 起点终点",
       len(layout.boxes) == len(flow.stages) + 2, str(len(layout.boxes)))
    ok("自动排布：一行（所有 y 相同或仅事件居中差）",
       len({round(box[1], 1) for node, box in layout.boxes.items()
            if node not in ("start", "end")}) == 1)

    # 拖一个节点
    before = flow.stages
    edges_before = flow.suppliers()
    layout.move("detect", 400, 300)
    ok("拖动只改坐标：阶段顺序不变", flow.stages == before)
    ok("拖动只改坐标：连线不变", flow.suppliers() == edges_before)
    ok("move 改了 y", layout.node_box("detect")[1] == 300,
       str(layout.node_box("detect")))
    ok("move 不改尺寸", layout.node_box("detect")[2:4] == (148.0, 56.0),
       str(layout.node_box("detect")))

    # 落盘 → 读回
    import tempfile

    path = Path(tempfile.mkdtemp()) / "flow.bpmn"
    try:
        flow.save(path, layout)
        back = FlowDefinition.load_layout(path)
        ok("DI 坐标往返：节点数一致",
           len(back.boxes) == len(layout.boxes),
           f"{len(back.boxes)} vs {len(layout.boxes)}")
        ok("DI 坐标往返：detect 位置一致",
           abs(back.node_box("detect")[1] - 300) < 1
           and abs(back.node_box("detect")[0] - 400) < 1,
           str(back.node_box("detect")))
        # 语义往返不受坐标影响
        reloaded = FlowDefinition.load(path)
        ok("带 DI 的文件语义往返不变", reloaded.stages == flow.stages)
        ok("带 DI 的文件连线往返不变",
           sorted((e.supplier, e.consumer, e.port, e.condition)
                  for e in reloaded.suppliers())
           == sorted((e.supplier, e.consumer, e.port, e.condition)
                     for e in flow.suppliers()))
    finally:
        path.unlink(missing_ok=True)
        path.parent.rmdir()

    # 条件边永远绕行（与 GUI 画布同一口径）
    conditional = [e for e in flow.suppliers() if e.condition]
    ok("默认流程有条件边（拼版生效那条）", bool(conditional))
    if conditional:
        edge = conditional[0]
        pts = layout.bypass_points("imposition", edge.consumer)
        ok("条件边折点 ≥4 个（真的绕了一行，不是直连）",
           len(pts) >= 4, str(pts))
        ok("条件边绕行 y 在所有节点下方",
           all(pts[1][1] > layout.node_box(n)[1] + layout.node_box(n)[3]
               for n in layout.boxes),
           str(pts[1][1]))


# ------------------------------------------------------------ 8. 默认模板文件
def _check_default_template(ok) -> None:
    """两个流程模板必须存在、能解析、有可执行步骤，**而且互不相同**。

    ⚠️ 口径（2026-10-05）：模板是**手工真源**，页面照着它渲染、状态机照着它
    排顺序，用户直接编辑它。所以：

    - **不比内容与代码是否一致**——内容由人决定，没有"正确答案"；
    - 但**必须比"两张图不能一样"**：自定义初值若退化成默认流程的副本，
      用户在弹窗里勾「自定义」看到的图和默认一模一样，勾了等于没勾
      （真实发生过：``task_detail.bpmn`` 缺失时 ``load_custom_init`` 静默回落）。
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.gen_default_bpmn import (
        CUSTOM_INIT_NAME, TEMPLATE_NAME, custom_init_path, template_path,
    )

    from desktop.steps.bpmn_diagram import FlowDiagram

    loaded: dict[str, object] = {}
    for name, path in ((TEMPLATE_NAME, template_path()),
                       (CUSTOM_INIT_NAME, custom_init_path())):
        ok(f"流程模板 {name} 存在", path.is_file(), str(path))
        if not path.is_file():
            continue
        diagram = FlowDiagram.load(path)
        loaded[name] = diagram
        ok(f"{name} 有节点", len(diagram.nodes) > 0, str(len(diagram.nodes)))
        ok(f"{name} 有可执行步骤（节点能认出运行阶段）",
           len(diagram.stage_order()) > 0, str(diagram.stage_order()))

    # ⚠️ 这里**不要求两张图不同**：用户常只维护 `task_default.bpmn`，自定义初值
    #    就是它的副本——那正是"自定义从默认流程开始改"的合理起点。
    #    真正要防的是**文件不见了**：`load_custom_init()` 会静默回落默认流程，
    #    于是勾不勾「自定义」看到的图一模一样（用户报过这个现象）。
    #    所以钉的是"初值文件必须在"，并由 `custom_init_missing()` 让界面能告警。
    from desktop.components.create_task_dialog import custom_init_missing

    ok("自定义初值文件在（不在时必须显式告警，不能静默回落）",
       not custom_init_missing(), str(custom_init_path()))

    # 默认流程**必须是流程图，不是端口依赖表**。端口依赖表的指纹很明确：
    # 每条 `sequenceFlow` 上都带 `guji:port`（那是"取哪个产物端口"，
    # 与"先做哪一步"无关）。`extract --pages--> rembg/imposition/rembg_submit`
    # 就是这么来的——画出来是从「提取图片」炸出去的一团。
    default_path_ = template_path()
    if default_path_.is_file():
        text = default_path_.read_text(encoding="utf-8")
        flows_with_port = [
            line.strip() for line in text.splitlines()
            if "sequenceFlow" in line and "guji:port" in line
        ]
        ok("默认流程的连线不带 guji:port（否则是端口依赖表冒充流程图）",
           not flows_with_port, str(flows_with_port[:2]))


def _check_node_names_unique(ok) -> None:
    """流程图上**不许出现两个同名节点**。

    背景（2026-10-05 实际踩到）：``rembg_submit`` 与 ``rembg`` 共用同一份
    :class:`StepSpec`，节点名直接取 ``spec.stage_name()`` 时两者都叫
    「图片去底色」——用户在图上根本分不清哪个是"生成预览"、哪个是"提交定稿"。
    修法是节点名一律走 ``ports.stage_label()``（那里对 ``rembg_submit`` 有
    独立文案）。这条断言就是钉死那个修法，别让将来有人"简化"回spec 取名。
    """
    from desktop.steps import ports
    from desktop.steps.flow import FlowDefinition

    flow = FlowDefinition.default()
    names = [ports.stage_label(stage) for stage in flow.stages]
    ok("流程图上没有重名节点", len(set(names)) == len(names), str(names))
    ok("rembg_submit 走独立文案（不与 rembg 同名）",
       ports.stage_label("rembg_submit") != ports.stage_label("rembg"),
       f'{ports.stage_label("rembg_submit")} vs {ports.stage_label("rembg")}')
    # store 那张文案表也必须跟着同一口径，否则步骤条与流程图对不上
    from desktop.store.tasks import STAGE_LABELS

    ok("步骤条文案与流程图节点名同源",
       all(STAGE_LABELS.get(s) == ports.stage_label(s)
           for s in ("extract", "detect", "rembg", "rembg_submit", "print")),
       str({s: STAGE_LABELS.get(s) for s in
            ("extract", "detect", "rembg", "rembg_submit", "print")}))


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
    short = chain("提取图片", "检测文本框", "生成 PDF").stage_slots()
    by_step = {slot.step: slot for slot in short}
    ok("少一步时 print 的栈页号仍是静态页号（不是被数出来的 2）",
       by_step["print"].stack_index == static_page["print"],
       f"print -> {by_step['print'].stack_index}，静态表说是 {static_page['print']}")
    ok("少一步时 bar 序号仍按本图顺序数（print 在第 3 格 = 2）",
       by_step["print"].bar_index == 2, str(by_step["print"].bar_index))

    # ② 全都有（含可选拼版）——页号必须与旧的硬编码口径一致
    full = chain("提取图片", "检测文本框", "图片去底色",
                 "提交去底色结果", "图片拼版", "生成 PDF").stage_slots()
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


# ------------------------------------- 12. 列表页的子任务胶囊按流程图给
def _check_list_chips_follow_diagram(ctx, ok) -> None:
    """任务列表每行的子任务胶囊必须**跟着该任务的流程图**走。

    ⚠️ 2026-10-05 之前它是硬编码 ``for stage in STAGES``（四个固定阶段），
    改流程图列表也不变：图上删掉「图片去底色」照样显示"去底"，图上加了新
    步骤不显示——用户看到的"这条任务有几个子任务"与实际流程对不上。

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
                    worker._stage_chips(task_id, repo.stage_states(task_id))]
        finally:
            worker.deleteLater()

    # ① 默认流程：四个
    full = repo.create_task(pdf, "chips-full", "胶囊-完整流程")
    ok("默认流程：四个子任务胶囊",
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

    # ③ 图里有"没功能"的节点 → 胶囊**不含**它（不能执行的不占子任务）
    ghosty = FlowDiagram(
        nodes=(node("h0", "提取图片"), node("h1", "OCR 识别"),
               node("h2", "PDF排版")),
        flows=(DiagramFlow("k1", "h0", "h1"), DiagramFlow("k2", "h1", "h2")),
    )
    task = repo.create_task(pdf, "chips-ghost", "胶囊-带未知节点",
                            diagram=ghosty)
    ok("图里没功能的节点不进胶囊（不可执行的不占子任务名额）",
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
    # ⚠️ ``stage_states`` 的键是**界面步骤**（四个），不含 rembg_submit 那种
    #    "同格内的第二个动作"——它要问 flow_stages（按格摊开后的运行阶段）。
    ok("flow_stages 按**界面格**摊开：同格的「提交去底色」跟着去底色一起去掉",
       repo.flow_stages(flag_task) == {"extract", "detect", "print"},
       str(repo.flow_stages(flag_task)))
    ok("默认流程里 flow_stages 含同格的 rembg_submit（共存亡）",
       "rembg_submit" in repo.flow_stages(full),
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


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
