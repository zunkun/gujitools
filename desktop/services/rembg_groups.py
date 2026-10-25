# -*- coding: utf-8 -*-
"""去底色全局阈值的**跨图分组**：同页左右裁图合并计算、共享一个阈值。

用户 2026-10-25 口径：

> 去底色全局方法计算阈值是一页中左右文本框内部进行计算的，比如
> ``35-l.jpg, 35-r.jpg``；如果某一页有 ``xx-l, xx-r``，那么合在一起计算阈值，
> 并把阈值应用在 xx 拆出来的两张图片。

分组依据**不是文件名猜的**，而是「当前去底色节点在流程上游最近的 detect
节点」写出的 ``boxes.json`` 提交计划（``entry["plan"]["outputs"]``）：

- ``label``：产物名（``35-l`` / ``35-r`` / ``35``）；
- ``placeholder``：占位图标记——占位图**不参与**合并，自己单独计算阈值；
- ``role``：拼版身份（这里只用于区分半幅/整幅，不参与阈值计算）。

只有同页左右两张**都真实存在**（非占位）且用同一个全局算法时才共享阈值；
占位图、局部算法、算法不一致都回落逐图计算。

没有 ``boxes.json``（自定义流程没有 detect、独立模块页、CLI）时按**逐图**
处理，行为与改造前完全一致。本模块不依赖 Qt，worker 子进程与实时预览共用。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: 同页左右裁图的后缀（提交阶段生成，``<页>-l`` / ``<页>-r``）。
SIDE_SUFFIXES = ("-l", "-r")


@dataclass(frozen=True)
class GroupMember:
    """一张去底色输入图在分组里的身份。"""

    path: Path
    label: str
    placeholder: bool = False
    role: str | None = None
    page: str | None = None


def strip_side_suffix(label: str) -> str:
    """``35-l`` / ``35-r`` → ``35``；没有后缀（整幅/半幅无侧）原样返回。"""
    text = str(label)
    for suffix in SIDE_SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)]
    return text


def load_plan_labels(boxes_path: str | Path | None) -> dict[str, dict]:
    """读 ``boxes.json`` 的提交计划 → ``{产物名: {page, placeholder, role}}``。

    只认 ``entry["plan"]["outputs"]``（「提交本次任务」写入的结构）。旧任务
    没有 plan，返回空表，调用方自然回落到逐图处理。
    """
    if not boxes_path:
        return {}
    from desktop.store.json_io import read_json

    data = read_json(Path(boxes_path), {})
    if not isinstance(data, dict):
        return {}
    labels: dict[str, dict] = {}
    for page, entry in data.items():
        plan = entry.get("plan") if isinstance(entry, dict) else None
        if not isinstance(plan, dict):
            continue
        outputs = plan.get("outputs")
        if not isinstance(outputs, list):
            continue
        for output in outputs:
            if not isinstance(output, dict):
                continue
            label = str(output.get("label") or "").strip()
            if not label:
                continue
            labels[label] = {
                "page": str(page),
                "placeholder": bool(output.get("placeholder")),
                "role": output.get("role"),
            }
    return labels


def group_files(
    files,
    boxes_path: str | Path | None = None,
) -> list[list[GroupMember]]:
    """把输入图按「源页」分组；没有 ``boxes_path`` 时每张图各自一组。

    同一页的 ``35-l`` / ``35-r`` 落进同一组（键是计划里的**源页名**）；
    计划里查不到的图单独成组——**不按后缀硬配对**，避免把来历不明的图
    与占位规则混在一起。
    """
    paths = [Path(item) for item in files]
    if not boxes_path:
        return [[GroupMember(path=path, label=path.stem)] for path in paths]

    labels = load_plan_labels(boxes_path)
    groups: dict[str, list[GroupMember]] = {}
    order: list[str] = []
    for path in paths:
        label = path.stem
        info = labels.get(label)
        if info is None:
            key = f"file:{label}"
            member = GroupMember(path=path, label=label)
        else:
            page = str(info.get("page") or strip_side_suffix(label))
            key = f"page:{page}"
            member = GroupMember(
                path=path,
                label=label,
                placeholder=bool(info.get("placeholder")),
                role=info.get("role"),
                page=page,
            )
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(member)
    return [groups[key] for key in order]


def group_of(
    files,
    target: str | Path,
    boxes_path: str | Path | None = None,
) -> list[GroupMember]:
    """在 ``files`` 里找 ``target`` 所在的分组（实时预览用）。"""
    target_path = Path(target)
    for group in group_files(files, boxes_path):
        if any(member.path == target_path for member in group):
            return group
    return [GroupMember(path=target_path, label=target_path.stem)]


__all__ = [
    "GroupMember",
    "SIDE_SUFFIXES",
    "group_files",
    "group_of",
    "load_plan_labels",
    "strip_side_suffix",
]
