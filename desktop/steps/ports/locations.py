# -*- coding: utf-8 -*-
"""产物落点：每个端口在 ``tasks/<任务号>/`` 下的相对/绝对路径与节点后缀规则。"""

from __future__ import annotations

import re
from pathlib import Path

from desktop.steps.ports.constants import STAGE_LOCATIONS, TASK_INPUT_LOCATION


def location_of(stage: str, port: str) -> str | None:
    """运行阶段某端口的相对落点；没有登记返回 ``None``。"""
    return STAGE_LOCATIONS.get(stage, {}).get(port)


def sanitize_node_id(node_id: str) -> str:
    """把节点 id 收成**可安全拼进路径**的名字（只留字母数字与 ``._-``）。

    BPMN 节点 id 一般是 ``Node_7`` / ``Activity_1a2b`` 这种安全形状，但用户在
    bpmn.io 里能把它改成任意字符串——拼进路径前必须洗一道，否则 ``/`` 或 ``\\``
    会把落点引到别的目录（副本产物跑到任务目录之外）。
    """
    return re.sub(r"[^0-9A-Za-z._-]", "_", str(node_id))


def suffix_last_segment(name: str, suffix: str) -> str:
    """在路径**最后一段**插入后缀：目录名加在结尾、文件名加在扩展名前。

    - ``stages/extract`` → ``stages/extract~X``
    - ``boxes.json`` → ``boxes~X.json``
    - ``stages/print/print.pdf`` → ``stages/print/print~X.pdf``
    - 裸文件名 ``pages.json`` → ``pages~X.json``（没有 ``/`` 时 ``head`` 为空）

    这是"副本产物怎么命名"的**唯一一处**实现：任务目录里的每一种按节点隔离的
    文件（阶段产物目录 / ``boxes.json`` / ``pages.json`` / ``drafts/<阶段>.json``）
    都走它，规则不会各写一份。
    """
    head, sep, tail = str(name).rpartition("/")
    if "." in tail:
        stem, dot, ext = tail.rpartition(".")
        tail = f"{stem}~{suffix}{dot}{ext}"
    else:
        tail = f"{tail}~{suffix}"
    return f"{head}{sep}{tail}"


def scoped_name(name: str, node_id: str | None,
                primary_id: str | None) -> str:
    """按**节点作用域**给一个名字加后缀：主节点/无节点 ⇒ 原名，副本 ⇒ ``~<节点>``。

    ⚠️ **主节点零迁移**：同阶段恰好一个节点时（=所有现存任务与默认流程）
    名字与改造前**逐字节相同**，没有任何文件需要搬家。
    """
    if not node_id or not primary_id or node_id == primary_id:
        return str(name)
    return suffix_last_segment(name, sanitize_node_id(node_id))


def node_scope_from_output_dir(dir_name: str) -> str:
    """从**产物目录名**里取出节点作用域后缀（``extract~Node_3`` → ``~Node_3``）。

    场景：worker 子进程（如 ``stages/rembg_stage.py``）拿不到 store，也读不到
    流程图，只能从它写入的产物落点 ``out_dir.name`` 反推节点作用域，好把**缩略
    图缓存目录**（``thumbnails/<名>[~<节点>]``）算成与产物同一份作用域。

    无后缀（主节点/单节点流程）⇒ 返回 ``""``。⚠️ 节点 id 经
    :func:`sanitize_node_id` 洗过 ⇒ **不含 ``~``**，所以按最后一个 ``~`` 切分是
    安全的：``~`` 只会出现在"主名~节点"这一处。
    """
    _head, sep, tail = str(dir_name).rpartition("~")
    return f"{sep}{tail}" if sep else ""


def rembg_methods_path(out_dir) -> Path | None:
    """去底色「每页用了哪种算法」的侧车文件路径（worker / 实时预览共用）。

    落点与 ``rembg_offsets[~节点].json`` 同级，都在**任务根目录**：
    ``tasks/<任务号>/rembg_methods[~节点].json``，值是 ``{页名: 算法 key}``。

    只在 ``stages/`` 下的真实任务产物目录返回路径；模块页/自测的临时输出目录
    （父目录不叫 ``stages``）返回 ``None``——那里不该凭空长出一个任务侧车文件。
    """
    path = Path(out_dir)
    if path.parent.name != "stages":
        return None
    scope = node_scope_from_output_dir(path.name)
    return path.parents[1] / f"rembg_methods{scope}.json"


def copy_location(stage: str, port: str, node_id: str) -> str | None:
    """**副本节点**（同阶段第二个及之后的节点）的相对落点；没登记返回 ``None``。

    规则：在主落点的**最后一段**插入 ``~<node_id>``——目录名结尾加后缀、文件名
    在扩展名前加后缀：

    - ``stages/extract`` → ``stages/extract~Node_3``
    - ``boxes.json`` → ``boxes~Node_3.json``
    - ``stages/print/print.pdf`` → ``stages/print/print~Node_3.pdf``

    ⚠️ **主节点沿用旧落点**（:func:`node_location`），所以"同阶段恰好一个节点"
    的现存任务与默认流程**零迁移**——只有第二个及之后的节点才落到副本落点。
    """
    base = location_of(stage, port)
    if base is None:
        return None
    return suffix_last_segment(base, sanitize_node_id(node_id))


def node_location(stage: str, port: str, node_id: str | None = None,
                  primary_id: str | None = None) -> str | None:
    """**某节点实例**某端口的相对落点。

    ``node_id`` 空、或等于该阶段的 ``primary_id``（主节点）⇒ 旧落点（零迁移）；
    否则 ⇒ 副本落点（:func:`copy_location`）。没登记该端口返回 ``None``。
    """
    if node_id is None or primary_id is None or node_id == primary_id:
        return location_of(stage, port)
    return copy_location(stage, port, node_id)


def artifact_path(task_dir: Path | str, stage: str, port: str,
                  node_id: str | None = None,
                  primary_id: str | None = None) -> Path | None:
    """产物在任务目录下的**绝对路径**；该阶段没登记这个端口则 ``None``。

    ``task_dir`` 传 ``tasks/<任务号>/``（不是数据根）。

    ``node_id`` / ``primary_id`` 给定时按 :func:`node_location` 支持**多节点**
    （同阶段副本落到带 ``~<node_id>`` 后缀的副本落点）；不给则恒取旧落点
    （单节点场景与改造前逐字节一致）。
    """
    location = node_location(stage, port, node_id, primary_id)
    if location is None:
        return None
    return Path(task_dir) / location


def task_input_dir(task_dir: Path | str) -> Path:
    """入口图片目录的绝对路径（``tasks/<任务号>/stages/input/``）。

    ⚠️ **目录不需要事先存在**：它是"用户往里放图"的地方，任务刚建出来时
    本来就是空的。判"有没有图"要看里面有没有图片文件，别只看目录在不在。
    """
    return Path(task_dir) / TASK_INPUT_LOCATION
