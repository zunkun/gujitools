# -*- coding: utf-8 -*-
"""执行日志：底部状态条 + 点击唤出的浮层。

原来日志是页面底部一张常驻卡片——空闲时是一块空白卡占着位置，展开时又把
预览区压扁。现在拆成两层：

- **状态条**（常驻，高 34px，不画卡片底，只画一条上分隔线）：状态圆点 +
  标题 + 最近一条输出，右侧是清空与展开按钮。整条可点，点击即唤出浮层。
  出错时圆点与摘要变红，不打开也能看到。
- **浮层**（按需）：从状态条上方升起，盖在预览区下缘而**不挤压**布局，内含
  完整日志（等宽字体，方便看堆栈与路径）。Esc、点击浮层外或再点状态条关闭。

浮层是状态条父控件（详情页）的子控件，因此只在首次打开时才挂到页面上，
并随状态条的位置/尺寸重排。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QSizePolicy, QWidget,
)
from qfluentwidgets import FluentIcon as FIF, TextEdit, ToolButton

from desktop.ui import theme as T
from desktop.ui.widgets import Card, Divider, apply_to, ui_font

#: 常驻状态条高度
BAR_HEIGHT = 34
#: 浮层默认高度；上方空间不足时自动收窄
POPUP_HEIGHT = 260
#: 浮层与状态条之间的留白
POPUP_GAP = 6
#: 浮层最小高度（再矮就不值得显示了）
POPUP_MIN_HEIGHT = 140

#: 判定"这条输出是错误"的关键字（只看最后一行）
_ERROR_KEYS = ("错误", "失败", "Traceback", "[stderr]", "Error")


def _last_line(text: str) -> str:
    """取最后一条非空行；全空时返回空串。"""
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def apply_log_view_style(view: QTextEdit) -> None:
    """给日志文本域套上"浅底内嵌字段"样式。

    样式必须设在控件自身、而不是写进 `style.py` 的全局 QSS：
    qfluentwidgets 的 `TextEdit` 在构造时会给控件设置自己的样式表，而控件级
    样式表的优先级高于应用级，写在全局 QSS 里的 `#logView` 规则会被它盖掉
    （实测底色始终是白的、描边也不生效）。
    """
    view.setStyleSheet(
        f"QTextEdit#logView {{"
        f" background: {T.SURFACE_SOFT};"
        f" border: 1px solid {T.BORDER};"
        f" border-radius: {T.RADIUS_MD}px;"
        f" padding: 6px 8px;"
        f"}}"
    )


class _LogOverlay(Card):
    """浮在页面上方的日志浮层：标题行 + 完整日志文本域。

    对外的 ``log_view`` 就是这里的 QTextEdit，页面各处沿用
    ``self.log_view.append`` 的既有调用方式。
    """

    def __init__(self, parent=None):
        """构建标题行（含关闭按钮）、分隔线与日志文本域。"""
        super().__init__(
            parent, padding=T.SPACE_SM, spacing=T.SPACE_SM, radius=T.RADIUS_LG,
            fill=T.SURFACE, border=T.BORDER_STRONG,
        )
        self.setObjectName("logOverlay")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        header = QHBoxLayout()
        header.setContentsMargins(T.SPACE_XS, 0, 0, 0)
        header.setSpacing(T.SPACE_SM)
        title = QLabel("执行日志")
        apply_to(title, T.SIZE_CAPTION, bold=True, color=T.INK)
        header.addWidget(title)
        header.addStretch()
        self.close_button = ToolButton(FIF.CLOSE)
        self.close_button.setToolTip("收起日志（Esc）")
        self.close_button.setFixedSize(26, 26)
        header.addWidget(self.close_button)
        self.box.addLayout(header)
        self.box.addWidget(Divider())

        self.log_view = TextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setFont(ui_font(T.SIZE_CAPTION))
        apply_log_view_style(self.log_view)
        self.box.addWidget(self.log_view, 1)


class LogPanel(QWidget):
    """执行日志状态条：一行摘要，点击唤出日志浮层。

    ``log_view`` 属性指向浮层里的 QTextEdit，页面各处沿用既有的
    ``self.log_view.append(...)`` 调用方式，无需改动调用点。
    """

    def __init__(self, parent=None):
        """构建状态条外观与（尚未挂到页面上的）日志浮层。"""
        super().__init__(parent)
        self._expanded = False
        self._filter_installed = False
        # 浮层先建出来（未 show 也未挂父），这样 log_view 在页面组装阶段
        # （self.log_view = self.log_panel.log_view）就已经可用
        self._overlay = _LogOverlay()
        self.log_view = self._overlay.log_view

        self.setFixedHeight(BAR_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("点击查看完整执行日志")

        row = QHBoxLayout(self)
        # 左侧留出 18px 给自绘的状态圆点
        row.setContentsMargins(18, 0, 0, 0)
        row.setSpacing(T.SPACE_SM)

        self.title = QLabel("执行日志")
        apply_to(self.title, T.SIZE_CAPTION, bold=True, color=T.INK_SOFT)
        row.addWidget(self.title)

        self.summary = QLabel("暂无输出")
        apply_to(self.summary, T.SIZE_CAPTION, color=T.INK_FAINT)
        row.addWidget(self.summary, 1)

        self.clear_button = ToolButton(FIF.DELETE)
        self.clear_button.setToolTip("清空日志")
        self.clear_button.setFixedSize(26, 26)
        row.addWidget(self.clear_button)

        self.toggle_button = ToolButton(FIF.UP)
        self.toggle_button.setToolTip("展开 / 收起执行日志")
        self.toggle_button.setFixedSize(26, 26)
        self.toggle_button.clicked.connect(self.toggle)
        row.addWidget(self.toggle_button)

        self.clear_button.clicked.connect(self.log_view.clear)
        self._overlay.close_button.clicked.connect(lambda: self.set_expanded(False))
        self.log_view.textChanged.connect(self._refresh_bar)
        self._sync_arrow()

    # ------------------------------------------------------------------ 状态
    def toggle(self) -> None:
        """在展开 / 收起之间切换（取反当前状态）。"""
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        """展开或收起日志浮层，并同步箭头方向与状态条摘要。

        展开时把浮层挂到页面、定位到状态条正上方并显示，同时滚到底部；
        收起时仅隐藏浮层（日志内容保留）。
        """
        expanded = bool(expanded)
        if expanded:
            self._attach_overlay()
            self._position_overlay()
            self._overlay.show()
            self._overlay.raise_()
            bar = self.log_view.verticalScrollBar()
            bar.setValue(bar.maximum())
            self._install_filter()
        else:
            self._overlay.hide()
            self._remove_filter()
        self._expanded = expanded
        self._sync_arrow()
        self._refresh_bar()

    def _state(self) -> str:
        """当前日志状态：``error`` / ``info`` / ``idle``（决定圆点与摘要颜色）。"""
        text = self.log_view.toPlainText().strip()
        if not text:
            return "idle"
        return "error" if any(k in _last_line(text) for k in _ERROR_KEYS) else "info"

    def _sync_arrow(self) -> None:
        self.toggle_button.setIcon(FIF.DOWN if self._expanded else FIF.UP)

    def _refresh_bar(self) -> None:
        """按日志内容刷新状态圆点与摘要行。"""
        state = self._state()
        if state == "idle":
            self.summary.setText("暂无输出")
            apply_to(self.summary, T.SIZE_CAPTION, color=T.INK_FAINT)
        else:
            elided = self.summary.fontMetrics().elidedText(
                _last_line(self.log_view.toPlainText()),
                Qt.TextElideMode.ElideRight,
                max(self.width() - 180, 120),
            )
            self.summary.setText(elided)
            apply_to(
                self.summary, T.SIZE_CAPTION,
                color=T.DANGER if state == "error" else T.INK_SOFT,
            )
        self.update()

    # ------------------------------------------------------------------ 浮层
    def _attach_overlay(self) -> None:
        """把浮层挂到状态条的父控件（详情页）上，成为覆盖层。"""
        host = self.parentWidget()
        if host is None or self._overlay.parentWidget() is host:
            return
        self._overlay.setParent(host)
        self._overlay.setWindowFlags(Qt.WindowType.Widget)

    def _position_overlay(self) -> None:
        """把浮层定位到状态条正上方，宽度与状态条对齐、高度自适应。"""
        host = self._overlay.parentWidget()
        if host is None:
            return
        top_left = self.mapTo(host, QPoint(0, 0))
        available = top_left.y() - POPUP_GAP
        height = max(POPUP_MIN_HEIGHT, min(POPUP_HEIGHT, available))
        self._overlay.setGeometry(
            top_left.x(), top_left.y() - height, self.width(), height
        )

    # ------------------------------------------------------------- 事件处理
    def _install_filter(self) -> None:
        app = QApplication.instance()
        if app is not None and not self._filter_installed:
            app.installEventFilter(self)
            self._filter_installed = True

    def _remove_filter(self) -> None:
        app = QApplication.instance()
        if app is not None and self._filter_installed:
            app.removeEventFilter(self)
            self._filter_installed = False

    @staticmethod
    def _hit(widget: QWidget, global_pos: QPoint) -> bool:
        """全局坐标是否落在控件可见区域内。"""
        return widget.isVisible() and widget.rect().contains(
            widget.mapFromGlobal(global_pos)
        )

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt 命名)
        """浮层打开期间：Esc 或点击浮层/状态条之外的任意位置即收起。"""
        if not self._expanded:
            return False
        etype = event.type()
        if etype == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.set_expanded(False)
                return True
        elif etype == QEvent.Type.MouseButtonPress:
            pos = event.globalPosition().toPoint()
            # 点状态条本身交给它自己的 mouseRelease 处理（切换），避免闪烁
            if not self._hit(self._overlay, pos) and not self._hit(self, pos):
                self.set_expanded(False)
        return False

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        """点击状态条空白处即可唤出 / 收起浮层。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_bar()
        if self._expanded:
            self._position_overlay()

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        if self._expanded:
            self._position_overlay()

    def paintEvent(self, event) -> None:  # noqa: N802
        """画一条上分隔线与状态圆点（不画卡片底，比整张卡片轻）。"""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(0, 0, self.width(), 1, QColor(T.BORDER_SOFT))
        state = self._state()
        dot = QColor(
            T.DANGER if state == "error"
            else T.ACCENT if state == "info"
            else T.INK_DISABLED
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot)
        painter.drawEllipse(
            QRectF(6.0, self.height() / 2 - 3.5, 7.0, 7.0)
        )
