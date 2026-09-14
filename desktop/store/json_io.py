# -*- coding: utf-8 -*-
"""JSON 持久化的原子读写工具。

任务状态全部存在 JSON 文件里，一旦写入过程中进程崩溃/断电，直接
``write_text`` 会留下半截文件；而读取侧把解析失败当作"没有数据"，
结果是全部任务或执行历史静默消失。因此统一改为：

1. 写入同目录的临时文件，``fsync`` 落盘后 ``os.replace`` 原子替换；
2. 读取失败时不返回空值，而是把损坏文件改名成 ``*.corrupt-<时间>``
   保留现场，再返回默认值——避免用户"数据被悄悄清空"。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

_SUFFIX = ".tmp"


def read_json(path: Path, default):
    """读取 JSON；文件不存在返回 default，损坏则备份后返回 default。"""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default
    except OSError:
        return default
    if not text.strip():
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        backup = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
        try:
            os.replace(path, backup)
            print(f"[store] JSON 损坏已备份：{backup.name}")
        except OSError:
            pass
        return default


def write_json(path: Path, data, indent: int = 1) -> None:
    """原子写 JSON（临时文件 + fsync + os.replace）。

    父目录不存在时直接放弃写入并返回 False 语义——任务目录被删除后
    仍在跑的子进程回调不应该把目录重新创建出来。
    """
    parent = path.parent
    if not parent.exists():
        raise FileNotFoundError(f"目录不存在：{parent}")
    tmp = path.with_name(path.name + _SUFFIX)
    payload = json.dumps(data, ensure_ascii=False, indent=indent)
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
