# -*- coding: utf-8 -*-
"""第四步「插入图片」弹窗面板：**上传图片 / 恢复已删除图片**。

用户 2026-10-31 的口径：

- 缩略图右键给「删除当前图片 / 向前插入图片 / 向后插入图片」；
- 「插入图片」按钮从缩略图**顶部**挪到缩略图**下面**，点开是弹窗；
- 弹窗两个页签：「上传图片」拖入/选择本地图、「恢复图片」列出已删除的图
  （可多选恢复）；
- 底部选落点：**插入第 x 页之前 / 之后**（x = 当前选中的页）。

用户 2026-11-01 的口径（本版）：页签顺序改为「上传图片」在前、「删除恢复」
在后；上传页空白处做成**虚线拖放框**（可拖入图片、点击打开文件选择框）；
恢复页的列表改成**一行多张**的图标网格。

⚠️ 本面板只负责收集用户意图，不碰数据层：恢复/复制由宿主
（``pages/taskdetail/print_list.py``）落盘与执行。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QIcon,
    QImageReader,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import PushButton, RadioButton

from desktop.ui import theme as T
from desktop.ui.widgets import SegmentedToggle, apply_to
from desktop.utils.files import default_open_dir

#: 拖放/文件框接受的扩展名（与 IMAGE_FILTER 同源，见下）
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
IMAGE_FILTER = "图片 (" + " ".join("*" + s for s in sorted(IMAGE_SUFFIXES)) + ")"


def _image_paths(mime) -> list[str]:
    """拖放数据里的**本地图片文件**（扩展名与文件框过滤同源）。"""
    if mime is None or not mime.hasUrls():
        return []
    out: list[str] = []
    for url in mime.urls():
        path = url.toLocalFile()
        if not path:
            continue
        if Path(path).suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if Path(path).is_file():
            out.append(path)
    return out


class _DropArea(QWidget):
    """虚线拖放框：拖入或点击都能加图片，已选图按缩略图铺开。

    ⚠️ 自绘（``paintEvent``）而不是引样式表：虚线框 + 空白提示 + 缩略图
    都在一张画布里，省掉"透明列表压在白底上"那类拼凑。
    """

    #: 用户拖入/放下图片（参数是本地文件路径列表）
    files_dropped = Signal(list)
    #: 单击框体（宿主打开文件选择框）
    clicked = Signal()

    #: 框内缩略图单元（图标框大小）
    CELL_SIZE = QSize(84, 112)
    #: 框内边距
    PADDING = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: list[str] = []
        self._pixmaps: dict[str, QPixmap | None] = {}
        self._drag_active = False
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(200)

    # ------------------------------------------------------------------ 数据
    def files(self) -> list[str]:
        """已选图片的本地路径（副本，宿主最终拿去复制）。"""
        return list(self._files)

    def add_files(self, paths) -> None:
        """追加图片（自动去重）；重复拖入同一张不会出现两份。"""
        known = set(self._files)
        for path in paths:
            text = str(path)
            if text and text not in known:
                self._files.append(text)
                known.add(text)
        self.update()

    def clear(self) -> None:
        self._files.clear()
        self.update()

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(T.SURFACE_SOFT))
        painter.drawRoundedRect(rect, T.RADIUS_MD, T.RADIUS_MD)
        pen = QPen(QColor(T.ACCENT if self._drag_active else T.BORDER_STRONG))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, T.RADIUS_MD, T.RADIUS_MD)
        if not self._files:
            painter.setPen(QColor(T.INK_SOFT))
            painter.drawText(
                rect, Qt.AlignmentFlag.AlignCenter,
                "把图片拖到这里\n或点击选择图片",
            )
            return
        inner = rect.adjusted(
            self.PADDING, self.PADDING, -self.PADDING, -self.PADDING
        )
        step_x = self.CELL_SIZE.width() + T.SPACE_MD
        step_y = self.CELL_SIZE.height() + T.SPACE_MD
        cols = max(1, (inner.width() + T.SPACE_MD) // step_x)
        for index, path in enumerate(self._files):
            row, col = divmod(index, cols)
            x = inner.left() + col * step_x
            y = inner.top() + row * step_y
            if y + self.CELL_SIZE.height() > inner.bottom() + 1:
                break  # 框内不滚动，放不下的靠下方"N 张"提示兜底
            cell = QRect(x, y, self.CELL_SIZE.width(), self.CELL_SIZE.height())
            pixmap = self._pixmap_for(path)
            if pixmap is None or pixmap.isNull():
                continue
            shown = pixmap.scaled(
                cell.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(
                cell.left() + (cell.width() - shown.width()) // 2,
                cell.top() + (cell.height() - shown.height()) // 2,
                shown,
            )

    def _pixmap_for(self, path: str) -> QPixmap | None:
        """按单元尺寸**缩放解码**（不把原图整张读进内存），结果缓存。"""
        if path in self._pixmaps:
            return self._pixmaps[path]
        pixmap: QPixmap | None = None
        try:
            reader = QImageReader(path)
            size = reader.size()
            if size.isValid():
                reader.setScaledSize(
                    size.scaled(
                        self.CELL_SIZE, Qt.AspectRatioMode.KeepAspectRatio
                    )
                )
            image = reader.read()
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
        except Exception:
            pixmap = None
        self._pixmaps[path] = pixmap
        return pixmap

    # ------------------------------------------------------------------ 交互
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if _image_paths(event.mimeData()):
            event.acceptProposedAction()
            self._drag_active = True
            self.update()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if _image_paths(event.mimeData()):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        self._drag_active = False
        self.update()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = _image_paths(event.mimeData())
        self._drag_active = False
        self.update()
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self.files_dropped.emit(paths)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()


class PrintInsertPanel(QWidget):
    """「插入图片」弹窗的内容面板。"""

    #: 已删除图片网格里的小缩略图尺寸（恢复页一行多张）
    THUMB_SIZE = QSize(96, 128)
    #: 恢复页网格单元：缩略图 + 下方一页文字
    RESTORE_CELL = QSize(THUMB_SIZE.width() + 28, THUMB_SIZE.height() + 34)

    def __init__(
        self,
        *,
        deleted: list[dict] | None = None,
        current_row: int = -1,
        total: int = 0,
        default_position: str = "after",
        thumb_for: Callable[[str], object] | None = None,
        parent=None,
    ):
        """deleted: print.json 的 deleted_pages 记录；current_row/total 决定页号。"""
        super().__init__(parent)
        self._deleted = [dict(page) for page in (deleted or [])]
        self._thumb_for = thumb_for
        self.current_row = int(current_row)
        self.total = max(0, int(total))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(T.SPACE_MD)

        # ⚠️ 页签顺序（用户 2026-11-01）：**上传图片在前、删除恢复在后**，
        #    默认停在第一个页签（上传）。
        self.toggle = SegmentedToggle(
            [("upload", "上传图片"), ("restore", "删除恢复")]
        )
        self.toggle.setFixedWidth(320)
        self.toggle.current_changed.connect(self._set_page)
        root.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignLeft)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_upload_page())
        self.stack.addWidget(self._build_restore_page())
        root.addWidget(self.stack, 1)

        root.addWidget(self._build_position_row(default_position))
        self.toggle.set_current("upload")
        self.stack.setCurrentIndex(0)

    # ------------------------------------------------------------------ 页签
    def _set_page(self, key: str) -> None:
        self.stack.setCurrentIndex(0 if key == "upload" else 1)

    # ------------------------------------------------------------- 恢复图片页
    def _build_restore_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_SM)

        # 一行多张的图标网格（不是"一张一行"）：IconMode + 静态铺排 + 自动换行
        self.restore_list = QListWidget(page)
        self.restore_list.setViewMode(QListView.ViewMode.IconMode)
        self.restore_list.setFlow(QListView.Flow.LeftToRight)
        self.restore_list.setWrapping(True)
        self.restore_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.restore_list.setMovement(QListView.Movement.Static)
        self.restore_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.restore_list.setIconSize(self.THUMB_SIZE)
        self.restore_list.setGridSize(self.RESTORE_CELL)
        self.restore_list.setSpacing(2)
        self.restore_list.itemDoubleClicked.connect(self._toggle_item)
        for page_record in self._deleted:
            file_text = str(page_record.get("file") or "")
            label = page_record.get("label") or Path(file_text).stem
            item = QListWidgetItem(self._icon_for(file_text), str(label))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.restore_list.addItem(item)
        layout.addWidget(self.restore_list, 1)

        hint = QLabel(
            f"已删除 {len(self._deleted)} 张图片；勾选要恢复的图片（可多选），"
            "双击图片可切换勾选。"
            if self._deleted
            else "还没有删除过图片。"
        )
        apply_to(hint, T.SIZE_CAPTION, color=T.INK_SOFT)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        select_all = PushButton("全选 / 取消全选")
        select_all.setEnabled(bool(self._deleted))
        select_all.clicked.connect(self._toggle_all)
        row = QHBoxLayout()
        row.addWidget(select_all)
        row.addStretch()
        layout.addLayout(row)
        return page

    def _toggle_item(self, item: QListWidgetItem) -> None:
        """双击一张 = 切换勾选（比点小方框省事）。"""
        item.setCheckState(
            Qt.CheckState.Unchecked
            if item.checkState() == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )

    def _toggle_all(self) -> None:
        check = any(
            self.restore_list.item(row).checkState() != Qt.CheckState.Checked
            for row in range(self.restore_list.count())
        )
        state = Qt.CheckState.Checked if check else Qt.CheckState.Unchecked
        for row in range(self.restore_list.count()):
            self.restore_list.item(row).setCheckState(state)

    # ------------------------------------------------------------- 新上传页
    def _build_upload_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_SM)

        # 中间空白 = 虚线拖放框（用户 2026-11-01）：可拖入图片，也可点击选图
        self.drop_area = _DropArea(page)
        self.drop_area.files_dropped.connect(self._add_files)
        self.drop_area.clicked.connect(self._choose_files)
        layout.addWidget(self.drop_area, 1)

        self.upload_hint = QLabel("")
        apply_to(self.upload_hint, T.SIZE_CAPTION, color=T.INK_SOFT)
        layout.addWidget(self.upload_hint)
        self._sync_upload_hint()

        choose = PushButton("选择图片…")
        choose.clicked.connect(self._choose_files)
        clear = PushButton("清空")
        clear.clicked.connect(self._clear_files)
        row = QHBoxLayout()
        row.addWidget(choose)
        row.addWidget(clear)
        row.addStretch()
        layout.addLayout(row)
        return page

    def _choose_files(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", str(default_open_dir()), IMAGE_FILTER
        )
        if filenames:
            self._add_files(filenames)

    def _add_files(self, paths) -> None:
        """把（文件框选的 / 拖入的）图片加进虚线框。"""
        self.drop_area.add_files(paths)
        self._sync_upload_hint()

    def _clear_files(self) -> None:
        self.drop_area.clear()
        self._sync_upload_hint()

    def _sync_upload_hint(self) -> None:
        count = len(self.drop_area.files())
        self.upload_hint.setText(
            f"已选择 {count} 张图片。"
            if count else "尚未选择图片（也可以直接把图片拖进上方虚线框）。"
        )

    # ------------------------------------------------------------- 落点选项
    def _build_position_row(self, default_position: str) -> QWidget:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_MD)
        self.before_radio: RadioButton | None = None
        self.after_radio: RadioButton | None = None
        if self.total <= 0:
            label = QLabel("列表为空，图片将插入到列表开头。")
            apply_to(label, T.SIZE_CAPTION, color=T.INK_SOFT)
            layout.addWidget(label)
            layout.addStretch()
            return row
        page_no = min(max(self.current_row, 0) + 1, self.total)
        self.before_radio = RadioButton(f"插入第 {page_no} 页之前", row)
        self.after_radio = RadioButton(f"插入第 {page_no} 页之后", row)
        (self.before_radio if default_position == "before"
         else self.after_radio).setChecked(True)
        layout.addWidget(self.before_radio)
        layout.addWidget(self.after_radio)
        layout.addStretch()
        return row

    # ------------------------------------------------------------------ 结果
    def result_data(self) -> dict:
        """弹窗关闭后宿主读取的三件事：落点 / 恢复哪些 / 新上传哪些。"""
        restored: list[dict] = []
        if self._deleted and self.restore_list is not None:
            for row in range(self.restore_list.count()):
                item = self.restore_list.item(row)
                if (
                    item.checkState() == Qt.CheckState.Checked
                    and row < len(self._deleted)
                ):
                    restored.append(dict(self._deleted[row]))
        position = "after"
        if (
            self.before_radio is not None
            and self.before_radio.isChecked()
        ):
            position = "before"
        return {
            "position": position,
            "deleted": restored,
            "files": self.drop_area.files(),
        }

    # ------------------------------------------------------------------ 缩略图
    def _icon_for(self, file_text: str) -> QIcon:
        """按目标尺寸**缩放解码**缩略图（不把原图整张读进内存）。"""
        source = file_text
        if self._thumb_for is not None:
            try:
                provided = self._thumb_for(file_text)
            except Exception:
                provided = None
            if provided:
                source = str(provided)
        try:
            reader = QImageReader(source)
            size = reader.size()
            if size.isValid():
                reader.setScaledSize(
                    size.scaled(
                        self.THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                    )
                )
            image = reader.read()
            if image.isNull():
                return QIcon()
            return QIcon(QPixmap.fromImage(image))
        except Exception:
            return QIcon()


__all__ = ["PrintInsertPanel", "IMAGE_FILTER"]
