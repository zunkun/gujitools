# -*- coding: utf-8 -*-
"""聚合任务的成员产物汇集与定期刷新。"""

from __future__ import annotations

from desktop.workers import connect_queued
from typing import TYPE_CHECKING, Any, Callable, cast


class ManifestAggregateMixin:
    """聚合任务输入汇集（只搬产出，拼版例外）。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _toast: Any
        run_worker: Any
        set_task: Any
        store: Any

    # ------------------------------------------------------- 补选源 PDF
    def _is_aggregate_task(self) -> bool:
        """本任务是不是**聚合任务**（输入来自成员产物，不是用户上传的文件）。

        聚合任务（用户 2026-11-17）没有源 PDF、也不该催用户"上传图片/文件夹"
        ——它的输入是创建时按成员顺序汇集进来的（见
        :mod:`desktop.services.aggregate_ingest`）。凡是"缺输入该提醒什么"
        的判据都先问这一句。
        """
        task_id = getattr(self, "task_id", None)
        if not task_id:
            return False
        try:
            record = self.store.get_task(task_id) or {}
        except Exception:  # noqa: BLE001 - 读不到就按普通任务处理
            return False
        return record.get("kind") == "aggregate"

    def _aggregate_pending(self) -> bool:
        """聚合任务的成员产物**还在汇集**（后台正在复制）。"""
        task_id = getattr(self, "task_id", None)
        if not task_id or not self._is_aggregate_task():
            return False
        from desktop.services.aggregate_ingest import is_pending

        try:
            return is_pending(self.store.task_dir(task_id))
        except (OSError, ValueError):
            return False

    def refresh_aggregate_inputs(self) -> None:
        """页头按钮：**重新汇集**成员产物（成员后来重跑过某一步时用）。

        聚合任务的输入与产出是"创建那一刻"的**快照**（按成员顺序复制，见
        :mod:`desktop.services.aggregate_ingest`）。成员重跑之后这份快照就
        过期了，而聚合任务的成员/顺序是创建时定的——没有这个入口，用户只能
        删掉聚合任务重选一遍成员。

        ⚠️ 会**覆盖**聚合任务现有的输入/产出（只动 ``NNN_`` 前缀的文件与
        起点那条合成记录），所以先弹确认框；确认后整套搬运在后台跑。
        """
        task_id = getattr(self, "task_id", None)
        if not task_id or not self._is_aggregate_task():
            return
        if self._aggregate_pending():
            self._toast("info", "正在汇集", "上一次汇集还没结束，请稍候。")
            return
        from desktop.ui.confirm_dialog import ConfirmDialog

        record = self.store.get_task(task_id) or {}
        members = "、".join(str(m) for m in (record.get("members") or []))
        dialog = ConfirmDialog(
            "重新汇集聚合输入",
            f"将按当前成员顺序（{members}）重新复制各成员在起始节点上的"
            "输入与产出。聚合任务里已有的输入/产出会被覆盖，起点节点重新记为"
            "「已完成」（PDF排版起点除外：它的输出由本任务现场执行生成）。",
            self,
            yes_text="重新汇集",
        )
        if not dialog.exec():
            return
        self._run_aggregate_refresh(task_id)

    def restart_aggregate_ingest(self, task_id: str) -> bool:
        """**已经确认过**要重取数时直接开工（不弹确认框，返回是否真起了）。

        供流程页"改了起始节点"用（用户 2026-11-18）：起点一变，旧起点汇集的
        输入与处理结果就作废了，必须立刻按新起点重取一遍——否则详情页那一步
        永远没有数据，用户还得自己去点页头那颗 ⟳。

        ⚠️ 不做确认：调用方（``TaskFlowPage._on_done``）已经弹过"历史数据
        作废"的确认框，这里再问一次就是重复打扰。
        """
        if not task_id:
            return False
        if getattr(self, "task_id", None) != task_id:
            return False
        if not self._is_aggregate_task():
            return False
        if self._aggregate_pending():
            self._toast("info", "正在汇集", "上一次汇集还没结束，请稍候。")
            return False
        self._run_aggregate_refresh(task_id)
        return True

    def _run_aggregate_refresh(self, task_id: str) -> None:
        """真正启动重新汇集（不含确认框；自测直接调这一层）。"""
        from desktop.services.aggregate_ingest import set_pending_marker
        from desktop.workers import AggregateIngestWorker

        try:
            set_pending_marker(self.store.task_dir(task_id), True)
        except (OSError, ValueError):
            pass
        worker = AggregateIngestWorker(self.store, task_id)

        def wire(w, thread) -> None:
            connect_queued(
                self, w.finished,
                lambda *_: self._on_aggregate_refreshed(task_id), thread,
            )
            connect_queued(
                self, w.failed,
                lambda _tid, msg: self._on_aggregate_refresh_failed(msg), thread,
            )
            w.finished.connect(thread.quit)
            w.failed.connect(thread.quit)

        self.run_worker(lambda: worker, wire)

    def _on_aggregate_refreshed(self, task_id: str) -> None:
        """重新汇集完成：提示并就地重载（页面清单/步骤状态全换新）。"""
        self._toast(
            "success", "聚合输入已重新汇集",
            "各成员在起始节点上的输入与产出已按当前顺序重新复制。",
        )
        if getattr(self, "task_id", None) == task_id:
            self.set_task(task_id)

    def _on_aggregate_refresh_failed(self, message: str) -> None:
        self._toast("error", "重新汇集失败", message)
