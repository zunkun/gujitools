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
from utils.sort_utils import pdf_custom_sort_key

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
            if not effects:
                self._toast(
                    "warning", "无输入页面",
                    "待打印列表为空，请先在第三步「生成预览」（必要时「提交"
                    "本次任务」选页），或在左侧列表插入图片。",
                )
                return
            doc["pages"] = [
                {k: e.get(k) for k in ("file", "label")}
                for e in entries
            ]
            self.store.save_print_doc(self.task_id, doc)
            args["_effects"] = effects
            args["input"] = str(self.store.workset_dir(self.task_id))
            args["output"] = str(self.store.stage_dir(self.task_id, "print"))
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
            workset = self._build_workset(stage, resume)
            if not any(workset.iterdir()):
                self._toast("info", "无需续跑", "该子任务的输出已完整。")
                return
            args["input"] = str(workset)
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

    # ---------------------------------------------------------- rembg 提交
    def _rembg_result_path(self, stem: str) -> Path | None:
        """某页面对应的「生成预览」去底色结果（stages/rembgpreview）。"""
        rembg_dir = self.store.rembg_preview_output_dir(self.task_id)
        for ext in ("png", "jpg", "jpeg"):
            candidate = rembg_dir / f"{stem}.{ext}"
            if candidate.exists():
                return candidate
        return None

    def _latest_print_pdf_path(self) -> Path | None:
        """最近一次 print 执行产出的 PDF 路径（按 YAML pdf_name 解析）。"""
        if not self.task_id:
            return None
        pdf_name = "print.pdf"
        history = self.store.list_stage_runs(self.task_id, "print")
        if history:
            params = history[0].get("parameters", {})
            if params.get("pdf_name"):
                pdf_name = str(params["pdf_name"])
        out_dir = self.store.stage_dir(self.task_id, "print")
        candidate = out_dir / pdf_name
        if candidate.exists():
            return candidate
        # 兜底：目录下任意 pdf
        for cand in out_dir.glob("*.pdf"):
            return cand
        return None

    def _rembg_submit_entries(self, area: int, border) -> list[dict]:
        """预览结果 + 检测框 + area/border → 最终图片条目。

        派生规则与 rembg 预览条目、print 待打印列表完全一致：
        - area=1 双框：拆 <页>-r / <页>-l 两条（古籍阅读顺序 r 在前）；
        - area=2/3 双框：取双框并集，单条输出；
        - 单框：area=2/3 走对称画布（parea=2），area=1 按普通框；
        - 无框：整页预览图透传。
        最终按 CLI natural sort 排序（同页 r 在 l 前）。
        """
        entries: list[dict] = []
        for path in self._manifest_paths():
            result = self._rembg_result_path(path.stem)
            if result is None:
                continue  # 该页尚未生成预览
            boxes = self._valid_boxes(self._detect_boxes_for(str(path)))
            stem = path.stem
            if area == 1 and len(boxes) == 2:
                entries.append(
                    {"file": str(result), "label": f"{stem}-r",
                     "box": boxes[1], "parea": 1}
                )
                entries.append(
                    {"file": str(result), "label": f"{stem}-l",
                     "box": boxes[0], "parea": 1}
                )
            elif area in (2, 3) and len(boxes) == 2:
                union = [
                    min(b[0] for b in boxes), min(b[1] for b in boxes),
                    max(b[2] for b in boxes), max(b[3] for b in boxes),
                ]
                entries.append(
                    {"file": str(result), "label": stem,
                     "box": union, "parea": 1}
                )
            elif len(boxes) == 1:
                entries.append(
                    {"file": str(result), "label": stem, "box": boxes[0],
                     "parea": 2 if area in (2, 3) else 1}
                )
            else:
                entries.append(
                    {"file": str(result), "label": stem,
                     "box": None, "parea": 1}
                )
        entries.sort(key=lambda e: pdf_custom_sort_key(e["label"]))
        return entries

    def _build_print_effects(
        self, list_entries: list[dict], area: int, border
    ) -> list[dict]:
        """第四步列表 + 第三步当前 area/border → worker 合成规格。

        与「提交本次任务」复用同一套派生规则（_rembg_submit_entries）：
        源图为 stages/rembgpreview 去底图，effect 携带检测框/area/border，
        由 run_print_stage 在子进程内实时合成后再排版为 PDF。

        与用户在第四步保存的列表（拖动排序/删除/外部插入）按 label 对齐：
        - 命中当前 area 派生集合的条目，按用户列表顺序输出合成规格；
        - 用户插入的外部图片（不在 stages/rembg 目录）整图透传；
        - area 模式切换后已失效的旧提交图（如旧 82-r/82-l 被新 82 取代）
          丢弃，当前集合中新派生的条目按默认顺序补在末尾，避免漏页或重复。
        """
        composed = self._rembg_submit_entries(area, border)
        dmap = {c["label"]: c for c in composed}
        rembg_dir = self.store.rembg_output_dir(self.task_id)

        def _spec(spec: dict) -> dict:
            return {
                "file": spec["file"],
                "effect": (
                    {
                        "boxes": [spec["box"]],
                        "area": spec.get("parea", 1),
                        "border": border,
                    }
                    if spec.get("box")
                    else None
                ),
            }

        # 已提交产物的 label 集合：用于区分「用户删除」与「area 切换新派生」
        submitted_labels = {p.stem for p in list_stage_images(rembg_dir)}
        effects: list[dict] = []
        used: set[str] = set()
        for e in list_entries:
            label = e.get("label") or Path(e["file"]).stem
            spec = dmap.get(label)
            if spec is not None:
                effects.append(_spec(spec))
                used.add(label)
            elif Path(e["file"]).parent != rembg_dir:
                # 用户手动插入的外部图片：不做区域合成，整页参与排版
                effects.append({"file": e["file"], "effect": None})
        # 仅补「当前 area 派生出、但提交产物里尚不存在」的条目（area 模式
        # 切换后的新结构页）；已存在提交图却不在用户列表的，属于用户主动
        # 删除，不得补回。
        for spec in composed:
            if spec["label"] not in used and spec["label"] not in submitted_labels:
                effects.append(_spec(spec))
        return effects

    def run_rembg_submit(self) -> None:
        """提交本次任务：把「生成预览」的去底色图片按 area/border 等
        合成为真正想要的最终图片，输出到 stages/rembg 目录。"""
        if not self.task_id or not self.source_path:
            self._toast("warning", "提示", "请先导入 PDF")
            return
        if self.process and self.process.state() != QProcess.NotRunning:
            self._toast("warning", "任务进行中", "当前子任务正在执行")
            return
        # 必须以最近一次「生成预览」成功为前提（旧图残留/失败/中断均拒绝提交）
        preview_state = self.store.stage_states(self.task_id)["rembg"]["status"]
        if preview_state != "success":
            self._toast(
                "warning", "请先生成预览",
                "「生成预览」执行成功后才能提交本次任务"
                + ("" if preview_state == "pending" else
                   f"（当前状态：{STATUS_LABELS.get(preview_state, preview_state)}）"),
            )
            return
        panel = self.control_stack.widget(2)  # rembg 面板
        try:
            args = panel.get_args()
        except ValueError as exc:
            self._toast("error", "参数错误", str(exc))
            return
        self._refresh_manifest()
        if not self._manifest_paths():
            self._toast(
                "warning", "无输入页面",
                "页面清单为空，请先完成上一步子任务，或在预览区插入图片。",
            )
            return
        entries = self._rembg_submit_entries(args["area"], args.get("border"))
        if not entries:
            self._toast(
                "warning", "尚未生成预览",
                "请先点击「生成预览」生成去底色图片，再提交本次任务。",
            )
            return
        args["_effects"] = [
            {
                "file": e["file"],
                "label": e["label"],
                "effect": (
                    {
                        "boxes": [e["box"]],
                        "area": e.get("parea", 1),
                        "border": args.get("border"),
                    }
                    if e.get("box")
                    else None
                ),
            }
            for e in entries
        ]
        args["output"] = str(self.store.rembg_output_dir(self.task_id))
        args["clean"] = True
        # 记录本次提交所基于的「生成预览」成功版本，用于判断预览是否又有新版本
        preview_run = next(
            (r for r in self.store.list_stage_runs(self.task_id, "rembg")
             if r.get("status") == "success"),
            None,
        )
        if preview_run:
            args["_preview_run_id"] = preview_run.get("run_id")
        self.log_view.append(
            f"提交本次任务：{len(entries)} 张最终图片 → {args['output']}"
        )
        self._launch_stage_process("rembg_submit", args, resume=False)

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
                pdf_path = self._latest_print_pdf_path()
                if pdf_path and pdf_path.exists():
                    self.log_view.append(f"PDF 已生成：{pdf_path}")
                    self.print_preview.set_pdf_path(pdf_path)
                else:
                    self.print_preview.set_pdf_path(None)
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
