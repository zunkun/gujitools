# -*- coding: utf-8 -*-
"""候选图的卡片与自动换行网格（``_SourceCard`` / ``_CardGrid``）。"""

from __future__ import annotations

from pathlib import Path

from desktop.components.imposition.picker._qt import (
    QColor,
    QFrame,
    QGridLayout,
    QLabel,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRectF,
    Qt,
    QVBoxLayout,
    QWidget,
    Signal,
)
from desktop.components.imposition.picker.constants import (
    CARD_GAP,
    CARD_H,
    CARD_HEAD,
    CARD_W,
    THUMB_H,
    THUMB_W,
)
from desktop.ui import theme as T
from desktop.ui.widgets import apply_to


class _SourceCard(QFrame):
    """一张可勾选的源图卡片：缩略图 + 名字 + 勾选标记，整张可点。

    ⚠️ 用**真控件**而不是 QListWidget 的图标模式：图标模式的缩略图尺寸/文字
    由委托按 sizeHint 自己算，在真机（高分屏 + 真实透明 PNG）上会把卡片内容
    画成一小条、文字也看不见（用户 2026-09-30 截图报过）。这里缩略图是固定
    ``THUMB_W×THUMB_H`` 的 QLabel、名字是独立 QLabel，尺寸完全由我们说了算。
    """

    clicked = Signal(object)  # 传出自己，宿主负责切换勾选

    def __init__(self, path: Path, parent=None, key: str = "", uploaded=False):
        super().__init__(parent)
        self.path = Path(path)
        #: 这条候选的**身份键**（宿主用：列表里的图 = 路径串；本次上传的图 =
        #: 每次上传一个唯一键）。同一张图上传两次会是两条不同键的候选。
        self.cand_key = key or str(self.path)
        #: 是否本次上传的图（`True` ⇒ 确认后宿主先把文件复制进任务目录）
        self.uploaded = bool(uploaded)
        self._checked = False
        self._pixmap = QPixmap()
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(
            f"{self.path}\n勾选后：序号在前的排到拼版页右侧"
            + ("\n（本次上传的图片，确认后复制进任务目录）" if self.uploaded else "")
        )

        column = QVBoxLayout(self)
        # ⚠️ 上留白必须够放下勾选框：勾选框画在卡片的 paintEvent 里，而缩略图是
        # **子控件**、会盖在卡片之上——不给它留位置，勾选标记就被缩略图压住，
        # 只剩一角露出来（实测像个残缺的弧线）。
        column.setContentsMargins(10, CARD_HEAD, 10, 8)
        column.setSpacing(6)
        self.thumb = QLabel(self)
        self.thumb.setFixedSize(THUMB_W, THUMB_H)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignHCenter)
        self.name = QLabel(self.path.stem, self)
        self.name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_to(self.name, T.SIZE_CAPTION, color=T.INK)
        column.addWidget(self.name, 0)
        column.addStretch(1)

    # ------------------------------------------------------------------ 状态
    def set_pixmap(self, pixmap: QPixmap) -> None:
        """回填缩略图（分批解码，见 ImpositionPickerDialog._fill_thumbs）。"""
        if pixmap.isNull():
            return
        self._pixmap = pixmap
        self.thumb.setPixmap(pixmap)
        self.update()

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool) -> None:
        if checked == self._checked:
            return
        self._checked = bool(checked)
        self.update()

    def toggle(self) -> None:
        self.clicked.emit(self)

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, _event) -> None:  # noqa: N802
        """卡片底 + 描边 + 左上角勾选框（勾中给主色浅底与对勾）。

        自绘而不是样式表：样式表一旦进子树，Qt 会把 QFrame 底色填白，还会连带
        改子 QLabel 的取色路径（见 step_bar 的教训）。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        if self._checked:
            painter.setPen(QPen(QColor(T.ACCENT), 1.6))
            painter.setBrush(QColor(T.ACCENT_SOFT))
        else:
            painter.setPen(QPen(QColor(T.BORDER), 1.0))
            painter.setBrush(QColor(T.SURFACE))
        painter.drawRoundedRect(rect, T.RADIUS_MD, T.RADIUS_MD)

        # 缩略图框：浅底 + 细边，让留白页也有边界感
        painter.setPen(QPen(QColor(T.BORDER_SOFT), 1.0))
        painter.setBrush(QColor(T.SURFACE_SOFT))
        painter.drawRoundedRect(QRectF(self.thumb.geometry()), T.RADIUS_SM,
                                T.RADIUS_SM)

        # 勾选框（画在卡片顶部的"页眉"里，不会被缩略图压住）
        box = QRectF(10.0, 8.0, 16.0, 16.0)
        painter.setPen(QPen(QColor(T.ACCENT if self._checked else T.BORDER_STRONG),
                            1.4))
        painter.setBrush(QColor(T.SURFACE))
        painter.drawRoundedRect(box, 4, 4)
        if self._checked:
            path = QPainterPath()
            path.moveTo(box.x() + 4.0, box.y() + 8.4)
            path.lineTo(box.x() + 6.8, box.y() + 11.2)
            path.lineTo(box.x() + 12.2, box.y() + 4.8)
            painter.setPen(QPen(QColor(T.ACCENT), 2.0, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        painter.end()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit(self)
        super().mouseReleaseEvent(event)


class _CardGrid(QWidget):
    """卡片容器：按可用宽度**自动算列数**（flex 换行），一行摆好几个。

    Qt 没有内置流式布局，用 ``QGridLayout`` + ``resizeEvent`` 重排即可：
    窗口变宽一行放更多、变窄自动折行，并保持卡片自身尺寸不变（不拉伸变形）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[_SourceCard] = []
        self._cols = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(CARD_GAP)
        self.grid.setVerticalSpacing(CARD_GAP)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

    def add_card(self, card: _SourceCard) -> None:
        self._cards.append(card)
        self._relayout(force=True)

    def detach_cards(self) -> None:
        """把当前卡片全部摘出布局（不销毁；实例还在宿主的字典里复用）。"""
        for old in self._cards:
            self.grid.removeWidget(old)
        self._cards = []

    def adopt_cards(self, cards: list) -> None:
        """装入一批卡片并重排（调用前必须先 ``detach_cards``）。"""
        self._cards = list(cards)
        self._cols = 0
        self._relayout(force=True)

    def columns(self) -> int:
        """当前一行摆了几张（护栏用；0 = 还没排过）。"""
        return self._cols

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self, force: bool = False) -> None:
        width = self.width() or self.sizeHint().width()
        cols = max(1, (width + CARD_GAP) // (CARD_W + CARD_GAP))
        if cols == self._cols and not force:
            return
        self._cols = cols
        for index, card in enumerate(self._cards):
            self.grid.addWidget(card, index // cols, index % cols)
        # 右侧/底部留一个可伸缩的空格：卡片靠左靠上排，不被摊开
        for column in range(cols):
            self.grid.setColumnStretch(column, 0)
        self.grid.setColumnStretch(cols, 1)
