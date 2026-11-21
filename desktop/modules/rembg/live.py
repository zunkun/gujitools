# -*- coding: utf-8 -*-
"""独立「去底色」页的**单页实时调整**：改参数 → 当前这张图立刻重算并上屏。

为什么独立页此前没有这个能力（用户 2026-11-21 提出）：

任务流程第三步有 :class:`~desktop.pages.taskdetail.rembg_live.RembgLiveMixin`，
它把草稿写进 ``tasks/<任务号>/preview/rembg[~节点]/``——那个路径的前提是**有
任务号**。独立功能页没有任务，于是这条链整条空着：用户调阈值偏移必须点
「开始去底色」跑完整批，才看得到效果。

本模块把同一件事接到独立页上，差别只有**草稿落在哪**：

- 任务流程：``tasks/<任务号>/preview/rembg[~节点]/``（随任务删除）；
- 独立页：``singletask/<独立功能>/preview/<源名-指纹>/``（随换源丢弃）。

两条线共用同一份计算与口径：

- 算法：``services/rembg_live.render_page``（与正式阶段同源）；
- 参数键：``services/rembg_live.REMBG_PREVIEW_PARAM_KEYS``（唯一一份）。

⚠️ **独立页是"没任务"的形态，草稿绝不能写进产物输出目录**：用户点「开始
去底色」之前，那些图还不该出现在产物里（否则"没执行却已经有结果"）。草稿目录
只服务预览控件（``RembgPreviewWidget`` 的 ``preview_dir``）。

⚠️ 触发闸：只有**用户改过参数**（``panels/base.py::param_edited``）之后才给
翻页/切图补算。没改参数时行为与改造前完全一致（显示上次执行结果 / 原图），
不会因为"翻了一下页"就凭空多算一张、也不会让用户误以为已经执行过。
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QTimer

from desktop.services.rembg_live import REMBG_PREVIEW_PARAM_KEYS

if TYPE_CHECKING:
    from desktop.components.viewers import RembgPreviewWidget
    from desktop.steps.control import StepControl


#: 参数连发时的防抖窗口（拖一次滑块会发几十次 valueChanged）。
#: 比任务流程的 350ms 略短：独立页是"边看边调"，用户更容易在调完的下一秒就
#: 期待画面变化。
LIVE_DEBOUNCE_MS = 300


def _snapshot(args: dict) -> dict:
    """只取「影响去底色结果」的那几个键做快照（与任务流程同一口径）。"""
    return {key: args.get(key) for key in REMBG_PREVIEW_PARAM_KEYS}


class RembgModuleLiveMixin:
    """依赖宿主（``RembgModulePage``）提供：

    ``control`` / ``viewer`` / ``log`` / ``SPEC`` / ``source_images()`` /
    ``run_worker()`` / ``shutdown_workers()``。
    """

    if TYPE_CHECKING:
        control: StepControl
        viewer: "RembgPreviewWidget"
        #: 宿主页面认领的步骤元数据（这里只要 ``disk_key()``，用 Any 免得把
        #: ``StepSpec`` 拖进本模块的类型依赖）
        SPEC: Any

        def log(self, text: str) -> None: ...

        def source_images(self) -> list[Path]: ...

        def run_worker(self, factory, wire): ...

    # ---------------------------------------------------------------- 初始化
    def _init_module_live(self) -> None:
        """装好触发点与状态（必须在 ``super().__init__()`` 之后调用）。

        触发点两个，与任务流程第三步同构：

        - 面板参数被改（``param_edited``）→ 记"用户动过参数"并起防抖；
        - 预览翻页（``current_changed``）→ 用户动过参数时给这一页补算。
        """
        #: stem → 该页草稿是按哪份参数算出来的（内存台账，换源即清）
        self._live_done: dict[str, dict] = {}
        #: 在飞任务的令牌：只有最新一次的 results 允许上屏
        self._live_token: object | None = None
        self._live_pending: dict | None = None
        #: 当前这批源图的草稿目录（无源时为 ``None``）
        self._live_dir: Path | None = None
        #: 用户动过参数没有（见模块 docstring 的"触发闸"）
        self._live_dirty = False

        self._live_timer = QTimer(self)  # type: ignore[arg-type]  # 宿主是 QWidget
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(LIVE_DEBOUNCE_MS)
        self._live_timer.timeout.connect(self._maybe_live_preview)

        panel = self.control.panel
        if panel is not None:
            panel.param_edited.connect(self._on_live_trigger)  # type: ignore[attr-defined]
        self.viewer.current_changed.connect(self._on_live_page_changed)
        # 全量执行开始时草稿作废（正式阶段会重写全部页）
        self.control.running_changed.connect(self._on_live_running)

    # ------------------------------------------------------------------ 触发
    def _on_live_trigger(self, *_args) -> None:
        """用户改了面板参数：记"动过参数"并起防抖（不立即算）。"""
        if self._live_dir is None:
            return
        self._live_dirty = True
        self._live_timer.start()

    def _on_live_page_changed(self, *_args) -> None:
        """翻页：用户动过参数就给这一页补算（草稿已是最新则自动跳过）。"""
        if self._live_dir is None or not self._live_dirty:
            return
        self._live_timer.start()

    # ------------------------------------------------------------------ 计算
    def _maybe_live_preview(self) -> None:
        """防抖到期：当前页的草稿与面板参数不一致才重算。"""
        live_dir = self._live_dir
        if live_dir is None:
            return
        # 全量执行在跑时不插队（执行线程与预览 worker 抢同一块磁盘/CPU）
        if self.control.busy():
            return
        entry_path = self.viewer.current_entry_path()
        if not entry_path:
            return
        try:
            args = self.control.args()
        except Exception:  # noqa: BLE001 - 参数填了一半（如 w/k 非法）：等用户填完再算
            return
        stem = Path(entry_path).stem
        snapshot = _snapshot(args)
        draft = live_dir / f"{stem}.png"
        if draft.is_file() and self._live_done.get(stem) == snapshot:
            return  # 这份参数已经算过（草稿就是它）
        self._start_live_job(entry_path, args, stem, snapshot)

    def _start_live_job(
        self, image_path: str, args: dict, stem: str, snapshot: dict
    ) -> None:
        """派发单页任务到后台线程：去底色 → **只写预览草稿**。"""
        from desktop.workers import RembgLiveWorker, connect_queued

        live_dir = self._live_dir
        if live_dir is None:
            return
        live_dir.mkdir(parents=True, exist_ok=True)
        token = object()
        # 上一单还在飞就先取消（令牌守卫只丢结果，这里让它尽早返回省算力）
        previous = getattr(self, "_live_worker", None)
        if previous is not None and hasattr(previous, "cancel"):
            try:
                previous.cancel()
            except Exception:  # noqa: BLE001 - 取消失败不影响新任务
                pass
        self._live_token = token
        self._live_pending = snapshot
        # 只在下方说明行提示，不动大图（算完再换）
        self.viewer.show_live_pending()
        # 草稿目录已随换源设好；执行过一轮后 preview 源可能被打回正式产物，
        # 这里重新挂上（只换来源、不重建条目）
        self.viewer.set_preview_dir(live_dir)
        # thumb_dir 传 None：预览不得写下游的缩略图缓存
        worker = RembgLiveWorker(
            str(image_path), dict(args), str(live_dir), None, token
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

    def _on_live_done(self, token, out_path: str) -> None:
        """单页结果回来：过期则丢弃，否则记账并刷新这一页。"""
        if token is not self._live_token:
            return
        if not out_path:
            return  # 被取消的那单（空路径，见 RembgLiveWorker.run）
        snapshot, self._live_pending = self._live_pending, None
        stem = Path(out_path).stem
        if snapshot is not None:
            self._live_done[stem] = snapshot
        self.viewer.refresh_display()

    def _on_live_failed(self, token, message: str) -> None:
        if token is not self._live_token:
            return
        self._live_pending = None
        self.log(f"实时去底色失败：{message}")

    # ------------------------------------------------------------ 全量执行闸
    def _on_live_running(self, running: bool) -> None:
        """「开始去底色」开跑：草稿整体丢弃，左栏改看正式产物。

        ⚠️ 必须**删掉草稿文件**（不是只清台账）：草稿目录里留着旧参数的图，
        执行结束后用户再翻页就会看到"执行前的旧效果盖在正式产物上"。
        正式产物目录一个字节都不动。
        """
        if not running:
            return
        self._live_timer.stop()
        self._live_token = None
        self._live_pending = None
        self._live_done.clear()
        self._live_dirty = False
        self._drop_live_drafts()
        dest = self.control.output()
        if dest is not None:
            # 边跑边看正式产物（同时把 preview 源摘掉）
            self.viewer.set_result_dir(dest)

    def _drop_live_drafts(self) -> None:
        """清空当前源的草稿文件（只删自己目录里的 png）。"""
        live_dir = self._live_dir
        if live_dir is None or not live_dir.is_dir():
            return
        for path in live_dir.glob("*.png"):
            try:
                path.unlink()
            except OSError:
                pass
        # 草稿目录里可能还留着 `.part`（进程被杀时的残片）
        for path in live_dir.glob("*.part"):
            try:
                path.unlink()
            except OSError:
                pass

    # ---------------------------------------------------------------- 换源/收尾
    def _reset_module_live(self, source) -> None:
        """换源：草稿目录跟着换，旧目录连同台账一起丢弃。

        ``source`` 为 ``None``（用户清空输入）时只是把状态收干净。

        ⚠️ 目录名带**源指纹**（源名 + 路径哈希）：两个不同文件夹里的同名
        ``1.png`` 不会互相串（草稿是按 ``<stem>.png`` 命名的）。
        """
        # 控件的 source_changed 理论上只在构造之后发；这里仍按"可能还没接线"
        # 写（missing_ok 式取法），构造期万一早到一次也不会 AttributeError。
        timer = getattr(self, "_live_timer", None)
        if timer is not None:
            timer.stop()
        self._live_token = None
        self._live_pending = None
        self._live_done.clear()
        self._live_dirty = False
        previous, self._live_dir = self._live_dir, None
        if previous is not None and source is not None:
            new_dir = self._live_dir_for(source)
            if new_dir != previous:
                # 只删本页上一批源自己的草稿目录（不是用户的任何文件）
                shutil.rmtree(previous, ignore_errors=True)
            self._live_dir = new_dir
            return
        if previous is not None:
            shutil.rmtree(previous, ignore_errors=True)
        if source is not None:
            self._live_dir = self._live_dir_for(source)

    def _live_dir_for(self, source) -> Path:
        """某批源图的草稿目录：``singletask/<独立功能>/preview/<名-指纹>``。"""
        base = self._live_root()
        path = Path(source)
        name = self._safe_name(path.name or path.stem or "source")
        digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:8]
        return base / f"{name}-{digest}"

    def _live_root(self) -> Path:
        """草稿根目录（自测替换这一个方法就能把整批草稿挪进临时区）。"""
        from desktop.utils.files import singletask_dir

        spec = self.SPEC
        key = str(getattr(spec, "disk_key", lambda: "rembg")())
        return singletask_dir(key) / "preview"

    @staticmethod
    def _safe_name(name: str) -> str:
        """源名 → 安全的目录名片段（Windows 不允许 ``\\ / : * ? " < > |``）。"""
        cleaned = "".join(
            "_" if char in '\\/:*?"<>|' else char for char in str(name)
        ).strip(" .")
        return (cleaned or "source")[:32]

    def _shutdown_module_live(self) -> None:
        """收尾：停掉防抖、作废在飞任务。"""
        self._live_timer.stop()
        self._live_token = None
        self._live_pending = None


__all__ = ["LIVE_DEBOUNCE_MS", "RembgModuleLiveMixin"]
