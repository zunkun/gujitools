# -*- coding: utf-8 -*-
"""模块一「选择拼版」的**页序/删页**分片：切页、批量删除、排序、插入、释放、清空。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from desktop.pages.taskdetail.imposition_pages.helpers import _chosen_items
from desktop.services.imposition import page_source_stems

if TYPE_CHECKING:
    from desktop.pages.taskdetail.imposition_pages._host import (
        ImpositionPagesHost,
    )
else:
    ImpositionPagesHost = object


class PageOpsMixin(ImpositionPagesHost):
    """切页、页序调整、删页/释放与清空。"""

    # ------------------------------------------------------------- 切页
    def _on_imposition_page_selected(self, index: int) -> None:
        """左列切到某一页（视图自己已切好画布，这里只更新状态行）。"""
        self._update_imposition_status(index)

    # ------------------------------------------------------------- 删页/页序
    def _on_imposition_batch_delete(self) -> None:
        """左列勾选多页后点悬浮框「批量删除」——**先弹窗确认**再删。

        语义与单页删除一致：版面调整丢失、图片释放回未选择列表。落盘后
        ``_save_imposition_pages`` 重建清单，勾选集合随页消失自动清空；
        当前页被删时落到「第一个被删页」左移后的位置（被删光了则钳到尾页）。
        """
        view = getattr(self, "imposition_view", None)
        if view is None:
            return
        pages = self._imposition_pages()
        indexes = [i for i in view.checked_pages() if 0 <= i < len(pages)]
        if not indexes:
            self._toast("info", "没有勾选", "先在左列勾选要删除的拼版页。")
            return
        # 确认弹窗（用户 2026-09-30 口径）：宽度固定、正文折行，正文下方
        # 逐页列出被勾选的页（「第一页：图名 · 图名」），页数多时列表
        # 内部滚动、弹窗高度封顶——见 BatchDeleteConfirmDialog。
        from desktop.components.imposition.confirm_delete import (
            BatchDeleteConfirmDialog,
        )

        dialog = BatchDeleteConfirmDialog(
            [(i, pages[i]) for i in indexes], self.window(),
        )
        if not dialog.exec():
            return
        current = view.current_index()
        drop = set(indexes)
        self._save_imposition_pages(
            [p for i, p in enumerate(pages) if i not in drop]
        )
        if current in drop:
            anchor = min(indexes)
            new_current = anchor - sum(1 for i in indexes if i < anchor)
        else:
            new_current = current - sum(1 for i in indexes if i < current)
        new_current = min(new_current, len(pages) - len(drop) - 1)
        view.set_current(new_current)
        self._update_imposition_status(view.current_index())
        # ⚠️ 页码清单必须先拼出来再用：此前这里直接引用 `{listing}` 而未定义
        #    ——批量删除**必定**在这条日志上抛 NameError（页已删、异常逃出，
        #    用户见不到任何提示；自测只验了信号发射，没跑过真正的处理器）。
        listing = "、".join(str(i + 1) for i in indexes)
        self.log_view.append(
            f"已批量删除 {len(indexes)} 页拼版（第 {listing} 页），"
            "图片已释放回未选择列表。"
        )

    def _on_imposition_page_reorder(self, source: int, target: int) -> None:
        """左列拖动排序松手：把第 ``source`` 页移到 ``target``（移除后口径）。

        ``_save_imposition_pages`` 会重建左列清单——页码标签「第几页」随新
        顺序重新生成，画布跟着落到拖动后的那一页。
        """
        pages = self._imposition_pages()
        if not (0 <= source < len(pages)):
            return
        page = pages.pop(source)
        target = max(0, min(target, len(pages)))
        pages.insert(target, page)
        self._save_imposition_pages(pages)
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.set_current(target)
        self._update_imposition_status(target)

    def _on_imposition_page_move(self, index: int, delta: int) -> None:
        """左列右键「上移 / 下移」：把第 ``index`` 页挪一位（``delta`` = ±1）。

        与拖动排序（:meth:`_on_imposition_page_reorder`）落到同一份文档：都是
        "先改顺序再 ``_save_imposition_pages``"。``✕``/批量删除不同——那两个
        会**释放图片**回候选池，挪位只是换顺序，图片引用一个不动。

        越界不动（首行上移 / 末行下移）：右键菜单里已经置灰，这里再兜一次。
        """
        pages = self._imposition_pages()
        target = index + delta
        if not (0 <= index < len(pages) and 0 <= target < len(pages)):
            return
        page = pages.pop(index)
        pages.insert(target, page)
        self._save_imposition_pages(pages)
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.set_current(target)
        self._update_imposition_status(target)

    def _on_imposition_page_insert(self, index: int, position: str) -> None:
        """左列右键「向前 / 向后插入拼版」：选图后把新页插到该页前/后。

        用户 2026-11-16：弹窗与「＋ 选择拼版」**同一个**（选择拼版 / 删除恢复
        两个页签 + 自己上传），只是多一行落点单选、并默认按右键那一项落位。
        与「＋ 选择拼版」的差别只在**插到哪儿**：那个追加到末尾，这个插中间。
        """
        if not self.task_id:
            return
        from desktop.components.imposition.picker import ImpositionPickerDialog

        doc = self._imposition_doc()
        pages = self._imposition_pages(doc)
        if not 0 <= index < len(pages):
            return
        pool = self._imposition_candidate_pool(doc)
        if not pool:
            # 一张候选都没有：仍开弹窗，用户可以直接上传自己的图（2026-11-16）
            self._toast(
                "info", "没有未使用的图片",
                "上一步还没有可用的成品图，或者所有图片都已被拼版使用；"
                "可以在弹窗里「上传图片」自己加图。",
            )
        dialog = ImpositionPickerDialog(
            pool, self.window(), mode="insert",
            thumb_provider=self._imposition_picker_thumb,
            position=position, current_row=index, total=len(pages),
        )
        if not dialog.exec():
            return
        new_pages, _batch = self._pages_from_chosen(_chosen_items(dialog))
        if not new_pages:
            self._toast(
                "error", "插入失败",
                "选中的图片无法读取尺寸，请换一张或换两张。",
            )
            return
        before = dialog.position() == "before"
        at = index if before else index + 1
        from desktop.services.imposition_insert import insert_pages_at

        merged = insert_pages_at(pages, new_pages, at)
        self._save_imposition_pages(merged)
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.set_current(at)
        self._update_imposition_status(at)
        listing = "、".join(
            " · ".join(page_source_stems(page)) for page in new_pages
        )
        self.log_view.append(
            f"已在第 {index + 1} 页{'之前' if before else '之后'}插入"
            f" {len(new_pages)} 页拼版：{listing}。"
        )

    def _on_imposition_release_page(self, index: int) -> None:
        """左列某页右侧的「✕」：删掉该页，把它的两张图释放回未选择列表。

        「未选择图片列表」= 源清单减去页引用与「删除图片」黑名单
        （``remaining_files``），所以删页即释放——下次「选择拼版」这两张图
        就回来了（除非它们被用户移出了选择范围）。
        """
        pages = self._imposition_pages()
        if not 0 <= index < len(pages):
            return
        removed = pages.pop(index)
        self._save_imposition_pages(pages)
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.set_current(min(index, len(pages) - 1))
        self._update_imposition_status(
            view.current_index() if view is not None else -1
        )
        self.log_view.append(
            f"已释放第 {index + 1} 页的两张图片（"
            + "、".join(Path(i["file"]).stem for i in removed.get("items") or [])
            + "），回到未选择列表，可重新「选择拼版」。"
        )

    def _on_imposition_clear(self) -> None:
        """清空全部拼版页（选择态保留，便于重新拼）。"""
        pages = self._imposition_pages()
        if not pages:
            return
        from qfluentwidgets import Dialog

        dialog = Dialog(
            "清空拼版",
            f"将删除全部 {len(pages)} 页拼版（源图片不受影响）。\n是否继续？",
            self.window(),
        )
        dialog.yesButton.setText("清空")
        dialog.cancelButton.setText("取消")
        if not dialog.exec():
            return
        self._save_imposition_pages([])
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.set_current(-1)
        self._update_imposition_status(-1)
        self.log_view.append("已清空全部拼版页。")
