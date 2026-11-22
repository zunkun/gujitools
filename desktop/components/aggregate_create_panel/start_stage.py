# -*- coding: utf-8 -*-
"""聚合任务面板的「起始节点」面：候选计算 + 单选勾选框（``_StartStageMixin``）。

Mixin 只在运行期与 ``AggregateCreatePanel`` 组合；本模块**不 import** 本包
``panel``，避免循环导入。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qfluentwidgets import CheckBox

from desktop.components.aggregate_create_panel.constants import DEFAULT_START_STAGE
from desktop.steps.aggregate import (
    AGGREGATE_START_STAGES,
    aggregate_start_label,
    any_member_stages,
    missing_members,
    preferred_start_stage,
)

if TYPE_CHECKING:
    from PySide6.QtWidgets import QHBoxLayout

    from qfluentwidgets import CaptionLabel


class _StartStageMixin:
    """起始节点候选与勾选框；宿主面见 TYPE_CHECKING。"""

    if TYPE_CHECKING:
        _store: Any
        _members: list[str]
        _start_stage: str
        _candidates: tuple[str, ...]
        _stage_boxes: dict[str, CheckBox]
        _syncing_stage: bool
        _inspect: bool
        _stage_layout: QHBoxLayout
        stage_hint: CaptionLabel

        def _rebuild_editor(self) -> None: ...
        def _refresh_summary(self) -> None: ...

    def start_candidates(self) -> tuple[str, ...]:
        """当前候选起始节点（按拓扑序；含「提取图片」，可作起点）。

        候选 = 所选子任务里**任意一个已经完成**的任务节点（用户 2026-11-18，
        取代早先"每个成员都完成过"的交集）：逐成员取
        :meth:`store.completed_aggregate_stages`（历史上成功过才算完成，
        拼版=已启用且有拼版页），再用
        :func:`desktop.steps.aggregate.any_member_stages` 求**并集**
        ——"现有任务已经存在生效的节点是提取/检测/去底，因此可以从这些节点
        里挑一个"。交集口径在"各子集进度不同步"时会收成空集（实测三个子集
        分别完成 检测/检测/去底 ⇒ 交集为空），列表就退化成兜底全集，等于
        没跟着子任务变。

        ⚠️ 并集意味着某些成员可能缺这个节点，汇集时缺它的页面——
        :meth:`_refresh_stage_hint` 会点名这些子任务。

        还没选成员、或并集为空时兜底成全部候选：列表空着用户连"先选一个"
        都做不到（提交时 ``store`` 仍会校验）。

        ⚠️ 查看模式（``inspect``）额外一条：**落库的那个起始节点必须在候选
        里**。它当年是按成员当时的进度选的，成员后来重跑/清理过的话并集可能
        已经不含它——那样勾选框里就看不到"当前起点"，看着像坏了。这里把它
        按拓扑序补回清单（只影响显示，不改落库值）。
        """
        done = self._member_done_lists()
        union = any_member_stages(done)
        stages = tuple(union or AGGREGATE_START_STAGES)
        if self._inspect and self._start_stage not in stages:
            wanted = set(stages) | {self._start_stage}
            stages = tuple(s for s in AGGREGATE_START_STAGES if s in wanted)
        return stages

    def _member_done_lists(self) -> list[tuple[str, ...]]:
        """逐成员**已完成**的节点（与 :meth:`members` 对齐；读失败按空算）。"""
        return [self._member_completed_of(tid) for tid in self._members]

    def _member_completed_of(self, task_id: str) -> tuple[str, ...]:
        """某个子任务**已经完成**的节点（读不出来返回空元组，交给兜底）。"""
        try:
            return tuple(self._store.completed_aggregate_stages(task_id))
        except Exception:  # noqa: BLE001 —— 进度读坏了不能拖死创建页
            return ()

    def _member_name(self, task_id: str) -> str:
        """子任务名（读不到回落任务号；提示文案用）。"""
        try:
            record = self._store.get_task(task_id) or {}
        except Exception:  # noqa: BLE001 —— 提示文案读不到名字不算错
            record = {}
        return str(record.get("name") or task_id)

    def _sync_candidates(self) -> None:
        """重算候选并重建勾选框；起始节点不在候选里就按
        :func:`preferred_start_stage` 落一个默认值。

        ⚠️ 起始节点被**挪**了（成员换了一批，原来那个节点没人完成过）时必须
        重建派生图——否则勾着的和图上画的是两个不同的起点（自测实测：
        只剩「拼版/排版」的成员加进来后，勾选框是拼版、图上还从 PDF排版
        开始）。
        """
        done = self._member_done_lists()
        self._candidates = tuple(self.start_candidates())
        moved = False
        if self._start_stage not in self._candidates:
            fallback = preferred_start_stage(done, self._start_stage)
            if fallback not in self._candidates:
                fallback = self._candidates[0] if self._candidates else DEFAULT_START_STAGE
            if fallback != self._start_stage:
                self._start_stage = fallback
                moved = True
        self._rebuild_stage_boxes()
        if moved:
            self._rebuild_editor()
            self._refresh_summary()

    def _rebuild_stage_boxes(self) -> None:
        """按候选重建 checkbox 列表（回显当前起始节点）。"""
        while self._stage_layout.count():
            item = self._stage_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._stage_boxes = {}
        self._syncing_stage = True
        try:
            for stage in self._candidates:
                box = CheckBox(aggregate_start_label(stage))
                box.setChecked(stage == self._start_stage)
                box.toggled.connect(
                    lambda checked, s=stage: self._on_stage_box_toggled(s, checked)
                )
                # 查看模式下**也可以改**（用户 2026-11-18：「起始节点可以切换
                # 变更」）——改完保存流程时会弹确认，讲清"历史汇集数据作废"。
                box.setToolTip(
                    f"选择「{aggregate_start_label(stage)}」"
                    if not self._inspect
                    else "改起始节点会让已汇集的输入与历史处理结果作废"
                    "（保存流程时会再确认一次）"
                )
                self._stage_layout.addWidget(box)
                self._stage_boxes[stage] = box
            self._stage_layout.addStretch()
        finally:
            self._syncing_stage = False
        self._refresh_stage_hint()

    def _refresh_stage_hint(self) -> None:
        """候选来源一句话 + **选中的节点有谁没跑过**（并集的代价必须可见）。"""
        count = len(self._members)
        if not count:
            hint = (
                "先选择子任务；候选 = 所选子任务里任意一个已经完成的任务节点"
                "（单选：选哪个节点，流程就从哪个节点开始）。"
            )
        else:
            done = self._member_done_lists()
            if not any(done):
                # 一个节点都没完成 ⇒ 候选是兜底全集（不是"推出来的"），
                # 说真话：别让用户以为这些节点都能直接拿来当起点。
                hint = (
                    f"所选 {count} 个子任务都还没有完成任何节点；"
                    "候选暂列全部节点，等子任务跑出结果后这里会跟着变。"
                )
            else:
                hint = (
                    f"候选来自 {count} 个子任务里任意一个已经完成的任务节点"
                    "（并集，单选）：选哪个节点，聚合流程就从哪个节点开始，"
                    "它前面的步骤会被丢弃。"
                )
                missing = missing_members(self._start_stage, done)
                if missing:
                    names = "、".join(
                        self._member_name(self._members[i]) for i in missing
                    )
                    hint += (
                        f"\n⚠️ 未完成「{aggregate_start_label(self._start_stage)}」："
                        f"{names} —— 汇集时不会带上这些子任务的页面。"
                    )
        if self._inspect:
            hint += (
                "\n（子任务只读；起始节点可以改——改了保存时会提示"
                "「历史汇集数据将作废」，确认后按新起点重新汇集。）"
            )
        self.stage_hint.setText(hint)

    def _on_stage_box_toggled(self, stage: str, checked: bool) -> None:
        """**单选**语义：勾一个别的全灭；点掉当前唯一勾选不生效。

        ⚠️ 点掉不生效是刻意的：不可能存在"没有起始节点"的聚合任务；也不再
        弹提示（用户只是想看看点一下，弹窗会烦）。``_syncing_stage`` 期间的
        信号一律忽略——批量改勾选状态不能被当成用户操作（否则自噬）。
        """
        if self._syncing_stage:
            return
        if not checked:
            box = self._stage_boxes.get(stage)
            if stage == self._start_stage and box is not None:
                self._syncing_stage = True
                try:
                    box.setChecked(True)
                finally:
                    self._syncing_stage = False
            return
        if stage == self._start_stage:
            return
        self._syncing_stage = True
        try:
            for key, box in self._stage_boxes.items():
                box.setChecked(key == stage)
        finally:
            self._syncing_stage = False
        self._start_stage = stage
        # 派生图跟着换（旧图不能原地改：根变了，那份"自定义"没有意义）
        self._rebuild_editor()
        self._refresh_summary()
        # 换节点 ⇒ "谁没跑过这一步"跟着变（提示里的点名要重算）
        self._refresh_stage_hint()


__all__ = ["_StartStageMixin"]
