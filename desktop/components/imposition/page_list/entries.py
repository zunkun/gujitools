# -*- coding: utf-8 -*-
"""左列的页条目（``_PageEntry``）与底部固定的「＋ 选择拼版」（``_AddEntry``）。
"""

from __future__ import annotations

from desktop.components.imposition.page_list._qt import (
    QColor,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPainter,
    QPen,
    QPixmap,
    QRectF,
    QToolButton,
    QVBoxLayout,
    Qt,
    Signal,
)
from qfluentwidgets import CheckBox

from desktop.services.imposition import cn_page_label
from desktop.ui import theme as T
from desktop.ui.widgets import apply_to


class _PageEntry(QFrame):
    """左列的一页拼版：**缩略图**（上）+ 标题「第一页」/ 副标题（下），整块可点。

    ⚠️ 版面（用户 2026-10-04 定）：**缩略图在上、文字在下**——原先是
    ``[勾选框][缩略图][文字]`` 横排，用户看图时把「标题在缩略图上方」读了序，
    明确要求改成上下结构；勾选框钉左上角、「✕」钉右上角。

    ⚠️ 底色/描边**自己画**（``paintEvent``），不用样式表：样式表一旦进入子树，
    Qt 会把 QFrame 底色填白（步骤条 `_StepBadge` 那条教训），而且会连带影响
    子 QLabel 的取色路径（``apply_to`` 对原生 QLabel 走的是调色板）。

    交互：单击切页；**按住上下拖**是页排序（``drag_started``）；当前页右上角
    有一个「✕」，点了发 ``remove_clicked``（把该页两张图释放回未选择列表）。

    ⚠️ **缩略图是真控件**（QLabel + ``set_thumb``），不是 paintEvent 里画：
    用户 2026-10-03 要求左栏显示缩略图，而缩略图是**异步解码**出来的（源图
    动辄几千像素）。自己画就得额外维护「图还没来」的占位状态与重绘时机，
    而 QLabel 只要在拿到图时 `setPixmap` 一次。

    拖动排序时本条目有两种临时态：**拖动态**（``set_drag_active``，主色
    虚线描边 + 半透明）用在跟着光标走的幽灵卡上；**置灰态**（``set_dimmed``）
    用在留在原位的本体上——清单本身在拖动过程中一动不动。
    """

    clicked = Signal(int)
    drag_started = Signal(int)
    remove_clicked = Signal(int)
    #: 左上勾选框被点（批量操作用）：``index, checked``
    check_toggled = Signal(int, bool)

    #: 按下后移动超过该距离判为拖动（小于则仍是单击切页）
    DRAG_THRESHOLD = 8

    #: 缩略图的**固定框**（px）。条目列宽只有 150px（见
    #: ``ImpositionPageList.list_scroll``；竖向细滚动条再咬掉几个像素），
    #: 框取 118 宽给左右留白；高 88：对开页（约 2:1）落在 ~118×59，
    #: 半幅（约 1:1.3）落在 ~68×88，两种形态都看得清——原先 56×78 的窄条
    #: 只够瞄一眼（用户 2026-10-04 报"缩略图显示的小"）。
    #: ⚠️ 框是**固定尺寸**：``set_thumb`` 按 ``self.thumb.size()`` 等比缩放，
    #: 尺寸随布局漂移的话，缓存下来的 pixmap 就永远停在旧比例上。
    THUMB_W = 118
    THUMB_H = 88

    def __init__(self, index: int, caption: str, parent=None):
        super().__init__(parent)
        self.index = index
        self.caption = caption
        self._current = False
        self._press_pos = None
        self._dragging = False
        self._drag_active = False
        self._dimmed = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 版面（用户 2026-10-04 定）：**缩略图在上、文字在下**；勾选框钉左上角、
        # 「✕」钉右上角。原先是 [勾选框][缩略图][文字] 横排——用户看图时把
        # 「标题在缩略图上方」读了序，要求改成上下结构。
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)
        # 顶行：勾选框（左上）+ 弹性 + 「✕」（右上，仅当前页显示）。
        # 点击被 QCheckBox/ToolButton 自行消费，不会触发本条目的单击切页/拖动。
        # ⚠️ 勾选框必须**钉死成小方块**：qfluentwidgets CheckBox 空文本的
        # sizeHint 有 57px 宽（指示器只有 ~20px，qss 兜底也是 29px），不钉死
        # 的话布局按 sizeHint 给宽，顶行会被撑歪。
        self.checkbox = CheckBox(self)
        self.checkbox.setFixedSize(29, 22)
        self.checkbox.setToolTip("勾选本页，清单下沿会出现「批量删除」悬浮框")
        self.checkbox.toggled.connect(
            lambda checked: self.check_toggled.emit(self.index, checked)
        )
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(0)
        top_row.addWidget(self.checkbox, 0, Qt.AlignmentFlag.AlignTop)
        top_row.addStretch(1)
        self.remove_button = QToolButton(self)
        self.remove_button.setText("✕")
        self.remove_button.setAutoRaise(True)
        self.remove_button.setFixedSize(18, 18)
        self.remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_button.setToolTip(
            "删除本页拼版，把这两张图释放回未选择列表（源图不受影响）"
        )
        self.remove_button.clicked.connect(
            lambda: self.remove_clicked.emit(self.index)
        )
        top_row.addWidget(self.remove_button, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(top_row)
        #: 本页缩略图（还没渲好时是**空框** + 自绘浅底，见 :meth:`set_thumb`）
        self.thumb = QLabel(self)
        self.thumb.setFixedSize(self.THUMB_W, self.THUMB_H)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setScaledContents(False)
        apply_to(self.thumb, T.SIZE_CAPTION, color=T.INK_FAINT)
        root.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignHCenter)
        # 文字（标题 + 副标题）在缩略图**下面**，居中对齐（与勾选框同一条
        # 视觉中轴，名称长短不一时也不显歪）
        labels = QVBoxLayout()
        labels.setContentsMargins(0, 0, 0, 0)
        labels.setSpacing(1)
        self.title_label = QLabel(cn_page_label(index), self)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption_label = QLabel(caption, self)
        self.caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption_label.setWordWrap(False)
        labels.addWidget(self.title_label)
        labels.addWidget(self.caption_label)
        root.addLayout(labels)
        self.remove_button.hide()
        # 右键菜单（用户 2026-11-16：参考「PDF排版」左列缩略图，给
        # 上移/下移/删除/向前插入/向后插入）：条目自己只发"在哪儿右键"，
        # 菜单与动作归 :class:`ImpositionPageList`——条目是每次重建的短命
        # 对象，把菜单挂在它身上，重建一次就丢一个菜单窗口。
        # ⚠️ 子控件（缩略图 QLabel、勾选框、✕）自己不处理右键，事件冒泡到
        # 本条目，所以"在缩略图上右键"也能命中。
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        #: 当前已贴缩略图的 ``QPixmap.cacheKey()``（``None`` = 还没贴/已清空）。
        #: ``set_thumb`` 的"同一张图不重贴"早退靠它，见该方法说明。
        self._thumb_key: int | None = None
        self._apply_style()

    def set_thumb(self, image) -> None:
        """把本页缩略图放上去（``QImage``/``QPixmap``；``None`` 回空占位）。

        ⚠️ **等比缩放后居中，不裁切**：拼版页是横向对开的两张图，硬裁会只剩
        半张（用户看到的是"缩略图里图缺一块"）。放不下就留白——留白比缺内容
        诚实。

        ⚠️ 没图时**不写「···」**（用户 2026-10-04 报「只看到 3 个点」）：
        空框 + ``paintEvent`` 里的浅底框即可——"还没渲"与"渲不出来"都由它兜着。

        ⚠️ **同一张图直接返回**（早退）：批量路径会重复贴同一张图，而每次都要
        重跑一次 ``scaled``。详见 :meth:`set_thumb_at` 里的说明。
        """
        if image is None or getattr(image, "isNull", lambda: True)():
            self._thumb_key = None
            self.thumb.clear()
            return
        pixmap = (
            image if isinstance(image, QPixmap) else QPixmap.fromImage(image)
        )
        if pixmap.isNull():
            self._thumb_key = None
            self.thumb.clear()
            return
        # ⚠️ **同一张图不重贴**（早退）：`set_thumb` 每次都要跑一次
        # `pixmap.scaled(SmoothTransformation)`，在"整列批量回填"路径上会被
        # 调用上万次（见 `set_thumb_at` 的说明）。判据用 pixmap 的
        # `cacheKey()`——它是内容标识，两次 `fromImage` 同一张图会得到同一个
        # key，而图内容变了 key 必变（不会"图换了却不刷新"）。
        key = pixmap.cacheKey()
        if key == self._thumb_key:
            return
        self._thumb_key = key
        self.thumb.setText("")
        self.thumb.setPixmap(
            pixmap.scaled(
                self.thumb.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def set_current(self, current: bool) -> None:
        if current != self._current:
            self._current = current
            self._apply_style()
        # 「✕」只在当前页显示（用户口径：第几页选中，右侧有个 ×）
        self.remove_button.setVisible(current)

    def set_drag_active(self, on: bool) -> None:
        """进入/退出拖动态（样式 + 关闭手型光标，暗示「抓着了」）。"""
        if on != self._drag_active:
            self._drag_active = on
            self.setCursor(Qt.CursorShape.ClosedHandCursor if on else Qt.CursorShape.PointingHandCursor)
            self.update()

    def set_dimmed(self, on: bool) -> None:
        """置灰半透明：拖动中本体留在原位的示意（幽灵卡在跟着光标走）。"""
        if on != self._dimmed:
            self._dimmed = on
            self.update()

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()

    def set_checked(self, on: bool) -> None:
        """程序化回填勾选（blockSignals：不回抛 ``check_toggled``）。"""
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(bool(on))
        self.checkbox.blockSignals(False)

    def _apply_style(self) -> None:
        apply_to(
            self.title_label, T.SIZE_BODY, bold=True,
            color=T.ACCENT if self._current else T.INK,
        )
        apply_to(self.caption_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        apply_to(self.remove_button, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        if self._dimmed:
            # 拖动中的本体：原地置灰半透明（正被拖走的是幽灵卡）
            painter.setOpacity(0.35)
            painter.setPen(QPen(QColor(T.BORDER), 1.0))
            painter.setBrush(QColor(T.SURFACE))
        elif self._drag_active:
            # 幽灵卡：主色虚线描边 + 半透明（盖在别的页上也能看出来）
            painter.setOpacity(0.85)
            painter.setPen(
                QPen(QColor(T.ACCENT), 1.6, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            )
            painter.setBrush(QColor(T.SURFACE))
        elif self._current:
            painter.setPen(QPen(QColor(T.ACCENT), 1.4))
            painter.setBrush(QColor(T.ACCENT_SOFT))
        else:
            painter.setPen(QPen(QColor(T.BORDER), 1.0))
            painter.setBrush(QColor(T.SURFACE))
        painter.drawRoundedRect(rect, T.RADIUS_SM, T.RADIUS_SM)
        # 缩略图框：浅底 + 细边（照抄选图弹窗卡片——留白/透明页也有边界感；
        # 图是子控件、画在本层之上，这里只是它的"底"）
        painter.setPen(QPen(QColor(T.BORDER_SOFT), 1.0))
        painter.setBrush(QColor(T.SURFACE_SOFT))
        painter.drawRoundedRect(
            QRectF(self.thumb.geometry()), T.RADIUS_SM, T.RADIUS_SM
        )
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._press_pos is not None
            and not self._dragging
            and (event.position().toPoint() - self._press_pos).manhattanLength()
            > self.DRAG_THRESHOLD
        ):
            self._dragging = True
            self.drag_started.emit(self.index)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                self._dragging = False  # 拖动结束，不算单击切页
            elif self.rect().contains(event.position().toPoint()):
                self.clicked.emit(self.index)
            self._press_pos = None
        super().mouseReleaseEvent(event)


class _AddEntry(QFrame):
    """左列最后一格：虚线的「＋ 选择拼版」。"""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QVBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(0)
        label = QLabel("＋ 选择拼版", self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_to(label, T.SIZE_BODY, color=T.ACCENT)
        row.addWidget(label)
        self.setToolTip("从剩余未被选择拼版的图片里自由勾选（不限张数），"
                        "开始拼版时按每两张一页配对")

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.9, 0.9, self.width() - 1.8, self.height() - 1.8)
        painter.setPen(
            QPen(QColor(T.ACCENT), 1.4, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, T.RADIUS_SM, T.RADIUS_SM)
        painter.end()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)
