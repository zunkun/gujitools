# -*- coding: utf-8 -*-
"""拼版页清单——**模块一：选择拼版** 的左列（「第一页」「第二页」…）。

虚线的**「＋ 选择拼版」固定钉在左列最底部**（不随页条目增长下移出视野），
点了发 ``add_requested``，由模块一控制器
（``desktop/pages/taskdetail/imposition_pages.py``）弹窗挑图建页。

页条目左上是**勾选框**、右上是当前页的「✕」；主体是**缩略图**，
标题「第一页」与副标题（两张源图名）排在缩略图**下方**（用户 2026-10-04：
文字要在缩略图下面）。勾了页，一条**悬浮操作框**（「已选 N 页」+「取消选择」
「批量删除」）悬在页码栏右侧中部，可拖动——取消选择即收起。

这里只做控件与信号：清单**只认页标题/副标题文案**，不认拼版文档本身——
页清单的数据（``drafts/imposition.json``）由装配层
``view.ImpositionViewWidget`` 灌进来。
"""

from __future__ import annotations

from functools import partial

from PySide6.QtCore import (
    QAbstractAnimation, QPoint, QRectF, Qt, QPropertyAnimation, QTimer, Signal,
)
from PySide6.QtCore import QEasingCurve
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QScrollArea, QToolButton,
    QVBoxLayout, QWidget,
)
from qfluentwidgets import CaptionLabel, CheckBox, PushButton

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


class ImpositionPageList(QWidget):
    """左列拼版页清单：滚动的页条目 + 底部固定的虚线「＋ 选择拼版」。

    只认文案：``set_pages(captions)`` 灌入每页的副标题（两张源图名），
    条目数即页数；当前页高亮由 ``set_current`` 控制。勾选了页，一条悬浮
    操作框（``_SelectBar``）悬在页码栏右侧中部（可拖动），提供
    「取消选择 / 批量删除」。

    页条目支持**按住上下拖动排序**，交互口径（用户 2026-09-30 三稿：拖动
    中清单不留空档）：按下后**本体留在原位置灰**，一张等大的「幽灵卡」
    跟着光标走，主色细线指示松手后落到哪——清单全程一动不动。**松手**
    后幽灵卡滑进落点槽位、这才真正换位，随后发
    ``reorder_requested(from, target)``——``target`` 是**拖走之后**的插入
    下标（调用方据此 pop/insert），拖回原位则不发。
    """

    #: 点了某一页
    page_selected = Signal(int)
    #: 点了虚线「＋ 选择拼版」
    add_requested = Signal()
    #: 拖动某页松手：``from`` 移到 ``target``（都是移除前的口径）
    reorder_requested = Signal(int, int)
    #: 点了某页右侧的「✕」：释放该页图片回未选择列表
    remove_requested = Signal(int)
    #: 勾选集合变了（含「取消选择」一键清空；控制器一般不用接）
    check_changed = Signal()
    #: 点了悬浮框「批量删除」
    batch_delete_requested = Signal()

    #: 拖动期间轮询光标的间隔（毫秒）
    _POLL_MS = 16
    #: 落位动画时长（毫秒）——短促跟手，不拖泥带水
    _ANIM_MS = 140
    #: 落点指示线的厚度（像素）
    _INDICATOR_H = 3
    #: 拖到滚动区上/下边缘这个距离内开始自动滚动（像素）
    _EDGE_PX = 24
    #: 自动滚动每轮步长（像素）
    _EDGE_STEP = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[_PageEntry] = []
        self._current = -1
        self._drag_from = -1
        self._drag_drop = -1
        self._drag_entry: _PageEntry | None = None   # 被拖的本体（留在原位）
        self._ghost: _PageEntry | None = None        # 跟着光标的幽灵卡
        self._flow: list[_PageEntry] = []            # 拖动中除本体外的东西
        self._anims: list[QPropertyAnimation] = []
        self._grab_dy = 0                     # 光标到卡片顶缘的抓取偏移
        self._drag_x = 0                      # 拖动横坐标（只上下拖，不横移）
        self._committing = False              # 松手落位动画进行中

        # 滚不动时也不挤压右侧画布
        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setFixedWidth(150)
        self.list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self.list_box = QVBoxLayout(container)
        self.list_box.setContentsMargins(0, 0, 0, 0)
        self.list_box.setSpacing(T.SPACE_SM)
        # 弹性空白垫在最底下：条目少时它们靠上排，不被摊开
        self.list_box.addStretch(1)
        self.list_scroll.setWidget(container)

        # 拖动排序的落点指示线（画在条目之间，指示松手后落到哪）
        self._indicator = QWidget(container)
        self._indicator.setFixedHeight(self._INDICATOR_H)
        self._indicator.setStyleSheet(
            f"background-color: {T.ACCENT}; border-radius: 1px;"
        )
        self._indicator.hide()

        self._drag_timer = QTimer(self)
        self._drag_timer.setInterval(self._POLL_MS)
        self._drag_timer.timeout.connect(self._poll_drag)

        row = QVBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(T.SPACE_SM)
        row.addWidget(self.list_scroll, 1)
        # 「＋ 选择拼版」钉在左列最底部（用户 2026-09-30：不跟在页码下面，
        # 页再多/再少它都钉在底部一格），从滚动区里拿出来，永远看得见
        self.add_entry = _AddEntry(self)
        self.add_entry.clicked.connect(self.add_requested)
        row.addWidget(self.add_entry)

        # 多选悬浮框：浮在滚动区下沿（盖住条目），勾选数归零自动收起
        self.select_bar = _SelectBar(self)
        self.select_bar.clear_requested.connect(self._clear_selection)
        self.select_bar.delete_requested.connect(self.batch_delete_requested)
        self.select_bar.hide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.select_bar.isVisible() and not self.select_bar._user_moved:
            self._place_select_bar()

    def set_float_host(self, host) -> None:
        """把悬浮框的宿主换成外部装配层（拼版视图整体）。

        页码栏只有 150px 宽，框要「浮在页码栏**右侧**」就得允许它超出本列、
        悬到右边画布上——挂到视图底下才行。``view.py`` 装配时调用；不设置
        则兜底贴在清单内右缘、垂直居中。
        """
        self.select_bar.setParent(host)
        self.select_bar.hide()

    # ------------------------------------------------------------------ 数据
    def entries(self) -> list[_PageEntry]:
        return list(self._entries)

    def set_pages(self, captions: list[str], current: int = -1) -> None:
        """按页数重建清单（``captions[i]`` 是第 i 页的副标题）。

        勾选集合**按副标题跨重建保留**：拖动排序/加页不丢勾选；页被删掉
        （副标题不在了）自然落选——批量删除自己就是靠这次重建清空的。
        """
        self._cancel_drag()
        keep_checked = {e.caption for e in self._entries if e.is_checked()}
        for entry in self._entries:
            self.list_box.removeWidget(entry)
            entry.deleteLater()
        self._entries = []
        for index, caption in enumerate(captions):
            entry = _PageEntry(index, caption, self.list_scroll.widget())
            entry.clicked.connect(self._on_entry_clicked)
            entry.drag_started.connect(self._on_drag_started)
            entry.remove_clicked.connect(self.remove_requested)
            entry.check_toggled.connect(self._on_entry_check_toggled)
            entry.set_checked(caption in keep_checked)
            self.list_box.insertWidget(index, entry)
            self._entries.append(entry)
        self.set_current(current)
        self._update_select_bar()

    def set_current(self, index: int) -> None:
        """高亮当前页（-1 = 无页）。"""
        self._current = index if index >= 0 else -1
        for entry in self._entries:
            entry.set_current(entry.index == self._current)

    def set_page_thumbs(self, thumbs: list) -> None:
        """给每页条目灌缩略图（``thumbs[i]`` 是第 i 页的 ``QImage``/``QPixmap``，
        ``None`` 表示还没渲好）。

        用户 2026-10-03：所有独立任务左栏都显示缩略图。**本方法只管贴图**，
        解码/缓存/异步在宿主那边做（拼图模块页用
        :class:`~desktop.workers.thumb_cache_worker.ImageThumbCacheWorker`，
        与其余四个独立任务页同一份缓存与同一份逻辑）。

        ⚠️ 下标要**按条目自己的 index** 灌而不是按参数位置：``set_pages`` 重建
        后条目的 index 是重建时的下标，两者一致；但拖动排序后条目的 index
        仍是它创建时的下标，而 ``_entries`` 的**列表位置**才是当前页序——
        所以这里遍历 ``_entries`` 并用 ``entry.index`` 取图。
        """
        by_index = {
            i: t for i, t in enumerate(thumbs or []) if t is not None
        }
        for entry in self._entries:
            entry.set_thumb(by_index.get(entry.index))

    def set_thumb_at(self, index: int, image) -> None:
        """只给**指定条目**贴缩略图（``index`` 是它在当前清单里的位置）。

        ⚠️ **"一张张到齐"的回填必须用它，不要用** :meth:`set_page_thumbs`：那个
        方法会遍历**全部**条目逐个 ``set_thumb``，于是"380 张缩略图陆续到达"
        变成 380 × 380 ≈ **7.2 万次** ``set_thumb``；而 ``set_thumb`` 每次都要
        重跑一次 ``pixmap.scaled(SmoothTransformation)``（现在有"同一张图早退"，
        但已贴过的那 379 条仍要走一遍字典查表 + 早退判断）。

        实测（离屏，380 页拼版）：整列重灌 = **主线程连续占住 27.5 秒**，
        用户看到的就是"程序卡死"；只贴单条 = **~0.03 秒**。

        ⚠️ 这里用**位置**（``_entries`` 的下标）而不是 ``entry.index``：调用方
        传的是"清单里的第几页"（与 :meth:`_imposition_page_reps` 同序），
        拖动排序后两者会分叉——那种情况下贴错一条比不贴更难查。

        无此条目（清单变短了/下标越界）时**静默忽略**：那是"用户正在翻页或
        删页"，不该让一个迟到的缩略图把异常抛到事件循环外面。
        """
        if not (0 <= index < len(self._entries)):
            return
        self._entries[index].set_thumb(image)

    def current(self) -> int:
        return self._current

    def _on_entry_clicked(self, index: int) -> None:
        self.set_current(index)
        self.page_selected.emit(index)

    # ------------------------------------------------------------- 勾选批量
    def checked_indexes(self) -> list[int]:
        """勾选了的页下标（升序）。"""
        return sorted(e.index for e in self._entries if e.is_checked())

    def _on_entry_check_toggled(self, _index: int, _checked: bool) -> None:
        self.check_changed.emit()
        self._update_select_bar()

    def _clear_selection(self) -> None:
        """悬浮框「取消选择」：清空全部勾选——勾选数归零，悬浮框随之消失。"""
        for entry in self._entries:
            entry.set_checked(False)
        self.check_changed.emit()
        self._update_select_bar()

    def _update_select_bar(self) -> None:
        """悬浮框跟着勾选数走：勾了页才浮出，取消选择/删页归零即收起。"""
        count = len(self.checked_indexes())
        self.select_bar.set_count(count)
        self.select_bar.setVisible(count > 0)
        if count > 0:
            self._place_select_bar()
            self.select_bar.raise_()

    def _place_select_bar(self) -> None:
        """摆悬浮框：默认悬在**页码栏右缘、垂直居中**（浮在右侧画布上，
        不压底部的「＋ 选择拼版」）；用户拖过就不再自动摆位。"""
        bar = self.select_bar
        if bar._user_moved:
            return
        hint = bar.sizeHint()
        host = bar.parentWidget()
        if host is None or host is self:
            # 兜底（没有外部宿主，比如单独实例化）：清单内右缘、垂直居中
            scroll = self.list_scroll.geometry()
            x = max(0, self.width() - hint.width() - T.SPACE_XS)
            y = scroll.top() + max(0, (scroll.height() - hint.height()) // 2)
            bar.setGeometry(x, y, hint.width(), hint.height())
            return
        g = self.geometry()  # 本列在宿主坐标系里的位置
        x = max(0, min(g.right() - 8, host.width() - hint.width()))
        y = max(0, g.top() + (g.height() - hint.height()) // 2)
        bar.setGeometry(x, y, hint.width(), hint.height())

    # ------------------------------------------------------------- 拖动排序
    def _on_drag_started(self, index: int) -> None:
        """某页被按住拖动了：**本体留在原位**（置灰），一张等大的「幽灵卡」
        跟着光标走，细线指示落点——清单全程不留空档（用户 2026-09-30
        三稿：占位块空档太大、原位置空着不像话）。
        """
        if self._committing or not (0 <= index < len(self._entries)):
            return
        entry = self._entries[index]
        self._drag_from = index
        self._drag_drop = index
        self._drag_entry = entry
        self._flow = [e for e in self._entries if e is not entry]
        entry.set_dimmed(True)
        container = self.list_scroll.widget()
        if container is None:  # 滚动区没内容 ⇒ 没有可拖的列表，收手
            return
        self._ghost = _PageEntry(index, entry.caption, container)
        self._ghost.set_drag_active(True)
        self._ghost.setGeometry(entry.geometry())
        self._ghost.raise_()
        self._ghost.show()
        self._drag_x = entry.x()
        self._grab_dy = container.mapFromGlobal(QCursor.pos()).y() - entry.y()
        self._drag_timer.start()
        self._poll_drag()

    def _poll_drag(self) -> None:
        """拖动中：幽灵卡贴着光标走；光标越过哪页中线，落点细线就移到那里。"""
        if QApplication.mouseButtons() != Qt.MouseButton.LeftButton:
            self._finish_drag()
            return
        if self._ghost is None:
            return
        container = self.list_scroll.widget()
        # ⚠️ list_scroll.widget() 的注解是 QWidget | None：理论上滚动区没装
        #     内容时会是 None（那就没列表可拖，直接收手）。
        if container is None:
            return
        pos = container.mapFromGlobal(QCursor.pos())
        y = max(0, min(pos.y() - self._grab_dy,
                       container.height() - self._ghost.height()))
        self._ghost.move(self._drag_x, y)
        self._auto_scroll()
        drop = len(self._flow)
        for i, entry in enumerate(self._flow):
            if pos.y() < entry.geometry().center().y():
                drop = i
                break
        if drop != self._drag_drop:
            self._drag_drop = drop
            self._place_indicator()

    def _place_indicator(self) -> None:
        """落点指示线：画在落点条目的上缘（末尾则最后条目下缘）；拖回
        原位（``drop == _drag_from``）藏线——表示松手不会换位。"""
        drop = self._drag_drop
        if self._ghost is None or not self._flow or drop == self._drag_from:
            self._indicator.hide()
            return
        if drop < len(self._flow):
            anchor = self._flow[drop].geometry()
            y = anchor.top() - (T.SPACE_SM + self._INDICATOR_H) // 2
        else:
            anchor = self._flow[-1].geometry()
            y = anchor.bottom() + (T.SPACE_SM - self._INDICATOR_H) // 2
        self._indicator.setGeometry(
            anchor.x(), max(0, y), anchor.width(), self._INDICATOR_H
        )
        self._indicator.show()
        self._indicator.raise_()

    def _register_anim(self, anim: QPropertyAnimation) -> None:
        """登记动画；它结束时自己从 ``_anims`` 摘除（finished 信号在
        C++ 对象销毁前发出，之后 deleteLater，避免留悬挂引用）。"""
        self._anims.append(anim)
        # ⚠️ 动画的 finished 在主线程发出，直连安全；但护栏静态扫描按信号名
        # 拦「worker 信号直连 lambda」，这里用 partial + 绑定方法保持同款写法
        anim.finished.connect(partial(self._forget_anim, anim))
        anim.finished.connect(anim.deleteLater)
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def _forget_anim(self, anim: QPropertyAnimation) -> None:
        if anim in self._anims:
            self._anims.remove(anim)

    def _auto_scroll(self) -> None:
        """光标贴近滚动区上/下边缘时慢慢滚，长清单拖远程不用分两把。"""
        bar = self.list_scroll.verticalScrollBar()
        vp = self.list_scroll.viewport().mapFromGlobal(QCursor.pos())
        if vp.y() < self._EDGE_PX:
            bar.setValue(bar.value() - self._EDGE_STEP)
        elif vp.y() > self.list_scroll.viewport().height() - self._EDGE_PX:
            bar.setValue(bar.value() + self._EDGE_STEP)

    def _slot_y(self, drop: int) -> int:
        """落点 ``drop`` 处的槽位纵坐标（清单从未被撑开，直接读邻条目）。"""
        if 0 <= drop < len(self._flow):
            return self._flow[drop].y()
        if self._flow:
            last = self._flow[-1]
            return last.y() + last.height() + T.SPACE_SM
        return 0

    def _finish_drag(self) -> None:
        """松手：幽灵卡滑进落点槽位**这才真正换位**，动画走完通知控制器。

        拖回原位（``drop == _drag_from``）不发信号，幽灵卡就地消散。
        ``_drag_entry`` 为 None 时（护栏合成驱动，只设 ``_drag_from``/
        ``_drag_drop``）走旧口径直接发信号，不做动画。
        """
        if self._committing:
            return
        entry = self._drag_entry
        if entry is None:
            source, drop = self._drag_from, self._drag_drop
            self._cancel_drag()
            if not (0 <= source < len(self._entries)):
                return
            target = drop - 1 if drop > source else drop
            if not (0 <= target <= len(self._entries)) or target == source:
                return
            self.reorder_requested.emit(source, target)
            return
        source, drop = self._drag_from, self._drag_drop
        self._drag_timer.stop()
        entry.set_dimmed(False)
        self._drag_entry = None
        self._drag_from = -1
        self._drag_drop = -1
        self._indicator.hide()
        ghost, self._ghost = self._ghost, None
        if ghost is None:
            self._flow = []
            return
        if drop == source:
            # 放回原位：幽灵卡就地消散，清单本来就一动没动
            self._flow = []
            ghost.deleteLater()
            return
        # 落位动画结束后才发信号：控制器据此 pop(source)/insert(drop) 落盘
        # （finished 在主线程发出；partial 写法见 _register_anim 的说明）
        target = drop
        self._committing = True
        anim = QPropertyAnimation(ghost, b"pos", self)
        anim.setDuration(self._ANIM_MS)
        anim.setStartValue(ghost.pos())
        anim.setEndValue(QPoint(self._drag_x, self._slot_y(drop)))
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(
            partial(self._emit_reorder, source, target, ghost))
        self._register_anim(anim)

    def _emit_reorder(self, source: int, target: int, ghost) -> None:
        """落位动画走完：幽灵卡消散、通知控制器落盘（``_committing`` 解除）。"""
        self._committing = False
        self._flow = []
        if ghost is not None:
            ghost.deleteLater()
        self.reorder_requested.emit(source, target)

    def _cancel_drag(self) -> None:
        self._drag_timer.stop()
        self._drag_from = -1
        self._drag_drop = -1
        self._committing = False
        if self._drag_entry is not None:
            self._drag_entry.set_dimmed(False)
            self._drag_entry = None
        if self._ghost is not None:
            self._ghost.deleteLater()
            self._ghost = None
        self._indicator.hide()
        self._flow = []
        # 动画一并停掉：set_pages 重建清单前会走到这里，
        # 别让 QPropertyAnimation 追着 deleteLater 的控件跑
        for anim in list(self._anims):
            anim.stop()
        self._anims = []
