# -*- coding: utf-8 -*-
"""垂直缩略图条控件。"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem


class ThumbStrip(QListWidget):
    """垂直缩略图条：图标在上、标签在下，加载完成前显示占位图。

    默认**不可拖动**（前三步的页面顺序由数据层决定）；第四步的待打印
    列表调 ``set_reorderable(True)`` 打开内部拖放排序，顺序变化发
    ``order_changed``。

    ⚠️ 条目尺寸只有一个事实来源（本类的 ``ICON_SIZE`` / ``GRID_SIZE`` /
    ``STRIP_WIDTH`` / ``DECODE_EDGE``）：调用方解码缩略图时必须用
    ``DECODE_EDGE`` 当"最长边"，不要写字面量 96——竖开本页面受**高度**
    约束，解码边取小了缩略图就只剩条目宽度的一半（缩略图看起来"没占满"）。
    """

    # 条目图标**框**：古籍页（竖开本，宽高比 ≈0.5~0.7）要尽量顶满条目宽度，
    # 所以框本身也得是竖的。早先是偏方的 96x128，竖页按"最长边=框宽 96"解码后
    # 只剩 55px 宽、约条目宽度的一半（用户反馈的正是这个）。
    ICON_SIZE = QSize(116, 156)
    # 图标下方的文字行（条目名/页码）。⚠️ 只要放得下一行就行：早先是 32，
    # 多出来的 8px 全是空行，用户看到的就是"条目之间还有一大段"。
    LABEL_H = 24
    # 条目网格 = 图标框 + 文字行；左右各留 3px，图标不至于贴着网格边
    GRID_SIZE = QSize(ICON_SIZE.width() + 6, ICON_SIZE.height() + LABEL_H)
    # 控件固定宽度 = 网格宽 + 竖向滚动条 + 边框余量（差 1px 就会挤出横向滚动条）
    STRIP_WIDTH = GRID_SIZE.width() + 22
    # 缩略图**解码最长边**。⚠️ ImageListWorker 的 edge 是"最长边"语义：
    # 竖页受高度约束，只有取框的长边，竖页才能真的用满框宽。
    DECODE_EDGE = max(ICON_SIZE.width(), ICON_SIZE.height())

    current_path_changed = Signal(int, str)
    order_changed = Signal()

    #: 条目之间的**可见间隙**（px）。⚠️ 这是条目外唯一的间距来源：条目
    #: 自己不再留任何余量（高度按图算，见 _item_hint），所以调间距只改这里。
    ITEM_SPACING = 6
    #: 允许的最小图标显示高度（再矮的图也不把条目压得点不到）
    MIN_DISPLAY_H = 56

    def __init__(self, parent=None):
        """初始化条目尺寸与流式布局；当前行变化发出 current_path_changed(行号, 路径)。

        ⚠️ 必须监听 ``currentRowChanged`` 而不是只接 ``itemClicked``：
        键盘翻页（方向键 / PageUp / PageDown）与程序化 ``setCurrentRow``
        只会改 currentRow、**不产生点击**，只接 itemClicked 就会出现
        「翻页了但右侧预览不更新，切到别的视图模式再切回来才正常」。
        """
        super().__init__(parent)
        self.setFixedWidth(ThumbStrip.STRIP_WIDTH)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.TopToBottom)
        self.setWrapping(False)
        self.setMovement(QListWidget.Movement.Static)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        # ⚠️ **不设** gridSize：网格单元一旦统一高度（哪怕是"取最高那张"），
        # 比它矮的条目就会在自己格子里留白——页面宽高比一有差异，留白大小
        # 还各不相同，用户看到的就是"同高图间距 0、不同高图间距很大"。
        # 条目高度改为**逐条按图算**（见 add_page_item / set_item_icon 的
        # setSizeHint）：条目 = 该图实际显示高度 + 文字行，一格不多。
        self.setIconSize(QSize(ThumbStrip.ICON_SIZE))
        self.setSpacing(ThumbStrip.ITEM_SPACING)
        self.setStyleSheet("QListWidget::item { padding: 0px; }")
        self._placeholder = self._make_placeholder()
        self._reorderable = False
        self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.model().rowsMoved.connect(self._on_rows_moved)
        # 当前行变化（鼠标点击 / 键盘方向键 / 程序化 setCurrentRow 都会走到）
        self.currentRowChanged.connect(self._on_current_row_changed)

    def _item_hint(self, display_h: int) -> QSize:
        """条目的 sizeHint：宽固定（占满条宽），高 = 图实际显示高 + 文字行。

        ⚠️ 这是"间距可控"的关键：条目高度跟着**这张图**走，不留格子余量，
        条目之间的空隙就只剩 ``ITEM_SPACING`` 一个来源。
        QListView 在 gridSize 未设置时使用每条的 sizeHint 布局，因此高度
        可以逐条不同——这正是统一网格做不到、也是早先留白的根因。
        """
        icon_h = max(self.MIN_DISPLAY_H, min(display_h, ThumbStrip.ICON_SIZE.height()))
        return QSize(ThumbStrip.GRID_SIZE.width(), icon_h + ThumbStrip.LABEL_H)

    def _on_current_row_changed(self, row: int) -> None:
        """当前行变化 → 通知宿主切换预览。

        清空列表期间会来 -1，此时条目已不存在，直接忽略。
        """
        if row < 0:
            return
        item = self.item(row)
        if item is None:
            return
        self.current_path_changed.emit(row, item.data(Qt.UserRole) or "")

    # ---------------------------------------------------------------- 排序
    def set_reorderable(self, on: bool) -> None:
        """打开/关闭条目内部拖放排序（第四步待打印列表用）。"""
        self._reorderable = bool(on)
        self.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove
            if self._reorderable
            else QAbstractItemView.DragDropMode.NoDragDrop
        )
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragEnabled(self._reorderable)
        self.setAcceptDrops(self._reorderable)
        self.viewport().setAcceptDrops(self._reorderable)
        self.setDropIndicatorShown(self._reorderable)

    def _on_rows_moved(self, *_args) -> None:
        """拖放发生后通知宿主（仅在可排序状态下转发）。"""
        if self._reorderable:
            self.order_changed.emit()

    @staticmethod
    def _make_placeholder() -> QIcon:
        """占位缩略图：浅灰底 + 边框，避免出现"加载中"文字。"""
        size = ThumbStrip.ICON_SIZE
        pixmap = QPixmap(size.width(), size.height())
        pixmap.fill(QColor("#e8ecf1"))
        painter = QPainter(pixmap)
        pen = QPen(QColor("#b8c0cc"), 1, Qt.DashLine)
        painter.setPen(pen)
        painter.drawRect(2, 2, size.width() - 5, size.height() - 5)
        painter.end()
        return QIcon(pixmap)

    def add_placeholder(self, text: str) -> None:
        """追加一个纯文字占位条目（无图标，如"缩略图加载中…"）。"""
        self.addItem(QListWidgetItem(text))

    def add_page_item(self, label: str, path: str = "") -> None:
        """新增一个带占位图的条目，缩略图就绪后由 set_item_icon 替换。

        占位图按满框（ICON_SIZE）给 sizeHint——此时还不知道这张图的宽高比；
        真实缩略图一到就由 set_item_icon 按实际比例改小。
        """
        item = QListWidgetItem(self._placeholder, label)
        item.setData(Qt.UserRole, path)
        item.setSizeHint(self._item_hint(ThumbStrip.ICON_SIZE.height()))
        self.addItem(item)

    def set_item_icon(self, index: int, image, path: str, label: str) -> None:
        """替换某条目的图标/文字/路径（缩略图异步就绪后回调）。"""
        if index >= self.count():
            return
        item = self.item(index)
        pixmap = QPixmap.fromImage(image)
        item.setIcon(QIcon(pixmap))
        item.setText(label)
        item.setData(Qt.UserRole, path)
        # 该图放进 116×156 框后的实际显示高度（等比缩放取小系数）——
        # 条目高度就按它定（_item_hint），条目内不再留任何空白
        display = pixmap.size().scaled(
            ThumbStrip.ICON_SIZE, Qt.AspectRatioMode.KeepAspectRatio
        )
        item.setSizeHint(self._item_hint(display.height()))
        self.scheduleDelayedItemsLayout()
