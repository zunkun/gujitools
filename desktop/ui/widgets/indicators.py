# -*- coding: utf-8 -*-
"""状态胶囊、进度条、文字胶囊与空状态（自 ``desktop/ui/widgets.py`` 拆出）。"""

from __future__ import annotations

from desktop.ui import theme as T
from desktop.ui.fonts import ui_font

from ._qt import (
    QColor,
    QLabel,
    QPainter,
    QPixmap,
    QRectF,
    QSize,
    QSizePolicy,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)
from .text import apply_to

class StatusChip(QWidget):
    """状态胶囊：圆点 + 文案 + 浅色底，用于表格里的阶段状态。"""

    def __init__(self, text: str = "", status: str = "pending", parent=None):
        """status 决定圆点与底色，取值见 theme.status_colors。"""
        super().__init__(parent)
        self._text = text
        self._color, self._soft = T.status_colors(status)
        self.setFont(ui_font(T.SIZE_CAPTION))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_state(self, text: str, status: str) -> None:
        """更新文案与状态色，并按新文案重算最小尺寸。"""
        self._text = text
        self._color, self._soft = T.status_colors(status)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        metrics = self.fontMetrics()
        return QSize(
            metrics.horizontalAdvance(self._text) + 30,
            max(metrics.height() + 8, 22),
        )

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._soft))
        radius = rect.height() / 2
        painter.drawRoundedRect(rect, radius, radius)
        # 左侧状态圆点
        dot = 6.0
        painter.setBrush(QColor(self._color))
        painter.drawEllipse(
            QRectF(rect.left() + 8, rect.center().y() - dot / 2, dot, dot)
        )
        painter.setPen(QColor(self._color))
        painter.setFont(self.font())
        painter.drawText(
            rect.adjusted(20, 0, -8, 0),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            self._text,
        )


class ProgressLine(QWidget):
    """细进度条：圆角轨道 + 主色填充。

    比 qfluent 的 ProgressBar 更克制（没有文字、没有内边距），
    适合嵌在参数卡片里表示"这一步执行到多少页"。

    **总量未知**（上限为 0）时自动切成"来回滑动"的未知态：并不是所有执行
    一开始就知道总量（print 的合成阶段、拼版合成、detect 找齐框之前都是），
    这时若还画一根不动的空条，用户会以为界面卡住了。
    """

    #: 未知态滑块占轨道的比例，以及每帧位移（像素）
    _MARGIN_RATIO = 0.3
    _MARGIN_STEP = 2.0

    def __init__(self, parent=None, height: int = 6):
        """height 为轨道像素高度（默认 6）。"""
        super().__init__(parent)
        self._value = 0
        self._maximum = 0
        #: 未知态的滑动偏移与方向（1 = 右移，-1 = 左移）
        self._offset = 0.0
        self._direction = 1.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._advance)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def setRange(self, minimum: int, maximum: int) -> None:  # noqa: N802
        """设置上限，并把当前值夹到 [0, maximum]；上限为 0 时归零（切未知态）。"""
        self._maximum = max(int(maximum), 0)
        self._value = min(max(int(minimum), 0), self._maximum) if self._maximum else 0
        self._sync_unknown_state()
        self.update()

    def setValue(self, value: int) -> None:  # noqa: N802
        """设置当前值（超出上限时夹到上限）。"""
        self._value = max(0, min(int(value), self._maximum)) if self._maximum else 0
        self._sync_unknown_state()
        self.update()

    def value(self) -> int:
        """当前值。"""
        return self._value

    def maximum(self) -> int:
        """上限（0 = 总量未知）。"""
        return self._maximum

    @property
    def ratio(self) -> float:
        """完成比例（0.0~1.0）；尚未设置上限时返回 0.0。"""
        if not self._maximum:
            return 0.0
        return self._value / self._maximum

    def is_unknown(self) -> bool:
        """当前是不是"总量未知"的滑动态。"""
        return self._maximum == 0

    def finish(self) -> None:
        """走到终点（成功收尾时用）；总量未知时什么也不做。

        给上层一个**公开**的收尾入口，是为了不必伸手去摸 ``_maximum``——
        进度行组件只该用这里与 :meth:`setRange` / :meth:`setValue`。
        """
        if self._maximum:
            self.setValue(self._maximum)

    # ------------------------------------------------------------ 未知态动画
    def _sync_unknown_state(self) -> None:
        """按"有没有上限"启停动画定时器。

        ⚠️ 只在**控件可见**时才启动：页面隐藏时挂着 40ms 定时器是白烧 CPU
        （定时器在事件循环里会一直跑，与控件是否被看无关）。
        """
        if self._maximum or not self.isVisible():
            self._timer.stop()
            return
        self._timer.start()

    def refresh_animation(self) -> None:
        """按当前可见性与上限重新启停动画（从隐藏切到显示时调一次）。

        单独开这个公开方法，是因为 Qt 的 ``showEvent`` 只在**控件自己**被
        隐藏过再显示时才重入；父容器整块显隐（独立页初始只有输入区那种情形）
        不保证触发它，滑块就会停在原地不动。
        """
        self._sync_unknown_state()

    def _advance(self) -> None:
        """未知态：滑块沿轨道来回走，撞到端点换方向。"""
        span = max(self.width() * (1.0 - self._MARGIN_RATIO), 1.0)
        self._offset += self._direction * self._MARGIN_STEP
        if self._offset >= span:
            self._offset, self._direction = span, -1.0
        elif self._offset <= 0:
            self._offset, self._direction = 0.0, 1.0
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().showEvent(event)
        self._sync_unknown_state()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = self.height() / 2
        track = QRectF(0, 0, self.width(), self.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(T.NEUTRAL_SOFT))
        painter.drawRoundedRect(track, radius, radius)
        if not self._maximum:
            # 总量未知：一段等宽的主色块在轨道里来回滑
            width = max(self.width() * self._MARGIN_RATIO, self.height())
            fill = QRectF(self._offset, 0, width, self.height())
            painter.setBrush(QColor(T.ACCENT))
            painter.drawRoundedRect(fill, radius, radius)
            return
        if self._value > 0:
            width = max(self.width() * self.ratio, self.height())
            fill = QRectF(0, 0, width, self.height())
            painter.setBrush(QColor(T.ACCENT))
            painter.drawRoundedRect(fill, radius, radius)


class Pill(QWidget):
    """无圆点的文字胶囊（用于源文件名、计数等标签）。"""

    def __init__(
        self,
        text: str = "",
        fg: str = T.INK_SOFT,
        bg: str = T.SURFACE_SOFT,
        parent=None,
    ):
        """fg/bg 分别是文字色与胶囊底色。"""
        super().__init__(parent)
        self._text = text
        self._fg = fg
        self._bg = bg
        self.setFont(ui_font(T.SIZE_CAPTION))
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def setText(self, text: str) -> None:  # noqa: N802 (对齐 QLabel 习惯)
        """更新文案并按新文案重算宽度。"""
        self._text = text
        self.updateGeometry()
        self.update()

    def text(self) -> str:
        """返回胶囊当前文案。"""
        return self._text

    def sizeHint(self) -> QSize:  # noqa: N802
        metrics = self.fontMetrics()
        return QSize(metrics.horizontalAdvance(self._text) + 20, 24)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        # 允许压缩到 60px：长文件名靠省略号收尾，不把页头撑宽
        return QSize(min(self.sizeHint().width(), 60), 24)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._bg))
        painter.drawRoundedRect(rect, T.RADIUS_SM, T.RADIUS_SM)
        painter.setPen(QColor(self._fg))
        painter.setFont(self.font())
        text = self.fontMetrics().elidedText(
            self._text, Qt.TextElideMode.ElideMiddle, int(rect.width()) - 16
        )
        painter.drawText(
            rect.adjusted(8, 0, -8, 0),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            text,
        )


def icon_pixmap(icon, size: int = 24, color: str = T.INK_FAINT) -> QPixmap:
    """把 FluentIcon 渲染成指定颜色的 pixmap（用于空状态插画）。"""
    pixmap = icon.icon(color=QColor(color)).pixmap(size, size)
    return pixmap



class EmptyState(QWidget):
    """浅色空状态：图标 + 主文案 + 补充说明 + 可选提示。

    原先各预览控件用的是深灰底 + 白字占位，面积大且显得像报错；这里
    统一成浅底 + 灰色图标 + 说明文字，和"还没有内容"的语义一致。
    """

    def __init__(self, text: str, hint: str = "", icon=None, parent=None):
        """icon 传 FluentIcon，会渲染成 44px 灰色图标；hint 为空时该行不占位。"""
        super().__init__(parent)
        self._text = text
        self._hint = hint
        self._icon = icon
        layout = QVBoxLayout(self)
        layout.setContentsMargins(T.SPACE_XL, T.SPACE_XL, T.SPACE_XL, T.SPACE_XL)
        layout.setSpacing(T.SPACE_SM)
        layout.addStretch()
        self._icon_label = QLabel(self)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if icon is not None:
            self._icon_label.setPixmap(icon_pixmap(icon, 44))
        layout.addWidget(self._icon_label)
        self.text_label = QLabel(text, self)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_to(self.text_label, T.SIZE_LABEL, color=T.INK_SOFT)
        layout.addWidget(self.text_label)
        self.hint_label = QLabel(hint, self)
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setWordWrap(True)
        apply_to(self.hint_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.hint_label.setVisible(bool(hint))
        layout.addWidget(self.hint_label)
        layout.addStretch()

    def set_text(self, text: str) -> None:
        """更新主文案。"""
        self._text = text
        self.text_label.setText(text)

    def set_hint(self, hint: str) -> None:
        """更新补充说明；传空串则隐藏该行。"""
        self._hint = hint
        self.hint_label.setText(hint)
        self.hint_label.setVisible(bool(hint))
