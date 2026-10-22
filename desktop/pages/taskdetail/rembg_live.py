# -*- coding: utf-8 -*-
"""第三步「图片去底色」的实时预览控制器（单页、只显示）。

用户改 offset / type / 印章等参数或翻页时，**只重算当前页**并立刻上屏，
不必等「执行去底色」全量任务。

与正式执行的分工：

- **「执行去底色」**：全量写 ``stages/rembg``（正式成品）；
- **本模块**：只算当前页、只写系统临时目录，供查看器临时显示。

参数与最近一次成功执行一致时，直接回到正式成品显示，不重复计算。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

from PySide6.QtCore import QObject, QProcess, QTimer

from desktop.services import rembg_live
from desktop.workers import RembgLiveWorker, connect_queued

if TYPE_CHECKING:
    from desktop.components.viewers import RembgPreviewWidget
    from desktop.store.store import TaskStore


class RembgLiveMixin:
    """依赖宿主页面提供：store / task_id / process / rembg_viewer /
    current_stage() / current_node() / run_worker / _latest_success_run() /
    panel_host_of_step()。"""

    if TYPE_CHECKING:
        store: TaskStore
        task_id: str | None
        process: QProcess | None
        rembg_viewer: "RembgPreviewWidget"
        log_view: Any
        run_worker: Callable[..., Any]
        current_stage: Callable[[], str]
        current_node: Callable[[], str | None]
        _latest_success_run: Callable[..., Any]
        panel_host_of_step: Callable[[str], Any]

    #: 参数连发时的防抖窗口（拖一次滑块会发几十次 valueChanged）
    LIVE_DEBOUNCE_MS = 350

    #: 影响去底色结果的参数（与正式执行共用一份口径）。
    PREVIEW_PARAM_KEYS = (
        "type", "offset", "seal", "sealcolor", "sealarea", "sealmin_sat",
    )

    # ---------------------------------------------------------------- 初始化
    def _init_rembg_live(self) -> None:
        """装好实时预览状态与触发点（在 _init_ui 之后调用）。"""
        self._live_done: dict[str, dict] = {}  # stem -> 已按哪份参数算过
        self._live_token: object | None = None
        self._live_pending: dict | None = None
        self.rembg_viewer.set_live_dir(None)

        # ⚠️ Mixin 本体是普通类，类型检查器看不到宿主是 QObject，故收窄后当
        #    QTimer 的 parent 用（运行时是恒等）。
        self._live_timer = QTimer(cast(QObject, self))
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(self.LIVE_DEBOUNCE_MS)
        self._live_timer.timeout.connect(self._maybe_run_live_preview)

        # 两个触发点：面板参数被改、预览区翻页。
        # ⚠️ 面板是惰性的：挂 created 回调，等它真被建好再接。
        rembg_host = self.panel_host_of_step("rembg")
        if rembg_host is not None:
            add_hook = getattr(rembg_host, "add_created_hook", None)
            if callable(add_hook):
                add_hook(
                    lambda panel: panel.param_edited.connect(self._on_live_trigger)
                )
            else:
                rembg_host.param_edited.connect(self._on_live_trigger)
        self.rembg_viewer.current_changed.connect(self._on_live_trigger)

    # ---------------------------------------------------------------- 触发
    def _on_live_trigger(self, *_args) -> None:
        """参数被改 / 翻页 → 起防抖计时（不立刻跑）。"""
        if self.current_stage() != "rembg":
            return
        self._live_timer.start()

    def _live_snapshot(self, args: dict) -> dict:
        """只取「影响去底色结果」的那几个键做快照。"""
        return {key: args.get(key) for key in self.PREVIEW_PARAM_KEYS}

    def _preview_run_snapshot(self) -> dict | None:
        """最近一次成功「执行去底色」所用的参数；没有成功记录时返回 None。"""
        record = self._latest_success_run("rembg")
        if not record:
            return None
        params = record.get("parameters") or {}
        return {key: params.get(key) for key in self.PREVIEW_PARAM_KEYS}

    # ---------------------------------------------------------------- 执行
    def _maybe_run_live_preview(self) -> None:
        """防抖到期：判断当前页要不要重算，需要才做。"""
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
        snapshot = self._live_snapshot(args)
        entry_path = self.rembg_viewer.current_entry_path()
        if not entry_path:
            return
        stem = Path(entry_path).stem
        base_snapshot = self._preview_run_snapshot()
        if base_snapshot is not None and snapshot == base_snapshot:
            # 参数与正式执行一致 → 显示正式成品，收起临时结果
            self._drop_live_results()
            return
        if self._live_done.get(stem) == snapshot:
            # 这一页已按当前参数算过：直接刷回它
            self.rembg_viewer.refresh_display()
            return
        self._start_live_job(entry_path, args, stem)

    def _start_live_job(self, image_path: str, args: dict, stem: str) -> None:
        """派发单页任务到后台线程：去底色 → 临时目录。"""
        task_id = self.task_id
        if not task_id:
            return
        live = rembg_live.live_dir(task_id)
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
        self.rembg_viewer.set_live_dir(live)
        # ⚠️ 只在**说明行**提示，**不动大图**：页面要优先显示。
        self.rembg_viewer.show_live_pending()
        worker = RembgLiveWorker(str(image_path), args, str(live), token)
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
        """单页结果回来：过期则丢弃，否则记住"这页已按该参数算过"并刷新显示。"""
        if token is not self._live_token:
            return
        if not out_path:
            return  # 被取消的那单（空路径，见 RembgLiveWorker.run）
        if self._live_pending is not None:
            self._live_done[Path(out_path).stem] = self._live_pending
        self._live_pending = None
        self.rembg_viewer.refresh_display()

    def _on_live_failed(self, token, message: str) -> None:
        if token is not self._live_token:
            return
        self._live_pending = None
        self.log_view.append(f"实时预览失败：{message}")

    # ---------------------------------------------------------------- 清理
    def _drop_live_results(self) -> None:
        """丢弃临时结果，让预览区回到「执行去底色」的正式成品。"""
        if not self._live_done and self.rembg_viewer.live_dir is None:
            return
        self._live_done.clear()
        self._live_token = None
        self._live_pending = None
        self.rembg_viewer.set_live_dir(None)
        if self.task_id:
            rembg_live.reset(self.task_id)
        self.rembg_viewer.refresh_display()

    def _reset_rembg_live(self) -> None:
        """切换任务时复位实时预览（临时目录与记账一并清掉）。"""
        self._live_timer.stop()
        self._live_done.clear()
        self._live_token = None
        self._live_pending = None
        if self.task_id:
            rembg_live.reset(self.task_id)
        self.rembg_viewer.set_live_dir(None)
