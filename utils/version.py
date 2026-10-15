# -*- coding: utf-8 -*-
"""版本号解析与比较（**纯规则**，无 Qt / 无重依赖）。

唯一用途是「检查更新」：把 GitHub Release 的 ``tag_name`` 与本机 ``config.VERSION``
比大小。放在 ``utils`` 而不是桌面侧，是因为它是纯字符串/数字规则——GUI 主进程
（``desktop/ui/menu.py``）要用，CLI 将来要报版本也随时能用，且**不能**把任何
重依赖（cv2/torch）带进主进程。

四条约定（改动前先读）
--------------------
1. **不抛异常**：输入来自网络（release tag 可能是 ``v2.0.4`` / ``2.0.4-rc1`` /
   ``release-2026`` 这类千奇百怪的串），解析失败一律退化成"不可比"，
   由 :func:`is_newer` 返回 ``False`` —— 宁可不说"有新版本"，也不谎报。
2. **数值比较，不是字典序**：``2.10.0 > 2.9.0``（字符串比会得出反的结果）。
3. **缺位补 0**：``2.0 == 2.0.0``，而 ``2.0.1 > 2.0``。
4. **预发布更旧**：``+build5`` 是构建元数据，**忽略**（不改变大小）；
   ``-rc1`` / ``-beta2`` 是预发布 ⇒ 同核时正式版更新。

::

    2.0.4      → (2, 0, 4)      非预发布
    v2.0.4     → (2, 0, 4)      非预发布（v/V 前缀剥掉）
    2.1.0-rc1  → (2, 1, 0)      预发布
    2.0.4+b57  → (2, 0, 4)      非预发布（构建元数据忽略）
    release    → ()             不可比
"""

from __future__ import annotations

import re

#: 版本**数字核**：``2`` / ``2.0`` / ``2.0.4`` / ``2026-10-15`` 这种"数字段用
#: ``.``/``_``/``-`` 相连"的最长前缀。⚠️ 段与段之间**必须跟数字**——所以
#: ``2.1.0-rc1`` 只吃到 ``2.1.0``（``-rc`` 不是数字段），``2.0.4+b57`` 只吃到
#: ``2.0.4``（``+`` 压根不在分隔符集合里）。
_CORE_RE = re.compile(r"\d+(?:[._-]\d+)*")

#: 拆段用的分隔符（与 ``_CORE_RE`` 同一族：点、下划线、连字符）。
_SEG_SPLIT_RE = re.compile(r"[._-]+")


def parse_version(text) -> tuple[int, ...]:
    """版本串 → 数字元组；解析不出数字时返回 ``()``。

    ``v2.0.4`` → ``(2, 0, 4)``；``2.1.0-rc1`` → ``(2, 1, 0)``；
    ``release`` → ``()``。只认**数字核**，前后缀（``v`` / ``rc1`` / ``+b57``）
    一概不参与大小比较。
    """
    if text is None:
        return ()
    raw = str(text).strip().lstrip("vV")
    if not raw:
        return ()
    match = _CORE_RE.search(raw)
    if match is None:
        return ()
    return tuple(int(part) for part in _SEG_SPLIT_RE.split(match.group(0)))


def is_prerelease(text) -> bool:
    """这个版本串是不是**预发布**（同核时比正式版旧）。

    ``+`` 之后是构建元数据（忽略，不影响）；数字核之后若出现**不以数字开头**
    的段（``rc1`` / ``beta2`` / ``alpha``）即为预发布；``2.0.4-1`` 那种纯数字
    附加段不算。``2.0.4`` / ``v2.0.4`` / ``2.0.4+b57`` 都不是预发布。
    """
    if text is None:
        return False
    raw = str(text).strip().lstrip("vV")
    core = raw.split("+", 1)[0]      # 构建元数据不改变"预发布与否"
    match = _CORE_RE.search(core)
    if match is None:
        return False
    for segment in _SEG_SPLIT_RE.split(core[match.end():]):
        if segment and not segment[0].isdigit():
            return True
    return False


def compare(left, right) -> int:
    """两版本串比较：左大 ``1``、右大 ``-1``、相等或不可比 ``0``。

    ⚠️ 不可比（任一侧 :func:`parse_version` 为空）也返回 ``0`` —— 与
    :func:`is_newer` 的"不可比就当没新版本"配套；需要区分"解析失败"的调用方
    请自己先查 :func:`parse_version` 的长度。
    """
    a, b = parse_version(left), parse_version(right)
    if not a or not b:
        return 0
    for index in range(max(len(a), len(b))):
        left_part = a[index] if index < len(a) else 0
        right_part = b[index] if index < len(b) else 0
        if left_part != right_part:
            return 1 if left_part > right_part else -1
    return 0


def is_newer(latest, current) -> bool:
    """``latest`` 是否比 ``current`` 新（＝本机该不该提示"有新版本"）。

    同核时只有"当前是预发布、最新不是"才算更新（``2.1.0-rc1`` → ``2.1.0``）。
    任一侧解析失败都返回 ``False``：不可比时不说"有新版本"。
    """
    result = compare(latest, current)
    if result > 0:
        return True
    if result == 0 and parse_version(latest) and parse_version(current):
        return is_prerelease(current) and not is_prerelease(latest)
    return False


__all__ = ["compare", "is_newer", "is_prerelease", "parse_version"]
