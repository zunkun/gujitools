# -*- coding: utf-8 -*-
"""``step_ports`` 第 4 章：源PDF 成对 / 结束事件级联 / 网关依附。"""

from __future__ import annotations


def run(st) -> None:
    _check_source_pdf_pairing(st.ok)
    _check_end_event_cascade(st.ok)
    _check_gateway_dependency(st.ok)


# ------------------------------------ 9. 源 PDF ↔ 提取图片：成对关系（纯逻辑）
def _check_source_pdf_pairing(ok) -> None:
    """「上传 PDF」与「提取图片」成对，判据是**图上的性质**（用户 2026-10-06）。

    > 如果删除了 上传pdf 或者 pdf图片提取中的一个，另外一个的存在没有意义，
    > 因此需要同步删除另外一个

    这里只验**判据**（纯逻辑，不碰界面）；真正的联动删除在
    ``bpmn_editor``（工具栏「删除」与 Delete 键**两条路径**都要成对），
    由 ``flow_ui`` 第 18 节端到端验。

    ⚠️ 「源 PDF」在图上**不是阶段**而是一个 ``startEvent``，所以
    **不能按 ``stage`` 判**——只能按事件类型或节点名认。
    """
    from desktop.steps import ports
    from desktop.steps.scheduler import load_default_diagram

    d = load_default_diagram()
    pdf_ids = ports.source_pdf_node_ids(d)
    ok("默认流程里认得出「源 PDF」节点（它是 startEvent，没有 stage）",
       len(pdf_ids) == 1, str(pdf_ids))
    ok("它是源 PDF 节点（is_source_pdf_node）",
       ports.is_source_pdf_node(d, pdf_ids[0]))
    extract = next(n.id for n in d.nodes if n.stage == "extract")
    detect = next(n.id for n in d.nodes if n.stage == "detect")

    ok("删 extract ⇒ 配对节点是「源 PDF」",
       ports.paired_node_for_stage(d, extract) in pdf_ids,
       str(ports.paired_node_for_stage(d, extract)))
    ok("删「源 PDF」⇒ 配对节点是 extract",
       ports.paired_node_for_stage(d, pdf_ids[0]) == extract,
       str(ports.paired_node_for_stage(d, pdf_ids[0])))
    ok("删其它步骤（detect）没有配对（别乱删）",
       ports.paired_node_for_stage(d, detect) is None,
       str(ports.paired_node_for_stage(d, detect)))

    # ⚠️ 已删掉 extract 时，删源 PDF **不能**再返回一个不存在的节点
    trimmed = type(d)(
        nodes=tuple(n for n in d.nodes if n.stage != "extract"),
        flows=tuple(f for f in d.flows
                    if f.source != extract and f.target != extract),
    )
    ok("extract 已经不在图里了 ⇒ 删源 PDF 没有配对（返回 None，不给幽灵 id）",
       ports.paired_node_for_stage(trimmed, pdf_ids[0]) is None,
       str(ports.paired_node_for_stage(trimmed, pdf_ids[0])))
    ok("空图/None 不炸（无节点、无配对）",
       ports.paired_node_for_stage(None, "x") is None
       and ports.source_pdf_node_ids(None) == ())


# ------------------------- 9b. 生成PDF结束事件附在PDF排版上（纯逻辑）
def _check_end_event_cascade(ok) -> None:
    """删「PDF排版」⇒ 附在后面的「生成PDF」结束事件被孤立（用户 2026-10-07）。

    > 流程图编辑中，生成PDF附在PDF排版，如果删除了PDF排版，
    > 那么生成PDF就一定不存在

    这里只验**判据**（纯逻辑，不碰界面）；编辑器两条删除路径的端到端
    联动由 ``flow_ui`` 第 19 节验。

    ⚠️ 判据是**图上的性质**（结束事件的入线是否全部来自被删节点），
    **不按名字认「生成PDF」**——结束事件不进拓扑序、没有运行语义。
    """
    from desktop.steps import ports
    from desktop.steps.bpmn_diagram import KIND_END
    from desktop.steps.scheduler import load_default_diagram

    d = load_default_diagram()
    print_node = next(n for n in d.nodes if n.stage == "print")
    imposition = next(n for n in d.nodes if n.stage == "imposition")
    detect = next(n for n in d.nodes if n.stage == "detect")
    ends = [n for n in d.nodes if n.kind == KIND_END]
    ok("默认流程里有一个结束事件（生成PDF），挂在「PDF排版」后面",
       len(ends) == 1, str([n.name for n in ends]))
    ok("删「PDF排版」⇒「生成PDF」结束事件被孤立",
       ports.orphaned_end_event_ids(d, print_node.id) == (ends[0].id,),
       str(ports.orphaned_end_event_ids(d, print_node.id)))
    ok("删「图片拼版」⇒「生成PDF」**不**孤立（入线还剩 PDF排版 那条）",
       ports.orphaned_end_event_ids(d, imposition.id) == (),
       str(ports.orphaned_end_event_ids(d, imposition.id)))
    ok("删其它步骤（detect）不牵连结束事件",
       ports.orphaned_end_event_ids(d, detect.id) == (),
       str(ports.orphaned_end_event_ids(d, detect.id)))
    ok("None/不传节点 不炸（返回空元组）",
       ports.orphaned_end_event_ids(None, "x") == ()
       and ports.orphaned_end_event_ids(d) == ())


# --------------------- 9c. 「是否拼版」网关依附「图片拼版」（纯逻辑）
def _check_gateway_dependency(ok) -> None:
    """网关**不是独立组件**：它依附「图片拼版」（用户 2026-10-08）。

    > 其实根本就没有判断这个组件，只有「是否拼版」这个特殊的判断组件，
    > 也就是说是否拼版依附拼版，因此删除左侧的判断 gateway、顶部的添加判断按钮

    本节只验**判据**（纯逻辑，不碰界面）：删掉最后一个「图片拼版」时网关
    跟着删；图里还剩拼版节点就不动它（那只是删重复）。界面上"能不能加网关"
    由"没有入口"这件事保证（``flow_ui`` 端到端验：面板与工具栏都没有那一项）。

    ⚠️ **反方向不成立**：删网关不动「图片拼版」（用户同日的前一条口径：
    "图片拼版可以不需要判断是否拼版"）。
    """
    from desktop.steps import ports
    from desktop.steps.scheduler import load_default_diagram

    d = load_default_diagram()
    gateways = [n.id for n in d.nodes if n.is_gateway]
    imposition = next(n for n in d.nodes if n.stage == "imposition")
    detect = next(n for n in d.nodes if n.stage == "detect")
    ok("默认流程里有一个「是否拼版」网关（它守着 imposition）",
       len(gateways) == 1 and ports.GATEWAY_GUARD_STAGE == "imposition",
       f"{gateways} guard={ports.GATEWAY_GUARD_STAGE}")

    ok("删「图片拼版」⇒ 依附它的网关一起删",
       ports.orphaned_gateway_ids(d, imposition.id) == (gateways[0],),
       str(ports.orphaned_gateway_ids(d, imposition.id)))
    ok("删别的步骤（detect）不牵连网关",
       ports.orphaned_gateway_ids(d, detect.id) == (),
       str(ports.orphaned_gateway_ids(d, detect.id)))
    ok("None/不传节点 不炸（返回空元组）",
       ports.orphaned_gateway_ids(None, "x") == ()
       and ports.orphaned_gateway_ids(d) == ())

    # ⚠️ 图里还剩**另一个**「图片拼版」时（``add_node`` / bpmn.io 画的图都可能
    #    有两个）删其中一个只是"删重复"，网关仍有依附对象，不该被带走。
    from desktop.steps.bpmn_diagram import KIND_TASK, DiagramNode

    twin = type(d)(
        nodes=tuple(d.nodes) + (DiagramNode("dup", KIND_TASK, "图片拼版",
                                            stage="imposition"),),
        flows=d.flows,
    )
    ok("图里还剩别的「图片拼版」⇒ 网关不跟着删（那只是删重复）",
       ports.orphaned_gateway_ids(twin, imposition.id) == (),
       str(ports.orphaned_gateway_ids(twin, imposition.id)))
