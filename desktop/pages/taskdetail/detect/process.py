# -*- coding: utf-8 -*-
"""单页检测子进程与输出解析（从原 ``detect.py`` 拆出）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QObject, QProcess

from desktop.store.json_io import write_json
from desktop.utils.files import project_root

if TYPE_CHECKING:
    from desktop.pages.taskdetail.detect._host import DetectHost
else:
    DetectHost = object


class DetectProcessMixin(DetectHost):
    """手动触发单页检测、进程生命周期与 JSON Lines 输出解析。"""
    def _detect_current_page(self) -> None:
        """手动触发当前页的检测文本框（YOLO 子进程，重负载）。

        ⚠️ 2026-11-16 起**没有界面入口了**：用户要求去掉面板上的「检测本页」，
        检测统一走底部「检测文本框」主按钮那条批处理。这条单页路径保留原样
        （自测 ``detect_boxes`` 用它驱动一次检测；要彻底删掉得连带
        ``detect_process`` / ``_start_detect`` / run-claim 的「单页检测」分支
        一起清），别在别处再给它接按钮。
        """
        if not self.task_id:
            return
        path = self.detect_viewer.current_path()
        if not path:
            self._toast("warning", "提示", "请先完成提取，再执行检测。")
            return
        key = str(path)
        entry = self.store.boxes_entry_at(self._boxes_write_path(), Path(path).stem)
        if entry is not None and any(entry[0] or []):
            self.detect_cache[key] = entry[0]
            self._apply_boxes(key, entry[0], entry[1])
            self._refresh_reference_boxes()
            self._toast("info", "已有检测结果", "该页检测结果已存在，直接展示。")
            return
        # 执行权守卫：单页检测同样要抢 worker 槽位（一次 torch 冷启动 5 秒以上）。
        # ``replace=("单页检测",)`` 是刻意留的口子——连点不同页面时应该「换一页重检」
        # （_start_detect 会先断旧进程信号再杀），而不是弹一句"正在执行"卡住用户；
        # 但步骤在跑时必须拦住，那种情况下再塞一个检测只会两个 torch 抢内存。
        if not self._acquire_run("单页检测", replace=("单页检测",)):
            return
        self.detect_viewer.info_label.setText("正在检测文本框位置...")
        self.detect_cache[key] = None  # 防止重复派发
        self._start_detect(path)

    def _stop_detect_process(self) -> None:
        """停掉在跑的单页检测并释放执行权（返回列表/切任务前必须调）。

        ⚠️ 不停的话（2026-09-26 第二轮审计 H3）：检测是几秒到十几秒的慢活，
        用户中途「返回」或切到任务 B 后，旧进程的 boxes 事件才姗姗到达——
        而 ``self.task_id`` 已经是 B 了，``save_detect_boxes`` 就会把 A 的
        检测框写进 **B 的** boxes.json（两本书页名同为 0001 时直接污染裁剪）；
        若 A 已被删除，这里还会 FileNotFoundError 从 Qt 槽直接炸出去。
        与 ``_start_detect`` 的顶替逻辑同款：先断信号再 kill。
        """
        proc = self.detect_process
        if proc is None:
            return
        if proc.state() != QProcess.ProcessState.NotRunning:
            for signal in (
                proc.readyReadStandardOutput,
                proc.readyReadStandardError,
                proc.finished,
            ):
                try:
                    signal.disconnect()
                except (RuntimeError, TypeError):
                    pass
            proc.kill()
            proc.waitForFinished(1000)
        self.detect_process = None
        self._detect_out_buffer = ""
        self._release_run()

    def _start_detect(self, path: Path) -> None:
        old = self.detect_process
        if old is not None and old.state() != QProcess.ProcessState.NotRunning:
            # 关键：先断开旧进程的全部信号再杀。否则旧进程迟到的 finished
            # 会把 self.detect_process 清空，新进程的输出就被当成无主的丢弃。
            for signal in (
                old.readyReadStandardOutput,
                old.readyReadStandardError,
                old.finished,
            ):
                try:
                    signal.disconnect()
                except (RuntimeError, TypeError):
                    pass
            old.kill()
            old.waitForFinished(1000)
        task_id = self.task_id
        assert task_id is not None, "单页检测时没有任务在身"
        runs_dir = self.store.runs_config_dir(task_id)
        runs_dir.mkdir(parents=True, exist_ok=True)
        config_path = runs_dir / "detect-config.json"
        write_json(
            config_path,
            {"mode": "detect", "image": str(path)},
        )
        self.detect_process = QProcess(cast("QObject", self))
        self._detect_out_buffer = ""  # stdout 半行重组缓冲（见 _read_detect_output）
        self.detect_process.setProgram(sys.executable)
        self.detect_process.setProcessEnvironment(self._worker_env())
        if getattr(sys, "frozen", False):
            arguments = ["--worker", "--config", str(config_path)]
        else:
            arguments = ["-m", "desktop.worker", "--config", str(config_path)]
            self.detect_process.setWorkingDirectory(str(project_root()))
        self.detect_process.setArguments(arguments)
        self.detect_process.readyReadStandardOutput.connect(self._read_detect_output)
        self.detect_process.readyReadStandardError.connect(self._read_worker_error)
        self.detect_process.finished.connect(self._detect_finished)
        self.detect_process.start()
        # 进程真的起来了 → 防抖窗口从这里开始计时（见 _run_launched_at）
        self._mark_run_launched()

    def _read_detect_output(self) -> None:
        if not self.detect_process:
            return
        # PySide6 的 QByteArray 运行时可直接 bytes()（存根不认 SupportsBytes）
        data = bytes(
            self.detect_process.readAllStandardOutput()  # type: ignore[reportArgumentType]
        ).decode("utf-8", errors="replace")
        # ⚠️ 半行重组（审计 P2）：readyRead 只保证"有字节"，不保证按行切齐。
        # JSON Lines 事件被切成两半时，两半都 json.loads 失败 → boxes 事件
        # 整条静默丢弃，界面上表现为"检测完了但框没了"。把不完整的首段
        # 留到缓冲，与下一块拼上再解析；进程结束时缓冲里如有残留按坏行丢弃。
        data = getattr(self, "_detect_out_buffer", "") + data
        if "\n" in data:
            data, self._detect_out_buffer = data.rsplit("\n", 1)
        else:
            self._detect_out_buffer = data
            return
        for line in data.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "boxes":
                boxes = []
                try:
                    full = event.get("full")
                    if full:
                        # 整幅内容(fullcontent)：单个框、**单槽**
                        boxes = [[int(v) for v in full]]
                    else:
                        # 半幅：固定 2 槽 [左, 右]，缺失侧为 None（保留左右身份），
                        # 与批量检测的 _store_stage_boxes 完全一致的槽位约定。
                        for key in ("left", "right"):
                            value = event.get(key)
                            boxes.append([int(v) for v in value] if value else None)
                except (TypeError, ValueError):
                    # 畸形坐标（int() 转不动）宁可整条丢弃也别让槽抛异常——
                    # 那样 Qt 只往控制台打一句，界面毫无反应
                    self.log_view.append(f"检测输出格式异常，已忽略：{str(event)[:120]}")
                    continue
                if "image" not in event:
                    continue
                self.detect_cache[event["image"]] = boxes
                # 检测结果写回 boxes.json；无框不存，避免下次选中无法重新检测
                # ⚠️ 写**本节点**那一份（B 方案）：单页检测也属于"这个检测节点
                #    的产物"，写进主节点的文件就是覆盖别人的框。
                if any(boxes) and self.task_id:
                    self.store.save_detect_boxes(
                        self.task_id, Path(event["image"]).stem, boxes,
                        origin="auto",
                        **self._node_scope(self.node_of_stage("detect")),
                    )
                self._apply_detect_result(Path(event["image"]), boxes)
            elif event.get("type") == "log":
                # 单页检测路径原先只认 boxes/detect_error，于是「模型加载用时」
                # 「detect xx.jpg …」这些记录全被丢掉，用户看不出执行了什么
                self.log_view.append(event.get("message", ""))
            elif event.get("type") == "detect_error":
                self.log_view.append(f"检测失败：{event.get('message')}")

    def _detect_finished(self, *_args) -> None:
        # sender() 是真正发出信号的那个进程：只有它仍是"当前进程"时才清空引用
        proc = self.sender()
        if proc is not None and proc is not self.detect_process:
            # 被顶替的旧进程（_start_detect 已断其信号，理论上到不了这里）：
            # 绝不能顺手释放执行权——新进程才持有它
            return
        # 结束后缓冲里若还有半行，是坏行/被截断的输出，直接丢弃防串到下一次
        self._detect_out_buffer = ""
        self.detect_process = None
        self._release_run()
        # 单页检测完成 → 该页形态可能变了，**立即**重算右侧统计
        self._refresh_stats_now()

    def _apply_detect_result(self, path: Path, boxes) -> None:
        """自动检测结果到达 → 上屏（只在本页仍是预览页、且还停在第二步时应用）。"""
        if self.current_stage() != "detect":
            return
        if str(self.detect_viewer.current_path()) != str(path):
            return
        if str(path) in self.detect_cache:
            self.detect_cache[str(path)] = boxes or []
        self._apply_boxes(str(path), boxes or [])
        self._refresh_reference_boxes()
