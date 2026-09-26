# -*- coding: utf-8 -*-
"""生成 PDF 的绘制辅助：字体注册、竖排文字、左右页判定。

从 `utils/pdf_utils.py` 拆出（见 docs/dev/refactor-modularity.md §3.B）；
PDF → 图片的部分在 `utils/pdf_extract.py`。

⚠️ 竖排的**分段规则**不在本模块，来自 `utils.page_layout.vertical_runs` ——
`functions/print.py`（fpdf 出 PDF）与 desktop 第四步「打印效果预览」
（QPainter）共用同一份，改分段只改那里。
"""

import os

from utils.fonts import pick_font
from utils.units import POINTS_PER_MM


def _used_names(pdf) -> set:
    """该 PDF 实例上已用过的字体注册名（挂在实例上，跨多条链共享）。"""
    used = getattr(pdf, "_guji_font_used", None)
    if used is None:
        used = set()
        pdf._guji_font_used = used
    return used


def _registered_paths(pdf) -> dict:
    """该 PDF 实例上「字体文件路径 → 注册名」的映射（挂在实例上，跨链共享）。

    ⚠️ 只按**注册名**去重不够（2026-09-26 审计）：标题链与页码链各调一次
    `build_font_chain`，两条链都会用到同一份主字体（如 simfang.ttf）。第二条链
    发现 "simfang" 这名字被占了，就换个名（`simfang_2`）**再注册一遍** ——
    PDF 里于是白多嵌一份字体子集，与"只注册用到的字体"的约定相悖。
    按**路径**去重才是本意。
    """
    mapping = getattr(pdf, "_guji_font_by_path", None)
    if mapping is None:
        mapping = {}
        pdf._guji_font_by_path = mapping
    return mapping


def _register_one(pdf, entry, used: set) -> str | None:
    """把单个字体注册进 pdf，返回注册名；失败返回 None。

    注册名取文件主名；重名时加序号——不同目录下可以有同名文件（比如
    `Fonts/simfang.ttf` 与用户自带的 `simfang.ttf`），撞名会让后一个
    把前一个悄悄顶掉。
    """
    base = os.path.splitext(os.path.basename(entry.path))[0] or "cjk"
    name = base
    index = 1
    while name in used:
        index += 1
        name = f"{base}_{index}"
    try:
        pdf.add_font(name, "", entry.path)
    except Exception:
        # 字体文件损坏 / fpdf 不支持的格式（个别 .ttc）：跳过即可，
        # 链条上还有别的字体
        return None
    used.add(name)
    return name


class FontChain:
    """一组已注册到某个 FPDF 实例的字体，可按字符挑名字。

    为什么需要它
    ------------
    古籍标题常有异体字 / 生僻字，而**没有任何单一字体**能覆盖它们：仿宋
    缺扩展 B 的字，Windows 自带的宋体-ExtB 有那些字却没有常用字。所以
    ``name_for(ch)`` 按优先级链挑第一个"有这个字"的字体——常用字仍是仿宋，
    只有仿宋真没有的那个字才落到补字字体上。

    ⚠️ 只注册**实际会用到**的字体（构造时传入全部待排文字来算）：
    把整条链二十来个字体全注册进去，每页 PDF 都要多嵌几个字体子集，
    体积与生成时间都白涨。
    """

    def __init__(self, entries, names: dict, primary: str):
        self._entries = list(entries)
        self._names = dict(names)
        self.primary = primary

    @property
    def entries(self) -> list:
        """参与本链条的字体条目（按优先级）。"""
        return list(self._entries)

    def name_for(self, char: str) -> str:
        """这个字符该用哪个已注册字体名（找不到时回落主字体）。"""
        entry = pick_font(self._entries, char)
        if entry is None:
            return self.primary
        return self._names.get(entry.path, self.primary)


def build_font_chain(pdf, texts=(), preferred=None) -> FontChain:
    """按优先级注册字体，返回可按字符取名的 `FontChain`。

    - ``preferred``：用户指定的字体（显示名 / 路径 / 文件名）；本机没有时
      忽略，链条仍从"仿宋优先"开始。
    - ``texts``：本次要排印的全部文字（标题、各章节标题…）。据此只注册
      真正需要的字体。

    一个都注册不上时链条为空、主字体为 `"Helvetica"`（fpdf 内置字体，不含
    中文字形），由调用方决定是否告警，这里不抛异常。
    """
    from utils.fonts import pick_font, resolve_chain

    chain = resolve_chain(preferred)
    needed: list = []
    seen: set[str] = set()
    for entry in chain:
        if entry.path in seen:
            continue
        seen.add(entry.path)
        # 主字体与补字字体都先记下：主字体必注册；补字字体按需注册
        needed.append(entry)

    # 按需：先把每个字符该用哪个字体算出来，再只注册被用到的
    primary_entry = chain[0] if chain else None
    used_paths: list = []
    if primary_entry is not None:
        used_paths.append(primary_entry)
    for text in texts or ():
        for char in str(text):
            entry = pick_font(chain, char)
            if entry is not None and entry.path not in {e.path for e in used_paths}:
                used_paths.append(entry)

    names: dict = {}
    # ⚠️ 已用注册名挂在 pdf 实例上：标题与页码各建一条链，两条链可能都要
    # 注册 simfang——各自持有一个 set 的话，第二条链会重新注册同名字体，
    # 把第一条的映射悄悄顶掉。
    used = _used_names(pdf)
    by_path = _registered_paths(pdf)
    registered: list = []
    for entry in used_paths:
        existing = by_path.get(entry.path)
        if existing is not None:
            # 同一个字体文件已经注册过（另一条链注册的）→ 直接复用它的注册名，
            # 不再 add_font 第二遍（见 _registered_paths 的说明）
            names[entry.path] = existing
            registered.append(entry)
            continue
        name = _register_one(pdf, entry, used)
        if name:
            by_path[entry.path] = name
            names[entry.path] = name
            registered.append(entry)
    if not names:
        return FontChain([], {}, "Helvetica")
    primary_name = names.get(primary_entry.path) if primary_entry else None
    if not primary_name:
        # 主字体注册失败（文件损坏）→ 用第一个注册成功的顶上
        first = registered[0]
        primary_name = names[first.path]
    return FontChain(registered, names, primary_name)


def register_fonts(pdf, preferred=None, texts=()):
    """注册系统中文字体，返回第一个成功注册的字体名。

    候选来自 `utils.fonts`（跨平台候选表 + `GUJI_CJK_FONT` 环境变量）——
    **中文字体路径不许在本文件硬编码**：曾经这么做过，换到非 Windows 平台
    后探测全部落空，标题/页码静默退回 Helvetica（方块、丢字）。

    需要**逐字降级**（生僻字）时请改用 `build_font_chain`：本函数只返回主
    字体名，画不出来就是画不出来。
    """
    return build_font_chain(pdf, texts=texts, preferred=preferred).primary


def draw_vertical_text(
    pdf, text, x, y_start, font_name, font_size, color, direction="down",
    chain=None,
):
    """在PDF上绘制竖排文字：宽字符一字一格，拉丁段整体旋转 90°。

    ⚠️ 分段规则来自 `utils.page_layout.vertical_runs`（与第四步预览**同一份**）：
    汉字等宽字符逐字下移，ASCII 可打印字符连成一段用 `pdf.rotation(90, …)`
    整体旋转——按竖排惯例，「呵呵Happiness」里的英文是一个转 90° 的竖条，
    而不是九个字母各占一格（那样既挤又认不出来）。

    ``chain``（`FontChain`）给出时**逐字挑选字体**：主字体缺这个字的字形
    就顺位落到下一个（生僻字因此落到宋体-ExtB 之类的补字字体上），
    而不是画出空白。不给则整段用 ``font_name``（历史行为）。
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
        # 一段里可能换字体（生僻字）：旋转段整段用同一个字体即可
        if chain is not None:
            pdf.set_font(chain.name_for(chunk[0]), "", font_size)
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
                if chain is not None:
                    pdf.set_font(chain.name_for(ch), "", font_size)
                pdf.text(x, y + index * step, ch)
            # ⚠️ 逐字换过字体后要把"当前字体"还原成主字体：advance 之后
            # 的下一段可能直接走 rotated 分支，那里读的是当前字体宽度。
            if chain is not None:
                pdf.set_font(font_name, "", font_size)
        y += -advance if direction == "down" else advance


def draw_horizontal_text(
    pdf, text, x, y, font_name, font_size, color, chain=None
):
    """在 PDF 上绘制横排文字；``chain`` 给出时逐字降级选字体。

    逐字降级必然要**逐字落笔**（每个字可能来自不同字体），宽度也必须用
    **该字所在字体**实测——用主字体量全串的宽度会在换字体处错位。
    """
    r, g, b = color
    if isinstance(r, float) and r <= 1:
        r, g, b = int(r * 255), int(g * 255), int(b * 255)
    pdf.set_font(font_name, "", font_size)
    pdf.set_text_color(r, g, b)
    if chain is None:
        pdf.text(x, y, text)
        return
    cursor = x
    for ch in str(text):
        pdf.set_font(chain.name_for(ch), "", font_size)
        pdf.text(cursor, y, ch)
        cursor += pdf.get_string_width(ch)
    pdf.set_font(font_name, "", font_size)


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
