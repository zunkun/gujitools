# -*- coding: utf-8 -*-
"""第三步「图片去底色」的**实时调整**控制器（单页、直接覆盖正式成品）。

用户改 offset / type / 印章等参数或翻页时，**只重算当前页**并立刻上屏，不必等
「执行去底色」全量任务。

⚠️ 2026-10-22（任务 0014 报障后）语义变更：算出来的**就是正式成品**——直接覆盖
``stages/rembg[~<节点>]/<页名>.png``（透明底）并刷新第四步缩略图。此前结果只落
系统临时目录，于是"页面看着变了，下一步 PDF排版 / 图片拼版拿到的还是旧图"。

与「执行去底色」的分工：那个是全量；这里只算**当前这一页**（改哪张就落哪张），
并通知下游（拼版重合成 / 第四步待打印列表）。参数与该页**盘上成品**当前所用的
取值一致时不再重算。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

from PySide6.QtCore import QObject, QProcess, QTimer

from desktop.workers import RembgLiveWorker, connect_queued
from utils.rembg_algorithms import REMBG_DEFAULT_ALGORITHM

if TYPE_CHECKING:
    from desktop.components.viewers import RembgPreviewWidget
    from desktop.store.store import TaskStore


class RembgLiveMixin:
    """依赖宿主页面提供：store / task_id / process / rembg_viewer /
    current_stage() / current_node() / node_of_stage() / run_worker /
    _latest_success_run() / panel_host_of_step() / _refresh_print_source() /
    _schedule_imposition_compose() / imposition_effective()。"""

    if TYPE_CHECKING:
        store: TaskStore
        task_id: str | None
        process: QProcess | None
        rembg_viewer: "RembgPreviewWidget"
        log_view: Any
        run_worker: Callable[..., Any]
        current_stage: Callable[[], str]
        current_node: Callable[[], str | None]
        node_of_stage: Callable[[str], str | None]
        _latest_success_run: Callable[..., Any]
        panel_host_of_step: Callable[[str], Any]
        _node_scope: Callable[..., dict]
        _refresh_print_source: Callable[..., None]
        _schedule_imposition_compose: Callable[[], None]
        imposition_effective: Callable[[], bool]

    #: 参数连发时的防抖窗口（拖一次滑块会发几十次 valueChanged）
    LIVE_DEBOUNCE_MS = 350

    #: 影响去底色结果的参数（与正式执行共用一份口径）。
    PREVIEW_PARAM_KEYS = (
        "algorithm", "window", "k",
        "type", "offset", "seal", "sealcolor", "sealarea", "sealmin_sat",
    )

    # ---------------------------------------------------------------- 初始化
    def _init_rembg_live(self) -> None:
        """装好实时调整状态与触发点（在 _init_ui 之后调用）。"""
        #: stem → 该页**盘上成品**当前是按哪份参数算出来的。
        #: 没有条目的页 ⇒ 盘上还是「执行去底色」全量那一轮的产物。
        self._live_done: dict[str, dict] = {}
        self._live_token: object | None = None
        self._live_pending: dict | None = None
        #: 待落盘的逐张 offset：(task_id, stem, value, node_id, primary_id)
        self._offset_pending: tuple | None = None
        #: 待落盘的逐张算法：(task_id, stem, algorithm, node_id, primary_id)
        self._algorithm_pending: tuple | None = None

        # ⚠️ Mixin 本体是普通类，类型检查器看不到宿主是 QObject，故收窄后当
        #    QTimer 的 parent 用（运行时是恒等）。
        self._live_timer = QTimer(cast(QObject, self))
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(self.LIVE_DEBOUNCE_MS)
        self._live_timer.timeout.connect(self._maybe_run_live_preview)

        self._offset_save_timer = QTimer(cast(QObject, self))
        self._offset_save_timer.setSingleShot(True)
        self._offset_save_timer.setInterval(self.LIVE_DEBOUNCE_MS)
        self._offset_save_timer.timeout.connect(self._flush_pending_offset)

        # 两个触发点：面板参数被改 → 实时算当前页并记录该图 offset；
        # 翻页 → 加载该图自己的 offset，并按当前参数**补算**（已是最新则跳过，
        # 没有成品时必算——用户 2026-10-23 报「切图中间没有去底色效果」）。
        # ⚠️ 面板是惰性的：挂 created 回调，等它真被建好再接。
        rembg_host = self.panel_host_of_step("rembg")
        if rembg_host is not None:
            add_hook = getattr(rembg_host, "add_created_hook", None)
            if callable(add_hook):
                add_hook(
                    lambda panel: (
                        panel.param_edited.connect(self._on_live_trigger),
                        panel.algorithm_edited.connect(self._on_algorithm_edited),
                    )
                )
            else:
                rembg_host.param_edited.connect(self._on_live_trigger)
                rembg_host.algorithm_edited.connect(self._on_algorithm_edited)
        self.rembg_viewer.current_changed.connect(self._on_image_changed)

    # ---------------------------------------------------------------- 触发
    def _on_live_trigger(self, *_args) -> None:
        """用户改了面板参数 → 记录该图 offset 并起实时计算防抖。"""
        if self.current_stage() != "rembg":
            return
        self._note_offset_pending()
        self._live_timer.start()

    def _on_algorithm_edited(self) -> None:
        """用户**改了算法下拉**：只把当前这张图的算法记进逐张表。

        ⚠️ 不能挂在 ``param_edited`` 上：改 offset/type 也会触发那个信号，那样
        每张调过 offset 的图都会被钉死当时的算法，之后换全局算法时它们不再跟随。
        """
        if self.current_stage() != "rembg":
            return
        task_id = self.task_id
        entry_path = self.rembg_viewer.current_entry_path()
        if not task_id or not entry_path:
            return
        panel = self.panel_host_of_step("rembg")
        if panel is None:
            return
        try:
            args = panel.get_args()
        except ValueError:
            return
        scope = self._node_scope(self.current_node())
        self._algorithm_pending = (
            task_id, Path(entry_path).stem,
            str(args.get("algorithm") or "otsu"),
            scope.get("node_id"), scope.get("primary_id"),
        )
        self._offset_save_timer.start()

    def _note_offset_pending(self) -> None:
        """记下"当前这张图 + 面板 offset"，防抖后落进逐张偏移表。"""
        task_id = self.task_id
        entry_path = self.rembg_viewer.current_entry_path()
        if not task_id or not entry_path:
            return
        panel = self.panel_host_of_step("rembg")
        if panel is None:
            return
        try:
            args = panel.get_args()
        except ValueError:
            return
        scope = self._node_scope(self.current_node())
        self._offset_pending = (
            task_id, Path(entry_path).stem, int(args.get("offset") or 0),
            scope.get("node_id"), scope.get("primary_id"),
        )
        self._offset_save_timer.start()

    def _flush_pending_offset(self) -> None:
        """把待写的逐张 offset / 算法落盘（切图/切任务/执行前都要调）。"""
        if self._offset_save_timer.isActive():
            self._offset_save_timer.stop()
        offset_pending, self._offset_pending = self._offset_pending, None
        algorithm_pending, self._algorithm_pending = self._algorithm_pending, None
        try:
            if offset_pending:
                task_id, stem, value, node_id, primary_id = offset_pending
                self.store.save_rembg_offset(
                    task_id, stem, value, node_id=node_id, primary_id=primary_id
                )
            if algorithm_pending:
                task_id, stem, algorithm, node_id, primary_id = algorithm_pending
                self.store.save_rembg_algorithm(
                    task_id, stem, algorithm,
                    node_id=node_id, primary_id=primary_id,
                )
        except Exception:  # noqa: BLE001 - 逐张记录失败不该拖垮实时调整
            pass

    def _on_image_changed(self, *_args) -> None:
        """翻页：回填该图自己的 offset、刷新显示，并**按当前参数实时补算**。

        用户 2026-10-23：「切换左侧缩略图，中间图片没有实时去底色效果」——
        切到的那张可能还没成品（新提交的占位图、上游重跑换了页名），
        也可能成品是按旧参数算的。这里起一次防抖：与盘上成品一致时
        :meth:`_maybe_run_live_preview` 会**直接返回**（不白算），不一致
        或成品缺失才重算当前页。
        """
        if self.current_stage() != "rembg":
            return
        self._flush_pending_offset()
        self._apply_current_image_offset()
        self.rembg_viewer.refresh_display()
        self._live_timer.start()

    def _formal_default_algorithm(self) -> str:
        """最近一次**成功**全量执行所用的默认算法（没跑过 = Otsu）。

        逐张算法表只记用户单独改过的页；没记录的页要回到"全量的默认算法"，
        而不是把上一页的临时选择带过去。
        """
        record = self._latest_success_run("rembg")
        if not record:
            return REMBG_DEFAULT_ALGORITHM
        params = record.get("parameters") or {}
        return str(params.get("algorithm") or REMBG_DEFAULT_ALGORITHM)

    def _apply_current_image_offset(self) -> None:
        """把当前图片记录的 offset / 算法回填到面板（程序化，不算用户改动）。

        算法：有逐张记录用它，没有则回落到最近一次全量执行的默认算法
        （与 offset 的"没记录 = 0"对称）；这样从单独调过算法的页切到普通页时，
        面板不会把上一页的临时选择带过去。
        """
        task_id = self.task_id
        entry_path = self.rembg_viewer.current_entry_path()
        if not task_id or not entry_path:
            return
        panel = self.panel_host_of_step("rembg")
        if panel is None:
            return
        stem = Path(entry_path).stem
        try:
            scope = self._node_scope(self.current_node())
            offset = self.store.rembg_offset(task_id, stem, **scope)
            algorithm = str(
                self.store.load_rembg_algorithms(task_id, **scope).get(
                    stem, self._formal_default_algorithm()
                )
            )
            args = panel.get_args()
        except Exception:  # noqa: BLE001 - 读不到/面板未填好：保持原值
            return
        changed = False
        if int(args.get("offset") or 0) != int(offset):
            args["offset"] = int(offset)
            changed = True
        if str(args.get("algorithm") or "") != str(algorithm):
            args["algorithm"] = str(algorithm)
            changed = True
        if changed:
            panel.apply_args(args)

    def _live_snapshot(self, args: dict) -> dict:
        """只取「影响去底色结果」的那几个键做快照。"""
        return {key: args.get(key) for key in self.PREVIEW_PARAM_KEYS}

    def _formal_snapshot_for(self, stem: str) -> dict | None:
        """某张图片最近一次**全量执行**所用的参数（含它自己的 offset）。"""
        record = self._latest_success_run("rembg")
        if not record:
            return None
        params = record.get("parameters") or {}
        snapshot = {key: params.get(key) for key in self.PREVIEW_PARAM_KEYS}
        try:
            if "offsets" in params:
                # GUI 执行：逐张表是唯一口径，没记录的图就是 0
                snapshot["offset"] = int((params.get("offsets") or {}).get(stem, 0))
            else:
                snapshot["offset"] = int(params.get("offset", 0))
        except (TypeError, ValueError):
            snapshot["offset"] = params.get("offset", 0)
        try:
            # 算法：逐张表里有的页用它自己的值，否则用那轮全量执行的默认算法。
            fallback = str(params.get("algorithm") or REMBG_DEFAULT_ALGORITHM)
            if "algorithms" in params:
                snapshot["algorithm"] = str(
                    (params.get("algorithms") or {}).get(stem, fallback)
                )
            else:
                snapshot["algorithm"] = fallback
        except (TypeError, ValueError):
            snapshot["algorithm"] = REMBG_DEFAULT_ALGORITHM
        return snapshot

    # ---------------------------------------------------------------- 执行
    def _maybe_run_live_preview(self) -> None:
        """防抖到期：当前页盘上成品与面板参数不一致才重算。"""
        if self.current_stage() != "rembg" or not self.task_id:
            return
        # 全量任务正在跑时不要插队（worker 槽位是同一个 QProcess）
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            return
        panel = self.panel_host_of_step("rembg")
        if panel is None:
            return
        try:
            args = panel.get_args()
        except ValueError:
            return
        entry_path = self.rembg_viewer.current_entry_path()
        if not entry_path:
            return
        stem = Path(entry_path).stem
        snapshot = self._live_snapshot(args)
        applied = self._live_done.get(stem)
        # 盘上有没有这张成品：占位图/上游换了页名时，旧的全量产物里没有它，
        # 此时参数即使"一致"也必须补算，否则中间大图永远停在原图（用户 2026-10-23）。
        out_dir = self.store.node_or_stage_output(
            self.task_id, self.node_of_stage("rembg"), "rembg"
        )
        has_result = (Path(out_dir) / f"{stem}.png").exists()
        if has_result:
            if applied is None:
                # 盘上是全量执行的产物：与它所用的取值一致 ⇒ 无需重算
                if snapshot == self._formal_snapshot_for(stem):
                    return
            elif applied == snapshot:
                return  # 盘上已经是这份参数算出来的
        self._start_live_job(entry_path, args, stem)

    def _start_live_job(self, image_path: str, args: dict, stem: str) -> None:
        """派发单页任务到后台线程：去底色 → 覆盖正式成品（+ 第四步缩略图）。"""
        task_id = self.task_id
        if not task_id:
            return
        node = self.node_of_stage("rembg")
        out_dir = self.store.node_or_stage_output(task_id, node, "rembg")
        thumb_dir = self.store.rembg_thumbnails_dir(task_id, node)
        token = object()
        # 上一单还在飞就先取消（token 守卫只丢结果，省算力）
        previous = getattr(self, "_live_worker", None)
        if previous is not None and hasattr(previous, "cancel"):
            try:
                previous.cancel()
            except Exception:  # noqa: BLE001
                pass
        self._live_token = token
        self._live_pending = self._live_snapshot(args)
        # 同页左右裁图共享阈值的上下文：最近上游 detect 的 boxes.json + 逐张
        # 算法表（占位标记与"用哪种算法"都从这两处来，不靠文件名猜）。
        live_args = dict(args)
        boxes_path = self.store.nearest_boxes_path(
            task_id, node, self.imposition_effective()
        )
        if boxes_path is not None:
            live_args["_boxes_path"] = str(boxes_path)
        live_args["algorithms"] = self.store.load_rembg_algorithms(
            task_id, **self._node_scope(node)
        )
        # ⚠️ 只在**说明行**提示，**不动大图**：页面要优先显示。
        self.rembg_viewer.show_live_pending()
        worker = RembgLiveWorker(
            str(image_path), live_args, str(out_dir), str(thumb_dir), token
        )
        self._live_worker = worker
        self.run_worker(
            lambda: worker,
            lambda worker_, thread: (
                connect_queued(self, worker_.finished, self._on_live_done, thread),
                connect_queued(self, worker_.failed, self._on_live_failed, thread),
                worker_.finished.connect(thread.quit),
                worker_.failed.connect(thread.quit),
            ),
        )

    # ------------------------------------------------------------ 结果回调
    def _on_live_done(self, token, out_path: str) -> None:
        """单页结果回来：过期则丢弃，否则记账、刷新显示并通知下游。"""
        if token is not self._live_token:
            return
        if not out_path:
            return  # 被取消的那单（空路径，见 RembgLiveWorker.run）
        snapshot, self._live_pending = self._live_pending, None
        stem = Path(out_path).stem
        if snapshot is not None:
            self._live_done[stem] = snapshot
        self.rembg_viewer.refresh_display()
        # 盘上成品已换：让"吃去底色成品 / 拼版成品"的下游立刻跟上
        if self.imposition_effective():
            self._schedule_imposition_compose()
        self._refresh_print_source([out_path])

    def _on_live_failed(self, token, message: str) -> None:
        if token is not self._live_token:
            return
        self._live_pending = None
        self.log_view.append(f"实时去底色失败：{message}")

    # ---------------------------------------------------------------- 清理
    def _drop_live_results(self) -> None:
        """丢弃实时台账（全量「执行去底色」开始前调用）。

        ⚠️ **不删文件**：正式执行会按逐张偏移表重写全部页，台账跟着作废即可。
        """
        self._flush_pending_offset()
        self._live_token = None
        self._live_pending = None
        self._live_done.clear()

    def _reset_rembg_live(self) -> None:
        """切换任务时复位实时调整状态（台账与在飞令牌一并清掉）。"""
        self._flush_pending_offset()
        self._live_timer.stop()
        self._offset_save_timer.stop()
        self._algorithm_pending = None
        self._live_done.clear()
        self._live_token = None
        self._live_pending = None
