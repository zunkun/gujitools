# -*- coding: utf-8 -*-
"""去底色数据包（``bookcontent.pt``）的检查/下载自测。

覆盖三层，都不碰真网络、不落真文件：

1. **纯规则**（``utils.data_package``）：data.json 解析、本地版本 sidecar 读写
   （用 **临时目录**替换权重目录，绝不在仓库里落 sidecar）、整数比大小；
2. **下载内核**（``DataDownloadWorker._download``）：把 ``urlopen`` 换成内存假
   响应，验证"写 .part → 校验 sha256 → 原子改名 → 写版本记录"，以及 sha 不符 /
   取消两条异常路径；
3. **控制器**（``menu.DataPackageController``）：有新版 → 弹「下载」提示 → 点了
   在程序内下载（``DataDownloadWorker`` 换成假 worker）→ 成功弹窗；已是最新 /
   检查失败 / 静默三分支，以及菜单项提示。

⚠️ 全部走 ``ctx.w`` 的真菜单与真控制器，但把 ``menu.shell_dialog`` /
``data_package_worker.fetch_data_json`` / ``DataDownloadWorker`` 整体换成替身，
用完在 finally 里还原。
"""

from __future__ import annotations

from tests.selftests._context import ok, pump, wait_until

NAME = "data_package"
TITLE = "去底色数据包检查与下载"
DEPENDS: list[str] = []

#: 用户给的样例 data.json（真源形态；bookcontent 版本 100）。
SAMPLE_DATA_JSON = {
    "generated_at": "2026-10-16T09:22:21+08:00",
    "release": "database",
    "files": {
        "bookcontent": {
            "name": "bookcontent-v100.pt",
            "version": 100,
            "sha256": "8a70a890c3132edc9da82f27e51113bf054dd82ab7fad2c7bb8d71dd66d2fa5d",
            "size": 6245475,
            "date": "2026-09-28T18:52:07+08:00",
        },
        "gujiline": {
            "name": "gujiline-v100.pt",
            "version": 100,
            "sha256": "89dca4b2b0541d078500a383a29ce514e7ceb57107dff095e9d343440a92940d",
            "size": 6252707,
            "date": "2026-09-23T01:14:32+08:00",
        },
    },
}


class _FakeDialog:
    """假弹窗实体：exec/show/adjustSize 空实现，close 记一笔。"""

    def __init__(self) -> None:
        self.closed = False

    def exec(self) -> int:
        return 1

    def show(self) -> None:
        return None

    def adjustSize(self) -> None:
        return None

    def done(self, _result: int = 0) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _DialogRecorder:
    """假弹窗外壳：替 ``menu.shell_dialog``，记下每次调用的标题/正文/按钮/回调。

    正文照真货口径从内容面板的 ``BodyLabel`` 读——断言的是"用户真会看到什么"。
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.dialogs: list[_FakeDialog] = []

    def __call__(self, title, panel, parent=None, **kwargs) -> _FakeDialog:
        from qfluentwidgets import BodyLabel

        labels = panel.findChildren(BodyLabel)
        self.calls.append(
            {
                "title": title,
                "body": "\n".join(label.text() for label in labels),
                "ok_text": kwargs.get("ok_text"),
                "cancel_text": kwargs.get("cancel_text"),
                "show_cancel": kwargs.get("show_cancel"),
                "on_ok": kwargs.get("on_ok"),
                "on_cancel": kwargs.get("on_cancel"),
            }
        )
        dialog = _FakeDialog()
        self.dialogs.append(dialog)
        return dialog


class _FakeResponse:
    """内存假响应：够 ``urlopen`` 那条读链路用（headers + 流式 read）。"""

    def __init__(self, data: bytes, with_length: bool = True) -> None:
        self._data = data
        self._pos = 0
        self.headers = {"Content-Length": str(len(data))} if with_length else {}

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            chunk = self._data[self._pos :]
            self._pos = len(self._data)
            return chunk
        chunk = self._data[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False


def _payload(
    version: int = 100, name: str = "bookcontent-v100.pt", size: int = 6245475
) -> dict:
    """``fetch_data_json`` 的返回形态（控制器测试用）。"""
    return {
        "info": {
            "name": name,
            "version": version,
            "sha256": "a" * 64,
            "size": size,
            "date": "",
        },
        "asset_name": name,
        "download_url": "https://v6.gh-proxy.org/https://example.invalid/x.pt",
        "mirror_prefix": "https://v6.gh-proxy.org/",
        "mirror_label": "v6.gh-proxy.org",
        "seconds": 0.38,
        "ranking": [
            {
                "prefix": "https://v6.gh-proxy.org/",
                "label": "v6.gh-proxy.org",
                "ok": True,
                "seconds": 0.38,
            },
            {"prefix": "", "label": "直连", "ok": True, "seconds": 2.42},
        ],
    }


def _menu_of(window, title: str):
    for action in window.menu_bar.actions():
        if action.text() == title:
            menu = action.menu()
            assert menu is not None, f"菜单 {title} 没有实体"
            return menu
    raise AssertionError(f"没有找到顶级菜单：{title}")


def _action_of(menu, text: str):
    for action in menu.actions():
        if not action.isSeparator() and action.text() == text:
            return action
    raise AssertionError(f"菜单里没有动作：{text}")


def run(ctx) -> None:
    import hashlib
    import json

    import desktop.ui.menu as menu
    import desktop.workers.data_package_worker as dw
    import utils.data_package as dp
    import utils.download as ud
    from tests.tmpdir import temp_dir

    app, w = ctx.app, ctx.w

    # ---- 1. 纯规则：解析 data.json ----
    info = dp.parse_data_json(SAMPLE_DATA_JSON)
    ok(
        "解析样例 data.json：取到 bookcontent 版本 100 与文件名/大小",
        info is not None
        and info["version"] == 100
        and info["name"] == "bookcontent-v100.pt"
        and info["size"] == 6245475,
        f"{info}",
    )
    ok(
        "解析：缺 files / 缺 bookcontent / version 非整数 一律 None（不抛异常）",
        dp.parse_data_json({}) is None
        and dp.parse_data_json({"files": {}}) is None
        and dp.parse_data_json({"files": {"bookcontent": {"name": "x"}}}) is None
        and dp.parse_data_json(None) is None,
        "",
    )
    ok(
        "地址：data.json 与资产都拼在 **gujitrain** 的 database release 下",
        dp.data_json_url()
        == "https://github.com/zunkun/gujitrain/releases/download/database/data.json"
        and dp.asset_url("bookcontent-v100.pt")
        == "https://github.com/zunkun/gujitrain/releases/download/database/"
        "bookcontent-v100.pt",
        dp.data_json_url(),
    )

    # ---- 2. 本地版本 sidecar（权重目录换临时目录，不落仓库） ----
    tmp = temp_dir("data_package_")
    real_weights_dir = dp.weights_dir
    dp.weights_dir = lambda: tmp  # type: ignore[assignment]
    try:
        ok(
            "sidecar 缺失 → 本机版本 0（于是远端 v100 必然算更新）",
            dp.read_local_version() == 0,
            f"{dp.read_local_version()}",
        )
        ok(
            "版本比较：100 > 0（有新版）、100 == 100（已最新）、0 > 100（更旧）",
            dp.has_update(100)
            and not dp.has_update(100, 100)
            and not dp.has_update(0, 100),
            "",
        )
        dp.record_local_version(
            {
                "version": 100,
                "name": "bookcontent-v100.pt",
                "sha256": "AB" * 32,
                "size": 6245475,
            }
        )
        ok(
            "写入 sidecar 后再读 = 100，且 sha256 统一转小写",
            dp.read_local_version() == 100
            and dp.read_local_info()["sha256"] == ("ab" * 32),
            f"{dp.read_local_info()}",
        )
        ok(
            "sidecar 落点就在权重目录旁（bookcontent.version.json）",
            (tmp / dp.VERSION_FILE_NAME).is_file(),
            f"{dp.version_file()}",
        )
    finally:
        dp.weights_dir = real_weights_dir  # type: ignore[assignment]

    # ---- 2b. 防缓存 + "取最新清单"（不是"取最快线路"）----
    # 背景：用户 2026-10-16 报「数据包检查不对，线上是 101」（本机 v100、远端已发
    # v101 却报"已是最新"）。release 资产地址固定、会被缓存，**缓存命中的旧清单
    # 一定更快**，于是"选最快那条"会系统性地选到旧版本。
    ok(
        "防缓存参数：每次调用都唯一，且不破坏已有的查询串",
        dw._cache_bust("https://x/y.json") != dw._cache_bust("https://x/y.json")
        and dw._cache_bust("https://x/y.json").startswith("https://x/y.json?t=")
        and dw._cache_bust("https://x/y.json?a=1").startswith("https://x/y.json?a=1&t="),
        dw._cache_bust("https://x/y.json"),
    )

    seen_urls: list[str] = []
    real_fetch_one = dw._fetch_one

    def _spy_fetch(prefix, url, timeout):
        seen_urls.append(f"{prefix}|{url}")
        return {"prefix": prefix, "ok": False, "payload": None,
                "reason": "network", "seconds": 0.1}

    dw._fetch_one = _spy_fetch  # type: ignore[assignment]
    try:
        dw.probe_mirrors("https://x/data.json")
    finally:
        dw._fetch_one = real_fetch_one  # type: ignore[assignment]
    ok(
        "测速四条线路一律走防缓存地址（同一次检查共用同一个 t=）",
        len(seen_urls) == len(dw.MIRROR_PREFIXES)
        and all("?t=" in url for url in seen_urls)
        and len({url.split("t=")[1] for url in seen_urls}) == 1,
        f"{seen_urls}",
    )

    # 排名的**第一条**是"缓存命中的旧清单"（更快），第二条才是刚发布的 v101。
    stale_ranking = [
        {"prefix": "https://cdn.gh-proxy.org/", "label": "cdn.gh-proxy.org",
         "ok": True, "reason": "", "seconds": 0.19,
         "payload": json.loads(json.dumps(SAMPLE_DATA_JSON))},
        {"prefix": "", "label": "直连", "ok": True, "reason": "", "seconds": 1.9,
         "payload": {"files": {"bookcontent": {
             "name": "bookcontent-v101.pt", "version": 101,
             "sha256": "b" * 64, "size": 6232163}}}},
    ]
    real_probe = dw.probe_mirrors
    dw.probe_mirrors = lambda *a, **k: stale_ranking  # type: ignore[assignment]
    try:
        fetched = dw.fetch_data_json()
    finally:
        dw.probe_mirrors = real_probe  # type: ignore[assignment]
    ok(
        "清单取**版本最大**那条：旧缓存清单就算排最快也不上当（v101 胜过 v100）",
        fetched["info"]["version"] == 101
        and fetched["asset_name"] == "bookcontent-v101.pt"
        and fetched["download_url"].endswith("/bookcontent-v101.pt")
        and fetched["download_url"].startswith(
            "https://github.com/zunkun/gujitrain/releases/download/database/"),
        f"{fetched['info']} / {fetched['download_url']}",
    )

    # ---- 3. 下载内核：下到版本名 → 校验 sha256 → 释放占用 → 更名 → 重新加载 ----
    data = b"0123456789" * 7000
    digest = hashlib.sha256(data).hexdigest()
    dest = tmp / "bookcontent.pt"
    recorded: list[dict] = []
    phases: list[str] = []
    real_record = dw.record_local_version
    real_urlopen = ud.urllib.request.urlopen
    real_release, real_reload = dw._release_model, dw._reload_model
    dw.record_local_version = lambda i: recorded.append(i)  # type: ignore[assignment]
    dw._release_model = lambda: phases.append("release") or True  # type: ignore[assignment]
    dw._reload_model = lambda: phases.append("reload") or True  # type: ignore[assignment]
    try:
        stages: list[str] = []
        urls: list[str] = []

        def _fake_open(request, timeout=None):
            urls.append(str(getattr(request, "full_url", request)))
            return _FakeResponse(data)

        ud.urllib.request.urlopen = _fake_open  # type: ignore[assignment]
        worker = dw.DataDownloadWorker(
            "https://example.invalid/x.pt",
            {
                "version": 100,
                "name": "bookcontent-v100.pt",
                "sha256": digest,
                "size": len(data),
            },
            dest=dest,
        )
        worker.stage.connect(stages.append)
        result = worker._download()
        ok(
            "下载内核：先落到**版本名**再校验、无残留 .part，最终才是 bookcontent.pt",
            dest.read_bytes() == data
            and not (tmp / "bookcontent-v100.pt").exists()  # 更名后版本名文件不在了
            and not (tmp / "bookcontent-v100.pt.part").exists(),
            f"size={dest.stat().st_size if dest.exists() else 0}",
        )
        ok(
            "下载内核：sha256 校验通过后回带版本号 + 写好版本记录",
            result["version"] == 100
            and result["sha256"] == digest
            and bool(recorded)
            and recorded[-1]["version"] == 100,
            f"{result} / {recorded}",
        )
        ok(
            "替换三步的顺序：校验 → 释放占用 → 更名 → 重新加载",
            stages == ["verify", "release", "replace", "reload"]
            and phases == ["release", "reload"],
            f"stages={stages} phases={phases}",
        )
        ok(
            "下载请求也走防缓存地址（同名重传时不被缓存副本坑成 sha 不符）",
            bool(urls) and "?t=" in urls[-1],
            f"{urls[-1] if urls else None}",
        )

        # sha 不符：删掉下好的版本名文件、**不替换**目标
        ud.urllib.request.urlopen = (  # type: ignore[assignment]
            lambda request, timeout=None: _FakeResponse(b"tampered"))
        bad = dw.DataDownloadWorker(
            "https://example.invalid/x.pt",
            {
                "version": 101,
                "name": "bookcontent-v101.pt",
                "sha256": digest,
                "size": 8,
            },
            dest=dest,
        )
        raised = False
        try:
            bad._download()
        except ValueError:
            raised = True
        ok(
            "校验不符：抛错、目标**不被替换**、下好的版本名文件删掉",
            raised
            and dest.read_bytes() == data
            and not (tmp / "bookcontent-v101.pt").exists(),
            f"raised={raised}",
        )

        # 取消：写出临时文件后中断（不落任何最终文件）
        ud.urllib.request.urlopen = (  # type: ignore[assignment]
            lambda request, timeout=None: _FakeResponse(data))
        cancelled = dw.DataDownloadWorker(
            "https://example.invalid/x.pt",
            {
                "version": 102,
                "name": "bookcontent-v102.pt",
                "sha256": digest,
                "size": len(data),
            },
            dest=dest,
        )
        cancelled.cancel()
        stopped = False
        try:
            cancelled._download()
        except dw._Cancelled:
            stopped = True
        ok(
            "取消下载：抛 _Cancelled 且不留任何文件（目标保持原样）",
            stopped
            and dest.read_bytes() == data
            and not (tmp / "bookcontent-v102.pt").exists()
            and not (tmp / "bookcontent-v102.pt.part").exists(),
            f"stopped={stopped}",
        )
    finally:
        dw.record_local_version = real_record  # type: ignore[assignment]
        ud.urllib.request.urlopen = real_urlopen  # type: ignore[assignment]
        dw._release_model = real_release  # type: ignore[assignment]
        dw._reload_model = real_reload  # type: ignore[assignment]

    # ---- 4. 控制器：真菜单 + 真控制器（弹窗/网络/下载 worker 换替身） ----
    controller = getattr(w, "data_package_controller", None)
    ok("窗口上挂着数据包控制器（与菜单项同源）", controller is not None, "")
    assert controller is not None
    action = _action_of(_menu_of(w, menu.MENU_HELP), menu.ACTION_DATA_PACKAGE)
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
                    "path": "X:/tmp/bookcontent.pt",
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
            wait_until(app, lambda: len(recorder.calls) > 1, timeout=8.0)
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
        pump(app, times=3)
        ok(
            "点「下载」：弹出下载进度窗",
            wait_until(
                app,
                lambda: any(c["title"].startswith("正在下载") for c in recorder.calls),
                timeout=8.0,
            ),
            f"{[c['title'] for c in recorder.calls]}",
        )
        ok(
            "下载完成：弹出「数据包下载完成」，菜单项恢复原文案",
            wait_until(
                app,
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
                app,
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
                app,
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
            wait_until(app, lambda: not controller._checking, timeout=8.0)
            and recorder.calls == []
            and menu.NEW_VERSION_SUFFIX in action.text()
            and "v100" in action.toolTip(),
            f"弹窗={[c['title'] for c in recorder.calls]} text={action.text()!r}",
        )
        # 复位（别把提示留给后面的模块）
        controller._newer_version = 0
        controller._apply_action_text()
    finally:
        menu.shell_dialog = real_shell  # type: ignore[assignment]
        dw.fetch_data_json = real_fetch  # type: ignore[assignment]
        dw.DataDownloadWorker = real_download_cls  # type: ignore[assignment]
        menu.read_local_version = real_read_version  # type: ignore[assignment]
        controller._finish()  # 别把菜单项留在忙态
        controller._finish_download()
