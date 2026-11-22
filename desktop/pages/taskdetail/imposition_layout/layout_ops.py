# -*- coding: utf-8 -*-
"""模块二「拼版操作」的**版面操作**分片：旋转、复位、删除选中图片。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from desktop.services.imposition import (
    cn_page_label, default_items, single_items,
)

if TYPE_CHECKING:
    from desktop.pages.taskdetail.imposition_layout._host import (
        ImpositionLayoutHost,
    )
else:
    ImpositionLayoutHost = object


class LayoutOpsMixin(ImpositionLayoutHost):
    """画布版面操作：整体/单图旋转、复位本页版面、删除选中图片。"""

    # ------------------------------------------------------------- 版面操作
    def _on_imposition_whole_rotate(self, delta: float) -> None:
        """面板的**整版旋转**组件吐了增量：画布即时转，停顿后统一落盘。

        滑块拖动会连续吐增量（每格 0.5°），不能每格都走一遍
        ``set_page`` + 落盘 + 合成——``rotate_whole`` 只原地改 items 重绘
        （顺带把待落盘标脏），由 ``_imposition_edit_timer`` 在用户停手后
        统一 ``flush_pending``（→ items_changed → 落盘 + 防抖合成）。
        之前积压的任何未上报编辑也由这同一个计时器一并补发。
        """
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0 or not view.canvas.has_items():
            return
        view.canvas.rotate_whole(delta)
        self._start_imposition_edit_commit()

    def _on_imposition_item_rotate(self, angle: float) -> None:
        """面板的**选中图旋转**组件设了绝对角度：即时转，停顿后统一落盘。"""
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0:
            return
        if view.selected_slot() < 0:
            return  # 组件没选中时本来就该禁用；防御一下
        view.canvas.set_item_rotation(angle)
        self._start_imposition_edit_commit()

    def _start_imposition_edit_commit(self) -> None:
        """旋转组件改了画布但还没上报：启动停顿计时器（没建就立刻兜底提交）。"""
        timer = getattr(self, "_imposition_edit_timer", None)
        if timer is None:
            view = getattr(self, "imposition_view", None)
            if view is not None:
                view.canvas.flush_pending()
            return
        timer.start()

    def _commit_imposition_edit(self) -> None:
        """旋转组件停顿到期：把画布上的改动补报出去 + 回填面板角度。"""
        view = getattr(self, "imposition_view", None)
        if view is None:
            return
        view.canvas.flush_pending()  # → items_changed → 落盘 + 防抖合成
        # 整版转过后外接框变了：重新适配可视区（拖动画布时有意不适配，这里
        # 是组件操作，落定后一次适配是期望行为）
        view.canvas.refit()
        self._sync_imposition_rotation_ui()

    def _sync_imposition_rotation_ui(self) -> None:
        """把画布当前的角度回填到面板旋转组件（整体=平均角，单图=选中角）。

        回填走 blockSignals 语义（panel 内部挡信号），不会把同步误当成用户
        输入再转一次。没有页时两组组件都禁用。
        """
        panel = getattr(self, "imposition_panel", None)
        view = getattr(self, "imposition_view", None)
        if panel is None or view is None:
            return
        canvas = view.canvas
        if view.current_index() < 0 or not canvas.has_items():
            panel.set_page_available(False)
            panel.set_whole_angle(0.0)
            panel.set_item_rotation(None)
            return
        panel.set_page_available(True)
        panel.set_whole_angle(canvas.spread_rotation() or 0.0)
        panel.set_item_rotation(
            canvas.selected_rotation()
            if canvas.selected() >= 0 else None
        )

    def _on_imposition_reset_layout(self) -> None:
        """把本页版面复位成**刚拼好时的样子**（两张并排、原始尺寸、无旋转）。

        没有纸张之后，"复位"只能以**两张图的原始尺寸**为基准：重新按
        ``default_items`` 摆一遍（右槽在左槽右边、顶部对齐）。这样用户把图拖得
        乱七八糟之后一键就能回到干净的并排版面。
        """
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0:
            self._toast("info", "没有拼版页", "请先点左侧的拼版页，或添加一页拼版。")
            return
        view.flush_pending()
        index = view.current_index()
        pages = self._imposition_pages()
        if not 0 <= index < len(pages):
            return
        items = pages[index].get("items") or []
        files = [item.get("file") for item in items]
        # 单图页（整幅/落单）只有一项：复位 = 原始尺寸、归零位（没有"并排"）
        reset = single_items(files[0]) if len(files) == 1 else default_items(files)
        if reset is None:
            self._toast(
                "error", "无法复位",
                "读不到源图尺寸（文件可能已被移动或删除）。",
            )
            return
        pages[index] = {**pages[index], "items": reset}
        if not self.task_id:
            return
        scope = self._imposition_scope()
        doc = self.store.load_imposition_doc(self.task_id, **scope)
        doc["pages"] = pages
        self.store.save_imposition_doc(self.task_id, doc, **scope)
        view.update_current_items(reset)
        self._schedule_imposition_compose()
        self._schedule_imposition_page_thumb(index)
        self._update_imposition_status(index)
        self.log_view.append(f"第 {index + 1} 页拼版已复位为默认并排版面。")

    def _on_imposition_delete_item(self) -> None:
        """「删除选中图片」（面板）：把画布里选中的那张图从本页删掉。

        **页保留**——剩一张时面板会自动出现「新增图片」可以再补一张；**删到
        最后一张则整页移除**（空页没有意义，与左列「✕」释放同款语义——全部
        页删光后拼版**仍然启用**，只是没有可拼的图，第四步会提示先去拼版；
        2026-09-30 用户定：整页移除前要弹确认框）。被删的图不再被任何页引用，
        即自动回到「未选择列表」（下次「选择拼版」或「新增图片」都能再选它）。
        落盘走 ``_save_imposition_pages``：画布重灌会清空选中，「当前图片样式」
        区随之灰掉。
        """
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0:
            self._toast("info", "没有拼版页", "请先点左侧的拼版页，或添加一页拼版。")
            return
        view.flush_pending()
        index = view.current_index()
        slot = view.selected_slot()
        if slot < 0:
            self._toast("info", "没有选中的图片", "先在画布里点选要删除的图片。")
            return
        pages = self._imposition_pages()
        if not 0 <= index < len(pages):
            return
        items = [dict(item) for item in pages[index].get("items") or []]
        if not 0 <= slot < len(items):
            return
        removed = items.pop(slot)
        if not items:
            # 本页最后一张：页会跟着一起删（2026-09-30 用户定：要确认）。
            # 此刻还没动任何状态（items 是副本），取消直接返回即可。
            from qfluentwidgets import Dialog

            dialog = Dialog(
                "删除图片",
                f"「{Path(removed['file']).stem}」是本页最后一张图片，"
                "删除后整页拼版将一并移除。\n是否继续？",
                self.window(),
            )
            dialog.yesButton.setText("删除")
            dialog.cancelButton.setText("取消")
            if not dialog.exec():
                return
        if items:
            pages[index] = {**pages[index], "items": items}
        else:
            # 单图页删掉最后一张：页一并删除（空页没有意义），与左列
            # 「✕」释放同款语义——拼版仍处于**启用**态，只是没有可拼的图了
            pages.pop(index)
        self._save_imposition_pages(pages)
        view.set_current(min(index, len(pages) - 1))
        self._update_imposition_status(
            view.current_index() if view is not None else -1
        )
        if items:
            self.log_view.append(
                f"已删除{cn_page_label(index)}选中的图片"
                f"「{Path(removed['file']).stem}」，回到未选择列表。"
            )
        else:
            self.log_view.append(
                f"已删除{cn_page_label(index)}最后一张图片"
                f"「{Path(removed['file']).stem}」，本页没有图了，整页移除"
                f"（源图回到未选择列表）。"
            )
