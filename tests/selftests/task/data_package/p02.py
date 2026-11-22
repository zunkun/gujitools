# -*- coding: utf-8 -*-
"""4. 控制器：真菜单 + 真控制器（弹窗/网络/下载 worker 换替身）"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import _DialogRecorder, _action_of, _menu_of, _payload
    from PySide6.QtCore import QObject, Signal, Slot
    import desktop.workers.data_package_worker as dw
    import desktop.ui.menu as menu
    from tests.selftests._context import ok, pump, wait_until
    controller = getattr(st.w, "data_package_controller", None)
    ok("窗口上挂着数据包控制器（与菜单项同源）", controller is not None, "")
    assert controller is not None
    action = _action_of(_menu_of(st.w, menu.MENU_HELP), menu.ACTION_DATA_PACKAGE)
    ok(
        "「更新数据包」菜单项默认文案带 &M 助记符",
        action.text() == menu.ACTION_DATA_PACKAGE
        and "(&M)" in menu.ACTION_DATA_PACKAGE,
        action.text(),
    )

    recorder = _DialogRecorder()
    real_shell = menu.shell_dialog
    real_fetch = dw.fetch_data_json
    real_read_version = menu.read_local_version
    real_download_cls = dw.DataDownloadWorker

    from PySide6.QtCore import QObject, Signal, Slot

    class _FakeDownloadWorker(QObject):
        """假下载 worker：立刻发进度 + 阶段 + finished，不碰真网络/真服务。"""

        progress = Signal(int)
        stage = Signal(str)
        finished = Signal(dict)
        failed = Signal(str)

        def __init__(self, url, info=None, dest=None):
            super().__init__()
            self.url = url
            self.info = dict(info or {})
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

        @Slot()
        def run(self) -> None:
            self.progress.emit(50)
            self.stage.emit("release")
            self.stage.emit("reload")
            self.finished.emit(
                {
                    "path": "X:/tmp/bookcontent-v100.pt",
                    "version": 100,
                    "sha256": "f" * 64,
                    "size": 6245475,
                }
            )

    try:
        menu.shell_dialog = recorder  # type: ignore[assignment]
        dw.DataDownloadWorker = _FakeDownloadWorker  # type: ignore[assignment]
        menu.read_local_version = lambda: 0  # type: ignore[assignment]

        # ---- 4a. 有新版：检查窗 → 「下载」提示 ----
        dw.fetch_data_json = (  # type: ignore[assignment]
            lambda *a, **k: _payload(version=100)
        )
        action.trigger()
        ok(
            "检查期间：先弹「正在检查数据包」窗、菜单项置灰",
            bool(recorder.calls)
            and "正在检查" in recorder.calls[0]["title"]
            and not action.isEnabled(),
            f"{[c['title'] for c in recorder.calls]}",
        )
        ok(
            "有新版：弹出「发现新版本数据包」提示（主按钮是「下载」，不跳浏览器）",
            wait_until(st.app, lambda: len(recorder.calls) > 1, timeout=8.0)
            and recorder.calls[-1]["title"] == "发现新版本数据包"
            and recorder.calls[-1]["ok_text"] == menu.BUTTON_DOWNLOAD
            and "v100" in recorder.calls[-1]["body"]
            and "bookcontent-v100.pt" in recorder.calls[-1]["body"],
            f"{[c['title'] for c in recorder.calls]}",
        )
        ok(
            "结果落地后：检查窗已关、菜单项恢复",
            recorder.dialogs[0].closed and action.text() == menu.ACTION_DATA_PACKAGE,
            f"closed={recorder.dialogs[0].closed} text={action.text()!r}",
        )

        # ---- 4b. 点「下载」：程序内下载 → 进度窗 → 成功弹窗 ----
        download_cb = recorder.calls[-1]["on_ok"]
        ok(
            "「下载」按钮接的是**程序内下载**回调（不是打开浏览器）",
            callable(download_cb),
            f"{download_cb}",
        )
        recorder.calls.clear()
        download_cb()  # 相当于点了结果窗的「下载」
        pump(st.app, times=3)
        ok(
            "点「下载」：弹出下载进度窗",
            wait_until(
                st.app,
                lambda: any(c["title"].startswith("正在下载") for c in recorder.calls),
                timeout=8.0,
            ),
            f"{[c['title'] for c in recorder.calls]}",
        )
        ok(
            "下载完成：弹出「数据包下载完成」，菜单项恢复原文案",
            wait_until(
                st.app,
                lambda: any(c["title"] == "数据包下载完成" for c in recorder.calls),
                timeout=8.0,
            )
            and action.text() == menu.ACTION_DATA_PACKAGE
            and action.isEnabled(),
            f"{[c['title'] for c in recorder.calls]} text={action.text()!r}",
        )

        # ---- 4c. 已是最新：只给「好的」，没有下载按钮 ----
        recorder.calls.clear()
        menu.read_local_version = lambda: 100  # type: ignore[assignment]
        dw.fetch_data_json = (  # type: ignore[assignment]
            lambda *a, **k: _payload(version=100)
        )
        action.trigger()
        ok(
            "已是最新：弹出「数据包已是最新」（无下载按钮）",
            wait_until(
                st.app,
                lambda: any(c["title"] == "数据包已是最新" for c in recorder.calls),
                timeout=8.0,
            )
            and recorder.calls[-1]["ok_text"] == menu.BUTTON_OK
            and recorder.calls[-1]["show_cancel"] is False,
            f"{[c['title'] for c in recorder.calls]}",
        )

        # ---- 4d. 检查失败：中文原因 + 发布页指引，不谎报有新版本 ----
        recorder.calls.clear()

        def _boom(*_a, **_k):
            raise dw.DataCheckError("network")

        dw.fetch_data_json = _boom  # type: ignore[assignment]
        action.trigger()
        ok(
            "检查失败：弹出「检查数据包失败」（分类来自 worker 的 kind）",
            wait_until(
                st.app,
                lambda: any(c["title"] == "检查数据包失败" for c in recorder.calls),
                timeout=8.0,
            )
            and menu.FAILURE_REASONS["network"][:6] in recorder.calls[-1]["body"]
            and menu.DATA_PACKAGE_URL in recorder.calls[-1]["body"],
            f"{[c['title'] for c in recorder.calls]}",
        )

        # ---- 4e. 静默检查：不弹窗，只在菜单项上挂提示 ----
        recorder.calls.clear()
        menu.read_local_version = lambda: 0  # type: ignore[assignment]
        dw.fetch_data_json = (  # type: ignore[assignment]
            lambda *a, **k: _payload(version=100)
        )
        controller.check_silently()
        ok(
            "静默检查有新版：**不弹任何窗**、菜单项挂「有新版本」提示、tooltip 带版本号",
            wait_until(st.app, lambda: not controller._checking, timeout=8.0)
            and recorder.calls == []
            and menu.NEW_VERSION_SUFFIX in action.text()
            and "v100" in action.toolTip(),
            f"弹窗={[c['title'] for c in recorder.calls]} text={action.text()!r}",
        )
        # ---- 4f. 本机一份权重都没有：静默检查**直接下载**（用户 2026-10-22） ----
        recorder.calls.clear()
        real_resolve = menu.resolve_weights
        menu.resolve_weights = lambda: None  # type: ignore[assignment]
        try:
            menu.read_local_version = lambda: 0  # type: ignore[assignment]
            dw.fetch_data_json = (  # type: ignore[assignment]
                lambda *a, **k: _payload(version=100)
            )
            controller._newer_version = 0
            controller._apply_action_text()
            controller.check_silently()
            ok(
                "没有任何权重时：静默检查**直接下载**（不弹「发现新版本」提示）",
                wait_until(
                    st.app,
                    lambda: any(
                        c["title"] == "数据包下载完成" for c in recorder.calls
                    ),
                    timeout=8.0,
                )
                and not any(
                    c["title"] == "发现新版本数据包" for c in recorder.calls
                ),
                f"{[c['title'] for c in recorder.calls]}",
            )
        finally:
            menu.resolve_weights = real_resolve  # type: ignore[assignment]
            controller._newer_version = 0
            controller._apply_action_text()

        # ---- 4g. 自动更新数据包（设置页「自动更新数据包」开着，用户 2026-11-02）----
        recorder.calls.clear()
        menu.read_local_version = lambda: 0  # type: ignore[assignment]
        dw.fetch_data_json = (  # type: ignore[assignment]
            lambda *a, **k: _payload(version=100)
        )
        notices: list[str] = []
        controller.notify.connect(notices.append)
        try:
            controller.check_silently(auto=True)
            ok(
                "自动更新数据包：静默检查直接**下载并替换**，全程不弹任何窗",
                wait_until(
                    st.app,
                    lambda: any("已下载并启用" in t for t in notices),
                    timeout=8.0,
                )
                and recorder.calls == []
                and controller.action.text() == menu.ACTION_DATA_PACKAGE,
                f"弹窗={[c['title'] for c in recorder.calls]} 提示={notices}",
            )
        finally:
            controller.notify.disconnect(notices.append)
    finally:
        menu.shell_dialog = real_shell  # type: ignore[assignment]
        dw.fetch_data_json = real_fetch  # type: ignore[assignment]
        dw.DataDownloadWorker = real_download_cls  # type: ignore[assignment]
        menu.read_local_version = real_read_version  # type: ignore[assignment]
        controller._finish()  # 别把菜单项留在忙态
        controller._finish_download()

