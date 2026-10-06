# -*- coding: utf-8 -*-
"""BPMN 流程图**编辑控件**：拖节点、连边、改名、增删。

## 设计要点

- **改的是同一份 :class:`FlowDiagram`**（页面看到的图 = 文件里的图），保存
  即写回 ``.bpmn``。没有"界面模型"与"文件模型"两份东西。
- **拖节点只改坐标**，不动连线语义——拖拽是排版操作。连线折点若文件里
  有，拖动后**清掉重算**（旧折点会指向老地方，线会歪）。
- **连线有两条路**（都能用，用户挑顺手的）：
  1. **连线模式**：点工具栏「连线」→ 点起点节点 → 点终点节点（推荐，
     命中判定宽松、有状态提示）；
  2. **热点拖拽**：直接按住节点右缘的小圆点拖到目标节点。
- **节点与连线各有一套选中**，互斥；选中后工具栏的「重命名 / 删除」才可用。
  这条是硬需求：之前只有"点一下变个色"，用户不知道选中能干什么。
- 所有鼠标/键盘事件 ``try/except``（控件在弹窗里，一次未捕获异常会连用户
  编好的图一起丢）。

⚠️ 编辑结果落在 :meth:`diagram` 返回的那份图上（原地改），由宿主调
:meth:`save_to` 落盘。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QInputDialog, QMessageBox, QSizePolicy

from desktop.components.bpmn_view import BpmnView
from desktop.steps.bpmn_diagram import (
    KIND_EXCLUSIVE, KIND_TASK, DiagramFlow, DiagramNode, FlowDiagram,
    default_size,
)
from desktop.ui import theme as T

#: 右侧连线热点的绘制半径（px）
HANDLE_RADIUS = 7.0
#: 热点的命中半径（比画出来的大一倍，否则要点中太难——实测 3px 的圆基本点不到）
HANDLE_HIT = 15.0
#: 拖拽的最小位移（低于它算"点击"而不是"拖拽"）
DRAG_THRESHOLD = 3.0
#: 连线命中判定的容差（点到折线的距离小于它算命中）
EDGE_HIT = 9.0
#: 新节点与锚点节点的间距
NEW_NODE_GAP = 40.0
#: 新节点最大尝试次数（先向右、再向下，避免压在已有节点上）
PLACE_TRIES = 8


def _distance_to_segment(point: QPointF, start: QPointF, end: QPointF) -> float:
    """点到线段的距离（纯 float 运算，**不对 QPointF 做 sip 运算**）。"""
    px, py = point.x(), point.y()
    ax, ay = start.x(), start.y()
    bx, by = end.x(), end.y()
    dx, dy = bx - ax, by - ay
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


class BpmnEditor(BpmnView):
    """可编辑的 BPMN 视图（继承 :class:`BpmnView` 的渲染，加交互）。"""

    #: 图被改动（宿主据此标"未保存"）
    diagram_changed = Signal()
    #: 选中节点变化（空串 = 清空）
    selection_changed = Signal(str)
    #: 选中连线变化（空串 = 清空）
    flow_selection_changed = Signal(str)
    #: 连线模式开关变化
    link_mode_changed = Signal(bool)

    #: 画布尺寸下限（类属性而非纯实例属性：``BpmnView.__init__`` 会先调一次
    #: ``_update_size``，那时 ``__init__`` 里赋的实例属性还不存在）。
    _floor: tuple[float, float] = (1.0, 1.0)

    def __init__(self, diagram: FlowDiagram | None = None, parent=None, *,
                 name_source: FlowDiagram | None = None):
        """
        :param name_source: 给**新加节点**取名字时参考的另一张图（通常是默认
            模板）。用户在模板里把 ``print`` 那格叫「PDF排版」，新加的节点就该
            沿用这个叫法——凭空起名会与结束事件撞名。
        """
        self._floor = (1.0, 1.0)
        super().__init__(diagram, parent)
        self._name_source = name_source
        # 接收从固定节点面板拖过来的节点（见 bpmn_palette）
        self.setAcceptDrops(True)
        self._drag_id: str | None = None
        self._drag_offset = QPointF()
        self._press_pos: QPointF | None = None
        self._moved = False
        self._link_from: str | None = None
        self._link_pos: QPointF | None = None
        self._link_mode = False
        self.setCursor(Qt.ArrowCursor)
        # 键盘（Delete 删选中）需要焦点
        self.setFocusPolicy(Qt.StrongFocus)

    # ------------------------------------------------------------ 数据
    def set_diagram(self, diagram: FlowDiagram) -> None:
        super().set_diagram(diagram)
        self._drag_id = None
        self._link_from = None
        self._link_pos = None

    def set_selected(self, node_id: str | None) -> None:
        """选中节点。

        ⚠️ 节点与连线**互斥**：选中一个就清掉另一个。不互斥的话界面上会出现
        "两个东西都高亮"，而「删除」只能删一个——用户按下去删错了才发现。
        这里用 ``super()`` 直接改状态，避免两个 setter 互相递归。
        """
        super().set_selected(node_id)
        self.selection_changed.emit(node_id or "")
        if node_id and self._selected_flow:
            super().set_selected_flow(None)
            self.flow_selection_changed.emit("")

    def set_selected_flow(self, flow_id: str | None) -> None:
        """选中连线（同样互斥，见 :meth:`set_selected`）。"""
        super().set_selected_flow(flow_id)
        self.flow_selection_changed.emit(flow_id or "")
        if flow_id and self.selected():
            super().set_selected(None)
            self.selection_changed.emit("")

    # ------------------------------------------------------------ 画布尺寸
    def set_canvas_floor(self, width: float, height: float) -> None:
        """给画布一个"至少这么大"的下限。

        ⚠️ 为什么需要：编辑时得**有地方放节点**。只按内容尺寸给大小的话，
        图很小时控件就只有一小条，用户想把节点拖到旁边都拖不出去（鼠标一出
        控件就从滚动区走了）。宿主把它设成视口尺寸，画布就总是铺满可见区。
        """
        floor = (float(max(width, 1)), float(max(height, 1)))
        if floor != self._floor:
            self._floor = floor
            self._update_size()

    def _update_size(self) -> None:
        """编辑态尺寸 = max(内容, 下限)；**min = max** 钉死，避免布局反复拉扯。"""
        width, height = self.content_size()
        w = int(max(width, self._floor[0]))
        h = int(max(height, self._floor[1]))
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setMinimumSize(w, h)
        self.setMaximumSize(w, h)
        if self.width() != w or self.height() != h:
            self.resize(w, h)
        self.update()

    # ------------------------------------------------------------ 连线模式
    def link_mode(self) -> bool:
        return self._link_mode

    def set_link_mode(self, enabled: bool) -> None:
        """开/关「点两下连线」模式（开时禁用拖拽，避免两种手势打架）。"""
        enabled = bool(enabled)
        if enabled == self._link_mode:
            return
        self._link_mode = enabled
        self._link_from = None
        self._link_pos = None
        self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)
        self.link_mode_changed.emit(enabled)
        self.update()

    # ------------------------------------------------------------ 编辑动作
    def add_node(self, kind: str = KIND_TASK, name: str = "新步骤",
                 stage: str | None = None,
                 at: tuple[float, float] | None = None,
                 connect_from: str | None = None) -> str:
        """加一个节点，返回它的 id。

        :param at: 画布坐标（**像素**，控件坐标）——从面板拖放的落点走这里，
            节点以该点为中心。不给就用 :meth:`_free_slot` 自动找空位。
        :param connect_from: 加完顺手连一条 ``connect_from → 新节点``
            （拖放时若正选中着某节点，就等于"接在它后面"）。
        """
        return self._add_node(kind, name, stage, at, connect_from)

    def add_step(self, token: str, at: tuple[float, float] | None = None,
                 connect_from: str | None = None) -> str | None:
        """按**步骤 key**加节点（固定节点面板拖放的入口）。

        ``token`` 是 :data:`~desktop.components.bpmn_palette.GATEWAY_TOKEN`
        时加的是排他网关；否则按步骤 key 取名字与运行阶段。
        """
        from desktop.components.bpmn_palette import (
            GATEWAY_NAME, GATEWAY_TOKEN, palette_name, step_stage,
        )
        from desktop.steps import ports

        def step_stage_of(stage_key: str) -> str:
            """运行阶段 → 它归属的**界面格**（`rembg_submit` 归 `rembg`）。"""
            return ports.STAGE_STEPS.get(stage_key, stage_key)

        if token == GATEWAY_TOKEN:
            return self._add_node(KIND_EXCLUSIVE, GATEWAY_NAME, None, at,
                                  connect_from)
        if not token:
            return None
        stage = step_stage(token)
        if stage is None:
            return None
        # ⚠️ **同一格只允许一个节点**：运行阶段是**按名字接回**的，两个同阶段
        #    节点只会让 `stage_order()` 去重、界面更乱，纯属给自己找麻烦。
        #    面板那头已经把已有的置灰了；这里再挡一道（拖放/程序调用都可能绕过）。
        for node in self.diagram().nodes:
            if node.stage and step_stage_of(node.stage) == token:
                return None
        name = palette_name(token, self.diagram(), self._name_source)
        return self._add_node(KIND_TASK, name, stage, at, connect_from)

    def _add_node(self, kind: str, name: str, stage: str | None,
                  at: tuple[float, float] | None,
                  connect_from: str | None) -> str:
        """加节点的实现（``add_node`` / ``add_step`` 都汇到这里）。

        ⚠️ **只有 ``task`` 才按名字接运行阶段**（与 :meth:`FlowDiagram.load`
        同一口径）：事件/网关是图形控制元素，名字碰巧撞上阶段名也不该占一格。
        不在这里接的话，用户新加的「图片拼版」会以"未被识别"的灰状态存在
        ——图上有、运行时却不跑，正是最容易被误判成 bug 的现象。
        """
        from desktop.steps.bpmn_diagram import default_size, stage_of_name

        if stage is None and kind == KIND_TASK:
            stage = stage_of_name(name)
        diagram = self.diagram()
        used = {n.id for n in diagram.nodes}
        index = len(used) + 1
        node_id = f"Node_{index}"
        while node_id in used:
            index += 1
            node_id = f"Node_{index}"
        if at is None:
            x, y, w, h = self._free_slot(kind)
        else:
            # 从面板拖过来：**以落点为中心**放节点（所见即所得），并夹在画布内
            w, h = default_size(kind)
            ox, oy = self._offset()
            x = max(4.0, float(at[0]) - ox - w / 2)
            y = max(4.0, float(at[1]) - oy - h / 2)
        diagram.nodes = diagram.nodes + (
            DiagramNode(id=node_id, kind=kind, name=name, stage=stage),
        )
        diagram.boxes[node_id] = (float(x), float(y), float(w), float(h))
        # 拖放时若正选中着某个节点，顺手接一条线（"挂在它后面"）——省一次连线
        if connect_from and connect_from != node_id \
                and diagram.node(connect_from) is not None:
            self.connect(connect_from, node_id)
        self._update_size()
        self.set_selected_flow(None)
        self.set_selected(node_id)
        self.diagram_changed.emit()
        self.update()
        return node_id

    # ------------------------------------------------------------ 面板拖放
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        from desktop.components.bpmn_palette import NODE_MIME

        if event.mimeData().hasFormat(NODE_MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        from desktop.components.bpmn_palette import NODE_MIME

        if event.mimeData().hasFormat(NODE_MIME):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        """面板拖过来的节点在这里落地。

        ⚠️ 全程 ``try/except``：拖放异常冒泡会连用户编好的图一起丢（同鼠标事件）。
        """
        from desktop.components.bpmn_palette import NODE_MIME

        mime = event.mimeData()
        if not mime.hasFormat(NODE_MIME):
            super().dropEvent(event)
            return
        try:
            token = bytes(mime.data(NODE_MIME)).decode("utf-8")
            pos = event.position()
            self.add_step(token, at=(pos.x(), pos.y()),
                          connect_from=self.selected())
        except Exception:  # noqa: BLE001 - 编辑期异常绝不冒泡
            return
        event.acceptProposedAction()

    def add_gateway(self, name: str = "判断") -> str:
        """加一个排他网关（分支判断）。"""
        return self.add_node(KIND_EXCLUSIVE, name, stage=None)

    def rename_node(self, node_id: str, name: str) -> None:
        """改节点名（就地换 dataclass：frozen，只能重建）。

        ⚠️ 名字改了要**重算 stage**：阶段是"按名字接回"的，改名后不重算，
        用户把「PDF排版」改成「生成 PDF 之外的东西」时阶段还挂在 ``print``。
        """
        from desktop.steps.bpmn_diagram import stage_of_name

        diagram = self.diagram()
        diagram.nodes = tuple(
            DiagramNode(id=n.id, kind=n.kind, name=name,
                        stage=(stage_of_name(name) if n.kind == KIND_TASK
                               else None))
            if n.id == node_id else n
            for n in diagram.nodes
        )
        self.diagram_changed.emit()
        self.update()

    def rename_flow(self, flow_id: str, label: str) -> None:
        """改连线上的文字（如网关分支的「否」）。"""
        diagram = self.diagram()
        diagram.flows = tuple(
            DiagramFlow(id=f.id, source=f.source, target=f.target, label=label)
            if f.id == flow_id else f
            for f in diagram.flows
        )
        self.diagram_changed.emit()
        self.update()

    def remove_node(self, node_id: str) -> None:
        """删节点：连到它的线一起删（悬空连线会让渲染与解析都出错）。"""
        diagram = self.diagram()
        doomed = [
            f.id for f in diagram.flows
            if f.source == node_id or f.target == node_id
        ]
        # ⚠️ 挂在它身上的**文字注释**也要一起删：节点没了、注释还留着，
        #    会变成一条漂在空白处的孤儿说明（虚线也没地方挂）。
        orphan_notes = [n.id for n in diagram.notes
                        if diagram.note_links.get(n.id) == node_id]
        diagram.nodes = tuple(n for n in diagram.nodes if n.id != node_id)
        diagram.flows = tuple(f for f in diagram.flows if f.id not in doomed)
        diagram.boxes.pop(node_id, None)
        if orphan_notes:
            diagram.notes = tuple(
                n for n in diagram.notes if n.id not in orphan_notes)
            for note_id in orphan_notes:
                diagram.note_links.pop(note_id, None)
                diagram.boxes.pop(note_id, None)
        for flow_id in doomed:
            diagram.waypoints.pop(flow_id, None)
        if self.selected() == node_id:
            self.set_selected(None)
        if self._link_from == node_id:
            self._link_from = None
        self._update_size()
        self.diagram_changed.emit()
        self.update()

    def remove_flow(self, flow_id: str) -> None:
        diagram = self.diagram()
        diagram.flows = tuple(f for f in diagram.flows if f.id != flow_id)
        diagram.waypoints.pop(flow_id, None)
        if self.selected_flow() == flow_id:
            self.set_selected_flow(None)
        self.diagram_changed.emit()
        self.update()

    def remove_selected(self) -> bool:
        """删掉当前选中的（连线优先）。删到了返回 ``True``。

        ⚠️ 节点**成对删**（用户 2026-10-06）：「上传 PDF」与「提取图片」必须
        成对存在，Delete 键与工具栏「删除」是**同一个动作**的两条入口——
        只在 :meth:`ask_delete_selected` 里做联动，键盘删就会漏（表现为
        "按 Delete 删掉提取图片，源 PDF 还在那儿，界面照样催上传 PDF"）。
        联动判据统一走 :func:`ports.paired_node_for_stage`。
        """
        flow_id = self.selected_flow()
        if flow_id:
            self.remove_flow(flow_id)
            return True
        node_id = self.selected()
        if node_id:
            from desktop.steps import ports

            partner_id = ports.paired_node_for_stage(self.diagram(), node_id)
            self.remove_node(node_id)
            if partner_id:
                self.remove_node(partner_id)
            return True
        return False

    def rename_selected(self, name: str) -> bool:
        """给选中的（连线优先）改名。改到了返回 ``True``。"""
        flow_id = self.selected_flow()
        if flow_id:
            self.rename_flow(flow_id, name)
            return True
        node_id = self.selected()
        if node_id:
            self.rename_node(node_id, name)
            return True
        return False

    def connect(self, source: str, target: str, label: str = "") -> str | None:
        """连一条边；自连/重复/悬空都拒绝（返回 ``None``）。"""
        if source == target:
            return None
        diagram = self.diagram()
        if diagram.node(source) is None or diagram.node(target) is None:
            return None
        if any(f.source == source and f.target == target for f in diagram.flows):
            return None
        used = {f.id for f in diagram.flows}
        index = len(used) + 1
        flow_id = f"Flow_{index}"
        while flow_id in used:
            index += 1
            flow_id = f"Flow_{index}"
        diagram.flows = diagram.flows + (
            DiagramFlow(id=flow_id, source=source, target=target, label=label),
        )
        # ⚠️ 折点**不要**现在算：位置可能还要变，渲染时按坐标现算更准
        #    （文件里存的是"这一刻"的折点，拖动后会过时）。
        self.diagram_changed.emit()
        self.update()
        return flow_id

    # ------------------------------------------------------------ 找空位
    def _free_slot(self, kind: str = KIND_TASK
                   ) -> tuple[float, float, float, float]:
        """给新节点找个**不压住别人**的位置。

        锚点优先取当前选中的节点（"在我选中的后面加一步"最符合直觉），
        没有选中就用最右边那个。先往右试，压住了就往下挪。
        """
        diagram = self.diagram()
        width, height = default_size(kind)
        boxes = [
            diagram.node_box(n.id) for n in diagram.nodes if n.id in diagram.boxes
        ]
        if not boxes:
            return (60.0, 60.0, width, height)
        anchor = self.selected()
        if anchor and anchor in diagram.boxes:
            ax, ay, aw, _ah = diagram.node_box(anchor)
        else:
            ax, ay, aw, _ah = max(boxes, key=lambda b: b[0] + b[2])

        def overlaps(x, y) -> bool:
            for bx, by, bw, bh in boxes:
                if (x < bx + bw + 8 and bx < x + width + 8
                        and y < by + bh + 8 and by < y + height + 8):
                    return True
            return False

        x = ax + aw + NEW_NODE_GAP
        y = ay
        for step in range(PLACE_TRIES):
            if not overlaps(x, y):
                break
            # 先往下、再往右（保证"在同一条链上往下排"的观感）
            if step % 2 == 0:
                y += height + NEW_NODE_GAP
            else:
                x += width + NEW_NODE_GAP
        return (float(x), float(y), float(width), float(height))

    # ------------------------------------------------------------ 落盘
    def save_to(self, path: Path | str) -> Path:
        """把当前图写回 ``.bpmn`` 文件（原子写）。"""
        return self.diagram().save(path)

    # ------------------------------------------------------------ 命中
    def _handle_at(self, point: QPointF) -> str | None:
        """点是否落在某节点右缘的**连线热点**上。"""
        for item in reversed(self.diagram().nodes):
            rect = self.rect_of(item.id)
            center_x = rect.right()
            center_y = rect.center().y()
            dx = point.x() - center_x
            dy = point.y() - center_y
            if dx * dx + dy * dy <= HANDLE_HIT * HANDLE_HIT:
                return item.id
        return None

    def flow_at(self, point: QPointF) -> str | None:
        """点是否落在某条**连线**上（返回最近的那条）。"""
        best: str | None = None
        best_distance = EDGE_HIT
        for flow in self.diagram().flows:
            points = self._points(flow)
            for start, end in zip(points, points[1:]):
                distance = _distance_to_segment(point, start, end)
                if distance < best_distance:
                    best_distance = distance
                    best = flow.id
        return best

    # ------------------------------------------------------------ 鼠标
    def mousePressEvent(self, event) -> None:  # noqa: N802
        try:
            self._on_press(event)
        except Exception:  # noqa: BLE001 - 编辑期异常绝不能冒泡（会丢用户的图）
            pass

    def _on_press(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        self.setFocus(Qt.MouseFocusReason)
        point = QPointF(event.position())
        self._press_pos = QPointF(point)
        self._moved = False
        node_id = self.node_at(point)

        # ① 连线模式：点起点 → 点终点 → 连上并退出模式
        if self._link_mode:
            if node_id is None:
                return
            if self._link_from is None:
                self._link_from = node_id
                self.set_selected_flow(None)
                self.set_selected(node_id)
                self.update()
                return
            source, self._link_from = self._link_from, None
            if node_id != source:
                self.connect(source, node_id)
                self.set_link_mode(False)
            self.update()
            return

        # ② 右缘热点：按住拖到目标节点（老手势，保留）
        handle = self._handle_at(point)
        if handle is not None:
            self._link_from = handle
            self._link_pos = QPointF(point)
            return

        # ③ 点空白：先看有没有点中连线（连线的可点范围比节点小，放后面判）
        if node_id is None:
            flow_id = self.flow_at(point)
            self.set_selected(None)
            self.set_selected_flow(flow_id)
            return

        # ④ 点节点：选中 + 准备拖拽
        self.set_selected_flow(None)
        self.set_selected(node_id)
        rect = self.rect_of(node_id)
        self._drag_id = node_id
        self._drag_offset = QPointF(point.x() - rect.left(),
                                    point.y() - rect.top())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        try:
            self._on_move(event)
        except Exception:  # noqa: BLE001
            pass

    def _on_move(self, event) -> None:
        point = QPointF(event.position())
        if self._link_from is not None:
            # 连线中：只更新橡皮筋终点
            self._link_pos = QPointF(point)
            self.update()
            return
        if self._drag_id is None:
            super().mouseMoveEvent(event)  # 悬停高亮
            return
        if self._press_pos is not None and not self._moved:
            dx = point.x() - self._press_pos.x()
            dy = point.y() - self._press_pos.y()
            if dx * dx + dy * dy < DRAG_THRESHOLD * DRAG_THRESHOLD:
                return
            self._moved = True
        self._move_node(point)

    def _move_node(self, point: QPointF) -> None:
        """把拖拽中的节点挪到鼠标位置（限制在画布内）。"""
        node_id = self._drag_id
        if node_id is None:
            return
        diagram = self.diagram()
        box = diagram.node_box(node_id)
        x = point.x() - self._drag_offset.x()
        y = point.y() - self._drag_offset.y()
        # 夹在留白之内，别拖到负坐标（会被当作"图外"看不见）
        x = max(x, 4.0)
        y = max(y, 4.0)
        diagram.boxes[node_id] = (float(x), float(y), box[2], box[3])
        # ⚠️ 折点要**清掉重算**：文件里存的旧折点指向老位置，不清的话线会
        #    歪（拖完保存再打开，线的拐点还停在原地）。
        for flow in diagram.flows:
            if flow.source == node_id or flow.target == node_id:
                diagram.waypoints.pop(flow.id, None)
        self._update_size()
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        try:
            self._on_release(event)
        except Exception:  # noqa: BLE001
            pass

    def _on_release(self, event) -> None:
        if self._link_from is not None and not self._link_mode:
            source = self._link_from
            self._link_from = None
            self._link_pos = None
            target = self.node_at(event.position())
            if target is not None:
                self.connect(source, target)
            self.update()
            return
        if self._drag_id is not None:
            moved = self._moved
            self._drag_id = None
            self._press_pos = None
            if moved:
                self.diagram_changed.emit()
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """双击节点 = 改名（最顺手的入口）。"""
        try:
            node_id = self.node_at(event.position())
            if node_id is None:
                return
            self.set_selected_flow(None)
            self.set_selected(node_id)
            self.ask_rename_selected()
        except Exception:  # noqa: BLE001
            pass

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            try:
                self.ask_delete_selected()
            except Exception:  # noqa: BLE001
                pass
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        from PySide6.QtGui import QPainter

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for item in self.diagram().nodes:
            rect = self.rect_of(item.id)
            center = QPointF(rect.right(), rect.center().y())
            chosen = item.id == self.selected()
            if not chosen:
                painter.setBrush(QColor(T.ACCENT))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(center, HANDLE_RADIUS / 2, HANDLE_RADIUS / 2)
            else:
                # 选中的节点：热点画大一圈并加白心，暗示"这里可以拖出连线"
                painter.setBrush(QColor(T.SURFACE))
                painter.setPen(QPen(QColor(T.ACCENT), 2.0))
                painter.drawEllipse(center, HANDLE_RADIUS * 0.75,
                                    HANDLE_RADIUS * 0.75)
        # 连线待连节点高亮
        if self._link_from is not None:
            rect = self.rect_of(self._link_from)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(T.ACCENT), 2.0, Qt.DashLine))
            painter.drawRect(rect.adjusted(-3, -3, 3, 3))
        if self._link_from and self._link_pos:
            rect = self.rect_of(self._link_from)
            start = QPointF(rect.right(), rect.center().y())
            painter.setPen(QPen(QColor(T.ACCENT), 1.8, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(start, self._link_pos)

    # ------------------------------------------------------------ 对话框动作
    def ask_add_node(self) -> None:
        """加一个**能被运行时认出来**的步骤（从已知阶段里选）。

        ⚠️ 不让用户直接敲名字：随手打的"新步骤"接不上任何阶段（
        :func:`stage_of_name` 认不出），加进去也**不参与运行**——用户会以为
        加了没生效。所以列出现有阶段让他选，名字自动就是阶段的中文名。
        """
        options = _stage_options()
        choice, confirmed = QInputDialog.getItem(
            self, "添加步骤", "选择步骤（名称即为运行阶段）：", options, 0, False
        )
        if not confirmed:
            return
        if choice == options[-1]:
            name, typed = QInputDialog.getText(self, "添加步骤", "节点名称：")
            if typed and name.strip():
                self.add_node(KIND_TASK, name.strip())
            return
        self.add_node(KIND_TASK, choice)

    def ask_rename_selected(self) -> None:
        """给选中的（连线优先）改名。"""
        flow_id = self.selected_flow()
        if flow_id:
            flow = next((f for f in self.diagram().flows if f.id == flow_id), None)
            label, confirmed = QInputDialog.getText(
                self, "连线文字", "这条线上写什么（如网关分支的「否」）：",
                text=flow.label if flow else "")
            if confirmed:
                self.rename_selected(label.strip())
            return
        node_id = self.selected()
        if not node_id:
            return
        item = self.diagram().node(node_id)
        name, confirmed = QInputDialog.getText(
            self, "重命名节点", "节点名称（改成阶段名即可参与运行）：",
            text=item.name if item else "")
        if confirmed and name.strip():
            self.rename_selected(name.strip())

    def ask_delete_selected(self) -> None:
        flow_id = self.selected_flow()
        if flow_id:
            flow = next((f for f in self.diagram().flows if f.id == flow_id), None)
            source = self.diagram().node(flow.source) if flow else None
            target = self.diagram().node(flow.target) if flow else None
            label = (f"{source.name if source else '?'} → "
                     f"{target.name if target else '?'}")
            answer = QMessageBox.question(
                self, "删除连线", f"确定删除连线「{label}」？")
            if answer == QMessageBox.StandardButton.Yes:
                self.remove_flow(flow_id)
            return
        node_id = self.selected()
        if not node_id:
            return
        item = self.diagram().node(node_id)
        label = item.name if item else node_id
        # ⚠️ **成对删除**（用户2026-10-06）：「上传 PDF」与「提取图片」是一对，
        #   删掉任一个，另一个就**没有意义**（留着 startEvent 图上有个入口却
        #    不产出图片；留着 extract 则界面那个 PDF 图标会一直催你上传）。
        #    判据在 :func:`ports.paired_node_for_stage`，**不在这里写死**
        #    "extract↔startEvent"——那是对��模型的声明，不是编辑器的事。
        from desktop.steps import ports

        partner_id = ports.paired_node_for_stage(self.diagram(), node_id)
        partner = (self.diagram().node(partner_id) if partner_id else None)
        if partner is not None:
            answer = QMessageBox.question(
                self, "删除节点",
                f"确定删除「{label}」？\n\n"
                f"「{partner.name}」是它的**配套节点**（上传 PDF 与提取图片"
                f"必须成对存在），会**一起删除**。")
        else:
            answer = QMessageBox.question(
                self, "删除节点",
                f"确定删除「{label}」？连到它的连线会一起删除。")
        if answer == QMessageBox.StandardButton.Yes:
            self.remove_node(node_id)
            # ⚠️ **配对节点跟着删**（正反两向都走这里，所以删哪个都成对消失）。
            #    用``remove_node`` 而不是直接改 diagram：它会连带清掉挂在这
            #    个节点上的连线、坐标、注释——漏一处就留下一堆悬空引用。
            if partner_id:
                self.remove_node(partner_id)


def _stage_options() -> list[str]:
    """可选步骤名（= 现有阶段的中文名）+ 一个"自己起名"兜底项。"""
    from desktop.steps import ports

    labels = [ports.stage_label(stage) for stage in ports.STAGE_STEPS]
    return labels + ["其他（自定义名称）"]


__all__ = ["BpmnEditor", "EDGE_HIT", "HANDLE_HIT", "HANDLE_RADIUS"]
