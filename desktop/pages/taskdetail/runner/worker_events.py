# -*- coding: utf-8 -*-
"""worker 事件消费：stdout 半行缓冲、progress / page_done、去底色反馈。"""

from __future__ import annotations

import json
from desktop.store import STAGE_LABELS
from ._qt import QObject, QTimer
from typing import TYPE_CHECKING, Any, Callable, cast


class WorkerEventsMixin:
    """worker 事件消费。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _REMBG_UI_MS: Any
        _consume_worker_stderr: Any
        _logs: Any
        _progress_belongs_here: Any
        _progress_ui_timer: Any
        _set_stage_status: Any
        _store_page_size: Any
        _store_stage_boxes: Any
        _worker_finished: Any
        current_node: Any
        current_stage: Any
        running_node: Any
        running_stage: Any
        stage_progress: Any
        store: Any
        task_id: Any

    # ---------------------------------------------------------- 输出解析
    def _on_stage_stdout(self, data: bytes) -> None:
        """传输层转来一批 stdout 原始字节：交给解析层（半行重组在这里）。

        ⚠️ "有输出就算有进展"的计时与提醒标志由传输层维护（见
        ``StageProcess._on_stdout``）——那是看门狗自己的状态。
        """
        self._consume_worker_stdout(data)

    def _on_stage_stalled(self, minutes: float) -> None:
        """传输层报"很久没有任何输出"：写日志 + 状态行（只提醒，不自动杀）。

        ⚠️ 为什么只提醒不自动杀（2026-09-26 审计）：worker 卡死（死锁、等
        常驻 YOLO 服务、torch 卡住、管道反压）与**合法的慢阶段**（2400 页的
        去底色/生成 PDF）在外部看是一样的——都只是"没输出"。自动杀掉会把
        用户跑了几分钟的正常任务误杀，代价远大于收益。所以这里只把
        "已经 N 分钟没有任何进展"摆到用户面前，让**他**决定要不要关窗重试。
        """
        self._logs.append(
            f"[看门狗] 已 {minutes:.0f} 分钟没有任何进度输出，"
            "若确认卡住可关闭窗口后重试。"
        )
        self._set_stage_status(f"已 {minutes:.0f} 分钟无进展（可能卡住，可关窗重试）")

    def _on_stage_unclean_exit(self) -> None:
        """传输层报"进程已退出但 Qt 没能正常收尾"：记成失败原因（看门狗兜底）。"""
        self._logs.append("[看门狗] 步骤子进程已退出但未正常收尾，按失败处理")
        self._last_error_line = "步骤子进程未正常收尾（看门狗兜底）"

    def _on_stage_finished(self, exit_code: int, status) -> None:
        """传输层报"进程结束"（**保证只发一次**）→ 走页面收尾链。"""
        self._worker_finished(exit_code, status)

    def _consume_worker_stdout(self, data: bytes, final: bool = False) -> None:
        """解析 worker 输出的 JSON Lines 事件。

        ``final=True`` 用于收尾的最后一次读取：此时把残留的半行也当完整行
        处理，别让它永远留在缓冲区里。

        ⚠️ **必须做半行重组**：管道读取会在任意字节处截断，一条 JSON 事件被劈成
        两半时 ``json.loads`` 必然失败、整条事件被降级成"人读日志"丢掉 ——
        表现就是"进度偶尔少一条"。所以留一个尾巴，等下一批字节拼回来。
        """
        text = self._stdout_tail + data.decode("utf-8", errors="replace")
        if final:
            self._stdout_tail = ""
            lines = text.splitlines()
        else:
            lines = text.split("\n")
            tail = lines.pop()  # 末段可能不完整，留给下一批
            # ⚠️ 只有「看起来是半条 JSON 事件」的余量才值得留到下一批拼回来。
            # 协议外的裸 print（没有换行的库输出）一旦被留下，下一条真正的事件
            # 会被拼到它后面、一起解析失败 —— 那就从"丢半条"变成"丢一条"。
            # 所以非 JSON 的余量立刻当人读日志收掉。
            if tail and not tail.lstrip().startswith("{"):
                if tail.strip():
                    self._logs.append(tail)
                tail = ""
            self._stdout_tail = tail
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # 非 JSON 行：worker 侧已用 ProgressStream 拦下大部分库输出，
                # 这里是最后的兜底（协议外的裸 print / 半行撕裂）。当日志收下，
                # 总比静默丢掉让用户「日志里什么都没有」要好。
                if line.strip():
                    self._logs.append(line)
                continue
            etype = event.get("type")
            if etype == "progress":
                self._on_worker_progress(event)
            elif etype == "log":
                self._logs.append(event.get("message", ""))
            elif etype == "page_boxes":
                self._store_stage_boxes(event)
            elif etype == "page_size":
                self._store_page_size(event)
            elif etype == "page_done":
                self._on_worker_page_done(event)
            elif etype == "started":
                self._logs.append(
                    f"步骤子进程已启动：{STAGE_LABELS.get(event.get('stage'), event.get('stage'))}"
                )
            elif etype == "error":
                # ⚠️ 结构化 error 事件是 worker 侧**最准确的失败原因**（stage 自己发的，
                # 比 stderr 里那行启发式匹配可靠）。必须同时记进 _last_error_line：
                # 只写日志的话，历史记录与失败弹窗只会显示「退出码 1」，真因
                # （比如"没有生成任何图片"）被淹在日志里，
                # 用户事后完全查不到（2026-09-26 审计发现）。
                message = event.get("message") or ""
                self._logs.append_now(f"错误：{message}")
                if message.strip():
                    self._last_error_line = message.strip()
            elif etype == "cancelled":
                self._logs.append_now("步骤子进程已被中断。")

    def _on_worker_page_done(self, event: dict) -> None:
        """一条 ``page_done``：该页产物已落盘 → 攒进脏集合，节流刷界面。

        ⚠️ 只对**去底色**有用：其它步骤的每页产物要么不直接上屏（extract 由
        ``_poll_extract_results`` 轮询），要么根本没有逐页预览（detect 走
        ``page_boxes``）。这里按 ``running_stage`` 过滤，不猜事件来源。
        """
        if self.running_stage != "rembg":
            return
        source = str(event.get("source") or "")
        if not source:
            return
        self._rembg_dirty.add(source)
        if not self._rembg_ui_timer.isActive():
            self._rembg_ui_timer.start()

    def _init_rembg_feedback(self) -> None:
        """建去底色阶段反馈的攒批器（宿主页面 __init__ 里调一次）。"""
        #: 本轮执行里**结果刚落盘**的源路径（攒批后一次刷可见行）
        self._rembg_dirty: set[str] = set()
        self._rembg_ui_timer = QTimer(cast("QObject", self))
        self._rembg_ui_timer.setSingleShot(True)
        self._rembg_ui_timer.setInterval(self._REMBG_UI_MS)
        self._rembg_ui_timer.timeout.connect(self._flush_rembg_feedback)

    def _flush_rembg_feedback(self) -> None:
        """攒批到期：把刚落盘的几页刷到界面（只刷看得见的行）。

        只在**当前看的就是去底色**时刷：在别的步骤上刷新一个隐藏控件纯属
        白花 CPU；切回去时 ``_refresh_preview`` 会整条重装，漏不掉。
        """
        changed = self._rembg_dirty
        self._rembg_dirty = set()
        if not changed or not self.task_id:
            return
        if self.current_stage() != "rembg":
            return
        viewer = getattr(self, "rembg_viewer", None)
        if viewer is None:
            return
        if viewer.result_dir is None:
            # 结果目录与 run_stage 的 rembg 分支同一份规则（取**正在跑**的节点）
            try:
                viewer.set_result_dir(
                    self.store.node_or_stage_output(
                        self.task_id, self.running_node or self.current_node(),
                        "rembg",
                    )
                )
            except Exception:  # noqa: BLE001 - 反馈是旁路，不能拖垮执行
                return
        viewer.refresh_running_results(changed)

    def _on_worker_progress(self, event: dict) -> None:
        """一条 progress 事件：轻量部分即时上屏，重活按窗口合并。

        ⚠️ 只有**当前显示这一步**自己的进度才上屏（见 :meth:`_progress_belongs_here`）：
        共享的进度条/文案被跨步骤的进度写进去，就会让人以为"这一步在跑"。
        """
        done, total = event.get("done", 0), event.get("total", 0)
        if total and self._progress_belongs_here(event.get("stage")):
            self.stage_progress.setRange(0, total)
            self.stage_progress.setValue(min(done, total))
            self._set_stage_status(f"进度 {done}/{total}")
        # 记住最近一次进度：finish_stage 用它补齐最终计数（见 _worker_finished）
        self._last_progress = (done, total)
        # 写运行记录 / 重建步骤条 / 重建提取结果缩略图条都是重活，见 _PROGRESS_UI_MS
        self._progress_dirty = True
        if not self._progress_ui_timer.isActive():
            self._progress_ui_timer.start()

    def _drain_worker_output(self, proc) -> None:
        """收尾前把管道余量读干（含最后那条不完整的行）。

        ⚠️ 唯一调用点是 :meth:`_worker_finished`，且**必须在清 ``self.process`` /
        ``self.run_id`` 之前**：这两个引用一清，后面到达的事件就再也进不了日志
        与运行记录（大任务时 GUI 本来就落后，管道里常常还压着一批事件）。
        """
        try:
            self._consume_worker_stdout(bytes(proc.readAllStandardOutput()), final=True)
            self._consume_worker_stderr(bytes(proc.readAllStandardError()))
        except RuntimeError:
            pass  # 底层对象已析构（进程被强行收掉）
        # ⚠️ 排空后立刻冲刷日志攒批：管道里最后一批事件刚写进合并器，剩下的
        #    收尾日志（"页面清单已刷新"等）若直接走 log_view 就会**插到它们前面**，
        #    日志顺序看着是乱的。所以这里先把攒批落笔再继续收尾（见计划 A1）。
        self._logs.flush()
