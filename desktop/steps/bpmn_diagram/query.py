# -*- coding: utf-8 -*-
"""图的查询投影：节点/连线/注释查找、拓扑序、上游与产出方 BFS。"""

from __future__ import annotations

import re

from desktop.steps import ports
from desktop.steps.bpmn_diagram.constants import AUTO_PADDING, KIND_TASK
from desktop.steps.bpmn_diagram.elements import DiagramFlow, DiagramNode, DiagramNote
from desktop.steps.bpmn_diagram.helpers import default_size
from desktop.steps.ports import fold_forward


class _QueryMixin:
    """``FlowDiagram`` 的查询/拓扑/供给关系部分（纯数据投影）。"""

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
        return (right - left + AUTO_PADDING * 2, bottom - top + AUTO_PADDING * 2)

    def stage_order(self) -> tuple[str, ...]:
        """可运行的阶段，按**图上的拓扑顺序**排（旧模型：状态机按 stage 寻址）。

        ⚠️ **同阶段的多个节点折叠成一个阶段**——这是 :meth:`node_order` 去掉
        阶段维度后的投影。B 方案（2026-10-17）后运行时按 ``node_id`` 寻址
        （:meth:`node_order`），本方法保留给仍按 stage 说话的旧调用方。

        ⚠️ **必须是拓扑序而不是遍历序**：图上从网关分叉出「否 → PDF排版」与
        「→ 古籍拼版 → PDF排版」两条路，广度遍历会先撞到短路的「PDF排版」，
        把 ``print`` 排到 ``imposition`` 前面——那样状态机会拿"还没拼版的
        图"去打印（实测踩过）。拓扑排序保证**所有前驱都排完才轮到它**，
        所以 ``imposition`` 稳稳排在 ``print`` 前面。

        认不出阶段的节点（``stage is None``，即网关/事件）跳过但不影响
        拓扑计算——它们是图上的控制元素，本身不占一格。

        实现用 Kahn 算法，**同层按文件声明顺序**出队（结果稳定、可预期）。
        有环（BPMN 允许回环）时剩下的按声明顺序兜底，不丢阶段。
        """
        return tuple(dict.fromkeys(stage for _, stage in self.node_order()))

    def _topo_node_ids(self) -> list[str]:
        """**全部**节点 id 的拓扑序（Kahn，同层按文件声明顺序；有环时剩下的
        按声明顺序接在后面，不丢节点）。

        :meth:`node_order` 与 :meth:`stage_order` 共用这一趟排序，只是投影维度
        不同（一个保留节点、一个折叠阶段）。
        """
        if not self.nodes:
            return []
        order_index = {item.id: index for index, item in enumerate(self.nodes)}
        indegree: dict[str, int] = {item.id: 0 for item in self.nodes}
        for flow in self.flows:
            if flow.target in indegree and flow.source in indegree:
                indegree[flow.target] += 1

        def sort_key(node_id: str) -> int:
            return order_index.get(node_id, len(order_index))

        ready = sorted((nid for nid, deg in indegree.items() if deg == 0), key=sort_key)
        seen: list[str] = []
        while ready:
            node_id = ready.pop(0)
            seen.append(node_id)
            newly: list[str] = []
            for flow in self.flows_of(node_id):
                if flow.target not in indegree:
                    continue
                indegree[flow.target] -= 1
                if indegree[flow.target] == 0:
                    newly.append(flow.target)
            # 新就绪的插回队首但**按文件顺序排**，保证确定性
            ready = sorted(ready + newly, key=sort_key)

        # 兜底：有环导致没排完的，按文件声明顺序接在后面（不丢节点）
        for item in self.nodes:
            if item.id not in seen:
                seen.append(item.id)
        return seen

    def node_order(self) -> tuple[tuple[str, str], ...]:
        """图上**可运行节点**按拓扑序排：``(node_id, stage)``，**不折叠同阶段**。

        B 方案（2026-10-17）的运行时真源：任务流程按**节点实例** ``node_id``
        寻址——同类型步骤（图片拼版 / 检测文本框 / 图片去底色 / PDF排版）可以
        放多个节点，它们彼此独立（各自参数、各自产物落点）。

        与 :meth:`stage_order` 是同一趟拓扑排序的两份投影：那个把同阶段的多个
        节点**折叠成一个阶段**（旧调用方按 stage 寻址，保持兼容），本方法
        **保留每个节点实例**。认不出阶段的节点（网关/事件/未知 task 不接功能）
        不进结果——它们不占运行位。
        """
        result: list[tuple[str, str]] = []
        for node_id in self._topo_node_ids():
            item = self.node(node_id)
            if item is not None and item.stage:
                result.append((node_id, item.stage))
        return tuple(result)

    def primary_of(self, stage: str) -> str | None:
        """该阶段在本图里的**主节点** id（没有该阶段返回 ``None``）。

        「主节点」是 B 方案里"沿用旧路径"的那个节点：同阶段**恰好一个节点**
        时它就是主节点，产物仍落在 ``stages/<阶段>``（现存任务与默认流程**零
        迁移**）；同阶段**多个节点**时其余节点是副本，产物落在
        ``stages/<阶段>~<node_id>``。

        ⚠️ 取法是该阶段在**文件声明顺序**里第一个节点，**不是**拓扑序第一个
        ——声明顺序比拓扑序稳定（拖拽、改连线都不改声明顺序，只有增删节点才
        变），所以"谁是主节点"不会因为用户改了连线而漂移。
        """
        for item in self.nodes:
            if item.stage == stage:
                return item.id
        return None

    def node_ids_of(self, stage: str) -> tuple[str, ...]:
        """该阶段在本图里的**全部节点** id（文件声明顺序；没有则空元组）。

        ``node_ids_of(stage)[0]`` 恒等于 :meth:`primary_of`（同一取法），其余
        是副本。界面按它给每个节点实例各建一页。
        """
        return tuple(item.id for item in self.nodes if item.stage == stage)

    def next_node_id(self) -> str:
        """分配一个**全新且永不复用**的节点 id（``Node_<n>``），并抬水位。

        水位 = ``max(自身记录的 node_seq, 现有 ``Node_<n>`` id 里的最大 n) + 1``
        （见 :attr:`node_seq`）。调用方（编辑器 ``_add_node``）必须走这里，
        **别再用"当前节点数 + 1"**——那会在删节点后复用旧 id。
        """
        seq = self.node_seq
        for item in self.nodes:
            match = re.match(r"Node_(\d+)$", item.id)
            if match:
                seq = max(seq, int(match.group(1)))
        seq += 1
        self.node_seq = seq
        return f"Node_{seq}"

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
        ``detect_submit``（提交检测结果）是第二步内的第二个动作，用户画图时
        不会给它单独开节点——但它**确实**是下游的输入（``rembg.pages
        ← detect_submit``）。只按图上的阶段算，链里就少了它，于是"提交过之后
        去底色已过期"这句提示永远不出现。所以收下阶段后要按
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
                    queue.append(source)  # 网关/事件：继续往前穿
                    continue
                if item.stage != stage and item.stage not in found:
                    found.append(item.stage)
                queue.append(source)  # 产出阶段：也继续往前（传递）

        # 把"上游阶段"摊开成"上游**格**里的所有阶段"（detect → detect_submit 也在内）
        steps = {ports.STAGE_STEPS.get(s, s) for s in found}
        expanded = [
            s for s in ports.STAGE_STEPS if ports.STAGE_STEPS.get(s, s) in steps
        ]
        order = self.stage_order()
        return tuple(
            [s for s in order if s in expanded]
            + [s for s in expanded if s not in order]
        )

    def nearest_producer(self, stage: str, port: str, active) -> str | None:
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
        # 节点版 BFS 由 :meth:`nearest_producer_node` 提供；这里对同阶段的
        # **每个**节点实例各问一次（单节点流程结果与改造前逐值一致）。
        for node_id in self.node_ids_of(stage):
            hit = self.nearest_producer_node(node_id, port, active)
            if hit is not None:
                # ⚠️ 折叠到**同格里最靠后的动作**：图上是「图片去底色」，
                #    真正产出 pages 的是同格的「提交去底色结果」。
                item = self.node(hit)
                return fold_forward(item.stage, port) if item and item.stage else None
        return None

    def producers_of(self, stage: str, port: str, active) -> tuple[str, ...]:
        """沿图往前能到达的、产出 ``port`` 的**全部**在流程阶段（已折叠）。

        与 :meth:`nearest_producer` 的区别是**返回全部**而不是"广度序第一个"
        ——用来判断"**图能不能给出唯一答案**"。

        ⚠️ 为什么需要这个判据（2026-10-06，用户"这个问题再次提出"）：
        ``store.stage_supplier`` 原先的规则是**"先静态声明、后沿图回退"**，
        于是 ``ports.SUPPLIERS``（一份**写死在代码里的默认流程连线**）在
        静态供给方还留在流程里时**压过用户的连线**。实测：两条节点集合相同、
        连线不同的流程（`extract→detect→rembg→print` 与用户自己连的
        `extract→print`），``print`` 的取图目录**完全一样**——用户明确画的
        连线被静默丢弃。这就是"自定义流程里总是冒出默认流程逻辑"的病根：
        **BPM 化只覆盖了"顺序"，没覆盖"语义"**。

        ⚠️ 但**不能无条件改成"图说了算"**：默认流程带一个网关（是否拼版），
        沿图回溯 ``print`` 会同时找到「图片拼版」与「图片去底色」两个产出方
        ——**图说不清**。那种情况必须退回静态声明 + 条件开关（那正是
        ``ports.print_pages_supplier`` 建模的东西）。所以调用方的判据是
        "**恰好一个**产出方 ⇒ 图说了算；0 个或多个 ⇒ 退回静态表"。

        产出方按 :func:`fold_forward` 折叠到同格最靠后的动作（去重后返回）。

        ⚠️ **遇到产出方就停，不再往它上游走**（"谁喂我"的语义）：一条线性链
        ``extract→detect→rembg→print`` 里，``print`` 的产出方是 ``rembg``，
        **不是** ``extract``——后者只是 rembg 的上游。若继续穿（把"可达"当
        "喂我"），线性链也会被判成"多个产出方"而退回静态表，等于图白做。
        真正需要"歧义"的是**网关分支**（两条**实线**都进同一个节点），那种
        情况在网关处就会同时看到两个产出方，判据照样成立。
        """
        candidates = set(active)
        if stage not in candidates:
            return ()
        # 节点版 BFS 见 :meth:`producer_nodes_of`；对同阶段的**每个**节点实例
        # 各问一次，再把节点 id 折回阶段（单节点流程结果与改造前逐值一致）。
        found: list[str] = []
        for node_id in self.node_ids_of(stage):
            for hit in self.producer_nodes_of(node_id, port, active):
                item = self.node(hit)
                folded = fold_forward(item.stage, port) if item and item.stage else None
                if folded and folded not in found:
                    found.append(folded)
        return tuple(found)

    # ------------------------------------------------------ 节点粒度的产出方
    # B 方案（2026-10-17）：同阶段可以有**多个节点**，它们彼此独立（各自产物
    # 落点）。所以"谁喂我"必须在**节点**粒度上回答，不能只在阶段粒度上。
    # 下面两个方法就是 :meth:`nearest_producer` / :meth:`producers_of` 的节点版；
    # 阶段版委托它们实现，以免两份 BFS 逻辑各写一遍（漂移风险）。
    def _node_producers(self, node_id: str, port: str, active
                        ) -> list[str]:
        """从 ``node_id`` 反向 BFS，产出 ``port`` 的**在流程节点** id（广度序）。

        ``stop_at_first`` 语义由调用方取首个决定：本方法返回**全部**，最近的
        在列表最前（广度序），调用方取 ``[0]`` 即"最近"。
        """
        candidates = set(active)
        start = self.node(node_id)
        if start is None or not start.stage or start.stage not in candidates:
            return []
        queue = [node_id]
        seen = {node_id}
        found: list[str] = []
        while queue:
            current = queue.pop(0)
            for flow in self.incoming(current):
                source = flow.source
                if source in seen:
                    continue
                seen.add(source)
                item = self.node(source)
                if item is None or not item.stage:
                    queue.append(source)  # 网关/事件：不产出产物，继续往前穿
                    continue
                if item.stage in candidates and port in ports.stage_outputs(item.stage):
                    # 产出方：收下并**停止**这条分支（"谁喂我"而非"可达"）
                    if source not in found:
                        found.append(source)
                else:
                    queue.append(source)
        return found

    def nearest_producer_node(self, node_id: str, port: str, active
                              ) -> str | None:
        """**节点粒度**：从 ``node_id`` 沿图往前，最近的产出 ``port`` 的节点 id。

        ``active`` 是本流程实际要跑的**阶段**集合（Scheduler 给）；候选按节点
        的 ``stage`` 判在不在流程里。
        """
        producible = self._node_producers(node_id, port, active)
        return producible[0] if producible else None

    def producer_nodes_of(self, node_id: str, port: str, active
                          ) -> tuple[str, ...]:
        """**节点粒度**：``node_id`` 沿图可达的全部产出 ``port`` 的节点 id。

        用来判"**图能不能给出唯一答案**"（与阶段版 :meth:`producers_of` 同一
        判据，只是按节点实例）。
        """
        return tuple(self._node_producers(node_id, port, active))
