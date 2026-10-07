# -*- coding: utf-8 -*-
"""画布上的**就地编辑文字块**（从 ``image_editor.py`` 拆出）。

``TextBlockItem`` 只依赖画布的少量回调（``_move_text_outline`` /
``_hide_text_outline`` / ``_active_text_block``），刻意不 import 画布，
避免循环依赖。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QGraphicsItem, QGraphicsTextItem

if TYPE_CHECKING:
    # ⚠️ 声明成画布的**宿主面**而不是 ``EditorCanvas`` 本身：文字块只
    # 用得上这几个回调，而拆分后 ``self`` 是 ``TextMixin``（不是
    # ``EditorCanvas``），写后者会让 ``item._canvas = self`` 报类型错。
    from .canvas._host import CanvasHost

class TextBlockItem(QGraphicsTextItem):
    """画布上的待插入文字块：就地编辑（光标可见），按住拖动整体移动。

    交互口径：**单击**进编辑态放光标（QGraphicsTextItem 原生），**按住
    拖动**超过阈值 = 移动整块。刻意不复用 ``ItemIsMovable``——它与文本
    编辑的"按住选字"打架，这里按位移阈值自己分流。拖动全程由画布的
    **边界虚线框**跟随（悬停即显示、松手即消失），用户随时知道"这一块
    会被整体挪走"（用户 2026-10-01：手机作图式文字）。
    """

    #: 按下后位移超过该值（图片像素）判定为拖动，否则视为点击放光标
    DRAG_THRESHOLD = 4.0

    def __init__(self, pos: QPointF, px: int, color: QColor, family: str):
        super().__init__()
        self.setPos(pos)
        # 文档默认有 4px 边距，会让"烧进图片"的位置比屏幕所见偏右下
        self.document().setDocumentMargin(0.0)
        font = QFont(family)
        font.setPixelSize(max(1, int(px)))
        self.setFont(font)
        self.setDefaultTextColor(color)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self._moving = False
        self._press_scene = QPointF()
        self._canvas: "CanvasHost | None" = None  # add_text_block 回填

    def apply_style(self, family: str, px: int, color: QColor) -> None:
        """选项行改字体/字号/颜色时对块即时生效（编辑中也能改）。

        ⚠️ 是**整块**生效：setFont/setDefaultTextColor 作用于整个文档，
        与手机作图App一致——样式是段落属性，不做逐字混排。
        """
        font = self.font()
        font.setFamily(family)
        font.setPixelSize(max(1, int(px)))
        self.setFont(font)
        self.setDefaultTextColor(color)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._moving = False
            self._press_scene = event.scenePos()
            if self._canvas is not None:
                self._canvas._move_text_outline(self)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if (event.buttons() & Qt.MouseButton.LeftButton
                and (self._moving
                     or (event.scenePos() - self._press_scene)
                     .manhattanLength() > self.DRAG_THRESHOLD)):
            delta = event.scenePos() - self._press_scene
            self._moving = True
            self.setPos(self.pos() + delta)
            self._press_scene = event.scenePos()
            if self._canvas is not None:
                self._canvas._move_text_outline(self)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._moving:
            self._moving = False
            if self._canvas is not None:
                self._canvas._hide_text_outline()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # Esc 结束编辑（块保留，可再拖动/再编辑）；不冒泡去关弹窗
        if event.key() == Qt.Key.Key_Escape:
            self.clearFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        # 报备"当前样式块"：选项行改字体/字号/颜色时作用在它身上。不能靠
        # 场景焦点项现查——选项行控件（尤其 Slider）一被点就把焦点抢走。
        if self._canvas is not None:
            self._canvas._active_text_block = self

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        # 空块（点了落点没打字）失焦即自删，不留隐形占位
        if not self.toPlainText().strip():
            if self._canvas is not None and self._canvas._active_text_block is self:
                self._canvas._active_text_block = None
            QTimer.singleShot(0, self.deleteLater)
