# -*- coding: utf-8 -*-
"""任务详情页的阶段执行控制器：构建参数、启动 worker 子进程、解析进度日志。

纯业务派生规则见 desktop/services/print_plan.py，
rembg 提交控制器见 desktop/pages/taskdetail/submit.py，
历史配置回填见 desktop/pages/taskdetail/history.py。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer

from desktop.services.print_plan import missing_extract_pages_spec
from desktop.store.json_io import write_json
from desktop.utils.files import list_stage_images, project_root
from desktop.store import STAGE_LABELS, STAGE_STEP

STATUS_LABELS = {
    "pending": "未执行",
    "running": "执行中",
    "success": "成功",
    "failed": "失败",
    "cancelled": "已中断",
}


class StageRunnerMixin:
    """依赖宿主页面提供的属性：store/task_id/source_path/pages、
    control_stack、stage_* 控件、log_view、process/run_id 等。"""

    #: 进度事件的**界面刷新合并窗口**(ms)。
    #:
    #: ⚠️ 为什么必须合并：extract 每渲染完一页就发一条 progress 事件，一本 100 页
    #: 的书就是 100 条。每条都去做「写 runs.json + 重建步骤条 + 重建提取结果缩略图
    #: 条」是几十毫秒级的重活（实测 GUI 每秒只吃得下十几条），GUI 于是远远落在
    #: worker 后面。后果有两个：界面明显发卡；更严重的是**进程退出时管道里还压着
    #: 一大批没读的事件**，收尾时被一并丢掉 —— 历史里留下「成功 done=14/total=84」、
    #: 日志缺「处理完成」那行，用户看到的就是"像被中断了/只提取了一半"。
    #: 进度条与状态文字仍逐条即时更新（纯内存操作，便宜）。
    _PROGRESS_UI_MS = 200

    def _init_progress_ui(self) -> None:
        """建进度刷新节流器（宿主页面 __init__ 里调一次，须在 _init_ui 之后）。"""
        self._progress_ui_timer = QTimer(self)
        self._progress_ui_timer.setSingleShot(True)
        self._progress_ui_timer.setInterval(self._PROGRESS_UI_MS)
        self._progress_ui_timer.timeout.connect(self._flush_progress_ui)
        self._progress_dirty = False

    def _flush_progress_ui(self) -> None:
        """把合并掉的进度落盘并刷新步骤条 / 提取结果（收尾时也必须调一次）。"""
        if self._progress_ui_timer.isActive():
            self._progress_ui_timer.stop()
        if not self._progress_dirty:
            return
        self._progress_dirty = False
        if self.task_id and self.run_id:
            done, total = self._last_progress
            if total:
                self.store.set_progress(self.task_id, self.run_id, done, total)
        self._refresh_stage_views()
        if self.running_stage == "extract":
            self._poll_extract_results()

    # ---------------------------------------------------- 进度该显示在哪一步
    def _step_of_stage(self, stage: str | None) -> str | None:
        """运行阶段 → 它归属的界面步骤（``rembg_submit`` 归第三步，见 STAGE_STEP）。"""
        if not stage:
            return None
        return STAGE_STEP.get(stage, stage)

    def _progress_belongs_here(self, stage: str | None) -> bool:
        """这条进度是否该画在**当前显示的这一步**上。

        ⚠️ 进度条与状态文字是**全页面共享**的一份控件，必须只服务当前这一步。
        以前无条件更新，于是第三步「提交本次任务」的进度被画在第四步的界面上：
        走动的进度条 +「进度 42/91」+ 灰掉的「生成PDF」按钮 —— 看起来就像第四步
        在自己生成 PDF（用户报的「在第三步提交，然后进第四步，pdf 在生成过程中」）。

        跨步骤的进度一律不上屏：想知道它还在跑，看「中断」按钮点得亮、日志在滚。
        """
        return self._step_of_stage(stage) == self.current_stage()

    def _own_step_running(self) -> bool:
        """当前这一步**自己**的活儿是否正在跑。

        此时进度条与状态文案归 :meth:`_on_worker_progress` 所有，别的路径
        （``_apply_stage_state``）不许再写，否则两者每 200ms 互相盖一次，
        状态文字来回跳。
        """
        return (
            self.running_stage is not None
            and self._step_of_stage(self.running_stage) == self.current_stage()
        )

    # ---------------------------------------------------------- 执行/中断
    def run_stage(self, resume: bool = False) -> None:
        """启动当前阶段的 worker 子进程（带执行权守卫，防连点起两个）。

        ⚠️ 守卫必须包在**最外层**：下面要做参数校验、effects 组装、写运行配置，
        这些都是同步重活，做完才 ``QProcess.start()``。若只在 start 之前判断
        ``self.process``，那段时间它还是 None，连点第二下就能再起一个 worker，
        两个 torch 同时加载、同时写同一批输出目录。

        守卫由 :meth:`TaskDetailPage._acquire_run` 提供（受理标记 + 防抖窗口）；
        真正干活的是 :meth:`_run_stage_unchecked`。
        """
        if not self._acquire_run("子任务"):
            return
        try:
            self._run_stage_unchecked(resume)
        finally:
            # ``running_stage`` 仍是 None 说明这次受理没落到进程上（参数错、
            # 无输入、无需续跑…）——立刻释放，否则按钮会一直灰着没人来解锁。
            # 一旦进程起来了，生命周期改由 _worker_finished 释放。
            if self.running_stage is None:
                self._release_run()

    def _run_stage_unchecked(self, resume: bool = False) -> None:
        """启动当前阶段的 worker 子进程（不含执行权守卫，勿直接调用）。

        resume=True 表示续跑：extract 只补缺失页、其余阶段跳过已有输出，
        否则 clean=True 全量重跑。会取面板参数、写运行配置、起子进程并连接
        输出/错误/完成信号，再挂看门狗兜底 Windows 偶发的 finished 丢失。
        """
        if not self.task_id or not self.source_path:
            self._toast("warning", "提示", "请先导入 PDF")
            return
        if self.process and self.process.state() != QProcess.NotRunning:
            self._toast("warning", "任务进行中", "当前子任务正在执行")
            return
        stage = self.current_stage()
        task = self.store.get_task(self.task_id)
        if not task:
            self._toast("error", "任务不存在", "该任务可能已被删除，请返回列表刷新。")
            return
        if stage == "extract" and not Path(self.source_path).exists():
            # self.source_path 已是任务目录里的备份（见 page.set_task）
            self._toast(
                "error", "PDF 缺失", f"任务备份 PDF 不存在：{self.source_path}"
            )
            return

        panel = self.control_stack.currentWidget()
        try:
            args = panel.get_args()
        except ValueError as exc:
            self._toast("error", "参数错误", str(exc))
            return
        if stage == "extract":
            args["input"] = str(self.source_path)
            args["output"] = str(self.store.stage_dir(self.task_id, "extract"))
            if resume:
                missing = missing_extract_pages_spec(
                    self.store.extract_output_dir(self.task_id),
                    self.pdf_page_count or 0,
                )
                if not missing:
                    self._toast("info", "无需续跑", "提取输出已完整。")
                    return
                args["pages"] = missing
                args["clean"] = False
        elif stage == "print":
            # print：左侧列表顺序即 PDF 页序。图片以第三步「生成预览」的
            # 去底图（stages/rembgpreview）为源，按第三步面板**当前**的
            # area/border + 检测框在 worker 子进程内实时合成（与「提交本次
            # 任务」完全相同的几何规则）——调整 border 后无需重新提交，
            # 直接生成 PDF 即可生效；第四步的纸张/边距/标题/页码等自定义
            # 参数继续传给 CLI print。
            entries, doc = self._print_entries()
            entries = [e for e in entries if Path(e["file"]).exists()]
            rembg_panel = self.control_stack.widget(2)  # 第三步 rembg 面板
            try:
                rargs = rembg_panel.get_args()
            except ValueError as exc:
                self._toast("error", "第三步参数错误", str(exc))
                return
            area = int(rargs.get("area", 1))
            border = rargs.get("border")
            effects = self._build_print_effects(entries, area, border)
            # 第三步 border 级联第四步默认边距：把上游 border 透传给 print，
            # 让其「通用边距默认」在 border 非 0 时回落为 0（避免双重留白）。
            args["upstream_border"] = border
            if not effects:
                self._toast(
                    "warning", "无输入页面",
                    "待打印列表为空，请先在第三步「生成预览」（必要时「提交"
                    "本次任务」选页），或在左侧列表插入图片。",
                )
                return
            doc["pages"] = [
                (
                    {"file": e.get("file"), "label": e.get("label"),
                     "rect": e["rect"]}
                    if e.get("rect") is not None
                    else {"file": e.get("file"), "label": e.get("label")}
                )
                for e in entries
            ]
            self.store.save_print_doc(self.task_id, doc)
            args["_effects"] = effects
            # 有序清单即页序：拖拽重排只改 print.json，不再物化任何文件。
            # input 仅供 CLI 作默认目录兜底，实际顺序由 files 决定。
            args["files"] = [str(Path(e["file"])) for e in entries]
            # 逐图坐标覆盖：把版面编辑器里记录的 rect 按 1-based 页序注入，
            # 生成 PDF 时直接作图片框（所见即所得），未编辑的页走自动排版。
            page_rects = {
                i + 1: list(e["rect"])
                for i, e in enumerate(entries)
                if e.get("rect") is not None
            }
            if page_rects:
                args["page_rects"] = page_rects
            args["input"] = str(self.store.task_dir(self.task_id))
            args["output"] = str(self.store.stage_dir(self.task_id, "print"))
            # 开始重新生成即清除「版面已修改」标脏
            self._print_dirty = False
            try:
                # ⚠️ 必须走 _set_stage_status（不能只 setText）：状态行是同一个
                # QLabel 被三处共用，只改文字不重置颜色的话，上一条"过期提示"的
                # 红字会留在这里（见 page.py::_set_stage_status）。
                self._set_stage_status("未执行")
            except Exception:
                pass
            self.log_view.append(
                f"区域合成：区域模式={area}"
                + (f"，边距={border}" if border is not None else "，边距=0")
                + f"（{len(effects)} 页）"
            )
        else:
            self._refresh_manifest()
            if not self._manifest_paths():
                self._toast(
                    "warning", "无输入页面",
                    "页面清单为空，请先完成上一步子任务，或在预览区插入图片。",
                )
                return
            # detect/rembg 都是逐图独立处理（不依赖顺序与命名），直接以
            # extract 输出目录为输入，不再物化 workset 副本。
            args["input"] = str(self.store.extract_output_dir(self.task_id))
            if stage == "detect":
                # 整页模式（area=4）：区域参数归第三步面板所有，detect 只是
                # 借来判定「要不要加载 YOLO」，worker 侧据此整页跳过检测。
                args["area"] = int(
                    self.control_stack.widget(2).get_args().get("area", 1)
                )
            if stage == "rembg":
                # 「生成预览」整页去底图固定写入 stages/rembgpreview；
                # rembg CLI 会自行追加 "rembg" 子目录，故用 _outpath 精确覆盖
                args["_outpath"] = str(
                    self.store.rembg_preview_output_dir(self.task_id)
                )
            else:
                # detect 的输出目录解析会在 output 后追加默认子目录名（detect）
                args["output"] = str(self.store.task_dir(self.task_id) / "stages")
            args["clean"] = not resume

        if stage == "print":
            # 记录最近一次执行的表单参数（供面板「重置」恢复）
            try:
                panel.mark_applied(args)
            except Exception:
                pass

        self._launch_stage_process(stage, args, resume)

    def _launch_stage_process(self, stage: str, args: dict, resume: bool = False) -> None:
        """写入运行配置并启动 worker 子进程。"""
        self.run_id = self.store.create_stage_run(self.task_id, stage, args, resume)
        runs_dir = self.store.runs_config_dir(self.task_id)
        runs_dir.mkdir(parents=True, exist_ok=True)
        config_path = runs_dir / f"run-{self.run_id}.json"
        write_json(
            config_path,
            {"task_id": self.task_id, "stage": stage, "run_id": self.run_id, "args": args},
        )
        self.cancel_requested = False
        self.running_stage = stage
        self._last_error_line = None
        # 最近一次 progress 事件 (done, total)：worker 结束时不带计数，
        # 用它把最终进度落到历史记录里（见 _worker_finished）。
        self._last_progress = (0, 0)
        # 半行缓冲/进度合并都是**每次运行**的临时状态，别把上一次的残留带过来
        self._stdout_tail = ""
        self._progress_dirty = False
        self._progress_ui_timer.stop()
        # 本步**自己**的活儿：立刻显示"执行中"并把进度归零 —— 第一个 progress
        # 事件到达之前（torch 冷启动可达数秒）不该继续挂着上一次的「成功 91/91」。
        # 跨步骤启动（在别的步骤点了按钮）则一个像素都不动：那一步的进度条与
        # 文案不该被这一步的活儿改写（见 _progress_belongs_here）。
        if self._progress_belongs_here(stage):
            self.stage_progress.setRange(0, 1)
            self.stage_progress.setValue(0)
            # 走 _set_stage_status 而不是 setText：颜色要跟着回到常规色，
            # 否则上一条"上游已重跑/版面已修改"的红字会留在「执行中」上
            self._set_stage_status(
                f"{STAGE_LABELS[stage]}：{STATUS_LABELS['running']}"
            )
        if stage == "extract":
            self._extract_seen = len(
                list_stage_images(self.store.extract_output_dir(self.task_id))
            )
        self.process = QProcess(self)
        self.process.setProgram(sys.executable)
        self.process.setProcessEnvironment(self._worker_env())
        if getattr(sys, "frozen", False):
            # 打包环境：主程序即入口，--worker 路由到子任务执行
            arguments = ["--worker", "--config", str(config_path)]
        else:
            # 源码环境：按模块启动，不依赖入口文件名（desktop.py 改名无影响），
            # 工作目录必须是项目根（能解析出 desktop 包的那一级）
            arguments = ["-m", "desktop.worker", "--config", str(config_path)]
            self.process.setWorkingDirectory(str(project_root()))
        self.process.setArguments(arguments)
        self.process.readyReadStandardOutput.connect(self._read_worker_output)
        self.process.readyReadStandardError.connect(self._read_worker_error)
        self.process.errorOccurred.connect(self._worker_error_occurred)

        # Windows 偶发丢失 finished 信号（尤其从 worker 回调链启动时）：
        # 看门狗轮询兜底——Qt 状态滞留 Running 但 OS 进程已退出时，
        # 直接用 Win32 探测并手动驱动完成流程。
        self._finish_delivered = False
        self._proc_started = False
        proc = self.process
        watchdog = QTimer(self)

        def _finish_once(code: int, status) -> None:
            if self._finish_delivered:
                return
            self._finish_delivered = True
            self._worker_finished(code, status)

        def _process_alive(pid: int) -> bool:
            if pid <= 0 or sys.platform != "win32":
                return True
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if not handle:
                return False  # 无法打开 = 已退出
            try:
                code = ctypes.c_ulong()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return code.value == STILL_ACTIVE
                return True
            finally:
                kernel32.CloseHandle(handle)

        def _watchdog() -> None:
            if self.process is None or self.process is not proc:
                watchdog.stop()
                return
            if proc.state() == QProcess.NotRunning:
                code = proc.exitCode()
                # 从未成功启动时 exitCode() 仍是 0，直接当成功会误报"执行成功"
                if not self._proc_started and code == 0:
                    code = 1
                _finish_once(code, proc.exitStatus())
            elif not _process_alive(proc.processId()):
                # OS 进程已退出，Qt 却没报 finished（Windows 偶发）。
                # ⚠️ 这里**不能**直接 ``_finish_once(0, NormalExit)``：
                # ① 硬编码 0 会把崩溃/失败（退出码非 0）报成"执行成功"；
                # ② 立刻收尾会丢掉管道里还没读的 progress/log 事件。
                # 所以先让 Qt 收尾——它会排空管道并把**真实退出码**带回来；
                # 实在收不了尾才按失败兜底（宁可误报失败，不可误报成功）。
                if proc.waitForFinished(1500):
                    code = proc.exitCode()
                    if not self._proc_started and code == 0:
                        code = 1
                    _finish_once(code, proc.exitStatus())
                else:
                    self.log_view.append(
                        "[看门狗] 子任务进程已退出但未正常收尾，按失败处理"
                    )
                    self._last_error_line = "子任务进程未正常收尾（看门狗兜底）"
                    _finish_once(1, QProcess.CrashExit)

        def _mark_started() -> None:
            self._proc_started = True

        proc.started.connect(_mark_started)
        proc.finished.connect(_finish_once)
        watchdog.timeout.connect(_watchdog)
        watchdog.start(300)
        self.process.start()
        # 进程真的起来了 → 防抖窗口从这里开始计时（见 _run_launched_at）
        self._mark_run_launched()

        self.store.update_task(self.task_id, "running")
        self._refresh_stage_views()
        # 开始执行时自动展开日志：用户此刻最需要看到实时输出
        self.log_panel.set_expanded(True)
        self.log_view.append(
            f"=== 开始执行 {STAGE_LABELS[stage]}{'（续跑）' if resume else ''} ==="
        )

    def cancel_stage(self) -> None:
        """中断正在执行的阶段：先落 cancelled 再 kill 子进程。

        先立即把运行记录置为 cancelled——防止进程被强杀来不及回调时状态永远
        停留 running（重启后按钮状态错乱）；随后置 cancel_requested 并 kill。
        """
        if self.process and self.process.state() != QProcess.NotRunning:
            self.cancel_requested = True
            self._set_stage_status("正在中断子任务...")
            self.log_view.append("已请求中断，正在终止子任务进程...")
            # 立即把运行记录置为已中断：进程被强杀来不及回调时，
            # 状态不会永远停留在 "running"（否则重启后按钮状态是错的）
            if self.run_id:
                self.store.finish_stage(self.task_id, self.run_id, "cancelled")
            self.process.kill()

    # ---------------------------------------------------------- 输出解析
    def _read_worker_output(self) -> None:
        """worker stdout 有数据到达（信号槽）：交给解析层。"""
        if not self.process:
            return
        self._consume_worker_stdout(bytes(self.process.readAllStandardOutput()))

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
                    self.log_view.append(tail)
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
                    self.log_view.append(line)
                continue
            etype = event.get("type")
            if etype == "progress":
                self._on_worker_progress(event)
            elif etype == "log":
                self.log_view.append(event.get("message", ""))
            elif etype == "page_boxes":
                self._store_stage_boxes(event)
            elif etype == "page_size":
                self._store_page_size(event)
            elif etype == "started":
                self.log_view.append(f"子任务进程已启动：{STAGE_LABELS.get(event.get('stage'), event.get('stage'))}")
            elif etype == "error":
                self.log_view.append(f"错误：{event.get('message')}")
            elif etype == "cancelled":
                self.log_view.append("子任务进程已被中断。")

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

    def _store_page_size(self, event: dict) -> None:
        """extract 阶段上报的页面图片原始尺寸写入 sizes.json（框坐标的坐标系基准）。"""
        if not self.task_id:
            return
        self.store.save_image_size(
            self.task_id, event.get("image", ""),
            event.get("width", 0), event.get("height", 0),
        )

    def _store_stage_boxes(self, event: dict) -> None:
        """detect 阶段上报的框坐标实时写回 boxes.json（origin=auto）；手动框不被覆盖。

        存储保留左右身份：[左框, 右框]，缺失一侧为 null，
        以便 area=1 输出条目按 -r/-l 规范排序。
        """
        if not self.task_id:
            return
        left = event.get("left")
        right = event.get("right")
        boxes = [
            [int(v) for v in left] if left else None,
            [int(v) for v in right] if right else None,
        ]
        if not any(boxes):
            return
        image_key = event.get("image", "")
        entry = self.store.detect_boxes_entry(self.task_id, image_key)
        if entry and entry[1] == "manual":
            return
        self.store.save_detect_boxes(
            self.task_id, image_key, boxes, origin="auto"
        )

    def _read_worker_error(self) -> None:
        """worker 的 stderr：崩溃堆栈/告警原样进日志，避免失败时无从排查。"""
        source = self.process or self.detect_process
        if not source:
            return
        self._consume_worker_stderr(bytes(source.readAllStandardError()))

    def _consume_worker_stderr(self, data: bytes) -> None:
        """解析 stderr 字节：逐行进日志，并记下像错误的那一行（失败提示用）。"""
        for line in data.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if line:
                self.log_view.append(f"[stderr] {line}")
                if "Error" in line or "Traceback" in line or "错误" in line:
                    self._last_error_line = line

    def _worker_error_occurred(self, error) -> None:
        if self.cancel_requested:
            return
        self.log_view.append(f"[进程错误] {error}")
        if error == QProcess.ProcessError.FailedToStart:
            program = self.process.program() if self.process else "worker"
            self._last_error_line = f"子进程启动失败：{program}"

    def _poll_extract_results(self) -> None:
        """提取过程中：一旦输出目录出现新图片，立即在「提取结果」里展示。"""
        if not self.task_id:
            return
        paths = list_stage_images(self.store.extract_output_dir(self.task_id))
        if len(paths) != self._extract_seen:
            self._extract_seen = len(paths)
            self.extract_result_viewer.set_images(paths)

    def _worker_finished(self, exit_code: int, _status) -> None:
        stage = self.running_stage
        # ⚠️ 收尾第一件事：把管道里剩下的输出读完。
        # Qt 的 finished / 看门狗可能比最后一批 progress/log 事件先到（大任务时
        # GUI 本来就落在 worker 后面），而下面马上要清 self.process 与 self.run_id ——
        # 一清就等于把这批事件永久丢掉：进度停在中间值（历史里
        # 「成功 done=14/total=84」）、日志缺「🎉 处理完成」那行，用户看到的就是
        # "像被中断了/只提取了一半"。排空 + 落最后一次进度之后再清引用。
        proc = self.process
        if proc is not None:
            if proc.state() != QProcess.NotRunning:
                try:
                    proc.waitForFinished(300)  # 让 Qt 收尾并排空管道
                except RuntimeError:
                    pass
            self._drain_worker_output(proc)
        self._flush_progress_ui()
        if self.cancel_requested:
            status = "cancelled"
        elif exit_code == 0:
            status = "success"
        else:
            status = "failed"
        # ⚠️ 失败原因算一次、用三处（落盘 / 日志 / toast）：worker 起不来的那类
        # 失败**一条输出都没有**（0 事件、0.2 秒退出），只有退出码可依。以前只
        # 弹一条转瞬即逝的 toast，记录里连原因都没有，事后完全无从查起。
        failure = None
        if status == "failed":
            failure = self._last_error_line or f"退出码 {exit_code}"
        if self.run_id:
            # worker 的 finished 事件不带 done/total（进度由结构化事件实时汇报），
            # 用最近一次进度补齐，否则历史记录会停在中间的 done 值上。
            self.store.finish_stage(
                self.task_id, self.run_id, status,
                str(self.store.stage_output_dir(self.task_id, stage)) if stage else None,
                progress=self._last_progress,
                error=failure,
            )
        if self.task_id:
            self.store.update_task(
                self.task_id, "completed" if status == "success" else status
            )
        # 这一步刚跑完 → "上游比下游新"的关系可能变了，重算过期提示缓存
        # （判定要读 runs.json，只能在这类"收尾"时刻做，不能放刷新热路径）。
        # 必须在下面的 _refresh_stage_views() 之前：那一次刷新就要用新缓存。
        try:
            self._refresh_stale_notices()
        except Exception:
            pass
        self.process = None
        self.run_id = None
        self.running_stage = None
        # 进程收尾 = 释放执行权（按钮恢复可用、下一次点击可受理）。
        # 放在这里是唯一出口：正常结束、被杀、看门狗兜底都汇到本方法。
        self._release_run()
        if status == "success" and self.task_id:
            if stage == "extract":
                # 页面清单只由 extract 输出决定；detect/rembg 结果留在各自目录，
                # 不回写清单，避免污染 extract 预览和后续子任务的输入。
                output_dir = self.store.stage_output_dir(self.task_id, stage)
                page_count = len(self.store.refresh_pages_from_dir(self.task_id, output_dir))
                self.log_view.append(f"页面清单已刷新（{page_count} 页）。")
                self._refresh_manifest()
                if page_count == 0:
                    self._toast(
                        "warning", "结果为空",
                        f"{STAGE_LABELS[stage]} 未产生任何图片，请查看日志（可能参数有误）。",
                    )
            if stage == "print":
                pdf_path = self._latest_print_pdf_path()
                if pdf_path and pdf_path.exists():
                    self.log_view.append(f"PDF 已生成：{pdf_path}")
                    self.print_preview.set_pdf_path(pdf_path)
                else:
                    self.print_preview.set_pdf_path(None)
                # 重新生成完成，清除「版面已修改」标脏
                self._print_dirty = False
                try:
                    # 同上：颜色要一起回到常规色
                    self._set_stage_status("成功")
                except Exception:
                    pass
        self._refresh_stage_views()
        self._refresh_preview()
        if stage == "extract":
            self._refresh_preview(1)  # 提取结果标签页
        override_toast = None
        if status == "success" and stage in ("rembg", "rembg_submit"):
            version = self._rembg_submit_version_state()
            if stage == "rembg":
                # 新预览图已落盘：若与最近一次提交不一致，提示有新版本待提交
                if version == "new_version":
                    override_toast = (
                        "info", "已生成新的预览版本",
                        "去底预览图片已更新，请点击「提交本次任务」生成最终图片",
                    )
                elif version == "preview_stale":
                    override_toast = (
                        "info", "预览已生成",
                        "提示：面板参数又有修改，请确认后重新「生成预览」",
                    )
            else:  # rembg_submit
                self._refresh_preview(3)  # 最终图变化，同步刷新第四步列表
                if version == "up_to_date":
                    override_toast = (
                        "success", "提交完成",
                        "最终图片已是最新预览版本，可前往第四步生成 PDF",
                    )
        if status == "failed":
            reason = failure or "退出码 " + str(exit_code)
            # 先落一行日志再弹 toast：toast 会自己消失，日志留在面板里
            self.log_view.append(f"失败原因：{reason}")
            self._toast("error", f"{STAGE_LABELS.get(stage, '')}失败", reason)
        elif override_toast is not None:
            self._toast(*override_toast)
        else:
            self._toast(
                "success" if status == "success" else "error",
                STAGE_LABELS.get(stage, ""),
                STATUS_LABELS.get(status, status),
            )

    @staticmethod
    def _worker_env() -> QProcessEnvironment:
        """子进程强制 UTF-8：GUI 按 UTF-8 解析 JSON Lines，CLI 输出含 emoji。"""
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUTF8", "1")
        return env
