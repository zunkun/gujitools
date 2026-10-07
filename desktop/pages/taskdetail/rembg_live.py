# -*- coding: utf-8 -*-
"""第三步「图片去底色」的实时预览控制器。

用户改 offset / type / 印章等参数时，**只重算当前页**并立刻显示，不必等
「生成预览」的全量任务；预览区翻页时，若那一页还没按当前参数算过，也算它。

三条边界（都是刻意的）：

1. **只在参数与「原本去底色参数」不同时才重算**。原本参数 = 最近一次成功
   「生成预览」所用的参数；一致就说明正式产物就是当前参数的结果，直接用它，
   不做无谓计算。
2. **一次只算一页**。全量是「生成预览」按钮的职责。
3. **只影响显示，不落正式产物**。结果写系统临时目录（``services.rembg_live``），
   绝不碰 ``stages/rembgpreview`` —— 那里一旦被单页结果覆盖，「提交本次任务」
   就会把不同参数下算出来的图混在一起。

滑块拖动时 ``valueChanged`` 会连发，所以统一走 ``LIVE_DEBOUNCE_MS`` 防抖；
每次请求带 token，迟到的旧结果直接丢弃（否则慢的旧结果会盖掉新的）。
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
    """依赖宿主页面提供：store / task_id / process / control_stack /
    rembg_viewer / log_view / current_stage() / run_worker /
    _latest_success_run() / PREVIEW_PARAM_KEYS。"""

    if TYPE_CHECKING:
        # 宿主 TaskDetailPage（或同级 Mixin）提供的属性/方法：Mixin 本体不持有，
        # 这里只做类型声明（类级注解、无赋值），运行时零副作用。
        store: TaskStore
        task_id: str | None
        process: QProcess | None
        rembg_viewer: RembgPreviewWidget
        log_view: Any  # 宿主 log_panel 里的 QTextEdit（.append 取用）
        run_worker: Callable[..., Any]
        current_stage: Callable[[], str]
        _latest_success_run: Callable[..., Any]
        # ⚠️ 返回值是 LazyPanelHost 或真面板（属性转发、鸭子类型），用 Any 承接
        panel_host_of_step: Callable[[str], Any]
        PREVIEW_PARAM_KEYS: Any  # 宿主从 desktop.services.rembg_live 取的键元组

    #: 参数连发时的防抖窗口（拖一次滑块会发几十次 valueChanged）
    LIVE_DEBOUNCE_MS = 350

    # ---------------------------------------------------------------- 初始化
    def _init_rembg_live(self) -> None:
        """装好实时预览状态与触发点（在 _init_ui 之后调用）。"""
        self._live_done: dict[str, dict] = {}  # stem -> 已按哪份参数算过
        self._live_token: object | None = None
        self._live_pending: dict | None = None  # 正在算的那份参数快照
        self.rembg_viewer.set_live_dir(None)

        # ⚠️ Mixin 本体是普通类，类型检查器看不到宿主是 QObject，故收窄后当
        #    QTimer 的 parent 用（运行时是恒等）。
        self._live_timer = QTimer(cast(QObject, self))
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(self.LIVE_DEBOUNCE_MS)
        self._live_timer.timeout.connect(self._maybe_run_live_preview)

        # 两个触发点：面板参数被改（只对 rembg 面板）、预览区翻页
        # ⚠️ 第三步面板是**惰性**的：这里绝不能直接 `widget(2).param_edited`
        # （属性转发会立刻把面板建出来）。挂 created 回调，等它真被建好再接。
        # ⚠️ 流程里没有「图片去底色」这一格时没有面板可挂（自定义流程合法），
        #    直接跳过——此时实时预览本来也跑不起来（``_on_live_trigger`` 第一句
        #    就要求 ``current_stage() == "rembg"``）。
        rembg_host = self.panel_host_of_step("rembg")
        if rembg_host is None:
            self.rembg_viewer.current_changed.connect(self._on_live_trigger)
            return
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
        """只取「影响去底色结果」的那几个键做快照。

        与「提交本次任务」的版本判定（``PREVIEW_PARAM_KEYS``）共用同一份定义：
        area/border 不在其中——它们只改变**显示范围**，不需要重新去底色。
        """
        return {key: args.get(key) for key in self.PREVIEW_PARAM_KEYS}

    def _preview_run_snapshot(self) -> dict | None:
        """最近一次成功「生成预览」所用的参数；没有成功记录时返回 None。"""
        record = self._latest_success_run("rembg")
        if not record:
            return None
        params = record.get("parameters") or {}
        return {key: params.get(key) for key in self.PREVIEW_PARAM_KEYS}

    # ---------------------------------------------------------------- 执行
    def _maybe_run_live_preview(self) -> None:
        """防抖到期：判断当前页是否需要重算，需要才算。"""
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

        base = self._preview_run_snapshot()
        if base is not None and snapshot == base:
            # 参数与「生成预览」时一致 → 正式产物已是当前参数的结果
            self._drop_live_results()
            return

        entry_path = self.rembg_viewer.current_entry_path()
        if not entry_path:
            return
        if self._live_done.get(Path(entry_path).stem) == snapshot:
            return  # 这一页已按当前参数算过
        self._start_live_render(entry_path, args, snapshot)

    def _start_live_render(self, image_path: str, args: dict, snapshot: dict) -> None:
        """派发单页去底色到后台线程，结果写实时暂存目录。"""
        # 实时暂存目录按任务归属；没有任务就没有落点（调用方都在任务态进这里）
        task_id = self.task_id
        if not task_id:
            return
        live = rembg_live.live_dir(task_id)
        token = object()
        self._live_token = token
        self._live_pending = snapshot
        self.rembg_viewer.set_live_dir(live)
        self.rembg_viewer.show_live_pending()
        # 上一单还在飞就先取消（token 守卫只丢结果不省算力，审计 L2）
        previous = getattr(self, "_live_worker", None)
        if previous is not None and hasattr(previous, "cancel"):
            try:
                previous.cancel()
            except Exception:  # noqa: BLE001
                pass
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
        """丢弃实时结果，让预览区回到「生成预览」的正式产物。"""
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
        """切换任务时复位实时预览（临时目录里的旧图一并清掉）。"""
        self._live_timer.stop()
        self._live_done.clear()
        self._live_token = None
        self._live_pending = None
        if self.task_id:
            rembg_live.reset(self.task_id)
        self.rembg_viewer.set_live_dir(None)
