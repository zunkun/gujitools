# -*- coding: utf-8 -*-
"""分段开关控件：一行内互斥选择几个视图形态。

从 `desktop/ui/widgets.py` 拆出（见 docs/dev/refactor-modularity.md §3.B）——
它独占 170 行，且只被「去底色结果 / 原图」这类视图切换用到，与 widgets 里
其余通用控件不是一回事。

原 widgets.py 仍 re-export 本类，调用点无需改动。
"""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from desktop.ui import theme as T
from desktop.ui.fonts import ui_font

class SegmentedToggle(QWidget):
    """分段开关：一行内互斥选择几个视图形态。

    用于「去底色结果 / 原图」这类同一视图的形态切换。自绘而非用
    qfluentwidgets 的 ``SegmentedWidget``——后者是给页面导航设计的
    （底部指示条、无法单独禁用某一项），而这里需要「还没有去底色结果时
    禁用其中一项」的语义。

    **选中态要一眼看得出**，所以三处一起给对比度（只靠白底滑块是不够的，
    浅底卡片上白滑块几乎看不出来）：

    - 轨道用 ``SURFACE_SUNKEN``（比 ``SURFACE_SOFT`` 明显重一档的灰底），
      白滑块压在上面才有边界；
    - 选中项文字用主色 ``ACCENT`` 且加粗，未选中项用 ``INK_SOFT``；
    - 禁用项转 ``INK_DISABLED``，比「未选中但可用」再淡一档，不会混淆。

    只有用户点击才发 ``current_changed``；``set_current`` 是程序化切换，
    不发信号（否则回流切换会自我递归）。
    """

    current_changed = Signal(str)

    #: 控件高度（px）。比表单控件（``CONTROL_HEIGHT``）略矮——它不在表单里，
    #: 是压在预览视图上的一条轻量开关。
    HEIGHT = 30

    def __init__(self, items: Sequence[Sequence[str]], parent=None):
        """items 为 ``[(键, 文案), ...]``，默认选中第一项。"""
        super().__init__(parent)
        self._items = [(str(key), str(text)) for key, text in items]
        self._enabled = {key: True for key, _ in self._items}
        self._current = self._items[0][0] if self._items else ""
        self._hover: str | None = None
        self.setFixedHeight(self.HEIGHT)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(ui_font(T.SIZE_BODY))

    # ------------------------------------------------------------------ API
    def current(self) -> str:
        """当前选中项的键。"""
        return self._current

    def set_current(self, key: str) -> None:
        """程序化切换选中项，不发 ``current_changed``。"""
        if key != self._current:
            self._current = key
            self.update()

    def set_item_enabled(self, key: str, enabled: bool) -> None:
        """启用/禁用某一项；禁用项不可悬停、不可点击，文案变灰。"""
        if key in self._enabled and self._enabled[key] != enabled:
            self._enabled[key] = enabled
            if not enabled and self._hover == key:
                self._hover = None
            self.update()

    def is_item_enabled(self, key: str) -> bool:
        """某一项当前是否可用。"""
        return self._enabled.get(key, False)

    # ------------------------------------------------------------------ 几何
    def _text_font(self, bold: bool) -> QFont:
        """取本控件字体的一份副本，按需加粗（选中项用粗体强化选中感）。"""
        font = self.font()
        font.setBold(bold)
        return font

    def _segment_widths(self) -> list[int]:
        """各段宽度：文案宽 + 左右内边距，并设下限避免短词被压成窄条。

        按**粗体**度量算宽度：选中项是粗体，若按常规字重算，「去底色结果」
        变粗后文字会顶到滑块边缘。
        """
        metrics = QFontMetrics(self._text_font(True))
        return [
            max(80, metrics.horizontalAdvance(text) + 36) for _, text in self._items
        ]

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSizeHint()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(sum(self._segment_widths()) + 4, self.HEIGHT)

    def _index_at(self, x: float) -> int | None:
        """控件横坐标 → 段下标；落在轨道两端留白时返回 None。"""
        left = 2
        for index, width in enumerate(self._segment_widths()):
            if left <= x < left + width:
                return index
            left += width
        return None

    # ------------------------------------------------------------------ 交互
    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        index = self._index_at(event.position().x())
        key = None
        if index is not None:
            candidate = self._items[index][0]
            if self._enabled[candidate]:
                key = candidate
        if key != self._hover:
            self._hover = key
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover is not None:
            self._hover = None
            self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        index = self._index_at(event.position().x())
        if index is None:
            return
        key = self._items[index][0]
        if not self._enabled[key] or key == self._current:
            return
        self._current = key
        self._hover = key
        self.update()
        self.current_changed.emit(key)

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        widths = self._segment_widths()
        radius = self.HEIGHT / 2
        # 轨道：内凹灰底胶囊。必须比卡片白底重一档，否则白滑块压上去没边界
        painter.setPen(QPen(QColor(T.BORDER), 1))
        painter.setBrush(QColor(T.SURFACE_SUNKEN))
        painter.drawRoundedRect(
            QRectF(0.5, 0.5, sum(widths) + 3, self.HEIGHT - 1), radius, radius
        )
        left = 2
        for index, (key, text) in enumerate(self._items):
            width = widths[index]
            slot = QRectF(left, 2, width, self.HEIGHT - 4)
            if key == self._current:
                self._draw_thumb(painter, slot)
                color, bold = T.ACCENT, True
            elif key == self._hover:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(T.SURFACE_HOVER))
                painter.drawRoundedRect(slot, radius - 2, radius - 2)
                color, bold = T.INK_SOFT, False
            else:
                color = T.INK_SOFT if self._enabled[key] else T.INK_DISABLED
                bold = False
            painter.setFont(self._text_font(bold))
            painter.setPen(QColor(color))
            painter.drawText(slot, int(Qt.AlignmentFlag.AlignCenter), text)
            left += width

    @staticmethod
    def _draw_thumb(painter: QPainter, slot: QRectF) -> None:
        """选中项的白底滑块：先垫一层投影，再画白底与描边。

        投影在灰轨道上必须有——只靠「白 vs 灰」的色差，滑块边界会显得发毛。
        """
        radius = slot.height() / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(26, 29, 33, 28))
        painter.drawRoundedRect(slot.adjusted(0.5, 1.0, -0.5, 0.5), radius, radius)
        painter.setPen(QPen(QColor(T.BORDER), 1))
        painter.setBrush(QColor(T.SURFACE))
        painter.drawRoundedRect(slot.adjusted(0.5, 0.5, -0.5, -1.0), radius, radius)
