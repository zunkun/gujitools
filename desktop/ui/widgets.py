# -*- coding: utf-8 -*-
"""基础视觉控件：卡片、分区标题、状态胶囊、空状态、页头。

统一用自绘而非样式表：Qt 的样式表引擎会在子树里有任何 ``setStyleSheet``
时把 QFrame 底色刷成白色，之前步骤条的卡片底就因此被整片盖掉过。自绘
（``paintEvent``）不受此影响，颜色完全可控，也不会污染子控件。

表单控件则相反，一律用 qfluentwidgets 的现成控件（它们自带绘制与焦点
动画），只把高度对齐到 ``CONTROL_HEIGHT``——见 ``combo_box()``。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)
from qfluentwidgets import ComboBox

from desktop.ui import theme as T

_FONT_FAMILY: str | None = None

#: 表单控件统一高度（px）。
#:
#: qfluentwidgets 的 ``LineEdit`` 在构造里写死 ``setFixedHeight(33)``，
#: ``SpinBox`` / ``DoubleSpinBox`` / ``EditableComboBox`` 都继承它，所以
#: 表单输入类天然同高；而 ``ComboBox`` 继承的是 ``QPushButton``，没有这个
#: 约束，实测只有 27px——和同列的输入框并排会明显矮一截。新建下拉框一律
#: 走 ``combo_box()``，由它抬到本高度；``tests/gui_selftest.py`` 有断言保证
#: 这个常量不会和库里的 ``LineEdit`` 实际高度脱节。
CONTROL_HEIGHT = 33


def ui_font(size: int = T.SIZE_BODY, bold: bool = False) -> QFont:
    """统一的界面字体（族名 + 像素字号）。

    族名走 ``resolve_font_family()`` 解析出的系统实际字体，与
    ``apply_app_style`` 给整个应用设置的字体保持一致；否则在没有
    ``Microsoft YaHei UI`` 的机器上，这些控件会各自回退到默认字体，
    和应用其它文字对不上。
    """
    global _FONT_FAMILY
    if _FONT_FAMILY is None:
        from desktop.ui.style import resolve_font_family

        _FONT_FAMILY = resolve_font_family()
    font = QFont(_FONT_FAMILY)
    font.setPixelSize(size)
    font.setBold(bold)
    return font


def apply_to(widget: QWidget, size: int = T.SIZE_BODY, bold: bool = False,
             color: str | None = None) -> QLabel:
    """给 QLabel 统一设置字体与颜色（颜色用调色板，不用样式表）。"""
    widget.setFont(ui_font(size, bold))
    if color:
        palette = widget.palette()
        palette.setColor(widget.foregroundRole(), QColor(color))
        widget.setPalette(palette)
    return widget


def combo_box(
    items: Iterable[str | Sequence[Any]] | None = None,
    width: int | None = None,
) -> ComboBox:
    """创建与输入框同高的下拉框（统一表单的行高节奏）。

    直接在表单里 ``ComboBox()`` 会比同列的 ``LineEdit``/``SpinBox`` 矮
    6px（见 ``CONTROL_HEIGHT`` 的说明），所以下拉框一律用本函数建。

    ``items`` 传字符串序列时只填显示文案；传 ``(文案, 值)`` 二元组序列时
    值写进 ``itemData``，读出用 ``currentData()``。``width`` 非空则固定宽度
    （用于节点行这类需要横向对齐的窄列）。
    """
    combo = ComboBox()
    combo.setFixedHeight(CONTROL_HEIGHT)
    # 它的 minimumSizeHint 偏大，而控制列最窄只有 340px：不放开会把表单
    # 撑出横向边界。表单字段列会自动拉伸，表格单元格内则按列宽收纳。
    combo.setMinimumWidth(0)
    for item in items or ():
        if isinstance(item, str):
            combo.addItem(item)
        else:
            label, value = item
            combo.addItem(label, userData=value)
    if width is not None:
        combo.setFixedWidth(width)
    return combo


class Card(QFrame):
    """白底圆角卡片，可选描边与内边距。"""

    def __init__(self, parent=None, padding: int = T.SPACE_LG,
                 spacing: int = T.SPACE_MD, radius: int = T.RADIUS_LG,
                 fill: str = T.SURFACE, border: str = T.BORDER,
                 layout: str = "v"):
        """
        layout="v"/"h" 选择内部盒方向；padding 同时作为四边内边距。

        内部布局通过 ``self.box`` 暴露，调用方直接往里加控件。
        """
        super().__init__(parent)
        self._fill = QColor(fill)
        self._border = QColor(border) if border else None
        self._radius = radius
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        box = QVBoxLayout(self) if layout == "v" else QHBoxLayout(self)
        box.setContentsMargins(padding, padding, padding, padding)
        box.setSpacing(spacing)
        self.box = box

    def set_colors(self, fill: str | None = None, border: str | None = None) -> None:
        """改底色/描边后立即重绘；传 None 表示该项保持不变。"""
        if fill is not None:
            self._fill = QColor(fill)
        if border is not None:
            self._border = QColor(border)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(self._fill)
        if self._border is not None:
            painter.setPen(QPen(self._border, 1))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, self._radius, self._radius)


class Divider(QFrame):
    """1px 水平分隔线。"""

    def __init__(self, parent=None):
        """固定高 1px、水平拉伸的水平分隔线。"""
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(T.BORDER_SOFT))


class SectionTitle(QLabel):
    """控制面板里的分组小标题（比正文略重，前面带一条主色短竖线）。"""

    def __init__(self, text: str, parent=None):
        """左侧预留 10px 给主色竖线，控件固定高 20px。"""
        super().__init__(text, parent)
        self.setFont(ui_font(T.SIZE_CAPTION, bold=True))
        # 左侧留出 10px 给主色短竖线
        self.setContentsMargins(10, 0, 0, 0)
        self.setFixedHeight(20)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(T.ACCENT))
        painter.drawRoundedRect(QRectF(0, 4, 3, 12), 1.5, 1.5)
        super().paintEvent(event)


class StatusChip(QWidget):
    """状态胶囊：圆点 + 文案 + 浅色底，用于表格里的阶段状态。"""

    def __init__(self, text: str = "", status: str = "pending", parent=None):
        """status 决定圆点与底色，取值见 theme.status_colors。"""
        super().__init__(parent)
        self._text = text
        self._color, self._soft = T.status_colors(status)
        self.setFont(ui_font(T.SIZE_CAPTION))
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

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
    """

    def __init__(self, parent=None, height: int = 6):
        """height 为轨道像素高度（默认 6）。"""
        super().__init__(parent)
        self._value = 0
        self._maximum = 0
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setRange(self, minimum: int, maximum: int) -> None:  # noqa: N802
        """设置上限，并把当前值夹到 [0, maximum]；上限为 0 时归零。"""
        self._maximum = max(int(maximum), 0)
        self._value = min(max(int(minimum), 0), self._maximum) if self._maximum else 0
        self.update()

    def setValue(self, value: int) -> None:  # noqa: N802
        """设置当前值（超出上限时夹到上限）。"""
        self._value = max(0, min(int(value), self._maximum)) if self._maximum else 0
        self.update()

    def value(self) -> int:
        """当前值。"""
        return self._value

    @property
    def ratio(self) -> float:
        """完成比例（0.0~1.0）；尚未设置上限时返回 0.0。"""
        if not self._maximum:
            return 0.0
        return self._value / self._maximum

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = self.height() / 2
        track = QRectF(0, 0, self.width(), self.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(T.NEUTRAL_SOFT))
        painter.drawRoundedRect(track, radius, radius)
        if self._value > 0:
            width = max(self.width() * self.ratio, self.height())
            fill = QRectF(0, 0, width, self.height())
            painter.setBrush(QColor(T.ACCENT))
            painter.drawRoundedRect(fill, radius, radius)


class Pill(QWidget):
    """无圆点的文字胶囊（用于源文件名、计数等标签）。"""

    def __init__(self, text: str = "", fg: str = T.INK_SOFT,
                 bg: str = T.SURFACE_SOFT, parent=None):
        """fg/bg 分别是文字色与胶囊底色。"""
        super().__init__(parent)
        self._text = text
        self._fg = fg
        self._bg = bg
        self.setFont(ui_font(T.SIZE_CAPTION))
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

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
        metrics = self.fontMetrics()
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
            max(80, metrics.horizontalAdvance(text) + 36)
            for _, text in self._items
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


class PageHeader(QWidget):
    """页面头部：左侧标题 + 副标题，右侧操作区。

    带一条底部分隔线，把页头和内容区分开——原来只有一行孤立的标题，
    和下面的内容混在一起，层次不清。
    """

    def __init__(self, title: str, subtitle: str = "", parent=None):
        """固定高 64px；右侧操作区通过 ``self.actions`` 布局添加按钮。"""
        super().__init__(parent)
        self.setFixedHeight(64)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(T.SPACE_XS, 0, T.SPACE_XS, 0)
        layout.setSpacing(T.SPACE_MD)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(2)
        self.title_label = QLabel(title, self)
        apply_to(self.title_label, T.SIZE_TITLE, bold=True, color=T.INK)
        text_column.addWidget(self.title_label)
        self.subtitle_label = QLabel(subtitle, self)
        apply_to(self.subtitle_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.subtitle_label.setVisible(bool(subtitle))
        text_column.addWidget(self.subtitle_label)
        layout.addLayout(text_column)
        layout.addStretch()

        self.actions = QHBoxLayout()
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(T.SPACE_SM)
        layout.addLayout(self.actions)

    def set_subtitle(self, text: str) -> None:
        """设置副标题文案，空串则隐藏副标题行。"""
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(
            0, self.height() - 1, self.width(), 1, QColor(T.BORDER)
        )
