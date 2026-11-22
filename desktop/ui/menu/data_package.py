# -*- coding: utf-8 -*-
"""「去底色数据包」检查 + 下载控制器（自 ``desktop/ui/menu.py`` 拆出）。"""

from __future__ import annotations

from desktop.components.dialog_shell import shell_dialog
from desktop.ui.toast import show_toast
from desktop.workers import connect_queued
from utils.data_package import has_update, read_local_version, resolve_weights

from ._qt import QAction, QDialog, QObject, QTimer, Signal
from .constants import (
    ACTION_DATA_PACKAGE,
    ACTION_DATA_PACKAGE_BUSY,
    ACTION_DATA_PACKAGE_DOWNLOADING,
    ACTION_DATA_PACKAGE_TOOLTIP,
    BUTTON_CANCEL,
    BUTTON_DOWNLOAD,
    FAILURE_REASONS,
    NEW_VERSION_SUFFIX,
    RESULT_LATEST,
    RESULT_NEWER,
)
from .panels import _DownloadProgress, _MessagePanel
from .verdicts import UpdateVerdict, data_package_result

# ------------------------------------------------------------------ 去底色数据包
class DataPackageController(QObject):
    """「去底色数据包」检查 + 下载的编排者（与 :class:`UpdateController` 各管一摊）。

    流程（用户 2026-10-16）：读权重仓库 ``database`` release 的 ``data.json`` →
    与本机**已装版本**比大小（``utils.data_package``）→ 有新版弹「下载」提示 →
    经最快线路**在程序内下载并启用**（文件保留发布名 ``bookcontent-v105.pt``，
    由 ``bookcontent.version.json`` 决定哪一份生效）——而不是让用户自己去 GitHub
    下。检查与下载都在子线程（``window.run_worker``），重入防护
    （``_checking`` / ``_downloading``）与收尾幂等沿用 UpdateController。

    ⚠️ 例外（用户 2026-10-22）：本机**一份权重都没有**时，启动期那次静默检查
    会**直接下载**（不再只挂个"有新版本"提示）——没有权重检测根本跑不起来。
    """

    #: 顶部提示条文案（空串 = 清掉这条提示；用户 2026-11-02）
    notify = Signal(str)

    def __init__(self, window, action: QAction, parent=None):
        super().__init__(parent if parent is not None else window)
        self.window = window
        self.action = action
        #: 检查在途标记（菜单项置灰 + 文案）
        self._checking = False
        #: 下载在途标记（与检查分开：下载期间菜单项也置灰）
        self._downloading = False
        #: 静默模式（启动时后台自动查）：不弹窗，只把"有新版本"挂到菜单项上
        self._silent = False
        #: 这次静默检查是否**自动下载并替换**（设置页「自动更新数据包」，2026-11-02）
        self._auto = False
        #: 当前这次下载是**自动**发起的（不弹进度窗/结果窗，只更新顶部提示条）
        self._auto_download = False
        #: 用户点了检查窗的「取消」：结果回来时静默丢弃
        self._aborted = False
        #: 上一次成功的检查结果（含 info 与 download_url；「下载」用它）
        self._last: dict | None = None
        #: 本次检查开始时"本机一份权重都没有"（决定静默检查是否直接下载）
        self._missing_weights = False
        #: 已知的新版数据包版本号（0 = 未知/已是最新）——菜单项文案与 tooltip 看它
        self._newer_version = 0
        self._check_dialog: QDialog | None = None
        #: 下载进度窗（_DownloadProgress；没有下载在跑时为 None）
        self._progress: _DownloadProgress | None = None
        #: 当前下载 worker（``_cancel_download`` 要调它的 ``cancel``）
        self._download: dict = {}

    # ---- 触发 ----
    def check(self) -> None:
        """查一次数据包最新版：**先弹「正在检查」窗，再弹结果窗**。"""
        if self._checking:
            if self._silent:
                self._silent = False
                self._auto = False
                self._present_checking()
                return
            show_toast(
                self.window, "info", "正在检查数据包", "上一次检查还没结束，请稍候。"
            )
            return
        if self._downloading:
            show_toast(self.window, "info", "正在下载数据包", "下载进行中，请稍候。")
            return
        self._silent = False
        self._auto = False
        self._aborted = False
        self.action.setEnabled(False)
        self.action.setText(ACTION_DATA_PACKAGE_BUSY)
        self._present_checking()
        self._start_check()

    def check_silently(self, auto: bool = False) -> None:
        """**后台静默**检查一次（启动时自动跑）：不弹窗，有新版才挂菜单提示。

        ``auto``（用户 2026-11-02）：有新版时**自动下载并替换**（不弹进度窗），
        由启动接线按设置页的「自动更新数据包」传入；默认 ``False`` 保持旧口径。
        """
        if self._checking or self._downloading:
            return
        self._silent = True
        self._auto = bool(auto)
        self._aborted = False
        self._start_check()

    def _start_check(self) -> None:
        """起一次后台检查（显式/静默共用）。"""
        self._checking = True
        # 本机**一份权重都没有**（没装过 / 被删了 / 安装损坏）时，光告诉用户
        # "有新版本"没有意义——检测根本跑不起来，得直接把权重下下来
        # （用户 2026-10-22：bookcontent.pt 也不存在则线上下载最新）。
        self._missing_weights = resolve_weights() is None
        # ⚠️ 惰性 import：启动期不该为一个"用户可能不点"的菜单项拉进网络模块。
        from desktop.workers.data_package_worker import DataCheckWorker

        self.window.run_worker(
            DataCheckWorker,
            lambda worker, thread: (
                connect_queued(self.window, worker.checked, self._on_checked, thread),
                connect_queued(self.window, worker.failed, self._on_failed, thread),
                connect_queued(
                    self.window,
                    thread.finished,
                    lambda *_: self._finish(),
                ),
            ),
        )

    # ---- 「正在检查」窗（先出） ----
    def _present_checking(self) -> None:
        """弹「正在检查数据包」窗（非模态；按钮是「取消」，点了丢掉这次结果）。"""
        panel = _MessagePanel("正在查询最新数据包......")
        dialog = shell_dialog(
            "正在检查数据包…",
            panel,
            self.window,
            size=(620, 180),
            ok_text=BUTTON_CANCEL,
            show_cancel=False,
            on_ok=self._abort_check,
        )
        self._check_dialog = dialog
        dialog.show()

    def _close_check_dialog(self) -> None:
        dialog = self._check_dialog
        self._check_dialog = None
        if dialog is not None:
            dialog.close()

    def _abort_check(self) -> None:
        """用户点了「取消」：关窗 + 丢掉这次结果（不掐断已发出的请求）。"""
        self._aborted = True
        self._close_check_dialog()
        self._finish()

    # ---- 检查结果 ----
    def _on_checked(self, payload) -> None:
        """拿到 data.json 结果：与本机已装版本比大小，决定"已是最新 / 有新版"。"""
        self._finish()
        self._close_check_dialog()
        if self._aborted:
            self._last = None
            return
        self._last = dict(payload or {})
        info = self._last.get("info") or {}
        remote = int(info.get("version") or 0)
        local = read_local_version()
        kind = RESULT_NEWER if has_update(remote, local) else RESULT_LATEST
        if self._silent:
            if kind == RESULT_NEWER and self._missing_weights:
                # 本机一份权重都没有 ⇒ 检测根本跑不起来，别只挂个"有新版本"提示
                # 让用户自己点：直接下（有进度窗，失败会弹原因）。
                self._newer_version = remote
                self._apply_action_text()
                self.notify.emit(f"本机缺少去底色数据包，正在自动下载 v{remote}…")
                self._start_download(auto=self._auto)
                return
            # 菜单提示：有新版才挂后缀；已是最新就清掉（别留成"鬼影"）。
            self._newer_version = remote if kind == RESULT_NEWER else 0
            self._apply_action_text()
            if kind != RESULT_NEWER:
                self.notify.emit("")      # 顶部提示条一并清掉
                return
            # 顶部提示条（用户 2026-11-02）：自动更新开着就顺手下载并替换。
            if self._auto:
                self.notify.emit(
                    f"发现新版本数据包 v{remote}，正在后台自动下载并替换…"
                )
                self._start_download(auto=True)
            else:
                self.notify.emit(
                    f"发现新版本数据包 v{remote}，可在「帮助 → 更新数据包」中下载。"
                )
            return
        self._present(data_package_result(kind, current=local, latest=self._last))

    def _on_failed(self, kind) -> None:
        """检查失败：静默模式什么都不做；显式模式关窗后给中文原因。"""
        self._finish()
        self._close_check_dialog()
        if self._aborted:
            return
        self._last = None
        if self._silent:
            # 启动时那次自动检查失败：安静收场，也不清掉已有的"有新版本"提示。
            return
        self._present(data_package_result(str(kind), current=read_local_version()))

    # ---- 菜单项文案 ----
    def _action_text(self) -> str:
        if self._downloading:
            return ACTION_DATA_PACKAGE_DOWNLOADING
        if self._newer_version:
            return f"{ACTION_DATA_PACKAGE}{NEW_VERSION_SUFFIX}"
        return ACTION_DATA_PACKAGE

    def _apply_action_text(self) -> None:
        self.action.setText(self._action_text())
        self.action.setToolTip(
            f"已发现新版本数据包 v{self._newer_version}，点这里下载并启用"
            if self._newer_version
            else ACTION_DATA_PACKAGE_TOOLTIP
        )

    def _finish(self) -> None:
        """解除检查忙标记并恢复菜单项（**幂等**）。"""
        if not self._checking:
            return
        self._checking = False
        self.action.setEnabled(True)
        self._apply_action_text()

    # ---- 结果弹窗（有新版时主按钮「下载」） ----
    def _present(self, verdict: UpdateVerdict) -> None:
        panel = _MessagePanel(verdict.body, verdict.link)
        is_download = verdict.ok_text == BUTTON_DOWNLOAD
        holder: dict = {}
        on_ok = None
        if is_download:
            def _go() -> None:
                dialog = holder.get("dialog")
                if dialog is not None:
                    dialog.done(0)
                QTimer.singleShot(0, self._start_download)

            on_ok = _go
        dialog = shell_dialog(
            verdict.title, panel, self.window,
            size=(640, 120),
            ok_text=verdict.ok_text,
            cancel_text=BUTTON_CANCEL,
            show_cancel=is_download,
            on_ok=on_ok,
        )
        holder["dialog"] = dialog
        dialog.adjustSize()
        dialog.exec()

    # ---- 下载 ----
    def _start_download(self, auto: bool = False) -> None:
        """开下载：弹进度窗 + 起 :class:`DataDownloadWorker`（子线程）。

        ``auto=True``（用户 2026-11-02）：启动时自动更新发起的下载**不弹进度窗**，
        结果只写顶部提示条；``False`` 是用户点「下载」的显式流程。
        """
        payload = self._last or {}
        info = payload.get("info") or {}
        url = str(payload.get("download_url") or "")
        if not url:
            return
        self._downloading = True
        self._auto_download = bool(auto)
        self.action.setEnabled(False)
        self.action.setText(ACTION_DATA_PACKAGE_DOWNLOADING)
        self._progress = None
        if not auto:
            self._progress = _DownloadProgress(
                self.window, "正在下载并启用去底色数据包", self._cancel_download)

        from desktop.workers.data_package_worker import DataDownloadWorker

        holder: dict = {}

        def _factory():
            worker = DataDownloadWorker(url, info)
            holder["worker"] = worker
            return worker

        def _wire(worker, thread) -> None:
            connect_queued(self.window, worker.progress, self._on_progress, thread)
            connect_queued(self.window, worker.stage, self._on_stage, thread)
            connect_queued(self.window, worker.finished, self._on_downloaded, thread)
            connect_queued(self.window, worker.failed, self._on_download_failed, thread)
            connect_queued(
                self.window, thread.finished, lambda *_: self._finish_download()
            )

        self._download = holder
        self.window.run_worker(_factory, _wire)

    def _on_progress(self, percent) -> None:
        if self._progress is not None:
            self._progress.progress(percent)

    def _on_stage(self, code) -> None:
        """下载之后的阶段提示（校验 / 释放占用 / 替换 / 重新加载）。"""
        if self._progress is None:
            return
        # ⚠️ 惰性 import：只是取那份"阶段码 → 文案"的词表（唯一来源）。
        from desktop.workers.data_package_worker import DATA_PACKAGE_STAGES

        self._progress.stage(DATA_PACKAGE_STAGES.get(str(code), "正在处理…"))

    def _on_downloaded(self, result) -> None:
        """下载成功：关进度窗、复位菜单项、给出成功提示。

        自动更新（``_auto_download``）时**不弹结果窗**，只更新顶部提示条。
        """
        was_auto = self._auto_download
        # 刚装上新模型 ⇒ "有新版本"提示该清掉（否则菜单项会一直催）。
        self._newer_version = 0
        self._finish_download()
        result = result or {}
        version = int(result.get("version") or 0)
        self.notify.emit(
            f"去底色数据包 v{version} 已下载并启用，下次检测即用新模型。"
        )
        if was_auto:
            return
        body = f"已下载并启用新模型（版本 v{version}），并已重新加载到内存。\n\n下次检测会直接用上新模型。"
        if result.get("path"):
            body += f"\n\n保存位置：{result['path']}"
            body += (
                "\n（文件名保留版本号；旧版模型仍留在同一目录里，"
                "bookcontent.version.json 决定当前生效的那一份。）"
            )
        self._present(UpdateVerdict("数据包下载完成", body))

    def _on_download_failed(self, kind) -> None:
        """下载失败（或被取消）：关进度窗、复位菜单项；取消则静默。"""
        was_auto = self._auto_download
        self._finish_download()
        key = str(kind)
        if key == "cancelled":
            return
        reason = FAILURE_REASONS.get(key)
        if reason is None:
            if "PermissionError" in key:
                # Windows 上目标权重被别的句柄打开时替换会失败（见 replace_with_retry）
                reason = (
                    "无法替换模型文件（文件可能被占用）。请关闭正在检测的任务后再试。"
                )
            else:
                reason = f"下载失败（{key}）。"
        if was_auto:
            self.notify.emit(
                f"去底色数据包自动下载失败：{reason} 可稍后在「帮助 → 更新数据包」中重试。"
            )
            return
        self._present(UpdateVerdict("数据包下载失败", f"{reason}\n\n稍后可以再试。"))

    def _cancel_download(self) -> None:
        """进度窗的「取消」：请 worker 收手（结果回来时按 ``cancelled`` 静默）。"""
        worker = self._download.get("worker")
        if worker is not None:
            worker.cancel()

    def _close_progress(self) -> None:
        progress = self._progress
        self._progress = None
        if progress is not None:
            progress.close()

    def _finish_download(self) -> None:
        """下载收尾（成功/失败/线程结束三条路都会到，**幂等**）。"""
        self._close_progress()
        self._download = {}
        self._auto_download = False
        if self._downloading:
            self._downloading = False
            self.action.setEnabled(True)
            self._apply_action_text()
