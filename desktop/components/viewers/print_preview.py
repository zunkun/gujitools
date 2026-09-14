# -*- coding: utf-8 -*-
"""生成 PDF 预览：图片瀑布流（flex 布局）。

展示待打印图片列表（第三步 rembg 处理后的图片），支持拖动排序、
删除选中、插入图片；仅操作列表数据，不生成/删除图片文件。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QKeySequence, QIcon, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QVBoxLayout, QWidget,
)
from qfluentwidgets import CaptionLabel, PrimaryPushButton, PushButton, ToolButton
from qfluentwidgets import FluentIcon as FIF

from ...workers import ImageListWorker, WorkerHost


class PrintPreviewWidget(QWidget, WorkerHost):
    """生成 PDF 页面列表：可拖动排序、删除选中、请求插入。"""

    order_changed = Signal()        # 列表内容/顺序变化（含拖动与删除）
    insert_requested = Signal()     # 请求插入图片

    ICON_SIZE = QSize(120, 156)

    def __init__(self, empty_hint: str = "暂无图片，请先完成去底色", parent=None):
        super().__init__(parent)
        self._init_worker_host()
        self._empty_hint = empty_hint
        self._gen = 0  # 加载代际：仅最新一次列表的缩略图事件生效
        self._thumb_retried = False
        self._received: set[int] = set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        self.insert_button = PrimaryPushButton(FIF.ADD, "插入图片")
        self.insert_button.clicked.connect(self.insert_requested.emit)
        self.delete_button = PushButton(FIF.DELETE, "删除选中")
        self.delete_button.clicked.connect(self.remove_selected)
        self.hint_label = CaptionLabel("拖动图片排序 · Delete 删除选中")
        toolbar.addWidget(self.insert_button)
        toolbar.addWidget(self.delete_button)
        toolbar.addStretch()
        toolbar.addWidget(self.hint_label)
        layout.addLayout(toolbar)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setWrapping(True)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list.setIconSize(PrintPreviewWidget.ICON_SIZE)
        self.list.setGridSize(QSize(140, 190))
        self.list.setSpacing(8)
        self.list.setUniformItemSizes(True)
        self.list.setWordWrap(True)
        self.list.model().rowsMoved.connect(self._sync_cache_order)
        self.list.model().rowsMoved.connect(self._emit_order_changed)
        QShortcut(QKeySequence(Qt.Key_Delete), self.list, self.remove_selected)
        layout.addWidget(self.list, 1)

        self.empty_label = QLabel(empty_hint)
        self.empty_label.setStyleSheet("color:#8b949e;")
        self.empty_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_label)
        self.empty_label.hide()

    # ------------------------------------------------------------------ API
    def set_entries(self, entries: list[dict]) -> None:
        """重建列表：entries = [{file, label}]。"""
        self._gen += 1
        gen = self._gen
        self._thumb_retried = False
        self._received = set()
        self._entries_cache = list(entries)  # 富条目（含 box/parea/effect/thumb）
        self._stop_worker()
        self.list.clear()
        if not entries:
            self.empty_label.show()
            self.list.hide()
            return
        self.empty_label.hide()
        self.list.show()
        for index, entry in enumerate(entries):
            item = QListWidgetItem(entry.get("title", entry.get("label", "")))
            item.setData(Qt.UserRole, entry["file"])
            item.setData(Qt.UserRole + 1, index)  # 指向 _entries_cache 下标
            item.setTextAlignment(Qt.AlignCenter)
            self.list.addItem(item)
        self._load_thumbs(entries, gen)

    def entries(self) -> list[dict]:
        """当前视觉顺序的富条目列表。"""
        result = []
        for row in range(self.list.count()):
            index = self.list.item(row).data(Qt.UserRole + 1)
            if index is not None and 0 <= index < len(self._entries_cache):
                result.append(self._entries_cache[index])
        return result

    def count(self) -> int:
        return self.list.count()

    def remove_selected(self) -> None:
        rows = sorted(
            (self.list.row(item) for item in self.list.selectedItems()),
            reverse=True,
        )
        if not rows:
            return
        for row in rows:
            self.list.takeItem(row)
        self._sync_cache_order()
        self._emit_order_changed()

    def _sync_cache_order(self) -> None:
        """按当前视觉顺序重排富条目缓存，并重新分配条目索引。"""
        order = []
        for row in range(self.list.count()):
            index = self.list.item(row).data(Qt.UserRole + 1)
            if index is not None and 0 <= index < len(self._entries_cache):
                order.append(index)
        self._entries_cache = [self._entries_cache[i] for i in order]
        # 重排后重新分配条目索引，保持与视觉顺序一致
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item is not None:
                item.setData(Qt.UserRole + 1, row)

    # ------------------------------------------------------------------ 内部
    def _emit_order_changed(self) -> None:
        if self.list.count():
            self.order_changed.emit()

    def _stop_worker(self) -> None:
        for thread in getattr(self, "_threads", []):
            thread.quit()

    def _load_thumbs(self, entries: list[dict], gen: int) -> None:
        """条目可带 thumb 规格（{"path": 小图, "crop": 框|None}），
        避免逐张解码原始分辨率大图。"""
        paths = []
        crops = []
        for entry in entries:
            spec = entry.get("thumb")
            if isinstance(spec, dict) and spec.get("path"):
                paths.append(spec["path"])
                crops.append(spec.get("crop"))
            else:
                paths.append(entry["file"])
                crops.append(None)
        self.run_worker(
            lambda: ImageListWorker(paths, edge=160, crops=crops),
            lambda worker, thread: (
                worker.thumbnail_ready.connect(
                    lambda i, img, p, g=gen: self._set_icon(i, img, g)
                ),
                worker.completed.connect(
                    lambda g=gen: self._thumbs_completed(g)
                ),
                worker.completed.connect(thread.quit),
                worker.failed.connect(lambda *_: thread.quit()),
            ),
        )

    def _thumbs_completed(self, gen: int) -> None:
        """完成后核对：仍有缺图条目（事件丢失/解码失败）时重试一次。"""
        if gen is not self._gen or self._thumb_retried:
            return
        missing = [i for i in range(self.list.count()) if i not in self._received]
        if not missing:
            return
        self._thumb_retried = True
        self._load_thumbs(getattr(self, "_entries_cache", []) or [], gen)

    def _set_icon(self, index: int, image, gen: int) -> None:
        if gen is not self._gen or index >= self.list.count():
            return
        self._received.add(index)
        item = self.list.item(index)
        if item is not None:
            item.setIcon(QIcon(QPixmap.fromImage(image)))
