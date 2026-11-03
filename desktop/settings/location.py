# -*- coding: utf-8 -*-
"""「存储位置」的**纯逻辑**：新目录合法性检查与整目录迁移。

设置页只负责弹窗与进度条，真正的规则放这里（可脱离 Qt 自测）：

- :func:`guard_destination` —— 目标目录不能是当前目录本身、它的子目录或
  它的上级目录（最后一条防"把 ``guji`` 里的东西散进上级目录"，也防
  "目标里还套着源目录"这种复制后自己复制自己的怪路径）；
- :func:`plan_migration` —— 先扫一遍要复制哪些文件（给进度条总数）；
- :func:`migrate_data` —— 按计划逐个 ``copy2``，可取消、可上报进度。

⚠️ 迁移是**复制**，不是剪切：旧目录原样保留。这样用户在设置里改错位置、
或中途取消，原来的数据都还在，随时能改回去。
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


class MigrationCanceled(Exception):
    """用户点了进度条上的「取消」。调用方应保留**旧存储位置**不变。"""


@dataclass(frozen=True)
class MigrationPlan:
    """一次迁移的清单：``files`` 每项是 ``(源文件, 目标文件, 字节数)``。"""

    source: Path
    destination: Path
    files: tuple[tuple[Path, Path, int], ...]

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(item[2] for item in self.files)


def resolve_data_root(selected) -> Path:
    """把「用户在文件对话框选的目录」换算成**真正的数据根**。

    数据根始终由 ``guji`` 文件夹包裹：选 ``D:\\备份`` ⇒ ``D:\\备份\\guji``；
    但如果选的目录本身就叫 ``guji``（用户直接选中了那个文件夹），就沿用它，
    不再套一层 ``guji\\guji``。
    """
    chosen = Path(selected).expanduser().resolve()
    if chosen.name.lower() == "guji":
        return chosen
    return chosen / "guji"


def _is_within(path: Path, parent: Path) -> bool:
    """``path`` 是否在 ``parent`` 里面（跨盘直接 False，不抛 ValueError）。"""
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def guard_destination(source, destination) -> str | None:
    """检查新存储位置能否使用；返回中文原因，能使用返回 ``None``。"""
    src = Path(source).expanduser().resolve()
    dst = Path(destination).expanduser().resolve()
    if dst == src:
        return "新目录与当前存储位置相同，无需更改。"
    if _is_within(dst, src):
        return "新目录不能选在当前存储位置里面（否则会把数据复制回自己）。"
    if _is_within(src, dst):
        return "新目录不能是当前存储位置的上级目录，请另选一个独立目录。"
    return None


def destination_has_content(destination) -> bool:
    """目标目录里是否已经有东西（有的话迁移会覆盖同名文件，要先提示）。"""
    try:
        with os.scandir(Path(destination)) as scan:
            return next(scan, None) is not None
    except OSError:
        return False


def plan_migration(source, destination) -> MigrationPlan:
    """扫出 ``source`` 下所有文件，映射到 ``destination`` 的对应相对路径。

    ⚠️ 只扫**文件**（空目录不复制也无所谓）；不跟随目录软链，
    避免把别处的整棵树拖进来。
    """
    src = Path(source).expanduser().resolve()
    dst = Path(destination).expanduser().resolve()
    entries: list[tuple[Path, Path, int]] = []
    if src.is_dir():
        for root, _dirs, names in os.walk(src, followlinks=False):
            root_path = Path(root)
            for name in names:
                file_path = root_path / name
                try:
                    size = file_path.stat().st_size
                except OSError:
                    size = 0
                entries.append((file_path, dst / file_path.relative_to(src), size))
    return MigrationPlan(src, dst, tuple(entries))


def migrate_data(
    plan: MigrationPlan,
    on_progress=None,
    should_cancel=None,
) -> tuple[int, int]:
    """执行迁移，返回 ``(已复制文件数, 已复制字节数)``。

    :param on_progress: ``(index, total, relative_name)`` 回调（从 1 开始）。
    :param should_cancel: 返回 True 时抛 :class:`MigrationCanceled`。
        取消**不会**回滚已复制的文件（复制操作无法原子撤销），调用方应提示
        "新目录里可能留下部分文件、但位置未切换"。

    ⚠️ 按文件粒度复制而不是整棵 ``copytree``：既能报进度，也能让用户在
    中途取消（一本书几百页缩略图时，整棵复制会长时间没有反馈）。
    """
    copied_files = 0
    copied_bytes = 0
    total = plan.total_files
    plan.destination.mkdir(parents=True, exist_ok=True)
    for index, (src_file, dst_file, size) in enumerate(plan.files, start=1):
        if should_cancel is not None and should_cancel():
            raise MigrationCanceled()
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        copied_files += 1
        copied_bytes += size
        if on_progress is not None:
            on_progress(index, total, str(src_file.relative_to(plan.source)))
    return copied_files, copied_bytes


def copy_file_if_missing(source, destination) -> bool:
    """把单个文件复制到目标（目标已存在则**不动**）；返回是否复制了。"""
    src = Path(source)
    dst = Path(destination)
    if not src.is_file() or dst.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


__all__ = [
    "MigrationCanceled",
    "MigrationPlan",
    "copy_file_if_missing",
    "destination_has_content",
    "guard_destination",
    "migrate_data",
    "plan_migration",
    "resolve_data_root",
]
