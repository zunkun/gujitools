# -*- coding: utf-8 -*-
"""基础视觉控件：卡片、分区标题、状态胶囊、空状态、页头。

统一用自绘而非样式表：Qt 的样式表引擎会在子树里有任何 ``setStyleSheet``
时把 QFrame 底色刷成白色，之前步骤条的卡片底就因此被整片盖掉过。自绘
（``paintEvent``）不受此影响，颜色完全可控，也不会污染子控件。

表单控件则相反，一律用 qfluentwidgets 的现成控件（它们自带绘制与焦点
动画），只把高度对齐到 ``CONTROL_HEIGHT``——见 ``combo_box()``。
"""

from __future__ import annotations

import textwrap
from collections.abc import Iterable, Sequence
from typing import Any

from PySide6.QtCore import QEvent, QObject, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    ComboBox, FluentLabelBase, Flyout, FlyoutAnimationType, FlyoutView,
    ToolTipFilter, ToolTipPosition, TransparentToolButton,
)

from desktop.ui.fonts import ui_font
from desktop.ui.icons import HELP_CIRCLE
from desktop.ui.segmented_toggle import SegmentedToggle
from desktop.ui import theme as T

#: 本模块是「控件总入口」：``SegmentedToggle`` / ``ui_font`` 的实现已分别迁到
#: ``desktop.ui.segmented_toggle`` 与 ``desktop.ui.fonts``，这里保留同名
#: re-export，调用点不必改。列进 ``__all__`` 是为了让 pyflakes 认账（它不认
#: ``# noqa``，只认 ``__all__``）。
__all__ = [
    "CONTROL_HEIGHT",
    "Card",
    "Divider",
    "EmptyState",
    "HelpButton",
    "PageHeader",
    "Pill",
    "ProgressLine",
    "SectionTitle",
    "SegmentedToggle",
    "StatusChip",
    "apply_to",
    "bold_button",
    "combo_box",
    "icon_pixmap",
    "install_button_pointer_cursor",
    "ui_font",
]

#: 表单控件统一高度（px）。
#:
#: qfluentwidgets 的 ``LineEdit`` 在构造里写死 ``setFixedHeight(33)``，
#: ``SafeSpinBox`` / ``SafeDoubleSpinBox`` / ``EditableComboBox`` 都继承它，所以
#: 表单输入类天然同高；而 ``ComboBox`` 继承的是 ``QPushButton``，没有这个
#: 约束，实测只有 27px——和同列的输入框并排会明显矮一截。新建下拉框一律
#: 走 ``combo_box()``，由它抬到本高度；``tests/gui_selftest.py`` 有断言保证
#: 这个常量不会和库里的 ``LineEdit`` 实际高度脱节。
CONTROL_HEIGHT = 33


def apply_to(
    widget: QWidget,
    size: int = T.SIZE_BODY,
    bold: bool = False,
    color: str | None = None,
) -> QLabel:
    """给 QLabel 统一设置字体与颜色。

    ⚠️ **上色有两条路，按控件类型分流**：

    - qfluentwidgets 的标签（``FluentLabelBase`` 子类：CaptionLabel / BodyLabel /
      StrongBodyLabel / TitleLabel / SubtitleLabel）**不读调色板**——它们用
      ``setStyleSheet("color: …")`` 自己画（``setTextColor``）。对它们只 ``setPalette``
      的话调色板里明明写着红色、**渲染出来仍是黑的**（2026-09-23 用户报「这个红色
      没有修改过来」就是这么来的）。所以必须走 ``setTextColor``。
    - 原生 ``QLabel`` 仍走调色板（原来的做法；对它用样式表反而会牵连子控件，
      见模块头那段"样式表会把 QFrame 底色刷白"的教训）。

    判据用 ``isinstance`` 而不是 ``hasattr(widget, "setTextColor")``：
    ``QTextEdit`` 也有同名方法，但它设的是"以后输入的文字颜色"，语义完全不同。
    """
    widget.setFont(ui_font(size, bold))
    if color:
        if isinstance(widget, FluentLabelBase):
            widget.setTextColor(QColor(color))
        else:
            palette = widget.palette()
            palette.setColor(widget.foregroundRole(), QColor(color))
            widget.setPalette(palette)
    return widget


def bold_button(button: QWidget, bold: bool) -> None:
    """把按钮文字加粗 / 还原（高亮用）。

    ⚠️ **别用 ``setStyleSheet("…{font-weight:bold;}")`` 干这件事**：qfluentwidgets
    给每个按钮的样式表是**整串 setStyleSheet 进去的**（约 7.6KB），里面有一条
    ``PushButton[hasIcon=true] { padding: 5px 12px 6px 36px; }`` —— 图标是
    ``paintEvent`` 手绘在左边 12px 处的，**全靠这 36px 左边距让居中的文字让开**。
    整串替换后 padding 全没了，图标就画到文字上了（2026-09-23 用户报
    「执行本子任务按钮中的图片显示在了文字上面」）。``setFont`` 只动字体，
    不碰样式表；按钮 qss 里没有 ``font:`` 规则，所以控件字体生效。
    """
    font = button.font()
    font.setBold(bold)
    button.setFont(font)


def mark_input_entry(button: QWidget) -> None:
    """给「给这一步喂图片」这类**输入入口**按钮加**常驻红框**。

    用户 2026-10-06："右上角的选择图片还可以选择目录，都是红色框住"、
    "左下角输入图片和目录也用红色框住"。红框的作用是**标识入口**（一眼找到
    该点哪儿喂图片），所以是**常驻**的，不随"缺不缺输入"变。

    ⚠️ **别和"缺输入才亮"的那套高亮混用**：详情页
    ``manifest._set_tool_highlight`` 是**动态**的（补上文件就灭），两套样式
    互相覆盖——动态那套灭的时候会把常驻红框一起抹掉。同一个按钮上**只能**
    选一套：要"入口标识"用本函数，要"缺什么提醒"用 ``_set_tool_highlight``。

    ⚠️ 用样式表而不是换 ``PrimaryPushButton``：那会让这一排工具按钮的
    **尺寸**变掉（文字按钮比图标按钮宽），把页头撑变形（同 ``bold_button``）。
    """
    from desktop.ui import theme as T

    button.setStyleSheet(
        f"ToolButton {{ border: 1.5px solid {T.DANGER};"
        f" border-radius: 6px; background-color: {T.DANGER_SOFT}; }}"
        f"ToolButton:hover {{ background-color: {T.DANGER_SOFT}; }}"
    )


def combo_box(
    items: Iterable[str | Sequence[Any]] | None = None,
    width: int | None = None,
) -> ComboBox:
    """创建与输入框同高的下拉框（统一表单的行高节奏）。

    直接在表单里 ``ComboBox()`` 会比同列的 ``LineEdit``/``SafeSpinBox`` 矮
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

    def __init__(
        self,
        parent=None,
        padding: int = T.SPACE_LG,
        spacing: int = T.SPACE_MD,
        radius: int = T.RADIUS_LG,
        fill: str = T.SURFACE,
        border: str = T.BORDER,
        layout: str = "v",
    ):
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
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

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
        painter.fillRect(0, self.height() - 1, self.width(), 1, QColor(T.BORDER))


#: 阶段说明气泡每行的字符数（按 CJK 字宽估）：太窄频繁折行难读，
#: 太宽气泡会顶到屏幕边。26 字 ≈ 气泡宽 360px 上下。
HELP_TOOLTIP_WIDTH = 26

#: 说明气泡（ToolTip / Flyout）内容最大宽度：与 hover 气泡同宽量级。
HELP_BUBBLE_WIDTH = 360


def _wrap_help_text(text: str, width: int = HELP_TOOLTIP_WIDTH) -> str:
    """把说明按固定字符数折行（ToolTip 气泡的 label 不开 wordWrap，必须预折）。"""
    return "\n".join(textwrap.wrap(text, width=width))


class _WrapFlyoutView(FlyoutView):
    """内容自动换行、整体限宽的 FlyoutView。

    ⚠️ 只给 contentLabel 开 wordWrap + setMaximumWidth **不够**：
    ``FlyoutView._adjustText`` 会先按屏幕宽把内容预折成最长 120 字符的行，
    label 的**期望宽度**（sizeHint）因此很大；气泡（本 view）若不限宽，
    Flyout 就按这个大 hint 撑开，文字却只渲染在左侧 360px 里——
    右侧一大块空白，看起来就是「气泡无限宽」。所以限宽必须加在整个 view 上。
    """

    def __init__(self, title: str, content: str, parent=None):
        super().__init__(title, content, parent=parent)
        self.contentLabel.setWordWrap(True)
        self.contentLabel.setMaximumWidth(HELP_BUBBLE_WIDTH)
        self.setMaximumWidth(HELP_BUBBLE_WIDTH)


class HelpButton(TransparentToolButton):
    """问号帮助按钮：hover 弹 ToolTip 气泡，点击弹/收说明 Flyout。

    各阶段面板（``StagePanel``）与「图片拼版」面板的标题旁都用它——
    说明文字不再平铺在标题下方占高度，全部收进这个按钮。
    """

    def __init__(self, title: str = "", description: str = "", parent=None):
        # ⚠️ 不能写 ``super().__init__(HELP_CIRCLE, parent)``：qfluentwidgets
        # 的图标构造分支内部是 ``self.__init__(parent)`` + 补 ``setIcon``——
        # 这个**虚调用**会带着 (parent) 重新进子类 __init__，改了签名的子类
        # 立刻 TypeError（缺 description）。所以走无图标分支完成 Qt 构造，
        # 图标由下面 setIcon 自己补（ToolButton.setIcon 直收 FluentIconBase）。
        super().__init__(parent)
        self._title = title
        self._description = description
        self._flyout: Flyout | None = None
        self.setIcon(HELP_CIRCLE)
        self.setFixedSize(26, 26)
        self.setIconSize(QSize(18, 18))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # hover 出气泡（ToolTip label 不换行，文字已预折行）
        self.setToolTip(_wrap_help_text(description))
        self.installEventFilter(
            ToolTipFilter(self, showDelay=300, position=ToolTipPosition.BOTTOM)
        )
        self.clicked.connect(self._toggle_help_flyout)

    def _toggle_help_flyout(self) -> None:
        """点问号按钮：弹出/关闭说明 Flyout（再点一次或点气泡外关闭）。

        ⚠️ 用 DROP_DOWN（按钮下方弹出）：按钮在面板顶部，PULL_UP（向上）
        会被屏幕边缘夹到窗口顶端，看起来像弹错了地方。
        """
        if self._flyout is not None and self._flyout.isVisible():
            self._flyout.close()
            return
        view = _WrapFlyoutView(self._title, self._description)
        self._flyout = Flyout.make(
            view, target=self, parent=self.window(),
            aniType=FlyoutAnimationType.DROP_DOWN,
        )
        # Flyout 默认 isDeleteOnClose：点气泡外/再点按钮关闭后 C++ 对象会被
        # 销毁，不清引用的话下次点击就是对已删对象调 isVisible() → RuntimeError
        self._flyout.destroyed.connect(lambda *_: setattr(self, "_flyout", None))


class _ButtonCursorFilter(QObject):
    """全局按钮光标过滤器：按钮首次被布局（Polish 事件）时设手型光标。

    挂在 QApplication 上，覆盖现在和将来创建的所有按钮，不用每个按钮
    单独 setCursor。下拉框（qfluent 的 ``ComboBox`` 继承 ``QPushButton``）
    与复选框是"选择"不是"按压"，保持系统箭头光标。
    """

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.Type.Polish
            and isinstance(obj, QAbstractButton)
            and not isinstance(obj, (QCheckBox, QComboBox))
        ):
            obj.setCursor(Qt.CursorShape.PointingHandCursor)
        return False


def install_button_pointer_cursor(app: QApplication) -> None:
    """给整个应用的按钮启用 hover 手型光标（见 :class:`_ButtonCursorFilter`）。"""
    guard = getattr(app, "_button_cursor_filter", None)
    if guard is None:
        guard = _ButtonCursorFilter(app)
        app._button_cursor_filter = guard  # 过滤器必须保引用，否则被 GC 摘掉
        app.installEventFilter(guard)
