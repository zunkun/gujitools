# -*- coding: utf-8 -*-
"""生成 PDF（print）预览：左侧缩略图条 + 右侧单页效果预览。

布局与前三步保持一致（``ImageViewerWidget`` / ``RembgPreviewWidget`` 的
「左缩略图 + 右大图」），右侧不再是网格瀑布流：

- **打印效果**：按右侧表单参数（纸张/方向/边距/标题/页码）把图片排进一
  张纸里给用户在屏幕上看到——**只是效果，不执行、不提交、不生成 PDF**；
- **原图**：待打印图片本身（第三步「提交本次任务」的最终图）。

几何全部来自 ``utils.page_layout.plan_print_page``，而真正生成 PDF 的
``functions/print.py`` 用的是同一个函数，所以预览与成品不会漂移。

缩略图默认用条目图片本身（``ImageListWorker`` 走 QImageReader 缩放解码，
等于现算缩略图）；传入 ``thumb_provider`` 时改用它给出的预生成小图。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)
from qfluentwidgets import CaptionLabel, PrimaryPushButton, PushButton
from qfluentwidgets import FluentIcon as FIF

from desktop.ui import theme as T
from desktop.ui import widgets as ui
from desktop.ui.widgets import SegmentedToggle
from desktop.workers import ImageListWorker, PreviewWorker, connect_queued
from desktop.components.viewers.image_view import ImageView
from desktop.components.viewers.print_layout_canvas import PrintLayoutCanvas
from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.components.viewers.thumbs_loader import ThumbsMixin
from utils.page_layout import plan_print_page, print_page_size_mm


class PrintPreviewWidget(QWidget, ThumbsMixin):
    """生成 PDF 预览：左侧待打印缩略图条（可拖动排序）+ 右侧单页效果。"""

    order_changed = Signal()        # 列表内容/顺序变化（含拖动与删除）
    insert_requested = Signal()     # 请求插入图片
    download_requested = Signal()   # 请求下载已生成的 PDF
    hint = Signal(str)              # 需要宿主提示用户（如"未选中任何图片"）
    # 版面编辑：某一页的图片坐标（[x,y,w,h] mm）被拖拽/缩放改了
    layout_changed = Signal(int, list)

    # 缩略图解码最长边：取 ThumbStrip 的**框长边**（不是框宽）——
    # ImageListWorker 的 edge 是最长边语义，竖开本页面受高度约束，
    # 取框宽会让缩略图只有条目宽度的一半。
    THUMB_EDGE = ThumbStrip.DECODE_EDGE

    def __init__(
        self,
        empty_hint: str = "暂无图片，请先完成去底色",
        params_provider=None,
        thumb_provider=None,
        parent=None,
    ):
        """构建工具栏 + 左缩略图条 + 右效果预览。

        params_provider: () -> print 参数字典；非法时抛异常（由本控件捕获
            并退回「原图」显示）。为 None 时关闭「打印效果」项。
        thumb_provider: (path_text) -> Path | dict | None，可选的小图来源。
        """
        super().__init__(parent)
        self._init_thumbs()
        self._empty_hint = empty_hint
        self._entries_cache: list[dict] = []
        self._params_provider = params_provider
        self._thumb_provider = thumb_provider
        self._mode = "layout"       # layout / original
        self._load_token = None     # 请求令牌：仅最新一次加载生效
        self._pdf_path: Path | None = None
        self._canvas_index = 0      # 当前在画布上编辑的页下标

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(self._build_toolbar())

        body = QHBoxLayout()
        body.setSpacing(8)

        left = QVBoxLayout()
        self.strip = ThumbStrip()
        self.strip.set_reorderable(True)
        self.strip.order_changed.connect(self._on_strip_order_changed)
        self.strip.current_path_changed.connect(self._select_image)
        left.addWidget(self.strip, 1)
        body.addLayout(left)
        # 兼容旧名字：历史自测与宿主代码里有 print_preview.list 的用法
        self.list = self.strip

        right = QVBoxLayout()
        toggle_row = QHBoxLayout()
        # 三个视图：版面编辑（可拖拽/缩放，默认）、打印效果（含标题/页码的
        # 整页效果，只读）、原图。效果预览同样吃 rect，故编辑后切过去即所见。
        self.toggle = SegmentedToggle(
            [("layout", "版面编辑"), ("effect", "打印效果"),
             ("original", "原图")]
        )
        self.toggle.current_changed.connect(self._set_mode)
        toggle_row.addWidget(self.toggle)
        toggle_row.addStretch()
        right.addLayout(toggle_row)
        self.caption = CaptionLabel("")
        right.addWidget(self.caption)
        # 版面编辑器：在 A4 纸上拖拽/缩放图片（默认模式）
        self.canvas = PrintLayoutCanvas()
        self.canvas.rect_changed.connect(self._on_canvas_rect)
        right.addWidget(self.canvas, 1)
        # 原图查看（非编辑）：复用 ImageViewerWidget 的大图查看
        self.view = ImageView(empty_hint)
        self.view.hide()
        right.addWidget(self.view, 1)
        body.addLayout(right, 1)
        layout.addLayout(body, 1)

        self.empty_label = QLabel(empty_hint)
        self.empty_label.setWordWrap(True)
        ui.apply_to(self.empty_label, T.SIZE_LABEL, color=T.INK_FAINT)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label, 1)
        self.empty_label.hide()

    # ------------------------------------------------------------------ 构建
    def _build_toolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        self.insert_button = PrimaryPushButton(FIF.ADD, "插入图片")
        self.insert_button.clicked.connect(self.insert_requested.emit)
        self.delete_button = PushButton(FIF.DELETE, "删除选中")
        self.delete_button.clicked.connect(self.remove_selected)
        self.download_button = PrimaryPushButton(FIF.SAVE, "下载 PDF")
        self.download_button.setToolTip("请先执行「生成 PDF」后再下载")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.download_requested.emit)
        self.hint_label = CaptionLabel("拖动缩略图排序 · Delete 删除选中")
        toolbar.addWidget(self.insert_button)
        toolbar.addWidget(self.delete_button)
        toolbar.addWidget(self.download_button)
        toolbar.addStretch()
        toolbar.addWidget(self.hint_label)
        return toolbar

    # ------------------------------------------------------------------ API
    def set_entries(self, entries: list[dict]) -> None:
        """重建列表：entries = [{file, label}]，可按条目自带 thumb 指定小图。"""
        self._stop_worker()
        self._entries_cache = list(entries)
        self.strip.clear()
        if not entries:
            self.view.clear_image(self._empty_hint)
            self.caption.setText("")
            return
        for index, entry in enumerate(entries):
            label = entry.get("label") or Path(entry["file"]).stem
            self.strip.add_page_item(str(label), str(entry["file"]))
            self.strip.item(index).setData(Qt.UserRole + 1, index)
        self._load_page_thumbs()
        self._select_entry(0)

    def entries(self) -> list[dict]:
        """当前视觉顺序的富条目列表。"""
        return list(self._entries_cache)

    def count(self) -> int:
        """列表当前条目数。"""
        return len(self._entries_cache)

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
        """删除所有选中条目，未选中则通过 hint 信号提示。"""
        rows = sorted(
            {self.strip.row(item) for item in self.strip.selectedItems()},
            reverse=True,
        )
        if not rows:
            self.hint.emit("请先在左侧缩略图条选中要删除的图片。")
            return
        for row in rows:
            self.strip.takeItem(row)
        self._sync_cache_order()
        self._emit_order_changed()
        self._load_display()

    def refresh_display(self) -> None:
        """右侧参数变化后按最新参数重画当前页（不生成任何文件）。"""
        if self._mode == "layout":
            self.refresh_layout()
        else:
            self._load_display()

    # ------------------------------------------------------------------ 内部
    def _stop_worker(self) -> None:
        for thread in getattr(self, "_threads", []):
            thread.quit()

    def _thumb_path_for(self, entry: dict) -> Path:
        """条目缩略图来源：条目自带 thumb → provider → 条目图片本身。"""
        spec = entry.get("thumb")
        if isinstance(spec, dict) and spec.get("path"):
            return Path(spec["path"])
        if spec:
            return Path(spec)
        file_text = str(entry["file"])
        if self._thumb_provider is not None:
            try:
                provided = self._thumb_provider(file_text)
            except Exception:
                provided = None
            if isinstance(provided, dict) and provided.get("path"):
                return Path(provided["path"])
            if provided:
                return Path(provided)
        return Path(file_text)

    def _load_page_thumbs(self) -> None:
        """加载左侧缩略图（缩放解码 = 现算小图，不落盘）。

        名字带 page 是为了与 ThumbsMixin 的 ``_load_thumbs(strip, paths)``
        区分——后者签名不同，两者互不覆盖。
        """
        entries = self._entries_cache
        if not entries:
            return
        paths = [self._thumb_path_for(e) for e in entries]
        labels = [
            str(e.get("label") or Path(str(e["file"])).stem) for e in entries
        ]
        self.run_worker(
            lambda: ImageListWorker(paths, edge=self.THUMB_EDGE),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.thumbnail_ready,
                    lambda i, img, _p: self.strip.set_item_icon(
                        i, img, str(entries[i]["file"]), labels[i]
                    ),
                    thread,
                ),
                worker.completed.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _current_index(self) -> int:
        row = self.strip.currentRow()
        if row < 0:
            return 0
        return row

    def _select_image(self, index: int, _path: str) -> None:
        if index >= len(self._entries_cache):
            return
        self.strip.setCurrentRow(index)
        self._load_display()

    def _select_entry(self, index: int) -> None:
        if not self._entries_cache or index >= len(self._entries_cache):
            return
        self.strip.setCurrentRow(index)
        self._load_display()

    def _set_mode(self, mode: str) -> None:
        if self._mode != mode:
            self._mode = mode
            self._load_display()

    def _on_strip_order_changed(self) -> None:
        self._sync_cache_order()
        self._emit_order_changed()

    def _sync_cache_order(self) -> None:
        """按当前视觉顺序重排富条目缓存，并重分配条目索引。"""
        order = []
        for row in range(self.strip.count()):
            index = self.strip.item(row).data(Qt.UserRole + 1)
            if index is not None and 0 <= index < len(self._entries_cache):
                order.append(int(index))
        # 删除后 order 会短于缓存——这正是"去掉被删条目"的效果，不能拦
        self._entries_cache = [self._entries_cache[i] for i in order]
        for row in range(self.strip.count()):
            self.strip.item(row).setData(Qt.UserRole + 1, row)

    def _emit_order_changed(self) -> None:
        if self._entries_cache:
            self.order_changed.emit()

    # ------------------------------------------------------------------ 加载
    def _print_spec(self, index: int, path: Path) -> tuple[dict | None, str]:
        """返回 (print_spec, 提示文案)；参数非法时 spec 为 None。"""
        if self._params_provider is None:
            return None, "未接入打印参数，已显示原图"
        try:
            args = self._params_provider()
        except Exception as exc:  # 颜色/边距填了一半：不阻塞预览
            return None, f"参数暂不合法：{exc}"
        if not isinstance(args, dict):
            return None, "未接入打印参数，已显示原图"
        return (
            {
                "args": args,
                "index": index,
                "total": len(self._entries_cache),
                "name": path.stem,
                # 逐图坐标覆盖：有则预览/成品都按此框排（与 plan_print_page
                # 同源）。宿主可能在没有条目时先取 spec 校验接线，故越界给 None。
                "rect": (
                    self._entries_cache[index].get("rect")
                    if 0 <= index < len(self._entries_cache) else None
                ),
            },
            "",
        )

    # ------------------------------------------------------------------ 版面编辑
    def _page_size_mm(self) -> tuple[float, float]:
        """当前纸张尺寸（mm），由打印参数推导；非法时回落 A4 横版。"""
        try:
            args = self._params_provider() or {}
        except Exception:
            args = {}
        return print_page_size_mm(
            args.get("paper_size", "A4"),
            args.get("orientation", "landscape"),
        )

    def _plan_for(self, index: int, path: Path, rect=None):
        """该页的完整排版几何（含标题/页码/跳过态）。

        ``rect`` 为已存的逐图坐标：传进去才能让**标题/页码也按同一份覆盖**
        算出来（它们的落点只取决于 page_margins，但 skipped/side 等仍需
        plan 给出）。返回 ``(plan, image)``，读图失败时为 ``(None, None)``。
        """
        try:
            args = self._params_provider() or {}
        except Exception:
            args = {}
        image = QImage(str(path))
        if image.isNull():
            return None, None
        plan = plan_print_page(
            (image.width(), image.height()), args, index,
            len(self._entries_cache), image_name=path.stem,
            image_rect=rect,
        )
        return plan, image

    def _show_layout(self, index: int) -> None:
        """在画布上编辑第 index 页：纸 + 图片 + 标题/页码，框可拖可缩放。"""
        self.view.hide()
        self.canvas.show()
        if index < 0 or index >= len(self._entries_cache):
            self.canvas.set_page(*self._page_size_mm(), None, [0.0, 0.0, 0.0, 0.0])
            return
        self._canvas_index = index
        entry = self._entries_cache[index]
        path = Path(str(entry["file"]))
        total = len(self._entries_cache)
        pw, ph = self._page_size_mm()
        if not path.exists():
            self.canvas.set_page(pw, ph, None, [0.0, 0.0, 0.0, 0.0])
            self.caption.setText(f"图片不存在：{path.name}")
            return
        # 已存坐标优先；否则用当前自动排版作为初始位置（用户再微调）。
        # 两种情况都要拿到完整 plan——标题/页码属于版面，编辑器必须画出来。
        rect = entry.get("rect")
        plan, image = self._plan_for(index, path, rect)
        if plan is None:
            self.canvas.set_page(pw, ph, None, [0.0, 0.0, 0.0, 0.0])
            self.caption.setText(f"图片无法读取：{path.name}")
            return
        if rect is None:
            rect = list(plan.image)
        self.canvas.set_page(pw, ph, image, rect, plan)
        self.caption.setText(
            f"版面编辑 · 第 {index + 1}/{total} 页 · 拖动图片移动，拖四角缩放"
        )

    def _on_canvas_rect(self, rect: list) -> None:
        """画布拖拽/缩放结束：写回条目并通知宿主（落盘 + 标脏）。"""
        index = self._canvas_index
        if 0 <= index < len(self._entries_cache):
            self._entries_cache[index]["rect"] = list(rect)
        self.layout_changed.emit(index, list(rect))

    def refresh_layout(self) -> None:
        """参数（纸张/方向）变化后刷新画布：保留已存坐标，仅重算页面尺寸。"""
        if self._mode == "layout":
            self._show_layout(self._current_index())

    def _load_display(self) -> None:
        if not self._entries_cache:
            self.canvas.hide()
            self.view.clear_image(self._empty_hint)
            self.caption.setText("")
            return
        index = self._current_index()
        if index >= len(self._entries_cache):
            return
        if self._mode == "layout":
            self._show_layout(index)
            return
        self.canvas.hide()
        self.view.show()
        entry = self._entries_cache[index]
        path = Path(str(entry["file"]))
        total = len(self._entries_cache)
        if not path.exists():
            self.view.clear_image(f"图片不存在：{path.name}")
            self.caption.setText("")
            return
        print_spec = None
        note = ""
        if self._mode == "effect":
            print_spec, note = self._print_spec(index, path)
        if note:
            self.caption.setText(note)
        elif print_spec is not None:
            self.caption.setText(
                f"打印效果 · 第 {index + 1}/{total} 页 · 仅预览，不会生成 PDF"
            )
        else:
            self.caption.setText(f"原图 · 第 {index + 1}/{total} 页")
        self.view.clear_image("正在加载...")
        token = self._load_token = object()
        self.run_worker(
            lambda: PreviewWorker(
                path, longest_edge=1600, print_spec=print_spec
            ),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.finished,
                    lambda _p, image, _s, t=token: self._display(t, image),
                    thread,
                ),
                connect_queued(
                    self,
                    worker.failed,
                    lambda _p, msg, t=token: self._load_failed(t, msg),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _load_failed(self, token, msg: str) -> None:
        if token is not self._load_token:
            return
        self.view.clear_image(f"加载失败：{msg}")

    def _display(self, token, image) -> None:
        if token is not self._load_token:
            return
        self.view.set_image(image, image_size=image.size())
