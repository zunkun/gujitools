# -*- coding: utf-8 -*-
"""分段开关控件：一行内互斥选择几个视图形态。

从 `desktop/ui/widgets.py` 拆出（见 docs/dev/refactor-modularity.md §3.B）——
它独占 170 行，且只被「去底色结果 / 原图」这类视图切换用到，与 widgets 里
其余通用控件不是一回事。

原 widgets.py 仍 re-export 本类，调用点无需改动。
"""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from desktop.ui import theme as T
from desktop.ui.fonts import ui_font


class _SegmentHit(QWidget):
    """一段的**命中层**：铺在自绘外观之上，只负责收鼠标，一个像素都不画。

    为什么不用 ``QPushButton``：

    - 旧回归守卫明令"切换行里不能再出现按钮"（``rembg`` 用例扫
      ``findChildren(QPushButton)``）；
    - 按钮的 ``clicked`` 要求 press/release 落在同一个控件内，且**双击不发
      ``clicked``**——快速连点两下时第二下会被吞，观感就是"点了两次才切过去"。

    这里**按下即生效**（不等 release），双击也按一次选中处理，命中区由父控件
    按段矩形铺满，因此不存在"只有戳到文字才算"。
    """

    def __init__(self, key: str, owner: "SegmentedToggle") -> None:
        super().__init__(owner)
        self._key = key
        self._owner = owner
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        # 不画背景：外观一律由父控件的 paintEvent 负责（否则会盖住胶囊）
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._owner._activate(self._key)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """双击＝"快速点两下"的第二下：Qt 不把它当 press 派发，这里补上。"""
        self._owner._activate(self._key)
        event.accept()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._owner._set_hover(self._key)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._owner._set_hover(None)

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
        # ⚠️ 必须先于 setFont：字体变更会触发 changeEvent → _sync_hit_geometry，
        #    那时列表还不存在就会在构造期炸掉。
        self._hits: list[_SegmentHit] = []
        self.setFixedHeight(self.HEIGHT)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(ui_font(T.SIZE_BODY))
        # 每段盖一个**命中层**：它不画任何东西，只负责接收鼠标。
        # ⚠️ 只靠自绘控件自己算坐标时，出现"必须戳到文字才算、而且第一下点了
        #    没反应"（用户 2026-10-17 连报两次）。把命中交给一个铺满整段的
        #    子控件后，点段内任何像素都算，且**按下即生效**（不等 release）。
        for key, _text in self._items:
            self._hits.append(_SegmentHit(key, self))

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

    def _spans(self) -> list[tuple[float, float]]:
        """各段在**当前控件宽度**里的横向区间 ``[(左, 右), ...]``。

        段宽（``_segment_widths``）只决定**比例**，真正绘制与命中都用这里
        的结果，并且**永远铺满整个控件**：控件比段宽之和窄（面板被拖窄、
        高 DPI 下字号变大）就等比压缩，宽就等比拉伸。

        ⚠️ 这是"点框即切换"的地基。以前绘制与命中都直接用 ``_segment_widths``
        的绝对像素：控件一旦被布局压缩，右侧那几段就被画到控件外面（看得见
        一截、却点不到），用户只能戳在文字附近才生效（用户 2026-10-17 报）。
        现在"画出来的框"和"能点的框"是同一个矩形，任何尺寸下都不会错位。
        """
        widths = self._segment_widths()
        left_edge, right_edge = 2.0, float(self.width()) - 2.0
        if not widths or right_edge <= left_edge:
            return []
        total = float(sum(widths)) or 1.0
        scale = (right_edge - left_edge) / total
        spans: list[tuple[float, float]] = []
        cursor = left_edge
        for width in widths:
            spans.append((cursor, cursor + width * scale))
            cursor += width * scale
        # 收边：抹掉浮点累计误差，最后一段右边界严格贴住轨道内缘
        spans[-1] = (spans[-1][0], right_edge)
        return spans

    def _index_at(self, x: float) -> int | None:
        """控件横坐标 → 段下标。

        ⚠️ 落在控件内**任何**位置都归到最近的一段（含两端 2px 描边留白与段
        之间的浮点缝隙）：用户点的是"框"，不是"框里的字"，点在框边缘上不该
        没反应（用户 2026-10-17）。
        """
        spans = self._spans()
        if not spans:
            return None
        if x < spans[0][0]:
            return 0
        for index, (start, end) in enumerate(spans):
            if start <= x < end:
                return index
        return len(spans) - 1

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
        self._activate(self._items[index][0])

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """双击＝"快速点两下"的第二下：Qt 不把它当 press 派发，这里补上。"""
        self.mousePressEvent(event)

    def _activate(self, key: str) -> None:
        """选中某一段：更新选中态并发 ``current_changed``。

        ⚠️ **不因为"已经是当前项"提前返回**：滑块可能因为宿主回填/上屏延迟
        停在旧值，此时用户点的正是它——静默忽略会让人以为"点了没反应，得点
        两次"（用户 2026-10-17）。重复发一次信号是幂等的：宿主的
        ``set_kind`` 按现值判等后自然返回。
        """
        if not self._enabled.get(key, False):
            return
        self._current = key
        self._hover = key
        self.update()
        self.current_changed.emit(key)

    def _set_hover(self, key: str | None) -> None:
        """命中层回报的悬停段；禁用段当没悬停（否则会亮一块点不动的地方）。"""
        if key is not None and not self._enabled.get(key, False):
            key = None
        if key != self._hover:
            self._hover = key
            self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_hit_geometry()

    def changeEvent(self, event) -> None:  # noqa: N802
        """字体变了段宽就变了 ⇒ 命中层跟着重铺。"""
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._sync_hit_geometry()

    def _sync_hit_geometry(self) -> None:
        """把命中层铺到各段矩形上——几何与 :meth:`paintEvent` 同源。

        ⚠️ 首段左缘取 0、末段右缘取控件右边、纵向铺满整个高度：轨道圆角
        与 2px 描边留白也算可点区。用户点的是"框"，框的最外一像素同样算。
        """
        spans = self._spans()
        if not spans:
            return
        last = len(spans) - 1
        for i, (hit, (start, end)) in enumerate(zip(self._hits, spans)):
            left = 0 if i == 0 else int(start)
            right = self.width() if i == last else int(round(end))
            hit.setGeometry(left, 0, max(1, right - left), self.HEIGHT)

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        spans = self._spans()
        radius = self.HEIGHT / 2
        # 轨道：内凹灰底胶囊。必须比卡片白底重一档，否则白滑块压上去没边界。
        # ⚠️ 宽度取**控件自身宽度**（不是段宽之和）：被布局压缩/拉伸时轨道跟着
        #    段一起伸缩，才不会出现"轨道画到控件外面"或"右侧露白无法点"。
        painter.setPen(QPen(QColor(T.BORDER), 1))
        painter.setBrush(QColor(T.SURFACE_SUNKEN))
        painter.drawRoundedRect(
            QRectF(0.5, 0.5, max(1.0, self.width() - 1.0), self.HEIGHT - 1),
            radius, radius,
        )
        for index, (key, text) in enumerate(self._items):
            if index >= len(spans):
                break
            start, end = spans[index]
            slot = QRectF(start, 2, end - start, self.HEIGHT - 4)
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
