# -*- coding: utf-8 -*-
"""图上的节点语义：源 PDF、配对删除、悬空事件/网关、流程要什么输入。"""

from __future__ import annotations

from desktop.steps.ports.constants import (
    GATEWAY_GUARD_STAGE,
    SOURCE_PDF_NODE_NAMES,
    SOURCE_PDF_STAGE,
)
from desktop.steps.ports.declaration import spec_for_stage


def source_pdf_node_ids(diagram) -> tuple[str, ...]:
    """图里代表「源 PDF」的节点 id（没有则空元组）。

    认法有两条，任一命中即可：

    1. **事件型**节点（``startEvent``）——BPMN 里流程入口就是它；
    2. **名字**在 :data:`SOURCE_PDF_NODE_NAMES` 里——用户可以把它改名，
       事件型仍是主判据；名字判据兜住"被改成 task 型"或用户自己画的。

    ⚠️ **别按 stage 判**：「源 PDF」没有 ``stage``（它不是运行阶段，
    :data:`desktop.steps.ports.SUPPLY_TASK_SOURCE` 才是它的语义标记）。
    """
    if diagram is None or not getattr(diagram, "nodes", ()):
        return ()
    from desktop.steps.bpmn_diagram import KIND_START

    return tuple(
        n.id
        for n in diagram.nodes
        if n.kind == KIND_START or (n.name or "").strip() in SOURCE_PDF_NODE_NAMES
    )


def is_source_pdf_node(diagram, node_id: str) -> bool:
    """这个节点是不是「源 PDF」（图上那个入口事件）。"""
    return node_id in source_pdf_node_ids(diagram)


def paired_node_for_stage(diagram, node_id: str) -> str | None:
    """删掉 ``node_id`` 时**该一起删掉**的配对节点 id；没有则 ``None``。

    用户 2026-10-06：

    > 流程编辑中，如果删除了 上传pdf或者 pdf图片提取中的一个，
    > 另外���个的存在没有意义，因此需要同步删除另外一个

    成对关系是双向的：

    - 删「源 PDF」事件 ⇒ 一并删 ``extract`` 节点；
    - 删 ``extract`` 节点 ⇒ 一并删「源 PDF」事件。

    ⚠️ **只删一个会留下坏图**：留着 startEvent 时第一步的``pages`` 沿图回溯
    不到任何产出者，界面就一直催"上传图片"；留着 extract 时它吃的是
    :data:`SUPPLY_TASK_SOURCE`（任务源 PDF），而界面上那个 PDF 图标会**仍然
    亮着**催你上传——正是用户说的"不需要 PDF 上传图标"。

    ⚠️ 返回 ``None``（而不是"没有配对就不删"里的空字符串）表示"无配对"；
    调用方**必须自己再判一次** ``extract`` 节点是否真的在图里（可能已经被
    用户先删了），别假定它一定存在。
    """
    if diagram is None or not getattr(diagram, "nodes", ()):
        return None
    if is_source_pdf_node(diagram, node_id):
        # 反向：源 PDF 被删 ⇒ 同格删掉 extract
        for item in diagram.nodes:
            if item.stage == SOURCE_PDF_STAGE:
                return item.id
        return None
    item = diagram.node(node_id)
    if item is not None and item.stage == SOURCE_PDF_STAGE:
        # 正向：extract 被删 ⇒ 同格删掉源 PDF 事件
        for other in source_pdf_node_ids(diagram):
            return other
    return None


def orphaned_end_event_ids(diagram, *node_ids: str) -> tuple[str, ...]:
    """删掉 ``node_ids`` 后会**悬空**的结束事件 id；没有则空元组。

    用户 2026-10-07：

    > 流程图编辑中，生成PDF附在PDF排版，如果删除了PDF排版，
    > 那么生成PDF就一定不存在

    默认流程里「生成PDF」是挂在「PDF排版」（``print``）后面的**结束事件**
    ——它不进拓扑序、没有运行语义，唯一意义是图示"流程在此收尾"。
    「PDF排版」一删它就一条入线不剩，留着是句谎话：图上写着"生成PDF"，
    流程却不再产出 PDF。

    ⚠️ 同名不同物（用户同日定的口径）：**步骤名**已改成「PDF排版」，与流程图
    那一格统一；而「生成PDF」现在只指两样东西——**结束事件**的名字，与**执行
    按钮**的文案（``StepSpec.run_label`` / ``run_button_text``）。

    ⚠️ 判据是**图上的性质**（入线是否全部来自将被删的节点），**不按名字
    认「生成PDF」**——用户改了名、自己画的收尾事件同理；反之「图片拼版」
    被删时「生成PDF」的入线还剩「PDF排版」那条，不跟着删。

    ⚠️ 只收**入线非空**的结束事件：本来就悬空的事件不是这次删除造成的，
    不归这里管（别借删除顺手清扫，删除面越界）。
    """
    if diagram is None or not node_ids or not getattr(diagram, "nodes", ()):
        return ()
    from desktop.steps.bpmn_diagram import KIND_END

    doomed = set(node_ids)
    orphans: list[str] = []
    for node in diagram.nodes:
        if node.kind != KIND_END or node.id in doomed:
            continue
        incoming = [f for f in diagram.flows if f.target == node.id]
        if incoming and all(f.source in doomed for f in incoming):
            orphans.append(node.id)
    return tuple(orphans)


def orphaned_gateway_ids(diagram, *node_ids: str) -> tuple[str, ...]:
    """删掉 ``node_ids`` 后会**失去依附对象**的「是否拼版」网关 id；没有则空元组。

    用户 2026-10-08：

    > 是否拼版依附拼版……因此删除左侧的判断 gateway、顶部的添加判断按钮

    图上的排他网关就是「是否拼版」这个判断（见 :data:`GATEWAY_GUARD_STAGE`）：
    它问的问题只对「图片拼版」这一步成立。删掉「图片拼版」之后，网关的两条
    分支里有一条已经悬空（``remove_node`` 会连带删掉那半条线），剩下一个
    "无条件放行"的菱形——图上写着"是否拼版"，流程里却已经没有拼版这一步，
    留着就是误导。所以跟着删。

    ⚠️ **反方向不删**（用户同日的前一条口径："图片拼版可以不需要判断是否拼版"）：
    删网关不动「图片拼版」——那一步照跑，只是不再画那个分支。

    ⚠️ 判据只看"删完之后图里**还剩不剩** ``imposition``"，**不看网关连在谁身上**：
    网关是这一步的附属图形（不是独立组件），一个流程里本就只该有一个
    （网关问的是同一件事，问两遍没有意义）。
    """
    if diagram is None or not node_ids or not getattr(diagram, "nodes", ()):
        return ()
    doomed = set(node_ids)
    if not any(
        getattr(diagram.node(node_id), "stage", None) == GATEWAY_GUARD_STAGE
        for node_id in doomed
    ):
        return ()
    # 图里还剩别的「图片拼版」节点 ⇒ 网关仍有依附对象，不跟着删
    # （理论上只该有一个，但 ``add_node`` / bpmn.io 画的图都可能有两个——
    #  删掉其中一个是"删重复"，不该顺手把网关也带走）
    if any(
        node.id not in doomed and getattr(node, "stage", None) == GATEWAY_GUARD_STAGE
        for node in diagram.nodes
    ):
        return ()
    return tuple(
        node.id
        for node in diagram.nodes
        if getattr(node, "is_gateway", False) and node.id not in doomed
    )


def flow_needs_source_pdf(diagram) -> bool:
    """**这条流程**里有没有直接吃源 PDF 的阶段吗（要问图，别写死）。
    ⚠️ **两处界面问的是同一个问题**（用户 2026-10-06）：
      ①创建任务页——"流程要 PDF 而用户没给，是否问一句"；
      ②任务详情页——"流程要 PDF 而这个任务还没源文件，按钮该高亮 + 顶部
      该红字提示 + 进页面该弹窗"。所以这个判据**只有这一份实现**，
      别在两个页面各写一遍（漂移起来是"创建时问了、详情页却不提示"）。

    阶段→"要不要源 PDF"走 :meth:`StepSpec.needs_source_pdf`（端口声明
    ``inputs`` 含 ``pdf``）；⚠️ **别拿** ``input_noun()`` 判——它是给人看的
    称呼，四步里三步都写着"选择图片"，用它会把去底色/PDF排版也算进去
    （它们吃的是上游产出的页，不是用户的文件）。

    :param diagram: :class:`~desktop.steps.bpmn_diagram.FlowDiagram`；
        空图/``None`` 一律 False（没有流程就没有"要不要"可言）。
    """
    if diagram is None or not getattr(diagram, "nodes", ()):
        return False
    from desktop.steps.scheduler import Scheduler

    # ⚠️ imposition 传 False：条件不满足时那一格被剔除，而我们问的是"有没有
    #    哪一步要 PDF"，剔除它不影响答案。
    sched = Scheduler.from_diagram(diagram, {"imposition": False})
    for stage in sched.stages:
        spec = spec_for_stage(stage)
        if spec is not None and spec.needs_source_pdf():
            return True
    return False


def flow_crops_pages(diagram) -> bool:
    """这条流程里页面会不会被「检测文本框」的提交**逐框裁开**。

    2026-10-22 起没有 area：有检测节点就一定会逐框裁图（半幅 ``-l``/``-r``）。
    凡是要问"这一步拿到的图是整页还是裁好的框"的地方都用本函数，别各写一份
    "流程里有没有 detect 节点"。

    ``imposition`` 那一格传 False（条件不满足时被剔除，与答案无关）。
    空图 / 没有 detect ⇒ False（＝图是整页的）。
    """
    if diagram is None or not getattr(diagram, "nodes", ()):
        return False
    from desktop.steps.scheduler import Scheduler

    return "detect" in set(
        Scheduler.from_diagram(diagram, {"imposition": False}).stages
    )
