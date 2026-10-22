# -*- coding: utf-8 -*-
"""第三步「图片去底色」的实时预览控制器（计算 + **增量落盘**）。

用户改 offset / type / 印章等参数、翻页、改 area/border 时，**只重算（或重新
合成）当前页**并立刻显示，不必等「生成预览」的全量任务。

三条边界：

1. **只看当前页**。全量是「生成预览」按钮的职责。
2. **参数与「原本去底色参数」一致且已落盘**时不再重复去底色（原本参数 = 最近
   一次成功「生成预览」所用参数，或本页上一次实时预览的）。
3. **增量落盘**（2026-10-18 起，用户明确要求）：该页去底色结果写
   ``stages/rembgpreview[~节点]``，按 area/border 合成的「应用图」写
   ``stages/rembg[~节点]``。两个目录允许**不完整**。

⚠️ **显示优先、落盘异步**（用户 2026-10-18：「页面要优先显示」「落地实体文件
后端执行，不要影响前端渲染/主线程，页面先渲染出效果」）：去底色一算完就
``emit finished`` 上屏，写正式产物目录（拷预览 + 合成应用图 + 透明 PNG 编码）
在 worker 线程继续跑，**不阻塞大图**；「正在按新参数去底色…」只写在说明行，
**不清大图**。已经按当前参数去过底色的页**不二次去底色**（见下面第 2 条）。

⚠️ 由此产生的两条硬约定（护栏见 ``tests/selftests/``）：

- ``stages/rembg`` 有零星文件**不等于本步已提交**。写应用图前先落 ``.draft``
  哨兵，第四步只有在该哨兵不存在时才认这个目录（用户 2026-10-18：
  > 虽然可能 rembg 会有零星图片，但是并不表明当前步骤已经提交，
  > 必须执行提交，下一步才能使用当前步骤的图片。
  ）。
- 各页可能在不同参数下算出来：那是**临时可观**的中间态，权威产物仍由全量的
  「生成预览 + 提交」重建（二者都会 clean 整目录，增量产物随之被覆盖）。

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
    rembg_viewer / log_view / current_stage() / current_node() / run_worker /
    _latest_success_run() / PREVIEW_PARAM_KEYS / _manifest_paths() /
    _book_page_widths() / _book_profile() / _side_overrides_all() /
    _boxes_map_all() / _update_submit_button()。"""

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
        current_node: Callable[[], str | None]
        _latest_success_run: Callable[..., Any]
        _manifest_paths: Callable[[], list]
        _book_page_widths: Callable[..., dict]
        _book_profile: Callable[..., Any]
        _side_overrides_all: Callable[[], dict]
        _boxes_map_all: Callable[[], dict]
        _boxes_read_path: Callable[[], Any]
        _update_submit_button: Callable[..., None]
        #: 检测框内存缓存（宿主持 VersionedBoxCache，读 ``.version`` 做缓存键）
        detect_cache: Any
        # ⚠️ 返回值是 LazyPanelHost 或真面板（属性转发、鸭子类型），用 Any 承接
        panel_host_of_step: Callable[[str], Any]
        PREVIEW_PARAM_KEYS: Any  # 宿主从 desktop.services.rembg_live 取的键元组

    #: 参数连发时的防抖窗口（拖一次滑块会发几十次 valueChanged）
    LIVE_DEBOUNCE_MS = 350

    # ---------------------------------------------------------------- 初始化
    def _init_rembg_live(self) -> None:
        """装好实时预览状态与触发点（在 _init_ui 之后调用）。"""
        self._live_done: dict[str, dict] = {}  # stem -> 已按哪份去底色参数算过
        #: stem -> 已按哪份「参数 + area/border」落过盘（增量落盘去重用）
        self._live_persist_done: dict[str, tuple] = {}
        self._live_token: object | None = None
        self._live_pending: dict | None = None  # 正在算的那份去底色参数快照
        #: 正在落盘的那一页（stem, 落盘键）；显示那单为 None（不记账）
        self._live_persist_pending: tuple[str, tuple] | None = None
        #: 整书判据（单栏书 + 页宽 + 指定左右）的（键, 值）缓存
        self._live_book_ctx: tuple | None = None
        self.rembg_viewer.set_live_dir(None)

        # ⚠️ Mixin 本体是普通类，类型检查器看不到宿主是 QObject，故收窄后当
        #    QTimer 的 parent 用（运行时是恒等）。
        self._live_timer = QTimer(cast(QObject, self))
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(self.LIVE_DEBOUNCE_MS)
        self._live_timer.timeout.connect(self._maybe_run_live_preview)

        # 两个触发点：面板参数被改（area/border/去底参数都发）、预览区翻页
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
        """参数被改 / area-border 被改 / 翻页 → 起防抖计时（不立刻跑）。"""
        if self.current_stage() != "rembg":
            return
        self._live_timer.start()

    def _live_snapshot(self, args: dict) -> dict:
        """只取「影响去底色结果」的那几个键做快照。

        与「提交本次任务」的版本判定（``PREVIEW_PARAM_KEYS``）共用同一份定义：
        area/border 不在其中——它们只改变**显示范围 / 应用图几何**，不需要重新
        去底色（但会让应用图需要重合成，见 :meth:`_maybe_run_live_preview`）。
        """
        return {key: args.get(key) for key in self.PREVIEW_PARAM_KEYS}

    @staticmethod
    def _snapshot_key(snapshot: dict) -> tuple:
        """把参数快照收成可哈希的键（用于「已落盘」去重）。"""
        return tuple(sorted((k, str(v)) for k, v in snapshot.items()))

    def _preview_run_snapshot(self) -> dict | None:
        """最近一次成功「生成预览」所用的参数；没有成功记录时返回 None。"""
        record = self._latest_success_run("rembg")
        if not record:
            return None
        params = record.get("parameters") or {}
        return {key: params.get(key) for key in self.PREVIEW_PARAM_KEYS}

    # ---------------------------------------------------------------- 执行
    def _maybe_run_live_preview(self) -> None:
        """防抖到期：判断当前页要不要重算 / 重落盘，需要才做。"""
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
        # ⚠️ 落盘键里**不再有 area/border**（2026-10-22：去底色就是整图去底色）：
        #    参数一样 ⇒ 结果一样，不需要按几何再合成一次。
        persist_key = self._snapshot_key(snapshot)
        persisted = self._live_persist_done.get(stem) == persist_key

        base_snapshot = self._preview_run_snapshot()
        if base_snapshot is not None and snapshot == base_snapshot:
            # 参数与「生成预览」时一致 → 正式产物就是当前参数的结果：
            # 显示回到正式产物，只用它那份结果补「应用图」。
            self._drop_live_results()
            if persisted:
                return
            base = self._formal_preview_path(stem)
            if base is not None:
                self._start_live_job(entry_path, args, stem, persist_key,
                                     render=False, base=base)
            return
        if self._live_done.get(stem) == snapshot:
            # 这一页已按当前参数算过去底色 ⇒ 只需重合成「应用图」
            if persisted:
                return
            base = self._live_base_path(stem) or self._formal_preview_path(stem)
            if base is not None:
                self._start_live_job(entry_path, args, stem, persist_key,
                                     render=False, base=base)
            return
        # 参数变了 / 本页还没按当前参数算过 → 重新去底色并增量落盘
        self._start_live_job(entry_path, args, stem, persist_key, render=True)

    def _start_live_job(self, image_path: str, args: dict, stem: str,
                        persist_key: tuple, *, render: bool,
                        base: Path | None = None) -> None:
        """派发单页任务到后台线程：去底色（可选）+ 增量落盘。

        ⚠️ 作业（boxes/area/border/单栏书/命名）必须在 **GUI 线程**算好再交给
        worker——那些全是界面态（面板表单、检测缓存），子线程不得碰 QWidget，
        也不该自己去读盘重算（见 ``RembgLiveWorker`` 的参数说明）。
        """
        task_id = self.task_id
        if not task_id:
            return
        node = self.current_node()
        jobs = self._current_page_submit_jobs(stem, args)
        live = rembg_live.live_dir(task_id)
        token = object()
        self._live_token = token
        self._live_pending = self._live_snapshot(args) if render else None
        self._live_persist_pending = (stem, persist_key) if jobs else None
        if render:
            self.rembg_viewer.set_live_dir(live)
            # ⚠️ 只在**说明行**提示，**不动大图**：页面要优先显示（用户 2026-10-18）。
            self.rembg_viewer.show_live_pending()
        else:
            # 不重算去底色（本页已按当前参数算过）⇒ 立刻按现有结果显示。
            self.rembg_viewer.refresh_display()
        # 上一单还在飞就先取消（token 守卫只丢结果不省算力，审计 L2）
        previous = getattr(self, "_live_worker", None)
        if previous is not None and hasattr(previous, "cancel"):
            try:
                previous.cancel()
            except Exception:  # noqa: BLE001
                pass
        worker = RembgLiveWorker(
            str(image_path), args, str(live), token,
            render=render,
            preview_out=(
                str(self.store.node_or_stage_output(task_id, node, "rembg"))
                if render else None
            ),
            apply_out=str(
                self.store.node_or_stage_output(task_id, node, "rembg_submit")
            ),
            jobs=jobs,
            draft_marker=str(self.store.rembg_draft_marker(task_id, node)),
            base_path=str(base) if base else None,
        )
        self._live_worker = worker
        self.run_worker(
            lambda: worker,
            lambda worker_, thread: (
                connect_queued(self, worker_.finished, self._on_live_done, thread),
                connect_queued(self, worker_.failed, self._on_live_failed, thread),
                connect_queued(self, worker_.applied, self._on_live_applied, thread),
                worker_.finished.connect(thread.quit),
                worker_.failed.connect(thread.quit),
            ),
        )

    # ------------------------------------------------------------ 当前页作业
    def _current_page_submit_jobs(self, stem: str, args: dict) -> list[dict]:
        """当前页的「提交」作业（GUI 线程算）：**一条进、一条出**。

        ⚠️ 2026-10-22：去底色不再按 area/border 合成，因此这里不再需要
        ``plan_rembg_submit_entries``/``compose_region_output``——输入是哪张图，
        成品就是那张图（白底转透明），文件名沿用页名。规则与「提交本次任务」
        完全一致（见 ``submit.SubmitMixin._run_rembg_submit_unchecked``）。

        保留 jobs 形状（而不是删掉参数）是为了让 worker 侧的落盘路径不变：
        ``services.rembg_live.apply_effects`` 对 ``compose=False`` 的作业就是
        "整图转透明写盘"。
        """
        page = next(
            (p for p in self._manifest_paths() if Path(p).stem == stem), None
        )
        if page is None:
            return []
        return [{
            "file": str(page),
            "label": stem,
            "compose": False,
            "boxes": [],
            "border": None,
            "names": [f"{stem}.png"],
        }]

    def _live_book_context(self) -> tuple:
        """整书判据（单栏书结论 + 页宽 + 指定左右 + 逐页槽位），带缓存。

        ⚠️ 逐页 ``_detect_boxes_for`` 会整份重读 ``boxes.json``（O(n²)），而实时
        预览按防抖反复要它 ⇒ **必须缓存**。失效判据（证据型）：页清单 + boxes
        文件 (mtime,size) + ``detect_cache`` 版本（用户在第二步改过框也自增）。
        """
        key = self._live_book_context_key()
        cached = self._live_book_ctx
        if cached is not None and cached[0] == key:
            return cached[1]
        widths = self._book_page_widths()
        boxes_map = self._boxes_map_all()
        profile = self._book_profile(
            widths, boxes_for=lambda text: boxes_map.get(Path(text).stem, [])
        )
        sides = self._side_overrides_all()
        value = (profile.single_column_book, widths, sides, boxes_map)
        self._live_book_ctx = (key, value)
        return value

    def _live_book_context_key(self) -> tuple:
        """整书判据缓存的失效键（页清单 + boxes 文件指纹 + 缓存版本）。"""
        paths = tuple(str(p) for p in self._manifest_paths())
        boxes_path = self._boxes_read_path()
        if boxes_path is None:
            boxes_sig: tuple = ("", None, None)
        else:
            try:
                stat = Path(boxes_path).stat()
                boxes_sig = (str(boxes_path), stat.st_mtime_ns, stat.st_size)
            except OSError:  # 还没有 boxes.json：也算一种"签名"
                boxes_sig = (str(boxes_path), None, None)
        version = getattr(self.detect_cache, "version", 0)
        return (paths, boxes_sig, version)

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
        self._live_persist_pending = None
        self.log_view.append(f"实时预览失败：{message}")

    def _on_live_applied(self, token, saved: list, errors: list) -> None:
        """增量落盘结果回来：记账（去重）、打日志、刷提交按钮状态。"""
        if token is not self._live_token:
            return
        pending = self._live_persist_pending
        self._live_persist_pending = None
        if saved and pending is not None:
            stem, key = pending
            self._live_persist_done[stem] = key
            self.log_view.append(
                f"已按当前参数增量落盘：{stem}"
                f"（去底色 → stages/rembgpreview，应用图 {len(saved)} 张 → stages/rembg）"
            )
        for message in errors:
            self.log_view.append(f"实时预览落盘失败：{message}")
        if saved:
            # 应用图变了 ⇒ 「提交本次任务」按钮的版本提示要跟着刷新
            self._update_submit_button(False)

    # ------------------------------------------------------------ 路径解析
    def _formal_preview_path(self, stem: str) -> Path | None:
        """该页在正式预览目录（``stages/rembgpreview[~节点]``）里的结果。"""
        task_id = self.task_id
        if not task_id:
            return None
        base = self.store.node_or_stage_output(task_id, self.current_node(), "rembg")
        for ext in ("png", "jpg", "jpeg"):
            candidate = base / f"{stem}.{ext}"
            if candidate.exists():
                return candidate
        return None

    def _live_base_path(self, stem: str) -> Path | None:
        """该页在实时暂存目录里的去底色结果（已按当前参数算过时才有）。"""
        live = self.rembg_viewer.live_dir
        if live is None:
            return None
        candidate = Path(live) / f"{stem}.png"
        return candidate if candidate.exists() else None

    # ---------------------------------------------------------------- 清理
    def _drop_live_results(self) -> None:
        """丢弃实时结果，让预览区回到「生成预览」的正式产物。

        ⚠️ **不清** ``_live_persist_done``：那份记账说的是"正式目录里已落过
        什么"，与临时结果无关（清它会让每次触发都重合成一遍应用图）。
        """
        if not self._live_done and self.rembg_viewer.live_dir is None:
            return
        self._live_done.clear()
        self._live_token = None
        self._live_pending = None
        self._live_persist_pending = None
        self.rembg_viewer.set_live_dir(None)
        if self.task_id:
            rembg_live.reset(self.task_id)
        self.rembg_viewer.refresh_display()

    def _reset_rembg_live(self) -> None:
        """切换任务时复位实时预览（临时目录与记账一并清掉）。"""
        self._live_timer.stop()
        self._live_done.clear()
        self._live_persist_done.clear()
        self._live_book_ctx = None
        self._live_token = None
        self._live_pending = None
        self._live_persist_pending = None
        if self.task_id:
            rembg_live.reset(self.task_id)
        self.rembg_viewer.set_live_dir(None)
