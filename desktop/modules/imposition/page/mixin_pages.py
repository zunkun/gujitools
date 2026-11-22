# -*- coding: utf-8 -*-
"""独立拼图页的页面增删/排序/插入操作（从原 ``page.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path

from desktop.services.imposition import (
    append_item_to_page,
    auto_impose_pages,
    cn_page_label,
    make_page,
    make_single_page,
    page_source_stems,
    used_source_files,
)

from .paths import _chosen_items, uploaded_page_dir


class PagesMixin:
    """「选择拼版」弹窗、自动拼版、增删/排序/插入页与清空。"""

    def _on_add_pages(self) -> None:
        """左侧虚线「＋ 选择拼版」：弹选图窗，勾选的图按规则成页。

        复用 ``ImpositionPickerDialog``（缩略图网格、自动拼版起点选择、自己
        上传图片），宿主只负责把勾选结果变成页。
        """
        if not self._sources:
            self.toast("warning", "还没有图片", "请先把图片拖到上面的输入框。")
            return
        dialog = self._picker_dialog(
            self._candidate_pool(), parent=self,
        )
        if not dialog.exec():
            return
        auto_start = dialog.auto_mode_file()
        if auto_start is not None:
            pages = auto_impose_pages(
                [str(p) for p in dialog.auto_sequence()]
            )
            self._doc["pages"] = list(self._doc.get("pages") or []) + pages
        else:
            self._append_pages_from(
                [str(p) for p in self._resolve_chosen(_chosen_items(dialog))]
            )
        self._refresh_view()
        self.status(f"当前共 {len(self._doc['pages'])} 页拼版", "info")

    def _resolve_chosen(self, items: list[dict]) -> list[Path]:
        """弹窗给的候选 → 可用文件路径（上传的图先复制进 singletask 缓存区）。"""
        from desktop.services.imposition_insert import resolve_chosen

        files, errors = resolve_chosen(items, uploaded_page_dir())
        for message in errors:
            self.log(f"插入图片：{message}")
        return files

    def _candidate_pool(self) -> list:
        """弹窗的**候选列表**：源清单里没用过的图 + 这个独立任务上传过、现在
        没被页引用的图（用户 2026-11-16：删掉拼版页后，自己上传的图要回到列表）。

        顺序：源清单在前、上传的按自然页序在后。
        """
        from desktop.services.imposition_insert import uploaded_candidates

        used = used_source_files(self._doc)
        sources = [p for p in self._sources if str(p) not in used]
        seen = {str(path) for path in sources}
        uploaded = [
            path for path in uploaded_candidates(uploaded_page_dir())
            if str(path) not in used and str(path) not in seen
        ]
        return sources + uploaded

    def _on_add_image(self) -> None:
        """单图页点「新增图片」：append 弹窗挑 1 张，并进当前这一页。

        与任务流程的 ``_on_imposition_add_image`` 同一套语义（2026-10-13
        用户：独立拼图页跟任务流程保持一致）：版面规则唯一实现在
        ``services.imposition.append_item_to_page``——原图是左半幅 → 新图
        进右槽贴右边；其余 → 新图进左槽贴左边；原图的位置/大小/旋转
        **原样保留**。候选池与「选择拼版」同一套（剩余未用，可恢复已删除）。
        """
        index = self.view.current_index()
        pages = self._doc.get("pages") or []
        if index < 0 or not (0 <= index < len(pages)):
            return
        items = pages[index].get("items") or []
        if len(items) != 1:
            return  # 按钮只在单图页出现；防御一下
        pool = self._candidate_pool()
        if not pool:
            # 一张候选都没有：仍开弹窗，用户可以直接上传自己的图（2026-11-16）
            self.toast(
                "info", "没有未使用的图片",
                "所有图片都已被拼版使用；可以在弹窗里「上传图片」自己加图。",
            )
        dialog = self._picker_dialog(pool, self, mode="append")
        if not dialog.exec():
            return
        picked = self._resolve_chosen(_chosen_items(dialog))
        if len(picked) != 1:
            return  # append 弹窗只放行 1 张；这里兜底
        merged = append_item_to_page(items, picked[0])
        if merged is None:
            self.toast(
                "error", "添加失败",
                "读不到所选图片的尺寸（文件可能已被移动或删除），请换一张。",
            )
            return
        pages[index] = {**pages[index], "items": merged}
        # 版面变了，这一页的整页手改记录作废（与拖动/删除同口径）
        self._drop_page_override(index, reason="图片已改动")
        self._refresh_view()
        self.log(
            f"已在{cn_page_label(index)}新增图片「{Path(picked[0]).stem}」"
            f"（原有「{Path(items[0]['file']).stem}」的版面保持不动）。"
        )
        self.status(f"当前共 {len(pages)} 页拼版", "info")

    def _append_pages_from(self, picked: list) -> None:
        """把勾选的图两两成页追加到文档末尾（奇数落单成单图页）。

        ⚠️ 成页规则与任务流程**共用** ``services.imposition_insert.
        pages_from_candidates``：两边各自写一份"每两张一页 + 落单单页"迟早会
        分叉（其中一边先支持了"半幅无后缀配对"之类）。
        """
        from desktop.services.imposition_insert import pages_from_candidates

        pages = self._doc.setdefault("pages", [])
        made, failed = pages_from_candidates([str(p) for p in picked])
        pages.extend(made)
        if failed:
            self.log(
                f"有 {len(failed)} 张图片读不到尺寸，未参与拼版："
                + "、".join(failed) + "。"
            )

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

    def _on_reorder(self, source: int, target: int) -> None:
        """左列拖动排序：把 ``source`` 移到 ``target``（移除后口径）。"""
        pages = self._doc.get("pages") or []
        if not (0 <= source < len(pages)) or source == target:
            return
        page = pages.pop(source)
        pages.insert(min(max(target, 0), len(pages)), page)
        self._refresh_view()

    def _on_move(self, index: int, delta: int) -> None:
        """左列右键「上移 / 下移」：第 ``index`` 页挪一位（``delta`` = ±1）。

        与拖动排序走同一条内存口径（只换顺序、不动图片引用），越界不动。
        """
        pages = self._doc.get("pages") or []
        target = index + delta
        if not (0 <= index < len(pages) and 0 <= target < len(pages)):
            return
        page = pages.pop(index)
        pages.insert(target, page)
        self._refresh_view()
        self.view.set_current(target)

    def _on_insert(self, index: int, position: str) -> None:
        """左列右键「向前 / 向后插入拼版」：选图后把新页插到该页前/后。

        弹窗与「＋ 选择拼版」同一个（选择拼版 / 删除恢复页签 + 自己上传），
        只多一行落点单选、默认按右键那一项落位。
        """
        pages = self._doc.get("pages") or []
        if not (0 <= index < len(pages)):
            return
        pool = self._candidate_pool()
        if not pool:
            # 一张候选都没有：仍开弹窗，用户可以直接上传自己的图（2026-11-16）
            self.toast(
                "info", "没有未使用的图片",
                "所有图片都已被拼版使用；可以在弹窗里「上传图片」自己加图。",
            )
        dialog = self._picker_dialog(
            pool, self, mode="insert",
            position=position, current_row=index, total=len(pages),
        )
        if not dialog.exec():
            return
        files = self._resolve_chosen(_chosen_items(dialog))
        if not files:
            return
        from desktop.services.imposition_insert import (
            insert_pages_at, pages_from_candidates,
        )

        new_pages, failed = pages_from_candidates([str(p) for p in files])
        if failed:
            self.log(
                f"有 {len(failed)} 张图片读不到尺寸，未参与拼版："
                + "、".join(failed) + "。"
            )
        if not new_pages:
            self.toast(
                "error", "插入失败", "选中的图片无法读取尺寸，请换一张或换两张。"
            )
            return
        before = dialog.position() == "before"
        at = index if before else index + 1
        self._doc["pages"] = insert_pages_at(pages, new_pages, at)
        self._refresh_view()
        self.view.set_current(at)
        listing = "、".join(
            " · ".join(page_source_stems(page)) for page in new_pages
        )
        self.log(
            f"已在第 {index + 1} 页{'之前' if before else '之后'}插入"
            f" {len(new_pages)} 页拼版：{listing}。"
        )
        self.status(f"当前共 {len(self._doc['pages'])} 页拼版", "info")

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

    def _on_delete_item(self) -> None:
        """删除选中图片（单图页删至空则整页移除，与详情页口径一致）。

        与任务流程的 ``_on_imposition_delete_item`` 对齐（2026-10-13 用户：
        独立拼图页跟任务流程保持一致）：**本页最后一张图删除前先弹确认框**
        ——整页拼版会一并移除；删剩一张时面板自动出现「新增图片」可再补。
        """
        slot = self.view.selected_slot()
        index = self.view.current_index()
        pages = self._doc.get("pages") or []
        if slot < 0 or not (0 <= index < len(pages)):
            if index >= 0:
                self.toast("info", "没有选中的图片", "先在画布里点选要删除的图片。")
            return
        self.view.flush_pending()  # 拖住/转住没松手的改动先落定再删
        items = [dict(item) for item in pages[index].get("items") or []]
        if not 0 <= slot < len(items):
            return
        removed_item = items.pop(slot)
        if not items:
            # 本页最后一张：页会跟着一起删（与详情页同款：要确认）。
            # 此刻还没动任何状态（items 是副本），取消直接返回即可。
            from qfluentwidgets import Dialog

            dialog = Dialog(
                "删除图片",
                f"「{Path(removed_item['file']).stem}」是本页最后一张图片，"
                "删除后整页拼版将一并移除。\n是否继续？",
                self.window(),
            )
            dialog.yesButton.setText("删除")
            dialog.cancelButton.setText("取消")
            if not dialog.exec():
                return
        if items:
            pages[index]["items"] = items
            self._drop_page_override(index, reason="图片已改动")
        else:
            pages.pop(index)
        self._refresh_view()
        if items:
            self.log(
                f"已删除{cn_page_label(index)}选中的图片"
                f"「{Path(removed_item['file']).stem}」，回到未选择列表。"
            )
        else:
            self.log(
                f"已删除{cn_page_label(index)}最后一张图片"
                f"「{Path(removed_item['file']).stem}」，本页没有图了，整页移除。"
            )

    def _on_clear(self) -> None:
        """清空全部页（源清单保留，可重新拼）。"""
        self._doc["pages"] = []
        self.close_zoom_dialog()
        self._refresh_view()
