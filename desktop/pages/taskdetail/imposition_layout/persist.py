# -*- coding: utf-8 -*-
"""模块二「拼版操作」的**版面落盘与状态行**分片。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from desktop.services.imposition import cn_page_label

if TYPE_CHECKING:
    from desktop.pages.taskdetail.imposition_layout._host import (
        ImpositionLayoutHost,
    )
else:
    ImpositionLayoutHost = object


class PersistMixin(ImpositionLayoutHost):
    """版面改动落盘（拖动/缩放/旋转）与状态行刷新。"""

    # ------------------------------------------------------------- 版面落盘
    def _on_imposition_slot_selected(self, _slot: int) -> None:
        """画布里选中了右槽/左槽/无：刷新状态行。"""
        view = getattr(self, "imposition_view", None)
        if view is not None:
            self._update_imposition_status(view.current_index())

    def _on_imposition_items_changed(self, index: int, items: list) -> None:
        """版面被拖动/缩放/旋转：落盘 + 重新合成（防抖）。"""
        pages = self._imposition_pages()
        if not 0 <= index < len(pages):
            return
        pages[index] = {**pages[index], "items": [dict(item) for item in items]}
        if not self.task_id:
            return
        scope = self._imposition_scope()
        doc = self.store.load_imposition_doc(self.task_id, **scope)
        doc["pages"] = pages
        self.store.save_imposition_doc(self.task_id, doc, **scope)
        self._schedule_imposition_compose()
        self._schedule_imposition_page_thumb(index)
        self._update_imposition_status(index)

    def _update_imposition_status(self, index: int) -> None:
        """状态行：当前页 + 选中槽位 + 生效与否。"""
        label = getattr(self, "imposition_panel_status", None)
        if label is None:
            return
        pages = self._imposition_pages()
        # 「新增图片」只在单图页出现（2026-09-30 用户定）——面板按钮显隐
        # 搭状态行这趟车一起同步（状态行是"当前页变了"的汇聚点）
        panel = getattr(self, "imposition_panel", None)
        if panel is not None:
            single = (
                0 <= index < len(pages)
                and len(pages[index].get("items") or []) == 1
            )
            panel.set_single_page(single)
        if not pages:
            text = "尚未添加拼版页"
        else:
            view = getattr(self, "imposition_view", None)
            slot = view.selected_slot() if view is not None else -1
            slot_text = {0: "（选中：右侧）", 1: "（选中：左侧）"}.get(slot, "")
            text = f"{cn_page_label(index)} / 共 {len(pages)} 页{slot_text}"
        # ⚠️ 四态措辞：**启用**决定取图来源，**有没有页**决定能不能真出东西。
        # 「已启用但一页都没拼」是最容易让人以为"没生效"的一档——必须把话说
        # 死：流程确实已经改走拼版了，只是还没有可拼的图。
        _usable, _reason = self._imposition_switch_state()
        if self.imposition_active() and not self.imposition_effective():
            # ⚠️ 中间档：用户**勾了**但这一步现在用不上（流程图里没有这一格等）。
            #    只说"已启用"会与实际取图矛盾，只说"未启用"又会让用户怀疑
            #    "我明明勾了"——所以把原因原样说出来。
            text += f"　·　已勾选但当前用不上：{_reason}"
        elif self.imposition_effective():
            text += (
                "　·　拼版已启用：PDF排版用拼版结果"
                if pages
                else "　·　拼版已启用，但还没有拼版页——"
                     "请先「选择拼版」，否则 PDF排版没有输入"
            )
        elif pages:
            text += "　·　拼版未启用：勾选下方开关后 PDF排版 才会用拼版结果"
        label.setText(text)
        # 状态行是所有"当前页/选中变了"路径的汇聚点，旋转组件的回填搭这趟车
        self._sync_imposition_rotation_ui()
