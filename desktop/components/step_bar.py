# -*- coding: utf-8 -*-
"""详情页顶部步骤条：编号/对勾徽标 + 连接箭头 + 主副标题。

设计要点：
- 每一步 = 圆形徽标（编号或 ✓）+ 标题 + 状态副标题，用形状表达"第几步"；
- 步骤之间用带箭头的连接线连起来，已完成的线段变色，直观表达先后顺序；
  连接线由 **StepBar 底层统一画**、从节点框**后面**穿过——节点框有实底
  （``_StepItem.pill`` / 拼版节点自己画），框内那截线被遮住，线自然"从
  框后面出发"，不用再对齐框边缘；
- 节点框：所有节点**同一套外观**——SURFACE 实底 + 浅色描边 + 高亮底色，
  选中/当前只有底色变化、**没有边框差异**（用户 2026-09-30：其他节点即使
  选中也没有 border，只有背景色；拼版节点生效与否样式统一）；
- 状态色：未执行（灰）· 执行中（蓝）· 成功（绿）· 失败（红）· 已中断（橙）；
- 整步可点击切换，带悬停底色，避免按钮样式的标签堆叠感。

对外接口（兼容旧调用）：
- ``buttons``：StepItem 列表（长度 = 步骤数）；
- ``_completed``：已完成步骤下标集合；
- ``set_steps`` / ``set_current`` / ``mark_completed`` / ``current_changed``。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from desktop.ui import theme as T

# 状态色统一取自 ui.theme，保证与列表页状态胶囊一致
ACCENT = T.ACCENT
GREEN = T.SUCCESS
RED = T.DANGER
AMBER = T.WARNING
GRAY = T.INK_FAINT
#: 「图上画了、但还没有对应功能」的节点在步骤条上的副标题（2026-10-05）
UNMAPPED_DETAIL = "未接入"

# 状态 → (徽标填充, 徽标描边, 徽标文字, 标题色, 副标题色)
_STATUS_COLORS = {
    "pending":   (T.SURFACE, "#C8C6C4", T.INK_SOFT, T.INK_SOFT, T.INK_FAINT),
    "running":   (ACCENT, ACCENT, T.SURFACE, ACCENT, ACCENT),
    "success":   (GREEN, GREEN, T.SURFACE, T.INK, GREEN),
    "failed":    (RED, RED, T.SURFACE, RED, RED),
    "cancelled": (T.SURFACE, AMBER, AMBER, T.INK, AMBER),
}

_BADGE = 26          # 徽标直径
_CONNECTOR_W = 38    # 连接线宽度（含箭头）
_BYPASS_CLEAR = 28   # 绕行线上下竖线离拼版节点左右缘的距离（用户 2026-09-30：别贴着按钮拐弯）
# 所有节点的**统一默认宽度**（用户 2026-09-30：所有节点设置一个默认宽度，
# 生效/不生效、选择/未选择都不改变宽度——状态只表达在徽标与副标题上）。
# 只是下限：状态副标题更长时节点仍可以变宽（文字走省略号兜底）。
_NODE_MIN_W = 140

_STATUS_LABELS = {
    "pending": "未执行",
    "running": "执行中",
    "success": "成功",
    "failed": "失败",
    "cancelled": "已中断",
}


class _StepBadge(QWidget):
    """圆形徽标：编号 / 成功对勾 / 自定义符号（如拼版节点的「＋」）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_BADGE, _BADGE)
        self._number = 1
        self._status = "pending"
        #: 非 success 状态下要画的符号（None = 画编号）。success 恒画对勾。
        self._symbol: str | None = None

    def set_state(self, number: int, status: str) -> None:
        self._number = number
        self._status = status
        self.update()

    def set_symbol(self, symbol: str | None) -> None:
        if symbol != self._symbol:
            self._symbol = symbol
            self.update()

    def paintEvent(self, _event) -> None:
        fill, border, text_color = _STATUS_COLORS.get(
            self._status, _STATUS_COLORS["pending"]
        )[:3]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        painter.setPen(QPen(QColor(border), 1.4))
        painter.setBrush(QColor(fill))
        painter.drawEllipse(rect)

        if self._status == "success":
            path = QPainterPath()
            w, h = self.width(), self.height()
            path.moveTo(w * 0.30, h * 0.52)
            path.lineTo(w * 0.44, h * 0.67)
            path.lineTo(w * 0.72, h * 0.35)
            painter.setPen(
                QPen(QColor(text_color), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            )
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
        elif self._symbol:
            font = QFont(self.font())
            font.setPixelSize(14)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(text_color))
            painter.drawText(self.rect(), Qt.AlignCenter, self._symbol)
        else:
            font = QFont(self.font())
            font.setPixelSize(12)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(text_color))
            painter.drawText(self.rect(), Qt.AlignCenter, str(self._number))
        painter.end()


class _Connector(QWidget):
    """步骤之间的**占位间隔**：只负责撑开左右节点的间距。

    连接线本体（线 + 箭头）由 ``StepBar._draw_connectors`` 在底层统一画、
    从节点框后面穿过——线端被节点的实底遮住，不再需要对齐框边缘。本控件
    不画任何东西，但自测依赖它的类型与槽位顺序，别删。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(_CONNECTOR_W)
        self.setFixedHeight(18)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)


class _ElidedLabel(QLabel):
    """可压缩标签：宽度不够时右侧省略号，不把父布局顶宽、也不硬裁文字。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._color = QColor("#1f1f1f")
        self.setMinimumWidth(0)

    def set_text_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(self._color)
        text = painter.fontMetrics().elidedText(
            self.text(), Qt.ElideRight, self.width()
        )
        painter.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, text)
        painter.end()


class StepItem(QFrame):
    """单个步骤：徽标 + 标题 + 状态副标题，整块可点击。

    外层只负责在步骤条里占位（等宽拉伸，保证徽标横向均匀），
    真正的底色/悬停胶囊是内层 ``#stepPill``——它贴合内容宽度，
    避免当前步骤的高亮底色被拉成一整格的"按钮"。
    """

    clicked = Signal(int)

    def __init__(self, index: int, title: str, parent=None):
        """初始化单个步骤项：徽标 + 标题 + 副标题，整块可点击。

        index 为步骤下标（从 0）；pill 为真身胶囊，底色由 paintEvent 自绘
        （不用样式表），current 高亮由 _apply_style 控制。
        """
        super().__init__(parent)
        self.index = index
        self._status = "pending"
        self._badge_status = "pending"
        self._background: QColor | None = None
        self.current = False
        self.setObjectName("stepItem")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 8, 0)
        outer.setSpacing(0)

        self.pill = QFrame(self)
        self.pill.setObjectName("stepPill")
        self.pill.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        # 统一默认宽度（_NODE_MIN_W）：节点之间宽窄一致，状态变化不引起跳动
        self.pill.setMinimumWidth(_NODE_MIN_W)
        row = QHBoxLayout(self.pill)
        row.setContentsMargins(8, 5, 12, 5)
        row.setSpacing(9)

        self.badge = _StepBadge(self.pill)
        row.addWidget(self.badge, 0, Qt.AlignVCenter)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self._base_title = title
        #: 「图上画了、但还没有对应功能」的灰节点标记（2026-10-05）
        self._unmapped = False
        self.title_label = _ElidedLabel(title, self.pill)
        self.detail_label = _ElidedLabel("", self.pill)
        self.detail_label.setVisible(False)
        column.addWidget(self.title_label)
        column.addWidget(self.detail_label)
        row.addLayout(column, 1)

        outer.addWidget(self.pill, 0, Qt.AlignLeft | Qt.AlignVCenter)
        outer.addStretch(0)

        self._apply_style()

    # ------------------------------------------------------------------ 状态
    def set_title(self, title: str) -> None:
        """只替换标题文案，不改动状态与徽标。"""
        self.title_label.setText(title)

    def set_status(self, status: str, detail: str = "", badge_status: str = "") -> None:
        """status 决定副标题/标题色，badge_status 决定徽标（缺省同 status）。

        两者分开是为了表达"这一步有产出，但最近一次重试失败"：
        徽标仍是对勾，副标题用失败色写明最近一次的结果。
        """
        self._status = status if status in _STATUS_COLORS else "pending"
        self._badge_status = (
            badge_status if badge_status in _STATUS_COLORS else self._status
        )
        # ⚠️ 未接入的节点**固定**显示「未接入」，不被状态刷新覆盖成
        #    "未执行"——那会把"这一步没功能"说成"这一步还没跑"。
        self.detail_label.setText(
            UNMAPPED_DETAIL if self._unmapped else detail)
        self.detail_label.setVisible(self._unmapped or bool(detail))
        self.badge.set_state(self.index + 1, self._badge_status)
        self._apply_style()

    def set_current(self, current: bool) -> None:
        """设置是否为当前步骤，切换高亮底色与标题字重。"""
        self.current = current
        self._apply_style()

    def _apply_style(self) -> None:
        # 标题色跟随徽标（有产出的步骤保持常规色），副标题色跟随最近一次执行状态
        _, _, _, title_color, _ = _STATUS_COLORS.get(
            self._badge_status, _STATUS_COLORS["pending"]
        )
        detail_color = _STATUS_COLORS.get(
            self._status, _STATUS_COLORS["pending"]
        )[4]
        if self.current:
            self._background = QColor(0, 120, 212, 26)
        elif self._hovered():
            self._background = QColor(0, 0, 0, 11)
        else:
            self._background = None
        self.update()

        title_font = QFont(self.font())
        title_font.setPixelSize(13)
        title_font.setBold(self.current)
        self.title_label.setFont(title_font)
        self.title_label.set_text_color(ACCENT if self.current else title_color)
        detail_font = QFont(self.font())
        detail_font.setPixelSize(12)
        self.detail_label.setFont(detail_font)
        self.detail_label.set_text_color(detail_color)

    def _hovered(self) -> bool:
        return self.underMouse()

    # ------------------------------------------------------------------ 绘制
    def set_unmapped(self, flag: bool = True) -> None:
        """标记为「图上有、但还没有对应功能」的**灰节点**（2026-10-05）。

        用户在流程图上可以画任意节点（bpmn.io 里加一个「OCR 识别」之类），
        本程序没有对应实现。这类节点**不再被静默丢掉**（界面上根本找不到
        "流程节点对不上"），而是照常占一格、显示为灰色并标注「未接入」。

        **仍可点**：点了由页面解释怎么接上（改名成已有步骤名）或怎么删掉
        ——比"点了没反应"或"直接不显示"都好解释。
        """
        self._unmapped = bool(flag)
        # ⚠️ 「未接入」放**副标题**而不是标题后缀：标题那格宽度有限，加后缀
        #    会被省略号截成"（未接…"，反而看不出是什么步骤了。副标题整行都是
        #    它的，写得下。
        self.title_label.setText(self._base_title)
        self.title_label.set_text_color(GRAY if self._unmapped else "#1f1f1f")
        self.detail_label.setText(UNMAPPED_DETAIL if self._unmapped else "")
        self.detail_label.setVisible(self._unmapped)
        self.setToolTip(
            "这一步还没有对应的处理功能，暂时不能执行"
            "（可在流程图里把它改名成已有步骤，或删掉）"
            if self._unmapped else ""
        )
        self.update()

    def paintEvent(self, _event) -> None:
        """自己画胶囊：样式表一旦出现在子树里，Qt 会把 QFrame 底色填白
        （盖住步骤条的卡片底色），所以这里不用样式表。

        胶囊**始终**有 SURFACE 实底 + 实线 border：实底用来遮住从框后面
        穿过的连接线（见 ``StepBar._draw_connectors``），实线 border 是
        真实步骤的视觉语言（可选节点才是虚线）。高亮底色（当前/悬停）
        叠在实底之上。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.pill.geometry())
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(T.SURFACE))
        painter.drawRoundedRect(rect, 8, 8)
        if self._background is not None:
            painter.setBrush(self._background)
            painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(QPen(QColor(T.BORDER), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        painter.end()

    # ------------------------------------------------------------------ 交互
    def enterEvent(self, event) -> None:
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._apply_style()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self.index)
        super().mouseReleaseEvent(event)


class _ImpositionNode(QFrame):
    """流程条上的「图片拼版」可选节点：**外观与真实节点完全同款**。

    用户 2026-09-30 定稿（替代早先的「虚线 = 可选」语言）：
    - **没有自己的边框差异**——其他节点即使选中也只有背景色、没有 border，
      本节点一样：SURFACE 实底 + 浅描边（与 StepItem 同一支画法）；
      **高亮底色只属于当前步**（用户 2026-09-30：生效但不是当前步骤 →
      白底，与其他节点一致），生效/不生效、选择/未选择**样式统一**，
      状态只表达在徽标与副标题上；
    - 徽标跟真实步骤同款圆形：未生效画灰色「＋」（可选、未进流程），
      **选中且生效**后跟前面节点一样是绿色对勾（``set_flow_active``）；
    - 未选择时副标题「未选择」，选择后「已选择」；
    - 当前正在查看它的详情时叠加当前步的高亮底色（与真实步骤一致）；
    - 框内**始终有 SURFACE 实底**：连接线从框后面穿过时靠它遮住（真实
      步骤同款，见 ``StepItem.paintEvent``）；
    - **能不能把两侧连接线点亮，看这条支路是不是真的在流程里**（生效态，
      由 ``StepBar.set_imposition_active`` 控制）：未生效 → 两端灰色虚线、
      主流程走节点上方的绕行线；生效 → 回到常规规则；
    - 宽度有统一默认下限（``_NODE_MIN_W``），状态变化不改变宽度。
    """

    clicked = Signal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._selected = False
        self._current = False
        self._flow = False
        self.setObjectName("impositionNode")
        self.setCursor(Qt.PointingHandCursor)
        # ⚠️ **不许被拉宽**：节点只包住自己的内容（用户 2026-09-30 报「虚线框
        # 宽度太宽」——它跟真实步骤平分了流程条的多余空间，实测 303px vs 步骤
        # 胶囊 145px）。Maximum = 宽度上限就是 sizeHint，窗口变窄时仍可压缩
        # （标题走省略号）；多余空间留给真实步骤。统一默认宽度由
        # ``setMinimumWidth(_NODE_MIN_W)`` 给下限。
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.setMinimumWidth(_NODE_MIN_W)
        self.setToolTip(
            "可选节点：第三步「区域模式」为 1（左右分开）时出现，"
            "位于「图片去底色」与「生成 PDF」之间。点击查看/选择。"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 5, 12, 5)   # 与 StepItem 胶囊一致
        row.setSpacing(9)
        self.badge = _StepBadge(self)
        self.badge.set_symbol("＋")           # 未生效：灰色「＋」；生效后转对勾
        row.addWidget(self.badge, 0, Qt.AlignVCenter)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.title_label = _ElidedLabel(title, self)
        self.detail_label = _ElidedLabel("未选择", self)
        column.addWidget(self.title_label)
        column.addWidget(self.detail_label)
        row.addLayout(column, 1)
        self._apply_style()

    def set_selected(self, selected: bool) -> None:
        if selected != self._selected:
            self._selected = selected
            self._apply_style()

    def is_selected(self) -> bool:
        return self._selected

    def set_current(self, current: bool) -> None:
        if current != self._current:
            self._current = current
            self._apply_style()

    def set_flow_active(self, active: bool) -> None:
        """拼版支路是否**生效**：生效 → 徽标转绿色对勾（与真实步骤同款）。"""
        active = bool(active)
        if active != self._flow:
            self._flow = active
            self.badge.set_state(0, "success" if active else "pending")
            self._apply_style()

    def _hovered(self) -> bool:
        return self.underMouse()

    def _apply_style(self) -> None:
        # 与真实节点同一套配色：高亮底色**只在当前步**（用户 2026-09-30：
        # 生效但不是当前步骤 → 白底，与其他节点一致；「已选择」由副标题
        # 与徽标表达，不再压蓝底）。
        if self._current:
            self._background = QColor(0, 120, 212, 26)
        elif self._hovered():
            self._background = QColor(0, 0, 0, 11)
        else:
            self._background = None
        self.detail_label.setText("已选择" if self._selected else "未选择")

        title_font = QFont(self.font())
        title_font.setPixelSize(13)
        title_font.setBold(self._current)
        self.title_label.setFont(title_font)
        self.title_label.set_text_color(ACCENT if self._current else T.INK_SOFT)
        detail_font = QFont(self.font())
        detail_font.setPixelSize(12)
        self.detail_label.setFont(detail_font)
        self.detail_label.set_text_color(ACCENT if self._selected else T.INK_FAINT)
        self.update()

    def paintEvent(self, _event) -> None:
        """与 ``StepItem.paintEvent`` 同一支画法：SURFACE 实底 + 高亮底色
        + 浅描边。选中/生效**不换边框**（用户 2026-09-30：其他节点即使
        选中也没有 border，只有背景色）。实底用来遮住从框后面穿过的连接线。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(T.SURFACE))
        painter.drawRoundedRect(rect, 8, 8)
        if self._background is not None:
            painter.setBrush(self._background)
            painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(QPen(QColor(T.BORDER), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        painter.end()

    def enterEvent(self, event) -> None:
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._apply_style()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


def _rounded_polyline(points: list[tuple[float, float]], radius: float = 6.0) -> QPainterPath:
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


class StepBar(QWidget):
    """横向步骤条：真实步骤按顺序排列，当前步骤高亮、已完成步骤打勾。

    除真实步骤外还支持一个**条件虚线节点**（「图片拼版」可选节点）：
    默认隐藏，``set_imposition_visible(True)`` 时插在**指定位置**——位置由
    构造参数 ``optional_after`` 决定（默认流程 = 插在倒数两个步骤之间）。
    伪步骤下标 ``imposition_index`` 是**步骤条上的格序**（含可选节点占位），
    ``set_current`` / ``current_changed`` 都以它表达"当前在看拼版详情"。

    ⚠️ **BPM 驱动**（``docs/tasks/bpm.md`` 的 M2）：真实步骤的顺序与可选
    节点的位置都来自本任务流程的槽位表（宿主
    ``TaskDetailPage._bar_step_titles`` / ``_optional_after_index`` 传入），
    换流程只换参数——本组件不认 ``STAGES``、也不数下标猜位置。

    节点有两条互相独立的状态线（别合并）：
    - **选择态**（``set_imposition_selected``）：只管节点自己的外观
      （「已选择/未选择」副标题；节点没有边框差异、也不压高亮底色，
      与真实步骤同一套外观）；
    - **生效态**（``set_imposition_active``）：这条支路是否真的承载流程
      （已启用且至少有一页拼版）。生效 → 两侧连接线常规点亮、节点徽标
      转绿色对勾；未生效 → 两侧连接线灰色虚线、徽标灰色「＋」，同时
      「去底色 → 生成 PDF」画一条从节点上方绕过的绕行线
      （``_draw_imposition_bypass``）——选了拼版但还没有拼版页时，
      第四步实际取的仍是第三步产物，线不能说谎。

    节点的宽度与间距分成两件事（都踩过坑，别再合并）：
    - **槽位**与真实步骤等宽（``imposition_slot`` + stretch 1）→ 步骤间距均分；
    - **节点框**只在槽位里靠左、宽度不超过内容但有统一默认下限
      （``QSizePolicy.Maximum`` + ``_NODE_MIN_W``）→ 不被拉宽、宽窄一致。
    """

    current_changed = Signal(int)
    #: 流程条上点了「图片拼版」虚线节点（宿主据此切到占位详情）。
    imposition_clicked = Signal()

    def __init__(self, steps, parent=None, optional_after=None,
                 unmapped=None):
        """按给定步骤标题逐项构建；steps 允许传生成器。

        ``optional_after`` 是**可选节点（拼版）插在第几个真实步骤之后**
        （``None`` = 插在最后一步之前，沿用旧行为）。⚠️ 这是 BPM 驱动的
        关键参数（``docs/tasks/bpm.md`` 的 M2）：默认流程下它等于
        ``len(steps) - 1``（拼版在「图片去底色」与「生成 PDF」之间，与旧
        硬编码一致）；自定义流程把拼版排到别处时，宿主按槽位表的
        ``bar_index`` 算出来传进来，**连线/绕行线也跟着挪**。
        """
        super().__init__(parent)
        steps = list(steps)  # 调用方传的是生成器（STAGE_LABELS[s] for s in STAGES）
        self.buttons: list[StepItem] = []
        self.connectors: list[_Connector] = []
        self._completed: set[int] = set()
        self._current = 0
        #: 拼版支路是否**生效**（承载真实流程）；与节点的选择态分开
        self._imposition_flow = False
        #: 可选节点插在第几个真实步骤之后（构造期算出，见 ``optional_after``）。
        #: 下游找"拼版左右邻居"一律走它，不再写死 ``buttons[-2]``。
        self._optional_after = (
            len(steps) - 1 if optional_after is None else int(optional_after)
        )
        # ⚠️ 越界兜底：可选节点插在最后（没有右邻居）或最前（没有左邻居）
        # 都是合法自定义流程，夹进可用范围，别让 ``insert_at`` 算出负下标。
        self._optional_after = max(
            0, min(self._optional_after, max(len(steps) - 1, 0))
        )
        #: 伪步骤（拼版节点）的下标与控件；节点默认隐藏。
        #: ⚠️ ``imposition_index`` 是**步骤条上的格序**（含可选节点占位），
        #:    自定义流程下不再等于 ``len(steps)``。
        self.imposition_index = self._optional_after + 1
        self.imposition_node = _ImpositionNode("图片拼版", self)
        self.imposition_node.clicked.connect(self._on_imposition_click)
        self._imposition_connector = _Connector(self)
        # 节点**槽位**：与真实步骤等宽（stretch 1 → 间距均分），虚线框在槽位里
        # 靠左、宽度仍贴合文字。这两件事必须分开——合成一个控件就只能二选一：
        # 槽位等宽 = 虚线框被拉宽（用户 2026-09-30 报过），框贴合文字 = 最后一段
        # 挤在一起（用户同日报「不均分步骤」，实测间距 406 vs 147px）。与
        # StepItem「外框等宽拉伸 + 内层 pill 贴合内容」是同一套写法。
        self.imposition_slot = QWidget(self)
        slot_row = QHBoxLayout(self.imposition_slot)
        slot_row.setContentsMargins(0, 0, 8, 0)  # 与 StepItem 外边距一致
        slot_row.setSpacing(0)
        slot_row.addWidget(self.imposition_node, 0, Qt.AlignLeft | Qt.AlignVCenter)
        slot_row.addStretch(0)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(0)
        self._row = row
        #: 「图上有、还没功能」的下标集合——这些节点画成灰的
        self._unmapped_indices = {int(i) for i in (unmapped or ())}
        for index, title in enumerate(steps):
            item = StepItem(index, title, self)
            if index in self._unmapped_indices:
                item.set_unmapped(True)
            item.clicked.connect(self._on_click)
            self.buttons.append(item)
            row.addWidget(item, 1)
            if index < len(steps) - 1:
                connector = _Connector(self)
                self.connectors.append(connector)
                row.addWidget(connector, 0, Qt.AlignVCenter)
        # 把「拼版节点 + 它后面的连接线」插到**第 ``_optional_after`` 个真实
        # 步骤之后**：布局此时为 [item0, conn0, item1, conn1, ...]，第 k 个
        # 真实步骤占下标 ``2k``，它**后面**那条连接件占 ``2k+1``。所以要
        # "插在第 k 个之后"= 插到下标 ``2k+2``（即下一个步骤的原位置）。
        # 默认流程 ``_optional_after = len(steps)-1`` 时正好等于旧口径的
        # ``row.count()-1``（两者都是"最后一项"的位置，完全等价）。
        # ⚠️ 必须是 2k+2：算成 2k+1 会插到 conn[k] 前面，箭头全跑到
        #    虚线框后面（用户截图报过：虚线前面没有箭头、后面挤两个）。
        insert_at = 2 * self._optional_after + 2
        row.insertWidget(insert_at, self._imposition_connector, 0, Qt.AlignVCenter)
        # 槽位 stretch **1**：与真实步骤平分多余空间（间距才均匀）；虚线框自身
        # 靠 Maximum 策略贴在槽位左侧，不会被拉宽。
        row.insertWidget(insert_at, self.imposition_slot, 1)
        #: 节点**前面**那条连接线——布局上就是紧挨着槽位左边的那条，也就是原本的
        #  「去底色→PDF」。绕行线的起终点现取左右胶囊几何（见 _bypass_points），
        #  本属性只用于标认「前端那格」；线本身的点亮/虚线由
        #  ``_connector_segments`` 按 ``_optional_after`` 判定。
        # ⚠️ 可选节点插在**最后一步之后**时它没有前端连接件（左侧直接是
        #    item[n-1]），此时取最后一条常规连接件，没有则 None。
        self.imposition_front_connector = (
            self.connectors[self._optional_after]
            if self._optional_after < len(self.connectors)
            else (self.connectors[-1] if self.connectors else None)
        )
        self.imposition_node.setVisible(False)
        self._imposition_connector.setVisible(False)
        row.addStretch(0)
        self._sync()

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
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
        - 「去底色 → 拼版」与「拼版 → PDF」：支路生效（``_imposition_flow``）
          才按常规点亮，未生效一律灰虚线——真实流向走节点上方的绕行线；
        - 节点隐藏（area≠1）时前端那格回归普通的「去底色 → PDF」常规段。
        """
        n = len(self.buttons)
        shown = self._imposition_shown()
        flow = shown and self._imposition_flow
        # ⚠️ 可选节点两侧的真实步骤（默认流程 = [-2] 与 [-1]）。插在最后一步
        #    之后时没有右邻居，左侧那格就是最后一步。
        after = self._optional_after
        segments = []
        # ⚠️ 上界取 ``n`` 而不是 ``n-1``：可选节点可以排在**最后一个真实
        #    步骤之后**（``after == n-1``），那时它的左邻居那一段恰好在
        #    ``index == n-1`` 处，用 ``range(n-1)`` 会漏掉这段（连接线断掉）。
        for index in range(n):
            if shown and index == after:
                segments.append((
                    self.buttons[index].pill, self.imposition_node,
                    flow and index in self._completed, not flow,
                ))
            elif index < n - 1:
                segments.append((
                    self.buttons[index].pill, self.buttons[index + 1].pill,
                    index in self._completed, False,
                ))
        if shown:
            if after < n - 1:
                segments.append(
                    (self.imposition_node, self.buttons[after + 1].pill,
                     flow, not flow)
                )
            # after == n-1（可选节点排在最后一步之后）：它右侧没有真实
            # 步骤可连，不补段（补了会画出指向虚空的线）。
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
                    color, 2, Qt.DashLine if dash else Qt.SolidLine, Qt.RoundCap
                )
            )
            painter.drawLine(QPointF(a.x(), a.y()), QPointF(b.x(), b.y()))
            painter.setPen(
                QPen(color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            )
            tip = b.x() - right.width() // 2 - 2
            arrow = QPainterPath()
            arrow.moveTo(tip - 5, a.y() - 4)
            arrow.lineTo(tip, a.y())
            arrow.lineTo(tip - 5, a.y() + 4)
            painter.drawPath(arrow)

    def _draw_imposition_bypass(self, painter) -> None:
        """「去底色 → 生成 PDF」绕行线：拼版节点在流程里但**未生效**时画。

        此刻第四步实际取的是第三步产物（``print_source_dir``），主线必须在
        节点上方绕过去，否则流程条上「去底色」和「生成 PDF」之间没有真实
        连接。颜色规则与普通连接线一致：左侧步骤（去底色）完成即绿。
        拼版支路自己的两条线此时是灰色虚线（见 ``_sync``）。
        """
        if self._imposition_shown() is False or self._imposition_flow:
            return
        points = self._bypass_points()
        if points is None:
            return
        done = self._optional_after in self._completed
        painter.setPen(
            QPen(
                QColor(GREEN if done else "#d6d6d6"), 2,
                Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin,
            )
        )
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(_rounded_polyline(points))

    def _bypass_points(self) -> list[tuple[float, float]] | None:
        """绕行线折点（**纯 float 元组**，见 ``_rounded_polyline`` 的警示）：
        **从「去底色」胶囊中心出发** → 向右 → **直角上折** → 向右越过节点
        上方 → **直角下折** → 向右接到「生成 PDF」胶囊左缘——**全部横平
        竖直**，像管道工铺管（用户 2026-09-30：不要任意角度的斜线）。

        ⚠️ 起点必须是**胶囊中心**而不是前端连接件的左缘（用户 2026-09-30
        报「实线左侧悬空」）：StepItem 胶囊贴合内容、右侧留白，虚线连接线
        从胶囊中心画出来——起点若取连接件左缘，胶囊右缘到连接件左缘之间
        就只剩一段没人覆盖的灰虚线。从胶囊中心出发，实线正好整段盖住虚线
        （胶囊框内的那截被胶囊 SURFACE 实底遮住，与常规连接线同款）。

        上下竖线离节点左右缘各 ``_BYPASS_CLEAR`` px（用户同日报「不要贴着
        按钮边缘拐弯」），且不越进左右胶囊（至少留 6px）；空间不够时往里
        收，竖线贴上仍放不下就不画（返回 None）。
        """
        node = self.imposition_node
        if node.width() < 5:
            return None
        # ⚠️ 左右邻居按 ``_optional_after`` 查（默认流程 = buttons[-2] /
        #    buttons[-1]）。可选节点排在最后一步之后时**没有右邻居**，
        #    也就没有"绕过它接到下一步"这根线——返回 None 不画。
        after = self._optional_after
        if after >= len(self.buttons) - 1:
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
            (float(right_c.x() - right_pill.width() // 2 - 1), y_main),
        ]

    # ------------------------------------------------------------------ 接口
    def _on_click(self, index: int) -> None:
        self.set_current(index)
        self.current_changed.emit(index)

    def _on_imposition_click(self) -> None:
        self._current = self.imposition_index
        self._sync()
        self.imposition_clicked.emit()

    def set_current(self, index: int) -> None:
        """设置当前步骤下标并同步各步骤高亮与徽标。"""
        self._current = index
        self._sync()

    def mark_completed(self, index: int) -> None:
        """标记某步骤已完成（徽标改为对勾，连接线着色）。"""
        self._completed.add(index)
        self._sync()

    def set_steps(self, texts) -> None:
        """兼容旧调用：只更新标题文本。"""
        for item, text in zip(self.buttons, texts):
            item.set_title(text)

    def set_imposition_visible(self, visible: bool) -> None:
        """显示/隐藏「图片拼版」虚线节点（随第三步区域模式是否为 1）。

        ⚠️ 槽位要一起隐藏：只藏节点的话，那格等宽槽位还占着位置，流程条上会
        留出一段空白（第四步/PDF 看起来被推远）。
        另外节点显示时行顶边距 6→18：给绕行线留一条**走线带**——拼版未生效
        时「去底色 → 生成 PDF」的线要贴着节点上方绕过去（见
        ``_draw_imposition_bypass``），不预留高度弧线会顶到卡片边框。
        """
        self.imposition_node.setVisible(visible)
        self.imposition_slot.setVisible(visible)
        self._imposition_connector.setVisible(visible)
        margins = self._row.contentsMargins()
        self._row.setContentsMargins(
            margins.left(), 18 if visible else 6, margins.right(), margins.bottom()
        )
        self._sync()

    def set_imposition_selected(self, selected: bool) -> None:
        """「图片拼版」是否被选择（副标题/徽标口径，不动连接线/绕行线）。"""
        self.imposition_node.set_selected(selected)
        self._sync()

    def set_imposition_active(self, active: bool) -> None:
        """拼版支路是否**生效**（已启用且至少有一页拼版，宿主判定）。

        生效 → 两侧连接线常规点亮、节点徽标转绿色对勾（与真实步骤同款）；
        未生效 → 两侧连接线灰色虚线、徽标灰色「＋」，主流程改走节点上方
        的绕行线。与 ``set_imposition_selected``
        （节点自己的选择外观）互不取代：选了但还没有拼版页时，节点
        显示「已选择」，但线仍然是灰色虚线 + 绕行。
        """
        active = bool(active)
        if active != self._imposition_flow:
            self._imposition_flow = active
            self.imposition_node.set_flow_active(active)
            self._sync()

    def set_step_status(
        self, index: int, status: str, progress: tuple | None = None,
        completed: bool | None = None,
    ) -> None:
        """设置某步骤状态；progress 为 (已完成, 总数) 时拼出 "成功 · 84/84"。

        completed=False 但 status='success' 不可能出现；completed=True 而
        status 为失败/中断时，徽标保持对勾、副标题仍显示最近一次的结果。
        """
        if not 0 <= index < len(self.buttons):
            return
        detail = _STATUS_LABELS.get(status, status)
        if progress and progress[1]:
            detail = f"{detail} · {progress[0]}/{progress[1]}"
        done = status == "success" if completed is None else bool(completed)
        if done:
            self._completed.add(index)
        else:
            self._completed.discard(index)
        self.buttons[index].set_status(
            status, detail, badge_status="success" if done else status
        )
        self._sync()

    def reset_statuses(self) -> None:
        """全部步骤恢复为未执行，并清空已完成标记。"""
        self._completed.clear()
        for item in self.buttons:
            item.set_status("pending", _STATUS_LABELS["pending"])
        self._sync()

    def _imposition_shown(self) -> bool:
        """拼版节点是否被**配置**为显示。

        ⚠️ 用 ``isHidden()``（只反映显式 ``setVisible(False)``）而不是
        ``isVisible()``（还要求整条窗口已经 show）：构建期/未显示时算出来的
        "未显示"会把两侧连接线压灰，而之后不一定再有 ``_sync`` 把它们点亮。
        """
        return not self.imposition_node.isHidden()

    def _sync(self) -> None:
        imposition_current = self._current == self.imposition_index
        for index, item in enumerate(self.buttons):
            item.badge.set_state(index + 1, item._badge_status)
            item.set_current(index == self._current)
        self.imposition_node.set_current(imposition_current)
        # 连接线（含拼版两侧）的点亮/虚线状态由 ``_connector_segments`` 在
        # 绘制时从 ``_completed`` / ``_imposition_flow`` 现算——控件不再存状态。
        self.update()
