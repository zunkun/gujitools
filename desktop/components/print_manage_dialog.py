# -*- coding: utf-8 -*-
"""第四步「管理图片」弹窗面板：**草稿式**缩略图网格 + 二次「插入图片」。

用户 2026-11-02 的口径：

- 缩略图条底部的「插入图片」按钮改为 **「管理图片」**，底部那行右键提示删掉；
- 点「管理图片」弹出本面板：缩略图**一行多列**（图标网格），可多选、可拖动排序；
- 面板底部仍有 **「插入图片」** 按钮，点开是原来的插入弹窗 B
  （``PrintInsertPanel``，上传图片 / 删除恢复）；
- 本面板里的改动只是**草稿**：点外壳的「保存」才写回，取消则一概不生效。

本版补充（用户 2026-11-02 第二轮）：

- 刚插入、还没保存的新图用**虚线框**圈起来（暖色，与已有图片区分）；
- 每张图**右上角有 x**，点它即从草稿里删掉；
- 选中一张或多张时，底部才出现 **「删除图片」** 按钮。

⚠️ 本面板只收集草稿，不碰数据层：顺序落盘、新图复制、恢复项出
``deleted_pages`` 全由宿主（``pages/taskdetail/print_list.py``）在「保存」后执行。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import (
    QItemSelectionModel,
    QMimeData,
    QPoint,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDrag,
    QFont,
    QIcon,
    QImageReader,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import PushButton

from desktop.components.dialog_shell import shell_dialog
from desktop.components.print_insert_dialog import PrintInsertPanel
from desktop.services.imposition import cn_page_label
from desktop.ui import theme as T
from desktop.ui.widgets import apply_to

#: 草稿条目的临时标记：刚从本地选入、还没复制进任务目录（保存时才复制）。
PENDING_KEY = "_pending"
#: 复制任务的目标路径（宿主在后台复制前写进来，完成回调据此替换文件）。
TARGET_KEY = "_target"

#: 缩略图框（与插入弹窗的恢复页一致，视觉统一）
THUMB_SIZE = QSize(96, 128)
#: 图标网格单元：缩略图 + 下方一行文字
CELL_SIZE = QSize(THUMB_SIZE.width() + 40, THUMB_SIZE.height() + 38)
#: 条目数据角色：图标的**实际显示尺寸**（自绘 x 与虚线框都要用它定位）
SHOWN_SIZE_ROLE = Qt.ItemDataRole.UserRole + 1
#: 右上角 x 的边长
CLOSE_SIZE = 18
#: 左上角多选框的边长
CHECK_SIZE = 18


def page_label(row: int) -> str:
    """条目名称 = **页码**（列表当前位置，写法与图片拼版一致）。

    用户 2026-11-02：显示「第一页」「第十二页」这种中文页码，不再用四位补零；
    文件名会误导（拖动/删除后它跟 PDF 页序对不上）。中文页码的唯一来源是
    ``services.imposition.cn_page_label``，这里只是借来用。
    """
    return cn_page_label(row)


def _image_rect(cell: QRect, shown: QSize) -> QRect:
    """缩略图在网格单元里的落点（水平居中、顶部留 6px）。"""
    if shown.width() <= 0 or shown.height() <= 0:
        shown = THUMB_SIZE
    fitted = shown.scaled(THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio)
    return QRect(
        cell.left() + (cell.width() - fitted.width()) // 2,
        cell.top() + 6,
        fitted.width(),
        fitted.height(),
    )


def _close_rect(image: QRect) -> QRect:
    """图片右上角 x 的命中区（完全落在图片内）。"""
    return QRect(
        image.right() - CLOSE_SIZE - 3,
        image.top() + 3,
        CLOSE_SIZE,
        CLOSE_SIZE,
    )


def _check_rect(image: QRect) -> QRect:
    """图片左上角多选框的命中区（与 x 对称）。"""
    return QRect(image.left() + 3, image.top() + 3, CHECK_SIZE, CHECK_SIZE)


def _icon_and_size(
    file_text: str, thumb_for: Callable[[str], object] | None, size: QSize,
) -> tuple[QIcon, QSize]:
    """按目标尺寸**缩放解码**缩略图，并返回图标的实际显示尺寸。"""
    source = file_text
    if thumb_for is not None:
        try:
            provided = thumb_for(file_text)
        except Exception:  # noqa: BLE001 - 小图来源坏了就回落原图
            provided = None
        if provided:
            source = str(provided)
    try:
        reader = QImageReader(source)
        image_size = reader.size()
        if image_size.isValid():
            reader.setScaledSize(
                image_size.scaled(size, Qt.AspectRatioMode.KeepAspectRatio)
            )
        image = reader.read()
        if image.isNull():
            return QIcon(), QSize()
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return QIcon(), QSize()
        return QIcon(pixmap), pixmap.size()
    except Exception:  # noqa: BLE001 - 坏图/占用：留空图标，不打断弹窗
        return QIcon(), QSize()


class _ThumbDelegate(QStyledItemDelegate):
    """网格条目自绘：选中底色 + 缩略图 + 右上角 x + 名称。

    ``QListWidget`` 原生条目没有"右上角按钮/虚线边框"这类装饰，自绘一次比
    叠一层透明控件更轻（滚动/拖动时不会有一堆子控件跟着搬）。
    """

    def paint(  # noqa: N802 - Qt 覆写
        self, painter: QPainter, option: QStyleOptionViewItem, index,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cell = option.rect.adjusted(2, 2, -2, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.setPen(QPen(QColor(T.ACCENT), 1))
            painter.setBrush(QColor(T.ACCENT_SOFT))
            painter.drawRoundedRect(cell, T.RADIUS_SM, T.RADIUS_SM)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

        entry = index.data(Qt.ItemDataRole.UserRole)
        pending = isinstance(entry, dict) and bool(entry.get(PENDING_KEY))
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        shown = index.data(SHOWN_SIZE_ROLE) or QSize()
        image = _image_rect(option.rect, shown)
        if isinstance(icon, QIcon) and not icon.isNull():
            icon.paint(painter, image, Qt.AlignmentFlag.AlignCenter)
        # 新图片：暖色虚线框（还没保存进任务目录，与已有图片区分）
        if pending:
            pen = QPen(QColor(T.WARNING), 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(image.adjusted(-3, -3, 3, 3),
                                    T.RADIUS_SM, T.RADIUS_SM)

        mark = QFont(option.font)
        mark.setBold(True)
        mark.setPixelSize(11)

        # 左上角多选框（与右键/Ctrl 多选等价；用户 2026-11-02）
        check = _check_rect(image)
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(T.ACCENT))
            painter.drawRoundedRect(check, 4, 4)
            painter.setFont(mark)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(check, Qt.AlignmentFlag.AlignCenter, "✓")
        else:
            painter.setPen(QPen(QColor(T.BORDER_STRONG), 1))
            painter.setBrush(QColor(255, 255, 255, 220))
            painter.drawRoundedRect(check, 4, 4)

        # 右上角删除 x
        close = _close_rect(image)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 130))
        painter.drawEllipse(close)
        painter.setFont(mark)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(close, Qt.AlignmentFlag.AlignCenter, "✕")

        # 名称 = **页码**（列表当前位置；拖动/删除后自动跟着变）
        text = page_label(index.row())
        font = QFont(option.font)
        painter.setFont(font)
        painter.setPen(QColor(T.WARNING if pending else T.INK_SOFT))
        text_rect = QRect(
            option.rect.left() + 2,
            image.bottom() + 6,
            option.rect.width() - 4,
            max(option.rect.bottom() - image.bottom() - 6, 0),
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            painter.fontMetrics().elidedText(
                text, Qt.TextElideMode.ElideMiddle, text_rect.width()
            ),
        )
        painter.restore()


class _ThumbGrid(QListWidget):
    """管理弹窗的图标网格：自绘条目 + 多选框/x 点击 + 手动拖放重排。

    ⚠️ 排序**不用** Qt 的 ``InternalMove``：IconMode 网格里它经常只搬当前一项、
    或者干脆不落位（用户 2026-11-02 报「拖动一张图片无法改变位置」）。
    这里与 ``ThumbStrip`` 同口径：自己记源行、自己算落点、自己 take/insert，
    多选时整批搬走。
    """

    #: 有条目被 x 删掉（参数是被删条目的草稿 dict，面板据此记进「删除恢复」）
    rows_removed = Signal(object)
    #: 拖动重排完成（页码挂在行号上，重排后自动跟着变）
    order_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_rows: list[int] = []
        self._drop_row: int | None = None

    # ---------------------------------------------------------------- 点击
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            item = self.itemAt(pos)
            if item is not None:
                image = _image_rect(
                    self.visualItemRect(item),
                    item.data(SHOWN_SIZE_ROLE) or QSize(),
                )
                if _close_rect(image).contains(pos):
                    entry = item.data(Qt.ItemDataRole.UserRole)
                    self.takeItem(self.row(item))
                    self.rows_removed.emit(entry)
                    event.accept()
                    return
                if _check_rect(image).contains(pos):
                    # 多选框：只翻转这一条，**不清空**其它选中项（多选就靠它）
                    item.setSelected(not item.isSelected())
                    self.setCurrentItem(
                        item, QItemSelectionModel.SelectionFlag.NoUpdate
                    )
                    event.accept()
                    return
        super().mousePressEvent(event)

    # ---------------------------------------------------------------- 拖动
    def startDrag(self, supported_actions) -> None:  # noqa: N802
        """自己建 QDrag 起拖。

        ⚠️ **不能**调 ``super().startDrag``：默认实现在 ``MoveAction`` 落定后会
        再删一遍源行（``clearOrRemove``），与我们的 take/insert 重复，等于
        把别的条目删掉。MIME 只用作"拖起来了"的载体，搬运全部由 ``dropEvent``
        按 __drag_rows__ 完成（与 ``ThumbStrip`` 同一套做法）。
        """
        rows = sorted(self.row(item) for item in self.selectedItems())
        if not rows:
            return
        item = self.item(rows[0])
        if item is None:
            return
        rect = self.visualItemRect(item)
        pixmap = QPixmap()
        if not rect.isEmpty():
            snapshot = self.viewport().grab(rect)
            if not snapshot.isNull():
                pixmap = QPixmap(snapshot.size())
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                painter.setOpacity(0.75)
                painter.drawPixmap(0, 0, snapshot)
                painter.end()
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-guji-manage-rows", b"1")
        drag.setMimeData(mime)
        if not pixmap.isNull():
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(
                pixmap.width() // 2, min(24, pixmap.height() // 2)
            ))
        self._drag_rows = rows
        self._drop_row = None
        self.viewport().update()
        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            self._drag_rows = []
            self._drop_row = None
            self.viewport().update()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.source() is self and self._drag_rows:
            self._drop_row = self._drop_index_at(event.position().toPoint())
            self.viewport().update()
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.source() is self and self._drag_rows:
            self._drop_row = self._drop_index_at(event.position().toPoint())
            self.viewport().update()
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._drop_row = None
        self.viewport().update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        if event.source() is not self or not self._drag_rows:
            super().dropEvent(event)
            return
        target = self._drop_index_at(event.position().toPoint())
        rows = list(self._drag_rows)
        self._drag_rows = []
        self._drop_row = None
        self.viewport().update()
        self._move_rows_to(rows, target)
        event.acceptProposedAction()

    def _drop_index_at(self, pos) -> int:
        """落点 → 「插到第几行之前」（0..count）。

        **先按行定位、再按左右半区判定**（用户 2026-11-02）：
        只看最近条目的话，瞄准某行**最左边**那片空白时会被上一行末尾的条目
        抢走（落点变成上一行开头）；先锁定光标所在的行，行内再按 x 判左右。
        """
        count = self.count()
        if count <= 0:
            return 0
        rows: list[tuple[int, QRect]] = []
        for row in range(count):
            rect = self.visualItemRect(self.item(row))
            if not rect.isEmpty():
                rows.append((row, rect))
        if not rows:
            return count
        # 1) 行定位：竖直距离最近的一行（缝隙里同距时取下面那行）
        best_top = rows[0][1].top()
        best_dy: int | None = None
        for _row, rect in rows:
            dy = max(rect.top() - pos.y(), 0, pos.y() - rect.bottom())
            if best_dy is None or dy < best_dy:
                best_dy, best_top = dy, rect.top()
            elif dy == best_dy and rect.top() > best_top:
                best_top = rect.top()
        band = [(row, rect) for row, rect in rows if rect.top() == best_top]
        # 2) 行内按 x：落在某张中心线左边 → 插到它前面；越过最后一张中心 → 下一行开头
        for row, rect in band:
            if pos.x() <= rect.center().x():
                return row
        return band[-1][0] + 1

    def _move_rows_to(self, rows: list[int], target: int) -> None:
        """把 ``rows`` 整批搬到 ``target``（原坐标，插到该行之前）。"""
        rows = sorted({row for row in rows if 0 <= row < self.count()})
        if not rows:
            return
        items = [self.item(row) for row in rows]
        before = sum(1 for row in rows if row < target)
        insert_at = max(0, min(target - before, self.count() - len(rows)))
        for row in reversed(rows):
            self.takeItem(row)
        for offset, item in enumerate(items):
            if item is None:
                continue
            self.insertItem(insert_at + offset, item)
            item.setSelected(True)
        # 用 NoUpdate 只移动"当前项"，否则 setCurrentRow 会把多选清掉
        current = self.item(insert_at)
        if current is not None:
            self.setCurrentItem(
                current, QItemSelectionModel.SelectionFlag.NoUpdate
            )
        self.order_changed.emit()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._drop_row is None or self.count() <= 0:
            return
        painter = QPainter(self.viewport())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(T.ACCENT))
        if self._drop_row >= self.count():
            rect = self.visualItemRect(self.item(self.count() - 1))
            x = rect.right() + 3
        else:
            rect = self.visualItemRect(self.item(self._drop_row))
            x = rect.left() - 3
        # 每行最左边那条落点线原本画在 x=-3（视口外，等于没有反馈）：
        # 夹回视口内，让「插到本行最前面」也看得见（用户 2026-11-02）。
        x = max(1, min(x, self.viewport().width() - 4))
        painter.drawRect(
            QRect(x, rect.top() + 2, 3, max(rect.height() - 4, 3))
        )


class PrintManagePanel(QWidget):
    """「管理图片」内容面板（草稿）。

    ``entries`` 是宿主传入的**当前**待打印条目（会被逐条复制，面板改动不影响
    入参）；``deleted`` 是 ``print.json`` 的 ``deleted_pages``，供面板内的
    「插入图片 → 删除恢复」页签使用。
    """

    #: 缩略图框（与插入弹窗的恢复页一致，视觉统一）
    THUMB_SIZE = THUMB_SIZE
    #: 图标网格单元：缩略图 + 下方一行文字
    CELL_SIZE = CELL_SIZE

    def __init__(
        self,
        *,
        entries: list[dict] | None = None,
        deleted: list[dict] | None = None,
        thumb_for: Callable[[str], object] | None = None,
        parent=None,
    ):
        """entries: [{file, label, rect?}]；deleted: print.json 的已删除记录。"""
        super().__init__(parent)
        self._thumb_for = thumb_for
        self._deleted = [dict(page) for page in (deleted or [])]

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(T.SPACE_SM)

        self.hint = QLabel(
            "勾选图片左上角方框（或按住 Ctrl / Shift）可多选；"
            "拖动缩略图调整顺序（多选后一起拖动）；"
            "在这里删掉的图可从「插入图片 → 删除恢复」放回。"
        )
        apply_to(self.hint, T.SIZE_CAPTION, color=T.INK_SOFT)
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        # 一行多列的图标网格（不是"一张一行"）：可多选、可拖动排序。
        # ⚠️ 排序走 ``_ThumbGrid`` 自己的 take/insert（见类注释）：Qt 的
        #    IconMode + InternalMove 在网格里不落位（用户实测拖不动）。
        self.list = _ThumbGrid(self)
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setFlow(QListView.Flow.LeftToRight)
        self.list.setWrapping(True)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list.setIconSize(self.THUMB_SIZE)
        self.list.setGridSize(self.CELL_SIZE)
        self.list.setSpacing(T.SPACE_XS)
        self.list.setDragEnabled(True)
        self.list.setAcceptDrops(True)
        self.list.viewport().setAcceptDrops(True)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        # 落点指示器自己画（网格里 Qt 默认指示器的位置与"插到哪"对不上）
        self.list.setDropIndicatorShown(False)
        self.list.setItemDelegate(_ThumbDelegate(self.list))
        self.list.rows_removed.connect(self._on_removed)
        self.list.order_changed.connect(self._after_rows_changed)
        self.list.itemSelectionChanged.connect(self._sync_actions)
        root.addWidget(self.list, 1)

        row = QHBoxLayout()
        row.setSpacing(T.SPACE_MD)
        self.insert_button = PushButton("插入图片")
        self.insert_button.setToolTip(
            "打开「插入图片」弹窗：上传新图片，或恢复已删除的图片"
        )
        self.insert_button.clicked.connect(self._open_insert)
        row.addWidget(self.insert_button)
        # 选中（含多选）后才出现的删除入口；用 qfluent 默认按钮（不叠样式表）
        self.delete_button = PushButton(FIF.DELETE, "删除图片")
        self.delete_button.setToolTip("从草稿里删掉选中的图片（点「保存」才生效）")
        self.delete_button.clicked.connect(self._remove_selected)
        row.addWidget(self.delete_button)
        self.count_label = QLabel("")
        apply_to(self.count_label, T.SIZE_CAPTION, color=T.INK_SOFT)
        row.addWidget(self.count_label)
        row.addStretch()
        root.addLayout(row)

        for entry in entries or []:
            self._append_entry(dict(entry))
        self._sync_count()
        self._sync_actions()

    # ------------------------------------------------------------------ 草稿
    def _append_entry(self, entry: dict, at: int | None = None) -> QListWidgetItem:
        """把一条草稿放进网格（``at=None`` 追加末尾，否则插入该行之前）。"""
        file_text = str(entry.get("file") or "")
        icon, shown = _icon_and_size(file_text, self._thumb_for, self.THUMB_SIZE)
        item = QListWidgetItem(icon, page_label(self.list.count()))
        item.setData(Qt.ItemDataRole.UserRole, entry)
        item.setData(SHOWN_SIZE_ROLE, shown)
        item.setToolTip(file_text)
        item.setSizeHint(self.CELL_SIZE)
        if at is None:
            self.list.addItem(item)
        else:
            self.list.insertItem(at, item)
        self._renumber()
        return item

    def _renumber(self) -> None:
        """条目文字 = **当前行号**的页码（重排/删除/插入后都要重写）。"""
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item is not None:
                item.setText(page_label(row))

    def entries(self) -> list[dict]:
        """当前草稿顺序（宿主在「保存」后读取；含 ``_pending`` 标记）。"""
        out: list[dict] = []
        for row in range(self.list.count()):
            item = self.list.item(row)
            entry = item.data(Qt.ItemDataRole.UserRole) if item else None
            if isinstance(entry, dict):
                out.append(dict(entry))
        return out

    def _sync_count(self) -> None:
        self.count_label.setText(f"共 {self.list.count()} 页")

    def _sync_actions(self) -> None:
        """选中项存在时才露出「删除图片」按钮。"""
        self.delete_button.setVisible(bool(self.list.selectedItems()))

    def _remove_selected(self) -> None:
        """底部「删除图片」：删掉选中的（可能多张）条目。"""
        rows = sorted(
            {self.list.row(item) for item in self.list.selectedItems()},
            reverse=True,
        )
        self._remove_rows(rows)

    def _remove_rows(self, rows: list[int]) -> None:
        """按行号删条目（x 与底部按钮共用的落点）。"""
        if not rows:
            return
        removed: list[object] = []
        for row in sorted(set(rows), reverse=True):
            item = self.list.item(row)
            if item is not None:
                removed.append(item.data(Qt.ItemDataRole.UserRole))
            self.list.takeItem(row)
        for entry in removed:
            self._remember_deleted(entry)
        self._after_rows_changed()

    def _on_removed(self, entry) -> None:
        """右上角 x：先记进「删除恢复」，再刷新计数/按钮。"""
        self._remember_deleted(entry)
        self._after_rows_changed()

    def _remember_deleted(self, entry) -> None:
        """草稿里删掉的图也进「删除恢复」清单，之后还能从「插入图片」放回。

        ⚠️ 只收**已在任务目录里**的图：``PENDING``（刚选入、还没复制）没有可
        恢复的源文件，收进来反而会在保存时指向本地临时路径。
        """
        if not isinstance(entry, dict) or entry.get(PENDING_KEY):
            return
        file_text = str(entry.get("file") or "")
        if not file_text:
            return
        if any(str(page.get("file")) == file_text for page in self._deleted):
            return
        self._deleted.append({
            "file": file_text,
            "label": str(entry.get("label") or Path(file_text).stem),
        })

    def _after_rows_changed(self) -> None:
        self._renumber()
        self._sync_count()
        self._sync_actions()

    # ------------------------------------------------------------- 插入图片
    def _open_insert(self) -> None:
        """弹二次窗 B（现有「插入图片」面板），结果先落进本面板草稿。"""
        row = self.list.currentRow()
        total = self.list.count()
        panel = PrintInsertPanel(
            deleted=self._deleted,
            current_row=row,
            total=total,
            default_position="after",
            thumb_for=self._thumb_for,
        )
        dialog = shell_dialog(
            "插入图片", panel, self.window(), size=(760, 640), ok_text="插入",
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._apply_insert_result(panel.result_data(), row=row, total=total)

    def _apply_insert_result(
        self, result: dict, *, row: int | None = None, total: int | None = None,
    ) -> None:
        """把弹窗 B 的 ``result_data()`` 落进草稿（**不落盘**，便于离屏自测）。

        落点口径与宿主一致：以打开 B 时选中的行为准，``before`` 插在该行前、
        ``after`` 插在该行后；未选中时按列表开头/末尾。
        """
        if row is None:
            row = self.list.currentRow()
        if total is None:
            total = self.list.count()
        before = result.get("position") == "before"
        if total <= 0:
            at = 0
        elif row < 0:
            at = 0 if before else total
        else:
            at = row if before else min(row + 1, total)
        restored = [dict(page) for page in (result.get("deleted") or [])]
        pending = [
            {
                "file": str(path),
                "label": Path(str(path)).stem,
                PENDING_KEY: True,
            }
            for path in (result.get("files") or [])
        ]
        for offset, entry in enumerate(restored + pending):
            self._append_entry(entry, at + offset)
        # 恢复过的图片不再属于「已删除」：否则再次打开 B 还能勾选同一张
        restored_files = {str(p.get("file")) for p in restored}
        self._deleted = [
            p for p in self._deleted
            if str(p.get("file")) not in restored_files
        ]
        if restored or pending:
            self.list.setCurrentRow(min(at, self.list.count() - 1))
        self._after_rows_changed()


__all__ = ["PrintManagePanel", "PENDING_KEY", "TARGET_KEY"]
