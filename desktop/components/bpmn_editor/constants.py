# -*- coding: utf-8 -*-
"""BPMN 编辑控件的共享常量与几何辅助（见 :mod:`desktop.components.bpmn_editor`）。"""

from __future__ import annotations

from desktop.components.bpmn_editor._qt import QPointF

#: 中线连接点的绘制半径（上下左右四个，悬停/选中时显示）
PORT_RADIUS = 5.0
#: 连接点的命中半径（比画出来的大一圈，否则 5px 的圆基本点不到——实测教训）
PORT_HIT = 14.0
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
