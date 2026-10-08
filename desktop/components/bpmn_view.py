# -*- coding: utf-8 -*-
"""BPMN 流程图**渲染控件**：照着 :class:`FlowDiagram` 画出标准的 BPMN 图形。

## 与旧 ``flow_view.FlowView`` 的关系

``FlowView`` 画的是**运行语义模型**（``FlowDefinition``：阶段序列 + 端口边），
坐标自己算、图形只有"矩形 + 圆"两种。它服务于「步骤条/流程示意」那套旧口径。

本控件画的是**文件本身**（``FlowDiagram``：节点类型 + DI 坐标 + 折点），
所以：用 bpmn.io 画的图，进这里长得**一模一样**——网关是菱形、结束事件是
双圈、连线走文件里存的折点。

两者并存不冲突：旧页面继续用 ``FlowView``（自测覆盖着），新入口用本控件。

## 图形规格（对齐 BPMN 2.0 惯例）

===================  =========================================
``startEvent``       细边圆
``endEvent``         粗边双圈
``…Gateway``         菱形（排他画 ✕、并行画 ＋）
``task``             圆角矩形
其余未知类型          圆角矩形（保底显示，不崩）
===================  =========================================

⚠️ 控件**只读渲染**（编辑在 :class:`~desktop.components.bpmn_editor.BpmnEditor`）。
⚠️ 绘制期**不对 QPointF 做 sip 运算**（PySide6 6.11 会 access violation，
   见 ``flow_view`` 里同款注释）——全程只用 ``x()``/``y()``。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QPainter, QPolygonF, QPen)
from PySide6.QtWidgets import QSizePolicy, QWidget

from desktop.steps.bpmn_diagram import (
    KIND_END, KIND_EXCLUSIVE, KIND_PARALLEL, KIND_START, DiagramFlow,
    DiagramNode, DiagramNote, FlowDiagram,
)
from desktop.ui import theme as T

#: 节点矩形圆角（任务框）
CORNER = 10.0
#: 箭头尺寸
ARROW = 9.0
#: 线宽
EDGE_WIDTH = 1.6
#: 事件圆的粗细（结束事件是双圈）
EVENT_BORDER = 1.6
END_EVENT_BORDER = 3.0
#: 名称文字与图形之间的间距
LABEL_GAP = 5.0
#: 连线**选中**时的线宽（比常态粗一圈，一眼能看出选的是哪条）
SELECTED_EDGE_WIDTH = 3.4

EDGE_COLOR = "#9AA2AE"
INK = "#1F2328"
FAINT = "#6B7280"
GATEWAY_COLOR = "#0F6CBD"
#: 文字注释的括号色（比正文淡，别抢节点）
NOTE_COLOR = "#98A2B3"


class BpmnView(QWidget):
    """只读的 BPMN 流程图视图（按文件坐标渲染）。

    坐标直接用 ``dc:Bounds`` 的用户单位（1 单位 ≈ 1px），不缩放——与 bpmn.io
    一致，用户在哪画的、这里就在哪显示。
    """

    #: 点到节点上（弹窗可据此显示详情）
    node_clicked = Signal(str)

    def __init__(self, diagram: FlowDiagram | None = None, parent=None):
        super().__init__(parent)
        self._diagram = diagram or FlowDiagram()
        self._selected: str | None = None
        #: 选中的**连线** id（节点与连线是两套选中，互斥，见各 set_selected*）
        self._selected_flow: str | None = None
        self._hovered: str | None = None
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.setMouseTracking(True)
        self._update_size()

    # ------------------------------------------------------------ 数据
    def set_diagram(self, diagram: FlowDiagram) -> None:
        """换图（新图坐标来自它自己的文件，不沿用旧坐标）。"""
        self._diagram = diagram
        self._selected = None
        self._selected_flow = None
        self._hovered = None
        self._update_size()
        self.update()

    def diagram(self) -> FlowDiagram:
        return self._diagram

    def set_selected(self, node_id: str | None) -> None:
        if node_id != self._selected:
            self._selected = node_id
            self.update()

    def selected(self) -> str | None:
        return self._selected

    def set_selected_flow(self, flow_id: str | None) -> None:
        """选中一条**连线**（与选中节点互斥：调用方负责清另一边）。"""
        if flow_id != self._selected_flow:
            self._selected_flow = flow_id
            self.update()

    def selected_flow(self) -> str | None:
        return self._selected_flow

    # ------------------------------------------------------------ 尺寸
    def _sized_ids(self) -> list[str]:
        """参与包围盒计算的 id：节点 + **注释框**（注释也算内容）。

        ⚠️ 别漏注释：它们常挂在节点外侧，只按节点算偏移会把注释推出画布
        ——现象是"注释看不见"，而模型里明明有。
        """
        return [n.id for n in self._diagram.nodes] + [
            n.id for n in self._diagram.notes
        ]

    def _offset(self) -> tuple[float, float]:
        """内容左上角的负偏移（把包围盒挪到 (PADDING, PADDING)）。"""
        ids = [i for i in self._sized_ids() if i in self._diagram.boxes]
        if not ids:
            return 0.0, 0.0
        left = min(self._diagram.boxes[i][0] for i in ids)
        top = min(self._diagram.boxes[i][1] for i in ids)
        pad = 24.0
        return pad - left, pad - top

    def _update_size(self) -> None:
        width, height = self.content_size()
        # ⚠️ 尺寸策略 Minimum/Fixed + 显式 resize（与 flow_view 同一套理由）：
        # 只设 policy 父容器不会替我们收尺寸；只 resize 又会被父布局按
        # sizeHint 重新分配。三件套一起做才稳定。
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setMinimumSize(1, 1)
        self.setMaximumSize(int(width), int(height))
        if self.width() != int(width) or self.height() != int(height):
            self.resize(int(width), int(height))
        self.update()

    def content_size(self) -> tuple[float, float]:
        """内容尺寸（含留白）：包围盒的宽高（**节点 + 注释框**）。"""
        ids = [i for i in self._sized_ids() if i in self._diagram.boxes]
        if not ids:
            return 48.0, 48.0
        left = min(self._diagram.boxes[i][0] for i in ids)
        top = min(self._diagram.boxes[i][1] for i in ids)
        right = max(self._diagram.boxes[i][0] + self._diagram.boxes[i][2]
                    for i in ids)
        bottom = max(self._diagram.boxes[i][1] + self._diagram.boxes[i][3]
                     for i in ids)
        # 边上的标签、网关上方的名字、注释框外侧的文字可能超出，多留一点
        pad = 24.0 + LABEL_GAP * 4
        return (right - left + pad * 2, bottom - top + pad * 2)

    def sizeHint(self):  # noqa: N802
        from PySide6.QtCore import QSize

        width, height = self.content_size()
        return QSize(int(width), int(height))

    def minimumSizeHint(self):  # noqa: N802
        return self.sizeHint()

    # ------------------------------------------------------------ 命中
    def rect_of(self, node_id: str) -> QRectF:
        """节点的绘制矩形（文件坐标 + 偏移）。"""
        x, y, w, h = self._diagram.node_box(node_id)
        ox, oy = self._offset()
        return QRectF(x + ox, y + oy, w, h)

    def node_at(self, point: QPointF) -> str | None:
        """命中测试：从**后往前**找（后画的在上层，符合视觉直觉）。"""
        for item in reversed(self._diagram.nodes):
            rect = self.rect_of(item.id)
            if item.is_gateway:
                center = rect.center()
                if (abs(point.x() - center.x()) / max(rect.width() / 2, 1)
                        + abs(point.y() - center.y()) / max(rect.height() / 2, 1)
                        <= 1.0):
                    return item.id
            elif rect.contains(point):
                return item.id
        return None

    def note_at(self, point: QPointF) -> str | None:
        """命中测试：点到哪条**文字注释**上（同样从后往前找）。

        与 :meth:`node_at` 的分工：节点画在注释**之上**（见 ``paintEvent`` 的
        绘制顺序），所以调用方要**先问节点、再问注释**——重叠处点到的该是
        看得见的那一个。
        """
        for note in reversed(self._diagram.notes):
            if self.note_rect_of(note.id).contains(point):
                return note.id
        return None

    # ------------------------------------------------------------ 交互
    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hovered = self.node_at(event.position())
        if hovered != self._hovered:
            self._hovered = hovered
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if hovered else Qt.CursorShape.ArrowCursor
            )
            self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        node_id = self.node_at(event.position())
        if node_id:
            self.set_selected(node_id)
            self.node_clicked.emit(node_id)

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(T.SURFACE_SOFT))
        # 先画线、再画注释、最后画节点：节点实底会盖住线头，接缝干净
        for flow in self._diagram.flows:
            self._draw_flow(painter, flow)
        for note in self._diagram.notes:
            self._draw_note(painter, note)
        for item in self._diagram.nodes:
            self._draw_node(painter, item)

    def _points(self, flow: DiagramFlow) -> list[QPointF]:
        """连线的折点（优先用文件里存的，缺了按直角算）。"""
        raw = self._diagram.waypoints.get(flow.id)
        if not raw:
            raw = self._diagram.route(flow)
        ox, oy = self._offset()
        return [QPointF(x + ox, y + oy) for x, y in raw]

    def _draw_flow(self, painter: QPainter, flow: DiagramFlow) -> None:
        points = self._points(flow)
        if len(points) < 2:
            return
        # ⚠️ 选中态在这里判（而不是在子类 paintEvent 里叠画一遍）：叠画会盖在
        #    节点之上，看出"线浮在框上"。走线本身的分支，层次才正确。
        chosen = flow.id == self._selected_flow
        pen = QPen(QColor(T.ACCENT if chosen else EDGE_COLOR),
                   SELECTED_EDGE_WIDTH if chosen else EDGE_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for first, second in zip(points, points[1:]):
            painter.drawLine(first, second)
        self._draw_arrow(painter, points[-2], points[-1],
                         QColor(T.ACCENT if chosen else EDGE_COLOR))
        if flow.label:
            self._draw_edge_label(painter, points, flow.label)

    def _draw_arrow(self, painter: QPainter, before: QPointF, tip: QPointF,
                    color: QColor | None = None) -> None:
        """箭头三角形。

        ⚠️ 必须 ``QPolygonF``（``QPolygon`` 只收 QPoint，传 QPointF 会
        TypeError）；且全程只用 x()/y()，不对 QPointF 做 sip 运算。
        """
        dx, dy = tip.x() - before.x(), tip.y() - before.y()
        length = (dx * dx + dy * dy) ** 0.5
        if length < 1e-6:
            return
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color or QColor(EDGE_COLOR))
        painter.drawPolygon(QPolygonF([
            tip,
            QPointF(tip.x() - ux * ARROW + px * ARROW / 2,
                    tip.y() - uy * ARROW + py * ARROW / 2),
            QPointF(tip.x() - ux * ARROW - px * ARROW / 2,
                    tip.y() - uy * ARROW - py * ARROW / 2),
        ]))

    def _draw_edge_label(self, painter: QPainter, points: list[QPointF],
                         text: str) -> None:
        """边上的文字（如网关分支的「否」）画在**第一条线段**中点上方。

        ⚠️ 不画在所有折点的几何中点：折线可能是"从节点下方绕回来"的形状，
        几何中点会落在图外的空白处（看着像标签飘了）。
        """
        first, second = points[0], points[1]
        mid_x = (first.x() + second.x()) / 2
        mid_y = (first.y() + second.y()) / 2
        font = QFont(self.font())
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QColor(FAINT))
        painter.drawText(QRectF(mid_x - 20, mid_y - 18, 40, 15),
                         Qt.AlignmentFlag.AlignCenter, text)

    def _draw_node(self, painter: QPainter, item: DiagramNode) -> None:
        rect = self.rect_of(item.id)
        if rect.width() <= 0 or rect.height() <= 0:
            return
        selected = item.id == self._selected
        hovered = item.id == self._hovered
        border = QColor(T.ACCENT if (selected or hovered) else _border_of(item))
        width = 2.2 if (selected or hovered) else 1.6
        painter.setPen(QPen(border, width))
        painter.setBrush(QColor(T.SURFACE if hasattr(T, "SURFACE") else "#FFFFFF"))

        if item.kind == KIND_START:
            painter.drawEllipse(rect)
        elif item.kind == KIND_END:
            painter.setPen(QPen(border, END_EVENT_BORDER))
            painter.drawEllipse(rect)
            painter.setPen(QPen(border, EVENT_BORDER))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect.adjusted(4, 4, -4, -4))
        elif item.is_gateway:
            self._draw_gateway(painter, rect, item.kind, border)
        else:
            painter.drawRoundedRect(rect, CORNER, CORNER)

        self._draw_node_label(painter, rect, item)

    def _draw_gateway(self, painter: QPainter, rect: QRectF, kind: str,
                      border: QColor) -> None:
        """菱形网关：中心按类型画符号（排他 ✕ / 并行 ＋）。"""
        center = rect.center()
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(border, 1.6))
        painter.drawPolygon(QPolygonF([
            QPointF(center.x(), rect.top()),
            QPointF(rect.right(), center.y()),
            QPointF(center.x(), rect.bottom()),
            QPointF(rect.left(), center.y()),
        ]))
        span = min(rect.width(), rect.height()) * 0.22
        painter.setPen(QPen(border, 1.8))
        if kind == KIND_PARALLEL:
            painter.drawLine(QPointF(center.x() - span, center.y()),
                             QPointF(center.x() + span, center.y()))
            painter.drawLine(QPointF(center.x(), center.y() - span),
                             QPointF(center.x(), center.y() + span))
        else:  # 排他/包含都画 ✕（包容网关严格说该画 ○，此处按排他画）
            painter.drawLine(QPointF(center.x() - span, center.y() - span),
                             QPointF(center.x() + span, center.y() + span))
            painter.drawLine(QPointF(center.x() - span, center.y() + span),
                             QPointF(center.x() + span, center.y() - span))

    def _draw_node_label(self, painter: QPainter, rect: QRectF,
                         item: DiagramNode) -> None:
        """节点名：网关写在**菱形上方**（里面塞不下），其余写在框内/圆下方。"""
        text = item.name
        if not text:
            return
        font = QFont(self.font())
        font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(QColor(INK))
        if item.is_gateway:
            painter.drawText(
                QRectF(rect.left() - 40, rect.top() - 22, rect.width() + 80, 18),
                Qt.AlignmentFlag.AlignCenter, text)
        elif item.kind in (KIND_START, KIND_END):
            painter.drawText(
                QRectF(rect.left() - 40, rect.bottom() + LABEL_GAP,
                       rect.width() + 80, 18),
                Qt.AlignmentFlag.AlignCenter, text)
        else:
            painter.drawText(rect.adjusted(6, 4, -6, -4),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)


    # ------------------------------------------------------------ 注释
    def note_rect_of(self, note_id: str) -> QRectF:
        """注释框的绘制矩形（文件坐标 + 偏移）。"""
        x, y, w, h = self._diagram.note_box(note_id)
        ox, oy = self._offset()
        return QRectF(x + ox, y + oy, w, h)

    def _draw_note(self, painter: QPainter, note: DiagramNote) -> None:
        """画一条文字注释（BPMN ``textAnnotation``）。

        形制同 bpmn.io：**左侧一个开口方括号** + 右侧多行文字，再用一条
        **虚线挂接**到被说明的节点。文字是作者写在图上的话，必须能读全，
        所以按框宽自动换行（不截断）。
        """
        rect = self.note_rect_of(note.id)
        if rect.width() <= 0 or rect.height() <= 0:
            return
        host = self._diagram.note_links.get(note.id)
        if host and self._diagram.node(host) is not None:
            painter.setPen(QPen(QColor(NOTE_COLOR), 1.2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # 挂接线**斜着连到左侧括号**（不是注释框中心）：括号才是注释的
            # "接头"，连中心会让线扎进文字、左边的括号像悬空断开的（用户
            # 2026-10-07）。直线允许倾斜——与「用户上传PDF」那种斜挂一致。
            painter.drawLine(self._anchor_point(host, rect),
                             QPointF(rect.left(), rect.center().y()))
        painter.setPen(QPen(QColor(NOTE_COLOR), 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        bracket = min(12.0, rect.width() * 0.3)
        top, bottom = rect.top(), rect.bottom()
        painter.drawLine(QPointF(rect.left(), top),
                         QPointF(rect.left() + bracket, top))
        painter.drawLine(QPointF(rect.left(), top),
                         QPointF(rect.left(), bottom))
        painter.drawLine(QPointF(rect.left(), bottom),
                         QPointF(rect.left() + bracket, bottom))
        if note.text:
            font = QFont(self.font())
            font.setPointSize(9)
            painter.setFont(font)
            painter.setPen(QColor(FAINT))
            painter.drawText(
                rect.adjusted(bracket + 4, 2, -4, -2),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
                note.text,
            )

    def _edge_anchor_points(self, node_id: str) -> list[QPointF]:
        """所有**流程连线**接到这个节点上的点（入口 + 出口）。

        注释挂接线要跟它们**错开**——实线和虚线从同一个点出发，看起来
        像一根线分了叉（用户 2026-10-07）。优先取**画出来的**折点
        （拖动中的临时折点也算），拖动时挂接线跟着实时让开。
        """
        points: list[QPointF] = []
        diagram = self._diagram
        ox, oy = self._offset()
        for flow in diagram.flows:
            raw = diagram.waypoints.get(flow.id) or diagram.route(flow)
            if flow.source == node_id:
                points.append(QPointF(raw[0][0] + ox, raw[0][1] + oy))
            if flow.target == node_id:
                points.append(QPointF(raw[-1][0] + ox, raw[-1][1] + oy))
        return points

    def _anchor_point(self, node_id: str, rect: QRectF) -> QPointF:
        """虚线从**节点框离注释最近的那条边**出发（不是节点中心）。

        从中心出发的线会穿过节点本体，看着像把节点划了一刀。
        ⚠️ 还要**避开流程连线的出入口**（:meth:`_edge_anchor_points`）：
        中点被占就沿这条边滑到四分点，再不行滑到 3/8 处。
        """
        box = self.rect_of(node_id)
        cx, cy = box.center().x(), box.center().y()
        tx, ty = rect.center().x(), rect.center().y()
        occupied = self._edge_anchor_points(node_id)

        def free(point: QPointF) -> bool:
            return not any(abs(point.x() - q.x()) < 2.0
                           and abs(point.y() - q.y()) < 2.0
                           for q in occupied)

        # 往注释那一侧先让（让出来的点离注释近，线不回头）
        sign = 1.0 if ty >= cy else -1.0
        if abs(tx - cx) >= abs(ty - cy):
            x = box.right() if tx > cx else box.left()
            span = box.height() / 2
            for part in (0.0, 0.5, -0.5, 0.75, -0.75):
                point = QPointF(x, cy + sign * part * span)
                if free(point):
                    return point
            return QPointF(x, cy)
        y = box.bottom() if ty > cy else box.top()
        span = box.width() / 2
        for part in (0.0, 0.5, -0.5, 0.75, -0.75):
            point = QPointF(cx + sign * part * span, y)
            if free(point):
                return point
        return QPointF(cx, y)


def _border_of(item: DiagramNode) -> str:
    """节点边框色：网关用主题蓝，其余用墨色（与 bpmn.io 观感接近）。"""
    return GATEWAY_COLOR if item.is_gateway else INK


__all__ = ["BpmnView"]
