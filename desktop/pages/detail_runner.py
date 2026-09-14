# -*- coding: utf-8 -*-
"""任务详情页的阶段执行控制器：构建参数、启动 worker 子进程、解析进度日志。"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer

from ..utils.files import list_stage_images
from ..store import STAGES, STAGE_LABELS

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

    # ---------------------------------------------------------- 参数与 workset
    def _missing_extract_pages(self, ext: str) -> str | None:
        output_dir = self.store.extract_output_dir(self.task_id)
        present = set()
        if output_dir.exists():
            for f in output_dir.iterdir():
                digits = ""
                for ch in f.stem:
                    if ch.isdigit():
                        digits += ch
                    else:
                        break
                if digits:
                    present.add(int(digits))
        total = self.pdf_page_count or 0
        missing = [n for n in range(1, total + 1) if n not in present]
        if not missing or not total:
            return None
        parts, start, prev = [], None, None
        for n in missing:
            if start is None:
                start = prev = n
            elif n == prev + 1:
                prev = n
            else:
                parts.append(f"{start}-{prev}" if prev > start else f"{start}")
                start = prev = n
        if start is not None:
            parts.append(f"{start}-{prev}" if prev > start else f"{start}")
        return ",".join(parts)

    def _build_workset(self, stage: str, resume: bool) -> Path:
        """按页面清单物化执行输入目录。

        与 stages/extract 同卷时使用硬链接，不产生图片副本；
        跨卷或链接失败时回退为复制。
        """
        workset = self.store.workset_dir(self.task_id)
        if workset.exists():
            shutil.rmtree(workset)
        workset.mkdir(parents=True, exist_ok=True)
        output_dir = self.store.stage_output_dir(self.task_id, stage)
        for entry in self.pages:
            source = Path(entry["file"])
            if not source.exists():
                continue
            if resume and stage == "rembg":
                # rembg 续跑：已有去底色结果的页跳过
                if (output_dir / f"{source.stem}.png").exists():
                    continue
            target = workset / source.name
            if target.exists():
                continue
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
        return workset

    # ---------------------------------------------------------- 执行/中断
    def run_stage(self, resume: bool = False) -> None:
        if not self.task_id or not self.source_path:
            self._toast("warning", "提示", "请先导入 PDF")
            return
        if self.process and self.process.state() != QProcess.NotRunning:
            self._toast("warning", "任务进行中", "当前子任务正在执行")
            return
        stage = self.current_stage()
        task = self.store.get_task(self.task_id)
        if stage == "extract" and not Path(task["source_path"]).exists():
            self._toast("error", "源文件缺失", f"源 PDF 不存在：{task['source_path']}")
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
                missing = self._missing_extract_pages(args.get("ext", "jpg"))
                if not missing:
                    self._toast("info", "无需续跑", "提取输出已完整。")
                    return
                args["pages"] = missing
                args["clean"] = False
        elif stage == "print":
            # print：左侧列表（顺序）+ YAML 参数；效果图合成在子进程内完成
            entries, doc = self._print_entries()
            entries = [e for e in entries if Path(e["file"]).exists()]
            if not entries:
                self._toast(
                    "warning", "无输入页面",
                    "待打印列表为空，请先完成去底色，或在左侧列表插入图片。",
                )
                return
            doc["pages"] = [
                {k: e.get(k) for k in ("file", "label", "box", "parea")}
                for e in entries
            ]
            self.store.save_print_doc(self.task_id, doc)
            args["_effects"] = [
                {"file": e["file"], "effect": e.get("effect")} for e in entries
            ]
            args["input"] = str(self.store.workset_dir(self.task_id))
            args["output"] = str(self.store.stage_dir(self.task_id, "print"))
        else:
            self._refresh_manifest()
            if not self._manifest_paths():
                self._toast(
                    "warning", "无输入页面",
                    "页面清单为空，请先完成上一步子任务，或在预览区插入图片。",
                )
                return
            workset = self._build_workset(stage, resume)
            if not any(workset.iterdir()):
                self._toast("info", "无需续跑", "该子任务的输出已完整。")
                return
            args["input"] = str(workset)
            # detect/rembg 的输出目录解析会在 output 后追加默认子目录名（detect/rembg）
            args["output"] = str(self.store.task_dir(self.task_id) / "stages")
            args["clean"] = not resume

        if stage == "print":
            # 记录最近一次执行的 YAML 参数（供面板「重置」恢复）
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
        config_path.write_text(
            json.dumps(
                {"task_id": self.task_id, "stage": stage, "run_id": self.run_id, "args": args},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.cancel_requested = False
        self.running_stage = stage
        self._last_error_line = None
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
            # 源码环境：按模块启动，不依赖入口文件名（desktop.py 改名无影响）
            arguments = ["-m", "desktop.worker", "--config", str(config_path)]
            self.process.setWorkingDirectory(str(Path(__file__).parents[2]))
        self.process.setArguments(arguments)
        self.process.readyReadStandardOutput.connect(self._read_worker_output)
        self.process.readyReadStandardError.connect(self._read_worker_error)
        self.process.errorOccurred.connect(self._worker_error_occurred)

        # Windows 偶发丢失 finished 信号（尤其从 worker 回调链启动时）：
        # 看门狗轮询兜底——Qt 状态滞留 Running 但 OS 进程已退出时，
        # 直接用 Win32 探测并手动驱动完成流程。
        self._finish_delivered = False
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
                _finish_once(proc.exitCode(), proc.exitStatus())
            elif not _process_alive(proc.processId()):
                # OS 进程已退出而 Qt 未感知
                _finish_once(0, QProcess.NormalExit)

        proc.finished.connect(_finish_once)
        watchdog.timeout.connect(_watchdog)
        watchdog.start(300)
        self.process.start()

        self.store.update_task(self.task_id, "running")
        self._refresh_stage_views()
        self.log_view.append(
            f"=== 开始执行 {STAGE_LABELS[stage]}{'（续跑）' if resume else ''} ==="
        )

    def cancel_stage(self) -> None:
        if self.process and self.process.state() != QProcess.NotRunning:
            self.cancel_requested = True
            self.stage_status.setText("正在中断子任务...")
            self.log_view.append("已请求中断，正在终止 worker...")
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
        """extract 阶段上报的页面图片原始尺寸入库（框坐标的坐标系基准）。"""
        if not self.task_id:
            return
        self.store.save_image_size(
            self.task_id, event.get("image", ""),
            event.get("width", 0), event.get("height", 0),
        )

    def _store_stage_boxes(self, event: dict) -> None:
        """detect 阶段上报的框坐标实时入库（origin=auto）；手动框不被覆盖。

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
            self.store.finish_stage(
                self.task_id, self.run_id, status,
                str(self.store.stage_output_dir(self.task_id, stage)) if stage else None,
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
                output = self.store.print_output_pdf(self.task_id)
                if output.exists():
                    self.log_view.append(f"PDF 已生成：{output}")
        self._refresh_stage_views()
        self._refresh_preview()
        if stage == "extract":
            self._refresh_preview(1)  # 提取结果标签页
        if status == "failed":
            reason = self._last_error_line or "退出码 " + str(exit_code)
            self._toast("error", f"{STAGE_LABELS.get(stage, '')}失败", reason)
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
