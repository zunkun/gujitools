# -*- coding: utf-8 -*-
"""单页排版的几何数据结构：文字规格与整页计划。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from utils.page_layout.constants import TEXT_MARGIN_MM


@dataclass(frozen=True)
class PrintTextSpec:
    """一段要画到页面上的文字（标题或页码）。

    属性:
        text: 文本内容。
        x_mm: 落点横坐标（竖排为整列的 x）。
        y_start_mm: 起始纵坐标（竖排为**首字**的基线附近）。
        char_h_mm: 单字高度（竖排据此逐字下移）。
        vertical: 是否竖排。
        font_size_pt: 字号（pt，仅用于渲染端换算）。
        color: (r, g, b)。
        direction: 逐字排布方向，"up" 表示 y **递增**（自页顶向下
            排列），与 ``utils.pdf_draw.draw_vertical_text`` 同名参数一致。
        ⚠️ `vertical=True` 时文本按 `vertical_runs` 分段：宽字符（汉字等）
            各自占一格，ASCII（拉丁字母/数字/半角符号）连成一段**整体旋转
            90°**（`Happiness` 不会拆成九个字母格）。
        baseline_mm: 横排时的基线 y（竖排逐字用 y_start_mm，忽略本值）。
        font: 字体指定值（显示名 / 文件路径 / 文件名）；None = 自动
            （仿宋优先）。只用于**选字体**，不参与几何计算——渲染端据此
            挑字体，PDF 端还要按字形降级（见 `utils.pdf_draw.FontChain`）。
    """

    text: str
    x_mm: float
    y_start_mm: float
    char_h_mm: float
    vertical: bool
    font_size_pt: float
    color: Tuple[int, int, int]
    direction: str = "up"
    baseline_mm: Optional[float] = None
    font: Optional[str] = None


@dataclass(frozen=True)
class PrintPagePlan:
    """单页排版的完整几何。

    属性:
        page_w_mm / page_h_mm: 纸张尺寸（已按方向交换）。
        image: (x, y, w, h) 毫米，图片在页面上的落点与显示尺寸。
        title / page_number: 文字规格，未开启时为 None。
        side: 本页标题/页码所在侧（"left" / "right"）。
        skipped: 本页命中 skip_pages（生成 PDF 时整页不输出，预览留空）。
        text_reserve_mm: 图片左右两侧的固定留白（mm）——**恒为
            `TEXT_MARGIN_MM`**：「距页边」现在只决定文字画在哪儿，
            不再反过来收窄图片（见模块 docstring 的说明）。
    """

    page_w_mm: float
    page_h_mm: float
    image: Tuple[float, float, float, float]
    title: Optional[PrintTextSpec] = None
    page_number: Optional[PrintTextSpec] = None
    side: str = "left"
    skipped: bool = False
    text_reserve_mm: float = TEXT_MARGIN_MM
