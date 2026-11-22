# -*- coding: utf-8 -*-
"""「管理图片」弹窗的图标网格（:class:`_ThumbGrid`：多选 + 拖放重排）。"""

from __future__ import annotations

from desktop.components.print_manage_dialog._qt import (
    QColor,
    QDrag,
    QItemSelectionModel,
    QListWidget,
    QMimeData,
    QMouseEvent,
    QPainter,
    QPixmap,
    QPoint,
    QRect,
    QSize,
    Qt,
    Signal,
)

from desktop.components.print_manage_dialog.constants import SHOWN_SIZE_ROLE, THUMB_SIZE
from desktop.components.print_manage_dialog.helpers import (
    _check_rect,
    _close_rect,
    _image_rect,
)
from desktop.ui import theme as T


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
        #: 与画布同一个缩略图框（面板按典型高度算出后覆盖），点击 x/方框要
        #: 按它算落点，否则高图被缩下来后命中区会错位
        self.thumb_box = QSize(THUMB_SIZE)

    # ---------------------------------------------------------------- 点击
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            item = self.itemAt(pos)
            if item is not None:
                image = _image_rect(
                    self.visualItemRect(item),
                    item.data(SHOWN_SIZE_ROLE) or QSize(),
                    self.thumb_box,
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
