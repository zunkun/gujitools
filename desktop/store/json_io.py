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

#: 按节点隔离的数据文件旁的**归属标记**后缀（``boxes.json.owner``）。
#:
#: 用户 2026-10-23：文件名本身只有「主节点用原名、副本带 ``~<节点>``」这条
#: **隐式**规则——主节点是谁由 ``flow.bpmn`` 的节点声明顺序推导。删掉主节点后，
#: 接替的节点会被当成新主节点、接管旧主名的文件（旧节点的数据被误认为它的）。
#: 标记文件把归属写成显式的：读取时不一致就退回本节点自己的 ``~<节点>`` 文件。
OWNER_SUFFIX = ".owner"


def owner_path(path: Path) -> Path:
    """某数据文件的归属标记路径（``boxes.json`` → ``boxes.json.owner``）。"""
    return path.with_name(f"{path.name}{OWNER_SUFFIX}")


def read_owner(path: Path) -> str | None:
    """读归属节点 id；没有标记（旧任务 / 任务级文件）返回 ``None``。"""
    data = read_json(owner_path(path), None)
    if isinstance(data, dict):
        node = data.get("node_id")
        return str(node) if node else None
    return None


def write_owner(path: Path, node_id: str | None) -> None:
    """记录该文件属于哪个节点；``node_id`` 为空则不动（旧调用方零行为）。

    ⚠️ 标记是**元数据**，写失败不该拖垮数据本身（磁盘满/权限异常时数据已
    原子落盘，标记缺了只会退回旧的"信任主名"行为）。
    """
    if not node_id or not path.parent.exists():
        return
    try:
        write_json(owner_path(path), {"node_id": str(node_id)})
    except OSError:
        pass


def owns(path: Path, node_id: str | None) -> bool:
    """该文件是否属于 ``node_id``：无标记（旧数据）或标记一致 ⇒ True。"""
    if not node_id:
        return True
    owner = read_owner(path)
    return owner is None or owner == str(node_id)


def resolve_scoped_path(path: Path, node_id: str | None) -> Path:
    """主名文件已被**别的节点**占用时，退回本节点自己的 ``~<节点>`` 文件。

    ⚠️ 只对**主名**（文件名不含 ``~``）判断：副本文件天然属于它自己。
    ⚠️ 无标记 = 旧任务 ⇒ 原样使用（零迁移）；标记一致 ⇒ 原样使用。
    """
    if not node_id or "~" in path.name or owns(path, node_id):
        return path
    from desktop.steps import ports

    return path.with_name(
        ports.suffix_last_segment(path.name, ports.sanitize_node_id(str(node_id)))
    )


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
