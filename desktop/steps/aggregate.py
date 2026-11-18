# -*- coding: utf-8 -*-
"""**聚合任务**的流程派生（纯逻辑，无 Qt——store 与自测都能导入）。

## 聚合任务是什么

同一部书拆成多个 PDF 子集、各建一个普通任务分别处理；处理到某一步（比如
「图片拼版」）之后，想把**所有子任务在这一步的产物**合并成一本完整的 PDF。
聚合任务就是这样一条任务：它的输入不是源文件，而是**若干成员任务在同一
节点上的产物**。

- 成员任务：创建聚合任务时从已有任务里挑选（弹窗多选），**顺序有意义**
  （决定合并时的页序）；
- 起始节点：**全体成员共用一个**（用户 2026-11-17 本轮口径：界面上用
  checkbox 列表**单选**一个），候选 = 所选子任务里**任意一个已经完成**的阶段
  （:func:`any_member_stages`，并集，用户 2026-11-18 口径；早先是"每个成员
  流程图里都有"的交集）。候选**跟着子任务列表变**：一个子任务都没选时不是
  空清单，而是允许的全集。聚合流程从起始节点开始派生：**前面的丢弃，后面的
  接上**；
- 起始节点**可以是「提取图片」**（``extract``，用户 2026-11-18：「可选，但是
  提取只能使用其产生的结果，没有输入源」）——这种聚合任务的输入就是各成员
  的提取产物（:mod:`desktop.services.aggregate_ingest` 只搬产出、不搬输入）。

⚠️ 并集有个必须让用户看见的代价：某成员没跑到这个节点 ⇒ 它交不出这一步的
产物，汇集时它的页面会被跳过。所以界面要在候选下方点名**缺这个节点的子任务**
（:func:`missing_members`），别让"少了一册"悄悄发生。

⚠️ **产物怎么进来**（本模块只管"流程从哪开始"，不管文件搬运）：创建之后由
:mod:`desktop.services.aggregate_ingest` 在后台把各成员在起始节点上的
**输入**（落到 ``stages/input/<NNN>_<页名>``）与**产出**（落到同一步骤的
产物目录）按成员顺序复制进来，并把起点记成"已完成"。页名前缀保证成员顺序
与页序都不丢。

## 流程怎么派生

真源仍是默认模板 ``task_default.bpmn``（不在这里写第二份流程顺序）：
从模板的**拓扑序**里找到起始节点，把它之前（拓扑序在前）的可执行节点
全部丢掉，然后：

- 换一个新开始事件「聚合输入」（原「上传文件」对聚合任务语义不对——
  聚合任务没有源文件）；
- 起始节点是 ``imposition`` / ``print`` 时把「是否拼版」网关一起丢掉：
  网关守护的是"拼版做不做"，用户明确选了从拼版开始（或拼版已被丢弃），
  "否"分支与选择自相矛盾；
- 结束事件（生成PDF）挂在 print 后面，print 恒被保留 ⇒ 恒保留；
- 保留图上其余节点间的连线与标签（网关的「是/否」）、以及挂在**保留**
  节点上的文字注释；
- 最后 :meth:`FlowDiagram.relayout` 重排坐标（被丢弃节点留下的空洞
  不能留在图上）。

派生出来的图交给创建面板的编辑器展示/微调；用户没再编辑时 store 直接
落这张派生图（聚合任务的 ``flow.bpmn`` **永远不是**默认模板的字节拷贝
——默认模板里还有 extract，语义不对）。
"""

from __future__ import annotations

from desktop.steps.bpmn_diagram import (
    KIND_END,
    KIND_START,
    DiagramFlow,
    DiagramNode,
    FlowDiagram,
)
from desktop.steps.scheduler import load_default_diagram

#: 聚合任务**允许的**起始节点全集（同时是排序用的拓扑序）。
#:
#: ⚠️ **含** ``extract``（用户 2026-11-18：「可选，但是提取只能使用其产生的
#: 结果，没有输入源」——从提取开始＝汇集各成员的提取产物，聚合任务自己跑
#: 检测/去底色/排版；不吃源 PDF 这条不变，汇集器对 extract 只搬产出）。
#: 更早的口径是"不含 extract"（2026-11-17），已作废。
#: ⚠️ 界面上的**候选**不是这张表：候选由所选子任务**已完成**的节点算出来
#: （:func:`any_member_stages` 并集），本表只负责"允许哪些"和"谁在前"。
AGGREGATE_START_STAGES = ("extract", "detect", "rembg", "imposition", "print")

#: 派生图上**新开始事件**的名字。原模板叫「上传文件」，对聚合任务不对——
#: 它的输入来自成员任务，不是用户上传的文件。
AGGREGATE_START_LABEL = "聚合输入"


def aggregate_start_label(stage: str) -> str:
    """起始节点的**中文**名（勾选框/摘要文案用；唯一走 ``stage_label``）。"""
    from desktop.steps.ports import stage_label

    return stage_label(stage)


def earliest_aggregate_stage(stages) -> str:
    """成员节点清单里**拓扑序最早**的一个。

    ⚠️ 界面本轮改回**全体共用**一个起始节点（用户 2026-11-17 本轮），这个
    函数现在只服务 store 的 ``member_stage`` 归一（老口径的 ``member_stages``
    仍可能长短不一，落库时取最早的那个）。

    清单为空、或给进来的全不在 :data:`AGGREGATE_START_STAGES` 里 ⇒ 返回
    **空串**（调用方自己兜底），这里不猜。
    """
    valid = [str(s) for s in (stages or []) if s in AGGREGATE_START_STAGES]
    if not valid:
        return ""
    return min(valid, key=AGGREGATE_START_STAGES.index)


def any_member_stages(stage_lists) -> tuple[str, ...]:
    """候选起始节点 = **任意一个**成员已经完成的阶段（并集，按拓扑序）。

    用户 2026-11-18：起始节点清单**跟着所选子任务变**——"现有任务已经存在
    生效的节点是提取、检测、去底，因此可以选择这些节点中的一个"。早先的
    交集口径（每个成员流程图里都必须有）在"各子集跑到不同步"时会收成空集
    （实测：三个子任务分别完成 检测/检测/去底 ⇒ 交集只剩提取），用户看不
    到任何可变项，只能看到兜底的全集——那正是这条反馈要治的病。

    ⚠️ 并集的代价：没跑到这个节点的成员交不出产物，汇集时会缺它的页面。
    调用方必须用 :func:`missing_members` 点名叫出这些成员，别静默少册。

    ``stage_lists`` = 逐成员**已完成**的阶段（各自
    ``store.completed_aggregate_stages``）。空输入（还没选子任务）⇒
    **空元组**，由调用方决定怎么兜底（创建面板按允许的全集先列出来），
    这里不猜。
    """
    found: set[str] = set()
    for stages in stage_lists or ():
        found.update(str(s) for s in (stages or ()))
    return tuple(stage for stage in AGGREGATE_START_STAGES if stage in found)


def missing_members(stage: str, stage_lists) -> tuple[int, ...]:
    """哪些成员**没完成** ``stage``（返回它们在 ``stage_lists`` 里的下标）。

    界面拿它点名"选了这个节点，但这几册没跑过 ⇒ 汇集时不会带上它们的页面"。
    没选成员时返**空元组**（没有"成员缺"这回事，别报假警）。
    """
    return tuple(
        index
        for index, stages in enumerate(stage_lists or ())
        if stage not in {str(s) for s in (stages or ())}
    )


def preferred_start_stage(stage_lists, current: str = "") -> str:
    """成员变了、当前起点不在候选里时，**默认落到哪个节点**。

    规则（按优先级）：

    1. ``current`` 还在候选里 ⇒ 原样保留（用户已经选过就别动他）；
    2. 有**每个成员都完成**过的节点 ⇒ 取其中**最靠后**的那个：那是"各子集
       都已做到、直接合并就能出书"的位置，既不丢页、也不重跑；
    3. 一个公共节点都没有（有人啥都没跑）⇒ 退回并集里**最靠前**的那个：
       起点越早，能交得出产物的成员越多——宁可多跑几步，也不静默少册。
       缺页风险由界面的点名提示兜住。

    空输入（没选成员）⇒ 返回 ``current``，让调用方自己兜底。
    """
    lists = [tuple(stages or ()) for stages in (stage_lists or ())]
    if not lists:
        return current
    union = any_member_stages(lists)
    if current in union:
        return current
    common = set(lists[0]).intersection(*lists[1:]) if len(lists) > 1 else set(lists[0])
    shared = [stage for stage in AGGREGATE_START_STAGES if stage in common]
    if shared:
        return shared[-1]
    return union[0] if union else current


def derive_aggregate_diagram(start_stage: str) -> FlowDiagram:
    """从默认模板派生聚合任务的流程图：**从 ``start_stage`` 开始，前面丢弃**。

    - ``start_stage`` 不在 :data:`AGGREGATE_START_STAGES` 里、或模板读不到
      ⇒ 返回**空图**（调用方按"没有流程"处理，不抛异常——与
      :func:`load_default_diagram` 同一条纪律）；
    - 返回的图已 :meth:`FlowDiagram.relayout` 重排坐标，可直接 ``save()``。
    """
    if start_stage not in AGGREGATE_START_STAGES:
        return FlowDiagram()
    base = load_default_diagram()
    if not base.nodes:
        return FlowDiagram()

    topo = base._topo_node_ids()
    # 拓扑序上的**可执行阶段序列**（找"起始节点之前有哪些阶段"用）
    stage_seq: list[str] = []
    for node_id in topo:
        item = base.node(node_id)
        if item is not None and item.stage:
            stage_seq.append(item.stage)
    if start_stage not in stage_seq:
        # 模板里没有这个节点（模板被改坏了）⇒ 不猜，返回空图
        return FlowDiagram()

    dropped_stages = set(stage_seq[: stage_seq.index(start_stage)])
    # 网关守护"拼版做不做"：起始节点在拼版及之后时，网关的"否"分支与
    # 用户的选择矛盾 ⇒ 丢掉（见模块头）。
    keep_gateway = start_stage in ("extract", "detect", "rembg")

    kept: list[DiagramNode] = []
    dropped_ids: set[str] = set()
    for item in base.nodes:
        if item.kind == KIND_START:
            dropped_ids.add(item.id)          # 旧开始事件恒替换
        elif item.stage and item.stage in dropped_stages:
            dropped_ids.add(item.id)          # 起始节点之前的可执行节点
        elif item.is_gateway and not keep_gateway:
            dropped_ids.add(item.id)          # 「是否拼版」网关（按需）
        else:
            kept.append(item)

    # 连线：两端都活着的才留
    flows = [
        f
        for f in base.flows
        if f.source not in dropped_ids and f.target not in dropped_ids
    ]

    # 孤儿结束事件：入线全被裁掉的事件不再保留（模板里只有 print 后那一个，
    # print 恒保留 ⇒ 恒活着；这条规则只是兜底，防模板被改出第二种结构）
    target_ids = {f.target for f in flows}
    kept = [
        item
        for item in kept
        if not (item.kind == KIND_END and item.id not in target_ids)
    ]

    # 新开始事件 → 起始节点（拓扑序里第一个该阶段的节点）
    first = next(
        (
            nid
            for nid in topo
            if nid not in dropped_ids
            and (base.node(nid) is not None and base.node(nid).stage == start_stage)
        ),
        None,
    )
    if first is None:  # 理论不可达（stage_seq 非空保证），守卫给类型收窄
        return FlowDiagram()
    start = DiagramNode(
        id=base.next_node_id(), kind=KIND_START, name=AGGREGATE_START_LABEL
    )
    flows.insert(0, DiagramFlow(id=base.next_node_id(), source=start.id, target=first))

    # 注释：挂在保留节点上的才留（丢掉节点的注释跟着丢——注释说的是那个节点）
    #
    # ⚠️⚠️ 挂接关系在 ``note_links``（注释 id → 宿主节点 id）里，**不在**
    # ``DiagramNote.attached_to`` 上——那是 ``load()`` 从没填过的空字段（解析
    # 时只记了 ``note_links``）。按 ``attached_to`` 判断会一律判成"没挂"，
    # 于是被丢弃节点的注释全部留在图上（用户 2026-11-17 实测：起始节点选
    # 「图片拼版」后，「检测古籍文本框」「从文件提取图片」「用户上传PDF/DjVu
    # 文件」「古籍图片去底色」四条注释还挂在开始事件下面）。
    # 没在 ``note_links`` 里的（用户自己画的孤立注释）保持——它们不属于任何
    # 节点，丢掉就等于删了作者的话。
    kept_ids = {item.id for item in kept} | {start.id}
    note_links = {
        note.id: base.note_links[note.id]
        for note in base.notes
        if base.note_links.get(note.id, "") in kept_ids
    }
    notes = tuple(
        n for n in base.notes if n.id in note_links or n.id not in base.note_links
    )

    diagram = FlowDiagram(
        nodes=(start, *kept),
        flows=tuple(flows),
        notes=notes,
        note_links=note_links,
        process_id=base.process_id,
        node_seq=base.node_seq,
    )
    # 坐标全重排：被丢弃节点留下的空洞不能留在图上（waypoints 一并清掉，
    # 连线走线由 relayout 重算）
    diagram.relayout()
    return diagram


__all__ = [
    "AGGREGATE_START_LABEL",
    "AGGREGATE_START_STAGES",
    "aggregate_start_label",
    "any_member_stages",
    "derive_aggregate_diagram",
    "earliest_aggregate_stage",
    "missing_members",
    "preferred_start_stage",
]
