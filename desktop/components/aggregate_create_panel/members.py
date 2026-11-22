# -*- coding: utf-8 -*-
"""聚合任务面板的「成员表格」面：分页/排序/删除/选择弹窗（``_MembersMixin``）。

Mixin 只在运行期与 ``AggregateCreatePanel`` 组合；本模块**不 import** 本包
``panel``，避免循环导入。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from desktop.components.aggregate_create_panel._qt import (
    QHBoxLayout,
    QTableWidgetItem,
    Qt,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    PushButton,
    ToolButton,
)
from qfluentwidgets import FluentIcon as FIF

from desktop import ui
from desktop.components.aggregate_create_panel.constants import (
    MEMBER_HEADER_HEIGHT,
    MEMBER_PAGE_SIZE,
)
from desktop.components.aggregate_create_panel.picker import AggregateMemberPicker
from desktop.components.pagination import Pager
from desktop.steps.aggregate import aggregate_start_label
from desktop.ui import theme as T

if TYPE_CHECKING:
    from qfluentwidgets import TableWidget

    from desktop.components.aggregate_create_panel._qt import Signal
    from desktop.components.pagination import Pagination


class _MembersMixin:
    """成员表格（分页展示、行内排序/删除、弹窗选择）；宿主面见 TYPE_CHECKING。"""

    if TYPE_CHECKING:
        _store: Any
        _members: list[str]
        _page: int
        _inspect: bool
        MEMBER_ROW_HEIGHT: int
        _STAGE_WIDTH: int
        _STAGE_WIDTH_MAX: int
        member_table: TableWidget
        member_hint: CaptionLabel
        member_pager: Pagination
        detail_requested: Signal

        def _sync_candidates(self) -> None: ...

    def _member_pager(self) -> Pager:
        """成员表格的分页状态（每页固定 ``MEMBER_PAGE_SIZE`` 行）。"""
        return Pager(len(self._members), MEMBER_PAGE_SIZE, self._page)

    def _member_index(self, local_row: int) -> int:
        """表格里的行号（当前页内）→ **成员下标**；非法行返回 ``-1``。"""
        if local_row < 0:
            return -1
        index = (self._page - 1) * MEMBER_PAGE_SIZE + local_row
        return index if index < len(self._members) else -1

    def _member_local_row(self, index: int) -> int:
        """成员下标 → 表格行号（不在当前页时返回 ``-1``，选中会退化成不选）。"""
        row = index - (self._page - 1) * MEMBER_PAGE_SIZE
        return row if 0 <= row < self.member_table.rowCount() else -1

    def _on_member_page_changed(self, page: int) -> None:
        """翻页：只重画当前页（成员顺序与已选集合都不动）。"""
        self._page = max(1, int(page))
        self._fill_members()

    def _fit_table_height(self, rows: int) -> None:
        """表格高度跟**当前页实际行数**走（用户 2026-11-18）。

        「最多 10 条一页，但是没有 10 条不能占用 10 条高度」——所以不是固定
        高度，而是 ``表头 + 行数 × 行高``；0 条时也有一行空白占位（见
        ``_fill_members``），高度跟那一行走。
        """
        height = MEMBER_HEADER_HEIGHT + max(0, int(rows)) * self.MEMBER_ROW_HEIGHT
        self.member_table.setFixedHeight(int(height) + 2)

    def _fill_members(self) -> None:
        """按 ``self._members`` 重画成员表格的**当前页**。

        数据仍是 `self._members`（有序、全量）；表格只画 ``[start, end)`` 这
        一段，行内按钮回调带上**成员下标**（不是表格行号），翻页才不会错位。
        """
        pager = self._member_pager()
        # 删掉/减少后页码越界：跟着钳制回来（末页删空不能停在空白页）
        self._page = pager.clamped_page
        start, end = pager.slice_bounds()
        page_ids = self._members[start:end]

        # 0 条时给**一行空白占位**（用户 2026-11-18）：表格塌成只剩表头看着
        # 像坏了；占位行不带任何控件，纯空行撑起一行的高度。
        rows: list = page_ids if page_ids else [None]

        self.member_table.setRowCount(0)
        self.member_table.setRowCount(len(rows))
        for local_row, tid in enumerate(rows):
            if tid is None:
                self.member_table.setRowHeight(local_row, self.MEMBER_ROW_HEIGHT)
                continue
            index = start + local_row
            record = self._store.get_task(tid)
            name = str(record.get("name") or "") if record else ""
            number_item = QTableWidgetItem(tid)
            number_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.member_table.setItem(local_row, 0, number_item)
            self.member_table.setItem(local_row, 1, QTableWidgetItem(name))
            self.member_table.setCellWidget(
                local_row, 2, self._node_widget(self._completed_stages(tid))
            )
            self.member_table.setCellWidget(
                local_row, 3, self._action_widget(index)
            )
            self.member_table.setRowHeight(local_row, self.MEMBER_ROW_HEIGHT)

        self._fit_stage_column()
        self._fit_table_height(len(rows))
        # 只有超过一页才出现分页条（10 条以内翻页没有意义，白占一行高度）
        self.member_pager.setVisible(pager.total > MEMBER_PAGE_SIZE)
        self.member_pager.set_pager(pager)

        count = len(self._members)
        self.member_hint.setText(
            f"已选 {count} 个（顺序即合并页序）" if count else "尚未选择子任务"
        )

    def _completed_stages(self, tid: str) -> list[str]:
        """该子任务**已经完成**的节点（读失败按"没完成"降级）。"""
        try:
            return list(self._store.completed_aggregate_stages(tid))
        except Exception:  # noqa: BLE001 - 进度读失败按"没完成"降级
            return []

    def _fit_stage_column(self) -> None:
        """任务节点列宽按**实际控件**放宽（用户 2026-11-17：「宽一些，能够显示
        完整节点」）。

        ⚠️ 量的是**已经建好的那一格**的 ``sizeHint()``（标签自己的字号 + 两侧
        内边距），不另算一份 ``QFontMetrics``：另起一份字体去度量，量出来的
        和画出来的未必是同一套（字体回退/DPI 一换就错位，结果就是"量着够宽、
        实际照样被裁"）。
        ⚠️ 只**加宽**不缩窄（下限 ``_STAGE_WIDTH``），且封顶
        ``_STAGE_WIDTH_MAX``：再长就让任务名称列（拉伸列）让位，别把表格撑出
        可视区。
        """
        needed = self._STAGE_WIDTH
        for row in range(self.member_table.rowCount()):
            wrap = self.member_table.cellWidget(row, 2)
            if wrap is not None:
                needed = max(needed, wrap.sizeHint().width() + 4)
        width = min(needed, self._STAGE_WIDTH_MAX)
        self.member_table.horizontalHeader().resizeSection(2, int(width))

    def _node_widget(self, done: list[str]) -> QWidget:
        """任务节点格：该子任务**已经完成**的节点（只读）。

        数据走 :meth:`store.completed_aggregate_stages`——与起始节点候选
        **同一份判据**（含「提取图片」，用户 2026-11-18）：用户看着每行各自
        完成了什么，就知道下面那排候选为什么是这几个。没有已完成节点时给
        灰字占位，别让格子空着像坏了。
        """
        wrap = QWidget()
        wrap.setFixedHeight(self.MEMBER_ROW_HEIGHT)
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(T.SPACE_SM, 0, T.SPACE_SM, 0)
        if done:
            label = BodyLabel("、".join(aggregate_start_label(s) for s in done))
            ui.apply_to(label, T.SIZE_CAPTION, color=T.INK)
            label.setToolTip(
                "该子任务已完成、可作为聚合节点的任务节点：\n"
                + "\n".join(aggregate_start_label(s) for s in done)
            )
        else:
            label = CaptionLabel("（暂无已完成节点）")
            ui.apply_to(label, T.SIZE_CAPTION, color=T.INK_FAINT)
        lay.addWidget(label)
        lay.addStretch()
        return wrap

    def _action_widget(self, row: int) -> QWidget:
        """操作格：行内「详情 / 上移 / 下移 / 删除」（行内即点即生效）。

        ⚠️ 「删除」是**文字按钮**（用户 2026-11-17：「移除按钮改成删除按钮」）：
        图标 × 看不出是"移出聚合"，文字最直接；tooltip 再说清它只影响本次
        聚合、不删任务本身。
        """
        wrap = QWidget()
        wrap.setFixedHeight(self.MEMBER_ROW_HEIGHT)
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(T.SPACE_SM, 0, T.SPACE_SM, 0)
        # 与任务列表行内操作列同款间距（那边也是 详情 + 危险色删除）
        lay.setSpacing(T.SPACE_SM)
        detail_btn = PushButton("详情")
        detail_btn.setFixedSize(52, 30)
        detail_btn.setToolTip("弹窗查看该子任务的详情（不离开本页）")
        detail_btn.clicked.connect(
            lambda: self.detail_requested.emit(self._members[row])
        )
        lay.addWidget(detail_btn)
        if self._inspect:
            # 查看模式只留「详情」：排序/删除会改成员集合（已汇集的输入随之失效）
            lay.addStretch()
            return wrap
        up = ToolButton(FIF.UP)
        up.setToolTip("上移（合并页序提前）")
        up.clicked.connect(lambda: self._on_move_from(row))
        down = ToolButton(FIF.DOWN)
        down.setToolTip("下移（合并页序靠后）")
        down.clicked.connect(lambda: self._on_move_from(row, delta=1))
        remove = PushButton("删除")
        remove.setFixedSize(52, 30)
        remove.setToolTip("从本次聚合里删掉这一行（不会删除该任务本身）")
        # ⚠️ 危险色走共享的一份（`theme.danger_button_qss`）：任务列表的行内
        #    「删除」就是这颗按钮，两处必须长得一样（用户 2026-11-17 要"删除
        #    按钮"，不是图标 ×）。
        remove.setStyleSheet(T.danger_button_qss())
        remove.clicked.connect(lambda: self._on_remove_from(row))
        for button in (up, down):
            button.setFixedSize(30, 30)
            lay.addWidget(button)
        lay.addWidget(remove)
        lay.addStretch()
        return wrap

    def _on_move_from(self, row: int, delta: int = -1) -> None:
        """上移/下移指定**成员下标**（行内按钮；顺序有意义）。"""
        target = row + delta
        if not (0 <= target < len(self._members)):
            return
        self._members[row], self._members[target] = (
            self._members[target],
            self._members[row],
        )
        self._fill_members()
        self.member_table.selectRow(self._member_local_row(target))

    def _on_remove_from(self, row: int) -> None:
        """删除指定**成员下标**（行内按钮）；成员变了候选也可能变。"""
        if not (0 <= row < len(self._members)):
            return
        del self._members[row]
        self._sync_candidates()
        self._fill_members()

    # 兼容旧调用（自测/外部的无参入口）：按当前选中行操作
    def _selected_member_row(self) -> int:
        """当前选中行 → **成员下标**（跨页也成立：表格只画当前页）。"""
        return self._member_index(self.member_table.currentRow())

    def _on_move(self, delta: int) -> None:
        """上移/下移**当前选中**的成员。"""
        row = self._selected_member_row()
        if row >= 0:
            self._on_move_from(row, delta)

    def _on_remove(self) -> None:
        """删除**当前选中**的成员。"""
        row = self._selected_member_row()
        if row >= 0:
            self._on_remove_from(row)

    def _open_picker(self) -> None:
        """弹「选择子任务」：勾掉的移除、新勾的按**列表顺序**追加在已排好的后面。

        ⚠️ 列表是任务号**倒序**（新的在前），所以新勾的追加顺序也是新的在前；
        用户手动排过的成员（上移/下移）位置不动——弹窗只影响"有没有选中"。
        """
        rows = self._load_task_rows()
        if rows is None:
            return
        picker = AggregateMemberPicker(rows, self._members, self)
        dialog = picker.build_dialog(self.window())
        if not dialog.exec():
            return
        self._apply_checked(picker.checked_ids())

    def _apply_checked(self, checked: list[str]) -> None:
        """把弹窗的勾选结果落回成员表（``_open_picker`` 拆出的落点，可测）。

        - 勾 **0 条**不算错误（用户 2026-11-18）：用户可能只是翻翻没挑，
          这里直接返回——成员保持原样，**不弹 toast、不清空已有成员**；
        - 勾了：已排好序的成员保序保留，新成员按弹窗列表顺序（任务号倒序）
          追加；成员变了候选节点可能变（共有节点少了一个），起始节点跟着收敛。
        """
        if not checked:
            return
        kept = [m for m in self._members if m in checked]
        known = set(kept)
        appended = [m for m in checked if m not in known]
        self._members = kept + appended
        # 新加的可能排得很后，回第一页更符合"刚选完"的预期
        self._page = 1
        self._sync_candidates()
        self._fill_members()

    def _load_task_rows(self) -> list[dict] | None:
        """读全量任务行（含节点状态胶囊），供「选择子任务」弹窗展示。

        数据与任务管理列表**同一来源**（``TaskRowsWorker``：逐任务读
        runs.json + 流程图，勾选弹窗里才能看到与列表一致的节点状态）。

        ⚠️ 这里**内联**跑 worker（不起后台线程）：行组装只是轻 IO，列表回程
        实测毫秒级；弹窗本来就是「点按钮等一下」的场景，不值得为它引入线程
        生命周期管理。列表页把同一个 worker 放后台，是为了「先画窗口再填
        数据」的**启动**体验，两个场景不矛盾。

        读失败返回 ``None``（弹 toast 让用户重试），不让弹窗开着空表。
        """
        from desktop.ui.toast import show_toast
        from desktop.workers import TaskRowsWorker

        worker = TaskRowsWorker(self._store)
        rows: list[dict] = []
        failures: list[str] = []
        worker.completed.connect(rows.extend)
        worker.failed.connect(failures.append)
        worker.run()
        if failures:
            show_toast(
                self.window(), "warning", "读取任务列表失败",
                f"{failures[0]}（请重试）",
            )
            return None
        return rows


__all__ = ["_MembersMixin"]
