# -*- coding: utf-8 -*-
"""BPMN 编辑控件的**命中测试 + 鼠标/键盘交互 + 连接点绘制**
（``_InteractionMixin``）。

Mixin 只在运行期与 ``BpmnEditor`` 组合（``class BpmnEditor(_DialogMixin,
_InteractionMixin, BpmnView)``）；宿主面见 :mod:`._host`，本模块**不 import**
主类 ``editor``，避免循环导入。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from desktop.components.bpmn_editor._qt import (
    QColor,
    QPainter,
    QPen,
    QPointF,
    Qt,
)

from desktop.components.bpmn_editor.constants import (
    DRAG_THRESHOLD,
    EDGE_HIT,
    PORT_HIT,
    PORT_RADIUS,
    _distance_to_segment,
)
from desktop.ui import theme as T

if TYPE_CHECKING:
    from desktop.components.bpmn_editor._host import BpmnEditorHost as _Host
else:
    _Host = object


class _InteractionMixin(_Host):
    """鼠标/键盘交互与连接点绘制；宿主面见 TYPE_CHECKING。"""

    # ------------------------------------------------------------ 命中
    def _ports_of(self, node_id: str) -> list[tuple[str, QPointF]]:
        """节点的**四个中线连接点**（上/右/下/左边中点，返回 ``(方向, 点)``）。"""
        rect = self.rect_of(node_id)
        center = rect.center()
        return [
            ("top", QPointF(center.x(), rect.top())),
            ("right", QPointF(rect.right(), center.y())),
            ("bottom", QPointF(center.x(), rect.bottom())),
            ("left", QPointF(rect.left(), center.y())),
        ]

    def _port_at(self, point: QPointF) -> tuple[str, str] | None:
        """点落在哪个节点的**中线连接点**上（返回 ``(节点id, 方向)``）。

        ⚠️ 从后往前找（后画的在上层，与 :meth:`BpmnView.node_at` 同一口径）。
        """
        for item in reversed(self.diagram().nodes):
            for side, center in self._ports_of(item.id):
                dx = point.x() - center.x()
                dy = point.y() - center.y()
                if dx * dx + dy * dy <= PORT_HIT * PORT_HIT:
                    return (item.id, side)
        return None

    def _nearest_port(self, node_id: str, point: QPointF) -> QPointF:
        """离 ``point`` 最近的那个连接点（橡皮筋从它出发——起点也自动匹配）。"""
        best = QPointF(point)
        best_distance = float("inf")
        for _side, center in self._ports_of(node_id):
            dx = point.x() - center.x()
            dy = point.y() - center.y()
            distance = dx * dx + dy * dy
            if distance < best_distance:
                best_distance = distance
                best = QPointF(center)
        return best

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
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
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

        # ② 中线连接点：按住往目标节点拖（四个方向的点，松手即连上）
        port = self._port_at(point)
        if port is not None:
            self._link_from = port[0]
            self._link_pos = QPointF(point)
            return

        # ③ 点空白：先看有没有点中**注释**，再看连线（连线的可点范围比节点小，
        #    放后面判）。⚠️ 顺序是"节点 → 注释 → 连线"：与绘制层次一致
        #    （节点实底盖住注释，注释又盖住连线），点到的总是看得见的那一个。
        if node_id is None:
            note_id = self.note_at(point)
            if note_id is not None:
                self.set_selected(None)
                self.set_selected_flow(None)
                rect = self.note_rect_of(note_id)
                self._drag_note = note_id
                self._drag_note_offset = QPointF(point.x() - rect.left(),
                                                 point.y() - rect.top())
                return
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
        if self._drag_note is not None:
            if self._passes_threshold(point):
                self._move_note(point)
            return
        if self._drag_id is None:
            super().mouseMoveEvent(event)  # 悬停高亮
            # 悬停在连接点上换十字光标——提示"这里能拖出连线"；
            # 悬停在**注释**上换四向箭头——提示"这个能拖走"
            if self._port_at(point) is not None:
                self.setCursor(Qt.CursorShape.CrossCursor)
            elif self.note_at(point) is not None:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            return
        if self._passes_threshold(point):
            self._move_node(point)

    def _passes_threshold(self, point: QPointF) -> bool:
        """这次移动算不算"拖动"（低于 :data:`DRAG_THRESHOLD` 仍算点击）。

        ⚠️ 阈值只判一次（``_moved`` 一旦为真就不再回头）：拖动过程中鼠标
        抖动回到起点附近，也不该被当成"没拖过"。
        """
        if self._moved:
            return True
        if self._press_pos is None:
            self._moved = True
            return True
        dx = point.x() - self._press_pos.x()
        dy = point.y() - self._press_pos.y()
        if dx * dx + dy * dy < DRAG_THRESHOLD * DRAG_THRESHOLD:
            return False
        self._moved = True
        return True

    def _move_node(self, point: QPointF) -> None:
        """把拖拽中的节点挪到鼠标位置（限制在画布内）。"""
        node_id = self._drag_id
        if node_id is None:
            return
        diagram = self.diagram()
        box = diagram.node_box(node_id)
        # ⚠️ **必须减掉画布偏移**（``_offset()``）：鼠标点与 ``_drag_offset``
        #    都是**视图坐标**，而 ``boxes`` 存的是**文件坐标**。不减这一下，
        #    写回去的坐标就带上了画布偏移（默认模板约 126px）——现象是
        #    "鼠标一动，节点先朝左上飞一截再跟着走"（2026-10-08 实测）。
        #    减掉之后视图位置严格等于"按下时的位置 + 鼠标位移"，与偏移无关。
        ox, oy = self._offset()
        x = point.x() - self._drag_offset.x() - ox
        y = point.y() - self._drag_offset.y() - oy
        # 夹在留白之内，别拖到负坐标（会被当作"图外"看不见）
        x = max(x, 4.0)
        y = max(y, 4.0)
        diagram.boxes[node_id] = (float(x), float(y), box[2], box[3])
        # ⚠️ 挂在它身上的**注释跟着走**（用户 2026-10-08）：注释是写在节点旁的
        #    说明，节点挪了而注释留在原地，虚线就会横穿整张图、还压在别的节点上。
        #    平移同样的量（而不是"重新挂到正下方"）——用户自己摆的位置得留住。
        self._shift_notes(node_id, x - box[0], y - box[1])
        # ⚠️ 拖动中**冻结连接点**（用户 2026-10-06）：按拖动开始那一刻的
        #    连接点现算折点，线跟着节点平滑移动。要是每帧都自动换边，节点
        #    一过中线线就猛跳一大截，微调根本没法看。松手才清掉重匹配
        #    （:meth:`_finish_drag`）。
        for flow in diagram.flows:
            if flow.source == node_id or flow.target == node_id:
                anchor = self._drag_sides.get(flow.id)
                if anchor is None:
                    anchor = diagram.route_anchor(flow)
                    self._drag_sides[flow.id] = anchor
                diagram.waypoints[flow.id] = diagram.route_sides(flow, anchor)
        self._update_size()
        self.update()

    def _shift_notes(self, node_id: str, dx: float, dy: float) -> None:
        """把挂在 ``node_id`` 上的注释**平移同样的量**（相对位置保持不变）。

        ⚠️ 增量式（每次按当前坐标算差值）而不是"记住拖动起点一次性挪"：
        ``_move_node`` 是逐帧调的，增量写法不需要额外的拖动起始快照，
        也就不会在拖动被打断时留下对不上的偏移。
        """
        if dx == 0.0 and dy == 0.0:
            return
        diagram = self.diagram()
        for note in diagram.notes_of(node_id):
            box = diagram.boxes.get(note.id)
            if box is None:  # 没坐标的注释（文件缺 DI 段）不硬塞一个位置
                continue
            diagram.boxes[note.id] = (box[0] + dx, box[1] + dy, box[2], box[3])

    def _move_note(self, point: QPointF) -> None:
        """把拖拽中的**注释**挪到鼠标位置（同样夹在留白之内）。

        ⚠️ 只改坐标，**不动挂接关系**（``note_links``）：拖注释是排版，
        不是"改挂到别的节点上"——虚线依旧连回原来那个节点，只是起点跟着
        注释的新位置重新算（``BpmnView._anchor_point`` 每次绘制现算）。
        """
        note_id = self._drag_note
        if note_id is None:
            return
        diagram = self.diagram()
        box = diagram.note_box(note_id)
        # ⚠️ 与 :meth:`_move_node` 同一条：视图坐标 → 文件坐标要减掉画布偏移
        ox, oy = self._offset()
        x = max(point.x() - self._drag_note_offset.x() - ox, 4.0)
        y = max(point.y() - self._drag_note_offset.y() - oy, 4.0)
        diagram.boxes[note_id] = (float(x), float(y), box[2], box[3])
        self._update_size()
        self.update()

    def _finish_drag(self) -> None:
        """收尾一次拖动：清掉冻结的连接点与临时折点（连线重新自动匹配）。"""
        diagram = self.diagram()
        for flow_id in self._drag_sides:
            diagram.waypoints.pop(flow_id, None)
        self._drag_sides.clear()

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
        if self._drag_note is not None:
            # 拖注释：坐标在 :meth:`_move_note` 里已经改完了，这里只收尾。
            # ⚠️ 只有真拖动过（越过阈值）才算"图被改动"，否则点一下就标脏。
            moved = self._moved
            self._drag_note = None
            self._press_pos = None
            if moved:
                self.diagram_changed.emit()
            self.update()
            return
        if self._drag_id is not None:
            moved = self._moved
            self._drag_id = None
            self._press_pos = None
            self._finish_drag()
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
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            try:
                self.ask_delete_selected()
            except Exception:  # noqa: BLE001
                pass
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # 悬停/选中的节点显示**四个中线连接点**（连线中的起点节点画大加白心）
        show_ports = {nid for nid in (self.selected(), self._hovered) if nid}
        if self._link_from is not None:
            show_ports.add(self._link_from)
        for item in self.diagram().nodes:
            if item.id not in show_ports:
                continue
            active = item.id == self._link_from
            for _side, center in self._ports_of(item.id):
                if active:
                    painter.setBrush(QColor(T.SURFACE))
                    painter.setPen(QPen(QColor(T.ACCENT), 2.0))
                    radius = PORT_RADIUS * 1.6
                else:
                    painter.setBrush(QColor(T.ACCENT))
                    painter.setPen(Qt.PenStyle.NoPen)
                    radius = PORT_RADIUS
                painter.drawEllipse(center, radius, radius)
        # 连线待连节点高亮
        if self._link_from is not None:
            rect = self.rect_of(self._link_from)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(T.ACCENT), 2.0, Qt.PenStyle.DashLine))
            painter.drawRect(rect.adjusted(-3, -3, 3, 3))
        if self._link_from and self._link_pos:
            # 橡皮筋：从起点节点**离鼠标最近的连接点**出发（起点也自动匹配），
            # 压着的目标节点加虚线框——落点在哪一眼可见
            start = self._nearest_port(self._link_from, self._link_pos)
            painter.setPen(QPen(QColor(T.ACCENT), 1.8, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(start, self._link_pos)
            target = self.node_at(self._link_pos)
            if target is not None and target != self._link_from:
                painter.setPen(QPen(QColor(T.ACCENT), 2.0, Qt.PenStyle.DashLine))
                painter.drawRect(self.rect_of(target).adjusted(-3, -3, 3, 3))


__all__ = ["_InteractionMixin"]
