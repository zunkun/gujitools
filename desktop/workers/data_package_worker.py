# -*- coding: utf-8 -*-
"""去底色数据包（``bookcontent*.pt``）的**网络** worker：查版本 + 下载并切换生效。

与「检查更新」（``update_worker``）同族、同样走"直连 + 三个 gh-proxy 镜像并发
测速"，但**对象不同**：那边查的是程序自身的 GitHub Release，这边查的是**权重
仓库**（``zunkun/gujitrain``）``database`` release 里的 ``data.json``，并且要
**把权重文件真的下下来**（用户口径 2026-10-16：不要让用户自己去 GitHub 下载）。

⚠️ 落地口径（用户 2026-10-22）：下载下来的文件**保留发布名**
（``bookcontent-v105.pt``），**不改名**成 ``bookcontent.pt``；"哪一份生效"由
``bookcontent.version.json`` 的 ``name`` 决定（见 ``utils/data_package.py``）。
目录里因此会同时存在多份权重，只用一份。

⚠️ 两处**不照抄** ``update_worker``（用户 2026-10-16 报「数据包检查不对，线上是
101」，本机 v100、远端已发 v101 却报"已是最新"）：

1. **不按"最快"选线路，按"清单里的 version 最大"选**——release 资产地址是固定的，
   缓存命中的旧清单**一定更快**，按速度选就会系统性地选到旧版本（选择规则 =
   ``utils.data_package.pick_latest``，与在线兜底共用）；
2. **请求一律挂 :func:`_cache_bust` 的唯一参数**，把缓存副本作废、逼各路回源。

⚠️ **不能直接复用** ``update_worker.probe_mirrors``：它的 ``_fetch_one`` 校验
``tag_name``（release 字段），而 ``data.json`` 根本没有这个字段，会被判成
``bad_json``。所以这里自带一份"只要求是合法 JSON 对象"的探测（``_fetch_one``）。

``kind`` 词表与 ``desktop/ui/menu.py::FAILURE_REASONS`` 一一对应：

===============  ==================================================
``network``      连不上（断网、四个地址全不可达）
``not_found``    HTTP 404
``rate_limited`` HTTP 403 / 429
``bad_json``     响应不是合法 JSON / 缺 bookcontent 记录
``http:<code>``  其余 HTTP 错误码
``cancelled``    下载被用户取消（只在 :class:`DataDownloadWorker` 出现）
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

from desktop.workers.update_worker import TIMEOUT_SECONDS
from utils.data_package import (
    MIRROR_PREFIXES,
    asset_url,
    build_url,
    cache_bust as _cache_bust,
    data_json_url,
    mirror_label,
    pick_latest,
    record_local_version,
    sha256_of,
    weights_dir,
)
from utils.download import DownloadCancelled, stream_to_file
from utils.file_utils import replace_with_retry

__all__ = [
    "DATA_PACKAGE_STAGES",
    "DataCheckError",
    "DataCheckWorker",
    "DataDownloadWorker",
    "DOWNLOAD_TIMEOUT",
    "fetch_data_json",
    "probe_mirrors",
]

#: 单条线路的超时（秒）；四条并发 ⇒ 最坏也就等这么久。
TIMEOUT = TIMEOUT_SECONDS

#: 下载整包的超时（秒）。比"取小 JSON"宽得多：6MB 走慢线路也要给足时间。
DOWNLOAD_TIMEOUT = 120.0

#: 替换权重前"等常驻服务退出、释放文件句柄"的最长等待（秒）。
RELEASE_WAIT = 8.0

_HEADERS = {
    "User-Agent": "gujitools-updater",
    "Accept": "application/json",
}

#: 防缓存参数：实现与理由在 ``utils.data_package.cache_bust``（与在线兜底共用一份），
#: 这里以 ``_cache_bust`` 的名字沿用（自测直接调 ``dw._cache_bust``）。


class DataCheckError(Exception):
    """检查数据包失败，``kind`` 是模块头词表里的分类串。"""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


#: 下载被取消：沿用 ``utils.download`` 的异常（与程序更新共用同一套下载内核）。
_Cancelled = DownloadCancelled


def _fetch_one(prefix: str, url: str, timeout: float) -> dict:
    """单条线路拉一次 ``data.json``（失败进 ``error``，不抛）。"""
    request = urllib.request.Request(build_url(prefix, url), headers=_HEADERS)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        seconds = time.monotonic() - started
    except urllib.error.HTTPError as exc:
        return {"prefix": prefix, "ok": False, "payload": None,
                "reason": f"http:{exc.code}",
                "seconds": round(time.monotonic() - started, 3)}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"prefix": prefix, "ok": False, "payload": None,
                "reason": f"network:{type(exc).__name__}",
                "seconds": round(time.monotonic() - started, 3)}
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
    except (ValueError, UnicodeError):
        return {"prefix": prefix, "ok": False, "payload": None,
                "reason": "bad_json", "seconds": round(seconds, 3)}
    if not isinstance(payload, dict):
        return {"prefix": prefix, "ok": False, "payload": None,
                "reason": "bad_json", "seconds": round(seconds, 3)}
    return {"prefix": prefix, "ok": True, "payload": payload,
            "reason": "", "seconds": round(seconds, 3)}


def probe_mirrors(url: str | None = None,
                  timeout: float = TIMEOUT) -> list[dict]:
    """**并发**测四条线路，返回按耗时升序的排名（每条含 ``reason``/``seconds``）。

    与 ``update_worker.probe_mirrors`` 结构一致，只是校验规则不同（见模块头）。
    一条都没通时不抛异常，由 :func:`fetch_data_json` 依据排名归类报错。

    ⚠️ 取的是**挂了防缓存参数**的地址（见 :func:`_cache_bust`）：四条线路共用同一个
    本次唯一的 ``t=``，让任何缓存副本都作废、逼各路回源。
    """
    target = _cache_bust(url or data_json_url())
    candidates = list(MIRROR_PREFIXES)
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, len(candidates))) as pool:
        futures = {
            pool.submit(_fetch_one, prefix, target, timeout): prefix
            for prefix in candidates
        }
        for future, prefix in futures.items():
            try:
                results.append(future.result())
            except Exception as exc:      # noqa: BLE001 - 探测本身绝不该抛
                results.append({"prefix": prefix, "ok": False, "payload": None,
                                "reason": f"network:{type(exc).__name__}",
                                "seconds": float("inf")})
    for item in results:
        item["label"] = mirror_label(item["prefix"])
    ok_items = sorted(
        (item for item in results if item["ok"]),
        key=lambda item: item.get("seconds", float("inf")),
    )
    return ok_items + [item for item in results if not item["ok"]]


def _failure_kind(ranking: list[dict]) -> str:
    """四条全败时的错误分类（与 ``update_worker`` 同口径）。"""
    reasons = [str(item.get("reason") or "network") for item in ranking]
    for preferred in ("bad_json", "not_found", "rate_limited"):
        for reason in reasons:
            if reason == preferred or reason.startswith(f"{preferred}"):
                return preferred
    for reason in reasons:
        if reason.startswith("http:"):
            return reason
    return "network"


def fetch_data_json(url: str | None = None,
                    timeout: float = TIMEOUT) -> dict:
    """经**最快线路**取 ``data.json`` 并规范化出 bookcontent 记录。

    四条全败或清单里没有合法的 bookcontent 记录时抛 :class:`DataCheckError`。
    返回::

        {
          "info": {name, version, sha256, size, date},
          "asset_name": name,
          "download_url": 拼过**最优线路**前缀的权重地址,
          "mirror_prefix" / "mirror_label" / "seconds",
          "ranking": [{prefix, label, ok, seconds}, ...],
        }

    ⚠️ ``download_url`` 与 :func:`probe_mirrors` 用的是**同一次**测速结果里
    **版本号最高**的那条（不再重测一遍），所以下载必然走"给出最新清单"的那条线路。
    ⚠️ 不是"最快"而是"最新"：会命中缓存的旧清单**一定更快**，按速度选就会系统性
    地报成"已是最新"（见 :func:`_cache_bust`）。
    """
    ranking = probe_mirrors(url, timeout)
    usable = [item for item in ranking if item["ok"] and item.get("payload")]
    if not usable:
        raise DataCheckError(_failure_kind(ranking))
    # 逐条解析，**取 version 最大的那条**；并列时保留排名在前（更快）的那条。
    # 选择规则与在线兜底共用 ``utils.data_package.pick_latest``（唯一实现）。
    picked = pick_latest([(item["prefix"], item["payload"]) for item in usable])
    if picked is None:
        raise DataCheckError("bad_json")
    prefix, info = picked
    best = next((item for item in usable if item["prefix"] == prefix), usable[0])
    return {
        "info": info,
        "asset_name": info["name"],
        "download_url": build_url(prefix, asset_url(info["name"])),
        "mirror_prefix": prefix,
        "mirror_label": best["label"],
        "seconds": best.get("seconds"),
        "ranking": [
            {"prefix": item["prefix"], "label": item["label"],
             "ok": bool(item["ok"]), "seconds": item.get("seconds", float("inf"))}
            for item in ranking
        ],
    }


class DataCheckWorker(QObject):
    """子线程里跑一次 :func:`fetch_data_json`。

    成功发 ``checked(dict)``，失败发 ``failed(kind)``。⚠️ ``run()`` 整体
    try/except：异常逃出子线程会让线程静默死掉、界面永远停在"正在检查"。
    """

    checked = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str | None = None, timeout: float = TIMEOUT):
        super().__init__()
        self.url = url
        self.timeout = timeout

    @Slot()
    def run(self) -> None:
        """执行一次检查并通过信号回报结果（异常一律走 ``failed``）。"""
        try:
            self.checked.emit(fetch_data_json(self.url, self.timeout))
        except DataCheckError as exc:
            self.failed.emit(exc.kind)
        except Exception as exc:      # noqa: BLE001 - 兜底：绝不把异常留给子线程
            self.failed.emit(f"http:{exc}")


#: 替换流程的阶段码 → 界面文案（``DataDownloadWorker.stage`` 发码，控制器渲染）。
DATA_PACKAGE_STAGES = {
    "verify": "正在校验文件完整性…",
    "release": "正在释放模型占用…",
    "replace": "正在启用新模型文件…",
    "reload": "正在重新加载模型…",
}


class DataDownloadWorker(QObject):
    """子线程里把权重下载到本地，**校验通过后**才切换生效文件（用户 2026-10-16 / 10-22）。

    严格顺序：

    1. **下载**权重到 ``<权重目录>/bookcontent-v105.pt``（传输期用 ``*.part``，
       下完才改成发布名）；中途失败/取消**不留半截文件**。⚠️ 本地已有同名同 sha
       的文件就**不重复下载**（见 :func:`_existing_file`）；
    2. **校验 sha256**：与 ``data.json`` 不符就删掉、报错——**不切换**；
    3. **释放占用**（``_release_model``：关掉常驻 YOLO 服务，卸载内存里的模型、
       松开权重的文件句柄）；
    4. **切换生效文件**：只改写 sidecar ``bookcontent.version.json``
       （``record_local_version``）指向新文件——**不再把新文件改名成
       ``bookcontent.pt``**（用户 2026-10-22：目录里可以留多个 pt，只有一个生效，
       旧版原地留着可回退）；
    5. **重新加载**（``_reload_model``：把常驻服务重新热起来，内存引用指向新权重）。

    信号：

    * ``progress(int)``：0~100 的百分比；**-1** 表示总量未知（无 Content-Length）；
    * ``stage(str)``：下载之后的阶段码（见 :data:`DATA_PACKAGE_STAGES`）；
    * ``finished(dict)``：``{path, version, sha256, size}``（``path`` 是**发布名**
      文件的绝对路径，不是 ``bookcontent.pt``）；
    * ``failed(str)``：分类串（``network`` / ``cancelled`` / ``http:<code>`` 等）。

    ⚠️ 先写 ``*.part`` 再改名：下载途中文件不能以最终名存在（否则 YOLO 服务/
    检测进程可能读到**半截权重**）。
    """

    progress = Signal(int)
    stage = Signal(str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str, info: dict | None = None,
                 dest=None):
        super().__init__()
        self.url = url
        self.info = dict(info or {})
        #: 目标**权重目录**（不是目标文件）：具体文件名取 ``info["name"]``。
        self.dest = Path(dest) if dest is not None else weights_dir()
        self._cancelled = False

    def cancel(self) -> None:
        """请求取消（``WorkerHost.shutdown_workers`` 也会调它）。"""
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        """执行下载并通过信号回报结果（异常一律走 ``failed``）。"""
        try:
            self.finished.emit(self._download())
        except _Cancelled:
            self.failed.emit("cancelled")
        except urllib.error.HTTPError as exc:
            self.failed.emit(f"http:{exc.code}")
        except Exception as exc:      # noqa: BLE001 - 兜底：绝不把异常留给子线程
            self.failed.emit(f"network:{type(exc).__name__}")

    def _transfer(self, temp: Path) -> tuple[str, int]:
        """流式下载到 ``temp``（共用 ``utils.download.stream_to_file``）。

        中途失败/取消**一定删掉 temp**——半截临时文件绝不能留下。

        ⚠️ 请求走 :func:`_cache_bust`：资产地址是固定的，若上游用**同一个版本名**
        重新上传（内容变了、名字没变），缓存副本会让 sha256 校验对不上而白下载
        一次。挂个唯一参数即绕开。
        """
        return stream_to_file(
            _cache_bust(self.url), temp,
            on_progress=self._emit_progress,
            is_cancelled=lambda: self._cancelled,
            timeout=DOWNLOAD_TIMEOUT,
            headers=_HEADERS,
        )

    def _emit_progress(self, written: int, total: int) -> None:
        """把 ``(已写字节, 总字节)`` 折成 0~100 进度；总量未知发 -1。"""
        self.progress.emit(int(written * 100 / total) if total else -1)

    def _download(self) -> dict:
        """真正干活（顺序见类 docstring）。"""
        weights = self.dest
        weights.mkdir(parents=True, exist_ok=True)
        # 落地用**发布名**（``bookcontent-v105.pt``）：用户口径是"下到本地还是叫
        # 这个名字"，由 sidecar 决定哪一份生效，不再改名成 bookcontent.pt。
        asset_name = Path(str(self.info.get("name") or "").strip()).name
        if not asset_name:
            version = int(self.info.get("version") or 0)
            asset_name = f"bookcontent-v{version}.pt" if version else "bookcontent.pt"
        target = weights / asset_name
        temp = target.with_name(target.name + ".part")
        expected = str(self.info.get("sha256") or "").lower()

        # 本地已有**同一份**（同名同 sha）：不重复下载，直接走"切换生效"。
        # ⚠️ 这不只是省流量：目标文件可能正被常驻服务打开，Windows 上往它身上
        # ``os.replace`` 会 PermissionError（而这一步在"释放占用"之前）。
        actual, written = _existing_file(target, expected)
        if not actual:
            actual, written = self._transfer(temp)
            replace_with_retry(temp, target)     # .part → 发布名文件

        # ---- 校验：不符就删掉，绝不启用 ----
        self.stage.emit("verify")
        if expected and actual != expected:
            _unlink_quiet(target)
            raise ValueError("sha256-mismatch")

        # ---- 1) 释放内存/句柄占用 → 2) 切换生效文件 → 3) 重新加载 ----
        self.stage.emit("release")
        _release_model()
        self.stage.emit("replace")
        # 切换 = 改写 sidecar 的 name（旧文件留在目录里，可回退）。
        record_local_version({**self.info, "name": asset_name}, weights)
        self.stage.emit("reload")
        _reload_model()

        return {"path": str(target), "version": int(self.info.get("version") or 0),
                "sha256": actual, "size": written, "asset_name": asset_name}


def _release_model() -> bool:
    """切换生效权重前**释放内存/文件句柄占用**：关掉常驻 YOLO 服务。

    常驻服务把模型（约 350MB）与权重文件句柄都握在手里——不先关掉，重新加载时
    服务会按**旧指纹**（旧权重路径 + 大小/mtime）继续用旧模型，用户看到的就是
    "下载了新版本、检测还是老结果"。这里关服务并**等它真的退出**（轮询发现
    发现文件消失），再让调用方去切换 sidecar。

    返回是否真的关掉了一个在跑的服务（没有服务时 ``False``，属正常）。

    ⚠️ 函数内延迟导入 ``functions``：分层守卫要求 desktop 的**模块级** import 只能
    到 utils/core（见 ``tests/selftests/layering.py``），延迟导入是放行的。
    ⚠️ 释放失败**不当错误抛**（服务可能本来就没起、或关不掉）：让后续更名去暴露
    真正的占用问题。
    """
    try:
        from functions import yolo_service as ys

        if ys.service_status() is None:
            return False
        ys.shutdown_service()
        deadline = time.monotonic() + RELEASE_WAIT
        while time.monotonic() < deadline:
            if ys.service_status() is None:
                break
            time.sleep(0.2)
        ys.client_log("数据包替换：已关闭常驻 YOLO 服务以释放权重占用")
        return True
    except Exception:  # noqa: BLE001 - 释放尽力而为，绝不因此让替换流程失败
        return False


def _reload_model() -> bool:
    """更名完成后**重新加载**模型：把常驻服务重新热起来（内存引用指向新权重）。

    与 GUI 预加载同一条路（``warm_up_service_only``：**只走常驻服务、绝不回落本
    进程加载**，见 ``desktop/services/yolo_prewarm.py``），因为替换发生在 GUI 进程
    的 worker 线程里，回落会把 torch 拽进 GUI 进程（违反分层守卫）。

    返回是否在常驻服务里就绪。
    """
    try:
        from functions import yolo_service as ys

        backend, _seconds = ys.warm_up_service_only()
        return backend == "service"
    except Exception:  # noqa: BLE001 - 重载失败只影响"下次检测要现载"，不算错误
        return False


def _existing_file(path: Path, expected: str) -> tuple[str, int]:
    """``path`` 已存在且 sha256 与 ``expected`` 一致 ⇒ 返回 ``(sha, 字节数)``，否则 ``("", 0)``。

    用于"重下同一版本"（比如 sidecar 回退后又换回来）：本地已有**完全一样**的
    文件就不再下一遍。⚠️ 这不只是省流量：目标文件可能正被常驻服务打开，Windows
    上往它身上 ``os.replace`` 会 ``PermissionError``，而下载落地发生在"释放占用"
    之前（见 :meth:`DataDownloadWorker._download`）。
    """
    if not expected:
        return "", 0
    try:
        if not path.is_file() or sha256_of(path) != expected:
            return "", 0
        return expected, path.stat().st_size
    except OSError:
        return "", 0


def _unlink_quiet(path: Path) -> None:
    """删文件、没删掉也不抛（清理尽力而为）。"""
    try:
        path.unlink()
    except OSError:
        pass
