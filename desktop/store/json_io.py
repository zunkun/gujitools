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
import threading
import time
from pathlib import Path

from utils.file_utils import replace_with_retry

_SUFFIX = ".tmp"


def _tmp_path(path: Path) -> Path:
    """临时文件名必须**带上 pid 与线程号**，不能是固定的 `x.json.tmp`。

    为什么（2026-09-26 审计）：单例守卫是**按构建目录**判定的，开发版与安装版
    会同时运行、共用 `~/Documents/guji` 数据区（`desktop/single_instance.py` 的
    注释明说了这一点）。固定名会让两个进程同时 `open(tmp,"w")`：A 写完 fsync
    准备 replace 时，B 正在往同一个 tmp 里写半截内容 → `os.replace` 把**半截
    JSON** 换成正式文件 → 下次 `read_json` 判为损坏、把 `tasks.json` 改名进
    `*.corrupt-*` 并返回默认值 → 用户看到"全部任务凭空消失"。
    带 pid/线程号后，各写各的临时文件，`os.replace` 仍是原子替换（后写者胜），
    不会出现半截内容被上线。
    """
    tid = threading.get_ident()
    return path.with_name(f"{path.name}.{os.getpid()}-{tid}{_SUFFIX}")


def read_json(path: Path, default):
    """读取 JSON；文件不存在返回 default，损坏则备份后返回 default。

    ⚠️ 「损坏」有两种，必须一起兜住：**语法坏了**（`JSONDecodeError`）与
    **不是合法 UTF-8**（`UnicodeDecodeError`，外部编辑器/磁盘损坏/异构工具写坏
    都能造成）。后者是 `ValueError` 的子类、**不是** `OSError`，早期实现只 try
    `OSError` + `JSONDecodeError`，于是它会一路穿透到调用它的 Qt 槽里——在事件
    处理中抛异常比"备份后返回默认值"糟糕得多。
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return default
    except OSError:
        return default
    try:
        text = raw.decode("utf-8")
        if not text.strip():
            return default
        return json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
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
    tmp = _tmp_path(path)
    payload = json.dumps(data, ensure_ascii=False, indent=indent)
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    # Windows：目标正被别的句柄打开时 os.replace 会抛 PermissionError（读者也算），
    # 必须短暂重试——见 utils/file_utils.replace_with_retry。
    replace_with_retry(tmp, path)
