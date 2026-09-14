# -*- coding: utf-8 -*-
"""详情页顶部步骤条：编号/对勾徽标 + 连接箭头 + 主副标题。

设计要点：
- 每一步 = 圆形徽标（编号或 ✓）+ 标题 + 状态副标题，用形状表达"第几步"；
- 步骤之间用带箭头的连接线连起来，已完成的线段变色，直观表达先后顺序；
- 状态色：未执行（灰）· 执行中（蓝）· 成功（绿）· 失败（红）· 已中断（橙）；
- 整步可点击切换，带悬停底色，避免按钮样式的标签堆叠感。

对外接口（兼容旧调用）：
- ``buttons``：StepItem 列表（长度 = 步骤数）；
- ``_completed``：已完成步骤下标集合；
- ``set_steps`` / ``set_current`` / ``mark_completed`` / ``current_changed``。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
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

_STATUS_LABELS = {
    "pending": "未执行",
    "running": "执行中",
    "success": "成功",
    "failed": "失败",
    "cancelled": "已中断",
}


class _StepBadge(QWidget):
    """圆形徽标：编号 / 成功对勾。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_BADGE, _BADGE)
        self._number = 1
        self._status = "pending"

    def set_state(self, number: int, status: str) -> None:
        self._number = number
        self._status = status
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
        else:
            font = QFont(self.font())
            font.setPixelSize(12)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(text_color))
            painter.drawText(self.rect(), Qt.AlignCenter, str(self._number))
        painter.end()


class _Connector(QWidget):
    """步骤之间的连接线 + 箭头；左侧步骤已完成时着色。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(_CONNECTOR_W)
        self.setFixedHeight(18)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._done = False

    def set_done(self, done: bool) -> None:
        if done != self._done:
            self._done = done
            self.update()

    def paintEvent(self, _event) -> None:
        color = QColor(GREEN if self._done else "#d6d6d6")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        y = self.height() / 2
        painter.setPen(QPen(color, 2, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(1, y), QPointF(self.width() - 10, y))
        arrow = QPainterPath()
        arrow.moveTo(self.width() - 9, y - 4)
        arrow.lineTo(self.width() - 4, y)
        arrow.lineTo(self.width() - 9, y + 4)
        painter.setPen(
            QPen(color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        )
        painter.drawPath(arrow)
        painter.end()


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
        row = QHBoxLayout(self.pill)
        row.setContentsMargins(8, 5, 12, 5)
        row.setSpacing(9)

        self.badge = _StepBadge(self.pill)
        row.addWidget(self.badge, 0, Qt.AlignVCenter)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
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
        self.detail_label.setText(detail)
        self.detail_label.setVisible(bool(detail))
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
    def paintEvent(self, _event) -> None:
        """自己画胶囊底色：样式表一旦出现在子树里，Qt 会把 QFrame 底色填白
        （盖住步骤条的卡片底色），所以这里不用样式表。"""
        if self._background is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._background)
        painter.drawRoundedRect(QRectF(self.pill.geometry()), 8, 8)
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


class StepBar(QWidget):
    """横向步骤条：4 个步骤按顺序排列，当前步骤高亮、已完成步骤打勾。"""

    current_changed = Signal(int)

    def __init__(self, steps, parent=None):
        """按给定步骤标题逐项构建；steps 允许传生成器。"""
        super().__init__(parent)
        steps = list(steps)  # 调用方传的是生成器（STAGE_LABELS[s] for s in STAGES）
        self.buttons: list[StepItem] = []
        self.connectors: list[_Connector] = []
        self._completed: set[int] = set()
        self._current = 0

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(0)
        for index, title in enumerate(steps):
            item = StepItem(index, title, self)
            item.clicked.connect(self._on_click)
            self.buttons.append(item)
            row.addWidget(item, 1)
            if index < len(steps) - 1:
                connector = _Connector(self)
                self.connectors.append(connector)
                row.addWidget(connector, 0, Qt.AlignVCenter)
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
        painter.end()

    # ------------------------------------------------------------------ 接口
    def _on_click(self, index: int) -> None:
        self.set_current(index)
        self.current_changed.emit(index)

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

    def _sync(self) -> None:
        for index, item in enumerate(self.buttons):
            item.badge.set_state(index + 1, item._badge_status)
            item.set_current(index == self._current)
        for index, connector in enumerate(self.connectors):
            connector.set_done(index in self._completed)
        self.update()
