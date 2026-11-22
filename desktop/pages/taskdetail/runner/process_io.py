# -*- coding: utf-8 -*-
"""阶段子进程的启动、日志标签、输出路径与取消。"""

from __future__ import annotations

import sys
from desktop.steps.process import StageProcess, worker_arguments
from desktop.store.json_io import write_json
from desktop.utils.files import list_stage_images, project_root
from desktop.store import STAGE_LABELS
from ._qt import QProcess
from typing import TYPE_CHECKING, Any, Callable, cast

from .constants import STATUS_LABELS


class StageProcessMixin:
    """子进程传输层接线：启动、输出路径、取消。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _consume_worker_stderr: Any
        _logs: Any
        _mark_run_launched: Any
        _on_stage_finished: Any
        _on_stage_stalled: Any
        _on_stage_stdout: Any
        _on_stage_unclean_exit: Any
        _progress_belongs_here: Any
        _progress_ui_timer: Any
        _refresh_stage_views: Any
        _rembg_dirty: Any
        _rembg_ui_timer: Any
        _set_stage_status: Any
        _worker_error_occurred: Any
        current_node: Any
        log_panel: Any
        node_display_suffix: Any
        stage_progress: Any
        store: Any
        task_id: Any

    def _launch_stage_process(
        self, stage: str, args: dict, resume: bool = False
    ) -> None:
        """写入运行配置并启动 worker 子进程。"""
        # ⚠️ 调用前 _run_stage_unchecked 的输入守卫已保证有任务在身
        task_id = self.task_id
        assert task_id is not None, "启动步骤时没有任务在身"
        # ⚠️ 记下是**哪个节点**在跑（B 方案）：收尾时用户可能已经切到同一步骤的
        #    另一个节点，那时 ``current_node()`` 不再是"跑的那个"。
        node = self.current_node()
        self.running_node = node
        self.run_id = self.store.create_stage_run(
            task_id, stage, args, resume, node_id=node
        )
        runs_dir = self.store.runs_config_dir(task_id)
        runs_dir.mkdir(parents=True, exist_ok=True)
        config_path = runs_dir / f"run-{self.run_id}.json"
        write_json(
            config_path,
            {
                "task_id": self.task_id,
                "stage": stage,
                "run_id": self.run_id,
                "args": args,
            },
        )
        self.cancel_requested = False
        self.running_stage = stage
        self._last_error_line = None
        # 最近一次 progress 事件 (done, total)：worker 结束时不带计数，
        # 用它把最终进度落到历史记录里（见 _worker_finished）。
        self._last_progress = (0, 0)
        # 半行缓冲/进度合并都是**每次运行**的临时状态，别把上一次的残留带过来
        # （"无进展计时"的临时状态已随看门狗搬进传输层，不在这里）
        self._stdout_tail = ""
        self._progress_dirty = False
        self._progress_ui_timer.stop()
        # 上一轮攒着的 page_done 不能带进这一轮（会刷到同名但不同内容的页上）
        self._rembg_dirty.clear()
        self._rembg_ui_timer.stop()
        # 本步**自己**的活儿：立刻显示"执行中"并把进度归零 —— 第一个 progress
        # 事件到达之前（torch 冷启动可达数秒）不该继续挂着上一次的「成功 91/91」。
        # 跨步骤启动（在别的步骤点了按钮）则一个像素都不动：那一步的进度条与
        # 文案不该被这一步的活儿改写（见 _progress_belongs_here）。
        if self._progress_belongs_here(stage):
            self.stage_progress.setRange(0, 1)
            self.stage_progress.setValue(0)
            # 走 _set_stage_status 而不是 setText：颜色要跟着回到常规色，
            # 否则上一条"上游已重跑/版面已修改"的红字会留在「执行中」上
            self._set_stage_status(f"{STAGE_LABELS[stage]}：{STATUS_LABELS['running']}")
        if stage == "extract":
            self._extract_seen = len(
                list_stage_images(
                    self.store.node_or_stage_output(task_id, node, "extract")
                )
            )
        # ---- 传输层：起进程 + 读字节流 + 看门狗（实现见 desktop.steps.process）----
        # ⚠️ 这里只接"业务"需要的信号；半行重组 / JSON 解析 / 落盘仍在本页——
        #    它们写 runs.json、boxes.json 与日志视图，是**页面**的事，
        #    放进传输层会让那一层重新长出"任务流程"的触手、也就没法复用了。
        # 上一次运行的传输层已经收尾（能走到这里说明没有进程在跑），顺手回收，
        # 免得一场会话跑几十次就攒几十个对象。
        previous = getattr(self, "_stage_transport", None)
        if previous is not None:
            previous.deleteLater()
        transport = StageProcess(self)
        transport.stdout.connect(self._on_stage_stdout)
        transport.stderr.connect(self._consume_worker_stderr)
        transport.process_error.connect(self._worker_error_occurred)
        transport.stalled.connect(self._on_stage_stalled)
        transport.unclean_exit.connect(self._on_stage_unclean_exit)
        transport.finished.connect(self._on_stage_finished)
        self._stage_transport = transport
        self.process = transport.start(
            sys.executable,
            worker_arguments(config_path),
            # 打包环境主程序即入口，工作目录随意；源码环境必须是项目根
            # （能解析出 desktop 包的那一级）
            workdir=None if getattr(sys, "frozen", False) else project_root(),
        )
        # 进程真的起来了 → 防抖窗口从这里开始计时（见 _run_launched_at）
        self._mark_run_launched()

        self.store.update_task(task_id, "running")
        self._refresh_stage_views()
        # 开始执行时自动展开日志：用户此刻最需要看到实时输出
        self.log_panel.set_expanded(True)
        # ⚠️ 走 ``append_now``：先冲刷攒批再立刻写——这行是"用户此刻最想立刻
        #    看到"的（阶段起止），不许跟攒批行一起等窗口。见计划 A1。
        self._logs.append_now(
            f"=== 开始执行 {self._stage_log_label(stage)}"
            f"{'（续跑）' if resume else ''} ==="
        )

    def _stage_log_label(self, stage: str | None) -> str:
        """日志/提示里的这一步叫什么：同一步骤有多个节点时带上节点序号。

        ⚠️ 不带序号的话，日志里两条「=== 开始执行 图片去底色 ===」完全一样，
        用户没法判断刚才跑的是哪个节点（B 方案最直接的可用性代价就在这儿）。
        """
        label = STAGE_LABELS.get(stage or "", stage or "")
        node = self.running_node or self.current_node()
        suffix = self.node_display_suffix(node) if node else ""
        return f"{label}{suffix}"

    def _output_path_for(self, stage: str | None, node: str | None) -> str | None:
        """某阶段在某**节点**下的主产物路径（写进运行记录的 ``output_path``）。

        - ``print``：产物是 PDF，落点在 ``stages/print[~<节点>]`` 目录里；
        - ``detect``：GUI 只回坐标（不落盘），沿用旧的"参考缩略图目录"；
        - 其余：按节点取端口 ``pages`` 的落点（主节点 = 旧路径）。
        """
        if not stage or not self.task_id:
            return None
        if stage == "print":
            return str(self.store.scoped_stage_dir(self.task_id, node, "print"))
        if stage == "detect":
            # ⚠️ 标注图目录按**节点**取（B 方案）：同一步骤的多个「检测文本框」
            #    节点各自一份 thumbnails/detect[~<节点>]。
            return str(self.store.stage_output_dir(self.task_id, stage, node))
        try:
            return str(
                self.store.node_or_stage_output(self.task_id, node, stage)
            )
        except KeyError:
            return str(self.store.stage_output_dir(self.task_id, stage))

    def cancel_stage(self) -> None:
        """中断正在执行的阶段：先落 cancelled 再 kill 子进程。

        先立即把运行记录置为 cancelled——防止进程被强杀来不及回调时状态永远
        停留 running（重启后按钮状态错乱）；随后置 cancel_requested 并 kill。
        """
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.cancel_requested = True
            self._set_stage_status("正在中断步骤...")
            self._logs.append_now("已请求中断，正在终止步骤子进程...")
            # 立即把运行记录置为已中断：进程被强杀来不及回调时，
            # 状态不会永远停留在 "running"（否则重启后按钮状态是错的）
            # ⚠️ 有进程在跑必有任务在身（见 run_stage 的守卫）
            task_id = self.task_id
            assert task_id is not None, "中断步骤时没有任务在身"
            if self.run_id:
                self.store.finish_stage(task_id, self.run_id, "cancelled")
            self.process.kill()
            # kill 是 TerminateProcess：worker 里的 `finally`/`with` 都不会执行，
            # 「PDF排版」的效果图暂存目录（整页 PNG，几百 MB~GB）会留在 %TEMP%。
            # 这里立刻扫一次（按属主 pid 判死活），不等下一次生成 PDF 才回收。
            try:
                from desktop.stages import sweep_orphan_staging

                sweep_orphan_staging()
            except Exception:  # noqa: BLE001 - 回收是尽力而为，不能影响中断
                pass
