# -*- coding: utf-8 -*-
"""检测结果复用：一条「这份坐标还算不算数」的判据 + 按它分拣待检测页。

## 为什么

1000+ 页的书，第二次点「检测文本框」时绝大多数页的框和上次一模一样——只要
源文件没换、检测参数（``area``）没变，重跑一遍纯属白花几十秒推理。所以把
"这份结果还对得上吗"写进 `boxes.json` 条目本身（``src`` 文件戳 + ``det`` 检测
指纹），下次直接读回来复用。

## 判据（两个字段，都写在条目里）

- ``src``：``[字节数, mtime_ns]``——**这一页的源文件**有没有被换过；
- ``det``：检测侧的身份指纹 = ``config.VERSION | DET_VERSION | area``。

两者同时匹配才算可复用；任何一项变了就重跑。⚠️ **无框页也留痕**（写空 ``boxes``
但带指纹）：不记的话"检测过、但没检出框"的页每次都重跑。

⚠️ **``det`` 不读权重文件**：``utils.model_path()`` 会把 cv2/ultralytics 拉进
GUI 主进程（违反 AGENTS.md「GUI 主进程禁重依赖」）。代价是开发期"换了权重但没
升 ``config.VERSION``"不会让旧结果失效——升版本即失效，记为已知限制。

⚠️ 本模块只放**纯逻辑**：不 import Qt、不 import 任何重依赖，主进程可直连，
也可脱离页面单测。

## 归属

判据与分拣只有这一份，taskdetail（写进任务目录的 ``boxes.json``）与 singletask
（写进 ``singletask/<子任务>/boxes_cache/<源键>.json``）共用——两者只是**落点**
不同，字段与判据完全一致。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, TypeGuard

from config import VERSION

#: 复用格式版本。判据口径（字段含义、事件负载形状）改动时 +1——让所有旧结果
#: 立即失效、下次重跑重写，而不是拿两套口径的数据互相污染。
DET_VERSION = "v1"

#: 结果文件里除 boxes/origin/updated_at 之外，本模块关心的两个字段名。
FIELD_SRC = "src"
FIELD_DET = "det"


def det_fingerprint(area: int) -> str:
    """一次检测的**廉价**身份指纹：程序版本 + 复用格式版本 + ``area``。

    ``area`` 是检测参数里**唯一**会改变结果的那一个（整页模式压根不走检测），
    所以指纹只需要它。见模块 docstring 里"不读权重"的取舍。
    """
    raw = f"{VERSION}|{DET_VERSION}|area={int(area)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def file_stamp(path: Path) -> list | None:
    """文件的 ``[字节数, mtime_ns]``；读不到（不存在 / 无权限）给 ``None``。"""
    try:
        stat = path.stat()
    except OSError:
        return None
    return [int(stat.st_size), int(stat.st_mtime_ns)]


def entry_usable(entry: object, path: Path, det: str) -> TypeGuard[dict]:
    """该条目能否复用：``det`` 指纹一致**且** ``src`` 与当前文件戳一致。

    ⚠️ **不要求条目里有框**：空框页（检测过但没检出内容框）同样可复用——它的
    价值正是"别再为它重跑一次推理"。
    """
    if not isinstance(entry, dict):
        return False
    if entry.get(FIELD_DET) != det:
        return False
    return entry.get(FIELD_SRC) == file_stamp(path)


def payload_of(entry: dict) -> dict:
    """把条目的**槽位**表示还原成 ``page_boxes`` 事件的负载形状。

    槽位约定见 ``utils.box_geometry``（半幅恒 2 槽、整幅 1 槽）：
    - 1 槽 → 整幅（``full``）；
    - 2 槽 → 半幅（``left`` / ``right``，缺失侧为 ``None``）；
    - 0 槽 → 无框。
    """
    slots = list(entry.get("boxes") or [])
    left = right = full = None
    if len(slots) == 1:
        full = slots[0]
    elif len(slots) >= 2:
        left = slots[0]
        right = slots[1]
    return {"left": left, "right": right, "full": full}


def split(files: Iterable[Path], doc: dict, det: str
          ) -> tuple[dict[str, dict], list[Path]]:
    """把 ``files`` 分成（**可复用**的 ``{stem: 事件负载}``, **待检测**的文件表）。

    ``doc`` 是结果文件的原始条目表（``{stem: entry}``，见
    ``desktop.store.annotations.AnnotationMixin.boxes_raw_at``）。只有 ``src``
    与 ``det`` 双匹配的页才复用；负载形状与 ``page_boxes`` 事件一致
    （``image`` / ``left`` / ``right`` / ``full``），调用方原样补发即可。

    ⚠️ 键用 ``stem``（不是路径字符串）：结果文件与两边的检测流程都按 stem 索引
    （见 ``utils.box_geometry.page_box_slots_from_event``）。
    """
    reuse: dict[str, dict] = {}
    todo: list[Path] = []
    for path in files:
        stem = Path(path).stem
        entry = doc.get(stem)
        if entry_usable(entry, Path(path), det):
            payload = payload_of(entry)
            payload["image"] = stem
            payload["reused"] = True
            reuse[stem] = payload
        else:
            todo.append(Path(path))
    return reuse, todo


def source_key(source) -> str:
    """独立任务结果缓存的文件名：源的可读前缀 + 归一化路径的短哈希。

    ⚠️ 哈希用 ``resolve()`` 后的绝对路径：同一个目录"相对路径打开 vs 绝对路径
    打开"必须落到同一个键，否则会各存一份、互相看不见。前缀（源名）纯粹为了
    让人一眼看出"这是哪一批图的结果"。

    ⚠️ 只是**文件名**，不建目录（由调用方决定往哪个缓存根里放，见
    ``desktop.utils.files.singletask_dir``）。
    """
    path = Path(source)
    try:
        resolved = str(path.resolve())
    except OSError:  # 极端情况（路径过长/权限）下退化成原样
        resolved = str(path)
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:12]
    name = path.stem if path.is_file() else path.name
    return f"{_safe_name(name)}-{digest}"


def _safe_name(name: str) -> str:
    """把源名洗成能当文件名的一串（去掉路径分隔符与控制字符）。"""
    cleaned = "".join(
        "-" if ch in '\\/:*?"<>|' else ch for ch in str(name)
    )
    cleaned = "".join(ch for ch in cleaned if ord(ch) >= 32).strip(" .")
    return cleaned or "source"
