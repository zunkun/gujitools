# -*- coding: utf-8 -*-
"""生成 PDF 预览：图片列表（IconMode 流式排列）。

展示待打印图片列表（第三步「提交本次任务」产出的最终图片），
支持拖动排序、删除选中、插入图片；仅操作列表数据，不生成/删除图片文件。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal, QTimer
from PySide6.QtGui import QKeySequence, QIcon, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QVBoxLayout, QWidget,
)
from qfluentwidgets import CaptionLabel, PrimaryPushButton, PushButton
from qfluentwidgets import FluentIcon as FIF

from desktop.ui import theme as T
from desktop.ui import widgets as ui
from desktop.workers import ImageListWorker, WorkerHost


class PrintPreviewWidget(QWidget, WorkerHost):
    """生成 PDF 页面列表：可拖动排序、删除选中、请求插入。"""

    order_changed = Signal()        # 列表内容/顺序变化（含拖动与删除）
    insert_requested = Signal()     # 请求插入图片
    download_requested = Signal()   # 请求下载已生成的 PDF
    hint = Signal(str)              # 需要宿主提示用户（如"未选中任何图片"）

    # 图标区：横向留足整页宽图的展示空间，高度覆盖常见古籍页比例
    ICON_SIZE = QSize(180, 240)
    # 文件名区高度（约 2 行 + 行距）。图标区与文字区**紧邻**，不再在
    # 两者之间留出固定空档——此前 GRID 高 290 而图标高 240，配合
    # AlignBottom 会把文字钉在网格底部，图片与文字之间恒定空出 50px
    # 死区（area=2 + border=None 的整页图恰好占满图标框，观感最明显）。
    LABEL_H = 44
    # 网格：图标 + 紧跟其下的文件名，无中间留白
    GRID_SIZE = QSize(200, ICON_SIZE.height() + LABEL_H)
    # 缩略图解码最长边（与 ICON_SIZE 宽度匹配，留余量给高 DPI 缩放）
    THUMB_EDGE = 360

    def __init__(self, empty_hint: str = "暂无图片，请先完成去底色", parent=None):
        """
        构建待打印列表与空状态占位。

        列表开启 InternalMove 以支持拖动排序；提示类反馈通过 hint 信号
        交给宿主弹 toast，而不是在控件内直接弹窗。
        """
        super().__init__(parent)
        self._init_worker_host()
        self._empty_hint = empty_hint
        self._gen = 0  # 加载代际：仅最新一次列表的缩略图事件生效
        self._thumb_retried = False
        self._received: set[int] = set()
        self._pdf_path: Path | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        self.insert_button = PrimaryPushButton(FIF.ADD, "插入图片")
        self.insert_button.clicked.connect(self.insert_requested.emit)
        self.delete_button = PushButton(FIF.DELETE, "删除选中")
        self.delete_button.clicked.connect(self.remove_selected)
        self.download_button = PrimaryPushButton(FIF.SAVE, "下载 PDF")
        self.download_button.setToolTip("请先执行「生成 PDF」后再下载")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.download_requested.emit)
        self.hint_label = CaptionLabel("拖动图片排序 · Delete 删除选中")
        toolbar.addWidget(self.insert_button)
        toolbar.addWidget(self.delete_button)
        toolbar.addWidget(self.download_button)
        toolbar.addStretch()
        toolbar.addWidget(self.hint_label)
        layout.addLayout(toolbar)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setWrapping(True)
        # Adjust：窗口宽度变化时自动重排；图标异步加载完成后再 doItemsLayout
        # 修正首次显示尺寸异常（放大再缩小才正常）的问题
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list.setIconSize(self.ICON_SIZE)
        self.list.setGridSize(self.GRID_SIZE)
        self.list.setSpacing(8)
        # 不启用 uniformItemSizes：图标异步加载，且各图宽高比不同，
        # 强制统一会导致首帧用纯文字的极小 sizeHint 布局且不再重算
        self.list.setUniformItemSizes(False)
        self.list.setWordWrap(True)
        # 文字在图标下方居中
        self.list.setTextElideMode(Qt.ElideMiddle)
        self.list.model().rowsMoved.connect(self._sync_cache_order)
        self.list.model().rowsMoved.connect(self._emit_order_changed)
        QShortcut(QKeySequence(Qt.Key_Delete), self.list, self.remove_selected)
        layout.addWidget(self.list, 1)

        self.empty_label = QLabel(empty_hint)
        self.empty_label.setWordWrap(True)
        ui.apply_to(self.empty_label, T.SIZE_LABEL, color=T.INK_FAINT)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label, 1)
        self.empty_label.hide()

    # ------------------------------------------------------------------ API
    def set_entries(self, entries: list[dict]) -> None:
        """重建列表：entries = [{file, label}]。"""
        self._gen += 1
        gen = self._gen
        self._thumb_retried = False
        self._received = set()
        self._entries_cache = list(entries)  # 条目 {file,label}，可含可选 thumb 规格
        self._stop_worker()
        self.list.clear()
        if not entries:
            self.empty_label.show()
            self.list.hide()
            return
        self.empty_label.hide()
        self.list.show()
        for index, entry in enumerate(entries):
            label = entry.get("title") or entry.get("label") or ""
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, entry["file"])
            item.setData(Qt.UserRole + 1, index)  # 指向 _entries_cache 下标
            # 文字紧贴图标下沿居中对齐。用 AlignVCenter（而非 AlignBottom）
            # 让文字落在网格内的文字区中部，避免被钉到网格最底部而在
            # 图片与文字间产生固定空档。
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            item.setSizeHint(QSize(self.GRID_SIZE.width(), self.GRID_SIZE.height()))
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
        """列表当前条目数。"""
        return self.list.count()

    def set_pdf_path(self, path: str | Path | None) -> None:
        """设置已生成 PDF 的路径；存在则启用下载按钮，否则禁用。"""
        p = Path(path) if path else None
        self._pdf_path = p if (p and p.exists()) else None
        self.download_button.setEnabled(self._pdf_path is not None)
        if self._pdf_path is not None:
            self.download_button.setToolTip(f"下载 PDF：{self._pdf_path.name}")
        else:
            self.download_button.setToolTip("请先执行「生成 PDF」后再下载")

    def remove_selected(self) -> None:
        """删除所有选中条目，未选中则通过 hint 信号提示。

        多选用 ExtendedSelection，按行倒序移除避免下标错位；删除后同步
        缓存顺序并 emit order_changed。
        """
        rows = sorted(
            (self.list.row(item) for item in self.list.selectedItems()),
            reverse=True,
        )
        if not rows:
            # 之前是静默 return，用户点了"删除选中"却没有任何反馈
            self.hint.emit("请先在列表中选中要删除的图片。")
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
            lambda: ImageListWorker(paths, edge=self.THUMB_EDGE, crops=crops),
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
        """缩略图全部加载完毕：重算列表布局，修复首次显示图片极小的问题。"""
        if gen is not self._gen:
            return
        missing = [i for i in range(self.list.count()) if i not in self._received]
        if missing and not self._thumb_retried:
            self._thumb_retried = True
            self._load_thumbs(getattr(self, "_entries_cache", []) or [], gen)
            return
        # 强制重算 item 几何：setUniformItemSizes(False) 下仍需这一步，
        # 否则首帧 item 大小基于加载前的 sizeHint（纯文字极小）
        self.list.scheduleDelayedItemsLayout()
        QTimer.singleShot(0, self.list.doItemsLayout)

    def _set_icon(self, index: int, image, gen: int) -> None:
        if gen is not self._gen or index >= self.list.count():
            return
        self._received.add(index)
        item = self.list.item(index)
        if item is not None:
            item.setIcon(QIcon(QPixmap.fromImage(image)))
