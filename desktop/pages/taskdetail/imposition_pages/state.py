# -*- coding: utf-8 -*-
"""模块一「选择拼版」的**启用状态**分片：读写开关与勾选回调。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from desktop.pages.taskdetail.imposition_pages._host import (
        ImpositionPagesHost,
    )
else:
    ImpositionPagesHost = object


class PagesStateMixin(ImpositionPagesHost):
    """拼版启用开关：读盘、落盘与勾选回调。"""

    # ------------------------------------------------------------- 选择状态
    def _load_imposition_enabled(self) -> bool:
        """当前任务是否选择了拼版（默认不选择）。

        ⚠️ 开关是**流程级**的（流程图上「是否拼版」网关问的就是它，决定第四步
        取图来源），所以读写都走**主节点**那一份文件
        （见 ``ImpositionBaseMixin._imposition_flag_scope``）；版面（pages）才
        按节点分。

        ⚠️ **流程条上那一格的"已选择/绿勾"不看它**（2026-10-18）：那一格表达的是
        "这一步处理到哪了"（判据是本节点有没有拼版页，见
        ``_sync_imposition_step_bar``）。这个开关只决定"第四步取不取拼版结果"。
        """
        if not self.task_id:
            return False
        return bool(
            self.store.load_imposition_doc(
                self.task_id, **self._imposition_flag_scope()
            ).get("enabled")
        )

    def _save_imposition_enabled(self, enabled: bool) -> None:
        """把选择状态随任务落盘（drafts/imposition.json ← 主节点那一份）。"""
        if not self.task_id:
            return
        scope = self._imposition_flag_scope()
        doc = self.store.load_imposition_doc(self.task_id, **scope)
        doc["enabled"] = bool(enabled)
        self.store.save_imposition_doc(self.task_id, doc, **scope)

    def _on_imposition_enabled_toggled(self, on: bool) -> None:
        """拼版详情里的启用开关：更新节点选择态并落盘。

        启用/取消会**改变第四步的取图来源**（见 ``print_source_dir``），所以
        同时把待打印列表刷新一次——否则用户切到第四步看到的还是旧的来源。
        """
        self._save_imposition_enabled(on)
        self._sync_imposition_step_bar()
        self._toast(
            "info", "图片拼版",
            "已启用「图片拼版」：第四步「PDF排版」将使用拼版结果。"
            if on else
            "已取消「图片拼版」：第四步「PDF排版」回到第三步的去底色产物。",
        )
        if on:
            self._schedule_imposition_compose()
        self._refresh_print_source()
