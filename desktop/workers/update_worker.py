# -*- coding: utf-8 -*-
"""「检查更新」的网络 worker（后台线程 + **多线路测速**查 GitHub Release 最新版）。

为什么在子线程
--------------
点「帮助 → 检查更新」要打网络（可能还要并发测 4 条线路），在主线程做就是"点了菜单、
界面卡住"——与本项目「重活/网络全走 worker」的口径一致（见 ``worker_host``）。

为什么要**镜像/测速**（用户 2026-10-15）
---------------------------------------
「github 容易被 ban，所以可以使用代理」——同一个 API 地址可以拼上加速前缀再访问：

    https://v6.gh-proxy.org/  +  https://api.github.com/repos/.../releases/latest
    https://v4.gh-proxy.org/  +  ...
    https://cdn.gh-proxy.org/ +  ...

于是共四种方案（**直连 + 三个镜像**，见 :data:`MIRROR_PREFIXES`）。**先测速再选最快
的那条**去取数据：四条**并发**各打一次（每条都有独立超时，互不拖累），全部失败才
报错。实测这台机器：v6 0.38s / cdn 0.44s / v4 0.69s / 直连 2.42s。

⚠️ **只镜像 API 与 release 资产（.exe），不镜像 release 网页**：实测三个镜像对
``https://github.com/<repo>/releases/latest`` 这种网页一律 **403**，而对 ``api.github.com``
与 ``/releases/download/...`` 资产都正常。所以下载地址取**资产**的
``browser_download_url`` 再拼镜像前缀，不拿网页地址。

只取**原始字段**，不做判断
--------------------------
worker 只"把 release 拉下来 + 归类错误 + 给出测速排名"，**不比较版本**：比较是纯
规则（``utils.version``），放在主线程做——于是自测能只替换本文件的一个模块级函数就
覆盖"已是最新 / 有新版本 / 查询失败"三分支。

``kind`` 的词表（与 ``desktop/ui/menu.py`` 的文案表一一对应）：

===============  ==================================================
``network``      连不上（断网、四个地址全不可达）
``not_found``    HTTP 404（仓库没有 release，或仓库名变了）
``rate_limited`` HTTP 403 / 429（限流；⚠️ 镜像对**网页**返回 403 也归这里）
``bad_json``     响应不是合法 JSON / 缺 ``tag_name``
``http:<code>``  其余 HTTP 错误码，原样带出来
===============  ==================================================
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal, Slot

#: 查"最新版"的 API 端点（仓库地址与 ``utils/help.py`` 里印的项目地址同源）。
RELEASE_API = "https://api.github.com/repos/zunkun/gujitools/releases/latest"

#: 反屏蔽/加速前缀，**空串 = 直连**。四种方案按此顺序就是测速后的候选集合；
#: ⚠️ 顺序不参与"选谁"（选**最快**的那条），只是并发发起时的书写顺序。
MIRROR_PREFIXES: tuple[str, ...] = (
    "",
    "https://v6.gh-proxy.org/",
    "https://v4.gh-proxy.org/",
    "https://cdn.gh-proxy.org/",
)

#: 单条线路的超时（秒）。四条并发 ⇒ 最坏也就等这么久，不会四倍叠加。
TIMEOUT_SECONDS = 6.0

#: ⚠️ GitHub API **要求**带 User-Agent，缺席直接 403（实测）；Accept 头声明用 v3 JSON
#: 口径，避免将来默认口径变化把字段名改掉。
_HEADERS = {
    "User-Agent": "gujitools-updater",
    "Accept": "application/vnd.github+json",
}

#: 从 release 里取的字段（``assets`` 用于拼**镜像过的下载地址**）。
_FIELDS = ("tag_name", "html_url", "name", "published_at", "prerelease", "assets")


class UpdateCheckError(Exception):
    """检查更新失败，``kind`` 是上面词表里的分类串（界面据此选文案）。"""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


def mirror_label(prefix: str) -> str:
    """线路的中文标签：直连 → 「直连」，镜像 → 域名（``v6.gh-proxy.org``）。"""
    if not prefix:
        return "直连"
    return prefix.split("//", 1)[-1].strip("/") or prefix


def build_url(prefix: str, url: str) -> str:
    """把加速前缀拼到原始地址前面（用户给的用法就是**直接拼接**）。"""
    return f"{prefix}{url}"


def _asset_url(payload: dict) -> str:
    """release 里**安装包资产**的下载地址；没有资产时退回网页地址。

    优先 ``.exe``（本项目发行物就是安装包），其次第一个资产。
    """
    assets = payload.get("assets")
    if isinstance(assets, list) and assets:
        named = [a for a in assets if isinstance(a, dict)]
        exe = [a for a in named
               if str(a.get("name") or "").lower().endswith(".exe")]
        pick = (exe or named)[0]
        url = str(pick.get("browser_download_url") or "")
        if url:
            return url
    return str(payload.get("html_url") or "")


def _fetch_one(prefix: str, url: str, timeout: float) -> dict:
    """单条线路拉一次（返回探测结果，含**耗时**；不抛异常——失败进 ``error``）。"""
    request = urllib.request.Request(build_url(prefix, url), headers=_HEADERS)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        seconds = time.monotonic() - started
    except urllib.error.HTTPError as exc:
        return {"prefix": prefix, "ok": False, "payload": None,
                "error": exc.code, "reason": f"http:{exc.code}",
                "seconds": round(time.monotonic() - started, 3)}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"prefix": prefix, "ok": False, "payload": None,
                "error": None, "reason": f"network:{type(exc).__name__}",
                "seconds": round(time.monotonic() - started, 3)}
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
    except (ValueError, UnicodeError):
        return {"prefix": prefix, "ok": False, "payload": None,
                "error": None, "reason": "bad_json", "seconds": round(seconds, 3)}
    if not isinstance(payload, dict) or not str(payload.get("tag_name") or ""):
        return {"prefix": prefix, "ok": False, "payload": None,
                "error": None, "reason": "bad_json", "seconds": round(seconds, 3)}
    return {"prefix": prefix, "ok": True, "payload": payload,
            "error": None, "reason": "", "seconds": round(seconds, 3)}


def _failure_kind(ranking: list[dict]) -> str:
    """四条全败时的错误分类：优先"有意义"的那类（404/限流/坏 JSON > 网络不通）。"""
    reasons = [str(item.get("reason") or "network") for item in ranking]
    for preferred in ("bad_json", "not_found", "rate_limited"):
        for reason in reasons:
            if reason == preferred or reason.startswith(f"{preferred}"):
                return preferred
    for reason in reasons:
        if reason.startswith("http:"):
            return reason
    for reason in reasons:
        if reason.startswith("network:"):
            return "network"
    return "network"


def probe_mirrors(url: str = RELEASE_API,
                  timeout: float = TIMEOUT_SECONDS) -> list[dict]:
    """**并发**测四条线路，返回按耗时升序的排名（每条：前缀/标签/是否可用/耗时/下载地址）。

    ⚠️ 并发是必须的：串行等四条，最坏 4×超时，用户点一下要瞪 24 秒。
    ⚠️ 排名里**带**``download_url``（用它自己的前缀拼出来的资产地址）——界面的
    「换条线路」直接取用，不必再回头拼一次（也就不会漏同步拼接规则）。

    一条都没通时**不抛异常**，由 :func:`fetch_latest_release` 依据排名归类报错
    （这样"哪几条怎么了"对界面也拿得到）。
    """
    candidates = list(MIRROR_PREFIXES)
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, len(candidates))) as pool:
        futures = {
            pool.submit(_fetch_one, prefix, url, timeout): prefix
            for prefix in candidates
        }
        for future, prefix in futures.items():
            try:
                results.append(future.result())
            except Exception as exc:      # noqa: BLE001 - 兜底：探测本身绝不该抛
                results.append({"prefix": prefix, "ok": False, "payload": None,
                                "error": None, "reason": f"network:{type(exc).__name__}",
                                "seconds": float("inf")})
    for item in results:
        payload = item.get("payload")
        item["label"] = mirror_label(item["prefix"])
        item["download_url"] = (
            build_url(item["prefix"], _asset_url(payload)) if payload else ""
        )
    ok_items = sorted(
        (item for item in results if item["ok"]),
        key=lambda item: item.get("seconds", float("inf")),
    )
    return ok_items + [item for item in results if not item["ok"]]


def fetch_latest_release(url: str = RELEASE_API,
                         timeout: float = TIMEOUT_SECONDS) -> dict:
    """经**最快线路**拉取最新 release；四条全败抛 :class:`UpdateCheckError`。

    ⚠️ 刻意做成**模块级函数**（而不是 worker 的方法）：自测要能整体替换它，从而不碰
    真网络地覆盖成功/失败路径。

    返回 ``{"tag_name", "html_url", "name", "published_at", "prerelease", "assets"}``
    再加三样界面要用的东西：

    - ``mirror_prefix`` / ``mirror_label``：这次用的是哪条线路（直连为空串/"直连"）；
    - ``download_url``：**拼过该线路前缀**的安装包下载地址；
    - ``ranking``：四条线路的测速排名（含每条的 ``download_url``，供"换条线路"）。
    """
    ranking = probe_mirrors(url, timeout)
    usable = [item for item in ranking if item["ok"] and item.get("payload")]
    if not usable:
        raise UpdateCheckError(_failure_kind(ranking))
    best = usable[0]
    payload = dict(best["payload"])
    result = {name: payload.get(name) for name in _FIELDS}
    result.update({
        "mirror_prefix": best["prefix"],
        "mirror_label": best["label"],
        "download_url": best["download_url"],
        "seconds": best.get("seconds"),
        "ranking": [
            {"prefix": item["prefix"], "label": item["label"],
             "ok": bool(item["ok"]), "download_url": item["download_url"],
             "seconds": item.get("seconds", float("inf"))}
            for item in ranking
        ],
    })
    return result


class UpdateCheckWorker(QObject):
    """子线程里跑一次 :func:`fetch_latest_release`（QObject，运行于子线程）。

    成功发 ``checked(dict)``（release 原始字段 + 线路信息），失败发 ``failed(kind)``。
    ⚠️ ``run()`` 整体 try/except：异常逃出子线程会让线程静默死掉、界面永远停在
    "正在检查"（仓库硬规则）。
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
    "MIRROR_PREFIXES",
    "RELEASE_API",
    "TIMEOUT_SECONDS",
    "UpdateCheckError",
    "UpdateCheckWorker",
    "build_url",
    "fetch_latest_release",
    "mirror_label",
    "probe_mirrors",
]
