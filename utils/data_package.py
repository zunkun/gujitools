# -*- coding: utf-8 -*-
"""去底色数据包（权重 ``bookcontent*.pt``）的命名规则、**生效判定**与本地版本记录。

背景（用户 2026-10-16 / 2026-10-22）
-----------------------------------
YOLO 权重由**另一个仓库**（``zunkun/gujitrain``）的 ``database`` release 分发。
那个 release 里除了权重本体，还有一份 ``data.json``，逐文件描述 ``name`` /
``version``（整数）/ ``sha256`` / ``size`` / ``date``::

    {
      "generated_at": "2026-10-16T09:22:21+08:00",
      "release": "database",
      "files": {
        "bookcontent": {"name": "bookcontent-v105.pt", "version": 105, ...},
        "gujiline":    {"name": "gujiline-v105.pt",    "version": 105, ...}
      }
    }

桌面端据此判断"本机权重是不是旧版"，有新版就提示并可一键下载替换（**不让用户
自己去 GitHub 下载**）。

权重目录的存放口径（用户 2026-10-22 定稿）
------------------------------------------
``static/weights`` 下**可以同时存在多个** ``.pt``，但**只有一个生效**：

* 下载下来的文件**保留发布名**（``bookcontent-v105.pt``），**不再改名**成
  ``bookcontent.pt``——旧版文件留在原地，出问题随时能退回；
* "哪一份生效"由 sidecar ``bookcontent.version.json`` 的 ``name`` 字段说了算
  （下载成功后由 :func:`record_local_version` 改写这一份，等于"切换生效文件"）；
* 安装包预置的 ``bookcontent.pt``（不带版本号，版本按 0 计）是最后的兜底。

生效文件的解析顺序（:func:`resolve_weights`，逐条对应用户口径）::

    ① sidecar 存在、且它指的 name 在本地         → 用它
    ② sidecar 不存在（或没有 name）               → 用 bookcontent.pt
    ③ sidecar 在、它指的文件却不在本地            → 本地**版本号最大**的
                                                   bookcontent-vNNN.pt
    ④ 再退回 bookcontent.pt
    ⑤ 一个都没有                                   → ``None``（调用方联网下载最新）

⚠️ ③ 之后才轮到 ④：用户明确要求"配置文件在、但对不上文件时先挑版本最大的那个"。
⚠️ 只在 ⑤ 才联网：本地只要还有**任何**一份权重就先跑着，不为了"可能更新"白下
   6MB（下载是最后手段，不是第一手段）。
⚠️ 迁移兼容：旧版下载流程是"下完 ``bookcontent-vNNN.pt`` 再改名成
   ``bookcontent.pt``"，所以升级上来的机器会出现"sidecar 写 v105、目录里只有
   ``bookcontent.pt``"。若两者**字节数一致**，就按 sidecar 的版本算
   （:func:`effective_info` 的 ``source="legacy"``），不重复下载。

为什么单列成模块（而不是塞进 ``yolo_utils``）
--------------------------------------------
1. 解析/判定/记录全是**纯规则**（JSON 解析 + 整数比大小 + 读一份 sidecar），没有
   cv2 / torch；而桌面**主进程**要用它（``desktop/ui/menu.py`` 的检查/下载），主
   进程**不许** import 重依赖（见 AGENTS 分层守卫）。``yolo_utils`` 模块级 import
   numpy，把纯规则塞进去等于顺带把 numpy 拽进启动。
2. 反过来 ``yolo_utils.model_path()`` 复用本模块的 :func:`resolve_weights` /
   :func:`weights_dir`：权重目录与命名规则**只此一处**，两边各写一份迟早漂移。

本模块里**唯一会打网络**的是 :func:`ensure_weights_online`（本机一份权重都没有
时兜底下载），只被 CLI / 常驻服务的加载路径调用；桌面端有完整的检查/下载流程
（``desktop/services`` + ``desktop/workers/data_package_worker.py``），不走它。
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from utils.download import stream_to_file
from utils.file_utils import replace_with_retry

#: ``database`` release 的资产下载前缀（GitHub Release 的固定形态：
#: ``https://github.com/<owner>/<repo>/releases/download/<tag>/``）。
#: ⚠️ 这是**另一个仓库**（``zunkun/gujitrain``），与程序自身的
#: ``zunkun/gujitools`` 不是同一个；换仓库/换 tag 时这里与发布流水线要一起改。
RELEASE_DOWNLOAD_BASE = (
    "https://github.com/zunkun/gujitrain/releases/download/database/"
)

#: 版本清单文件名（release 资产之一；先拿它问"有没有新版"）。
DATA_JSON_NAME = "data.json"

#: ``data.json`` 里本程序关心的文件键（内容框检测模型）。
BOOKCONTENT_KEY = "bookcontent"

#: 安装包预置的**兜底**权重文件名（不带版本号；版本按 0 计）。
LOCAL_WEIGHTS_NAME = "bookcontent.pt"

#: 发布资产名里"带版本号"的形态：``bookcontent-v105.pt``。
#: ⚠️ 下载后**保留**这个名字（用户 2026-10-22），不再改名成兜底名。
VERSIONED_PREFIX = "bookcontent-v"

#: 权重文件后缀。
WEIGHTS_SUFFIX = ".pt"

#: 本地版本 sidecar 文件名（放权重目录旁；``name`` 字段决定哪份权重生效）。
VERSION_FILE_NAME = "bookcontent.version.json"

#: 权重所在子目录（相对仓库根）。与 ``yolo_utils`` 共用的唯一来源。
WEIGHTS_SUBPATH = ("static", "weights")

#: 反屏蔽/加速前缀，**空串 = 直连**。四种方案按此顺序就是测速后的候选集合。
#: ⚠️ 唯一来源在这里：程序更新（``desktop/workers/update_worker.py``）与数据包
#: 下载（``desktop/workers/data_package_worker.py``、本模块的在线兜底）共用，
#: 别再各写一份（改了一处漏另一处 = 某条线路永远试不到）。
#: ⚠️ 顺序不参与"选谁"（程序更新选**最快**那条），只是并发发起时的书写顺序。
MIRROR_PREFIXES: tuple[str, ...] = (
    "",
    "https://v6.gh-proxy.org/",
    "https://v4.gh-proxy.org/",
    "https://cdn.gh-proxy.org/",
)

#: 取 ``data.json`` 时单条线路的超时（秒）。
MANIFEST_TIMEOUT = 6.0

#: 下载整包的超时（秒）；这是**每次 socket 操作**的超时，不是整包总时长。
WEIGHTS_TIMEOUT = 120.0

#: GitHub 要求的请求头（缺 ``User-Agent`` 直接 403）。
_HEADERS = {
    "User-Agent": "gujitools-updater",
    "Accept": "application/json",
}

#: 带版本号的权重文件名 → 版本号（``bookcontent-v105.pt`` → 105）。
_VERSIONED_RE = re.compile(
    rf"^{re.escape(VERSIONED_PREFIX)}(\d+){re.escape(WEIGHTS_SUFFIX)}$",
    re.IGNORECASE,
)

#: 防缓存参数里的**进程内自增序号**（见 :func:`cache_bust`）。
_CACHE_BUST_SEQ = itertools.count(1)


# ---------------------------------------------------------------- 地址与线路
def data_json_url() -> str:
    """``data.json`` 的**直连**地址（镜像前缀由调用方 :func:`build_url` 拼）。"""
    return RELEASE_DOWNLOAD_BASE + DATA_JSON_NAME


def asset_url(name: str) -> str:
    """release 里某个资产的**直连**下载地址（镜像前缀由调用方拼）。"""
    return RELEASE_DOWNLOAD_BASE + str(name)


def mirror_label(prefix: str) -> str:
    """线路的中文标签：直连 → 「直连」，镜像 → 域名（``v6.gh-proxy.org``）。"""
    if not prefix:
        return "直连"
    return prefix.split("//", 1)[-1].strip("/") or prefix


def build_url(prefix: str, url: str) -> str:
    """把加速前缀拼到原始地址前面（用户给的用法就是**直接拼接**）。"""
    return f"{prefix}{url}"


def cache_bust(url: str) -> str:
    """给 URL 挂一个**本次调用唯一**的查询串，绕开 CDN/镜像对固定 URL 的缓存。

    ``data.json`` 与权重资产都是 GitHub Release 的**固定下载地址**，而 release
    资产会被"同名覆盖"（``data.json`` 每次发布都重写、文件名却不变）。这类地址
    实测确实被缓存：三个 gh-proxy 是 ``Cache-Control: public, max-age=60``，直连
    回包的 ``Age`` 有 300s+。

    ⚠️ 危害不止"看到旧内容"：**缓存命中的那条线路一定更快**，而程序更新是"选最快
    那条"，于是系统性地选中**旧清单**——用户 2026-10-16 报的「数据包检查不对，
    线上是 101」（本机 v100、远端已发 v101，检查却报"已是最新"）正是这个成因。
    每次换一个新缓存键即可让各线路回源。
    """
    sep = "&" if "?" in url else "?"
    # ⚠️ 只靠 ``time.time_ns()`` 在 Windows 上**不保证唯一**（``time.time`` 的时钟
    # 粒度约 15.6ms，紧挨着的两次调用会撞出同一个值）⇒ 再叠一个进程内的自增序号。
    return f"{url}{sep}t={time.time_ns()}-{next(_CACHE_BUST_SEQ)}"


# ---------------------------------------------------------------- 目录与文件
def weights_dir() -> Path:
    """权重目录：``<仓库根>/static/weights``。

    仓库根取 ``utils`` 包的上一级（与 ``yolo_utils.model_path`` 原口径一致）；
    打包（onedir）下 ``static`` 数据文件落在 ``_internal/static``，该表达式同样
    成立——所以本函数是**权重目录的唯一来源**，别再各写一份。
    """
    return Path(__file__).resolve().parents[1].joinpath(*WEIGHTS_SUBPATH)


def _folder(directory=None) -> Path:
    """把可选的 ``directory`` 参数收敛成 ``Path``（省略时用 :func:`weights_dir`）。"""
    return Path(directory) if directory is not None else weights_dir()


def local_weights_path(directory=None) -> Path:
    """**兜底**权重路径（``static/weights/bookcontent.pt``，不等于"生效的文件"）。

    ⚠️ 要知道"当前真正生效的是哪一份"请用 :func:`resolve_weights`——本目录可能
    同时躺着 ``bookcontent-v103.pt`` / ``bookcontent-v105.pt``，生效的那份由
    sidecar 决定。
    """
    return _folder(directory) / LOCAL_WEIGHTS_NAME


def version_file(directory=None) -> Path:
    """本地版本 sidecar 路径（``static/weights/bookcontent.version.json``）。"""
    return _folder(directory) / VERSION_FILE_NAME


def parse_versioned_name(name) -> int | None:
    """从文件名解析版本号（``bookcontent-v105.pt`` → ``105``）；认不出返回 ``None``。"""
    match = _VERSIONED_RE.match(str(name or "").strip())
    return int(match.group(1)) if match else None


def versioned_weights(directory=None) -> list[tuple[int, Path]]:
    """目录里全部带版本号的权重，**版本号降序**（同版本按文件名）。

    只认 ``bookcontent-v<整数>.pt`` 这个形态（发布资产名）；兜底的
    ``bookcontent.pt`` **不在**结果里——它的版本按 0 计、由调用方单独判断。
    目录不存在 / 不可读时返回空列表（绝不抛：缺失是常态，不是错误）。
    """
    folder = _folder(directory)
    try:
        entries = list(folder.iterdir())
    except OSError:
        return []
    found: list[tuple[int, Path]] = []
    for entry in entries:
        version = parse_versioned_name(entry.name)
        if version is None:
            continue
        try:
            if not entry.is_file():
                continue
        except OSError:
            continue
        found.append((version, entry))
    found.sort(key=lambda item: (-item[0], item[1].name))
    return found


def _is_file(path: Path) -> bool:
    """``path`` 是不是一个存在的文件（吞掉权限等 OS 错误）。"""
    try:
        return path.is_file()
    except OSError:
        return False


def _recorded_name(info: dict) -> str:
    """sidecar 里记录的权重文件名（只取末段，防 ``../`` 之类的路径穿越）。"""
    return Path(str(info.get("name") or "").strip()).name


def resolve_weights(directory=None) -> Path | None:
    """按"只有一个生效"的口径解析出**当前要加载**的权重文件；一份都没有返回 ``None``。

    顺序见模块头（① sidecar 指的文件 → ② 兜底名 → ③ 本地最大版本 → ④ 兜底名 →
    ⑤ ``None``）。⚠️ 千万别把它简化成"有 bookcontent.pt 就用它"：下载下来的文件
    叫 ``bookcontent-v105.pt``，兜底名可能根本不存在；反过来 sidecar 指的版本被
    用户手动删了，也得能退到本地次新的那一份，而不是直接报"没有权重"。
    """
    folder = _folder(directory)
    base = folder / LOCAL_WEIGHTS_NAME
    recorded = _recorded_name(read_local_info(folder))
    if recorded:
        target = folder / recorded
        if _is_file(target):
            return target
        # ③ sidecar 在、文件不在 → 本地版本号最大的那份（不给用户"直接报错"）
        newest = versioned_weights(folder)
        if newest:
            return newest[0][1]
        # ④ 再退回兜底名
        return base if _is_file(base) else None
    # ② sidecar 不存在（或没写 name）→ 兜底名优先
    if _is_file(base):
        return base
    # sidecar 都没了、兜底名也没有：只要本地还有带版本的权重就先用它，
    # 避免"明明有 v105 却要重下 6MB"
    newest = versioned_weights(folder)
    if newest:
        return newest[0][1]
    return None


def _base_matches_record(path: Path, info: dict) -> bool:
    """兜底 ``bookcontent.pt`` 是否就是 sidecar 记录的那份权重（迁移判定）。

    旧版安装流程是"下完 ``bookcontent-vNNN.pt`` 再改名成 ``bookcontent.pt``"，
    所以升级上来的机器会出现"sidecar 写 v105、目录里却只有 ``bookcontent.pt``"
    ——名字对不上但**字节数一模一样**。不认这种情况就会白下一次 5MB、还多出一份
    内容完全相同的权重。

    判据只有一条：记录里的 ``size`` > 0 且与兜底文件大小相等（同日发布改名，
    大小必然相同；不同版本的权重几乎不可能字节数恰好相等）。
    """
    if path.name != LOCAL_WEIGHTS_NAME:
        return False
    recorded = _recorded_name(info)
    if not recorded or recorded.lower() == path.name.lower():
        return False
    expected = _as_int(info.get("size"))
    if expected <= 0:
        return False
    try:
        return path.stat().st_size == expected
    except OSError:
        return False


def effective_info(directory=None) -> dict:
    """当前生效权重的摘要：``{path, name, version, source}``。

    ``source`` 说明这份文件是怎么被选中的（排障/界面提示用）：

    ==========  ==================================================
    ``config``  sidecar 明确指定（正常情况：下载/切换之后）
    ``default`` 落到兜底的 ``bookcontent.pt``（安装包预置）
    ``latest``  sidecar 对不上文件，退到本地版本最大的那份
    ``legacy``  落到兜底的 ``bookcontent.pt``，但**大小与 sidecar 记录一致**
                （旧版安装流程把下载物改名成了它，等同 ``config`` 的版本）
    ``none``    一份都没有（``path`` 为 ``None``、版本 0）
    ==========  ==================================================

    版本号取法：sidecar 指的就是这份文件 ⇒ 用 sidecar 的 ``version``（下载时
    记下的权威值）；否则从文件名解析；兜底的 ``bookcontent.pt`` 解析不出 ⇒ 0。
    """
    folder = _folder(directory)
    info = read_local_info(folder)
    path = resolve_weights(folder)
    if path is None:
        return {"path": None, "name": "", "version": 0, "source": "none"}
    recorded = _recorded_name(info)
    same = bool(recorded) and recorded.lower() == path.name.lower()
    legacy = not same and _base_matches_record(path, info)
    version = int(info.get("version") or 0) if (same or legacy) else 0
    if version <= 0:
        version = parse_versioned_name(path.name) or 0
    if same:
        source = "config"
    elif legacy:
        source = "legacy"
    elif path.name == LOCAL_WEIGHTS_NAME:
        source = "default"
    else:
        source = "latest"
    return {"path": path, "name": path.name, "version": version, "source": source}


# ---------------------------------------------------------------- data.json
def parse_data_json(payload) -> dict | None:
    """抽出 ``payload['files']['bookcontent']`` 并规范化；不合法返回 ``None``。

    只做"取字段 + 类型收敛"，**不做比较**：版本判断留给 :func:`has_update`，
    于是纯规则能在自测里逐条钉死，网络返回什么垃圾都只是 ``None``。
    缺 ``version`` 或不是整数 ⇒ ``None``（宁可不说"有新版"也不谎报，与
    ``utils/version.py`` 同一口径）。
    """
    files = payload.get("files") if isinstance(payload, dict) else None
    entry = files.get(BOOKCONTENT_KEY) if isinstance(files, dict) else None
    if not isinstance(entry, dict):
        return None
    try:
        version = int(entry.get("version"))
    except (TypeError, ValueError):
        return None
    return {
        "name": str(entry.get("name") or ""),
        "version": version,
        "sha256": str(entry.get("sha256") or "").lower(),
        "size": _as_int(entry.get("size")),
        "date": str(entry.get("date") or ""),
    }


def pick_latest(entries) -> tuple[str, dict] | None:
    """从 ``[(线路前缀, data.json 内容), …]`` 里挑出**版本最高**的那份清单。

    返回 ``(prefix, info)``；没有一个可用清单时返回 ``None``。并列时保留**先出现**
    的那条（调用方按耗时排过序，于是并列取更快的线路）。

    ⚠️ 判据是"版本最高"而**不是**"哪条最快"：release 资产地址固定、会被缓存，
    缓存命中的旧清单一定更快——按速度选就会系统性地选到旧版本（用户 2026-10-16
    报的「线上是 101 却报已是最新」）。桌面端（测速排名）与本模块的在线兜底
    （顺序试探）都走这一个选择规则，别各写一份。
    """
    best: tuple[str, dict] | None = None
    for prefix, payload in entries:
        parsed = parse_data_json(payload)
        if parsed is None or not parsed["name"]:
            continue
        if best is None or parsed["version"] > best[1]["version"]:
            best = (prefix, parsed)
    return best


def _as_int(value) -> int:
    """宽松转 int（拿不到就 0）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------- 本地版本记录
def read_local_info(directory=None) -> dict:
    """本地版本 sidecar 的完整记录；缺失/损坏给一个版本 0 的空壳。"""
    try:
        data = json.loads(version_file(directory).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data["version"] = _as_int(data.get("version"))
            return data
    except (OSError, ValueError):
        pass
    return {"version": 0, "name": "", "sha256": "", "size": 0, "date": ""}


def read_local_version(directory=None) -> int:
    """本机**当前生效**权重的版本号；无权重/无法确定一律 ``0``。

    ⚠️ 不是"sidecar 里写的数字"：sidecar 指的 ``bookcontent-v105.pt`` 被用户删了
    之后，真正在跑的是本地次新的 v103（或兜底 ``bookcontent.pt``），对外仍报 105
    就会让"检查更新"误判成"已是最新"。所以取 :func:`effective_info` 的口径。
    """
    return int(effective_info(directory).get("version") or 0)


def record_local_version(info: dict, directory=None) -> None:
    """原子写 sidecar（临时文件 + ``os.replace``），记录**刚安装并生效**的版本。

    这是"切换生效文件"的唯一动作：下载完新权重只要改写这一份，程序下次解析
    ``resolve_weights`` 就会指向新文件（旧文件留在目录里，可回退）。

    ⚠️ 用 :func:`replace_with_retry`：Windows 上目标文件被别的句柄打开时
    ``os.replace`` 会直接 ``PermissionError``（YOLO 常驻服务可能正读着权重）。
    """
    target = version_file(directory)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _as_int(info.get("version")),
        "name": str(info.get("name") or ""),
        "sha256": str(info.get("sha256") or "").lower(),
        "size": _as_int(info.get("size")),
        "date": str(info.get("date") or ""),
    }
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    replace_with_retry(tmp, target)


def has_update(remote_version, local_version=None) -> bool:
    """远端版本是否比本机**已生效**版本新（整数比大小）。

    ``local_version`` 省略时读 :func:`read_local_version`。任一侧取不到合法
    整数都返回 ``False``——不可比时不说"有新版"。
    """
    if local_version is None:
        local_version = read_local_version()
    try:
        return int(remote_version) > int(local_version)
    except (TypeError, ValueError):
        return False


def sha256_of(path, chunk_size: int = 1 << 20) -> str:
    """流式算文件 SHA-256（校验下载到的权重，避免半截/被篡改的包落地）。"""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def human_size(size) -> str:
    """把字节数收成一句人读的大小（``6.0 MB``）；拿不到就空串。"""
    try:
        value = float(size)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return ""


# ---------------------------------------------------------------- 在线兜底
class WeightsDownloadError(RuntimeError):
    """联网取权重失败；``kind`` 是分类串（与 worker 的词表同口径）。"""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


def _fetch_manifest(prefix: str, timeout: float) -> dict | None:
    """单条线路取一次 ``data.json``；失败返回 ``None``（不抛）。"""
    request = urllib.request.Request(
        build_url(prefix, cache_bust(data_json_url())), headers=_HEADERS
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        payload = json.loads(raw.decode("utf-8", "replace"))
    except (urllib.error.HTTPError, urllib.error.URLError, OSError,
            ValueError, UnicodeError):
        return None
    return payload if isinstance(payload, dict) else None


def fetch_latest_info(timeout: float = MANIFEST_TIMEOUT) -> dict:
    """顺序试探四条线路取 ``data.json``，返回**版本最高**的那份清单::

        {"info": {name, version, sha256, size, date},
         "asset_name": name, "download_url": …, "mirror_prefix": …,
         "mirror_label": …}

    四条全败 / 清单里没有合法 bookcontent 记录 ⇒ :class:`WeightsDownloadError`
    （``kind`` = ``network`` / ``bad_json``）。

    ⚠️ 与桌面端 ``data_package_worker.fetch_data_json`` 的区别只是**transport**：
    那边并发测速挑线路（要给用户看"走的哪条多快"），这边顺序试探、够用就走
    （只在本机一份权重都没有时兜底）；"选版本最高的清单"两边共用
    :func:`pick_latest`。
    """
    entries: list[tuple[str, dict]] = []
    for prefix in MIRROR_PREFIXES:
        payload = _fetch_manifest(prefix, timeout)
        if payload is not None:
            entries.append((prefix, payload))
    picked = pick_latest(entries)
    if picked is None:
        raise WeightsDownloadError("bad_json" if entries else "network")
    prefix, info = picked
    return {
        "info": info,
        "asset_name": info["name"],
        "download_url": build_url(prefix, asset_url(info["name"])),
        "mirror_prefix": prefix,
        "mirror_label": mirror_label(prefix),
    }


def download_weights(info: dict, mirror_prefix: str = "", directory=None,
                     on_progress=None, timeout: float = WEIGHTS_TIMEOUT) -> Path:
    """把 release 里的权重下到权重目录，**保留发布名**，校验通过才写 sidecar。

    流程：下到 ``<name>.part`` → 改名成发布名（``bookcontent-v105.pt``）→ 校验
    sha256（不符就删掉、报错、**不切换**）→ 写 sidecar（= 启用这一份）。

    ⚠️ 传输期一律用 ``*.part``：半截权重绝不能以最终名出现（YOLO 服务/检测进程
    可能读到），这也是 :mod:`utils.download` 的硬约定。
    """
    folder = _folder(directory)
    folder.mkdir(parents=True, exist_ok=True)
    name = Path(str(info.get("name") or "")).name or LOCAL_WEIGHTS_NAME
    target = folder / name
    temp = target.with_name(target.name + ".part")

    url = build_url(mirror_prefix, cache_bust(asset_url(name)))
    actual, _written = stream_to_file(
        url, temp, on_progress=on_progress, timeout=timeout, headers=_HEADERS
    )
    replace_with_retry(temp, target)      # .part → 发布名文件

    expected = str(info.get("sha256") or "").lower()
    if expected and actual != expected:
        try:
            target.unlink()
        except OSError:
            pass
        raise WeightsDownloadError("sha256-mismatch")

    record_local_version({**info, "name": name}, folder)
    return target


def ensure_weights_online(directory=None, on_progress=None) -> Path:
    """确保本地有可用权重：有就返回它，**一份都没有**才联网下载最新。

    给 CLI / 常驻服务的加载路径当兜底（桌面端有自己的检查/下载流程）。失败抛
    :class:`WeightsDownloadError`（断网、清单坏、sha 不符），调用方应包成
    "本机缺权重且下载失败"的人话再抛给用户。
    """
    folder = _folder(directory)
    resolved = resolve_weights(folder)
    if resolved is not None:
        return resolved
    latest = fetch_latest_info()
    return download_weights(
        latest["info"], latest.get("mirror_prefix") or "", folder,
        on_progress=on_progress,
    )


__all__ = [
    "BOOKCONTENT_KEY",
    "DATA_JSON_NAME",
    "LOCAL_WEIGHTS_NAME",
    "MANIFEST_TIMEOUT",
    "MIRROR_PREFIXES",
    "RELEASE_DOWNLOAD_BASE",
    "VERSIONED_PREFIX",
    "VERSION_FILE_NAME",
    "WEIGHTS_SUFFIX",
    "WEIGHTS_TIMEOUT",
    "WeightsDownloadError",
    "asset_url",
    "build_url",
    "cache_bust",
    "data_json_url",
    "download_weights",
    "effective_info",
    "ensure_weights_online",
    "fetch_latest_info",
    "has_update",
    "human_size",
    "local_weights_path",
    "mirror_label",
    "parse_data_json",
    "parse_versioned_name",
    "pick_latest",
    "read_local_info",
    "read_local_version",
    "record_local_version",
    "resolve_weights",
    "sha256_of",
    "version_file",
    "versioned_weights",
    "weights_dir",
]
