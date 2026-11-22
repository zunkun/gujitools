# -*- coding: utf-8 -*-
"""步骤条的绘制：连接线、绕行线与几何辅助（``_StepBarPaintMixin``）。

Mixin 只在运行期与 ``StepBar`` 组合（``class StepBar(_StepBarPaintMixin, QWidget)``）；
本模块**不 import** 本包 ``StepBar``，避免循环导入。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from desktop.components.step_bar._qt import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPoint,
    QPointF,
    QRectF,
    Qt,
)

from desktop.components.step_bar.constants import _BYPASS_CLEAR, GREEN
from desktop.ui import theme as T

if TYPE_CHECKING:
    from desktop.components.step_bar.widgets import StepItem, _ImpositionNode


def _rounded_polyline(
    points: list[tuple[float, float]], radius: float = 6.0
) -> QPainterPath:
    """带圆角的折线（``points`` 是 **(x, y) float 元组**）。

    ⚠️ 全程用 ``QPainterPath`` 的 float 重载（``moveTo(x, y)``），**不要**换成
    QPointF 对象运算（``corner - prev``、``QPainterPath(QPointF)`` 那套）：
    PySide6 6.11.1 在 paint 派发期间做 QPointF 的 sip 运算会触发 access
    violation（2026-09-30 自测稳定复现，直线 float 版连跑全绿）。拐角圆滑
    用二次贝塞尔的折线逼近（每角 4 个中间点，2px 线宽下肉眼是平滑的）。
    相邻段太短时半径自动收缩（取半段长），不会画出越界的圆角。
    """
    path = QPainterPath()
    path.moveTo(points[0][0], points[0][1])
    for i in range(1, len(points) - 1):
        (px, py), (cx, cy), (nx, ny) = points[i - 1], points[i], points[i + 1]
        vx, vy = cx - px, cy - py
        wx, wy = nx - cx, ny - cy
        len_in = (vx * vx + vy * vy) ** 0.5
        len_out = (wx * wx + wy * wy) ** 0.5
        if len_in < 1 or len_out < 1:
            path.lineTo(cx, cy)
            continue
        r = min(radius, len_in / 2, len_out / 2)
        ax, ay = cx - vx * (r / len_in), cy - vy * (r / len_in)
        bx, by = cx + wx * (r / len_out), cy + wy * (r / len_out)
        for k in range(1, 4):
            t = k / 4
            mt = 1 - t
            path.lineTo(
                mt * mt * ax + 2 * mt * t * cx + t * t * bx,
                mt * mt * ay + 2 * mt * t * cy + t * t * by,
            )
    path.lineTo(points[-1][0], points[-1][1])
    return path


class _StepBarPaintMixin:
    """``StepBar`` 的绘制面（宿主声明见 TYPE_CHECKING，运行期不加载）。"""

    if TYPE_CHECKING:
        buttons: list[StepItem]
        optional_nodes: list[_ImpositionNode]
        optional_afters: list[int]
        _completed: set[int]
        _bar_of_pos: list[int]
        _optional_flow: list[bool]

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        painter.setPen(QPen(QColor(T.BORDER), 1))
        painter.setBrush(QColor(T.SURFACE))
        painter.drawRoundedRect(rect, T.RADIUS_MD, T.RADIUS_MD)
        # 连接线先画（底层）：端点伸进左右节点框内，被节点的实底遮住，
        # 看起来就是"从节点框后面出发"（用户 2026-09-30）。
        self._draw_connectors(painter)
        self._draw_imposition_bypass(painter)
        painter.end()

    def _connector_segments(self) -> list[tuple]:
        """按布局顺序枚举连接段：``(左节点框, 右节点框, 点亮?, 虚线?)``。

        点亮/虚线规则与旧 _Connector 时代一致：
        - 常规段：左侧步骤完成即点亮，永不变虚；
        - 「去底色 → 拼版」与「拼版 → PDF」：**那个拼版节点自己**生效
          （``_optional_flow``）才按常规点亮，未生效一律灰虚线——真实流向走
          节点上方的绕行线；
        - 节点隐藏（area≠1）时前端那格回归普通的「去底色 → PDF」常规段。

        ⚠️ 生效态**按节点**取（B 方案）：两个拼版节点各连各的，一个生效
        不代表另一个生效（用户 2026-10-18）。
        """
        n = len(self.buttons)
        # ⚠️ 把整条流程条摊成**自左向右的序列**（真实步骤 + 各自后面挂着的可选
        #    节点），再逐对相邻元素出段：这样"多个可选节点、甚至同一位置挂多个"
        #    都自然成立，不必为每种排布写一遍 if。
        seq: list[tuple[str, int]] = []   # ("real", 位置) / ("opt", 可选节点序号)
        for order, after in enumerate(self.optional_afters):
            if after < 0 and not self.optional_nodes[order].isHidden():
                seq.append(("opt", order))
        for index in range(n):
            seq.append(("real", index))
            for order, after in enumerate(self.optional_afters):
                if after == index and not self.optional_nodes[order].isHidden():
                    seq.append(("opt", order))
        segments = []
        for k in range(len(seq) - 1):
            left_kind, left_ref = seq[k]
            right_kind, right_ref = seq[k + 1]
            if left_kind == "real":
                # ⚠️ ``_completed`` 存的是**格序**，这里 index 是位置——
                #    可选节点之前两者相等，之后差一段，必须查表（用户 2026-10-06
                #    报"最后一段连接线永远是灰的"）。
                done = self._bar_of_pos[left_ref] in self._completed
                if right_kind == "opt":
                    # 进可选节点那一段：**该节点自己**生效才点亮，否则灰虚线
                    # （真实流向走节点上方的绕行线）。
                    opt_flow = self._optional_flow[right_ref]
                    segments.append(
                        (
                            self.buttons[left_ref].pill,
                            self.optional_nodes[right_ref],
                            opt_flow and done,
                            not opt_flow,
                        )
                    )
                else:
                    segments.append(
                        (
                            self.buttons[left_ref].pill,
                            self.buttons[right_ref].pill,
                            done,
                            False,
                        )
                    )
            else:
                # 从左/上一个可选节点出发：跟**这个**节点的生效态走。
                target = (
                    self.optional_nodes[right_ref]
                    if right_kind == "opt"
                    else self.buttons[right_ref].pill
                )
                opt_flow = self._optional_flow[left_ref]
                segments.append(
                    (self.optional_nodes[left_ref], target, opt_flow, not opt_flow)
                )
        return segments

    def _draw_connectors(self, painter) -> None:
        """把每段连接线画成「左节点中心 → 右节点中心」的整线 + 箭头。

        线端伸进节点框内、被节点 SURFACE 实底遮住（``StepItem.pill`` /
        ``_ImpositionNode.paintEvent`` 都先铺实底）——这就是"连接线从节点
        框后面出发"。箭头钉在右节点框左缘外侧，**始终实线**（虚线笔画会把
        5px 的短箭头裁成断续的小段）。
        """
        for left, right, done, dash in self._connector_segments():
            a = left.mapTo(self, QPoint(left.width() // 2, left.height() // 2))
            b = right.mapTo(self, QPoint(right.width() // 2, right.height() // 2))
            color = QColor(GREEN if done else "#d6d6d6")
            painter.setPen(
                QPen(
                    color,
                    2,
                    Qt.PenStyle.DashLine if dash else Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawLine(QPointF(a.x(), a.y()), QPointF(b.x(), b.y()))
            painter.setPen(
                QPen(
                    color,
                    2,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            tip = b.x() - right.width() // 2 - 2
            arrow = QPainterPath()
            arrow.moveTo(tip - 5, a.y() - 4)
            arrow.lineTo(tip, a.y())
            arrow.lineTo(tip - 5, a.y() + 4)
            painter.drawPath(arrow)

    def _draw_imposition_bypass(self, painter) -> None:
        """「去底色 → PDF排版」绕行线：可选节点在流程里但**未生效**时画。

        此刻第四步实际取的是第三步产物（``print_source_dir``），主线必须在
        节点上方绕过去，否则流程条上「去底色」和「PDF排版」之间没有真实
        连接。颜色规则与普通连接线一致：左侧步骤（去底色）完成即绿。
        拼版支路自己的两条线此时是灰色虚线（见 ``_sync``）。

        ⚠️ **每个可选节点各画一条**（B 方案）：两个「图片拼版」节点各自绕开
        自己那一段，不是只画第一个的；**已生效的那个不画**（它走真实连线）。
        """
        for order in range(len(self.optional_nodes)):
            if self._optional_flow[order]:
                continue
            if self.optional_nodes[order].isHidden():
                continue
            points = self._bypass_points(order)
            if points is None:
                continue
            # ⚠️ ``_completed`` 存的是**格序**，``optional_afters`` 是标**位置**
            #    ——可选节点插在前面时两者会错开，必须查表（同 _connector_segments）。
            done = self._bar_of_pos[self.optional_afters[order]] in self._completed
            color = QColor(GREEN if done else "#d6d6d6")
            painter.setPen(
                QPen(
                    color,
                    2,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(_rounded_polyline(points))
            # 终点箭头：常规连接线有箭头（见 _draw_connectors），绕行线是主流程
            # 的替代连线，**同样必须带箭头**——否则「去底色 → PDF排版」的绿线
            # 看着像断在半路（用户 2026-11-02）。位置与常规连接线的箭头一致，
            # 用来盖住拼版那条灰色虚线的箭头。
            tip_x, tip_y = points[-1]
            arrow = QPainterPath()
            arrow.moveTo(tip_x - 5, tip_y - 4)
            arrow.lineTo(tip_x, tip_y)
            arrow.lineTo(tip_x - 5, tip_y + 4)
            painter.drawPath(arrow)

    def _bypass_points(self, order: int = 0
                       ) -> list[tuple[float, float]] | None:
        """绕行线折点（**纯 float 元组**，见 ``_rounded_polyline`` 的警示）：
        **从「去底色」胶囊中心出发** → 向右 → **直角上折** → 向右越过节点
        上方 → **直角下折** → 向右接到「PDF排版」胶囊左缘——**全部横平
        竖直**，像管道工铺管（用户 2026-09-30：不要任意角度的斜线）。

        ⚠️ 起点必须是**胶囊中心**而不是前端连接件的左缘（用户 2026-09-30
        报「实线左侧悬空」）：StepItem 胶囊贴合内容、右侧留白，虚线连接线
        从胶囊中心画出来——起点若取连接件左缘，胶囊右缘到连接件左缘之间
        就只剩一段没人覆盖的灰虚线。从胶囊中心出发，实线正好整段盖住虚线
        （胶囊框内的那截被胶囊 SURFACE 实底遮住，与常规连接线同款）。

        上下竖线离节点左右缘各 ``_BYPASS_CLEAR`` px（用户同日报「不要贴着
        按钮边缘拐弯」），且不越进左右胶囊（至少留 6px）；空间不够时往里
        收，竖线贴上仍放不下就不画（返回 None）。

        ``order`` 是第几个可选节点（默认第一个——老调用方只认那一个）。
        """
        node = self.optional_nodes[order]
        if node.width() < 5:
            return None
        # ⚠️ 左右邻居按该节点自己的 ``after`` 查（默认流程 = buttons[-2] /
        #    buttons[-1]）。可选节点排在**最前**（after = -1）时没有左邻居
        #    ——没有"绕过它接到下一步"的起点（不该用 buttons[-1] 兜底，
        #    Python 负下标会静默取到最后一步）；排在最后一步之后时没有右
        #    邻居。两种情况都返回 None 不画。
        after = self.optional_afters[order]
        if after < 0 or after >= len(self.buttons) - 1:
            return None
        left_pill = self.buttons[after].pill
        right_pill = self.buttons[after + 1].pill
        left_c = left_pill.mapTo(
            self, QPoint(left_pill.width() // 2, left_pill.height() // 2)
        )
        right_c = right_pill.mapTo(
            self, QPoint(right_pill.width() // 2, right_pill.height() // 2)
        )
        top_left = node.mapTo(self, QPoint(0, 0))
        y_main = float(left_c.y())
        y_top = min(max(top_left.y() - 7.0, 4.0), y_main - 10.0)
        x_in = max(
            float(top_left.x() - _BYPASS_CLEAR),
            float(left_c.x() + left_pill.width() // 2 + 6.0),
        )
        x_out = min(
            float(top_left.x() + node.width() + _BYPASS_CLEAR),
            float(right_c.x() - right_pill.width() // 2 - 6.0),
        )
        if x_in >= x_out:
            return None
        return [
            (float(left_c.x()), y_main),
            (x_in, y_main),
            (x_in, y_top),
            (x_out, y_top),
            (x_out, y_main),
            # 与 _draw_connectors 的箭头尖端一致（胶囊左缘外 2px），绿色箭头
            # 正好盖住拼版支路那条灰色虚线的箭头，不出现"两个箭头/没有箭头"。
            (float(right_c.x() - right_pill.width() // 2 - 2), y_main),
        ]


__all__ = ["_StepBarPaintMixin", "_rounded_polyline"]
