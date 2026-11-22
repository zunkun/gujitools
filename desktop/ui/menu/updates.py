# -*- coding: utf-8 -*-
"""「检查更新」控制器（自 ``desktop/ui/menu.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from config import VERSION
from desktop.components.dialog_shell import shell_dialog
from desktop.store.json_io import read_json, write_json
from desktop.ui.toast import show_toast
from desktop.utils.files import pending_install_file, updates_dir
from desktop.workers import connect_queued
from utils.version import is_newer

from ._qt import (
    QAction,
    QDesktopServices,
    QDialog,
    QObject,
    QTimer,
    QUrl,
    Signal,
)
from .installer import install_and_restart
from .constants import (
    ACTION_UPDATE,
    ACTION_UPDATE_BUSY,
    ACTION_UPDATE_DOWNLOADING,
    ACTION_UPDATE_TOOLTIP,
    BUTTON_BROWSER,
    BUTTON_CANCEL,
    BUTTON_DOWNLOAD,
    BUTTON_INSTALL,
    BUTTON_LATER,
    BUTTON_RETRY,
    NEW_VERSION_SUFFIX,
    PROJECT_URL,
    RESULT_LATEST,
    RESULT_NEWER,
)
from .panels import _DownloadProgress, _MessagePanel
from .verdicts import (
    UpdateVerdict,
    _download_failed_verdict,
    _ready_verdict,
    update_result,
)

# ------------------------------------------------------------------ 检查更新
class UpdateController(QObject):
    """「检查更新」的编排者：一次一个请求，结果用弹窗汇报。

    三条硬约束：

    1. **重入防护**：连点菜单不叠出第二个请求（``_checking``），期间菜单项
       **置灰**并改名「正在检查更新…」，用户看得见"正在跑"；
    2. **网络在子线程**（``window.run_worker``，见 ``WorkerHost``）；
    3. **收尾幂等**：``_finish`` 由 worker 信号与线程结束两条路都会调到，
       重复调用只生效一次。
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
        #: 上一次成功检查的 payload（含**四条线路测速排名**；下载走 ranking 里那条线路）
        self._last_payload: dict | None = None
        #: 下载走 ranking 里第几条可用线路（0 = 最快那条；下载失败自动换下一条）
        self._scheme_index = 0
        #: 「正在检查」窗（先弹出来的那个；结果落地或用户取消时关掉）
        self._check_dialog: QDialog | None = None
        #: 下载进度窗（_DownloadProgress；没有下载在跑时为 None）
        self._progress: _DownloadProgress | None = None
        #: 当前下载 worker（「取消」要调它的 ``cancel``）
        self._download: dict = {}
        #: 最近一次"下好但还没装"的安装包记录（tag/path/sha256），供"稍后"后免重下
        self._pending: dict | None = None
        #: 用户点了「取消」：结果回来时静默丢弃，不再弹结果窗
        self._aborted = False
        #: 当前这次检查是**静默**的（启动时后台自动查）：不弹任何窗，只在菜单项上
        #: 挂"有新版本"提示；用户中途点了菜单就转成显式（见 :meth:`check`）。
        self._silent = False
        #: 这次静默检查是否**自动下载**（来自设置页「自动更新软件」，用户 2026-11-02）
        self._auto = False
        #: 当前这次下载是**自动**发起的（不弹进度窗/结果窗，只更新顶部提示条）
        self._auto_download = False
        #: 已知的新版本 tag（空 = 未知/已是最新）——菜单项文案与 tooltip 看它
        self._newer_tag = ""

    # ---- 触发 ----
    def check(self) -> None:
        """查一次 GitHub Release 最新版：**先弹「正在检查」窗，再弹结果窗**。

        用户 2026-10-15：「检查更新，先出弹窗，再反馈结果」——点下去立刻要有可见反馈
        （后台要并发测四条线路，可能几秒），不能像以前那样只有菜单项变灰 + 静默等。

        ⚠️ 若此刻正有一次**静默**检查在飞（启动时自动跑的那次），这里**升级**成显式
        检查（挂上检查窗、结果照常弹），而不是回一句"正在检查"——用户在启动几秒内
        就点菜单是完全正常的事，让他白等一次很没道理；同一次请求两种模式共用。
        """
        if self._checking:
            if self._silent:
                self._silent = False
                # 用户主动点进来 = 不要"静默自动下载"，改成显式流程（弹窗问用户）
                self._auto = False
                self._present_checking()
                return
            show_toast(
                self.window,
                "info",
                "正在检查更新",
                "上一次检查还没结束，请稍候。",
            )
            return
        if self._downloading:
            show_toast(
                self.window, "info", "正在下载更新", "安装包还在下载，请稍候。",
            )
            return
        self._silent = False
        self._auto = False
        self._aborted = False
        self.action.setEnabled(False)
        self.action.setText(ACTION_UPDATE_BUSY)
        self._present_checking()
        self._start_worker()

    def check_silently(self, auto: bool = False) -> None:
        """**后台静默**检查一次（启动时自动跑，用户 2026-10-15）。

        与显式检查的三点不同：

        1. **不弹任何窗**（没有「正在检查」窗，也没有结果窗）——启动时不该打扰用户；
        2. **不动菜单项文案**（不置灰、不写"正在检查更新…"）——避免启动瞬间闪一下；
        3. 只有**发现有新版本**时，才在菜单项上挂提示（:data:`NEW_VERSION_SUFFIX`，
           版本号进 tooltip），失败则完全安静（网络不好时别在启动日志里刷错误）。

        ``auto``（用户 2026-11-02）：发现新版本后**自动下载安装包**，不弹进度窗；
        由启动接线按设置页的「自动更新软件」传入（默认 ``False``，显式调用/自测
        走的仍是"只提示、不自动下"的老口径）。
        """
        if self._checking or self._downloading:
            return  # 显式检查在跑、已有一次静默检查在飞，或在下载安装包
        self._silent = True
        self._auto = bool(auto)
        self._aborted = False
        self._start_worker()

    def _start_worker(self) -> None:
        """起一次后台检查（显式/静默共用）：置忙标记 + 接线信号。"""
        self._checking = True
        # ⚠️ 惰性 import：启动期不该为一个"用户可能不点"的菜单项拉进网络模块。
        from desktop.workers.update_worker import UpdateCheckWorker

        self.window.run_worker(
            UpdateCheckWorker,
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
        """弹「正在检查更新」窗（**非模态**：检查在子线程，主线程得能继续收信号）。

        ⚠️ 用 ``show()`` 而不是 ``exec()``：``exec()`` 会把主线程压进嵌套事件循环，
        这里没必要（结果本来就走信号回主线程），而且非模态才允许用户点「取消」改主意。
        ⚠️ 它的按钮是**「取消」**：点了就关窗并**丢掉这次结果**（见 ``_abort_check``），
        不然用户关掉了窗、几秒后又冒出一个结果窗，像是"点了没反应还自己弹东西"。
        """
        panel = _MessagePanel("正在查询检查最新版......")
        dialog = shell_dialog(
            "正在检查更...",
            panel,
            self.window,
            size=(620, 180),
            ok_text="取消",
            show_cancel=False,
            on_ok=self._abort_check,
        )
        self._check_dialog = dialog
        dialog.show()

    def _close_check_dialog(self) -> None:
        """关掉「正在检查」窗（结果落地 / 用户取消时都要关，别留着）。"""
        dialog = getattr(self, "_check_dialog", None)
        self._check_dialog = None
        if dialog is not None:
            dialog.close()

    def _abort_check(self) -> None:
        """用户点了「正在检查」窗的「取消」：关窗 + **丢掉这次结果**。

        ⚠️ 只是"不看结果"，**不掐断**已经发出去的请求（子线程里是并发 HTTP，掐断
        要额外的取消协议，收益不值当）；结果回来时 ``_on_checked`` 看到 ``_aborted``
        就静默收尾。
        """
        self._aborted = True
        self._close_check_dialog()
        self._finish()

    # ---- 结果 ----
    def _on_checked(self, payload) -> None:
        """拿到 release 原始字段：比版本决定"已是最新 / 有新版本"。

        ⚠️ 同时记下 payload（含**四条线路的测速排名**）并复位线路下标——「换条线路」
        就在这份排名上换，不再重新联网。
        ⚠️ **静默模式**（启动时那次自动检查）只把"有新版本"挂到菜单项上、**不弹任何
        窗**；显式模式才关「正在检查」窗并弹结果（见 :meth:`check` / `check_silently`）。
        """
        self._finish()
        self._close_check_dialog()
        if self._aborted:
            self._last_payload = None
            return
        self._last_payload = dict(payload or {})
        self._scheme_index = 0
        tag = str(self._last_payload.get("tag_name") or "")
        kind = RESULT_NEWER if is_newer(tag, VERSION) else RESULT_LATEST
        if self._silent:
            # 菜单提示：有新版本才挂后缀；已是最新就把提示清掉（比如用户在别的
            # 机器上升级后重开程序，提示不该留成"鬼影"）。
            self._newer_tag = tag if kind == RESULT_NEWER else ""
            self._apply_action_text()
            if kind != RESULT_NEWER:
                self.notify.emit("")      # 顶部提示条一并清掉
                return
            # 顶部提示条（用户 2026-11-02）：启动时发现新版本要一直看得见，
            # 直到用户自己点关闭；自动更新开着就顺手把安装包下下来。
            pending = self._pending_for(tag)
            if pending is not None:
                self._pending = pending
                self.notify.emit(
                    f"发现新版本 {tag}，安装包已下载，"
                    "可在「帮助 → 检查更新」中重启安装。"
                )
                return
            if self._auto:
                self.notify.emit(f"发现新版本 {tag}，正在后台自动下载…")
                self._start_app_download(auto=True)
            else:
                self.notify.emit(
                    f"发现新版本 {tag}，可在「帮助 → 检查更新」中下载。"
                )
            return
        if kind == RESULT_NEWER:
            # 上次点了「稍后」、安装包还躺在用户目录里 ⇒ 直接给「立即重启安装」，
            # 不必重下几百 MB（见 _pending_for / _ready_verdict）。
            pending = self._pending_for(tag)
            if pending is not None:
                self._pending = pending
                self._present(_ready_verdict(tag))
                return
            self._present(self._verdict_for_scheme(self._scheme_index))
            return
        self._present(update_result(kind, current=VERSION, latest=self._last_payload))

    def _on_failed(self, kind) -> None:
        """网络/解析失败：**静默模式**什么都不做；显式模式关窗后给中文原因。"""
        self._finish()
        self._close_check_dialog()
        if self._aborted:
            self._last_payload = None
            return
        self._last_payload = None
        if self._silent:
            # 启动时那次自动检查失败（断网/限流都常见）：安静收场，别弹框打扰。
            # ⚠️ 也**不**清掉已有的"有新版本"提示：这次没查到 ≠ 已经是最新。
            return
        self._present(update_result(str(kind), current=VERSION))

    # ---- 菜单项文案（有新版本时的提示）----
    def _action_text(self) -> str:
        """菜单项当前该显示的文案：下载中显示进行时；已知有新版本时带后缀。"""
        if self._downloading:
            return ACTION_UPDATE_DOWNLOADING
        if self._newer_tag:
            return f"{ACTION_UPDATE}{NEW_VERSION_SUFFIX}"
        return ACTION_UPDATE

    def _apply_action_text(self) -> None:
        """把文案/悬停提示刷成当前状态（版本号放 tooltip，菜单项别撑太宽）。"""
        self.action.setText(self._action_text())
        self.action.setToolTip(
            f"已发现新版本 {self._newer_tag}，点这里看详情并下载"
            if self._newer_tag
            else ACTION_UPDATE_TOOLTIP
        )

    def _finish(self) -> None:
        """解除忙标记并恢复菜单项（**幂等**，见类 docstring）。

        ⚠️ 恢复的是 ``_action_text()`` 而不是写死的 ``ACTION_UPDATE``：静默检查
        发现过新版本时，菜单项该带着"有新版本"的提示留下来。
        """
        if not self._checking:
            return
        self._checking = False
        self.action.setEnabled(True)
        self._apply_action_text()

    # ---- 线路切换（用户 2026-10-15：「下载更新的时候，可以选择测试选择最优方案」）----
    def _usable_schemes(self) -> list[dict]:
        """这次检查里**通了的**线路，按测速从快到慢（第一条就是自动选中的最优）。"""
        payload = self._last_payload or {}
        return [
            item
            for item in (payload.get("ranking") or [])
            if isinstance(item, dict) and item.get("ok")
        ]

    def _verdict_for_scheme(self, index: int) -> UpdateVerdict:
        """把 payload 换成"走第 ``index`` 条线路"，再生成结论文案。"""
        payload = dict(self._last_payload or {})
        schemes = self._usable_schemes()
        if schemes:
            entry = schemes[index % len(schemes)]
            payload.update(
                {
                    "mirror_prefix": entry.get("prefix", ""),
                    "mirror_label": entry.get("label", "直连"),
                    "download_url": entry.get("download_url", ""),
                    "seconds": entry.get("seconds"),
                }
            )
        return update_result(RESULT_NEWER, current=VERSION, latest=payload)

    def _present(self, verdict: UpdateVerdict) -> None:
        """把结论弹出来；主按钮语义由 ``verdict.ok_text`` 决定（见 :class:`UpdateVerdict`）。

        - ``BUTTON_DOWNLOAD`` / ``BUTTON_RETRY`` → **应用内下载**（``_start_app_download``），
          次按钮「前往下载页」= 开浏览器（**备用**，用户自己下）；
        - ``BUTTON_INSTALL`` → 「立即重启安装」（``_install_and_restart``），次按钮「稍后」；
        - 其余 → 只有「好的」。

        ⚠️ ``shell_dialog`` 的按钮点下去**不会**自己关窗，所以回调里先 ``done(0)``，
        再 ``QTimer.singleShot(0, …)`` 把后续动作排到本次点击处理完**之后**执行；
        直接在回调里再 ``exec()`` 会叠出两层模态（外面那层还留在屏幕上）。
        """
        panel = _MessagePanel(verdict.body, verdict.link)
        holder: dict = {}
        # ⚠️ 先窄化到局部变量再进闭包：直接闭包捕获 ``after``（类型含 None）会被
        #    Pyright 判成"可能不可调用"（``reportOptionalCall``）。
        after: Callable[[], None] | None = None
        if verdict.ok_text in (BUTTON_DOWNLOAD, BUTTON_RETRY):
            after = self._start_app_download
        elif verdict.ok_text == BUTTON_INSTALL:
            after = self._install_and_restart
        on_ok = None
        if after is not None:
            action = after

            def _go() -> None:
                dialog = holder.get("dialog")
                if dialog is not None:
                    dialog.done(0)
                QTimer.singleShot(0, action)

            on_ok = _go

        on_cancel: Callable[[], None] | None = None
        cancel_text = BUTTON_BROWSER
        show_cancel = False
        if verdict.ok_text == BUTTON_INSTALL:
            cancel_text = BUTTON_LATER
            show_cancel = True
        elif verdict.browser_url:
            url = verdict.browser_url

            def _open_browser() -> None:
                dialog = holder.get("dialog")
                if dialog is not None:
                    dialog.done(0)
                QDesktopServices.openUrl(QUrl(url))

            on_cancel = _open_browser
            show_cancel = True

        dialog = shell_dialog(
            verdict.title,
            panel,
            self.window,
            # ⚠️ 高度**按内容自适应**：这里只给一个"下限"，真正的尺寸在下面
            #    ``adjustSize()`` 里由正文长短算出来。写死 360 时正文只有三四行、
            #    下面空掉一大片（用户 2026-10-15 截图报「弹窗高度太高，大片空白」）。
            size=(620, 120),
            ok_text=verdict.ok_text,
            cancel_text=cancel_text,
            show_cancel=show_cancel,
            on_ok=on_ok,
            on_cancel=on_cancel,
        )
        holder["dialog"] = dialog
        # ⚠️ 正文是可换行的 BodyLabel，只有拿到宽度后 sizeHint 才准 ⇒ 先布好再
        #    adjustSize（``shell_dialog`` 已经设了最小尺寸，所以不会被缩得更矮）。
        dialog.adjustSize()
        dialog.exec()

    # ---- 应用内下载安装包 + 重启安装（用户 2026-10-16）----
    def _pending_for(self, tag: str) -> dict | None:
        """上次「稍后」留下的安装包记录：tag 一致、文件还在，才算数（免重下）。"""
        if not tag:
            return None
        data = read_json(pending_install_file(), {}) or {}
        if not isinstance(data, dict) or str(data.get("tag") or "") != tag:
            return None
        path = Path(str(data.get("path") or ""))
        if not path.is_file():
            return None
        return data

    def _scheme_download_url(self) -> str:
        """当前该走的下载地址：优先 ranking 里第 ``_scheme_index`` 条可用线路。"""
        payload = self._last_payload or {}
        schemes = self._usable_schemes()
        if schemes:
            entry = schemes[self._scheme_index % len(schemes)]
            url = str(entry.get("download_url") or "")
            if url:
                return url
        return str(payload.get("download_url") or "")

    def _browser_url(self) -> str:
        """「前往下载页」的目标：release 网页（拿不到就用项目主页兜底）。"""
        payload = self._last_payload or {}
        return str(payload.get("html_url") or "") or PROJECT_URL

    def _start_app_download(self, auto: bool = False) -> None:
        """开始**应用内**下载安装包（走测速排名里当前那条线路）。

        ``auto=True``（用户 2026-11-02）表示这次是启动时自动更新发起的：**不弹
        进度窗**，下载结果只写顶部提示条；``False`` 是用户点「下载」的显式流程。
        """
        payload = self._last_payload or {}
        asset = payload.get("asset") or {}
        url = self._scheme_download_url()
        if not url:
            return
        name = Path(str(asset.get("name") or "")).name or "guji_setup.exe"
        dest = updates_dir() / name
        self._downloading = True
        self._auto_download = bool(auto)
        self.action.setEnabled(False)
        self.action.setText(ACTION_UPDATE_DOWNLOADING)
        self._progress = None
        if not auto:
            self._progress = _DownloadProgress(
                self.window, "正在下载安装包", self._cancel_app_download
            )

        from desktop.workers.update_worker import AppDownloadWorker

        holder: dict = {}

        def _factory():
            worker = AppDownloadWorker(
                url, dest,
                sha256=str(asset.get("sha256") or ""),
                size=int(asset.get("size") or 0),
            )
            holder["worker"] = worker
            return worker

        def _wire(worker, thread) -> None:
            connect_queued(self.window, worker.progress, self._on_progress, thread)
            connect_queued(self.window, worker.stage, self._on_app_stage, thread)
            connect_queued(
                self.window, worker.finished, self._on_app_downloaded, thread)
            connect_queued(self.window, worker.failed, self._on_app_failed, thread)
            connect_queued(
                self.window, thread.finished, lambda *_: self._finish_download())

        self._download = holder
        self.window.run_worker(_factory, _wire)

    def _on_progress(self, percent) -> None:
        if self._progress is not None:
            self._progress.progress(percent)

    def _on_app_stage(self, code) -> None:
        """下载之后的阶段提示（当前只有"校验安装包完整性"）。"""
        if self._progress is None:
            return
        from desktop.workers.update_worker import APP_UPDATE_STAGES

        self._progress.stage(APP_UPDATE_STAGES.get(str(code), "正在处理…"))

    def _on_app_downloaded(self, result) -> None:
        """安装包下好：记一笔"待安装"记录（供「稍后」免重下），再提示重启安装。

        ``_auto_download`` 时**不弹结果窗**，只更新顶部提示条（启动自动更新）。
        """
        was_auto = self._auto_download
        self._finish_download()
        result = result or {}
        tag = str((self._last_payload or {}).get("tag_name") or "")
        record = {
            "tag": tag,
            "path": str(result.get("path") or ""),
            "name": str(result.get("name") or ""),
            "sha256": str(result.get("sha256") or ""),
            "size": int(result.get("size") or 0),
        }
        try:
            updates_dir().mkdir(parents=True, exist_ok=True)
            write_json(pending_install_file(), record)
        except OSError:
            pass      # 记不住只是"下次要重下"，不该挡住"提示重启安装"
        self._pending = record
        self.notify.emit(
            f"新版本 {tag or '已下载'} 已下载完成，"
            "可在「帮助 → 检查更新」中立即重启安装。"
        )
        if was_auto:
            return
        self._present(_ready_verdict(tag))

    def _on_app_failed(self, kind) -> None:
        """下载失败：关进度窗、复位菜单项；取消则静默，真失败就换线路给重试。"""
        was_auto = self._auto_download
        self._finish_download()
        key = str(kind)
        if key == "cancelled":
            return
        if was_auto:
            self.notify.emit(
                "新版本安装包自动下载失败，可稍后在「帮助 → 检查更新」中重试。"
            )
            return
        schemes = self._usable_schemes()
        if len(schemes) > 1:
            self._scheme_index = (self._scheme_index + 1) % len(schemes)
        self._present(_download_failed_verdict(key, self._browser_url()))

    def _cancel_app_download(self) -> None:
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

    def _install_and_restart(self) -> None:
        """启动安装器（分离进程）后退出本程序，让安装器接管文件替换。"""
        install_and_restart(self.window, self._pending)
