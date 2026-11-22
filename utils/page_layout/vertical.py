# -*- coding: utf-8 -*-
"""竖排文字的分段与占位规则（fpdf 与 Qt 预览共用的唯一实现）。"""

from __future__ import annotations

from typing import List, Tuple

from utils.page_layout.constants import LATIN_ADVANCE_RATIO


def is_rotated_char(ch: str) -> bool:
    """该字符是否属于"整段旋转 90°"的拉丁/半角段。"""
    return 0x20 <= ord(ch) <= 0x7E


def rotated_run_offset_mm(ascent_mm: float, descent_mm: float) -> Tuple[float, float]:
    """竖排里"整段旋转 90°"的拉丁段：绘制点相对列基线的偏移 (dx, dy)。

    为什么必须偏移
    ------------
    宽字符（汉字）的落点是**基线**，字形以基线为底向上长（上方 ascent、
    下方 descent，两者之和 = 一个字高）；而旋转段的绘制点是**串首**，字形
    从那里沿列方向**向下**排，横向只占 ascent + descent。两者共用同一个
    落点 y 时：旋转段**之前**会空出约一个 ascent（与前一汉字之间出现近一
    个字高的缝），**之后**又会因没留出 descent 而压住下一个汉字。
    补偿：横向 +descent（旋转后 descender 本落在列左，右移后列才对得上）、
    纵向 -ascent（串首上提一个 ascent）。预览（QPainter）与成品（fpdf）都
    按这份偏移落笔，混排标题才是一列连续的竖排。
    """
    return float(descent_mm), -float(ascent_mm)


def vertical_runs(text: str) -> List[Tuple[str, bool]]:
    """竖排文本 → [(片段, 是否旋转 90°)]，相邻同类字符合并成一段。

    ``"呵呵Happiness"`` → ``[("呵呵", False), ("Happiness", True)]``：
    汉字各自占一格，英文整段旋转。绘制端（fpdf / QPainter）按这个分段渲染，
    所以两边的断段规则**只在这里定义一次**。
    """
    runs: List[Tuple[str, bool]] = []
    for ch in str(text or ""):
        rotated = is_rotated_char(ch)
        if runs and runs[-1][1] == rotated:
            runs[-1] = (runs[-1][0] + ch, rotated)
        else:
            runs.append((ch, rotated))
    return runs


def vertical_advance_mm(chunk: str, char_h_mm: float, rotated: bool) -> float:
    """一段竖排片段在竖直方向上占的高度（mm）——**估算值**。

    ⚠️ 只用于排版占位（`vertical_extent_mm` → 标题/页码落点）。绘制时的
    逐段步进请用 ``vertical_chunk_advance_mm`` 并传渲染端的实测宽度。
    """
    text = str(chunk or "")
    if not rotated:
        return len(text) * float(char_h_mm)
    return len(text) * LATIN_ADVANCE_RATIO * float(char_h_mm)


def vertical_chunk_advance_mm(
    chunk: str, char_h_mm: float, rotated: bool, latin_width_mm=None
) -> float:
    """绘制端一段竖排片段的实际步进（mm）——`draw_vertical_text`（fpdf）
    与 desktop 预览（QPainter）共用的同一份规则。

    - 宽字符段：仍是一字一格（``len × char_h_mm``）；
    - 旋转拉丁段：优先用渲染端**实测**的字符串宽度（fpdf 的
      ``get_string_width`` / Qt 的 ``QFontMetrics.horizontalAdvance``），
      拿不到实测值（``latin_width_mm=None``）才回落到 `LATIN_ADVANCE_RATIO`
      估算——回落只为兼容，正常路径两条渲染端都会传实测值。
    """
    text = str(chunk or "")
    if not rotated:
        return len(text) * float(char_h_mm)
    if latin_width_mm is None:
        return vertical_advance_mm(text, char_h_mm, True)
    return float(latin_width_mm)


def vertical_extent_mm(text: str, char_h_mm: float) -> float:
    """整串竖排文本的高度（mm）。"""
    return sum(
        vertical_advance_mm(chunk, char_h_mm, rotated)
        for chunk, rotated in vertical_runs(text)
    )


def text_block_width_mm(text: str, char_h_mm: float, vertical: bool) -> float:
    """一段文字的**横向宽度**（mm）——即它从落点 x 向右占多宽。

    用于「距右纸边」的口径：用户填的是**文字轮廓右边缘**到纸边的距离，
    所以落点得从右边往回退「右距 + 本宽度」，否则文字会比设定值多缩一个字宽
    （用户明确要求，见 `_text_anchor`）。

    * 竖排：整串是**一列**，宽度就是一个字宽（汉字方块格，等于字号）；
      拉丁段旋转 90° 后也只是一列的宽度，不额外加宽。
    * 横排：宽度 ≈ 字符数 × 字宽（比例字体的粗估，`LATIN_ADVANCE_RATIO`
      同一套近似口径；误差只体现在右页横向标题的 1~2mm 留白上）。
    """
    text = str(text or "")
    if not text:
        return 0.0
    cell = float(char_h_mm)
    if vertical:
        return cell
    return len(text) * cell
