# -*- coding: utf-8 -*-
"""步骤条构建与按流程重建（从原 ``view.py`` 拆出）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from desktop.components.step_bar import StepBar
from desktop.store import IMPOSITION_STAGE

if TYPE_CHECKING:
    from desktop.pages.taskdetail.view._host import DetailViewHost
else:
    DetailViewHost = object


class DetailStepBarMixin(DetailViewHost):
    """步骤条的槽位快照、标题序数与重建。"""
    def _build_step_bar(self) -> StepBar:
        # 步骤条自带卡片底（paintEvent 绘制），不再套一层 Card，避免"卡片套卡片"
        # ⚠️ **记下这份槽位快照**（2026-10-06）：重建时要用**它**把旧下标解析成
        #    步骤 key。解析"旧高亮在哪一步"绝不能去问 ``flow_slots()``——那读的是
        #    磁盘上那张（可能已经改过的）新流程图，旧格序会被解释成新格序，
        #    高亮就默默挪到了别的步骤上。快照是"这条步骤条**当时**按哪张图建的"
        #    唯一可靠凭据。
        self._step_bar_slots = self.flow_slots()
        self.step_bar = StepBar(
            self._bar_step_titles(),
            optional_after=self._optional_after_index(),
            unmapped=self._unmapped_step_indices(),
            # ⚠️ 下标只有一种语义＝格序 bar_index（MEMORY「三套下标」第①种）。
            #    少传这一张映射表，StepBar 就会退回"真实步骤序"，于是点「生成
            #    PDF」打开的是「图片拼版」、它的状态也永远上不了屏。
            bar_indices=self._bar_step_indices(),
            optional_bar_index=self._optional_bar_index(),
            # ⚠️ **全部**可选节点（B 方案）：同一步骤可以画多个「图片拼版」，
            #    只给一个会让第二个在流程条上凭空消失（用户 2026-10-17 报障：
            #    "任务详情没有完整显示自定义的流程"）。
            optionals=self._optional_bar_specs(),
        )
        self.step_bar.current_changed.connect(self._select_stage)
        # ⚠️ 只接 ``optional_clicked``（带格序）：它覆盖"点的是哪一个可选节点"，
        #    多节点下才寻址正确；``imposition_clicked``（无参、只认第一个）留着
        #    给外部调用方，这里**不再**接——两个都接会让同一次点击切两遍步骤
        #    （``_select_stage`` 每次都要读盘解析流程 + 重载页清单，不是免费的）。
        self.step_bar.optional_clicked.connect(self._select_stage)
        return self.step_bar

    def _bar_step_titles(self) -> list[str]:
        """步骤条上**真实步骤**的标题序列（按本任务流程顺序）。

        可选节点（拼版）**不在这里**——它由 :class:`StepBar` 按
        ``optional_after`` 插进去；这里只给真实步骤，顺序取槽位表的
        ``bar_index``。构造期还没有任务（``flow_slots`` 回落默认流程），
        此时就是默认流程的步骤序列。

        ⚠️ **同一步骤的多个节点各占一格，标题要能区分**（B 方案）：两个
        「图片去底色」节点都写「图片去底色」的话，用户根本看不出点了哪个、
        哪个跑过、哪个有产物。这里按节点在**同类型节点里的序号**加「（2）」，
        单节点时**恒不加**（默认流程与所有现存任务逐字不变）。
        """
        slots = sorted(
            (s for s in self.flow_slots() if not s.optional),
            key=lambda s: s.bar_index,
        )
        return [f"{s.label}{self.node_display_suffix(s.node_id)}" for s in slots]

    def _bar_step_indices(self) -> list[int]:
        """真实步骤序列里每一格的**格序 ``bar_index``**（喂 :class:`StepBar`）。

        ⚠️ 与 :meth:`_bar_step_titles` **同序同长**（都过滤掉可选节点），
        两者按下标一一对应。序数 ≠ 格序：默认流程里「PDF排版」序数 3 而
        格序 4（拼版占了第 3 格），两者混用就是"点一个步骤打开另一个步骤"。
        """
        slots = sorted(
            (s for s in self.flow_slots() if not s.optional),
            key=lambda s: s.bar_index,
        )
        return [s.bar_index for s in slots]

    def _optional_bar_index(self) -> int | None:
        """拼版节点自己的格序（``None`` = 本流程没有这一格）。"""
        for slot in self.flow_slots():
            if slot.optional and slot.step == IMPOSITION_STAGE:
                return slot.bar_index
        return None

    def _optional_bar_specs(self) -> list[tuple[int, int, str]]:
        """步骤条上**全部可选节点**：``[(插在第几个真实步骤之后, 格序, 标题), …]``。

        ⚠️ 同一步骤可以有**多个**可选节点（用户 2026-10-17 的流程图：开头一个
        「图片拼版」、网关「是」分支里又一个）。只传一个的话第二个在流程条上
        凭空消失——用户看到的就是"任务详情没有完整显示自定义流程"。

        ``after`` 的口径与 :meth:`FlowDiagram.optional_after` 一致：**最后一个
        左邻居真实步骤的序数**，没有左邻居时 ``-1``（插在最前）。标题带节点序号
        （``图片拼版（2）``），与真实步骤同一套区分规则。
        """
        slots = self.flow_slots()
        real = [s for s in slots if not s.optional]
        specs: list[tuple[int, int, str]] = []
        for slot in sorted((s for s in slots if s.optional), key=lambda s: s.bar_index):
            after = -1
            for position, item in enumerate(real):
                if item.bar_index < slot.bar_index:
                    after = position
            label = f"{slot.label}{self.node_display_suffix(slot.node_id)}"
            specs.append((after, slot.bar_index, label))
        return specs

    def _unmapped_step_indices(self) -> set[int]:
        """步骤条上"图上有、但还没有功能"的下标集合（2026-10-05）。

        口径 = 槽位表里 ``mapped=False`` 的那些格（真实步骤序列里的下标）。
        它们仍占格子，只是画成灰色并标注"未接入"——用户能在流程图上画任意
        节点，界面上就必须**看得见**那一步，否则"改了流程图没反应"。

        ⚠️ 只算**真实步骤**（``optional`` 的拼版不算），下标要与
        :meth:`_bar_step_titles` 的序列一致——那个序列过滤掉了可选节点。
        """
        return {
            i
            for i, slot in enumerate((s for s in self.flow_slots() if not s.optional))
            if not slot.mapped
        }

    def _optional_after_index(self) -> int | None:
        """可选节点插在**第几个真实步骤之后**（喂 :class:`StepBar`）。

        口径与算法都在 :meth:`FlowDiagram.optional_after`（⚠️ 那是
        "真实步骤列表里的下标"，**不是**槽位表的 ``bar_index``——后者含了
        可选节点自己占的格子，两者不相等）。本流程没有可选节点时返回
        ``None``；可选节点排在**最前**（没有左邻居）时返回 ``-1``，
        :class:`StepBar` 据此把节点插在第一个真实步骤之前。
        """
        task_id = getattr(self, "task_id", None)
        if not task_id:
            # 没任务时按**默认模板**算（静态展示）。⚠️ 此前这里是
            # ``FlowDefinition.default().optional_after(...)``——那是**旧模型**
            # 从端口边表派生的一份流程，与 ``FlowDiagram.optional_after``
            # 算法不同；模板文件缺失时两条路会给出不同的插入位（步骤条上
            # 拼版节点与槽位表对不上）。
            from desktop.steps.scheduler import load_default_diagram

            return load_default_diagram().optional_after(IMPOSITION_STAGE)
        # ⚠️ 走**图模型**（能读 bpmn.io 的网关/自定义 id）；旧 `task_flow`
        #    读不了就静默回落默认流程 ⇒ 步骤条永远长的像 task_default。
        return self.store.task_diagram(task_id).optional_after(IMPOSITION_STAGE)

    @staticmethod
    def _step_key_at(slots, bar_index: int) -> str | None:
        """**给定**槽位表里第 ``bar_index`` 格的步骤 key；没有这一格返回 ``None``。

        ⚠️ 为什么要单独一个"吃 slots 的"版本：解析"旧步骤条的 ``_current``
        到底是哪一步"时，**不能**用 :meth:`flow_slots`（它读磁盘上那张图，
        而磁盘已经是**新**流程了），必须用**旧步骤条建时那份**槽位。
        """
        for slot in slots or ():
            if slot.bar_index == bar_index:
                return slot.step
        return None

    def _rebuild_step_bar(self) -> None:
        """按**当前任务流程**重建步骤条（BPM 驱动）。

        步骤条在 ``_init_ui`` 期间就建好了，那时还没有任务、只能按默认流程
        排；``set_task`` 拿到 ``task_id`` 后本任务可能是自定义流程（换了步骤
        顺序或把可选节点排到别处），这时重建一次，让步骤条与流程一致。

        ⚠️ 必须重建**而不是只改标题**：可选节点的位置
        （``optional_after``）决定布局插入点与连接线/绕行线的几何，改标题
        改不动它们。
        ⚠️ 重建会丢当前高亮与完成态，所以先把它们按**步骤 key** 存下来，
        重建后按新流程的格序恢复（换流程后某一步可能被删，匹配不上就回第
        一格——那里是流程的入口，缺上游也不该从中间起跑）。
        """
        old_bar = getattr(self, "step_bar", None)
        if old_bar is None:
            return
        # ⚠️ 先把**节点索引**（阶段→节点、按流程条顺序）建好再造步骤条：
        #    标题里的「（2）」这类序号由它算（``node_display_suffix``），晚一步
        #    就会退回"文件声明顺序"，用户看到第一个节点叫（2）（2026-10-17 实测）。
        self._rebuild_node_index()
        # ⚠️⚠️ **用旧步骤条自己记的那份槽位解析旧下标**（2026-10-06 用户报障
        #    "顶部流程图编辑后不立即更新"）。这里**不能**调 ``flow_slots()``：
        #    它读的是**磁盘上那张新流程图**，而 ``old_bar._current`` 是**旧
        #    流程**的格序——两者语义已经错位。实测：停在「图片去底色」（旧格序
        #    2），删掉「提取图片」后它在新流程里是格序 1，用新表查旧下标 2
        #    得到的是「图片拼版」⇒ 重建完高亮默默挪到了别的步骤上，用户看着
        #    就是"步骤条没更新"。完成态 ``_completed`` 同理（存的是旧格序）。
        old_slots = getattr(self, "_step_bar_slots", None)
        if not old_slots:
            # 没有记录（构造期的第一条）：退回按当前表解析，最坏退回第一格
            old_slots = self.flow_slots()
        current_step = self._step_key_at(old_slots, old_bar._current)
        completed_steps = [
            s.step
            for s in old_slots
            if not s.optional and s.bar_index in old_bar._completed
        ]
        # ⚠️ 先把旧步骤条从根布局里摘掉再换新的，否则两个步骤条叠在一起
        #    （旧控件还占着位置、只是被遮住，自测里的几何断言会全错）。
        #    ⚠️ 不能用 ``replaceWidget(old, None)``——传 None 给它会抛
        #    ``addLayoutOwnership`` 的 RuntimeError（Qt 不接受 None 接管布局项）。
        root = getattr(self, "_root_layout", None)
        if root is not None:
            root.removeWidget(old_bar)
            old_bar.setParent(None)
            old_bar.deleteLater()
        self.step_bar = self._build_step_bar()
        if root is not None:
            row = getattr(self, "_step_bar_row", 1)
            root.insertWidget(row, self.step_bar)
        for slot in self.flow_slots():
            if slot.optional or slot.step not in completed_steps:
                continue
            self.step_bar.mark_completed(slot.bar_index)
        if current_step is not None:
            # ⚠️ 优先按**上次停留的节点**恢复高亮（B 方案）：同一步骤有多个
            #    节点时，按 step key 恢复恒定回到第一个节点——用户看着的是
            #    副本节点，重建后高亮跳回主节点（"改了流程图位置就跳走了"）。
            index = None
            tid = self.task_id
            last_node = self.store.load_last_node(tid) if tid else None
            if last_node:
                for slot in self.flow_slots():
                    if slot.mapped and slot.node_id == last_node:
                        index = slot.bar_index
                        break
            if index is None:
                index = self.bar_index_of_step(current_step)
            self.step_bar.set_current(0 if index is None else index)

    def _select_optional_node(self) -> None:
        """点了「图片拼版」虚线节点 → 切到它在本流程里的那一格。"""
        index = self.bar_index_of_step(IMPOSITION_STAGE)
        if index is not None:
            self._select_stage(index)
