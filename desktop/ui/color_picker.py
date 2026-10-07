# -*- coding: utf-8 -*-
"""文字颜色选择器：触发器按钮 + 弹出面板（内置常用色块 + 完整取色）。

用户 2026-10-01 定的三件事（图片编辑 → 文字工具）：

1. **常用色块搬进面板里**——原来 6 个色块散在选项行上，既挤、又和"颜色"这个
   概念分了家；现在统一收进选择器，选项行只留一个颜色按钮；
2. 选择器要**好看**：当前色预览、饱和度/明度方块、色相条、常用色、十六进制
   输入，全部走 ``desktop.ui.theme`` 的令牌，跟其它界面同一套配色；
3. 任意色仍要能取（色相/明度方块 + 十六进制可输入）。

为什么不用 qfluentwidgets 的 ``ColorPickerButton``
--------------------------------------------------
- 它把常用色块留在**外面**（本需求正是要收进去）；
- 它开的是 488×696 的遮罩大对话框 ``ColorDialog``，而且本应用**不加载 .qm
  翻译**，里面全是英文 ``OK`` / ``Cancel`` / ``Edit Color``，与全中文界面不搭。

⚠️ 面板里所有可点控件都是 ``NoFocus``：选项行一旦抢走键盘焦点，画布上正在
就地编辑的文字块就丢焦点、光标消失（用户 2026-10-01 报的"字号不生效"根因
就是焦点被抢）。触发器在面板关闭时补发 ``panelClosed``，宿主据此把焦点还给
文字块，接着打字不中断。
"""

from __future__ import annotations

from typing import Iterable, cast

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
    QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from desktop.ui import theme as T
from desktop.ui.fonts import ui_font

#: 预设色块的边长（px）——6 个一行刚好铺满面板内宽（6×30 + 5×8 = 220）
SWATCH_SIZE = 30
#: 面板宽度（px）。内宽 = 268 − 2×14 = 240
PANEL_WIDTH = 268


class SwatchButton(QAbstractButton):
    """面板里的预设色块：圆角方块，悬停描边、选中打勾。

    底色描边是必需的：白粉/浅色块压在白色面板上，没有描边就"不存在"。
    打勾颜色按底色明度自适应（亮底用墨色、暗底用白色），任何色都看得清。
    """

    def __init__(self, color: QColor, name: str = "", parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._selected = False
        self._hover = False
        self.setFixedSize(SWATCH_SIZE, SWATCH_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 不抢画布焦点
        self.setToolTip(name or self._color.name().upper())

    def color(self) -> QColor:
        """这个色块代表的颜色。"""
        return QColor(self._color)

    def is_selected(self) -> bool:
        """当前是否被标为"选中的那一个"。"""
        return self._selected

    def set_selected(self, selected: bool) -> None:
        selected = bool(selected)
        if selected != self._selected:
            self._selected = selected
            self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        chip = QRectF(self.rect()).adjusted(2.5, 2.5, -2.5, -2.5)
        painter.setPen(QPen(QColor(0, 0, 0, 32), 1.0))
        painter.setBrush(self._color)
        painter.drawRoundedRect(chip, 7.0, 7.0)
        if self._selected:
            painter.setPen(QPen(QColor(T.ACCENT), 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(chip, 7.0, 7.0)
            self._draw_check(painter, chip)
        elif self._hover:
            painter.setPen(QPen(QColor(T.ACCENT), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0), 8.0, 8.0)

    def _draw_check(self, painter: QPainter, chip: QRectF) -> None:
        """在色块中央画对勾（颜色按底色明暗反转，保证对比度）。"""
        ink = QColor(T.INK) if self._color.lightnessF() > 0.6 \
            else QColor("#ffffff")
        pen = QPen(ink, 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        center = chip.center()
        half = chip.width() * 0.24
        path = QPainterPath()
        path.moveTo(center.x() - half, center.y() + half * 0.05)
        path.lineTo(center.x() - half * 0.15, center.y() + half * 0.8)
        path.lineTo(center.x() + half, center.y() - half * 0.75)
        painter.drawPath(path)


class _PreviewChip(QWidget):
    """当前色小预览块（只显示，不交互）。"""

    def __init__(self, color: QColor, size: int = 22, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(size, size)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(0, 0, 0, 38), 1.0))
        painter.setBrush(self._color)
        painter.drawRoundedRect(rect, 6.0, 6.0)


class ColorArea(QWidget):
    """饱和度 / 明度方块：横轴 = 饱和度（左灰右艳），纵轴 = 明度（上亮下暗）。

    底色用**三层渐变**叠出来（纯色相 → 白到透明 → 透明到黑），而不是逐像素
    算 HSV：200×120 的方块逐像素在 Python 里要几十毫秒，拖动色相条时会卡。
    渐变结果按 (尺寸, 色相) 缓存，拖动游标时一次都不用重画。
    """

    picked = Signal(float, float)  # 饱和度 0~1、明度 0~1

    HEIGHT = 116
    RADIUS = 8.0
    #: 游标半径。游标圆心只在**四边内缩一个半径**的范围里走，贴到极值
    #: （黑/纯色）时整颗圆还在方块里，不会被裁成四分之一圆。
    CURSOR_R = 7.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0.0
        self._sat = 0.0
        self._val = 0.0
        self._base: QPixmap | None = None
        self._base_key: tuple | None = None
        self.setFixedHeight(self.HEIGHT)
        self.setMinimumWidth(120)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_hsv(self, hue: float, sat: float, val: float) -> None:
        """程序化同步（不发 ``picked``）。"""
        self._hue, self._sat, self._val = float(hue), float(sat), float(val)
        self.update()

    def _cursor_area(self) -> QRectF:
        """游标**圆心**的活动范围（见 ``CURSOR_R``）；取值映射也按它算。"""
        return QRectF(self.rect()).adjusted(
            self.CURSOR_R, self.CURSOR_R, -self.CURSOR_R, -self.CURSOR_R)

    def _cursor_point(self) -> QPointF:
        """当前 (饱和度, 明度) 对应的游标圆心。"""
        area = self._cursor_area()
        return QPointF(area.left() + self._sat * area.width(),
                       area.top() + (1.0 - self._val) * area.height())

    def _base_pixmap(self) -> QPixmap:
        key = (self.width(), self.height(), round(self._hue, 4))
        if self._base is None or self._base_key != key:
            width, height = max(1, self.width()), max(1, self.height())
            pixmap = QPixmap(width, height)
            rect = QRectF(0, 0, width, height)
            painter = QPainter(pixmap)
            painter.fillRect(rect, QColor.fromHsvF(self._hue % 1.0, 1.0, 1.0))
            white = QLinearGradient(rect.topLeft(), rect.topRight())
            white.setColorAt(0.0, QColor(255, 255, 255, 255))
            white.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, white)
            black = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            black.setColorAt(0.0, QColor(0, 0, 0, 0))
            black.setColorAt(1.0, QColor(0, 0, 0, 255))
            painter.fillRect(rect, black)
            painter.end()
            self._base, self._base_key = pixmap, key
        return self._base

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(rect, self.RADIUS, self.RADIUS)
        painter.setClipPath(clip)
        painter.drawPixmap(rect.topLeft(), self._base_pixmap())
        painter.setClipping(False)
        painter.setPen(QPen(QColor(T.BORDER), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)
        # 游标：内外双色圈，亮底暗底都看得见
        point = self._cursor_point()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 90), 3.0))
        painter.drawEllipse(point, self.CURSOR_R, self.CURSOR_R)
        painter.setPen(QPen(QColor("#ffffff"), 2.0))
        painter.drawEllipse(point, self.CURSOR_R, self.CURSOR_R)

    def _pick(self, pos: QPointF) -> None:
        area = self._cursor_area()
        self._sat = min(1.0, max(0.0, (pos.x() - area.left())
                                / max(1.0, area.width())))
        self._val = 1.0 - min(1.0, max(0.0, (pos.y() - area.top())
                                     / max(1.0, area.height())))
        self.update()
        self.picked.emit(self._sat, self._val)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._pick(event.position())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._pick(event.position())
            event.accept()
            return
        super().mouseMoveEvent(event)


class HueBar(QWidget):
    """色相条：0~359 的彩虹渐变，拖动/点击改色相。"""

    picked = Signal(float)  # 色相 0~1

    HEIGHT = 20
    BAR = 12
    KNOB = 17

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0.0
        self.setFixedHeight(self.HEIGHT)
        self.setMinimumWidth(120)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_hue(self, hue: float) -> None:
        """程序化同步（不发 ``picked``）。"""
        self._hue = float(hue)
        self.update()

    def _bar_rect(self) -> QRectF:
        """色相条几何：左右各内缩半个滑块，滑块贴到两端也不会被裁掉。"""
        rect = QRectF(self.rect())
        inset = self.KNOB / 2.0
        return QRectF(rect.left() + inset, rect.center().y() - self.BAR / 2.0,
                      max(1.0, rect.width() - 2 * inset), self.BAR)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar = self._bar_rect()
        clip = QPainterPath()
        clip.addRoundedRect(bar, self.BAR / 2.0, self.BAR / 2.0)
        painter.setClipPath(clip)
        gradient = QLinearGradient(bar.topLeft(), bar.topRight())
        for step in range(7):
            ratio = step / 6.0
            gradient.setColorAt(ratio, QColor.fromHsvF(min(0.9999, ratio), 1.0, 1.0))
        painter.fillRect(bar, gradient)
        painter.setClipping(False)
        painter.setPen(QPen(QColor(0, 0, 0, 36), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(bar, self.BAR / 2.0, self.BAR / 2.0)
        # 滑块：白底圆点 + 当前色相的内圆
        center_y = QRectF(self.rect()).center().y()
        x = min(bar.right(), max(bar.left(),
                                 bar.left() + self._hue * bar.width()))
        knob = QRectF(x - self.KNOB / 2.0, center_y - self.KNOB / 2.0,
                      self.KNOB, self.KNOB)
        painter.setPen(QPen(QColor(T.BORDER_STRONG), 1.0))
        painter.setBrush(QColor(T.SURFACE))
        painter.drawEllipse(knob)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor.fromHsvF(self._hue % 1.0, 1.0, 1.0))
        painter.drawEllipse(knob.adjusted(3.5, 3.5, -3.5, -3.5))

    def _pick(self, pos: QPointF) -> None:
        bar = self._bar_rect()
        self._hue = min(1.0, max(0.0, (pos.x() - bar.left())
                                / max(1.0, bar.width())))
        self.update()
        self.picked.emit(self._hue)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._pick(event.position())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._pick(event.position())
            event.accept()
            return
        super().mouseMoveEvent(event)


class ColorPickerPopup(QWidget):
    """颜色面板（弹出层）：当前色 + 明度/饱和度方块 + 色相条 + 常用色 + 十六进制。

    ⚠️ 自己开一个 ``Qt.Popup`` 顶层窗口，而不是用 ``RoundMenu``：面板里有可
    输入的 ``QLineEdit``，塞进 QMenu 里键盘事件会被菜单抢走，十六进制根本没法
    敲。``Qt.Popup`` 自带"点外面就关"的语义，正是要的。
    """

    colorChanged = Signal(QColor)
    #: 面板关闭（宿主据此把键盘焦点还给画布上的文字块）
    closed = Signal()

    #: 面板四周给投影留的边距（QGraphicsDropShadowEffect 要有地方铺开）
    SHADOW_MARGIN = 14

    def __init__(self, color: QColor, swatches: Iterable = (), parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._hue = 0.0
        self._sat = 0.0
        self._val = 0.0
        self._color = QColor(color)

        card = QFrame(self)
        card.setObjectName("colorPickerCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(
            f"#colorPickerCard {{"
            f" background-color: {T.SURFACE};"
            f" border: 1px solid {T.BORDER};"
            f" border-radius: {T.RADIUS_MD}px; }}"
        )
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(30.0)
        shadow.setOffset(0.0, 8.0)
        shadow.setColor(QColor(26, 29, 33, 70))
        card.setGraphicsEffect(shadow)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*([self.SHADOW_MARGIN] * 4))
        outer.addWidget(card)

        box = QVBoxLayout(card)
        box.setContentsMargins(14, 12, 14, 14)
        box.setSpacing(10)

        # ---- 标题行：左"文字颜色"、右当前色预览 + 十六进制输入 ----
        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel("文字颜色", card)
        title.setFont(ui_font(T.SIZE_CAPTION))
        title.setStyleSheet(f"color: {T.INK_SOFT}; background: transparent;")
        head.addWidget(title)
        head.addStretch(1)
        self._preview = _PreviewChip(self._color, 22, card)
        head.addWidget(self._preview)
        self._hex = QLineEdit(card)
        self._hex.setFixedSize(90, 26)
        self._hex.setMaxLength(7)
        self._hex.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hex.setFont(ui_font(T.SIZE_CAPTION))
        self._hex.setStyleSheet(
            f"QLineEdit {{"
            f" background-color: {T.SURFACE_SOFT};"
            f" border: 1px solid {T.BORDER};"
            f" border-radius: {T.RADIUS_SM}px;"
            f" padding: 2px 6px; color: {T.INK};"
            f" selection-background-color: {T.ACCENT}; }}"
            f"QLineEdit:focus {{ border-color: {T.ACCENT};"
            f" background-color: {T.SURFACE}; }}"
        )
        head.addWidget(self._hex)
        box.addLayout(head)

        # ---- 明度/饱和度方块 + 色相条 ----
        self._area = ColorArea(card)
        box.addWidget(self._area)
        self._hue_bar = HueBar(card)
        box.addWidget(self._hue_bar)

        # ---- 常用色（原来散在选项行上的那排，现在收进面板） ----
        box.addWidget(self._separator(card))
        label = QLabel("常用色", card)
        label.setFont(ui_font(T.SIZE_CAPTION))
        label.setStyleSheet(f"color: {T.INK_FAINT}; background: transparent;")
        box.addWidget(label)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._swatches: list[SwatchButton] = []
        for item in swatches:
            name, value = item if isinstance(item, (tuple, list)) else ("", item)
            swatch = SwatchButton(QColor(value), str(name), card)
            swatch.clicked.connect(
                lambda _=False, s=swatch: self._pick_swatch(s))
            self._swatches.append(swatch)
            row.addWidget(swatch)
        row.addStretch(1)
        box.addLayout(row)

        self._area.picked.connect(self._on_area_picked)
        self._hue_bar.picked.connect(self._on_hue_picked)
        self._hex.textEdited.connect(self._on_hex_edited)
        self._apply_color(self._color, notify=False)
        self.setFixedWidth(PANEL_WIDTH)

    @staticmethod
    def _separator(parent: QWidget) -> QFrame:
        """1px 分隔线（用 BORDER_SOFT，比常规描边轻，只做分区不做边框）。"""
        line = QFrame(parent)
        line.setFixedHeight(1)
        line.setStyleSheet(
            f"background-color: {T.BORDER_SOFT}; border: none;")
        return line

    # ------------------------------------------------------------ 取色
    def color(self) -> QColor:
        """面板当前颜色。"""
        return QColor(self._color)

    def set_color(self, color: QColor, notify: bool = False) -> None:
        """程序化设色（不发 ``colorChanged`` 除非 ``notify``）。"""
        self._apply_color(color, notify=notify)

    def _apply_color(self, color: QColor, notify: bool = True) -> None:
        """把颜色灌进面板各控件（并可选对外发信号）。

        ⚠️ 灰度色（黑/白/灰）的色相是 -1：此时**保留原色相**，否则拖明度到
        最暗再往上拉，色相条会莫名其妙跳回红色。
        """
        color = QColor(color)
        if not color.isValid():
            return
        # ⚠️ PySide6 存根把 ``QColor.getHsvF()`` 的返回标成 ``object``（实际是
        # ``(h, s, v, a)`` 四元组），故显式 cast 一次再解包。
        hue, sat, val, _ = cast(
            "tuple[float, float, float, float]", color.getHsvF()
        )
        if hue >= 0:
            self._hue = hue
        self._sat, self._val = sat, val
        self._color = color
        self._area.set_hsv(self._hue, self._sat, self._val)
        self._hue_bar.set_hue(self._hue)
        self._preview.set_color(color)
        wanted = color.name().upper()
        if self._hex.text().upper() != wanted:
            self._hex.setText(wanted)
        self._sync_swatches()
        if notify:
            self.colorChanged.emit(QColor(color))

    def _sync_swatches(self) -> None:
        """把与当前色一致的色块标为选中。"""
        current = self._color.name().lower()
        for swatch in self._swatches:
            swatch.set_selected(swatch.color().name().lower() == current)

    def _on_area_picked(self, sat: float, val: float) -> None:
        self._apply_color(
            QColor.fromHsvF(self._hue % 1.0, sat, val), notify=True)

    def _on_hue_picked(self, hue: float) -> None:
        self._apply_color(
            QColor.fromHsvF(hue % 1.0, self._sat, self._val), notify=True)

    def _on_hex_edited(self, text: str) -> None:
        raw = text.strip()
        if raw and not raw.startswith("#"):
            raw = "#" + raw
        color = QColor(raw)
        if color.isValid():
            self._apply_color(color, notify=True)

    def _pick_swatch(self, swatch: SwatchButton) -> None:
        """点常用色：整块换色并**收起面板**——常用色就是"一击即换"的路径。"""
        self._apply_color(swatch.color(), notify=True)
        self.hide()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self.closed.emit()


class ColorPickerButton(QAbstractButton):
    """文字颜色触发器：色点 + 十六进制 + 下拉箭头；点开弹出颜色面板。

    自带绘制（不走 qfluentwidgets 的 ``ColorPickerButton``）：那个是个 96×32
    的纯色块，看不出当前色值，也不带下拉指示。
    """

    colorChanged = Signal(QColor)
    #: 面板关闭（宿主据此把键盘焦点还给画布上的文字块）
    panelClosed = Signal()

    HEIGHT = 32
    CHIP = 16

    def __init__(self, color: QColor, swatches: Iterable = (),
                 title: str = "文字颜色", parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._swatches = tuple(swatches)
        self._title = title
        self._popup: ColorPickerPopup | None = None
        self._hover = False
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # ⚠️ NoFocus：见模块头——选项行抢焦点会让画布上的文字丢光标
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFont(ui_font(T.SIZE_CAPTION))
        self.setToolTip("文字颜色（常用色 + 任意色）")
        self.clicked.connect(self._toggle_popup)

    # ------------------------------------------------------------ 取值/设值
    def color(self) -> QColor:
        """当前颜色。"""
        return QColor(self._color)

    def set_color(self, color: QColor, notify: bool = False) -> None:
        """程序化设色（同步面板，不发信号除非 ``notify``）。"""
        color = QColor(color)
        if not color.isValid():
            return
        self._color = color
        self.update()
        if self._popup is not None:
            self._popup.set_color(color)
        if notify:
            self.colorChanged.emit(QColor(color))

    # ------------------------------------------------------------ 弹出面板
    def popup(self) -> ColorPickerPopup | None:
        """当前面板（没开过/已销毁则 None）——自测用。"""
        return self._popup

    def _toggle_popup(self) -> None:
        if self._popup is not None and self._popup.isVisible():
            self._popup.hide()
            return
        self._open_popup()

    def _ensure_popup(self) -> ColorPickerPopup:
        """面板只建一次、之后复用（每次新建都会攒下一个隐藏的旧窗口）。"""
        if self._popup is None:
            popup = ColorPickerPopup(self._color, self._swatches, self)
            popup.colorChanged.connect(self._on_popup_color)
            popup.closed.connect(self.panelClosed)
            self._popup = popup
        return self._popup

    def _open_popup(self) -> None:
        popup = self._ensure_popup()
        popup.set_color(self._color)  # 每次都从当前色重新铺开
        popup.adjustSize()
        popup.move(self._popup_pos(popup.size()))
        popup.show()

    def _popup_pos(self, size: QSize) -> QPoint:
        """面板落点：默认贴按钮下沿，越界就上翻/内收，别跑出屏幕。"""
        below = self.mapToGlobal(QPoint(0, self.height() + 6))
        screen = QApplication.screenAt(below) or QApplication.primaryScreen()
        if screen is None:
            return below
        area = screen.availableGeometry()
        x = min(below.x(), area.right() - size.width() + 1)
        y = below.y()
        if y + size.height() > area.bottom() + 1:
            above = self.mapToGlobal(QPoint(0, 0)).y() - size.height() - 6
            y = above if above >= area.top() else area.bottom() - size.height() + 1
        return QPoint(max(area.left(), x), max(area.top(), y))

    def _on_popup_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()
        self.colorChanged.emit(QColor(color))

    # ------------------------------------------------------------ 绘制
    def sizeHint(self) -> QSize:  # noqa: N802
        metrics = QFontMetrics(self.font())
        return QSize(
            12 + self.CHIP + 8 + metrics.horizontalAdvance("#FFFFFF")
            + 10 + 12 + 12,
            self.HEIGHT,
        )

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        active = self._hover or self.isDown() or (
            self._popup is not None and self._popup.isVisible())
        painter.setPen(QPen(QColor(T.ACCENT if active else T.BORDER), 1.0))
        painter.setBrush(QColor(T.SURFACE_HOVER if active else T.SURFACE))
        painter.drawRoundedRect(rect, T.RADIUS_SM, T.RADIUS_SM)

        chip = QRectF(rect.left() + 12, rect.center().y() - self.CHIP / 2.0,
                      self.CHIP, self.CHIP)
        painter.setPen(QPen(QColor(0, 0, 0, 40), 1.0))
        painter.setBrush(self._color)
        painter.drawRoundedRect(chip, 4.0, 4.0)

        arrow = 20.0
        text_rect = QRectF(chip.right() + 8, rect.top(),
                           max(1.0, rect.right() - arrow - chip.right() - 8),
                           rect.height())
        painter.setFont(self.font())
        painter.setPen(QColor(T.INK))
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            self._color.name().upper(),
        )
        self._draw_chevron(painter, QPointF(rect.right() - 13, rect.center().y()))

    @staticmethod
    def _draw_chevron(painter: QPainter, center: QPointF) -> None:
        pen = QPen(QColor(T.INK_SOFT), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(center.x() - 4.0, center.y() - 2.0)
        path.lineTo(center.x(), center.y() + 2.0)
        path.lineTo(center.x() + 4.0, center.y() - 2.0)
        painter.drawPath(path)
