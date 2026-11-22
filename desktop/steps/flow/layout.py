# -*- coding: utf-8 -*-
"""流程的**图形布局** :class:`FlowLayout`（纯数据、纯计算，不 import Qt）。"""

from __future__ import annotations

from dataclasses import dataclass, field


def _diagram_nodes(flow: "FlowDefinition") -> list[str]:
    """图形段里该画哪些节点：``start`` + 运行阶段 + ``end``。"""
    return ["start", *flow.stages, "end"]


@dataclass
class FlowLayout:
    """流程的**图形布局**：节点框位置 + 连线折点（BPMN DI 段的来源）。

    坐标单位是 BPMN ``dc:Bounds`` 的用户单位（1 ≈ 1px，本项目不缩放）。

    ⚠️ **纯数据、纯计算，不 import Qt**（与本模块其余部分同一约束）：它既是
    :meth:`FlowDefinition.to_xml` 写 DI 段的数据源，也是 GUI 画布（需要
    ``QPointF``）的换算依据。GUI 侧只做类型转换，几何算法**只有这一份**。

    - ``boxes``：``节点 id → (x, y, w, h)``，缺节点按 :meth:`auto` 补；
    - :meth:`node_box` 返回矩形 :meth:`auto` 生成的节点，:meth:`edge_points`
      返回 :meth:`route` 生成的折点。
    """

    boxes: dict[str, tuple[float, float, float, float]] = field(
        default_factory=dict
    )
    #: 排了几行（:meth:`auto` 填）。**不参与序列化**——它能从 ``boxes`` 算出来，
    #: 只是给"绕行留白/行距"用，省得每次都重算 max。
    _row_count: int = field(default=1, repr=False)
    #: 事件圆直径 / 任务框尺寸 / 节点间距 / 画布留白（与 GUI 画布共用口径）
    EVENT_SIZE = 36.0
    NODE_SIZE = (148.0, 56.0)
    GAP = 56.0
    PADDING = 22.0
    #: 条件边绕行那一行的额外高度
    BYPASS_ROW = 44.0
    #: 折行时**行与行之间**的垂直间距（比行内间距大，让两条连线不粘在一起）
    ROW_GAP = 40.0

    @classmethod
    def auto(cls, flow: "FlowDefinition", max_width: float | None = None
             ) -> "FlowLayout":
        """默认排布：``start → 节点… → end``。

        :param max_width:
            ``None``（默认）= 强制**一行到底**，落进 ``flow.bpmn`` 的 DI 段
            用这个——文件里的坐标要稳定可预期，不能随打开它的窗口宽度变。

            给定宽度时**超宽就折行**：默认流程 8 个节点一字排开约 1400px，
            弹窗/面板通常只有 1000 出头，不折行的话右侧节点被横向滚动条
            挡住——用户在"创建任务"弹窗里一眼看不完整个流程，这正是
            入口该做到的事。

        有条件边时底部**多留一行** ``BYPASS_ROW``——条件边要从节点底下绕
        过去，留白不够那条线会被裁掉（现象是"虚线条件边看不见"）。
        折行时每行都按需留绕行空间（绕行路径按行数逐层下移）。
        """
        layout = cls()
        nodes = _diagram_nodes(flow)
        limit = max_width if max_width and max_width > 0 else None
        # 折行时先算每行能放几个：按"节点宽 + 间距"贪心装，装不下的换行。
        per_row = len(nodes)
        if limit is not None:
            per_row = cls._nodes_per_row(nodes, limit)

        y = cls.PADDING
        x = cls.PADDING
        row = 0
        index = 0
        while index < len(nodes):
            # 本行节点：按 per_row 切一段
            chunk = nodes[index:index + per_row]
            # ⚠️ 每行**按实际节点数居中**：末行往往只有两三个节点，若一律
            # 从左边起排，右边会空一大块、整张图看着"歪向左上"（折行只解决
            # 装不下的问题，观感问题得靠居中）。
            row_width = sum(
                cls.EVENT_SIZE if n in ("start", "end") else cls.NODE_SIZE[0]
                for n in chunk
            ) + cls.GAP * (len(chunk) - 1)
            x = cls.PADDING + max(
                0.0, (cls.widest_row(nodes, per_row) - row_width) / 2
            )
            for node_id in chunk:
                if node_id in ("start", "end"):
                    size = cls.EVENT_SIZE
                    top = y + (cls.NODE_SIZE[1] - size) / 2
                else:
                    size = None
                    top = y
                box = layout.boxes.get(node_id)
                if box is None:
                    layout.boxes[node_id] = (
                        x, top,
                        size if size is not None else cls.NODE_SIZE[0],
                        size if size is not None else cls.NODE_SIZE[1],
                    )
                else:
                    # 已有坐标：保留用户拖的位置，只补尺寸
                    layout.boxes[node_id] = (box[0], box[1], box[2], box[3])
                x += (size or cls.NODE_SIZE[0]) + cls.GAP
            index += per_row
            if index < len(nodes):
                # 换行：y 下移一整行（含上一行可能需要的绕行留白）
                y += cls.NODE_SIZE[1] + cls.BYPASS_ROW + cls.ROW_GAP
                row += 1
        layout._row_count = row + 1
        return layout

    @classmethod
    def widest_row(cls, nodes: list[str], per_row: int) -> float:
        """折行后**最宽那一行**的节点带宽度（不含留白，用来把各行居中）。"""
        widest = 0.0
        for start in range(0, len(nodes), per_row):
            chunk = nodes[start:start + per_row]
            widest = max(widest, sum(
                cls.EVENT_SIZE if n in ("start", "end") else cls.NODE_SIZE[0]
                for n in chunk
            ) + cls.GAP * (len(chunk) - 1))
        return widest

    @classmethod
    def _nodes_per_row(cls, nodes: list[str], max_width: float) -> int:
        """给定宽度，一行最多放几个节点（贪心装，至少 2 个）。

        ⚠️ 至少 2：只有 1 个/行的折行比不折还难看（每个节点独占一整行，
        竖向拉得极长）。宁可让那一行稍微超宽、出横向滚动条。
        """
        total = 0.0
        count = 0
        for node_id in nodes:
            w = cls.EVENT_SIZE if node_id in ("start", "end") else cls.NODE_SIZE[0]
            need = w if count == 0 else cls.GAP + w
            if count and total + need > max_width and count >= 2:
                break
            total += need
            count += 1
        return max(count, 2)

    # ------------------------------------------------------------ 查询
    def node_box(self, node_id: str) -> tuple[float, float, float, float]:
        """节点矩形 ``(x, y, w, h)``；没有就按默认排布补一个。"""
        if node_id not in self.boxes:
            raise KeyError(f"布局里没有节点 {node_id!r}")
        return self.boxes[node_id]

    def has(self, node_id: str) -> bool:
        return node_id in self.boxes

    def move(self, node_id: str, x: float, y: float) -> None:
        """拖动节点：只改左上角坐标，**尺寸不变**（拖拽不改语义）。"""
        if node_id in self.boxes:
            box = self.boxes[node_id]
            self.boxes[node_id] = (float(x), float(y), box[2], box[3])

    def remove(self, node_id: str) -> None:
        self.boxes.pop(node_id, None)

    # ------------------------------------------------------------ 连线折点
    def edge_points(self, source: str, consumer: str,
                    landing: int = 0, total: int = 1
                    ) -> list[tuple[float, float]]:
        """一条无条件连线的折点（``di:waypoint`` 序列）。

        源点取源框**右缘中点**，终点取目标框**左缘中点**——与 GUI 画布
        (:mod:`desktop.components.flow_view`) 的画法一致，两边不会画出
        两条不一样的线。

        - ``landing`` / ``total``：这条边在"进 ``consumer`` 的所有边"里排第
          几、共几条。**必须错开落点**（纵向均分），否则多条边画成同一条线，
          只看得出最后画的那条（默认流程 ``rembg``/``print`` 都有多条入边）。
        """
        src = self.boxes.get(source)
        dst = self.boxes.get(consumer)
        if src is None or dst is None:
            return []
        start = (src[0] + src[2], src[1] + src[3] / 2)
        end = (dst[0], dst[1] + dst[3] / 2 + self._landing_offset(landing, total))
        if abs(start[1] - end[1]) < 1.0:
            return [start, end]
        row_y = self.bypass_y()
        if end[0] <= start[0]:
            return [start, (start[0], row_y), (end[0], row_y), end]
        mid = (start[0] + end[0]) / 2
        return [start, (mid, start[1]), (mid, end[1]), end]

    def bypass_points(self, source: str, consumer: str,
                      landing: int = 0, total: int = 1
                      ) -> list[tuple[float, float]]:
        """条件边的折点：**永远绕行**（不因同行就直连）。"""
        src = self.boxes.get(source)
        dst = self.boxes.get(consumer)
        if src is None or dst is None:
            return []
        start = (src[0] + src[2], src[1] + src[3] / 2)
        end = (dst[0], dst[1] + dst[3] / 2 + self._landing_offset(landing, total))
        row_y = self.bypass_y()
        return [start, (start[0], row_y), (end[0], row_y), end]

    #: 同目标多条边的落点纵向间距（px）
    LANDING_GAP = 16.0

    def _landing_offset(self, landing: int, total: int) -> float:
        """第 ``landing`` 条（共 ``total`` 条）入边的纵向偏移：整体居中均分。"""
        if total <= 1:
            return 0.0
        return (landing - (total - 1) / 2) * self.LANDING_GAP

    def bypass_y(self) -> float:
        """条件边绕行那一行的 y（所有节点下方、留白之内）。"""
        if not self.boxes:
            return self.PADDING
        bottom = max(box[1] + box[3] for box in self.boxes.values())
        return bottom + self.BYPASS_ROW / 2

    # ------------------------------------------------------------ 序列化
    def to_dict(self) -> dict[str, list[float]]:
        return {key: list(box) for key, box in self.boxes.items()}

    @classmethod
    def from_dict(cls, raw: dict | None) -> "FlowLayout":
        """从 :meth:`to_dict` 的结构还原；**忽略尺寸为 0 的坏数据**。"""
        layout = cls()
        for key, value in (raw or {}).items():
            try:
                numbers = tuple(float(v) for v in value)
            except (TypeError, ValueError):
                continue
            if len(numbers) == 4 and numbers[2] > 0 and numbers[3] > 0:
                layout.boxes[key] = numbers  # type: ignore[assignment]
        return layout
