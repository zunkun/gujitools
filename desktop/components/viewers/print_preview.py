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
from PySide6.QtGui import QPageLayout, QPageSize, QImage, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)
from qfluentwidgets import CaptionLabel, PrimaryPushButton, PushButton
from qfluentwidgets import FluentIcon as FIF

from desktop.ui import theme as T
from desktop.ui import widgets as ui
from desktop.ui.widgets import SegmentedToggle
from desktop.workers import ImageListWorker, PreviewWorker, connect_queued
from desktop.components.viewers.image_view import ImageView
from desktop.components.viewers.image_zoom_dialog import (
    ZoomPopupMixin, ZoomTarget, save_image,
)
from desktop.components.viewers.print_layout_canvas import PrintLayoutCanvas
from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.components.viewers.thumbs_loader import ThumbsMixin
from utils.page_layout import plan_print_page, print_page_size_mm


class PrintPreviewWidget(QWidget, ThumbsMixin, ZoomPopupMixin):
    """生成 PDF 预览：左侧待打印缩略图条（可拖动排序）+ 右侧单页效果。"""

    order_changed = Signal()        # 列表内容/顺序变化（含拖动与删除）
    insert_requested = Signal()     # 请求插入图片
    download_requested = Signal()   # 请求下载已生成的 PDF
    # 请求把**当前页**导出为 A4 效果图片（宿主弹保存对话框，见 _export_print_image）
    export_image_requested = Signal()
    export_finished = Signal(str)   # 导出成功：文件路径
    export_failed = Signal(str)     # 导出失败：原因
    print_finished = Signal(str)    # 打印成功：打印机名
    print_failed = Signal(str)      # 打印失败：原因
    hint = Signal(str)              # 需要宿主提示用户（如"未选中任何图片"）
    # 版面编辑：某一页的图片坐标（[x,y,w,h] mm）被拖拽/缩放改了
    layout_changed = Signal(int, list)

    #: 导出图片的精度：与 PDF **同级**（`functions/print.py` 的 `PRINT_IMAGE_DPI`）。
    #: 密度上限由 `compose_print_page` 夹住（不得超过源图原生密度），小图不会被拉大。
    EXPORT_IMAGE_DPI = 300

    #: print 参数的纸张名 → Qt 页面尺寸（打印用；候选与表单 PAPER_SIZES 一致）
    _PAPER_TO_QPAGE = {
        "A3": QPageSize.PageSizeId.A3,
        "A4": QPageSize.PageSizeId.A4,
        "A5": QPageSize.PageSizeId.A5,
        "B5": QPageSize.PageSizeId.B5,
    }

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
        #: 与 _entries_cache **同序同长**的条目身份令牌（每个条目一个 object()）。
        #: 缩略图是分批异步装的，若按"派发时的行号"落值，用户在装载途中删除/
        #: 拖动条目就会把 A 页的图写到 B 页那一行（见 _apply_page_thumb）。
        self._entry_keys: list[object] = []
        self._params_provider = params_provider
        self._thumb_provider = thumb_provider
        self._mode = "layout"       # layout / original
        self._load_token = None     # 请求令牌：仅最新一次加载生效
        self._export_token = None   # 单页导出令牌：作废在飞的导出
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
        # 工具条提示写着「Delete 删除选中」，那就得真的响应 Delete/Backspace
        # （ThumbStrip 只管把键翻成信号，删哪些仍由本类的 remove_selected 决定）
        self.strip.set_deletable(True)
        self.strip.delete_requested.connect(self.remove_selected)
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
        # 双击画布 → 预览弹窗（版面编辑模式下看该页的打印效果放大；
        # 打印效果/原图模式的双击在 self.view 上，见 _init_zoom_popup）
        self.canvas.double_clicked.connect(self._open_zoom_popup)
        right.addWidget(self.canvas, 1)
        # 原图查看（非编辑）：复用 ImageViewerWidget 的大图查看
        self.view = ImageView(empty_hint)
        self.view.hide()
        right.addWidget(self.view, 1)
        # 双击大图 → 图片预览弹窗（打印效果按目标边长**重新排版**，见 _zoom_target）
        self._init_zoom_popup(self.view)
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
        # 单页导出：当前页排进 A4 纸后的**最终效果**（与 PDF 同精度），不生成 PDF
        self.export_image_button = PushButton(FIF.IMAGE_EXPORT, "下载本页图片")
        self.export_image_button.setToolTip(
            f"把当前页按 A4 打印效果导出为图片"
            f"（{self.EXPORT_IMAGE_DPI}dpi，单页）"
        )
        self.export_image_button.clicked.connect(self.export_image_requested.emit)
        # 单页打印：与导出同一份渲染（A4 效果图），交系统打印对话框选打印机
        self.print_button = PushButton(FIF.PRINT, "打印本页")
        self.print_button.setToolTip(
            f"把当前页按 A4 打印效果送到打印机"
            f"（{self.EXPORT_IMAGE_DPI}dpi，单页）"
        )
        self.print_button.clicked.connect(self._print_current)
        self.hint_label = CaptionLabel("拖动缩略图排序 · Delete 删除选中")
        # ⚠️ 提示文字是**次要信息**，必须能被压缩：QLabel 的 minimumSizeHint 默认
        # 等于文字宽度（`setMinimumWidth(0)` 也压不动它，布局看的是 minimumSizeHint），
        # 于是它会以固定宽度占住工具栏，把**整页/整个详情页**的最窄需求抬高——
        # 窗口宽度固定时，被挤窄的是左侧控制面板（实测第三步输入框 200 → 178px，
        # 正是 `panel_label_fit` 那条不变量在守的东西）。Ignored 策略让布局可以
        # 把它压到 0，窄窗口下先牺牲提示、不牺牲输入框。
        self.hint_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        toolbar.addWidget(self.insert_button)
        toolbar.addWidget(self.delete_button)
        toolbar.addWidget(self.export_image_button)
        toolbar.addWidget(self.print_button)
        toolbar.addWidget(self.download_button)
        toolbar.addStretch()
        toolbar.addWidget(self.hint_label)
        # 初建时列表为空 → 先禁用（不能只等 set_entries，它会早退）
        self._sync_export_button()
        return toolbar

    # ------------------------------------------------------------------ API
    def set_entries(self, entries: list[dict]) -> None:
        """重建列表：entries = [{file, label}]，可按条目自带 thumb 指定小图。"""
        self._stop_worker()
        # 列表整个换了一批：弹窗按"打开时的条目"取源，留着就是旧数据/错位
        self.close_zoom_popup()
        self._entries_cache = list(entries)
        # 身份令牌与条目一一对应重建：列表整个换了一批，旧令牌全部作废
        self._entry_keys = [object() for _ in entries]
        self._sync_export_button()
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
        self._sync_export_button()
        self._emit_order_changed()
        self._load_display()

    def refresh_display(self) -> None:
        """右侧参数变化后按最新参数重画当前页（不生成任何文件）。"""
        if self._mode == "layout":
            self.refresh_layout()
        else:
            self._load_display()
        # ⚠️ 弹窗里那页是**打开时的快照**：纸张/方向/标题/页码一变就过期
        # （用户 17:50 反馈"预览要按配置的纸张大小适配 A4/A5 等"——渲染链路
        # 本就跟随参数，过期的是已打开的快照）。不关窗打断查看，重渲染当前页。
        self._refresh_zoom_popup_if_open()

    def _refresh_zoom_popup_if_open(self) -> None:
        """弹窗开着 → 用**当前参数**重渲染该页（快照保持新鲜）。"""
        dialog = self._zoom_dialog
        if dialog is None or not dialog.isVisible():
            return
        dialog.show_for(index=self._current_index())

    def navigate(self, forward: bool) -> None:
        """方向键翻页（详情页 ←/→ 调用；联动预览刷新，见 ThumbStrip.navigate）。"""
        self.strip.navigate(forward)

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

        ⚠️ 走基类 ``_load_thumbs_chunked`` 分批：页面多时一次性解码会把
        一个核打满（风扇起转），分批后首批立刻可见、其余按间隙补齐。

        ⚠️ 分批派发的是**条目身份令牌**而不是下标：批次跑完之前用户可能已经
        删除/拖动过条目，行号会变（详见 :meth:`_apply_page_thumb`）。
        """
        entries = self._entries_cache
        if not entries:
            return
        pending = [
            (key, self._thumb_path_for(entry))
            for key, entry in zip(self._entry_keys, entries)
        ]
        keys = [key for key, _ in pending]
        edge = self._decode_edge(self.THUMB_EDGE)
        self._load_thumbs_chunked(
            len(pending),
            make_worker=lambda start, end: ImageListWorker(
                [path for _, path in pending[start:end]], edge=edge
            ),
            sink=lambda index, image, _path, keys=keys: (
                self._apply_page_thumb(keys[index], image)
                if 0 <= index < len(keys) else None
            ),
        )

    def _apply_page_thumb(self, key, image) -> None:
        """某条目的缩略图就绪：**按身份**找回它当前所在的行再落值。

        ⚠️ 这里绝不能用"派发时的下标"。缩略图是分批异步装的（首批 10 张，
        之后每批 12 张、首轮还要等 2s），一本几百页的书尾部要好几秒才补齐；
        这期间用户删掉/拖动了条目，行号就整体前移了——按旧下标写会把
        「别的页的图 + 别的页的标签 + 别的页的路径」一并刷到这一行上。后果
        不只是看着乱：用户照着缩略图删页，删掉的是**数据层那一条**，跟屏幕
        上看到的页不是同一张（2026-09-23 用户报「缩略图跟真实图片映射乱了，
        我就删除了某些页」）。条目已被删除（令牌找不到）时直接丢弃。
        """
        try:
            row = self._entry_keys.index(key)
        except ValueError:
            return
        entry = self._entries_cache[row]
        label = entry.get("label") or Path(str(entry["file"])).stem
        self.strip.set_item_icon(row, image, str(entry["file"]), str(label))

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
        keys = self._entry_keys
        if len(keys) != len(self._entries_cache):
            # 正常不会走到（两个表只在 set_entries / 本方法里成对重建）；
            # 真错位也只重建令牌，绝不让 IndexError 把同步链路打断
            keys = [object() for _ in self._entries_cache]
        self._entries_cache = [self._entries_cache[i] for i in order]
        # 身份令牌必须与条目**同步换序**：_apply_page_thumb 靠它找回条目
        # 当前所在的行号，两者一旦错位就会把缩略图写到别的页上
        self._entry_keys = [keys[i] for i in order]
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
        # 「原比例缩放」决定画布手感（四角等比 vs 四角+四边自由拉伸）。
        # ⚠️ 参数可能填了一半（provider 抛 ValueError）：兜底 True，别挡住编辑。
        keep_ratio = True
        if self._params_provider is not None:
            try:
                keep_ratio = bool(
                    (self._params_provider() or {}).get("keep_ratio", True)
                )
            except Exception:
                keep_ratio = True
        if index < 0 or index >= len(self._entries_cache):
            self.canvas.set_page(*self._page_size_mm(), None,
                                 [0.0, 0.0, 0.0, 0.0], keep_ratio=keep_ratio)
            return
        self._canvas_index = index
        entry = self._entries_cache[index]
        path = Path(str(entry["file"]))
        total = len(self._entries_cache)
        pw, ph = self._page_size_mm()
        if not path.exists():
            self.canvas.set_page(pw, ph, None, [0.0, 0.0, 0.0, 0.0],
                                 keep_ratio=keep_ratio)
            self.caption.setText(f"图片不存在：{path.name}")
            return
        # 已存坐标优先；否则用当前自动排版作为初始位置（用户再微调）。
        # 两种情况都要拿到完整 plan——标题/页码属于版面，编辑器必须画出来。
        rect = entry.get("rect")
        plan, image = self._plan_for(index, path, rect)
        if plan is None:
            self.canvas.set_page(pw, ph, None, [0.0, 0.0, 0.0, 0.0],
                                 keep_ratio=keep_ratio)
            self.caption.setText(f"图片无法读取：{path.name}")
            return
        if rect is None:
            rect = list(plan.image)
        self.canvas.set_page(pw, ph, image, rect, plan, keep_ratio=keep_ratio)
        handle_hint = (
            "拖四角等比缩放，拖四边拉伸宽/高"
            if keep_ratio else
            "拖四角/四边拉伸（可改变比例）"
        )
        self.caption.setText(
            f"版面编辑 · 第 {index + 1}/{total} 页 · 拖动移动，{handle_hint}，"
            f"双击放大预览"
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
        # ⚠️ 渲染密度在 GUI 线程先算好（worker 线程不得碰 QWidget）
        edge = self.view.preview_edge()
        if print_spec is not None:
            # 「打印效果」必须让 worker 按目标边长**重新排版**（target_edge），
            # 而且密度要**高于屏幕需求**（超采样）。原因不是"像素不够"：
            # Qt 的 SmoothTransformation 在**一次大比例缩小**时质量明显差于
            # "分两档温和缩放"，所以中间画布越大越接近理想。
            # 实测（A4 横向、源图 5873x3539、视口长边 788、最终显示 756）：
            #   合成 1600 → worker 缩到 1200 → 显示   锐度 13121（旧口径）
            #   合成 1200（=preview_edge）→ 显示       16165
            #   合成 3000（本条）→ 显示                23200 ← 接近理想 23387
            #   合成 = 显示尺寸（1:1）→ 显示            9797  ← 反而最糊
            render_edge = max(edge, ImageView.MAX_PREVIEW_EDGE)
            print_spec = {**print_spec, "target_edge": render_edge}
        # longest_edge=0（不缩放）：画布已按 target_edge 的密度合成，这里再缩
        # 一次纯属白扔细节。密度的上限（不超过源图原生密度，防放大）由
        # compose_print_page 自己夹住，小图不会被拉大。
        self.run_worker(
            lambda: PreviewWorker(
                path,
                longest_edge=0 if print_spec is not None else edge,
                print_spec=print_spec,
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

    # -------------------------------------------------------------- 单页导出
    def _sync_export_button(self) -> None:
        """有没有可操作的单页（没页就别让导出/打印可点，点了只能弹空对话框）。"""
        enabled = bool(self._entries_cache)
        self.export_image_button.setEnabled(enabled)
        self.print_button.setEnabled(enabled)

    def export_default_name(self) -> str | None:
        """导出对话框的默认文件名；没有可导出的页时返回 None。"""
        index = self._current_index()
        if not (0 <= index < len(self._entries_cache)):
            return None
        stem = Path(str(self._entries_cache[index]["file"])).stem
        return f"{stem}-打印效果.png"

    def export_current_effect(self, target: str | Path) -> None:
        """把**当前页**排进纸面后的 A4 效果图按 300dpi 写到 ``target``。

        单页、不生成 PDF。走 worker 合成（与预览同一条 ``compose_print_page``
        链路），所以"下载的图 = 屏幕上看到的效果"，只是精度与 PDF 同级而非
        受屏幕像素限制。参数不合法/无条目时发 :attr:`export_failed`。
        """
        index = self._current_index()
        if not (0 <= index < len(self._entries_cache)):
            self.export_failed.emit("没有可导出的页面")
            return
        path = Path(str(self._entries_cache[index]["file"]))
        if not path.exists():
            self.export_failed.emit(f"图片不存在：{path.name}")
            return
        spec, note = self._print_spec(index, path)
        if spec is None:
            self.export_failed.emit(note or "打印参数不合法")
            return
        target = Path(target)
        edge = self._export_edge()
        token = self._export_token = object()
        self.run_worker(
            lambda: PreviewWorker(
                path, longest_edge=0,
                print_spec={**spec, "target_edge": edge},
            ),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.finished,
                    lambda _p, image, _s, t=token: self._write_export(
                        t, image, target
                    ),
                    thread,
                ),
                connect_queued(
                    self,
                    worker.failed,
                    lambda _p, msg, t=token: self._export_failed(t, msg),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _export_edge(self) -> int:
        """导出密度（= 与 PDF 同级的 300dpi）对应的**最长边**像素数。"""
        args: dict = {}
        if self._params_provider is not None:
            try:
                args = self._params_provider() or {}
            except Exception:
                args = {}  # 参数半填状态：按默认纸张算，别挡住导出
        w_mm, h_mm = print_page_size_mm(
            args.get("paper_size") or "A4",
            args.get("orientation") or "landscape",
        )
        return max(1, round(max(w_mm, h_mm) / 25.4 * self.EXPORT_IMAGE_DPI))

    def _write_export(self, token, image, target: Path) -> None:
        """在主线程落盘（``save_image`` 按后缀选 PNG/JPEG）。"""
        if token is not self._export_token:
            return
        if not save_image(image, target):
            self.export_failed.emit(f"写入失败：{target}")
            return
        self.export_finished.emit(str(target))

    def _export_failed(self, token, message: str) -> None:
        if token is not self._export_token:
            return
        self.export_failed.emit(str(message))

    # -------------------------------------------------------------- 单页打印
    def _render_current_effect_sync(self):
        """同步渲染当前页的 A4 效果图 → (QImage, 错误文案)。

        与导出/预览同一条 `compose_print_page` 链路、同 300dpi 精度；
        同步执行（A4 合成约几十毫秒，打印对话框弹出前完成，不打断操作流）。
        """
        index = self._current_index()
        if not (0 <= index < len(self._entries_cache)):
            return None, "没有可打印的页面"
        path = Path(str(self._entries_cache[index]["file"]))
        if not path.exists():
            return None, f"图片不存在：{path.name}"
        spec, note = self._print_spec(index, path)
        if spec is None:
            return None, note or "打印参数不合法"
        captured: dict = {}
        worker = PreviewWorker(
            path, longest_edge=0,
            print_spec={**spec, "target_edge": self._export_edge()},
        )
        worker.finished.connect(
            lambda _p, image, _s: captured.update(image=image)
        )
        worker.run()  # 同线程直跑（run() 是普通方法），免异步等待
        image = captured.get("image")
        if image is None or image.isNull():
            return None, "渲染失败"
        return image, ""

    def _print_current(self) -> None:
        """把当前页的 A4 效果图送到打印机（对话框里选打印机/份数）。

        纸张与方向**按右侧参数**设置——效果图就是按它排版的，纸面与预览
        一致；对话框里仍可换打印机/份数/逐份打印。
        """
        from PySide6.QtGui import QPageLayout

        image, err = self._render_current_effect_sync()
        if image is None:
            self.print_failed.emit(err)
            return
        args: dict = {}
        if self._params_provider is not None:
            try:
                args = self._params_provider() or {}
            except Exception:
                args = {}
        paper = str(args.get("paper_size") or "A4").upper()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageSize(QPageSize(
            self._PAPER_TO_QPAGE.get(paper, QPageSize.PageSizeId.A4)
        ))
        landscape = str(args.get("orientation") or "landscape").lower() in (
            "l", "landscape"
        )
        printer.setPageOrientation(
            QPageLayout.Orientation.Landscape if landscape
            else QPageLayout.Orientation.Portrait
        )
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle(f"打印当前页（{paper} "
                              f"{'横版' if landscape else '竖版'}）")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        painter = QPainter(printer)
        # 效果图与纸张**同比例**（plan 按纸面排版）→ 等比铺满可打印区
        # 就是整页还原，不会变形；页边留白由打印机驱动自己保守处理
        painter.drawImage(printer.pageRect(QPrinter.Unit.DevicePixel), image)
        painter.end()
        self.print_finished.emit(printer.printerName())

    # -------------------------------------------------------------- 图片预览
    def _zoom_index(self) -> int:
        """放大弹窗当前页 = 列表当前行。"""
        return self._current_index()

    def _zoom_target(self, index: int) -> ZoomTarget | None:
        """第 index 页的图片预览来源：原图模式给原图，其余按打印效果重排。

        ⚠️ 打印效果必须让 worker **按目标边长重新排版**（``target_edge``）：
        ``compose_print_page`` 默认按 ``preview_px_per_mm``（目标 1600px 长边）
        合成，直接放大会连标题/页码一起糊掉（见 preview_worker._load_image）。
        """
        if not (0 <= index < len(self._entries_cache)):
            return None
        path = Path(str(self._entries_cache[index]["file"]))
        if not path.exists():
            return None
        count = len(self._entries_cache)
        if self._mode == "original":
            return ZoomTarget(
                render=lambda edge: PreviewWorker(path, longest_edge=edge),
                note=f"原图 · 第 {index + 1}/{count} 页",
                stem=path.stem,
                count=count,
            )
        spec, note = self._print_spec(index, path)
        if spec is None:
            # 参数不合法时主预览也退回原图，弹窗保持一致（不另造一套逻辑）
            return ZoomTarget(
                render=lambda edge: PreviewWorker(path, longest_edge=edge),
                note=f"原图（{note}） · 第 {index + 1}/{count} 页",
                stem=path.stem,
                count=count,
            )
        return ZoomTarget(
            render=lambda edge: PreviewWorker(
                path,
                # 0=不缩放：画布已按 target_edge 的密度重新排版，别再缩一次
                longest_edge=0,
                print_spec={**spec, "target_edge": edge},
            ),
            note=f"打印效果 · 第 {index + 1}/{count} 页",
            stem=path.stem,
            count=count,
        )
