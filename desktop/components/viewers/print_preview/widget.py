# -*- coding: utf-8 -*-
"""print 预览主控件 ``PrintPreviewWidget``：**装配点 + 展示主路径**。

从 ``print_preview.py`` 拆出（2026-10-07）。本文件放：类头（信号/类属性）、
``__init__``、动作按钮、条目增删、当前页展示（``_load_display`` 等），以及
宿主协议（``_zoom_index`` / ``_zoom_target`` / ``_on_zoom_image_saved``）。
缩略图、版面、导出分别由兄弟模块的 Mixin 提供；方法体逐字未改。

⚠️ 宿主协议三个方法必须**留在本类**（不能下沉到 Mixin）——它们要盖住
``ZoomPopupMixin`` 的同名默认实现，靠的是"本类方法优先于基类"。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPageSize
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, MessageBox, PrimaryPushButton, PushButton
from qfluentwidgets import FluentIcon as FIF
from desktop.ui import theme as T
from desktop.ui import widgets as ui
from desktop.ui.widgets import SegmentedToggle
from desktop.workers import PreviewWorker, connect_queued
from desktop.components.viewers.image_view import ImageView
from desktop.components.viewers.image_zoom_dialog import ZoomPopupMixin, ZoomTarget
from desktop.components.viewers.print_layout_canvas import PrintLayoutCanvas
from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.components.viewers.thumbs_loader import ThumbsMixin

from .export import PrintExportMixin
from .layout import PrintLayoutMixin
from .thumbs import PrintThumbsMixin


class PrintPreviewWidget(
    PrintExportMixin,
    PrintLayoutMixin,
    PrintThumbsMixin,
    QWidget,
    ThumbsMixin,
    ZoomPopupMixin,
):
    """PDF排版预览：左侧待打印缩略图条（可拖动排序）+ 右侧单页效果。"""

    order_changed = Signal()        # 列表内容/顺序变化（含拖动与删除）
    manage_requested = Signal()     # 请求打开「管理图片」弹窗（草稿式）
    # 右键菜单：向前 / 向后插入图片（弹窗里落点可再改）
    insert_before_requested = Signal()
    insert_after_requested = Signal()
    #: 已生成 PDF 的可用状态变了（宿主据此显示/隐藏右下方控制面板的「下载 PDF」）
    pdf_state_changed = Signal(bool)
    # 请求把**当前页**导出为 A4 效果图片（宿主弹保存对话框，见 _export_print_image）
    export_image_requested = Signal()
    export_finished = Signal(str)   # 导出成功：文件路径
    export_failed = Signal(str)     # 导出失败：原因
    print_finished = Signal(str)    # 打印成功：打印机名
    print_failed = Signal(str)      # 打印失败：原因
    hint = Signal(str)              # 需要宿主提示用户（如"未选中任何图片"）
    # 版面编辑：某一页的图片坐标（[x,y,w,h] mm）被拖拽/缩放改了
    layout_changed = Signal(int, list)
    #: 编辑器覆盖了某张待打印图 ``image_saved(path, edited)``：宿主据此记日志
    #: （提示"点「生成PDF」即生效"）——待打印图就是最终进 PDF 的那张
    image_saved = Signal(str, object)

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
        params_provider: Callable[[], dict] | None = None,
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
        #: 缩略图右键菜单（非阻塞弹窗，不持有引用就没人回收；见 _show_context_menu）
        self._context_menu = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._build_action_buttons()

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
        # 右键缩略图：删除当前图片（软删除，可在「管理图片 → 插入图片」里恢复）/
        # 向前插入 / 向后插入（均打开插入弹窗，落点可再改）
        self.strip.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.strip.customContextMenuRequested.connect(self._show_context_menu)
        left.addWidget(self.strip, 1)
        # 「管理图片」按钮放在缩略图**下面**（用户 2026-10-31 / 2026-11-02）：
        # 点它弹草稿式管理弹窗（网格多选/拖动排序 + 二次「插入图片」）。
        left.addWidget(self.manage_button)
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
        # 单页导出 / 单页打印：与「版面编辑 / 打印效果 / 原图」**同一行、靠右**
        # （用户 2026-11-01：原来的顶部按钮行整行取消，这两颗挪到这一行）
        toggle_row.addWidget(self.export_image_button)
        toggle_row.addWidget(self.print_button)
        right.addLayout(toggle_row)
        self.caption = CaptionLabel("")
        right.addWidget(self.caption)
        # 版面编辑器：在 A4 纸上拖拽/缩放图片（默认模式）
        self.canvas = PrintLayoutCanvas()
        self.canvas.rect_changed.connect(self._on_canvas_rect)
        # 双击画布 → 预览弹窗（版面编辑模式下看该页的打印效果放大；
        # 打印效果/原图模式的双击在 self.view 上，见 _init_zoom_popup）
        self.canvas.double_clicked.connect(self._open_zoom_popup)
        # 右键画布 → 同一套「预览图片 / 编辑图片」菜单（版面编辑是第四步默认
        # 视图，用户最自然的右键位置就是这里）
        self.canvas.context_menu_requested.connect(self._open_zoom_menu)
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
    def _build_action_buttons(self) -> None:
        """建预览区的动作按钮；**摆放位置**由 ``__init__`` 决定。

        ⚠️ 顶部原来有一整行按钮（删除选中 / 下载本页图片 / 打印本页 / 下载 PDF），
        用户 2026-11-01 要求整行取消：删除选中进窗口顶部菜单栏（见
        ``desktop/ui/menu.py``），下载本页图片/打印本页挪到「版面编辑」那一行
        右侧，下载 PDF 挪到右下方控制面板「生成PDF」的下一行（宿主负责）。
        """
        self.manage_button = PrimaryPushButton(FIF.PHOTO, "管理图片")
        self.manage_button.setToolTip(
            "打开「管理图片」弹窗：拖动调整顺序、多选，或插入 / 恢复图片"
        )
        self.manage_button.clicked.connect(self.manage_requested.emit)
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
        # 初建时列表为空 → 先禁用（不能只等 set_entries，它会早退）
        self._sync_export_button()


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
            # ⚠️ 空清单必须把「版面编辑」画布一起收起来（审计 M4）：否则上一份
            #    清单的纸面+图片框还挂在界面上**可拖动**，layout_changed 会照常
            #    触发宿主落盘标脏——用户对着一个空列表"编辑"不存在的页。
            self.canvas.hide()
            self._canvas_index = -1
            self.view.show()
            self.view.clear_image(self._empty_hint)
            self.caption.setText("")
            return
        for index, entry in enumerate(entries):
            # 缩略图下方的文字是**页码**（当前行号），不是源文件名：页码只在
            # 列表顺序里成立，见 PrintThumbsMixin._page_label
            self.strip.add_page_item(self._page_label(index), str(entry["file"]))
            self.strip.item(index).setData(Qt.ItemDataRole.UserRole + 1, index)
        self._load_page_thumbs()
        self._select_entry(0)


    def entries(self) -> list[dict]:
        """当前视觉顺序的富条目列表。"""
        return list(self._entries_cache)


    def count(self) -> int:
        """列表当前条目数。"""
        return len(self._entries_cache)


    def set_pdf_path(self, path: str | Path | None) -> None:
        """记录已生成 PDF 的路径；宿主据此显示/隐藏右下方控制面板的下载按钮。"""
        p = Path(path) if path else None
        self._pdf_path = p if (p and p.exists()) else None
        self.pdf_state_changed.emit(self._pdf_path is not None)


    def remove_selected(self) -> None:
        """删除所有选中条目，未选中则通过 hint 信号提示。"""
        rows = self._selected_rows()
        if not rows:
            self.hint.emit("请先在左侧缩略图条选中要删除的图片。")
            return
        for row in rows:
            self.strip.takeItem(row)
        self._sync_cache_order()
        self._sync_export_button()
        self._emit_order_changed()
        self._load_display()

    def _selected_rows(self) -> list[int]:
        """选中的行号（**从大到小**：先删大行号，前面的行号才不会错位）。"""
        return sorted(
            {self.strip.row(item) for item in self.strip.selectedItems()},
            reverse=True,
        )

    def _remove_current_with_confirm(self) -> None:
        """右键「删除当前图片」：先确认再删。

        删除是**软删除**（文件仍在任务目录、「插入图片 → 删除恢复」可以放回），
        但缩略图一删就从列表里消失，误点一下也够吓人——弹窗里说明"能恢复"
        再动手。未选中时仍按 ``remove_selected`` 的口径提示，不弹确认。
        """
        rows = self._selected_rows()
        if not rows:
            self.remove_selected()
            return
        if not self._ask_delete_confirm(len(rows)):
            return
        self.remove_selected()

    def _delete_confirm_text(self, count: int) -> str:
        """删除确认弹窗的正文（必须告诉用户"删了还能恢复"）。"""
        what = "这张图片" if count <= 1 else f"这 {count} 张图片"
        return (
            f"确定从待打印列表删除{what}吗？\n\n"
            "删除后图片文件仍保留在任务目录里，"
            "之后可以用「管理图片 → 插入图片 → 删除恢复」重新放回列表。"
        )

    def _ask_delete_confirm(self, count: int) -> bool:
        """弹删除确认框；``False`` = 用户取消。

        ⚠️ 弹窗与动作分开一层：离屏自测绝不真弹模态，替换本方法即可验
        「取消不删 / 确认才删」两条分支。
        """
        dialog = MessageBox(
            "删除当前图片", self._delete_confirm_text(count), self.window()
        )
        dialog.yesButton.setText("删除")
        dialog.cancelButton.setText("取消")
        return bool(dialog.exec())

    def print_current(self) -> None:
        """公开入口：把当前页按 A4 效果送打印机（窗口菜单「打印图片」用）。

        与控件自己的「打印本页」按钮同一条实现（``_print_current``）；按钮
        只管显隐/启用，动作本身不复制一份。
        """
        self._print_current()


    def _show_context_menu(self, pos) -> None:
        """缩略图右键菜单：上移 / 下移 / 删除当前图片 / 向前插入 / 向后插入。

        ⚠️ 先右键命中的条目设成当前行：用户点的是「这一张」，菜单动作
        （上移/下移/删除/插入落点）必须作用在同一张上，不能沿用上一次的选中行。
        """
        item = self.strip.itemAt(pos)
        row = self.strip.row(item) if item is not None else -1
        if row >= 0:
            self.strip.setCurrentRow(row)
        if not self._entries_cache:
            return
        from qfluentwidgets import Action, FluentIcon as FIF, RoundMenu

        # ⚠️ 菜单的父对象必须是**顶层窗口**（``self.window()``），不能用 ``self``：
        #    qfluentwidgets 的 ``exec`` 只是非阻塞 ``show()``，Qt 会沿父链回溯
        #    找 popup 的原生父窗口；父对象是页面里的嵌套控件时，回溯到的窗口
        #    不是 top-level，控制台就会刷
        #    ``QWidgetWindow(...) must be a top level window.``（用户 2026-11-01）。
        #    上一份菜单也主动销毁：非阻塞 exec 不回收，右键一次就残留一个窗口。
        previous = self._context_menu
        if previous is not None:
            previous.deleteLater()
        menu = RoundMenu(parent=self.window())
        self._context_menu = menu
        # 上移/下移（用户 2026-11-01 追加）：首/末行置灰，避免点了"没反应"。
        # 走 ``strip.move_row``——它同时作废滚轮前缀和并让当前行跟到新位置，
        # 顺序变化照常经 order_changed 落盘（与拖动排序同一条链路）。
        count = self.strip.count()
        for text, icon, delta, enabled in (
            ("上移", FIF.CARE_UP_SOLID, -1, row > 0),
            ("下移", FIF.CARE_DOWN_SOLID, +1, 0 <= row < count - 1),
        ):
            action = Action(icon, text, menu)
            action.setEnabled(enabled)
            action.triggered.connect(
                lambda _checked=False, d=delta: self.strip.move_row(
                    self.strip.currentRow(), d
                )
            )
            menu.addAction(action)
        menu.addSeparator()
        for text, icon, slot in (
            # 删除走确认（用户 2026-11-01）：误点一下就把页删没了，弹窗说清
            # 「还能在插入图片里恢复」再动手；插入两项本身是弹窗，无需再确认
            ("删除当前图片", FIF.DELETE, self._remove_current_with_confirm),
            ("向前插入图片", FIF.UP,
             lambda: self.insert_before_requested.emit()),
            ("向后插入图片", FIF.DOWN,
             lambda: self.insert_after_requested.emit()),
        ):
            action = Action(icon, text, menu)
            action.triggered.connect(slot)
            menu.addAction(action)
        menu.exec(self.strip.viewport().mapToGlobal(pos))


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


    def _on_zoom_image_saved(self, path_text: str, image=None) -> None:
        """弹窗/右键里覆盖了待打印图：重画当前显示（缩略图缓存按 mtime 自愈）。

        打印列表的缩略图命中判据是「thumb mtime ≥ 源图 mtime」，覆盖后
        源图变新，旧缓存自动失效回退真图解码，无需在这里重建整列图标。
        另发 ``image_saved`` 让宿主记日志（待打印图就是最终进 PDF 的那张）。
        """
        if self._current_index() >= 0 and self._entries_cache:
            entry = self._entries_cache[self._current_index()]
            if entry.get("file") == path_text:
                self.refresh_display()
        self.image_saved.emit(path_text, image)


    # -------------------------------------------------------------- 内部
    def _stop_worker(self) -> None:
        for thread in getattr(self, "_threads", []):
            thread.quit()


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
                # 原图模式显示的就是这个文件的全部像素：编辑器「完成」可覆盖它
                save_path=path,
                # 编辑目标 = 待打印的这张图（第三步提交产物/拼版成品），
                # 也就是最终进 PDF 的那张——改了它点「生成PDF」即生效
                edit_path=path,
            )
        spec, note = self._print_spec(index, path)
        if spec is None:
            # 参数不合法时主预览也退回原图，弹窗保持一致（不另造一套逻辑）
            return ZoomTarget(
                render=lambda edge: PreviewWorker(path, longest_edge=edge),
                note=f"原图（{note}） · 第 {index + 1}/{count} 页",
                stem=path.stem,
                count=count,
                # 打印效果不可算时显示的是原图：同样按真实文件回写
                edit_path=path,
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
            # 打印效果是**派生显示**（A4 重排），不是这个文件的全部像素，
            # 故不给 save_path；但编辑改的仍是它派生的真实文件（用户原则：
            # 编辑串起各步、最终落到 PDF），「完成」后重新排版当前页。
            edit_path=path,
        )
