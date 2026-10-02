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

from pathlib import Path

from PySide6.QtWidgets import QFileDialog
from qfluentwidgets import FluentIcon as FIF, PrimaryPushButton, PushButton

from desktop.components.imposition import (
    ImpositionPanel,
    ImpositionPickerDialog,
    ImpositionViewWidget,
)
from desktop.modules.base import ModulePage
from desktop.services.imposition import (
    auto_impose_pages,
    cn_page_label,
    compose_doc,
    make_page,
    make_single_page,
    normalize_doc,
    page_source_stems,
    removed_source_files,
)
from desktop.steps import SourceZone, StepKernel, StepRequest, callable_job, spec_by_key
from desktop.ui.widgets import Card

#: 本页的步骤元数据（标题/副标题/过滤串的唯一来源）
_SPEC = spec_by_key("imposition")


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
        return self.view

    # ------------------------------------------------------------------ 控制
    def _build_control(self) -> Card:
        """右栏：自动拼版/导出按钮 + 复用 ``ImpositionPanel``（选图在页头输入区）。"""
        card = Card()

        # 导出走共用执行内核：拼版是纯函数，所以用 CallableJob
        self.kernel = StepKernel(callable_job(self._compose_job), self)
        self.kernel.log.connect(self.log)
        self.kernel.finished.connect(self._on_exported)
        self.kernel.failed.connect(self._on_export_failed)

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
        first = Path(self._sources[0])
        self._out_dir = _SPEC.default_output(first)
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
        """清空输入：源清单、拼版文档、输出目录一起复位。"""
        self._sources = []
        self._doc = normalize_doc({})
        self._out_dir = None
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
        """画布改了当前页版面：写回文档（内存态）。"""
        pages = self._doc.get("pages") or []
        if 0 <= index < len(pages):
            pages[index]["items"] = list(items)

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
        else:
            pages.pop(index)
        self._refresh_view()

    def _on_clear(self) -> None:
        """清空全部页（源清单保留，可重新拼）。"""
        self._doc["pages"] = []
        self._refresh_view()

    # ------------------------------------------------------------------ 导出
    def _compose_job(self, request: StepRequest, _report) -> str | None:
        """执行内核的 job：把整份文档合成为图片（纯函数，线程里安全）。

        ⚠️ 写成 job 而不是页面方法，是为了让"跑什么"与"怎么跑/怎么汇报"
        分开——内核负责后者（线程 + 信号），本页只管前者。
        """
        written = compose_doc(request.args["doc"], Path(request.dest))
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
        self.status("正在导出…", "info")
        self.log(f"开始导出 {len(pages)} 页 → {out_dir}")
        self._export_result = {}
        request = StepRequest(dest=out_dir, args={"doc": dict(self._doc)})
        if not self.kernel.run(request):
            self.export_button.setEnabled(True)
            self.status("正在导出", "warning")

    def _on_exported(self, out_dir: str) -> None:
        """导出成功：恢复按钮并提示。"""
        count = int(self._export_result.get("count", 0))
        self.export_button.setEnabled(True)
        self.status(f"导出完成：{out_dir}（{count} 页）", "success")
        self.log(f"导出完成：{count} 页 → {out_dir}")
        self.toast("success", "导出完成", f"共导出 {count} 页到：\n{out_dir}")

    def _on_export_failed(self, message: str) -> None:
        """导出失败：恢复按钮并提示。"""
        self.export_button.setEnabled(True)
        self.status("导出失败", "error")
        self.log(f"导出失败：{message}")
        self.toast("error", "导出失败", message)

    # ------------------------------------------------------------------ 刷新
    def _refresh_view(self) -> None:
        """把当前文档灌进拼版视图（页清单 + 画布），并同步面板状态。"""
        pages = self._doc.get("pages") or []
        current = min(self.view.current_index(), len(pages) - 1)
        self.view.set_pages(pages, current=current if current >= 0 else -1)
        self._refresh_panel()
        self.export_button.setEnabled(bool(pages))

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
