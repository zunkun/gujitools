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
from desktop.store import STAGE_LABELS

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

    # ---------------------------------------------------------- 执行/中断
    def run_stage(self, resume: bool = False) -> None:
        """启动当前阶段的 worker 子进程。

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
                self.stage_status.setText("未执行")
            except Exception:
                pass
            self.log_view.append(
                f"区域合成：area={area}"
                + (f"，border={border}" if border is not None else "，border=0")
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
                # OS 进程已退出而 Qt 未感知
                _finish_once(0, QProcess.NormalExit)

        def _mark_started() -> None:
            self._proc_started = True

        proc.started.connect(_mark_started)
        proc.finished.connect(_finish_once)
        watchdog.timeout.connect(_watchdog)
        watchdog.start(300)
        self.process.start()

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
            self.stage_status.setText("正在中断子任务...")
            self.log_view.append("已请求中断，正在终止 worker...")
            # 立即把运行记录置为已中断：进程被强杀来不及回调时，
            # 状态不会永远停留在 "running"（否则重启后按钮状态是错的）
            if self.run_id:
                self.store.finish_stage(self.task_id, self.run_id, "cancelled")
            self.process.kill()

    # ---------------------------------------------------------- 输出解析
    def _read_worker_output(self) -> None:
        if not self.process:
            return
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        for line in data.splitlines():
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
                done, total = event.get("done", 0), event.get("total", 0)
                if self.run_id:
                    self.store.set_progress(self.task_id, self.run_id, done, total)
                if total:
                    self.stage_progress.setRange(0, total)
                    self.stage_progress.setValue(min(done, total))
                    self.stage_status.setText(f"进度 {done}/{total}")
                # 记住最近一次进度：finish_stage 用它补齐最终计数（见 _worker_finished）
                self._last_progress = (done, total)
                self._refresh_stage_views()
                if self.running_stage == "extract":
                    self._poll_extract_results()
            elif etype == "log":
                self.log_view.append(event.get("message", ""))
            elif etype == "page_boxes":
                self._store_stage_boxes(event)
            elif etype == "page_size":
                self._store_page_size(event)
            elif etype == "started":
                self.log_view.append(f"worker 已启动：{event.get('stage')}")
            elif etype == "error":
                self.log_view.append(f"错误：{event.get('message')}")
            elif etype == "cancelled":
                self.log_view.append("worker 已被中断。")

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
        data = bytes(source.readAllStandardError()).decode("utf-8", errors="replace")
        for line in data.splitlines():
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
        if self.cancel_requested:
            status = "cancelled"
        elif exit_code == 0:
            status = "success"
        else:
            status = "failed"
        if self.run_id:
            # worker 的 finished 事件不带 done/total（进度由结构化事件实时汇报），
            # 用最近一次进度补齐，否则历史记录会停在中间的 done 值上。
            self.store.finish_stage(
                self.task_id, self.run_id, status,
                str(self.store.stage_output_dir(self.task_id, stage)) if stage else None,
                progress=self._last_progress,
            )
        if self.task_id:
            self.store.update_task(
                self.task_id, "completed" if status == "success" else status
            )
        self.process = None
        self.run_id = None
        self.running_stage = None
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
                    self.stage_status.setText("成功")
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
            reason = self._last_error_line or "退出码 " + str(exit_code)
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
