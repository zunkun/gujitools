# -*- coding: utf-8 -*-
"""worker 输出的落盘与错误采集：页面尺寸/检测框攒批、统计刷新、stderr。"""

from __future__ import annotations

from utils.box_geometry import page_box_slots_from_event
from ._qt import QObject, QProcess, QTimer
from typing import TYPE_CHECKING, Any, Callable, cast


class WorkerOutputMixin:
    """输出落盘与错误采集。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _ANNOT_FLUSH_MS: Any
        _STATS_UI_MS: Any
        _logs: Any
        _node_scope: Any
        _refresh_detect_stats: Any
        cancel_requested: Any
        current_stage: Any
        detect_process: Any
        detect_stats: Any
        process: Any
        running_node: Any
        store: Any
        task_id: Any

    def _store_page_size(self, event: dict) -> None:
        """extract 阶段上报的页面图片原始尺寸 → 攒批（sizes.json 是框坐标基准）。

        ⚠️ 不逐条落盘：320 页逐条「读整个 sizes.json + 写回」实测累计 **1.3 秒**
        主线程阻塞（2400 页的书记忆里是几十秒）。攒到 400ms 一次批量写。
        """
        if not self.task_id:
            return
        self._pending_sizes[event.get("image", "")] = (
            int(event.get("width", 0)),
            int(event.get("height", 0)),
        )
        self._annot_timer.start(self._ANNOT_FLUSH_MS)

    def _store_stage_boxes(self, event: dict) -> None:
        """detect 阶段上报的框坐标 → 攒批（origin=auto；人工框不被覆盖）。

        槽位拼装走 **共用实现**（``utils.box_geometry.page_box_slots_from_event``，
        ``utils`` 层无重依赖、主进程可直连）——独立「检测文本框」模块页读的是
        同一条通道、同一个约定，两处各写一遍必然漂移。槽位约定的含义见
        ``functions/detect.PageBoxes``（半幅 2 槽 ``[左, 右]``、整幅 1 槽
        ``[整幅]``，下游据此分辨形态）。

        ⚠️ 逐条落盘是「读 boxes.json + 写回」× 页数，320 页实测累计 **1.8 秒**
        主线程阻塞；改攒批 + 一次性写。人工框的优先级判定挪到批量写里
        （见 store.save_detect_boxes_batch），顺带省掉每条一次的文件读。

        ⚠️ **空结果也攒**（2026-10-20）：以前 ``not any(boxes)`` 直接丢，于是
        "检测过、但没检出内容框"的页在 boxes.json 里**没有条目**，统计便无法
        区分"检测过、无框"与"还没检测"。现在空框也留痕（写空 ``boxes``）；
        ``classify_page_slots([])`` 与"条目缺失"分类结果相同，统计口径不变。
        """
        if not self.task_id:
            return
        self._pending_boxes[event.get("image", "")] = page_box_slots_from_event(event)
        self._annot_timer.start(self._ANNOT_FLUSH_MS)

    def _flush_annotations(self) -> None:
        """把攒下的尺寸/框一次性落盘（定时器到期、阶段收尾、切任务时都要调）。

        ⚠️ 必须在 `_worker_finished` 里调：阶段结束后下游要用 sizes.json/
        boxes.json 做坐标基准，攒着不写会让下一阶段读到旧数据。

        ⚠️ 落点按**正在跑的那个节点**（B 方案）：同一步骤的第二个「检测文本框」
        节点必须写自己的 ``boxes~<节点>.json``，写进主节点那份就是**覆盖别人的
        结果**（而且它的下游永远读不到自己那批框）。
        """
        if self._annot_timer.isActive():
            self._annot_timer.stop()
        sizes, self._pending_sizes = self._pending_sizes, {}
        boxes, self._pending_boxes = self._pending_boxes, {}
        if not self.task_id:
            return
        scope = self._node_scope(self.running_node)
        try:
            if sizes:
                self.store.save_image_sizes_batch(self.task_id, sizes, **scope)
            if boxes:
                self.store.save_detect_boxes_batch(self.task_id, boxes, **scope)
                # detect 批量检测中：落了一批框 → 右侧统计跟着刷新。
                # ⚠️ **置脏 + 节流**（不是立即重算）：统计每次要整份读
                #    boxes.json + sizes.json + profile_book，1000+ 页时是单次
                #    最贵的主线程动作，不能跟着落盘定时器以同样频率跑。
                #    收尾/切阶段/手工改框仍走 ``_refresh_stats_now`` 立即算。
                self._mark_stats_dirty()
        except Exception as exc:  # noqa: BLE001 - 落盘失败不该打断阶段收尾
            # ⚠️ 但不能**静默**吞掉（2026-09-26 审计）：磁盘满 / 任务目录被删 /
            # 权限异常时，下游（去底色、打印）会按**缺失的坐标基准**算错布局，
            # 而界面上一点提示都没有。这里做三件事：告警、记成失败原因、把数据
            # 放回去等下次 flush 再试一次（否则这批攒好的框就永久丢了）。
            message = f"页框/尺寸落盘失败：{type(exc).__name__}: {exc}"
            self._logs.append_now(message)
            self._last_error_line = message
            for key, value in sizes.items():
                self._pending_sizes.setdefault(key, value)
            for key, value in boxes.items():
                self._pending_boxes.setdefault(key, value)

    def _init_annotation_batch(self) -> None:
        """建标注攒批器与检测统计节流器（宿主页面 __init__ 里调一次）。"""
        self._pending_sizes: dict[str, tuple[int, int]] = {}
        self._pending_boxes: dict[str, list] = {}
        self._annot_timer = QTimer(cast("QObject", self))
        self._annot_timer.setSingleShot(True)
        self._annot_timer.setInterval(self._ANNOT_FLUSH_MS)
        self._annot_timer.timeout.connect(self._flush_annotations)
        # 统计重算的节流（见 _STATS_UI_MS / _refresh_stats_now / _flush_stats_ui）
        self._stats_dirty = False
        self._stats_timer = QTimer(cast("QObject", self))
        self._stats_timer.setSingleShot(True)
        self._stats_timer.setInterval(self._STATS_UI_MS)
        self._stats_timer.timeout.connect(self._flush_stats_ui)

    def _mark_stats_dirty(self) -> None:
        """把检测统计标脏并起一次节流（到期重算）。

        ⚠️ 只用于**执行期间**的批量落盘：统计要跟着 boxes.json 走，但没必要时时
        重算（单次最贵的动作，见 ``_STATS_UI_MS``）。
        """
        self._stats_dirty = True
        self._stats_timer.start(self._STATS_UI_MS)

    def _refresh_stats_now(self) -> None:
        """**立即**重算检测统计（不走节流）。

        必须立即重算的时机：阶段收尾、切阶段、以及用户手工改框——这几处
        "错一拍就是错的"，节流那一次可能还没到点。
        """
        if self._stats_timer.isActive():
            self._stats_timer.stop()
        self._stats_dirty = False
        if self.current_stage() == "detect" and self.detect_stats.isVisible():
            self._refresh_detect_stats()

    def _flush_stats_ui(self) -> None:
        """节流到期：标脏过就重算（见 ``_mark_stats_dirty``）。"""
        if not self._stats_dirty:
            return
        self._refresh_stats_now()

    def _read_worker_error(self) -> None:
        """worker 的 stderr：崩溃堆栈/告警原样进日志，避免失败时无从排查。"""
        source = self.process or self.detect_process
        if not source:
            return
        # PySide6 的 QByteArray 运行时可直接 bytes()（存根不认 SupportsBytes）
        self._consume_worker_stderr(
            bytes(source.readAllStandardError())  # type: ignore[reportArgumentType]
        )

    def _consume_worker_stderr(self, data: bytes) -> None:
        """解析 stderr 字节：逐行进日志，并记下像错误的那一行（失败提示用）。

        ⚠️ 匹配**不区分大小写**且覆盖几种常见形态：原先只认 `"Error"`/`"Traceback"`
        （首字母大写），而 argparse 的报错是 `prog: error: the following arguments
        are required: --config`（小写）、apt/pip 之类是 `E:`，全都会漏掉 →
        `_last_error_line` 仍是 None，用户看到的还是「退出码 1」。
        """
        _MARKERS = (
            "error",
            "traceback",
            "exception",
            "failed",
            "failure",
            "unable",
            "cannot",
            "can't",
            "no such",
            "no space",
            "denied",
            "errno",
            "not found",
            "missing",
            "错误",
            "失败",
            "异常",
        )
        for line in data.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if line:
                self._logs.append(f"[stderr] {line}")
                lowered = line.lower()
                if any(marker in lowered for marker in _MARKERS):
                    self._last_error_line = line

    def _worker_error_occurred(self, error) -> None:
        if self.cancel_requested:
            return
        self._logs.append_now(f"[进程错误] {error}")
        if error == QProcess.ProcessError.FailedToStart:
            program = self.process.program() if self.process else "worker"
            self._last_error_line = f"子进程启动失败：{program}"
