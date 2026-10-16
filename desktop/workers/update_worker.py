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
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from utils.download import DownloadCancelled, stream_to_file
from utils.file_utils import replace_with_retry

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

#: 下载安装包的超时（秒）。⚠️ 这是**每次 socket 操作**的超时（不是整包总时长），
#: 所以大安装包不会被它掐死；只有某次读写卡住过久才抛。
DOWNLOAD_TIMEOUT = 300.0

#: 程序更新下载的阶段码 → 界面文案（``AppDownloadWorker.stage`` 发码，控制器渲染）。
APP_UPDATE_STAGES = {
    "verify": "正在校验安装包完整性…",
}

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


def _as_int(value) -> int:
    """宽松转 int（拿不到就 0）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def pick_asset(payload: dict) -> dict:
    """release 里**安装包资产**的信息；没有可用资产时返回 ``{}``。

    优先 ``.exe``（本项目发行物就是 Inno 安装包），其次第一个资产。返回::

        {"name": 文件名, "url": 直连下载地址, "size": 字节数, "sha256": 十六进制}

    ``sha256`` 取 GitHub API 资产对象的 ``digest``（形如 ``"sha256:..."``）；
    **老 release 没有这个字段** ⇒ 空串，此时下载后不做校验（不谎报"校验失败"）。
    """
    assets = payload.get("assets")
    if not isinstance(assets, list) or not assets:
        return {}
    named = [a for a in assets if isinstance(a, dict)]
    if not named:
        return {}
    exe = [a for a in named
           if str(a.get("name") or "").lower().endswith(".exe")]
    pick = (exe or named)[0]
    url = str(pick.get("browser_download_url") or "")
    if not url:
        return {}
    digest = str(pick.get("digest") or "")
    if digest.lower().startswith("sha256:"):
        digest = digest.split(":", 1)[1]
    return {
        "name": str(pick.get("name") or ""),
        "url": url,
        "size": _as_int(pick.get("size")),
        "sha256": digest.strip().lower(),
    }


def _asset_url(payload: dict) -> str:
    """安装包资产的下载地址；没有资产时退回网页地址（探测排名用）。"""
    return pick_asset(payload).get("url") or str(payload.get("html_url") or "")


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
        "asset": pick_asset(payload),
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


class AppDownloadWorker(QObject):
    """子线程里把**安装包**下下来（应用内下载；用户 2026-10-16 要求）。

    与 :class:`~desktop.workers.data_package_worker.DataDownloadWorker` 共用
    ``utils.download.stream_to_file``；差别是这里**不做替换/重载**——安装包只是
    下到用户目录，真正的安装交给安装器（见 ``desktop/ui/menu.py`` 的
    ``_install_and_restart``）。

    信号：``progress(int)`` / ``stage(str)`` / ``finished(dict)`` / ``failed(str)``。
    """

    progress = Signal(int)
    stage = Signal(str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str, dest, sha256: str = "", size: int = 0,
                 timeout: float = DOWNLOAD_TIMEOUT):
        super().__init__()
        self.url = url
        self.dest = Path(dest)
        self.sha256 = str(sha256 or "").lower()
        self.size = int(size or 0)
        self.timeout = timeout
        self._cancelled = False

    def cancel(self) -> None:
        """请求取消（``WorkerHost.shutdown_workers`` 也会调它）。"""
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        """下载安装包并通过信号回报结果（异常一律走 ``failed``）。"""
        try:
            self.finished.emit(self._download())
        except DownloadCancelled:
            self.failed.emit("cancelled")
        except urllib.error.HTTPError as exc:
            self.failed.emit(f"http:{exc.code}")
        except Exception as exc:      # noqa: BLE001 - 兜底：绝不把异常留给子线程
            self.failed.emit(f"network:{type(exc).__name__}")

    def _download(self) -> dict:
        """流式下载（``*.part`` 先行）→ 校验摘要（有才验）→ 落盘。"""
        dest = self.dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        temp = dest.with_name(dest.name + ".part")
        actual, written = stream_to_file(
            self.url, temp,
            on_progress=self._emit_progress,
            is_cancelled=lambda: self._cancelled,
            timeout=self.timeout,
            headers=_HEADERS,
        )
        replace_with_retry(temp, dest)
        self.stage.emit("verify")
        if self.sha256 and actual != self.sha256:
            # 摘要不符：删掉下好的安装包，别让半截/被篡改的东西留着被"安装"
            _unlink_quiet(dest)
            raise ValueError("sha256-mismatch")
        return {"path": str(dest), "name": dest.name,
                "sha256": actual, "size": written}

    def _emit_progress(self, written: int, total: int) -> None:
        """把 ``(已写字节, 总字节)`` 折成 0~100 进度；总量未知发 -1。"""
        self.progress.emit(int(written * 100 / total) if total else -1)


def _unlink_quiet(path: Path) -> None:
    """删文件、没删掉也不抛（清理尽力而为）。"""
    try:
        Path(path).unlink()
    except OSError:
        pass


__all__ = [
    "APP_UPDATE_STAGES",
    "AppDownloadWorker",
    "DOWNLOAD_TIMEOUT",
    "MIRROR_PREFIXES",
    "RELEASE_API",
    "TIMEOUT_SECONDS",
    "UpdateCheckError",
    "UpdateCheckWorker",
    "build_url",
    "fetch_latest_release",
    "mirror_label",
    "pick_asset",
    "probe_mirrors",
]
