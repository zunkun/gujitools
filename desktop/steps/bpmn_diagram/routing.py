# -*- coding: utf-8 -*-
"""连线走线：锚点自动匹配、多边摊开、折点计算与遮挡绕行。"""

from __future__ import annotations

from desktop.steps.bpmn_diagram.constants import (
    CORNER_CELL_EPS,
    ROUTE_ALIGN_TOLERANCE,
)
from desktop.steps.bpmn_diagram.elements import DiagramFlow


class _RoutingMixin:
    """``FlowDiagram`` 的连线走线部分（纯几何，不改语义）。"""

    # ---- 连线走线：锚点自动匹配 + 多边摊开 + 遮挡绕行 ----
    def _side_anchor(self, node_id: str, side: str, t: float) -> tuple[float, float]:
        """某条边上参数 ``t``（0=起点端，1=终点端，0.5=中点）处的锚点。

        ⚠️ **网关只认四个顶点**（用户 2026-10-06："判断输入输出都从四个角
        出，不是边的中间"）。菱形的边是**斜边**，"右边的 t=1/3"落在斜边中段
        ——看着像"从角上出发"，其实既不在角上，两条分支还挤在同一段斜边
        上。所以把 ``t`` **吸到最近的角**（0.5 保持顶点，<0.5 往上角、
        >0.5 往下角；左右两侧吸附到右/左顶点）。

        非网关（任务框、事件圆）不受影响：仍是边上的 ``t`` 位置。
        """
        x, y, w, h = self.node_box(node_id)
        item = self.node(node_id)
        if item is not None and item.is_gateway:
            cx, cy = x + w / 2, y + h / 2
            if side in ("right", "left"):
                px = x + w if side == "right" else x
                # 左右两侧只有一个顶点可用（中点就是角），t 不参与
                return (px, cy)
            # 上/下侧：按 t 吸到上角或下角（t=0.5 是正中，落在角上）
            py = y if t < 0.5 else y + h
            return (cx, py)
        if side == "right":
            return (x + w, y + h * t)
        if side == "left":
            return (x, y + h * t)
        if side == "bottom":
            return (x + w * t, y + h)
        return (x + w * t, y)  # top

    def route_anchor(self, flow: DiagramFlow) -> tuple[str, float, str, float]:
        """连线两端**该用哪个连接点**：``(源方向, 源位置t, 目标方向, 目标位置t)``。

        方向按两节点中心的相对方位挑（横向主导走左右、纵向主导走上下）。

        **多条边怎么分开**（用户 2026-10-06，2026-10-07 细化）：

        - **同侧挤车先改侧**：一个节点有多条入边/出边、且多条按方位落到
          同一条**横向边**上时，只留与它**同一行**的那条（保持中线对齐），
          其余按"对端在下方→走下边、在上方→走上边"改走竖边——
          「图片拼版 → PDF排版」因此从**下边**进，不再把网关「否」那条
          顶得偏离 PDF排版 的水平中线。竖边内部真撞车才沿边摊开。
        - **任务框 / 事件圆**：改侧之后仍同侧的多条边沿边摊开（``t`` 均分）。
        - **网关（判断）**：**分配到不同的角**（:meth:`_corner_pick`）。
        """
        s_side, s_t = self._end_anchor(flow, outgoing=True)
        t_side, t_t = self._end_anchor(flow, outgoing=False)
        # 网关端：方向与 t 一起由「九宫格分区」决定（保证不同分支占不同角）
        if self._is_gateway(flow.source):
            s_side, s_t = self._corner_pick(flow.source, flow, outgoing=True)
        if self._is_gateway(flow.target):
            t_side, t_t = self._corner_pick(flow.target, flow, outgoing=False)
        return (s_side, s_t, t_side, t_t)

    def _end_anchor(
        self,
        flow: DiagramFlow,
        *,
        outgoing: bool,
    ) -> tuple[str, float]:
        """非网关一端的 ``(方向, t)``：同侧撞车先改侧，入口/出口**不共点**。

        ``outgoing=True`` 算**源端**（对端是 target），否则算**目标端**
        （对端是 source）。横向边上的撞车按"同一行"判：对端中心与
        本节点中心的 ``|dy|`` 超过两边高之和的 1/4 就算不齐行——
        网关与任务框同行（dy≈0）留左边，正下方的任务框让出左边改走下边。

        ⚠️ **入口/出口不共点**（用户 2026-10-07）：同一个节点、同一条边
        上，**反向**的那条连线已经占了某个位置（比如"从左边进来"和"往
        左边出去"都想要中点），本端沿边挪到四分点让开。网关只有四个
        顶点、``t`` 产生不出新位置，保持九宫格分角的结果不让。
        """
        node_id = flow.source if outgoing else flow.target
        side, t = self._raw_end_anchor(flow, outgoing=outgoing)
        if not self._is_gateway(node_id):
            # 撞车的不止一对时按**声明顺序**分空档：排在前面的挑第一个
            # 空位——两边各自计算也能算出互补的错位点（不然会一起挪到
            # 同一个四分点上，白让）。
            occupied: set[float] = set()
            my_index = next(i for i, f in enumerate(self.flows) if f is flow)
            rank = 0
            for other_index, other in enumerate(self.flows):
                if other is flow:
                    continue
                if (other.target if outgoing else other.source) != node_id:
                    continue
                o_side, o_t = self._raw_end_anchor(other, outgoing=not outgoing)
                if o_side != side:
                    continue
                o_t = round(o_t, 6)
                occupied.add(o_t)
                if o_t == round(t, 6) and other_index < my_index:
                    rank += 1
            if round(t, 6) in occupied:
                free_slots = [
                    c
                    for c in (0.25, 0.75, 0.125, 0.375, 0.625, 0.875)
                    if round(c, 6) not in occupied
                ]
                if rank < len(free_slots):
                    t = free_slots[rank]
        return side, t

    def _raw_end_anchor(
        self,
        flow: DiagramFlow,
        *,
        outgoing: bool,
    ) -> tuple[str, float]:
        """不看反向共点的 ``(方向, t)``（纯几何方位 + 同侧摊开）。"""
        node_id = flow.source if outgoing else flow.target
        others = [
            f for f in self.flows if (f.source if outgoing else f.target) == node_id
        ]
        nx, ny, nw, nh = self.node_box(node_id)
        ncx, ncy = nx + nw / 2, ny + nh / 2
        opposite = [self.node_box(f.target if outgoing else f.source) for f in others]
        sides: list[str] = []
        for box in opposite:
            bx, by, bw, bh = box
            dx = (bx + bw / 2) - ncx
            dy = (by + bh / 2) - ncy
            if abs(dx) >= abs(dy):
                # 横向主导：走**朝向对端**的那条边（源端朝对端出、
                # 目标端从对端来的那面进——两个方向的表达式相同）
                sides.append("right" if dx >= 0 else "left")
            else:
                sides.append("bottom" if dy >= 0 else "top")
        # 横向边撞车：不齐行的让出横边，改走对着对端的竖边
        for horiz in ("left", "right"):
            members = [i for i, s in enumerate(sides) if s == horiz]
            if len(members) <= 1:
                continue
            for i in members:
                bx, by, bw, bh = opposite[i]
                dy = (by + bh / 2) - ncy
                if abs(dy) > (nh + bh) / 4:
                    sides[i] = "bottom" if dy > 0 else "top"
        index = others.index(flow)
        side = sides[index]
        group = [i for i, s in enumerate(sides) if s == side]
        if len(group) <= 1:
            return side, 0.5
        return side, (group.index(index) + 1) / (len(group) + 1)

    def _is_gateway(self, node_id: str) -> bool:
        item = self.node(node_id)
        return bool(item is not None and item.is_gateway)

    def _corner_pick(
        self, gateway_id: str, flow: DiagramFlow, *, outgoing: bool
    ) -> tuple[str, float]:
        """网关上这条线该占**哪个角**：返回 ``(方向, t)``。

        ⚠️ 别用"方位角接近就同侧"来分——自动排版后「PDF排版」在网关**正右**、
        「图片拼版」在**右下**，方位角只差 0.4 弧度，会被判成"同侧"而挤到
        同一个点上（实测）。这里按**九宫格分区**：先看对端在网关的左/中/右
        三列，再看上/中/下三行，落到哪个格就用那个格对应方向的角。

        分区后若仍有两条落在同一格（对端真的重叠），才退回沿边摊开。
        """
        gx, gy, gw, gh = self.node_box(gateway_id)
        gcx, gcy = gx + gw / 2, gy + gh / 2

        def cell_of(other: DiagramFlow) -> int:
            other_id = other.target if outgoing else other.source
            ox, oy, ow, oh = self.node_box(other_id)
            ocx, ocy = ox + ow / 2, oy + oh / 2
            col = (
                0
                if ocx < gcx - CORNER_CELL_EPS
                else (2 if ocx > gcx + CORNER_CELL_EPS else 1)
            )
            row = (
                0
                if ocy < gcy - CORNER_CELL_EPS
                else (2 if ocy > gcy + CORNER_CELL_EPS else 1)
            )
            return row * 3 + col

        others = [
            f for f in self.flows if (f.source if outgoing else f.target) == gateway_id
        ]
        cell = cell_of(flow)
        same = [f for f in others if cell_of(f) == cell]
        if len(same) <= 1:
            return (self._cell_side(cell), 0.5)
        # 真重叠：沿边摊开，保证两点不重合
        index = next(i for i, f in enumerate(same) if f.id == flow.id)
        return (self._cell_side(cell), (index + 1) / (len(same) + 1))

    @staticmethod
    def _cell_side(cell: int) -> str:
        """九宫格格子 → 该占菱形的哪个**顶点方向**。

        行 0=上/中/下，列 0=左/中/右。菱形只有四个顶点（上/右/下/左），
        所以角落格要**对角映射**：右上格→右顶点、右下格→下顶点（两条分支
        才能真的分开——早前把col==2 一律映射成"右"，右上与右下撞成同一
        个点，实测「是否拼版」的「是/否」又叠回去了）。
        """
        row, col = divmod(cell, 3)
        if row == 1 and col == 1:
            return "right"  # 正前方：右顶点
        if row == 0 and col >= 1:
            return "top"  # 上方两格 → 上顶点
        if row == 2 and col >= 1:
            return "bottom"  # 下方两格 → 下顶点
        return "left" if col == 0 else "right"

    def route(self, flow: DiagramFlow) -> list[tuple[float, float]]:
        """连线的折点（文件没存 ``di:waypoint`` 时算一份）。

        连接点自动匹配（:meth:`route_anchor`）；两端**正好共线**时走直线，
        但直线被中间节点挡住就**绕行**——线段不许被别的节点盖住（用户
        2026-10-06）。需要"锚点不动"的场合（拖动中预览）走 :meth:`route_sides`。
        """
        return self.route_sides(flow, self.route_anchor(flow))

    def route_sides(
        self,
        flow: DiagramFlow,
        anchor: tuple[str, float, str, float],
    ) -> list[tuple[float, float]]:
        """按**指定的连接点**算折点（锚点冻结的走线）。

        ⚠️ **近似共线就拉直**（容差 :data:`ROUTE_ALIGN_TOLERANCE`）：同一节点
        的多条出入边要沿边摊开（判断的「是/否」不能从同一点出发），于是出口
        与入口的 y 会差几像素——这时画成 L 形会多出一个肉眼看得见的小台阶，
        不如直接拉一条直线（BPMN 惯例）。
        """
        s_side, s_t, t_side, t_t = anchor
        start = self._side_anchor(flow.source, s_side, s_t)
        end = self._side_anchor(flow.target, t_side, t_t)
        s_horizontal = s_side in ("right", "left")
        t_horizontal = t_side in ("right", "left")
        if s_horizontal != t_horizontal:
            # 混合轴（如"任务框右边 → 目标下边"）：第一段沿**源**的轴离开、
            # 末段沿**目标**的轴进入——箭头永远垂直于被进入的那条边。早前
            # 一律"先横后竖"，从竖边（网下角）出来的线会先横着拐、箭头变成
            # 向下斜戳进目标的横边（用户 2026-10-07）。
            if s_horizontal:
                points = [start, (end[0], start[1]), end]
            else:
                points = [start, (start[0], end[1]), end]
            blockers: list[tuple[float, float, float, float]] = []
            for first, second in zip(points, points[1:]):
                blockers.extend(self._blockers_on(first, second, flow))
            if not blockers:
                return points
            return self._detour_around(start, end, blockers)
        if s_horizontal:
            if abs(start[1] - end[1]) <= ROUTE_ALIGN_TOLERANCE:
                blockers = self._blockers_on(start, end, flow)
                if not blockers:
                    return [start, end]
                return self._detour_around(start, end, blockers)
            mid = (start[0] + end[0]) / 2
            points = [start, (mid, start[1]), (mid, end[1]), end]
        else:
            if abs(start[0] - end[0]) <= ROUTE_ALIGN_TOLERANCE:
                blockers = self._blockers_on(start, end, flow)
                if not blockers:
                    return [start, end]
                return self._detour_around(start, end, blockers)
            mid = (start[1] + end[1]) / 2
            points = [start, (start[0], mid), (end[0], mid), end]
        # ⚠️ **L 形也要查挡路**：上面两处只在"两端共线"时才查（那时一条直线
        # 段就够判断），L 形有两段，漏查就会让「是否拼版 →(否)→ PDF排版」那种
        # 跨层长边从「图片拼版」的框里穿过去（用户 2026-10-06）。绕行按直线
        # 段的挡路算——终点那一段被挡时也还有别的路可走。
        blockers: list[tuple[float, float, float, float]] = []
        for first, second in zip(points, points[1:]):
            blockers.extend(self._blockers_on(first, second, flow))
        if not blockers:
            return points
        return self._detour_around(start, end, blockers)

    def _blockers_on(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        flow: DiagramFlow,
    ) -> list[tuple[float, float, float, float]]:
        """直线段穿过的**其他节点**的框（略放大，线不贴着别人的框走）。"""
        margin = 6.0
        skip = {flow.source, flow.target}
        blockers: list[tuple[float, float, float, float]] = []
        for node in self.nodes:
            if node.id in skip or node.id not in self.boxes:
                continue
            bx, by, bw, bh = self.boxes[node.id]
            bx -= margin
            by -= margin
            bw += margin * 2
            bh += margin * 2
            lo_x, hi_x = sorted((start[0], end[0]))
            lo_y, hi_y = sorted((start[1], end[1]))
            if lo_x <= bx + bw and bx <= hi_x and lo_y <= by + bh and by <= hi_y:
                blockers.append((bx, by, bw, bh))
        return blockers

    def _detour_around(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        blockers: list[tuple[float, float, float, float]],
    ) -> list[tuple[float, float]]:
        """从挡路的节点**侧面绕过去**（挑近的一侧，4 个折点）。

        直线段的两端必在障碍带外侧（:meth:`_blockers_on` 只收"段中间"的
        框），所以先沿自己这条边走到障碍带外、贴着障碍带走一段、再回到
        终点所在的边——三段都走在空档里。起终点本身在障碍带里（绕不了）
        就退回普通的中间通道走线。
        """
        margin = 10.0
        vertical = abs(start[0] - end[0]) < 1.0
        if vertical:
            # 沿 y 的直线：从左右两侧绕（bus = 绕行通道的 x）
            band_lo = min(b[1] for b in blockers) - margin
            band_hi = max(b[1] + b[3] for b in blockers) + margin
            left = min(b[0] for b in blockers) - margin
            right = max(b[0] + b[2] for b in blockers) + margin
            y1, y2 = sorted((start[1], end[1]))
            if band_lo < y1 or band_hi > y2:
                mid = (start[1] + end[1]) / 2
                return [start, (start[0], mid), (end[0], mid), end]
            bus = left if abs(left - start[0]) <= abs(right - start[0]) else right
            return [start, (bus, start[1]), (bus, end[1]), end]
        # 沿 x 的直线：从上下两侧绕（bus = 绕行通道的 y）
        band_lo = min(b[0] for b in blockers) - margin
        band_hi = max(b[0] + b[2] for b in blockers) + margin
        top = min(b[1] for b in blockers) - margin
        bottom = max(b[1] + b[3] for b in blockers) + margin
        x1, x2 = sorted((start[0], end[0]))
        if band_lo < x1 or band_hi > x2:
            mid = (start[0] + end[0]) / 2
            return [start, (mid, start[1]), (mid, end[1]), end]
        bus = top if abs(top - start[1]) <= abs(bottom - start[1]) else bottom
        return [start, (start[0], bus), (end[0], bus), end]
