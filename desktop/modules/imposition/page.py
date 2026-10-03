# -*- coding: utf-8 -*-
"""「拼图」独立模块页（= 图片拼版）。

**复用共用组件**：

- 输入：:class:`~desktop.steps.source_zone.SourceZone`——页头下方横跨整幅的
  **大输入区**（拖一批图片、拖一个图片文件夹、或点选），与"图片提取 / 去底色"
  是同一块控件；
- 执行：:class:`~desktop.steps.kernel.StepKernel` + ``CallableJob``——
  拼版不是 CLI 命令，所以走"纯函数 job"这条路（内核同样只认"输出目录"）；
- 界面：``ImpositionViewWidget``（左页清单 + 右拖拽画布）、
  ``ImpositionPanel``（右侧控制面板）、``ImpositionPickerDialog``（选图弹窗）；
- 规则：``desktop.services.imposition`` 是**纯函数模块**（无 Qt），版面默认
  摆放、自动拼版、合成紧裁全部直接用；
- 元数据：``desktop/steps/spec.py`` 的 imposition 条目（标题/副标题/过滤串/
  后缀/输出名）。

**独立**：不依赖任务目录、不依赖 ``TaskDetailPage`` 的拼版控制器。用户选了
一批图片作为「源清单」，模块自己维护一份 ``doc``（内存 + 可导出），
点「导出成品」把每页合成为 PNG。

⚠️ 与任务流程的差别（有意为之）：任务流程里拼版的产物供第四步生成 PDF，
且「启用开关」决定取图来源；单文件模式下没有下游，所以这里把面板里的
「启用开关」隐掉，只留版面操作与导出。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog
from qfluentwidgets import FluentIcon as FIF, PrimaryPushButton, PushButton

from desktop.components.imposition import (
    ImpositionPanel,
    ImpositionPickerDialog,
    ImpositionViewWidget,
)
from desktop.components.progress_row import ProgressRow
from desktop.modules.base import ModulePage
from desktop.services.imposition import (
    FILE_FMT,
    auto_impose_pages,
    cn_page_label,
    compose_doc,
    make_page,
    make_single_page,
    normalize_doc,
    normalize_page,
    page_source_stems,
    removed_source_files,
)
from desktop.steps import SourceZone, StepKernel, StepRequest, callable_job, spec_by_key
from desktop.ui.widgets import Card
from desktop.utils.files import THUMBNAIL_EDGE as THUMB_EDGE

#: 本页的步骤元数据（标题/副标题/过滤串的唯一来源）
_SPEC = spec_by_key("imposition")

#: 手工修饰过的整页组合落在 ``singletask/<子任务>/`` 下的哪个子目录。
EDITED_DIRNAME = "edited"


def edited_page_dir() -> Path:
    """手工修饰过的整页组合的存放目录（**缓存**，不是产物）。

    「编辑整页组合」在独立拼图页里没有现成的落点：成品是点「导出成品」那一刻
    才写进用户选的目录的。所以手改的那张先存在 singletask 下（用户 2026-10-03
    定的独立任务缓存区），导出时再盖到对应成品上——输出目录归用户，程序只往
    里写最终成品。

    ⚠️ 目录名走 ``spec.disk_key()``（= ``imposition``）而不是标题：这里存着
    用户手改过的版面图，标题一改就再也读不到（"明明改过版面，重新打开又变回
    原样"）。见 :meth:`desktop.steps.spec.StepSpec.disk_key`。
    """
    from desktop.utils.files import singletask_dir

    return singletask_dir(_SPEC.disk_key()) / EDITED_DIRNAME


def _page_overrides(doc: dict) -> list[Path | None]:
    """按 ``compose_doc`` 的页序取出每页的手改图；没手改过的页是 ``None``。

    ⚠️ 过滤口径必须与 ``compose_doc`` **完全一致**（同样走 ``normalize_page``）：
    那边会静默丢掉不可修复的页，这里若按原列表下标取，一页坏数据就会让后面
    所有页的手改**错位到别人身上**。
    """
    overrides: list[Path | None] = []
    for raw in (doc or {}).get("pages") or []:
        if normalize_page(raw) is None:
            continue
        edited = raw.get("edited_file") if isinstance(raw, dict) else None
        overrides.append(Path(str(edited)) if edited else None)
    return overrides


class ImpositionModulePage(ModulePage):
    """拼图模块页：选图 → 自动/手动拼版 → 调整版面 → 导出成品。"""

    TITLE = _SPEC.title
    SUBTITLE = _SPEC.subtitle

    #: 拼版视图 + 控制面板需要更宽的控制列（沿用详情页拼版档位）
    CONTROL_MIN_WIDTH = 340
    CONTROL_MAX_WIDTH = 460

    def __init__(self, parent=None):
        """先建骨架，再补「选图 / 自动拼版 / 导出」这条操作链。"""
        self._sources: list[str] = []
        self._doc: dict = normalize_doc({})
        self._out_dir: Path | None = None
        #: 最近一次导出的页数（job 在 worker 线程里写、主线程读，只搬一个整数）
        self._export_result: dict = {}
        #: 左列每页的缩略图（QPixmap 列表，页序；未就绪处是 None）
        self._page_thumbs: list = []
        #: 已渲好的**源图**缩略图：源图路径 → QPixmap（跨页复用：同一张图
        #: 可能在两页里都出现，重复解码就是白花 CPU）
        self._source_thumbs: dict[str, object] = {}
        #: 预览弹窗（懒建，与任务流程的拼版步骤同一个控件）
        self._zoom_dialog = None
        super().__init__(parent)
        self.status("尚未选择图片")

    # ------------------------------------------------------------------ 输入
    def _build_input(self) -> SourceZone:
        """页头下方的**大输入区**：拖一批图片 / 拖一个图片文件夹 / 点选。

        ⚠️ 拼图的"源"是**一批**图片（不是单个源），所以这里不关心
        :meth:`StepSpec.resolve_source` 的单源归一化，而是把拖进来的东西
        **展开成图片清单**（文件夹取顶层图片），见 :meth:`_on_paths_chosen`。
        """
        self.zone = SourceZone(_SPEC)
        self.zone.paths_chosen.connect(self._on_paths_chosen)
        self.zone.cleared.connect(self._on_clear_sources)
        self.zone.rejected.connect(
            lambda message: self.toast("warning", "这个用不上", message)
        )
        return self.zone

    # ------------------------------------------------------------------ 预览
    def _build_preview(self) -> ImpositionViewWidget:
        """左栏：拼版页清单 + 操作画布（复用现成装配控件）。"""
        self.view = ImpositionViewWidget()
        self.view.add_requested.connect(self._on_add_pages)
        self.view.page_remove_requested.connect(self._on_release_page)
        self.view.page_selected.connect(lambda _i: self._refresh_panel())
        self.view.items_changed.connect(self._on_items_changed)
        self.view.page_reorder_requested.connect(self._on_reorder)
        self.view.pages_batch_delete_requested.connect(self._on_batch_delete)
        # 双击 / 右键：预览（单张原图 · 整页左右组合）与「编辑图片」直达编辑器。
        # 与任务流程的拼版步骤**同一组信号、同一套语义**——此前这四条没接线，
        # 画布右键菜单弹得出来、双击也有反应信号，但**点了什么都不会发生**
        # （用户 2026-10-03：「独立步骤，图片也可以编辑生效」）。
        self.view.item_preview_requested.connect(self._open_item_preview)
        self.view.spread_preview_requested.connect(self._open_spread_preview)
        self.view.item_edit_requested.connect(self._open_item_edit)
        self.view.spread_edit_requested.connect(self._open_spread_edit)
        return self.view

    # ------------------------------------------------------------------ 控制
    def _build_control(self) -> Card:
        """右栏：自动拼版/导出按钮 + 复用 ``ImpositionPanel``（选图在页头输入区）。"""
        card = Card()

        # 导出走共用执行内核：拼版是纯函数，所以用 CallableJob
        self.kernel = StepKernel(callable_job(self._compose_job), self)
        self.kernel.log.connect(self.log)
        self.kernel.progress.connect(self._on_progress)
        self.kernel.finished.connect(self._on_exported)
        self.kernel.failed.connect(self._on_export_failed)

        # 执行进度：与四个步骤页**同一个**组件（``StepControl`` 内部那条也是
        # 它），所以拼图页的进度条长得跟别处一模一样。
        # ⚠️ 本页**不继承** ``StepModulePage``（源是一批图、执行是纯函数导出），
        # 所以这条得自己摆、自己接——别以为基类会捎带带上。
        self.progress_row = ProgressRow(noun=_SPEC.progress_unit())
        card.box.addWidget(self.progress_row)

        self.auto_button = PushButton(FIF.MOVE, "自动拼版")
        self.auto_button.setFixedHeight(34)
        self.auto_button.setToolTip(
            "按文件名规则自动配对：前一页左半幅 + 当前页右半幅拼成对页"
        )
        self.auto_button.clicked.connect(self._auto_impose)
        card.box.addWidget(self.auto_button)

        self.panel = ImpositionPanel()
        # 单文件模式下没有「第四步取图来源」这个概念，隐掉启用开关
        self._hide_enable_switch(self.panel)
        self.panel.reset_requested.connect(self._on_reset_layout)
        self.panel.item_rotation_edited.connect(self._on_item_rotate)
        self.panel.item_delete_requested.connect(self._on_delete_item)
        self.panel.clear_requested.connect(self._on_clear)
        card.box.addWidget(self.panel)

        self.export_button = PrimaryPushButton(FIF.SAVE, "导出成品")
        self.export_button.setFixedHeight(36)
        self.export_button.clicked.connect(self._export)
        card.box.addWidget(self.export_button)
        return card

    @staticmethod
    def _hide_enable_switch(panel: ImpositionPanel) -> None:
        """把「启用图片拼版」开关藏掉（单文件模式没有下游流程）。

        用 ``setVisible(False)`` 而不是删控件：面板的其余接线（状态行、
        旋转、复位）都还在，藏一个控件最省事也最不易漏。
        """
        for attr in ("enabled_checkbox",):
            widget = getattr(panel, attr, None)
            if widget is not None:
                widget.setVisible(False)
                widget.setChecked(True)  # 让面板内部按"已启用"渲染状态

    # ------------------------------------------------------------------ 选图
    def _on_paths_chosen(self, paths: list) -> None:
        """大输入区给了路径：展开成**图片清单**（文件夹取图片，含唯一子目录下钻）。

        与"图片提取 / 去底色"的差别在这里：那两步最终只要**一个**源（文件或
        目录），拼图要的是**一批**图片，所以走 :meth:`StepSpec.collect_files`
        （摊平成清单、去重、按名字排序），而不是 :meth:`StepSpec.resolve_source`。
        """
        images = _SPEC.collect_files(paths)
        if not images:
            self.toast(
                "warning", "没有可用的图片",
                "请拖入图片文件，或拖一个放着图片的文件夹。",
            )
            return
        self._set_sources(images)

    def _set_sources(self, images: list[Path]) -> None:
        """把图片清单定为本页的源：复位文档与输出目录，并刷新视图。

        文档一律重置——换了源清单还留着上一批图的拼版页，导出时会去合并不存在
        的文件（或者更糟：把两批图混在一份成品里）。
        """
        self._sources = [str(p) for p in images]
        self._doc = normalize_doc({})
        self.close_zoom_dialog()  # 弹窗里那几页是上一批图的快照
        first = Path(self._sources[0])
        self._out_dir = _SPEC.default_output(first)
        # 选到图了 → 显出拼版视图与控制面板（初始只有输入框，见
        # ModulePage 类 docstring）
        self.sync_workspace_visible(first)
        if len(self._sources) == 1:
            self.zone.set_source(first, f"1 张图片 · {first.parent}")
            summary = f"已选 1 张图片 → {self._out_dir}"
        else:
            common = first.parent
            self.zone.set_source(
                common, f"共 {len(self._sources)} 张图片 · {common}"
            )
            summary = f"已选 {len(self._sources)} 张图片 → {self._out_dir}"
        self.header.set_subtitle(summary)
        self.status("已选好图片，点「自动拼版」或左侧「＋ 选择拼版」", "info")
        self._refresh_view()
        self.log(f"已选择 {len(self._sources)} 张图片")

    def _on_clear_sources(self) -> None:
        """清空输入：源清单、拼版文档、输出目录一起复位。

        操作界面也一起收回去——源没了就没有可拼的图，只留输入框（用户
        2026-10-03：初始/清空后页面上只有输入框）。
        """
        self._sources = []
        self._doc = normalize_doc({})
        self._out_dir = None
        self._page_thumbs = []
        self._source_thumbs.clear()
        self.close_zoom_dialog()
        self.sync_workspace_visible(None)
        self.header.set_subtitle("")
        self.status("已清空输入", "info")
        self._refresh_view()

    def _on_add_pages(self) -> None:
        """左侧虚线「＋ 选择拼版」：弹选图窗，勾选的图按规则成页。

        复用 ``ImpositionPickerDialog``（自带缩略图网格、删除/恢复、自动拼版
        起点选择），宿主只负责把勾选结果变成页。
        """
        if not self._sources:
            self.toast("warning", "还没有图片", "请先把图片拖到上面的输入框。")
            return
        candidates = self._sources + list(removed_source_files(self._doc))
        dialog = ImpositionPickerDialog(
            candidates,
            parent=self,
            removed_files=list(removed_source_files(self._doc)),
        )
        if not dialog.exec():
            # 取消也要落软删除黑名单（用户在弹窗里删过图）
            if dialog.removed_changed():
                self._doc["removed"] = [str(p) for p in dialog.removed_files()]
                self._refresh_view()
            return
        picked = [str(p) for p in dialog.checked_files()]
        self._doc["removed"] = [str(p) for p in dialog.removed_files()]
        auto_start = dialog.auto_mode_file()
        if auto_start is not None:
            pages = auto_impose_pages(
                [str(p) for p in dialog.auto_sequence()]
            )
            self._doc["pages"] = list(self._doc.get("pages") or []) + pages
        else:
            self._append_pages_from(picked)
        self._refresh_view()
        self.status(f"当前共 {len(self._doc['pages'])} 页拼版", "info")

    def _append_pages_from(self, picked: list[str]) -> None:
        """把勾选的图两两成页追加到文档末尾（奇数落单成单图页）。"""
        pages = self._doc.setdefault("pages", [])
        index = 0
        while index + 1 < len(picked):
            page = make_page(picked[index:index + 2])
            if page is not None:
                pages.append(page)
            index += 2
        if index < len(picked):
            page = make_single_page(picked[index])
            if page is not None:
                pages.append(page)

    def _auto_impose(self) -> None:
        """整份源清单按 ``auto_impose_pages`` 规则自动拼版（覆盖现有页）。"""
        if not self._sources:
            self.toast("warning", "还没有图片", "请先把图片拖到上面的输入框。")
            return
        pages = auto_impose_pages(self._sources)
        if not pages:
            self.toast("warning", "无法自动拼版", "图片尺寸读取失败，或清单为空。")
            return
        self._doc["pages"] = pages
        self._refresh_view()
        self.status(f"自动拼版完成，共 {len(pages)} 页", "success")
        self.log(f"自动拼版：{len(self._sources)} 张 → {len(pages)} 页")

    # ------------------------------------------------------------------ 版面
    def _on_items_changed(self, index: int, items: list) -> None:
        """画布改了当前页版面：写回文档（内存态）。

        ⚠️ 顺带**作废这一页的手改记录**（``edited_file``）：版面一变，导出时
        会按新版面重新合成，手改的那张图已经不代表这一页了。
        """
        pages = self._doc.get("pages") or []
        if 0 <= index < len(pages):
            pages[index]["items"] = list(items)
            self._drop_page_override(index)

    def _drop_page_override(self, index: int, reason: str = "版面已改动") -> None:
        """丢掉第 ``index`` 页的整页手改记录（有的话写一句日志）。"""
        pages = self._doc.get("pages") or []
        if not (0 <= index < len(pages)):
            return
        if pages[index].pop("edited_file", None) is not None:
            self.log(
                f"{cn_page_label(index)}{reason}，之前对整页组合的手工修饰作废；"
                "导出时按当前版面重新合成。"
            )

    def _on_reorder(self, source: int, target: int) -> None:
        """左列拖动排序：把 ``source`` 移到 ``target``（移除后口径）。"""
        pages = self._doc.get("pages") or []
        if not (0 <= source < len(pages)) or source == target:
            return
        page = pages.pop(source)
        pages.insert(min(max(target, 0), len(pages)), page)
        self._refresh_view()

    def _on_release_page(self, index: int) -> None:
        """左列「✕」：把这一页的源图移回候选池（页删除，文件不动）。"""
        pages = self._doc.get("pages") or []
        if not (0 <= index < len(pages)):
            return
        pages.pop(index)
        self._refresh_view()

    def _on_batch_delete(self) -> None:
        """左列勾选多页后批量删除。"""
        pages = self._doc.get("pages") or []
        for index in sorted(self.view.checked_pages(), reverse=True):
            if 0 <= index < len(pages):
                pages.pop(index)
        self._refresh_view()

    def _on_reset_layout(self) -> None:
        """「复位本页版面」：按当前页的源图重新生成默认并排。"""
        index = self.view.current_index()
        pages = self._doc.get("pages") or []
        if not (0 <= index < len(pages)):
            return
        files = [item["file"] for item in pages[index].get("items") or []]
        page = make_page(files) or make_single_page(files[0])
        if page is None:
            return
        # 复位 = 换掉整页内容（包括手改记录）：先按"原本有没有"记一句日志
        self._drop_page_override(index, reason="已复位为默认并排")
        pages[index] = page
        self._refresh_view()

    def _on_item_rotate(self, angle: float) -> None:
        """把选中图设为绝对旋转角（顺时针，度）。"""
        slot = self.view.selected_slot()
        if slot < 0:
            return
        items = [dict(item) for item in self.view.current_items()]
        if slot < len(items):
            items[slot]["rotation"] = float(angle)
            self.view.update_current_items(items)
            self._on_items_changed(self.view.current_index(), items)

    def _on_delete_item(self) -> None:
        """删除选中图片（单图页删至空则整页移除，与详情页口径一致）。"""
        slot = self.view.selected_slot()
        index = self.view.current_index()
        pages = self._doc.get("pages") or []
        if slot < 0 or not (0 <= index < len(pages)):
            return
        items = [dict(item) for item in self.view.current_items()]
        if slot < len(items):
            items.pop(slot)
        if items:
            pages[index]["items"] = items
            self._drop_page_override(index, reason="图片已改动")
        else:
            pages.pop(index)
        self._refresh_view()

    def _on_clear(self) -> None:
        """清空全部页（源清单保留，可重新拼）。"""
        self._doc["pages"] = []
        self.close_zoom_dialog()
        self._refresh_view()

    # -------------------------------------------------------------- 预览与编辑
    #
    # 用户 2026-10-03：「**独立步骤，图片也可以编辑生效**」。这四条此前在独立
    # 拼图页**整个没接线**——画布的右键菜单弹得出来、双击也会发信号，但点了
    # 什么都不会发生（信号发出去没人接）。语义与任务流程的拼版步骤逐条对齐：
    # 双击图上/空白 = 预览单张原图 / 整页左右组合；右键「编辑图片」= 不经预览
    # 弹窗直接进编辑器，编辑结果覆盖真实文件并在导出时生效。

    def _open_item_preview(self, slot: int) -> None:
        """画布**双击某张图**：弹窗预览这张原图（可缩放、下载）。"""
        index = self.view.current_index()
        self._open_zoom(lambda _i: self._item_target(index, slot), 0)

    def _open_spread_preview(self) -> None:
        """画布**双击两图之外的空白**：预览整页左右组合（按导出口径合成）。"""
        index = self.view.current_index()
        self._open_zoom(lambda _i: self._spread_target(index), 0)

    def _open_zoom(self, factory, index: int) -> None:
        """打开（或复用）预览弹窗；没有可预览的页时静默返回。"""
        from desktop.components.viewers.image_zoom_dialog import ImageZoomDialog

        if factory(index) is None:
            return
        if self._zoom_dialog is None:
            self._zoom_dialog = ImageZoomDialog(
                self.window() or self, factory=factory
            )
        dialog = self._zoom_dialog
        # 先 show 再 show_for：视口有了真实尺寸，渲染密度才算得准
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.show_for(factory=factory, index=index)

    def close_zoom_dialog(self) -> None:
        """关掉预览弹窗（内容失效时调：换源 / 清空）。"""
        if self._zoom_dialog is not None:
            self._zoom_dialog.close()

    def _item_target(self, page_index: int, slot: int):
        """弹窗「**单张原图**」来源：``slot`` 即弹窗页码（0 右槽 / 1 左槽）。

        ⚠️ **不给 ``edit_path``**：弹窗是只读预览，编辑走画布右键
        （:meth:`_open_item_edit`）——与任务流程的拼版步骤完全一致。若这里也
        给 ``edit_path``，弹窗里那个「编辑」按钮**只改弹窗画布副本、不落盘**
        （它没有回写目标），同一件事就出现两套语义。
        """
        from desktop.components.viewers.image_zoom_dialog import ZoomTarget
        from desktop.workers import PreviewWorker

        pages = self._doc.get("pages") or []
        if not (0 <= page_index < len(pages)):
            return None
        items = pages[page_index].get("items") or []
        if not (0 <= slot < len(items)):
            return None
        path = Path(str(items[slot].get("file") or ""))
        if not path.is_file():
            return None
        side = "右侧" if slot == 0 else "左侧"
        return ZoomTarget(
            render=lambda edge, p=path: PreviewWorker(p, longest_edge=edge),
            note=f"{cn_page_label(page_index)} · {side}「{path.name}」",
            stem=path.stem,
            count=len(items),
        )

    def _spread_target(self, page_index: int):
        """弹窗「**整页左右组合**」来源：构造时快照版面，合成在 worker 线程。"""
        from desktop.components.viewers.image_zoom_dialog import ZoomTarget
        from desktop.workers import ImpositionPagePreviewWorker

        pages = self._doc.get("pages") or []
        if not (0 <= page_index < len(pages)):
            return None
        items = [dict(item) for item in pages[page_index].get("items") or []]
        if not items:
            return None
        stems = page_source_stems(pages[page_index])
        right = stems[0] if stems else ""
        left = stems[1] if len(stems) > 1 else ""
        return ZoomTarget(
            render=lambda edge, page={"items": items}: (
                ImpositionPagePreviewWorker(page, edge)
            ),
            note=f"{cn_page_label(page_index)} 左右组合（左「{left}」+ 右「{right}」）",
            stem=f"imposition-{page_index + 1:02d}",
            count=1,
        )

    def _open_item_edit(self, slot: int) -> None:
        """画布**右键某张图 →「编辑图片」**：不经预览弹窗，直接编辑原图。

        编辑的是该槽位对应的**源图全分辨率原图**，「完成」= 原子覆盖回该文件
        （与其余独立步骤、任务流程同一套 ``overwrite_image_file``）。落盘后的
        刷新链：① 画布丢掉这张图的解码缓存并重绘；② 左列该页缩略图按新图重渲
        （源图 mtime 变新 ⇒ 缓存自动判过期重写）；③ 日志说明**什么时候生效**。
        """
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QDialog

        index = self.view.current_index()
        pages = self._doc.get("pages") or []
        if not (0 <= index < len(pages)):
            return
        items = pages[index].get("items") or []
        if not (0 <= slot < len(items)):
            return
        file_text = str(items[slot].get("file") or "")
        path = Path(file_text)
        image = QImage(file_text) if path.is_file() else QImage()
        if image.isNull():
            self.toast(
                "warning", "无法编辑",
                f"读不到原图：{path.name}（文件可能已被移动或删除）。",
            )
            return
        from desktop.components.viewers.image_editor import ImageEditorDialog
        from desktop.components.viewers.image_zoom_dialog import overwrite_image_file

        editor = ImageEditorDialog(self.window(), image, save_back=True)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        edited = editor.result_image()
        if edited is None or edited.isNull():
            return
        if not overwrite_image_file(edited, path):
            self.toast("error", "保存失败", f"编辑未生效：{path.name}")
            return
        self.view.canvas.invalidate_image(file_text)
        self._load_source_thumbs([file_text])  # 左列那条缩略图按新图重渲
        self.log(
            f"已编辑拼版源图「{path.name}」并覆盖原图"
            f"（{edited.width()}×{edited.height()} px）；"
            "点「导出成品」即用上这次修改。"
        )

    def _open_spread_edit(self) -> None:
        """画布**右键空白处 →「编辑图片」**：直接编辑整页左右组合（成品口径）。

        组合图是**虚拟图**（没有源文件），所以这里按导出口径（``compose_page``
        的紧裁合成，与落盘成品同一套代码）在 worker 线程现场合成**全分辨率**
        图交给编辑器；「完成」把结果原子覆盖到 ``singletask/拼图/edited/<页>.png``，
        导出那一刻由 :meth:`_compose_job` 盖到对应成品上。

        ⚠️ 独立页没有任务流程那种"提交进 ``stages/imposition``"的落点，所以
        手改图先存缓存区；若之后又拖这一页的版面，会重新合成、覆盖这次修饰
        （:meth:`_on_items_changed` 会清掉手改记录，日志里也写了）。
        """
        index = self.view.current_index()
        pages = self._doc.get("pages") or []
        if not (0 <= index < len(pages)):
            return
        self.view.flush_pending()  # 拖住没松手的改动先落定，快照才是最新的
        items = [dict(item) for item in self.view.current_items()]
        if not items:
            return
        from desktop.workers import ImpositionPagePreviewWorker, connect_queued

        # longest_edge=0 = 不缩：编辑器要的是全分辨率（与落盘成品同一分辨率）
        self.run_worker(
            lambda: ImpositionPagePreviewWorker({"items": items}, longest_edge=0),
            lambda worker, thread: (
                connect_queued(
                    self, worker.finished,
                    lambda _i, image, _s, t=index: self._on_spread_edit_ready(
                        t, image
                    ),
                    thread,
                ),
                connect_queued(
                    self, worker.failed,
                    lambda _i, msg: self.toast("error", "拼版合成失败", msg),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_spread_edit_ready(self, page_index: int, image) -> None:
        """组合图合成完毕（主线程）：开编辑器，「完成」存进缓存区待导出盖上。"""
        from PySide6.QtWidgets import QDialog

        if image is None or image.isNull():
            return
        pages = self._doc.get("pages") or []
        if not (0 <= page_index < len(pages)):
            return
        from desktop.components.viewers.image_editor import ImageEditorDialog
        from desktop.components.viewers.image_zoom_dialog import overwrite_image_file

        editor = ImageEditorDialog(self.window(), image, save_back=True)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        edited = editor.result_image()
        if edited is None or edited.isNull():
            return
        target = edited_page_dir() / FILE_FMT.format(page_index + 1)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not overwrite_image_file(edited, target):
            self.toast("error", "保存失败", f"编辑未生效：{target.name}")
            return
        pages[page_index]["edited_file"] = str(target)
        self.log(
            f"已编辑{cn_page_label(page_index)}的整页组合并保存"
            f"（{edited.width()}×{edited.height()} px）；"
            "点「导出成品」时这一页用编辑后的图。"
        )
        self.toast("success", "整页组合已编辑", "导出成品时这一页用编辑后的图。")

    # ------------------------------------------------------------------ 导出
    def _compose_job(self, request: StepRequest, report) -> str | None:
        """执行内核的 job：把整份文档合成为图片（纯函数，线程里安全）。

        ⚠️ 写成 job 而不是页面方法，是为了让"跑什么"与"怎么跑/怎么汇报"
        分开——内核负责后者（线程 + 信号），本页只管前者。

        **手工修饰过的整页组合优先**：右键空白处「编辑图片」改出来的那张图
        存在 ``singletask/拼图/edited/`` 里（见 :meth:`_open_spread_edit`），
        这里在整套合成之上把它按页盖回去——不盖的话，用户改完一看导出的
        成品还是老样子（这就是"编辑没生效"）。
        """
        doc = request.args["doc"]
        dest = Path(request.dest)
        # ⚠️ 页数按 **compose_doc 的过滤后口径**取（``normalize_page`` 会静默
        #    丢掉不可修复的页），否则这里算出的分母与合成循环报的分母不一致，
        #    进度条会在末页突然倒退。``_page_overrides`` 用的也是这套口径。
        pages = len(_page_overrides(doc))
        # 逐页进度：``compose_doc`` 合成一页报一次（内核转成 progress 信号）。
        # ⚠️ report 为 None 时整条链都不汇报（内核正常运行时一定非None，
        #    但 job 契约允许"只干活"——既有自测就是这么直接调本 job 的）。
        written = compose_doc(
            doc, dest,
            report=None if report is None else (
                lambda done, total: report(
                    "progress", {"done": done, "total": total}
                )
            ),
        )
        overrides = _page_overrides(doc)
        for index, source in enumerate(overrides):
            if source is None or not source.is_file():
                continue
            target = dest / FILE_FMT.format(index + 1)
            try:
                shutil.copyfile(source, target)
            except OSError:
                continue  # 盖不上就当没手改过，至少合成结果还在
            if target not in written:
                written.append(target)
        # ⚠️ 合成那 100% **不等于整轮跑完**：手改整页组合还要一页页盖回去。
        #    这里再报一轮"盖回 n/N"，否则进度条会在还有活儿的时候显示完成。
        # ⚠️ ``report`` 可能是 None——job 契约是"可只干活不汇报"（既有自测就是
        #    直接传 None 调本job 的），所以每处汇报前都要判，别假定它可用。
        edited = sum(1 for s in overrides if s is not None and s.is_file())
        if edited and report is not None:
            for index in range(edited):
                report("progress", {
                    "done": pages + index + 1,
                    "total": pages + edited,
                })
        self._export_result["count"] = len(written)
        return str(request.dest)

    def _export(self) -> None:
        """把整份文档合成为 PNG（后台线程，避免大图阻塞界面）。"""
        pages = self._doc.get("pages") or []
        if not pages:
            self.toast("warning", "没有拼版页", "请先把图片拖到上面的输入框，再拼版。")
            return
        if self.kernel.busy():
            self.toast("warning", "正在导出", "上一次导出还没结束，请稍候。")
            return
        out_dir = self._out_dir
        if out_dir is None:
            base = Path(self._sources[0]).parent if self._sources else Path.cwd()
            out_dir = base / "拼图成品"
        directory = QFileDialog.getExistingDirectory(
            self, "选择导出目录", str(out_dir)
        )
        if directory:
            out_dir = Path(directory)
        self._out_dir = out_dir

        self.export_button.setEnabled(False)
        # 先点亮进度条再起线程：极小的一批可能瞬间跑完，先亮才不会被收尾盖掉
        self.progress_row.start()
        self.status("正在导出…", "info")
        self.log(f"开始导出 {len(pages)} 页 → {out_dir}")
        self._export_result = {}
        request = StepRequest(dest=out_dir, args={"doc": dict(self._doc)})
        if not self.kernel.run(request):
            self.export_button.setEnabled(True)
            self.progress_row.reset()
            self.status("正在导出", "warning")

    def _on_progress(self, done: int, total: int) -> None:
        """一条执行进度：喂给右栏那条进度行。"""
        self.progress_row.update(done, total)

    def _on_exported(self, out_dir: str) -> None:
        """导出成功：恢复按钮、进度条走到头并提示。"""
        count = int(self._export_result.get("count", 0))
        self.export_button.setEnabled(True)
        self.progress_row.succeed(
            f"完成 {count} 页" if count else "已完成"
        )
        self.status(f"导出完成：{out_dir}（{count} 页）", "success")
        self.log(f"导出完成：{count} 页 → {out_dir}")
        self.toast("success", "导出完成", f"共导出 {count} 页到：\n{out_dir}")

    def _on_export_failed(self, message: str) -> None:
        """导出失败：恢复按钮、进度条停住并提示。"""
        self.export_button.setEnabled(True)
        self.progress_row.fail()
        self.status("导出失败", "error")
        self.log(f"导出失败：{message}")
        self.toast("error", "导出失败", message)

    # ------------------------------------------------------------------ 刷新
    def _refresh_view(self) -> None:
        """把当前文档灌进拼版视图（页清单 + 画布），并同步面板状态。"""
        pages = self._doc.get("pages") or []
        current = min(self.view.current_index(), len(pages) - 1)
        self.view.set_pages(pages, current=current if current >= 0 else -1)
        self._refresh_page_thumbs()
        self._refresh_panel()
        self.export_button.setEnabled(bool(pages))

    # -------------------------------------------------------------- 缩略图
    def _refresh_page_thumbs(self) -> None:
        """左列每页的缩略图：已缓存的直接贴，没缓存的起后台 pass 补。

        用户 2026-10-03：所有独立任务左栏都显示缩略图，且统一缓存在
        ``~/Documents/guji/singletask/拼图/``。这里**每页取第一张源图的缩略图**
        ——一页拼版本来就是「两张图并排」，给一张代表图已经能认出是哪页，
        而把两张都渲出来只为在 56px 宽的格子里并排显示并不更清楚。
        """
        pages = self._doc.get("pages") or []
        #: 每页的代表图（第一张源图）
        reps = []
        for page in pages:
            files = [item.get("file") for item in page.get("items") or []]
            reps.append(str(next((f for f in files if f), "")))
        # 已有的先贴上（换页/排序不该让已渲好的缩略图闪一下）
        thumbs = []
        for rep in reps:
            thumbs.append(self._source_thumbs.get(rep) if rep else None)
        self._page_thumbs = thumbs
        self.view.set_page_thumbs(thumbs)
        missing = [
            rep for rep in reps if rep and rep not in self._source_thumbs
        ]
        if missing:
            self._load_source_thumbs(list(dict.fromkeys(missing)))

    def _load_source_thumbs(self, images: list[str]) -> None:
        """后台把这些源图的缩略图渲进 singletask 缓存，回来后贴进左列。"""
        from desktop.utils.files import image_thumbs_dir
        from desktop.workers import ImageThumbCacheWorker, connect_queued

        # ⚠️ 目录规则与 :class:`ThumbSourceMixin` 同源
        #    （``desktop.utils.files.image_thumbs_dir``，两份都取那一个函数），
        #    但这里**不继承那个混入**——拼图页的"源"是一批图片而非单个源，
        #    且左栏是拼版页清单而不是 ImageViewerWidget，继承它只会拿到一堆
        #    用不上的方法。
        cache_dir = image_thumbs_dir(_SPEC.disk_key(), THUMB_EDGE)
        edge = THUMB_EDGE
        self.run_worker(
            lambda: ImageThumbCacheWorker(images, cache_dir, edge=edge),
            lambda worker, thread: (
                connect_queued(
                    self, worker.thumbnail_ready,
                    lambda index, image, _cached, items=list(images): (
                        self._on_source_thumb(index, image, items)
                    ),
                    thread,
                ),
                worker.completed.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_source_thumb(self, index: int, image, images: list[str]) -> None:
        """一张源图缩略图就绪：存起来并刷左列（只刷，不重建条目）。"""
        if image is None or getattr(image, "isNull", lambda: True)():
            return
        if not (0 <= index < len(images)):
            return
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return
        self._source_thumbs[images[index]] = pixmap
        self._refresh_page_thumbs()

    def _refresh_panel(self) -> None:
        """刷新右侧面板的状态文案与选中图信息（面板自绘，这里只给文案）。"""
        label = self.panel.status_label
        pages = self._doc.get("pages") or []
        index = self.view.current_index()
        if not pages or index < 0:
            label.setText("还没有拼版页")
            return
        stems = page_source_stems(pages[index])
        if len(stems) == 1:
            label.setText(f"{cn_page_label(index)}　·　整幅「{stems[0]}」")
        else:
            label.setText(
                f"{cn_page_label(index)}　·　右「{stems[0]}」　左「{stems[1]}」"
            )

    # ------------------------------------------------------------------ 收尾
    def shutdown_workers(self) -> None:
        """关闭页面前中止并等待导出线程。"""
        try:
            self.view.flush_pending()
        except RuntimeError:
            pass
        self.kernel.shutdown()
        super().shutdown_workers()


__all__ = ["ImpositionModulePage"]
