# -*- coding: utf-8 -*-
"""步骤条的节点控件：徽标 / 占位连接件 / 可省略标签 / 真实节点 / 可选节点。"""

from __future__ import annotations

from desktop.components.step_bar._qt import (
    QColor,
    QFont,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPainter,
    QPainterPath,
    QPen,
    QRectF,
    QSize,
    QSizePolicy,
    Qt,
    QVBoxLayout,
    QWidget,
    Signal,
)

from desktop.components.step_bar.constants import (
    ACCENT,
    _BADGE,
    _CONNECTOR_W,
    _NODE_MIN_W,
    _STATUS_COLORS,
    GRAY,
    UNMAPPED_DETAIL,
)
from desktop.ui import theme as T


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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
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
                QPen(
                    QColor(text_color),
                    2.0,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        elif self._symbol:
            font = QFont(self.font())
            font.setPixelSize(14)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(text_color))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._symbol)
        else:
            font = QFont(self.font())
            font.setPixelSize(12)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(text_color))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, str(self._number)
            )
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
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


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
            self.text(), Qt.TextElideMode.ElideRight, self.width()
        )
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
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
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 8, 0)
        outer.setSpacing(0)

        self.pill = QFrame(self)
        self.pill.setObjectName("stepPill")
        self.pill.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        # 统一默认宽度（_NODE_MIN_W）：节点之间宽窄一致，状态变化不引起跳动
        self.pill.setMinimumWidth(_NODE_MIN_W)
        row = QHBoxLayout(self.pill)
        row.setContentsMargins(8, 5, 12, 5)
        row.setSpacing(9)

        self.badge = _StepBadge(self.pill)
        row.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)

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

        outer.addWidget(
            self.pill, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
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
        self.detail_label.setText(UNMAPPED_DETAIL if self._unmapped else detail)
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
        detail_color = _STATUS_COLORS.get(self._status, _STATUS_COLORS["pending"])[4]
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
            if self._unmapped
            else ""
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.pill.geometry())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(T.SURFACE))
        painter.drawRoundedRect(rect, 8, 8)
        if self._background is not None:
            painter.setBrush(self._background)
            painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(QPen(QColor(T.BORDER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
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
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
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
    - 徽标跟真实步骤同款圆形：未处理过画灰色「＋」，**处理过**后跟前面节点
      一样是绿色对勾（``set_selected``）。⚠️「处理过」由**宿主**按**该节点
      有没有拼版页**判定（2026-10-18 用户口径：流程条上这一格表达的是"这一步
      处理到哪了"——没拼过版的节点不该亮成"已处理"，见
      ``desktop.pages.taskdetail.imposition._sync_imposition_nodes``）；
      「在流程中启用图片拼版」开关是**流程级**条件，不点亮这一格；
    - 未选择时副标题「未选择」，选择后「已选择」；
    - 当前正在查看它的详情时叠加当前步的高亮底色（与真实步骤一致）；
    - 框内**始终有 SURFACE 实底**：连接线从框后面穿过时靠它遮住（真实
      步骤同款，见 ``StepItem.paintEvent``）；
    - **能不能把两侧连接线点亮，看这条支路是不是真的在流程里**（生效态，
      由 ``StepBar.set_imposition_active`` 控制，宿主按**启用开关**判定）：
      未生效 → 两端灰色虚线、主流程走节点上方的绕行线；生效 → 回到常规规则。
      ⚠️ 生效态与徽标**互相独立**（2026-10-23 用户口径：关掉启用开关后流程
      要绕行，但处理过的绿勾照旧）；
    - 宽度有统一默认下限（``_NODE_MIN_W``），状态变化不改变宽度。
    """

    clicked = Signal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._selected = False
        self._current = False
        self._flow = False
        self.setObjectName("impositionNode")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # ⚠️ **不许被拉宽**：节点只包住自己的内容（用户 2026-09-30 报「虚线框
        # 宽度太宽」——它跟真实步骤平分了流程条的多余空间，实测 303px vs 步骤
        # 胶囊 145px）。Maximum = 宽度上限就是 sizeHint，窗口变窄时仍可压缩
        # （标题走省略号）；多余空间留给真实步骤。统一默认宽度由
        # ``setMinimumWidth(_NODE_MIN_W)`` 给下限。
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(_NODE_MIN_W)
        self.setToolTip(
            "可选节点：流程图上画了「图片拼版」时出现，"
            "位于「图片去底色」与「PDF排版」之间。点击查看/选择。"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 5, 12, 5)  # 与 StepItem 胶囊一致
        row.setSpacing(9)
        self.badge = _StepBadge(self)
        self.badge.set_symbol("＋")  # 未生效：灰色「＋」；生效后转对勾
        row.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)

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
            # 徽标跟**这一格自己有没有处理过**走（用户 2026-10-18：第一个拼版
            # 运行过 → 绿勾；第二个还没到那一步 → 灰色「＋」）。
            # ⚠️ 与「这条支路是不是真的在流程里」（``set_flow_active``，决定
            #    连接线与绕行）**刻意分开**：用户 2026-10-23 口径——关掉
            #    「在流程图中启用图片拼版」后，PDF排版取上一步的数据，流程图上
            #    这一支就该绕行；但它确实处理过页，绿勾不该跟着灭。
            self.badge.set_state(0, "success" if self._selected else "pending")
            self._apply_style()

    def is_selected(self) -> bool:
        return self._selected

    def set_current(self, current: bool) -> None:
        if current != self._current:
            self._current = current
            self._apply_style()

    def set_flow_active(self, active: bool) -> None:
        """拼版支路是否**真的在流程里**（决定连接线点亮与否、要不要画绕行线）。

        ⚠️ **只影响流向**，不碰徽标：徽标表达"这一格处理过没有"（见
        ``set_selected``）。早先这里同时改徽标，导致"有拼版页但没启用"时
        流程条仍然经过拼版节点（用户 2026-10-23 报障）。
        """
        active = bool(active)
        if active != self._flow:
            self._flow = active
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(T.SURFACE))
        painter.drawRoundedRect(rect, 8, 8)
        if self._background is not None:
            painter.setBrush(self._background)
            painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(QPen(QColor(T.BORDER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        painter.end()

    def enterEvent(self, event) -> None:
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._apply_style()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


__all__ = [
    "StepItem",
    "_Connector",
    "_ElidedLabel",
    "_ImpositionNode",
    "_StepBadge",
]
