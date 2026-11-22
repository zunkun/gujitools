# -*- coding: utf-8 -*-
"""勾选页之后浮在页码栏右侧中部的批量操作框（``_SelectBar``）。"""

from __future__ import annotations

from qfluentwidgets import CaptionLabel, PushButton

from desktop.components.imposition.page_list._qt import (
    QColor,
    QFrame,
    QPainter,
    QPen,
    QPoint,
    QRectF,
    QVBoxLayout,
    Qt,
    Signal,
)
from desktop.ui import theme as T
from desktop.ui.widgets import apply_to


class _SelectBar(QFrame):
    """勾选了页之后**浮在页码栏右侧中部**的批量操作框。

    「已选 N 页」计数 +「取消选择」「批量删除」两个按钮（列宽只有 150px，
    两个 74px 的按钮并排摆不下，竖排）。默认悬在页码栏右缘、垂直居中
    （用户 2026-09-30：不要压在底部）；**按住计数行/空白处可拖动**，拖过
    之后就不再自动摆位。取消选择由宿主清空全部勾选——勾选数归零，悬浮框
    随之消失（显隐完全跟着勾选数走，见 ``ImpositionPageList._update_select_bar``）。

    配色（用户 2026-09-30）：「批量删除」**红底高亮**（删除语义，三态红与
    画布红色对齐线 ``canvas.SPINE_COLOR`` 同源）；「取消选择」用**主色浅底**
    标记（跟红色区分开）。⚠️ 按钮配色走**各自控件上的样式表**——按钮没有
    子控件，不踩「样式表进 QFrame 子树填白底」那条坑；框体底色/描边仍然
    自画，描边用 ``BORDER_STRONG``（主题里「浮层/悬浮面板」专用）。
    """

    #: 「批量删除」三态红：常态 / 悬停 / 按下
    _DANGER = ("#E02020", "#C41B1B", "#A81717")
    #: 「取消选择」三态主色浅底：常态 / 悬停 / 按下（ACCENT_SOFT 的加深档）
    _CALM = (T.ACCENT_SOFT, "#D5E9EC", "#C5E0E4")

    clear_requested = Signal()
    delete_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_from = None     # 按下时的光标全局位置（拖动用）
        self._drag_origin: QPoint | None = None   # 按下时自己的位置
        self._user_moved = False   # 用户拖过 → 宿主不再自动摆位
        # 空白处/计数行可拖动：光标给「移动」暗示（按钮自己会盖成手型）
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setToolTip("按住空白处或「已选 N 页」可拖动本悬浮框")
        column = QVBoxLayout(self)
        column.setContentsMargins(10, 8, 10, 8)
        column.setSpacing(T.SPACE_XS)
        self.count_label = CaptionLabel("已选 0 页", self)
        apply_to(self.count_label, T.SIZE_CAPTION, bold=True, color=T.INK)
        column.addWidget(self.count_label)
        self.clear_button = PushButton("取消选择", self)
        apply_to(self.clear_button, T.SIZE_CAPTION)
        self.clear_button.setStyleSheet(
            f"PushButton {{ background-color: {self._CALM[0]};"
            f" color: {T.ACCENT}; border: 1px solid {T.ACCENT};"
            f" border-radius: {T.RADIUS_SM}px; padding: 4px 12px; }}"
            f"PushButton:hover {{ background-color: {self._CALM[1]}; }}"
            f"PushButton:pressed {{ background-color: {self._CALM[2]}; }}"
        )
        self.clear_button.setToolTip("取消所有勾选，悬浮框随之收起")
        self.clear_button.clicked.connect(self.clear_requested)
        column.addWidget(self.clear_button)
        self.delete_button = PushButton("批量删除", self)
        apply_to(self.delete_button, T.SIZE_CAPTION)
        self.delete_button.setStyleSheet(
            f"PushButton {{ background-color: {self._DANGER[0]};"
            f" color: #FFFFFF; border: none;"
            f" border-radius: {T.RADIUS_SM}px; padding: 4px 12px; }}"
            f"PushButton:hover {{ background-color: {self._DANGER[1]}; }}"
            f"PushButton:pressed {{ background-color: {self._DANGER[2]}; }}"
        )
        self.delete_button.setToolTip(
            "删除勾选的拼版页：版面调整丢失，图片释放回未选择列表"
            "（源图不受影响），删除前会再确认。"
        )
        self.delete_button.clicked.connect(self.delete_requested)
        column.addWidget(self.delete_button)

    def set_count(self, count: int) -> None:
        self.count_label.setText(f"已选 {count} 页")

    # ---------------------------------------------------------------- 拖动
    def _cursor_global(self, event):
        """光标的全局位置。

        不用 ``event.globalPosition()``（合成鼠标事件里它不可靠），改把事件
        的本控件坐标经 ``mapToGlobal`` 映射——真实拖动与合成事件下语义一致。
        """
        return self.mapToGlobal(event.position().toPoint())

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_from = self._cursor_global(event)
            self._drag_origin = self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_from is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = self._cursor_global(event) - self._drag_from
            if delta.manhattanLength() > 2:
                host = self.parentWidget()
                # ⚠️ _drag_origin 与 _drag_from 同进同出（mousePressEvent 一起
                # 设、mouseReleaseEvent 一起清），判完前者再判它即可收窄。
                if host is not None and self._drag_origin is not None:
                    x = self._drag_origin.x() + delta.x()
                    y = self._drag_origin.y() + delta.y()
                    x = max(0, min(x, host.width() - self.width()))
                    y = max(0, min(y, host.height() - self.height()))
                    self.move(x, y)
                    self._user_moved = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_from = None
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        painter.setPen(QPen(QColor(T.BORDER_STRONG), 1.0))
        painter.setBrush(QColor(T.SURFACE))
        painter.drawRoundedRect(rect, T.RADIUS_MD, T.RADIUS_MD)
        painter.end()
