# -*- coding: utf-8 -*-
"""拼版共享基元的**文档读写**分片：拼版文档、作用域与成品目录。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from desktop.pages.taskdetail.imposition._host import ImpositionBaseHost
else:
    ImpositionBaseHost = object


class DocumentMixin(ImpositionBaseHost):
    """拼版文档读写、节点作用域、成品输出目录与启用开关落盘。"""

    # ------------------------------------------------------------- 文档读写
    def _imposition_doc(self) -> dict:
        """**当前拼版节点**的拼版文档（含选择态与逐页版面）。

        ⚠️ 读写必须走**同一个**作用域（B 方案）：开关（``enabled``）与逐页版面
        （``pages``）都按节点存（``drafts/imposition[~<节点>].json``）。此前这个读法
        漏了作用域——写进副本节点的 122 页，读的却是主节点那份空文档 ⇒ 选完页
        「拼版窗口」里一张也不显示、左侧还停在「还没有拼版页」（用户 2026-10-17
        实测报障）。
        """
        if not self.task_id:
            return {"enabled": False, "pages": []}
        return self.store.load_imposition_doc(
            self.task_id, **self._imposition_scope()
        )

    def _imposition_pages(self, doc: dict | None = None) -> list[dict]:
        return list((doc or self._imposition_doc()).get("pages") or [])

    def _save_imposition_pages(self, pages: list[dict]) -> None:
        """把拼版页清单落盘（保持选择态不变）并刷新视图 + 重新合成。

        页数 0↔n 会翻转「生效」状态（流程条连线/绕行线跟着变），一并同步。
        """
        if not self.task_id:
            return
        # ⚠️ 版面按**节点**存（B 方案）：`enabled` 保持流程级那一份不动。
        scope = self._imposition_scope()
        doc = self.store.load_imposition_doc(self.task_id, **scope)
        doc["pages"] = [dict(page) for page in pages]
        self.store.save_imposition_doc(self.task_id, doc, **scope)
        self._sync_imposition_step_bar()
        self._refresh_imposition_view()
        self._schedule_imposition_compose()

    def _set_imposition_checked(self, on: bool) -> None:
        """程序化同步启用开关（blockSignals 避免回抛覆盖落盘值）。"""
        checkbox = getattr(self, "imposition_enabled_checkbox", None)
        if checkbox is not None:
            checkbox.blockSignals(True)
            checkbox.setChecked(bool(on))
            checkbox.blockSignals(False)
        self._save_imposition_enabled(bool(on))
        self._sync_imposition_step_bar()
        if on:
            self._schedule_imposition_compose()
        self._refresh_print_source()
        self._update_imposition_status(
            getattr(
                getattr(self, "imposition_view", None), "current_index", lambda: -1
            )()
        )

    # ------------------------------------------------------------- 源图与生效
    def _imposition_scope(self) -> dict:
        """拼版**版面文档**的节点作用域（B 方案）：两个「图片拼版」节点各有
        自己的 ``drafts/imposition[~<节点>].json``（页面清单与逐页版面）。"""
        return self._node_scope(self.node_of_stage("imposition"))

    def _imposition_flag_scope(self) -> dict:
        """「在流程中启用图片拼版」这个**开关**的作用域：恒取拼版的主节点。

        ⚠️ 开关是**流程级条件**（流程图上那个「是否拼版」网关问的就是它；
        状态机的 ``imposition`` 标志没有节点上下文，见 ``store.scheduler_flags``），
        所以它只有一份、读写都走主节点的文件；**版面（pages）才是按节点分的**。
        在副本节点上勾选，改的仍是这一份——与"这个开关决定第四步取图来源"的
        既有语义一致。

        ⚠️ **流程条上那一格的"已选择/绿勾"不看这个开关**（2026-10-18）：那一格
        表达的是"这一步处理到哪了"，判据是**本节点有没有拼版页**
        （见 :meth:`_sync_imposition_nodes`）。开关只决定"第四步取不取拼版结果"。
        """
        return self._node_scope(self._stage_primary.get("imposition"))

    def _imposition_output_dir(self) -> Path:
        """**本节点**拼版成品的输出目录（``stages/imposition[~<节点>]``）。

        合成 worker 写这里、缩略图/编辑回写/新鲜度判定也读这里——按阶段取会让
        两个「图片拼版」节点互相覆盖成品页。
        """
        task_id = self.task_id
        if not task_id:
            return Path()
        return self.store.node_or_stage_output(
            task_id, self.node_of_stage("imposition"), "imposition"
        )
