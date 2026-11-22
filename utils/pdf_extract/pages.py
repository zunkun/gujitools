# -*- coding: utf-8 -*-
"""页码解析与缩放计算（纯函数，无 IO）。

- ``parse_pages`` / ``validate_page_range``：把用户给的页码选择变成 0-based 列表；
- ``calculate_zoom``：quick / 内嵌图路径的缩放（只受 6000px 宽度封顶）；
- ``render_zoom``：整页渲染路径的缩放（额外兜 DPI 下限）。
"""

from pathlib import Path
from typing import List, Optional

from utils.pdf_extract.constants import (
    DEFAULT_RENDER_DPI,
    DJVU_EXTS,
    MAX_OUTPUT_WIDTH_PX,
    WIDE_PAGE_PT,
)


def is_djvu_path(path) -> bool:
    """这个源文件是不是 DjVu（否则按 PDF 处理）。"""
    return Path(str(path)).suffix.lower() in DJVU_EXTS


def parse_pages(pages_str: str, total_pages: int) -> List[int]:
    """解析页码字符串为 0-based 页码列表。

    支持格式: "1,3-5,7" → [0, 2, 3, 4, 6]
    页码为 1-based，返回值转换为 0-based。

    参数:
        pages_str: 页码字符串（逗号分隔，支持范围）。
        total_pages: PDF 总页数（用于越界检查）。

    返回:
        排序后的 0-based 页码列表。

    异常:
        ValueError: 页码格式错误或超出范围。
    """
    if not pages_str:
        return list(range(total_pages))
    selected_pages = set()
    parts = [p.strip() for p in str(pages_str).split(",")]
    for part in parts:
        if not part:
            # 前后多余的逗号（"1,,3" / "1,"）当空项跳过，别抛原生 ValueError
            continue
        if "-" in part:
            # 范围: "3-5" → 页 3,4,5 → 0-based: 2,3,4
            pieces = part.split("-")
            if len(pieces) != 2 or not all(p.strip() for p in pieces):
                # ⚠️ `"1-2-3"` / `"-"` 以前抛的是原生 `ValueError: too many values
                #    to unpack`，对用户毫无指导意义（2026-09-26 审计）。这里明确
                #    指出是哪个 token 写错了。
                raise ValueError(
                    f"页码范围格式错误: {part!r}（应形如 3、3-5、1,4-8；"
                    f"总页数 {total_pages}）"
                )
            a, b = pieces
            try:
                start = int(a) - 1
                end = int(b) - 1
            except ValueError:
                raise ValueError(
                    f"页码范围里有非数字: {part!r}（总页数 {total_pages}）"
                ) from None
            if start < 0 or end >= total_pages or start > end:
                raise ValueError(f"页码范围无效: {part} (总页数: {total_pages})")
            for p in range(start, end + 1):
                selected_pages.add(p)
        else:
            # 单页: "7" → 0-based: 6
            try:
                p = int(part) - 1
            except ValueError:
                raise ValueError(
                    f"页码里有非数字: {part!r}（应形如 3、3-5、1,4-8）"
                ) from None
            if p < 0 or p >= total_pages:
                raise ValueError(f"页码 {part} 超出范围 (总页数: {total_pages})")
            selected_pages.add(p)
    return sorted(selected_pages)


def validate_page_range(
    start: Optional[int], end: Optional[int], total_pages: int
) -> List[int]:
    """根据 start/end 整数对生成 0-based 页码列表。

    参数:
        start: 起始页（1-based），None 表示从第 1 页开始。
        end: 结束页（1-based），None 表示到最后一页。
        total_pages: PDF 总页数。

    返回:
        0-based 页码列表。
    """
    if start is None and end is None:
        return list(range(total_pages))
    start_idx = start - 1 if start is not None else 0
    end_idx = end - 1 if end is not None else total_pages - 1
    if start_idx < 0:
        start_idx = 0
    if end_idx >= total_pages:
        end_idx = total_pages - 1
    if start_idx > end_idx:
        raise ValueError(f"起始页 {start_idx+1} 不能大于结束页 {end_idx+1}")
    return list(range(start_idx, end_idx + 1))


def calculate_zoom(page_width: float, requested_zoom: float = 1) -> float:
    """计算实际缩放因子，限制最大输出宽度为 6000px。

    参数:
        page_width: PDF 页面宽度（pt 单位，1pt ≈ 1/72 inch）。
        requested_zoom: 用户请求的缩放因子。

    返回:
        实际使用的缩放因子。
    """
    # 页面已足够宽时不再放大
    if page_width > WIDE_PAGE_PT:
        return 1
    if page_width <= 0:
        # ⚠️ 异常小/0 宽度的页（畸形 PDF）不能直接做除法：`MAX_OUTPUT_WIDTH_PX //
        #    int(page_width)` 在 int(page_width) == 0 时抛 ZeroDivisionError，
        #    而它会被外层 `except Exception` 吞成"这一页失败"，真因看不出来
        #    （2026-09-26 审计）。宽度异常时按"不缩放"处理，让后续渲染去报真正的错。
        return 1
    target_width = page_width * requested_zoom
    # 限制最大输出宽度，防止内存溢出
    if target_width > MAX_OUTPUT_WIDTH_PX:
        return max(1, MAX_OUTPUT_WIDTH_PX // int(page_width))
    return requested_zoom


def render_zoom(page_width: float, requested_zoom: float = 1,
                dpi: float = DEFAULT_RENDER_DPI) -> float:
    """整页渲染实际使用的缩放因子 = max(用户 zoom, DPI 下限)，再受宽度封顶。

    与 `calculate_zoom` 的区别：**只有这一条路径会补 DPI**。内嵌图（quick）
    路径仍旧用 `calculate_zoom` —— 原图字节直拷，既不该被下限放大，也不该
    因为下限变严而被判成"低清"降级（那会把 240 DPI 的扫描件重新渲染成
    放大插值图，反而更糊）。

    参数:
        page_width: PDF 页面宽度（pt）。
        requested_zoom: 用户请求的缩放因子（>=1）。
        dpi: 目标 DPI 下限；传 72 即等价于旧行为（zoom 说了算）。

    返回:
        实际渲染缩放因子。
    """
    base = calculate_zoom(page_width, requested_zoom)
    if not dpi or page_width <= 0:
        return base
    # 下限也要受封顶约束：页面本身就极宽时，6000px 上限反而更小
    cap = max(1.0, MAX_OUTPUT_WIDTH_PX / float(page_width))
    return max(base, min(dpi / 72.0, cap))
