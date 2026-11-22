# -*- coding: utf-8 -*-
"""图的排布：无 DI 段兜底铺开、主动自动排版、注释重挂。"""

from __future__ import annotations

from desktop.steps.bpmn_diagram.constants import (
    AUTO_GAP_X,
    AUTO_GAP_Y,
    AUTO_PADDING,
    DEFAULT_SIZE,
    FALLBACK_SIZE,
    KIND_START,
    KIND_TASK,
    LAYOUT_GAP_X,
    LAYOUT_GAP_Y,
    LAYOUT_NOTE_GAP,
    LAYOUT_NOTE_STEP,
)
from desktop.steps.bpmn_diagram.helpers import _note_size, _overlaps, default_size


class _LayoutMixin:
    """``FlowDiagram`` 的排布部分（纯视觉，不改语义）。"""

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
        queue: list[tuple[str, int]] = (
            [(n.id, 0) for n in diagram.nodes if n.kind == KIND_START]
            or [(diagram.nodes[0].id, 0)]
            if diagram.nodes
            else []
        )
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

    def relayout(self) -> "FlowDiagram":
        """整图**自动排版**（就地改 ``boxes``、清空 ``waypoints``）。

        与 :meth:`auto_layout` 的分工：那个只在**文件没有 DI 段**时兜底，
        这个是用户点「自动排版」时的主动整理——不管有没有坐标都重排。

        分层布局（Sugiyama 简化版）：

        1. **分层**：层号 = 无入边节点出发的最长路（Kahn 拓扑序上逐点取
           ``max(前驱层)+1``）；环上剩下的点按声明顺序垫在最底层。
        2. **长边插虚拟节点**：跨了多层的那条边在中间层各占一个格子（经典
           Sugiyama 的 dummy node）。少了这一步，「是否拼版 →(否)→ PDF排版」
           会从同层的「图片拼版」框里横穿过去（用户 2026-10-06）。虚拟节点
           **只参与排序与占行**，不落坐标、不写文件。
        3. **同层排序**：按前驱重心向下扫一遍、再按后继重心向上扫一遍，
           减少连线交叉；重心相同时**虚拟节点优先**——让长边保持直线，
           分支节点被挤到下一行（与 bpmn.io 画出来的一致）。
        4. **落坐标**：x 按层排开；y **按行号**排（不再"相对最宽层居中"——
           那会让主链忽高忽低），每个节点在自己的行里**垂直居中**：要对齐
           的是水平中线，不是顶边（36px 的事件与 80px 的任务顶边对齐会高
           出一截）。
        5. **注释重挂**：每条注释放到**宿主节点正下方**，互相压住就往下让。
           ⚠️ 早期做法是"注释跟着宿主一起平移"——保留文件里的旧相对偏移，
           节点重排后那些偏移就变成一堆斜飘的注释、虚线还压着别的节点。

        ⚠️ 只动**节点**坐标与折点；阶段顺序（语义）不受影响——排版是纯视觉。
        """
        ids = [n.id for n in self.nodes]
        if not ids:
            return self
        id_set = set(ids)

        # ---- 有效连线（去重、去掉自环与悬空端点） -------------------------
        edges: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str]] = set()
        for flow in self.flows:
            pair = (flow.source, flow.target)
            if (
                flow.source in id_set
                and flow.target in id_set
                and flow.source != flow.target
                and pair not in seen
            ):
                seen.add(pair)
                edges.append((flow.source, flow.target, flow.id))
        successors: dict[str, list[str]] = {nid: [] for nid in ids}
        predecessors: dict[str, list[str]] = {nid: [] for nid in ids}
        for source, target, _fid in edges:
            successors[source].append(target)
            predecessors[target].append(source)

        # ---- ① 分层：Kahn 拓扑序上取最长路 ------------------------------
        indegree = {nid: len(predecessors[nid]) for nid in ids}
        ready = [nid for nid in ids if indegree[nid] == 0]
        order: list[str] = []
        while ready:
            nid = ready.pop(0)
            order.append(nid)
            for target in successors[nid]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
        layer: dict[str, int] = {nid: 0 for nid in order}
        for nid in order:
            for target in successors[nid]:
                layer[target] = max(layer.get(target, 0), layer[nid] + 1)
        bottom = max(layer.values(), default=0) + 1
        for nid in ids:  # 环上没排到的：垫在最底层，不丢节点
            layer.setdefault(nid, bottom)

        # ---- ② 跨层长边插虚拟节点 --------------------------------------
        # 「格子」= 真节点 ("n", id) 或虚拟节点 ("e", "<连线id>@<层号>")。
        cells: dict[int, list[tuple[str, str]]] = {}
        for nid in ids:
            cells.setdefault(layer[nid], []).append(("n", nid))
        cell_succ: dict[tuple[str, str], list[tuple[str, str]]] = {}
        cell_pred: dict[tuple[str, str], list[tuple[str, str]]] = {}

        def link(a: tuple[str, str], b: tuple[str, str]) -> None:
            cell_succ.setdefault(a, []).append(b)
            cell_pred.setdefault(b, []).append(a)

        for source, target, fid in edges:
            previous: tuple[str, str] = ("n", source)
            for lv in range(layer[source] + 1, layer[target]):
                current = ("e", f"{fid}@{lv}")
                cells.setdefault(lv, []).append(current)
                link(previous, current)
                previous = current
            link(previous, ("n", target))

        # ---- ③ 同层排序：前驱重心 → 后继重心，各扫两遍 ------------------
        # 重心相同按"虚拟节点优先"——长边走直线，分支垂下去。
        for row in cells.values():
            row.sort(key=lambda cell: 0 if cell[0] == "e" else 1)
        pos = {cell: i for row in cells.values() for i, cell in enumerate(row)}

        def barycenter(
            cell: tuple[str, str],
            table: dict[tuple[str, str], list[tuple[str, str]]],
        ) -> float:
            values = [pos[n] for n in table.get(cell, ()) if n in pos]
            return sum(values) / len(values) if values else pos[cell]

        for sweep in range(4):
            levels = sorted(cells) if sweep % 2 == 0 else sorted(cells, reverse=True)
            table = cell_pred if sweep % 2 == 0 else cell_succ
            for lv in levels:
                cells[lv].sort(key=lambda cell: barycenter(cell, table))
                for index, cell in enumerate(cells[lv]):
                    pos[cell] = index

        # ---- ④ 落坐标：x 按层、y 按行 ----------------------------------
        task_w, task_h = DEFAULT_SIZE[KIND_TASK]
        slot = task_h + LAYOUT_GAP_Y
        for lv in sorted(cells):
            x = AUTO_PADDING + lv * (task_w + LAYOUT_GAP_X)
            for index, cell in enumerate(cells[lv]):
                if cell[0] != "n":  # 虚拟节点只占行，不落坐标
                    continue
                item = self.node(cell[1])
                w, h = default_size(item.kind if item else KIND_TASK)
                self.boxes[cell[1]] = (
                    x,
                    AUTO_PADDING + index * slot + (slot - h) / 2,
                    w,
                    h,
                )

        # ---- ⑤ 注释重挂到宿主正下方（而不是跟着旧坐标平移） -------------
        self._layout_notes()

        # ---- ⑥ 旧折点全清：连线按新坐标由 route() 现算 -----------------
        self.waypoints.clear()
        return self

    def _layout_notes(self) -> None:
        """把每条注释放到**宿主节点的正下方**，互相压住就往下让一格。

        没有宿主的（用户自己画上去的）保持原坐标——但仍要与别人错开。
        """
        if not self.notes:
            return
        node_boxes = {n.id: self.boxes[n.id] for n in self.nodes if n.id in self.boxes}
        placed: list[tuple[float, float, float, float]] = []
        for note in self.notes:
            width, height = _note_size(note.text, self.boxes.get(note.id))
            host = node_boxes.get(self.note_links.get(note.id, ""))
            if host is not None:
                # 居中于宿主下方；⚠️ 别让左边界跑到画布外（窄节点如事件圆
                # 居中后会有一半悬在 0 左边）
                x = max(AUTO_PADDING, host[0] + (host[2] - width) / 2)
                y = host[1] + host[3] + LAYOUT_NOTE_GAP
            else:
                old = self.boxes.get(note.id)
                x, y = (old[0], old[1]) if old else (AUTO_PADDING, AUTO_PADDING)
            box = (x, y, width, height)
            for _ in range(len(self.notes) * 2 + 4):
                if not any(
                    _overlaps(box, other) for other in node_boxes.values()
                ) and not any(_overlaps(box, other) for other in placed):
                    break
                y += LAYOUT_NOTE_STEP
                box = (x, y, width, height)
            self.boxes[note.id] = box
            placed.append(box)
