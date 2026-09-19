# -*- coding: utf-8 -*-
"""生成 PDF 的绘制辅助：字体注册、竖排文字、左右页判定。

从 `utils/pdf_utils.py` 拆出（见 docs/dev/refactor-modularity.md §3.B）；
PDF → 图片的部分在 `utils/pdf_extract.py`。

⚠️ 竖排的**分段规则**不在本模块，来自 `utils.page_layout.vertical_runs` ——
`functions/print.py`（fpdf 出 PDF）与 desktop 第四步「打印效果预览」
（QPainter）共用同一份，改分段只改那里。
"""

import os

from utils.units import POINTS_PER_MM


def register_fonts(pdf):
    """尝试注册系统中文字体，返回第一个成功注册的字体名。"""
    font_paths = [
        r"C:\Windows\Fonts\fsgb2312.ttf",
        r"C:\Windows\Fonts\simfang.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
    ]
    for path in font_paths:
        if os.path.exists(path):
            font_name = os.path.splitext(os.path.basename(path))[0]
            try:
                pdf.add_font(font_name, "", path)
                return font_name
            except Exception:
                continue
    return "Helvetica"


def draw_vertical_text(
    pdf, text, x, y_start, font_name, font_size, color, direction="down"
):
    """在PDF上绘制竖排文字：宽字符一字一格，拉丁段整体旋转 90°。

    ⚠️ 分段规则来自 `utils.page_layout.vertical_runs`（与第四步预览**同一份**）：
    汉字等宽字符逐字下移，ASCII 可打印字符连成一段用 `pdf.rotation(90, …)`
    整体旋转——按竖排惯例，「呵呵Happiness」里的英文是一个转 90° 的竖条，
    而不是九个字母各占一格（那样既挤又认不出来）。
    """
    from utils.page_layout import (
        vertical_chunk_advance_mm, vertical_runs,
    )

    r, g, b = color
    if isinstance(r, float) and r <= 1:
        r, g, b = int(r * 255), int(g * 255), int(b * 255)
    pdf.set_font(font_name, "", font_size)
    pdf.set_text_color(r, g, b)
    char_height_mm = font_size / POINTS_PER_MM  # 点数转毫米
    y = y_start
    for chunk, rotated in vertical_runs(text):
        if rotated:
            # ⚠️ 旋转段占高必须用**当前字体实测**的串宽，不能用
            # LATIN_ADVANCE_RATIO 估算——数字/下划线长段（如
            # 「Harvard_drs_435580539_」22 字符）按 0.55/字符估算会比
            # 实际（≈0.5）多出约 1 个字高，旋转段与后续汉字之间出现
            # 一条空隙。get_string_width 返回的就是当前文档单位（mm）。
            latin_width_mm = pdf.get_string_width(chunk)
        else:
            latin_width_mm = None
        advance = vertical_chunk_advance_mm(
            chunk, char_height_mm, rotated, latin_width_mm
        )
        if rotated:
            # 以列位置为基线旋转 90°：文字自上而下排出、字头朝右（竖排惯例）。
            # ⚠️ fpdf 的 rotation 正角是**逆时针**，所以这里要写 -90；对应
            # Qt 侧是 `painter.rotate(+90)`（Qt 正角顺时针）。写 +90 的话
            # 单词会从下往上读（Happiness 变成 nippessH）。
            with pdf.rotation(-90, x, y):
                pdf.text(x, y, chunk)
        else:
            # 宽字符逐字落格。⚠️ direction 的历史语义要照旧：`down` 是 y 递减、
            # 其余（默认 `up`，print.py 走这条）是 y 递增 —— 名字与页面上的
            # 视觉方向相反，别顺手"修正"。
            step = -char_height_mm if direction == "down" else char_height_mm
            for index, ch in enumerate(chunk):
                pdf.text(x, y + index * step, ch)
        y += -advance if direction == "down" else advance


def get_page_side_from_name(name_without_ext):
    """根据文件名末尾 '-l' 或 '-r' 判断左右页。"""
    lower = name_without_ext.lower()
    if lower.endswith("-l"):
        return "left"
    if lower.endswith("-r"):
        return "right"
    return None


def get_page_side_by_start(image_files, current_index, start_page, default_side="left"):
    """根据起始页的左右属性推断当前页是左还是右。"""
    if not (1 <= start_page <= len(image_files)):
        start_side = default_side
    else:
        start_name = os.path.splitext(os.path.basename(image_files[start_page - 1]))[0]
        start_side = get_page_side_from_name(start_name) or default_side
    offset = current_index - start_page
    if offset % 2 == 0:
        return start_side == "left"
    return start_side == "right"
