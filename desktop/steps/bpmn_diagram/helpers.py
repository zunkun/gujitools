# -*- coding: utf-8 -*-
"""纯函数助手：XML 标签、节点名 → 阶段、注释尺寸、默认尺寸。"""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from desktop.steps import ports
from desktop.steps.bpmn_diagram.constants import (
    DEFAULT_SIZE,
    FALLBACK_SIZE,
    GUJI_NS,
    NOTE_CHAR_W,
    NOTE_CHROME_W,
    NOTE_LINE_H,
    NOTE_MAX_W,
    NOTE_MIN_H,
    NOTE_MIN_W,
    STAGE_ALIASES,
)


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _is_note_id(candidate: str, notes) -> bool:
    """这个 id 是不是某条注释（``association`` 两端要判哪头是注释）。"""
    return any(note.id == candidate for note in notes)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_node_seq(process: ET.Element, nodes: list) -> int:
    """读节点号水位：``guji:node_seq`` 属性优先，缺则从 ``Node_<n>`` id 反推。

    ⚠️ 老图（默认模板 ``task_default.bpmn`` / bpmn.io 画的图）没有该属性，节点
    id 也不是 ``Node_<n>`` 形状 ⇒ 水位为 0，新加的节点从 ``Node_1`` 起——与
    改造前行为一致（见 :attr:`FlowDiagram.node_seq`）。
    """
    raw = process.get(_q(GUJI_NS, "node_seq"))
    seq = 0
    if raw:
        try:
            seq = max(0, int(raw))
        except (TypeError, ValueError):
            seq = 0
    for item in nodes:
        match = re.match(r"Node_(\d+)$", item.id)
        if match:
            seq = max(seq, int(match.group(1)))
    return seq


def stage_of_name(name: str, guji_stage: str | None = None) -> str | None:
    """节点名（或扩展属性）→ 运行阶段 key；认不出返回 ``None``。

    ⚠️ **认不出不报错**：用户可能在图上画了本工具没有的节点（备注、其他
    系统步骤）。那些节点该照常显示，只是不参与运行——报错会让整张图打不开。
    """
    if guji_stage and guji_stage in ports.STAGE_STEPS:
        return guji_stage
    compact = "".join((name or "").split()).lower()
    if not compact:
        return None
    if compact in STAGE_ALIASES:
        return STAGE_ALIASES[compact]
    # 再退一步：用阶段的中文名（走 ports 单一来源）比一遍
    for stage in ports.STAGE_STEPS:
        label = "".join(ports.stage_label(stage).split()).lower()
        if label == compact:
            return stage
    return None


def _overlaps(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    """两个 ``(x, y, w, h)`` 框是否相交（注释避让用；贴边不算交叠）。"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _note_size(
    text: str,
    old: tuple[float, float, float, float] | None,
) -> tuple[float, float]:
    """注释框该多大：按**正文长度**算，宁可一行放下也不折行。

    ⚠️ 别沿用文件里的旧宽高：那些是bpmn.io 里手画的，102px 宽装不下
    「检测古籍文本框」七个字（渲染时按框宽自动换行，注释被折成两行、
    高度对不齐，一眼看去像"乱"）。宽高只作**下限**——用户手动拉大过就尊重。
    """
    need_w = min(
        NOTE_MAX_W, max(NOTE_MIN_W, len(text or "") * NOTE_CHAR_W + NOTE_CHROME_W)
    )
    lines = max(
        1,
        int((len(text or "") * NOTE_CHAR_W - (need_w - NOTE_CHROME_W)) // NOTE_LINE_H)
        + 1,
    )
    need_h = max(NOTE_MIN_H, lines * NOTE_LINE_H + 12.0)
    if old is None:
        return need_w, need_h
    return max(need_w, old[2]), max(need_h, old[3])


def default_size(kind: str) -> tuple[float, float]:
    """某类元素的默认宽高（文件缺 DI 段时用）。"""
    return DEFAULT_SIZE.get(kind, FALLBACK_SIZE)
