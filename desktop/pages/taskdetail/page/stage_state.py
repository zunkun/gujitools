# -*- coding: utf-8 -*-
"""任务详情页的阶段状态：槽位状态、步骤条刷新、「上游已过期」提示。"""

from __future__ import annotations

import time
from desktop.services.stale_chain import stale_upstream
from desktop.store import IMPOSITION_LABEL, IMPOSITION_STAGE, STAGE_LABELS
from desktop.ui import theme as T
from desktop.ui.widgets import apply_to
from desktop.pages.taskdetail.runner import STATUS_LABELS
from typing import TYPE_CHECKING, Any


class StageStateMixin:
    """阶段状态计算与刷新（步骤条 / 过期提示 / 重新生成提示）。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _aggregate_pending: Any
        _input_node_mode: Any
        _own_step_running: Any
        _print_source_mark_text: Any
        _slot_at_index: Any
        _update_run_buttons: Any
        current_stage: Any
        flow_slots: Any
        imposition_effective: Any
        print_source_stage: Any
        stage_progress: Any
        stage_status: Any
        step_bar: Any
        store: Any
        task_id: Any

    #: 状态缺失时的兜底（"这一步还没跑过"）——**不借别的节点/阶段的状态**：
    #: 同一步骤两个节点各跑各的，借来就是"B 看着已完成、其实从没跑过"。
    _PENDING_STATE = {
        "status": "pending", "done": 0, "total": 0, "completed": False,
        "in_flow": True,
    }

    def _slot_state(self, slot, node_states: dict, stage_states: dict) -> dict:
        """某个**界面格**当前该显示的状态（B 方案：按节点取，单节点时 = 旧口径）。

        - 这一格有节点 ⇒ 取 :meth:`~desktop.store.runs.RunMixin.node_states`
          里**该节点**的状态；该节点没有记录就是"还没跑过"（pending），
          **绝不回落**该阶段的状态——那会把同一步骤里另一个节点跑出的"成功"
          显示到这个从没跑过的节点上；
        - 这一格没有节点（老模型投影 / 未接入节点）⇒ 退回阶段状态。
        """
        if slot.node_id:
            return node_states.get(slot.node_id) or dict(self._PENDING_STATE)
        return stage_states.get(slot.stage) or dict(self._PENDING_STATE)

    def _refresh_stage_views(self) -> None:
        if not self.task_id:
            return
        # 换步骤/跑完都可能换掉"这一步是不是聚合输入节点"的答案：先作废缓存
        # （``_input_node_mode`` 里说明为什么需要缓存）
        self._input_node_cached = None
        stage_states = self.store.stage_states(self.task_id)
        # ⚠️ 一次读全（runs.json）：逐槽位问 store 会把整份文件读 N 遍。
        node_states = self.store.node_states(self.task_id)
        self.step_bar.reset_statuses()
        # ⚠️ 按**槽位表**刷而不是 ``enumerate(STAGES)``：步骤条上的格序来自
        #    本任务流程（BPM 驱动），自定义流程换了顺序，状态要刷到对应那一格；
        #    可选节点（拼版）没有 runs 状态，跳过（它在下方单独给状态行文案）。
        # ⚠️ 同一步骤的多个节点**各刷各的**（B 方案）：一格一个节点，状态/进度/
        #    打勾都按该节点自己的运行记录来（:meth:`_slot_state`）。
        for slot in self.flow_slots():
            if slot.optional or not slot.mapped:
                continue
            state = self._slot_state(slot, node_states, stage_states)
            progress = (state["done"], state["total"]) if state["total"] else None
            # 步骤条只表达"第几步 / 执行到哪"：completed 决定徽标是否打勾，
            # status 决定副标题文案与颜色（重试失败不会让已完成步骤退回未完成）
            self.step_bar.set_step_status(
                slot.bar_index, state["status"], progress,
                completed=state["completed"],
            )
        stage = self.current_stage()
        if stage == IMPOSITION_STAGE:
            # 「图片拼版」伪步骤在 runs.json 里没有状态可读；执行按钮组也
            # 整体隐藏（见 _select_imposition_detail），这里只给状态行文案。
            self._set_stage_status(
                "图片拼版：可选节点（勾选「在流程中启用图片拼版」后，"
                "PDF排版使用拼版结果）"
            )
            return
        slot = self._slot_at_index(self.step_bar._current)
        state = (
            self._slot_state(slot, node_states, stage_states)
            if slot is not None and slot.mapped
            else stage_states[stage]
        )
        self._apply_stage_state(stage, state)
        if self._input_node_mode():
            # 输入节点说清楚"为什么不给执行按钮"，别让人以为界面坏了
            if self._aggregate_pending():
                self._set_stage_status(
                    "正在汇集子任务产物……清单会随复制进度陆续补全"
                )
            else:
                self._set_stage_status(
                    "输入节点：图片由子任务汇集而来，无需执行（直接看左侧清单）"
                )
        self._update_run_buttons()

    def _slot_of_node(self, node_id: str | None):
        """节点 id → 它在步骤条上占的那一格（没有对应格返回 ``None``）。"""
        if not node_id:
            return None
        for slot in self.flow_slots():
            if slot.mapped and slot.node_id == node_id:
                return slot
        return None

    def _apply_stage_state(self, stage: str, state: dict) -> None:
        if self._own_step_running():
            # 本步自己的活儿正在跑：进度条与文案此刻归 _on_worker_progress 所有。
            # 这里若照旧刷成"上一次运行"的 done/total，就会和进度文案每 200ms
            # 互相覆盖一次（状态文字来回跳，看着像卡住）。跑完 running_stage
            # 清空，下一次刷新自然回到真实状态。
            return
        total, done = state["total"], state["done"]
        if total:
            self.stage_progress.setRange(0, total)
            self.stage_progress.setValue(min(done, total))
        else:
            self.stage_progress.setRange(0, 1)
            self.stage_progress.setValue(0)
        # 「产物需要重新生成」优先于"最近一次的结果"：改了版面、或上游又跑过
        # 一次之后，再显示「成功」会误导（用户看着"成功"就把旧产物发出去了）
        notice = self._regenerate_notice(stage)
        if notice:
            self._set_stage_status(notice, alert=True)
        else:
            self._set_stage_status(
                f"{STAGE_LABELS[stage]}："
                f"{STATUS_LABELS.get(state['status'], state['status'])}"
            )

    def _set_stage_status(self, text: str, alert: bool = False) -> None:
        """写状态行文案，并选颜色：``alert=True`` 用警示色（红），否则常规柔和色。

        ⚠️ 颜色必须在这里**一起**写：状态行是同一个 QLabel，被三处抢着用
        （常规状态 / 版面已修改 / 上游已重跑）。只改文字不重置颜色，就会出现
        "过期提示的红字留在下一次的常规状态上"。
        """
        self.stage_status.setText(text)
        apply_to(
            self.stage_status, T.SIZE_CAPTION,
            color=T.DANGER if alert else T.INK_SOFT,
        )

    # ---------------------------------------------------- 上游重跑 → 产物过期
    def _refresh_stale_notices(self) -> None:
        """重算"上游比本步新"与"取图来源已换"的判定缓存。

        ⚠️ 只在**运行收尾**、**切任务**、**拼版开关变化**时调，别放进
        ``_refresh_stage_views`` 的热路径：判定要读整份 runs.json，而那里运行期
        每 ≤200ms 就跑一次。
        """
        self._print_source_stale = False
        #: 取图目录的**内容**变了（拼版成品重存 / 去底色成品被实时改写）：
        #: 磁盘上那份 PDF 同样是旧数据，见 ``_regenerate_notice`` 第 3 条。
        self._print_data_stale = False
        if not self.task_id:
            self._stale_notices = {}
            return
        # 一次读全（五个阶段逐个 list_stage_runs 会把 runs.json 读五遍）
        runs = self.store.all_stage_runs(self.task_id)
        # ⚠️ 上游链**按本任务的流程图算**，不用写死的那张表：用户加/删/换了步骤
        #    之后，写死的链会指错上游（提示"上游已重新执行"却指到不相干的步骤），
        #    或者漏掉真正影响它的那一步。
        from desktop.services.stale_chain import upstream_from_diagram

        self._stale_notices = stale_upstream(
            runs, upstream_from_diagram(self.store.task_diagram(self.task_id))
        )
        # 取图来源是否已换（拼版开关）——同一份 runs.json 顺手算掉，不额外读盘
        try:
            from desktop.services.stale_chain import (
                print_input_changed,
                print_source_switched,
            )

            self._print_source_stale = print_source_switched(
                runs, self.print_source_stage()
            )
            # 来源阶段没换、但取图目录内容变了（拼版删页 ⇒ 成品页重新编号重存）：
            # 磁盘上那份 PDF 同样是旧数据，判据见 services.stale_chain。
            self._print_data_stale = print_input_changed(
                runs, self._print_source_mark_text()
            )
        except Exception:  # noqa: BLE001 - 判定失败不该拦住界面刷新
            self._print_source_stale = False
            self._print_data_stale = False

    def _regenerate_notice(self, stage: str) -> str | None:
        """本步产物"需要重新生成"的提示文案（没有则 None）。

        三种来源，顺序即优先级：

        1. 第四步的逐图坐标刚被版面编辑器改过（``_print_dirty``）——用户的直接
           改动，最该被看见；
        2. **取图来源换了**（``_print_source_stale``）——勾上/取消「图片拼版」
           之后，磁盘上那份 PDF 是上一轮来源的产物，旧数据不该再被当成结果；
        3. **取图目录的内容变了**（``_print_data_stale``）——拼版里删/排一页会让
           成品页重新编号重存，来源阶段没换但图片全变了，那份 PDF 同样是旧数据
           （用户 2026-10-22：「拼版里删了一张图片，然后 PDF排版那里那一页还在」）；
        4. **上游重新执行过**（``services/stale_chain`` 的时间戳链）——本步产物是
           那之前生成的，可能已经不是最新参数下的结果。

        ⚠️ 第 2/3 条读**缓存**（``_print_source_stale`` / ``_print_data_stale``）
        而不是现算：本方法经 ``_refresh_stage_views`` 在执行期间每 ≤200ms 被拉
        一次，而现算要读 runs.json + 拼版文档 + 目录指纹。缓存由
        :meth:`_refresh_stale_notices` 在切任务/运行收尾、以及拼版开关变化时
        重算（见 ``imposition._refresh_print_source``）。
        """
        if stage == "print":
            if getattr(self, "_print_dirty", False):
                return "● 版面已修改，点击「生成PDF」生效"
            if getattr(self, "_print_source_stale", False):
                # ⚠️ 认 effective：图里没这一格时来源确实已回到去底色，
                #    这里必须跟着说"去底色"而不是说"拼版"（否则界面与执行打架）
                where = (
                    IMPOSITION_LABEL if self.imposition_effective()
                    else "去底色"
                )
                return f"● 取图来源已改为{where}，请重新「生成PDF」"
            if getattr(self, "_print_data_stale", False):
                return "● 取图里的图片已更新，请重新「生成PDF」"
        info = (self._stale_notices or {}).get(stage)
        if not info:
            return None
        label = STAGE_LABELS.get(info["stage"], info["stage"])
        when = time.strftime("%H:%M", time.localtime(info["upstream_at"]))
        return (
            f"● 上游已重新执行（{label} · {when}），"
            "本步产物可能已过期，请重新生成"
        )
