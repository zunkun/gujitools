# -*- coding: utf-8 -*-
"""BPMN 2.0 流程图的**忠实模型**：文件是唯一真源，页面照着它渲染与编辑。

## 为什么另起一个模型（与 :mod:`desktop.steps.flow` 的分工）

:mod:`~desktop.steps.flow` 的 ``FlowDefinition`` 是**运行语义**模型：它把流程
表达成「端口级边表」``(consumer, port) → supplier``——那是为了回答"这一步该去
谁那儿取产物"。它**不是**流程图，页面拿它渲染只能自己算坐标、自己猜图形。

本模块是**图形模型**：节点带 BPMN 元素类型（task / exclusiveGateway /
startEvent / …）、带文件里 DI 段的真实坐标，连线带折点。页面（
:class:`desktop.components.bpmn_view.BpmnView`）照着它画，**看到的就是文件里
画的**——用 bpmn.io 画的图，进页面长得一样。

## 为什么不做完整 BPMN 引擎

用户 2026-10-05 的口径：

> 后端驱动可以使用状态机来实现，bpm 流程引擎太复杂

所以这里**只做"读得懂、画得出、改得动"**：认识本工具用得到的元素类型，
不认识的原样保留（``kind`` 存原始标签名，绘图时按类型降级成矩形）。语义
（谁先谁后、跳过谁）由运行时的状态机负责，不在这里推导。

⚠️ 本模块**纯数据 + 纯 XML，不 import Qt**（与 ports/spec/flow 同一约束），
可以被子进程、CLI、自测安全导入。
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from desktop.steps import ports

# ---------------------------------------------------------------- 命名空间
BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
GUJI_NS = "https://guji.tools/bpmn/2025"

# ---------------------------------------------------------------- 元素类型
KIND_START = "startEvent"
KIND_END = "endEvent"
KIND_TASK = "task"
KIND_EXCLUSIVE = "exclusiveGateway"
KIND_PARALLEL = "parallelGateway"
KIND_INCLUSIVE = "inclusiveGateway"
KIND_INTERMEDIATE = "intermediateCatchEvent"

#: 网关家族（都画成菱形，只是中心符号不同）
GATEWAY_KINDS = frozenset({KIND_EXCLUSIVE, KIND_PARALLEL, KIND_INCLUSIVE})
#: 事件家族（都画成圆，结束/中断事件是双圈）
EVENT_KINDS = frozenset({KIND_START, KIND_END, KIND_INTERMEDIATE})

#: 本模块认识的元素类型（其余类型照旧保留 id/name，绘图时降级成矩形）。
KNOWN_KINDS = frozenset({KIND_TASK, *GATEWAY_KINDS, *EVENT_KINDS})

#: 各类元素的默认尺寸（BPMN 惯例值）——文件里没有 DI 段时按这个排。
DEFAULT_SIZE = {
    KIND_TASK: (100.0, 80.0),
    KIND_START: (36.0, 36.0),
    KIND_END: (36.0, 36.0),
    KIND_INTERMEDIATE: (36.0, 36.0),
    KIND_EXCLUSIVE: (50.0, 50.0),
    KIND_PARALLEL: (50.0, 50.0),
    KIND_INCLUSIVE: (50.0, 50.0),
}
FALLBACK_SIZE = (100.0, 80.0)

#: 自动排版时的横向/纵向间距（仅用于「文件没有 DI 段」的兜底）。
AUTO_GAP_X = 60.0
AUTO_GAP_Y = 150.0
AUTO_PADDING = 24.0

#: ``StageSlot.stack_index`` 的哨兵：**两个栈里没有这一页**。
#:
#: 用于"图上画了、但本程序还没有对应功能"的节点（见
#: :meth:`FlowDiagram.stage_slots`）。它们在步骤条上有格子、能点，但点下去
#: 不会切到任何面板——页面据此拦下并解释，而不是拿 ``-1`` 去
#: ``QStackedWidget.setCurrentIndex``（那会静默跳到最后一页，看起来像"点了
#: 跳到别的步骤"，比不跳更难解释）。
NO_PAGE = -1

#: 节点名 → 运行阶段。用于把「人画的中文名」接回程序里的阶段 key。
#:
#: ⚠️ 只在**没有** ``guji:stage`` 属性时才查这张表（属性是显式声明，优先）。
#: 用户用 bpmn.io 画图时不会写扩展属性，只能靠名字接——所以别名要写全
#: （"图片拼版"/"古籍拼板" 都指 ``imposition``，"生成 PDF"/"PDF排版" 都指
#: ``print``）。匹配时先去掉所有空白，避免"生成 PDF"与"生成PDF"不一致。
STAGE_ALIASES: dict[str, str] = {
    "提取图片": "extract",
    "提取pdf图片": "extract",
    "提取pdf": "extract",
    "检测文本框": "detect",
    "检测文本": "detect",
    "图片去底色": "rembg",
    "去底色": "rembg",
    "提交去底色结果": "rembg_submit",
    "生成pdf": "print",
    "输出pdf": "print",
    "pdf排版": "print",
    "排版": "print",
    "图片拼版": "imposition",
    "图片拼板": "imposition",
    "古籍拼板": "imposition",
    "古籍拼版": "imposition",
    "拼版": "imposition",
}


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _is_note_id(candidate: str, notes) -> bool:
    """这个 id 是不是某条注释（``association`` 两端要判哪头是注释）。"""
    return any(note.id == candidate for note in notes)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def stage_of_name(name: str, guji_stage: str | None = None) -> str | None:
    """节点名（或扩展属性）→ 运行阶段 key；认不出返回 ``None``。

    ⚠️ **认不出不报错**：用户可能在图上画了本工具没有的节点（备注、其他
    系统步骤）。那些节点该照常显示，只是不参与运行——报错会让整张图打不开。
    """
    if guji_stage and guji_stage in ports.STAGE_STEPS:
        return guji_stage
    compact = "".join((name or "").split()).lower()
    if not compact:
        return None
    if compact in STAGE_ALIASES:
        return STAGE_ALIASES[compact]
    # 再退一步：用阶段的中文名（走 ports 单一来源）比一遍
    for stage in ports.STAGE_STEPS:
        label = "".join(ports.stage_label(stage).split()).lower()
        if label == compact:
            return stage
    return None


def default_size(kind: str) -> tuple[float, float]:
    """某类元素的默认宽高（文件缺 DI 段时用）。"""
    return DEFAULT_SIZE.get(kind, FALLBACK_SIZE)


def fold_forward(stage: str, port: str) -> str:
    """把图上认出的阶段**升级到同一界面格里最靠后的、也产出该端口的动作**。

    ⚠️ 为什么必须有这一步：用户画流程图时，第三步只会画一个「图片去底色」
    节点；但他真正**提交**的产物由 ``rembg_submit``（提交去底色结果）产出
    ——两者在界面上**折成同一格**（折叠关系见 ``ports.STAGE_STEPS``）。
    若按图回退时直接取 ``rembg``，拿到的是**实时预览目录**
    （``stages/rembgpreview``），而用户提交过的成品在 ``stages/rembg``
    ——**打印出来会是"没提交的图"**（比报错更难发现）。

    同格里多个阶段都产出该端口时，取声明顺序里**最靠后**的那个（最下游的
    动作）；没有同格伙伴时原样返回。
    """
    step = ports.STAGE_STEPS.get(stage, stage)
    siblings = [s for s, owner in ports.STAGE_STEPS.items() if owner == step
                and port in ports.stage_outputs(s)]
    return siblings[-1] if siblings else stage


# ---------------------------------------------------------------- 图元素
@dataclass(frozen=True)
class DiagramNode:
    """流程图上的一个**节点**（图形意义上的，不是运行阶段）。

    ``kind`` 是 BPMN 元素类型（:data:`KIND_TASK` 等）；``stage`` 是它对应的
    运行阶段 key（接不上就是 ``None``，照样画）。
    """

    id: str
    kind: str
    name: str = ""
    stage: str | None = None

    @property
    def is_gateway(self) -> bool:
        return self.kind in GATEWAY_KINDS

    @property
    def is_event(self) -> bool:
        return self.kind in EVENT_KINDS


@dataclass(frozen=True)
class DiagramFlow:
    """一条**连线**（BPMN ``sequenceFlow``）。

    ``label`` 是边上写的字（如网关分支的「否」）。它**只是显示文案**——
    运行语义由状态机管，这里不解释它。
    """

    id: str
    source: str
    target: str
    label: str = ""


@dataclass(frozen=True)
class DiagramNote:
    """节点旁边的一条**文字注释**（BPMN ``textAnnotation`` + ``association``）。

    用户在 bpmn.io 里给节点挂的说明（例如「图片拼板」→「古籍图片拼板」）。
    它**不参与运行**，但必须**显示出来**——那是作者写在图上的话，丢了等于
    把图的信息删了一半。

    :attr:`attached_to` 是它挂在哪张节点上（``association`` 的 ``sourceRef``）；
    空串表示没挂（图上孤立的一条注释）。
    """

    id: str
    text: str = ""
    attached_to: str = ""


@dataclass
class FlowDiagram:
    """一张完整的流程图：节点 + 连线 + 坐标（= bpmn 文件的全部内容）。

    ``boxes`` / ``waypoints`` 直接来自文件的 **DI 段**（``dc:Bounds`` /
    ``di:waypoint``）——这正是 bpmn.io 等编辑器存布局的地方，所以"页面上看到
    的"与"文件里存下的"是同一份坐标。文件没有 DI 段时按 :meth:`auto_layout`
    兜底排一份。
    """

    nodes: tuple[DiagramNode, ...] = ()
    flows: tuple[DiagramFlow, ...] = ()
    #: 节点旁的**文字注释**（``textAnnotation`` + ``association``，见
    #: :class:`DiagramNote`）。只显示、不参与运行，但要往返保真。
    notes: tuple[DiagramNote, ...] = ()
    #: 注释的挂接关系：注释 id → 它挂在哪个节点上（``association`` 的 sourceRef）
    note_links: dict[str, str] = field(default_factory=dict)
    boxes: dict[str, tuple[float, float, float, float]] = field(
        default_factory=dict
    )
    waypoints: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    #: 流程 id（文件里的 ``bpmn:process/@id``，往返时原样写回）
    process_id: str = "guji_task"

    # ------------------------------------------------------------ 查询
    def node(self, node_id: str) -> DiagramNode | None:
        for item in self.nodes:
            if item.id == node_id:
                return item
        return None

    def flows_of(self, node_id: str) -> list[DiagramFlow]:
        """以该节点为**起点**的连线（画箭头/找下一步用）。"""
        return [f for f in self.flows if f.source == node_id]

    def node_box(self, node_id: str) -> tuple[float, float, float, float]:
        """节点矩形；没有坐标就按类型给个默认尺寸摆 (0,0)。"""
        if node_id in self.boxes:
            return self.boxes[node_id]
        item = self.node(node_id)
        w, h = default_size(item.kind if item else KIND_TASK)
        return (0.0, 0.0, w, h)

    def note_box(self, note_id: str) -> tuple[float, float, float, float]:
        """注释框（和 :meth:`node_box` 同一套坐标；没有就按默认尺寸摆 0,0）。"""
        return self.boxes.get(note_id, (0.0, 0.0, 150.0, 50.0))

    def notes_of(self, node_id: str) -> list[DiagramNote]:
        """挂在某个节点上的注释（显示用；顺序即文件声明顺序）。"""
        return [n for n in self.notes if self.note_links.get(n.id) == node_id]

    def content_size(self) -> tuple[float, float]:
        """内容包围盒（宽, 高），含留白。空图返回留白尺寸。

        ⚠️ 注释框**也要算进来**：注释常挂在节点外侧（本例里都在节点下方
        一行的位置），只按节点算包围盒会把它们裁在画布外——现象是"注释
        看不见"，而模型里明明有。
        """
        ids = [n.id for n in self.nodes] + [n.id for n in self.notes]
        keys = [i for i in ids if i in self.boxes]
        if not keys:
            return AUTO_PADDING * 2, AUTO_PADDING * 2
        left = min(self.boxes[k][0] for k in keys)
        top = min(self.boxes[k][1] for k in keys)
        right = max(self.boxes[k][0] + self.boxes[k][2] for k in keys)
        bottom = max(self.boxes[k][1] + self.boxes[k][3] for k in keys)
        return (right - left + AUTO_PADDING * 2,
                bottom - top + AUTO_PADDING * 2)

    def stage_order(self) -> tuple[str, ...]:
        """可运行的阶段，按**图上的拓扑顺序**排（状态机的输入）。

        ⚠️ **必须是拓扑序而不是遍历序**：图上从网关分叉出「否 → PDF排版」与
        「→ 古籍拼板 → PDF排版」两条路，广度遍历会先撞到短路的「PDF排版」，
        把 ``print`` 排到 ``imposition`` 前面——那样状态机会拿"还没拼版的
        图"去打印（实测踩过）。拓扑排序保证**所有前驱都排完才轮到它**，
        所以 ``imposition`` 稳稳排在 ``print`` 前面。

        认不出阶段的节点（``stage is None``，即网关/事件）跳过但不影响
        拓扑计算——它们是图上的控制元素，本身不占一格。

        实现用 Kahn 算法，**同层按文件声明顺序**出队（结果稳定、可预期）。
        有环（BPMN 允许回环）时剩下的按声明顺序兜底，不丢阶段。
        """
        if not self.nodes:
            return ()
        order_index = {item.id: index for index, item in enumerate(self.nodes)}
        indegree: dict[str, int] = {item.id: 0 for item in self.nodes}
        for flow in self.flows:
            if flow.target in indegree and flow.source in indegree:
                indegree[flow.target] += 1

        def sort_key(node_id: str) -> int:
            return order_index.get(node_id, len(order_index))

        ready = sorted(
            (nid for nid, deg in indegree.items() if deg == 0), key=sort_key
        )
        seen: list[str] = []
        stages: list[str] = []
        while ready:
            node_id = ready.pop(0)
            seen.append(node_id)
            item = self.node(node_id)
            if item is not None and item.stage and item.stage not in stages:
                stages.append(item.stage)
            newly: list[str] = []
            for flow in self.flows_of(node_id):
                if flow.target not in indegree:
                    continue
                indegree[flow.target] -= 1
                if indegree[flow.target] == 0:
                    newly.append(flow.target)
            # 新就绪的插回队首但**按文件顺序排**，保证确定性
            ready = sorted(ready + newly, key=sort_key)

        # 兜底：有环导致没排完的，按文件声明顺序接在后面（不丢阶段）
        for item in self.nodes:
            if item.stage and item.stage not in stages:
                stages.append(item.stage)
        return tuple(stages)

    def incoming(self, node_id: str) -> list[DiagramFlow]:
        """以该节点为**终点**的连线。"""
        return [f for f in self.flows if f.target == node_id]

    def upstream_stages(self, stage: str) -> tuple[str, ...]:
        """沿图往前找，哪些阶段是 ``stage`` 的**上游**（传递闭包）。

        用途：**"上游重跑过 ⇒ 本步产物可能过期"** 的判定链。它必须**按图算**，
        不能写死一张表——用户改了流程（加一步、去掉一步、换分支）之后，
        写死的链会把不相干的步骤算成上游（提示"上游已重新执行"却指错人），
        或者漏掉真正影响它的那一步。

        走法：从该阶段的节点出发反向遍历；遇到**网关/事件**（不带 stage 的）
        继续往前穿（它们是控制元素，不产出产物）；遇到产出阶段就收下并
        **继续往前**（传递性）。

        ⚠️⚠️ **要按"界面格"摊开，而不是只认图上出现的阶段**：
        ``rembg_submit``（提交去底色结果）是第三步内的第二个动作，用户画图时
        不会给它单独开节点——但它**确实**是「生成 PDF」的输入（``print.pages
        ← rembg_submit``）。只按图上的阶段算，链里就少了它，于是"提交过之后
        PDF 已过期"这句提示永远不出现。所以收下阶段后要按
        ``ports.STAGE_STEPS`` 反查它那一格里的**所有**阶段。

        结果按 :meth:`stage_order` 排（顺序稳定、可断言），图上没有节点的阶段
        追加在后面。该阶段不在图里时返回 ``()``。
        """
        starts = [n.id for n in self.nodes if n.stage == stage]
        if not starts:
            return ()
        seen: set[str] = set(starts)
        found: list[str] = []
        queue: list[str] = list(starts)
        while queue:
            node_id = queue.pop(0)
            for flow in self.incoming(node_id):
                source = flow.source
                if source in seen:
                    continue
                seen.add(source)
                item = self.node(source)
                if item is None or not item.stage:
                    queue.append(source)      # 网关/事件：继续往前穿
                    continue
                if item.stage != stage and item.stage not in found:
                    found.append(item.stage)
                queue.append(source)          # 产出阶段：也继续往前（传递）

        # 把"上游阶段"摊开成"上游**格**里的所有阶段"（rembg → rembg_submit 也在内）
        steps = {ports.STAGE_STEPS.get(s, s) for s in found}
        expanded = [
            s for s in ports.STAGE_STEPS
            if ports.STAGE_STEPS.get(s, s) in steps
        ]
        order = self.stage_order()
        return tuple(
            [s for s in order if s in expanded]
            + [s for s in expanded if s not in order]
        )

    def nearest_producer(self, stage: str, port: str,
                         active) -> str | None:
        """沿图**往前**找最近的、产出 ``port`` 的**在流程里**的阶段。

        ⚠️ 为什么需要它：运行时要回答"这一步的 ``pages`` 去哪个目录取"，
        而旧答案来自代码里的端口级边表（``ports.SUPPLIERS``）。一旦用户把
        流程改成**不含某一步**（例如去掉「图片去底色」），边表给的供给方就
        不在流程里了——按它取路径会指向**永远不会产生的文件**（故障现象是
        "生成 PDF 报找不到输入"，而不是流程报错，极难查）。

        规则：从 ``stage`` 反向广度遍历（跳过网关与事件——它们不产出产物），
        返回**第一个**既在 ``active`` 里、又产出 ``port`` 的阶段。
        找不到返回 ``None``（调用方按"没有这个输入"处理）。

        ``active`` = 本流程实际要跑的阶段集合（由 :class:`Scheduler` 给，
        已排除条件不满足的步骤，如未启用拼版时的 ``imposition``）。
        """
        candidates = set(active)
        if stage not in candidates:
            return None
        # ⚠️ 入参是**阶段 key**，而图上的节点 id 是 `Activity_xxx` 这种
        #    （bpmn.io 生成）——**必须先从阶段 key 找到节点 id 再遍历**，
        #    直接拿 key 当 id 去查入边会一条都查不到（返回 None，表现为
        #    "生成 PDF 找不到输入"）。
        starts = [n.id for n in self.nodes if n.stage == stage]
        if not starts:
            return None
        queue = list(starts)
        seen = set(starts)
        while queue:
            node_id = queue.pop(0)
            for flow in self.incoming(node_id):
                source = flow.source
                if source in seen:
                    continue
                seen.add(source)
                item = self.node(source)
                if item is None or not item.stage:
                    # 网关/事件：不产出产物，继续往前穿
                    queue.append(source)
                    continue
                if item.stage in candidates and port in ports.stage_outputs(
                        item.stage):
                    # ⚠️ 折叠到**同格里最靠后的动作**：图上是「图片去底色」，
                    #    真正产出 pages 的是同格的「提交去底色结果」。
                    return fold_forward(item.stage, port)
                queue.append(source)
        return None

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

        1. ``rembg_submit`` 折叠进 ``rembg`` 那一格（它是第三步的第二个动作）；
        2. 同一格重复出现保留**首次**位置；
        3. ``bar_index`` 只数**本图里有**的格子（步骤条上就这么多格）；
        4. **图上画了、但本程序还没有对应功能的 task 节点**（例如随手加的
           「OCR 识别」）也**占一格**，排在真实步骤之后，标 ``mapped=False``
           且 ``stack_index = NO_PAGE``——界面据此画灰节点并在点它时解释
           （改成已有步骤名即可接上）。这类节点不会进 ``stage_order()``
           （那里只收认得出阶段的），所以是单独扫节点表挑出来的。

        ⚠️⚠️ **``stack_index`` 不是"数出来的"，而是"查出来的"**——这是最容易
        写错的一处（2026-10-05 实测踩中）：

        两个栈（``control_stack`` / ``preview_stack``）是**按静态步骤表**一次
        建好的固定页数（``FLOW_STAGES`` 各一页 + ``OPTIONAL_STEPS`` 追加在末尾），
        **与流程图文件无关**。所以页号必须查"这一步在静态表里的位置"：

        - 文件里**少了**某一步（例如默认流程改成不含「图片去底色」）时，若还
          按"数当前有几格"来编号，后面每一步的页号都会**整体前移**——
          点「生成 PDF」会翻到「图片去底色」那一页（用户报的"改了文件程序
          没跟着变"就是这个）。
        - 文件里**多了/调换了顺序**也一样：页号只认静态位置，步骤条上哪一格
          对应哪一页由 :meth:`slot_of` / ``_select_stage`` 查出来。
        """
        from desktop.steps.flow import StageSlot
        from desktop.steps.spec import FLOW_STAGES, OPTIONAL_STEPS

        # 栈页号 = 静态面板顺序里的位置（两个栈就是这么建的）
        page_of: dict[str, int] = {
            step: index
            for index, step in enumerate(tuple(FLOW_STAGES) + tuple(OPTIONAL_STEPS))
        }

        slots: list[StageSlot] = []
        seen: set[str] = set()
        for stage in self.stage_order():
            spec = ports.spec_for_stage(stage)
            if spec is None:
                continue
            step = ports.STAGE_STEPS.get(stage, stage)
            if step in seen:
                continue
            seen.add(step)
            slots.append(
                StageSlot(step=step, stage=stage, optional=spec.role == "optional")
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
            if label in seen:
                continue
            seen.add(label)
            slots.append(StageSlot(
                step=label, stage="", optional=False, mapped=False,
                name=label, stack_index=NO_PAGE,
            ))
        return tuple(
            StageSlot(
                step=slot.step,
                stage=slot.stage,
                optional=slot.optional,
                bar_index=bar_index,
                # 已接入的查静态表拿页号；未接入的两个栈里没有它的页
                stack_index=(page_of.get(slot.step, bar_index) if slot.mapped
                             else NO_PAGE),
                mapped=slot.mapped,
                name=slot.name,
            )
            for bar_index, slot in enumerate(slots)
        )

    def optional_after(self, step: str | None = None) -> int | None:
        """可选节点插在**真实步骤数组的第几位之后**（喂 ``StepBar``）。

        语义抄自 ``FlowDefinition.optional_after``（那里有详细推演，别重推）：
        ``after`` 指的是**最后一个左邻居的下标**，不是左邻居的个数。
        """
        slots = self.stage_slots()
        optional = [s for s in slots if s.optional]
        if not optional:
            return None
        target = None
        if step is not None:
            target = next((s for s in optional if s.step == step), None)
        node = target or optional[0]
        after: int | None = None
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

    # ------------------------------------------------------------ 排布
    @classmethod
    def auto_layout(cls, diagram: "FlowDiagram") -> "FlowDiagram":
        """给"没有 DI 段"的图排一份坐标（就地改 ``boxes``）。

        简单横向铺开 + 分支下移：够用即可，用户拖一下就会覆盖它。
        """
        if diagram.boxes:
            return diagram
        from collections import Counter

        depth: dict[str, int] = {}
        queue: list[tuple[str, int]] = [
            (n.id, 0) for n in diagram.nodes if n.kind == KIND_START
        ] or [(diagram.nodes[0].id, 0)] if diagram.nodes else []
        while queue:
            node_id, level = queue.pop(0)
            if node_id in depth:
                continue
            depth[node_id] = level
            for flow in diagram.flows_of(node_id):
                if flow.target not in depth:
                    queue.append((flow.target, level + 1))
        for item in diagram.nodes:
            depth.setdefault(item.id, 0)

        per_depth: Counter[int] = Counter()
        x = AUTO_PADDING
        for level in sorted(set(depth.values())):
            for item in diagram.nodes:
                if depth[item.id] != level:
                    continue
                w, h = default_size(item.kind)
                y = AUTO_PADDING + per_depth[level] * AUTO_GAP_Y
                diagram.boxes[item.id] = (x, y, w, h)
                per_depth[level] += 1
            x += DEFAULT_SIZE.get(KIND_TASK, FALLBACK_SIZE)[0] + AUTO_GAP_X
        return diagram

    # ------------------------------------------------------------ 解析
    @classmethod
    def load(cls, path: Path | str) -> "FlowDiagram":
        """从 ``.bpmn`` 文件读回整张图（节点/连线/坐标）。

        ⚠️ 与 :meth:`desktop.steps.flow.FlowDefinition.load` 的区别：那个只读
        **能跑的阶段**、认不出就抛错；这个读**图上画的一切**、认不出也保留。
        页面渲染用这个，运行语义用那个（或状态机）。
        """
        path = Path(path)
        if not path.is_file():
            raise ValueError(f"流程图文件不存在：{path}")
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            raise ValueError(f"流程图不是合法 XML：{path}（{exc}）") from exc

        process = next((el for el in root if _local(el.tag) == "process"), None)
        if process is None:
            raise ValueError(f"流程图里没有 <process>：{path}")

        nodes: list[DiagramNode] = []
        flows: list[DiagramFlow] = []
        notes: list[DiagramNote] = []
        note_links: dict[str, str] = {}
        raw_links: list[tuple[str, str]] = []
        for element in process:
            kind = _local(element.tag)
            if kind in KNOWN_KINDS:
                name = element.get("name", "") or ""
                # ⚠️ **只有 ``task`` 才映射运行阶段**：事件（尤其结束事件）常
                #    叫「生成PDF」这类名字，按名字查表会把它误认成 ``print``
                #    阶段——那会让状态机多跑一遍、顺序也全乱（实测踩过）。
                #    网关、事件都是**图形/控制**元素，不产生运行阶段。
                stage = None
                if kind == KIND_TASK:
                    stage = stage_of_name(name, element.get(_q(GUJI_NS, "stage")))
                nodes.append(DiagramNode(
                    id=element.get("id", ""), kind=kind, name=name, stage=stage,
                ))
            elif kind == "sequenceFlow":
                flows.append(DiagramFlow(
                    id=element.get("id", ""),
                    source=element.get("sourceRef", ""),
                    target=element.get("targetRef", ""),
                    label=element.get("name", "") or "",
                ))
            elif kind == "textAnnotation":
                # ⚠️ 注释正文在**子元素** ``<bpmn:text>`` 里，不在属性上。
                body = element.find(_q(BPMN_NS, "text"))
                text = (body.text or "") if body is not None else ""
                notes.append(DiagramNote(
                    id=element.get("id", ""), text=text.strip(),
                ))
            elif kind == "association":
                raw_links.append(
                    (element.get("sourceRef", ""), element.get("targetRef", ""))
                )

        # ⚠️ 挂接关系**延后**解析：``association`` 可能写在 ``textAnnotation``
        #    前面（XML 元素顺序没保证），当场判"哪头是注释"会漏掉一半。
        #    方向：sourceRef=被说明的节点，targetRef=注释（bpmn.io 的写法）；
        #    反过来写也认（别的工具可能反过来）。
        for source, target in raw_links:
            if not source or not target:
                continue
            if _is_note_id(target, notes):
                note_links[target] = source
            elif _is_note_id(source, notes):
                note_links[source] = target

        diagram = cls(
            nodes=tuple(nodes), flows=tuple(flows), notes=tuple(notes),
            note_links=note_links,
            process_id=process.get("id", "guji_task"),
        )
        _read_di(root, diagram)
        has_node_box = any(n.id in diagram.boxes for n in diagram.nodes)
        return diagram if has_node_box else cls.auto_layout(diagram)

    # ------------------------------------------------------------ 序列化
    def to_xml(self) -> bytes:
        """写回 BPMN 2.0（含 DI 段），保证 bpmn.io 等工具能原样打开。

        ⚠️ 连线必须**双向引用**：``sourceRef``/``targetRef`` 属性给解析用，
        节点里的 ``<bpmn:incoming>``/``<bpmn:outgoing>`` 子元素给渲染器用
        —— 缺了后者，标准渲染器画不出箭头。
        """
        ET.register_namespace("bpmn", BPMN_NS)
        ET.register_namespace("bpmndi", BPMNDI_NS)
        ET.register_namespace("dc", DC_NS)
        ET.register_namespace("di", DI_NS)
        ET.register_namespace("guji", GUJI_NS)

        definitions = ET.Element(_q(BPMN_NS, "definitions"), {
            "id": "guji-definitions",
            "targetNamespace": GUJI_NS,
            "exporter": "guji",
            "exporterVersion": "2.0",
        })
        process = ET.SubElement(
            definitions, _q(BPMN_NS, "process"),
            {"id": self.process_id, "isExecutable": "false"},
        )
        for item in self.nodes:
            element = ET.SubElement(process, _q(BPMN_NS, item.kind), {
                "id": item.id, "name": item.name,
            })
            for flow in self.flows:
                if flow.target == item.id:
                    ET.SubElement(element, _q(BPMN_NS, "incoming")).text = flow.id
            for flow in self.flows:
                if flow.source == item.id:
                    ET.SubElement(element, _q(BPMN_NS, "outgoing")).text = flow.id
        for flow in self.flows:
            attrs = {
                "id": flow.id, "sourceRef": flow.source, "targetRef": flow.target,
            }
            if flow.label:
                attrs["name"] = flow.label
            ET.SubElement(process, _q(BPMN_NS, "sequenceFlow"), attrs)

        # ---- 文字注释 + 挂接（写回，别把用户写在图上的话丢了）----
        for note in self.notes:
            element = ET.SubElement(
                process, _q(BPMN_NS, "textAnnotation"), {"id": note.id})
            ET.SubElement(element, _q(BPMN_NS, "text")).text = note.text
        for note in self.notes:
            host = self.note_links.get(note.id)
            if not host:
                continue
            ET.SubElement(process, _q(BPMN_NS, "association"), {
                "id": f"Association_{note.id}",
                "associationDirection": "None",
                "sourceRef": host, "targetRef": note.id,
            })

        plane = ET.SubElement(
            ET.SubElement(definitions, _q(BPMNDI_NS, "BPMNDiagram"),
                          {"id": "guji-diagram"}),
            _q(BPMNDI_NS, "BPMNPlane"),
            {"id": "guji-plane", "bpmnElement": self.process_id},
        )
        for item in self.nodes:
            x, y, w, h = self.node_box(item.id)
            shape = ET.SubElement(plane, _q(BPMNDI_NS, "BPMNShape"), {
                "id": f"{item.id}_di", "bpmnElement": item.id,
            })
            if item.is_gateway:
                shape.set("isMarkerVisible", "true")
            ET.SubElement(shape, _q(DC_NS, "Bounds"), {
                "x": f"{x:.0f}", "y": f"{y:.0f}",
                "width": f"{w:.0f}", "height": f"{h:.0f}",
            })
        for note in self.notes:
            x, y, w, h = self.note_box(note.id)
            shape = ET.SubElement(plane, _q(BPMNDI_NS, "BPMNShape"), {
                "id": f"{note.id}_di", "bpmnElement": note.id,
            })
            ET.SubElement(shape, _q(DC_NS, "Bounds"), {
                "x": f"{x:.0f}", "y": f"{y:.0f}",
                "width": f"{w:.0f}", "height": f"{h:.0f}",
            })
        for flow in self.flows:
            points = self.waypoints.get(flow.id) or self.route(flow)
            edge = ET.SubElement(plane, _q(BPMNDI_NS, "BPMNEdge"), {
                "id": f"{flow.id}_di", "bpmnElement": flow.id,
            })
            for px, py in points:
                ET.SubElement(edge, _q(DI_NS, "waypoint"), {
                    "x": f"{px:.0f}", "y": f"{py:.0f}",
                })
        return ET.tostring(definitions, encoding="utf-8", xml_declaration=True)

    def route(self, flow: DiagramFlow) -> list[tuple[float, float]]:
        """连线的折点（文件没存 ``di:waypoint`` 时按直角走线算一份）。"""
        sx, sy, sw, sh = self.node_box(flow.source)
        tx, ty, tw, th = self.node_box(flow.target)
        start = (sx + sw, sy + sh / 2)
        end = (tx, ty + th / 2)
        if abs(start[1] - end[1]) < 1.0:
            return [start, end]
        if end[0] >= start[0]:
            mid = (start[0] + end[0]) / 2
            return [start, (mid, start[1]), (mid, end[1]), end]
        # 目标在左侧：从下方绕回去
        row = max(sy + sh, ty + th) + 40
        return [start, (start[0], row), (end[0], row), end]

    def save(self, path: Path | str) -> Path:
        """原子落盘（写 ``.part`` 再 ``os.replace``，防半截文件）。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, part = tempfile.mkstemp(
            dir=str(path.parent), prefix=path.name + ".", suffix=".part"
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(self.to_xml())
            os.replace(part, path)
        except BaseException:
            try:
                os.unlink(part)
            except OSError:
                pass
            raise
        return path


def _read_di(root: ET.Element, diagram: FlowDiagram) -> None:
    """把 DI 段的坐标读进 ``diagram.boxes`` / ``waypoints``（就地改）。"""
    for shape in root.iter(_q(BPMNDI_NS, "BPMNShape")):
        node_id = shape.get("bpmnElement", "")
        bounds = shape.find(_q(DC_NS, "Bounds"))
        if not node_id or bounds is None:
            continue
        try:
            diagram.boxes[node_id] = (
                float(bounds.get("x", 0)), float(bounds.get("y", 0)),
                float(bounds.get("width", 0)), float(bounds.get("height", 0)),
            )
        except (TypeError, ValueError):
            continue
    for edge in root.iter(_q(BPMNDI_NS, "BPMNEdge")):
        flow_id = edge.get("bpmnElement", "")
        points: list[tuple[float, float]] = []
        for point in edge.findall(_q(DI_NS, "waypoint")):
            try:
                points.append((float(point.get("x", 0)), float(point.get("y", 0))))
            except (TypeError, ValueError):
                continue
        if flow_id and len(points) >= 2:
            diagram.waypoints[flow_id] = points


__all__ = [
    "AUTO_GAP_X", "AUTO_GAP_Y", "AUTO_PADDING",
    "BPMNDI_NS", "BPMN_NS", "DC_NS", "DI_NS", "GUJI_NS",
    "DEFAULT_SIZE", "DiagramFlow", "DiagramNode", "DiagramNote", "EVENT_KINDS",
    "FlowDiagram", "GATEWAY_KINDS", "KIND_END", "KIND_EXCLUSIVE",
    "KIND_INCLUSIVE", "KIND_INTERMEDIATE", "KIND_PARALLEL", "KIND_START",
    "KIND_TASK", "KNOWN_KINDS", "NO_PAGE", "STAGE_ALIASES", "default_size",
    "fold_forward", "stage_of_name",
]
