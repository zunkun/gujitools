# -*- coding: utf-8 -*-
"""去底色：**每种算法上次手调过的窗口/灵敏度**的记忆（跨会话）。

用户 2026-11-24 口径：切算法要跟着切最优值，但**自己改过的值要记下来**——切走
再切回来应该还是自己那组，而不是又跳回推荐值。

落点：数据根 ``ui.json`` 里的一节 ``rembg_algorithm_params``::

    {"last_task": "0012",
     "rembg_algorithm_params": {"niblack": {"window": 45, "k": 0.35}}}

为什么放 ``ui.json``：它已经是「跨任务的界面小状态」的落点（见
``desktop/store/ui_state.py`` 的模块说明：任务级在 ``tasks/<id>/ui.json``，
跨任务的在数据根 ``ui.json``）。再开一个文件只会让界面状态散成两处。

为什么不走 store：面板没有 store —— ``StagePanel`` 的契约只有
``get_args / apply_args / reset_to_default``（见 ``AGENTS.md``「公共组件只认
输入目录 + 输出目录」）。这里只用「读—改—写 JSON」+ 数据根，不碰任何任务数据。

⚠️ 写盘是「读—改—写」，**只改自己那一节**：``last_task`` 等其它键必须原样保留。
⚠️ 所有函数**失败都不抛**（记忆丢了只是回到推荐值，绝不能让界面操作失败）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

#: ``ui.json`` 里存「每种算法的手调值」的键名。
SECTION_KEY = "rembg_algorithm_params"

#: 与面板控件范围一致（窗口 3~201，灵敏度 0~1）；读盘时越界一律丢弃。
WINDOW_MIN = 3
WINDOW_MAX = 201
K_MIN = 0.0
K_MAX = 1.0

__all__ = [
    "SECTION_KEY",
    "clear_all",
    "load",
    "remember",
    "ui_path",
]


def ui_path() -> Path:
    """记忆的落点：数据根下的 ``ui.json``。

    ⚠️ 每次调用都重新取数据根（用户可以在设置页改目录），不做缓存；自测用它
    把文件指到临时目录（patch 这个函数即可，**不要**调 ``set_guji_data_dir``，
    那会改用户的位置指针）。
    """
    from desktop.utils.files import guji_data_dir

    return guji_data_dir() / "ui.json"


def _read_all() -> dict:
    """整份 ``ui.json``（读不到/写坏都当空字典）。"""
    path = ui_path()
    try:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_all(data: dict) -> bool:
    """整份写回（原子性由「先算完整字典再一次写」保证；失败返回 False）。"""
    try:
        path = ui_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        return False
    return True


def _clean_entry(value) -> Optional[dict]:
    """一条记忆的清洗：非法（缺键/越界）返回 ``None``。"""
    if not isinstance(value, dict):
        return None
    try:
        window = int(value.get("window"))
        k = float(value.get("k"))
    except (TypeError, ValueError):
        return None
    if not (WINDOW_MIN <= window <= WINDOW_MAX):
        return None
    if not (K_MIN <= k <= K_MAX):
        return None
    return {"window": window, "k": round(k, 2)}


def _section(data: dict) -> dict[str, dict]:
    """取出并清洗记忆节：只留**已登记算法**的合法条目（改名的旧条目自然丢弃）。"""
    from utils.rembg_algorithms import ALGORITHM_KEYS

    raw = data.get(SECTION_KEY)
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, dict] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or key not in ALGORITHM_KEYS:
            continue
        entry = _clean_entry(value)
        if entry is not None:
            cleaned[key] = entry
    return cleaned


def load() -> dict[str, dict]:
    """读回记忆：``{算法 key: {"window": int, "k": float}}``（失败返回空字典）。"""
    return _section(_read_all())


def remember(algorithm: str, params: Optional[dict]) -> bool:
    """记下某算法的手调值；``params=None`` ⇒ 抹掉该条目（回到"用推荐值"）。

    返回是否写盘成功。值非法（窗口/灵敏度越界）或算法未登记时按 ``None``
    处理，免得把脏值记成"用户的最优"。
    """
    key = str(algorithm or "")
    entry = _clean_entry(params) if params is not None else None

    data = _read_all()
    section = _section(data)
    if entry is None:
        if key not in section:
            return True
        section.pop(key, None)
    else:
        if not key:
            return False
        if section.get(key) == entry:
            return True
        section[key] = entry
    if section:
        data[SECTION_KEY] = section
    else:
        data.pop(SECTION_KEY, None)
    return _write_all(data)


def clear_all() -> bool:
    """清空全部记忆（设置页/自测用）；不碰 ``ui.json`` 的其它键。"""
    data = _read_all()
    if SECTION_KEY not in data:
        return True
    data.pop(SECTION_KEY, None)
    return _write_all(data)
