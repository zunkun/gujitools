# -*- coding: utf-8 -*-
"""「检查更新」的网络请求 worker（后台线程查 GitHub Release 最新版）。

为什么在子线程
--------------
点「帮助 → 检查更新」时，请求要打到 ``api.github.com``：DNS/连接/读取加起来
在网络不佳时能到秒级。放在主线程就是"点了菜单、界面卡住"——与本项目
「重活/网络全走 worker」的口径一致（见 ``worker_host`` 的说明）。

只取**原始字段**，不做判断
--------------------------
worker 只负责"把 release 拉下来 + 归类错误"，**不比较版本**：比较是纯规则
（``utils.version``），放在主线程做——于是自测能只替换本文件的一个模块级函数
就覆盖"已是最新 / 有新版本 / 查询失败"三分支。

``kind`` 的词表（与 ``desktop/ui/menu.py`` 的文案表一一对应，别各写一份）：

===============  ==================================================
``network``      连不上 / 超时（断网、公司网络挡了 api.github.com）
``not_found``    HTTP 404（仓库没有 release，或仓库名变了）
``rate_limited`` HTTP 403 / 429（GitHub 匿名调用限流）
``bad_json``     响应不是合法 JSON / 缺 ``tag_name``
``http:<code>``  其余 HTTP 错误码，原样带出来
===============  ==================================================
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from PySide6.QtCore import QObject, Signal, Slot

#: 查"最新版"的端点。仓库地址与 ``utils/help.py`` 里印的项目地址同源。
RELEASE_API = "https://api.github.com/repos/zunkun/gujitools/releases/latest"

#: 请求超时（秒）。检查更新是**用户点了才做**的一次性动作，等太久不如报错。
TIMEOUT_SECONDS = 6.0

#: ⚠️ GitHub API **要求**带 User-Agent，缺席直接 403（实测）；Accept 头声明
#: 用 v3 JSON 口径，避免将来默认口径变化把字段名改掉。
_HEADERS = {
    "User-Agent": "gujitools-updater",
    "Accept": "application/vnd.github+json",
}

#: 从 release 里取的字段（其余字段不取——少一份随上游变化而失效的耦合）。
_FIELDS = ("tag_name", "html_url", "name", "published_at", "prerelease")


class UpdateCheckError(Exception):
    """检查更新失败，``kind`` 是上面词表里的分类串（界面据此选文案）。"""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


def fetch_latest_release(url: str = RELEASE_API,
                         timeout: float = TIMEOUT_SECONDS) -> dict:
    """拉取最新 release 的原始字段；失败抛 :class:`UpdateCheckError`。

    ⚠️ 刻意做成**模块级函数**（而不是 worker 的方法）：自测要能整体替换它，
    从而不碰真网络地覆盖成功/失败路径。

    返回 ``{"tag_name", "html_url", "name", "published_at", "prerelease"}``；
    ``tag_name`` 缺失视为 ``bad_json``（比大小全靠它，没有就无话可说）。
    """
    request = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        code = int(getattr(exc, "code", 0) or 0)
        if code == 404:
            raise UpdateCheckError("not_found") from exc
        if code in (403, 429):
            raise UpdateCheckError("rate_limited") from exc
        raise UpdateCheckError(f"http:{code}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # URLError 覆盖 DNS/连接失败与超时；ValueError 覆盖非法 URL。
        raise UpdateCheckError("network") from exc
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
    except (ValueError, UnicodeError) as exc:
        raise UpdateCheckError("bad_json") from exc
    if not isinstance(payload, dict) or not str(payload.get("tag_name") or ""):
        raise UpdateCheckError("bad_json")
    return {name: payload.get(name) for name in _FIELDS}


class UpdateCheckWorker(QObject):
    """子线程里跑一次 :func:`fetch_latest_release`（QObject，运行于子线程）。

    成功发 ``checked(dict)``（release 原始字段），失败发 ``failed(kind)``。
    ⚠️ ``run()`` 整体 try/except：异常逃出子线程会让线程静默死掉、界面永远
    停在"正在检查"（仓库硬规则）。
    """

    checked = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str = RELEASE_API,
                 timeout: float = TIMEOUT_SECONDS):
        super().__init__()
        self.url = url
        self.timeout = timeout

    @Slot()
    def run(self) -> None:
        """执行一次检查并通过信号回报结果（异常一律走 ``failed``）。"""
        try:
            self.checked.emit(fetch_latest_release(self.url, self.timeout))
        except UpdateCheckError as exc:
            self.failed.emit(exc.kind)
        except Exception as exc:      # noqa: BLE001 - 兜底：绝不把异常留给子线程
            self.failed.emit(f"http:{exc}")


__all__ = [
    "RELEASE_API",
    "TIMEOUT_SECONDS",
    "UpdateCheckError",
    "UpdateCheckWorker",
    "fetch_latest_release",
]
