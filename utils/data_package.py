# -*- coding: utf-8 -*-
"""去底色数据包（``bookcontent.pt``）的版本规则与本地版本记录。

背景（用户 2026-10-16）
----------------------
YOLO 权重 ``bookcontent.pt`` 由**另一个仓库**（``zunkun/gujitrain``）的
``database`` release 分发。那个 release 里除了权重本体，还有一份 ``data.json``，
逐文件描述 ``name`` / ``version``（整数）/ ``sha256`` / ``size`` / ``date``：

    {
      "generated_at": "2026-10-16T09:22:21+08:00",
      "release": "database",
      "files": {
        "bookcontent": {"name": "bookcontent-v100.pt", "version": 100, ...},
        "gujiline":    {"name": "gujiline-v100.pt",    "version": 100, ...}
      }
    }

桌面端据此判断"本机权重是不是旧版"，有新版就提示并可一键下载替换（**不让用户
自己去 GitHub 下载**）。

为什么单列成模块（而不是塞进 ``yolo_utils``）
--------------------------------------------
1. 这里全是**纯规则**（JSON 解析 + 整数比大小 + 读一份 sidecar），没有 cv2 /
   torch；而桌面**主进程**要用它（``desktop/ui/menu.py`` 的检查/下载），主进程
   **不许** import 重依赖（见 AGENTS 分层守卫）。``yolo_utils`` 模块级 import
   numpy，把一个纯规则塞进去等于顺带把 numpy 拽进启动。
2. 反过来 ``yolo_utils.model_path()`` 复用本模块的 :func:`weights_dir`：
   权重目录**只此一处**定义，两边各写一份 ``static/weights`` 迟早漂移。

本地版本记在哪
--------------
本机 ``bookcontent.pt`` 是**安装包预置**的、文件名不带版本（用户口径：
"bookcontent-v100.pt 版本是 100 > bookcontent.pt"）。为便于后续比较，这里在
权重目录旁维护一份 sidecar ``bookcontent.version.json``，记录**最近一次已安装**
的版本（含 name/sha256/size）。sidecar 不存在 ⇒ 视为版本 ``0``，于是远端任何
带版本号的分发都算更新（正是用户要的效果）；下载成功后由下载侧
:func:`record_local_version` 写回。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

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

#: 本地权重文件名（安装包预置，**不带版本号**）。
LOCAL_WEIGHTS_NAME = "bookcontent.pt"

#: 本地版本 sidecar 文件名（放权重目录旁）。
VERSION_FILE_NAME = "bookcontent.version.json"

#: 权重所在子目录（相对仓库根）。与 ``yolo_utils`` 共用的唯一来源。
WEIGHTS_SUBPATH = ("static", "weights")


def data_json_url() -> str:
    """``data.json`` 的**直连**地址（镜像前缀由调用方 :func:`build_url` 拼）。"""
    return RELEASE_DOWNLOAD_BASE + DATA_JSON_NAME


def asset_url(name: str) -> str:
    """release 里某个资产的**直连**下载地址（镜像前缀由调用方拼）。"""
    return RELEASE_DOWNLOAD_BASE + str(name)


def weights_dir() -> Path:
    """权重目录：``<仓库根>/static/weights``。

    仓库根取 ``utils`` 包的上一级（与 ``yolo_utils.model_path`` 原口径一致）；
    打包（onedir）下 ``static`` 数据文件落在 ``_internal/static``，该表达式同样
    成立——所以本函数是**权重目录的唯一来源**，别再各写一份。
    """
    return Path(__file__).resolve().parents[1].joinpath(*WEIGHTS_SUBPATH)


def local_weights_path() -> Path:
    """本机权重文件路径（``static/weights/bookcontent.pt``）。"""
    return weights_dir() / LOCAL_WEIGHTS_NAME


def version_file() -> Path:
    """本地版本 sidecar 路径（``static/weights/bookcontent.version.json``）。"""
    return weights_dir() / VERSION_FILE_NAME


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


def _as_int(value) -> int:
    """宽松转 int（拿不到就 0）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def read_local_info() -> dict:
    """本地版本 sidecar 的完整记录；缺失/损坏给一个版本 0 的空壳。"""
    try:
        data = json.loads(version_file().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data["version"] = _as_int(data.get("version"))
            return data
    except (OSError, ValueError):
        pass
    return {"version": 0, "name": "", "sha256": "", "size": 0, "date": ""}


def read_local_version() -> int:
    """本机已安装权重的版本号；sidecar 缺失/损坏一律 ``0``。"""
    return int(read_local_info().get("version") or 0)


def record_local_version(info: dict) -> None:
    """原子写 sidecar（临时文件 + ``os.replace``），记录刚安装的版本。

    ⚠️ 用 :func:`replace_with_retry`：Windows 上目标文件被别的句柄打开时
    ``os.replace`` 会直接 ``PermissionError``（YOLO 常驻服务可能正读着权重）。
    """
    target = version_file()
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
    """远端版本是否比本机**已安装**版本新（整数比大小）。

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


__all__ = [
    "BOOKCONTENT_KEY",
    "DATA_JSON_NAME",
    "LOCAL_WEIGHTS_NAME",
    "RELEASE_DOWNLOAD_BASE",
    "VERSION_FILE_NAME",
    "asset_url",
    "data_json_url",
    "has_update",
    "human_size",
    "local_weights_path",
    "parse_data_json",
    "read_local_info",
    "read_local_version",
    "record_local_version",
    "sha256_of",
    "version_file",
    "weights_dir",
]
