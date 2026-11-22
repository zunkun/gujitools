# -*- coding: utf-8 -*-
"""「管理图片」内容面板（草稿）：:class:`PrintManagePanel`。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from desktop.components.print_manage_dialog._qt import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidgetItem,
    QSize,
    Qt,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import PushButton

from desktop.components.dialog_shell import shell_dialog
from desktop.components.print_insert_dialog import PrintInsertPanel
from desktop.components.print_manage_dialog.constants import (
    CELL_LABEL_H,
    CELL_SIZE,
    PENDING_KEY,
    SHOWN_SIZE_ROLE,
    THUMB_SIZE,
)
from desktop.components.print_manage_dialog.delegate import _ThumbDelegate
from desktop.components.print_manage_dialog.grid import _ThumbGrid
from desktop.components.print_manage_dialog.helpers import (
    _icon_and_size,
    _typical_thumb_height,
    page_label,
)
from desktop.ui import theme as T
from desktop.ui.widgets import apply_to


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
        self._delegate = _ThumbDelegate(self.list)
        self.list.setItemDelegate(self._delegate)
        #: 当前网格单元（按本书图片长宽比自适应，见 ``_fit_cells``）
        self._cell_size = QSize(self.CELL_SIZE)
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
        self._fit_cells()
        self._sync_count()
        self._sync_actions()

    # ------------------------------------------------------------------ 草稿
    def _append_entry(self, entry: dict, at: int | None = None) -> QListWidgetItem:
        """把一条草稿放进网格（``at=None`` 追加末尾，否则插入该行之前）。"""
        file_text = str(entry.get("file") or "")
        # 任务里的图只读预生成的小图；刚选入的 ``_pending`` 还没有缓存，
        # 允许现解码（数量少，且是用户刚挑的本地图）。
        icon, shown = _icon_and_size(
            file_text, self._thumb_for, self.THUMB_SIZE,
            allow_original=bool(entry.get(PENDING_KEY)),
        )
        item = QListWidgetItem(icon, page_label(self.list.count()))
        item.setData(Qt.ItemDataRole.UserRole, entry)
        item.setData(SHOWN_SIZE_ROLE, shown)
        item.setToolTip(file_text)
        item.setSizeHint(self._cell_size)
        if at is None:
            self.list.addItem(item)
        else:
            self.list.insertItem(at, item)
        self._renumber()
        return item

    def refresh_thumb(self, file_text: str) -> None:
        """后台缩略图就绪：按**文件路径**找回那一格，就地换图标。

        弹窗打开时缩略图可能还没渲完（首次进入本步），生成一张就补一张；
        按路径而不是行号，用户此时拖动/删除过也不会刷错格。
        """
        if not file_text:
            return
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item is None:
                continue
            entry = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(entry, dict) and str(entry.get("file")) == file_text:
                self._refresh_item(item, entry)
                return

    def refresh_thumbs(self) -> None:
        """整批刷新（所有小图都生成完时调用；此时只读缓存，开销很小）。"""
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item is None:
                continue
            entry = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(entry, dict):
                self._refresh_item(item, entry)
        # 之前没图时网格按 96×128 兜底，现在按真实长宽比收紧
        self._fit_cells()

    def _fit_cells(self) -> None:
        """按**本书缩略图的典型高度**收紧网格（用户 2026-11-02）。

        固定 96×128 的框对横版/方版书会让每行多出一大截空白（"文字下面好大
        一段"）。这里用 :func:`_typical_thumb_height` 从实际缩略图高度里取
        稳健值（扉页/插图这类特别高、特别矮的不参与统计），网格行高 =
        典型高度 + 名称区；高过典型值的个别图按框高缩放，不撑破行。

        每本书长宽比不同 → 每个任务/每次刷新自己算一份，不写死常量。
        """
        heights: list[int] = []
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item is None:
                continue
            shown = item.data(SHOWN_SIZE_ROLE)
            if isinstance(shown, QSize) and shown.height() > 0:
                heights.append(shown.height())
        box_h = _typical_thumb_height(heights)
        # 太扁的书也给右上角 x/多选框留够高度
        box_h = max(box_h, self.THUMB_SIZE.height() // 2)
        self._delegate.thumb_box = QSize(self.THUMB_SIZE.width(), box_h)
        self.list.thumb_box = QSize(self._delegate.thumb_box)
        self._cell_size = QSize(
            self.CELL_SIZE.width(), box_h + CELL_LABEL_H,
        )
        self.list.setIconSize(self._delegate.thumb_box)
        self.list.setGridSize(self._cell_size)
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item is not None:
                item.setSizeHint(self._cell_size)

    def _refresh_item(self, item: QListWidgetItem, entry: dict) -> None:
        icon, shown = _icon_and_size(
            str(entry.get("file") or ""), self._thumb_for, self.THUMB_SIZE,
            allow_original=bool(entry.get(PENDING_KEY)),
        )
        if icon.isNull():
            return
        item.setIcon(icon)
        item.setData(SHOWN_SIZE_ROLE, shown)
        self.list.viewport().update(self.list.visualItemRect(item))

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
        self._fit_cells()
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


__all__ = ["PrintManagePanel"]
