# -*- coding: utf-8 -*-
"""把排版计划画到 PDF 上的辅助函数与兼容入口。"""

from __future__ import annotations

from utils.page_layout import PrintTextSpec, paper_size_mm, resolve_title_nodes
from utils.pdf_draw import draw_horizontal_text, draw_vertical_text


def _draw_plan_text(pdf, spec: PrintTextSpec, font_name: str, chain=None) -> None:
    """把 `plan_print_page` 算好的一段文字画到当前页。

    竖排走 `draw_vertical_text`（逐字下移），横排用 fpdf 的 `text` ——
    横排的基线在 `baseline_mm`（竖排不需要，逐字用 `y_start_mm`）。

    ``chain`` 是 `utils.pdf_draw.FontChain`：给出时**逐字挑选字体**，主字体
    缺这个字的字形就顺位降级（古籍标题里的异体字因此落到宋体-ExtB 这类补字
    字体上，而不是画出空白）。
    """
    if spec.vertical:
        draw_vertical_text(
            pdf,
            spec.text,
            spec.x_mm,
            spec.y_start_mm,
            font_name,
            spec.font_size_pt,
            spec.color,
            direction=spec.direction,
            chain=chain,
        )
        return
    y_text = spec.y_start_mm if spec.baseline_mm is None else spec.baseline_mm
    if chain is not None:
        draw_horizontal_text(
            pdf,
            spec.text,
            spec.x_mm,
            y_text,
            font_name,
            spec.font_size_pt,
            spec.color,
            chain=chain,
        )
        return
    pdf.set_font(font_name, "", spec.font_size_pt)
    pdf.set_text_color(*spec.color)
    pdf.text(spec.x_mm, y_text, spec.text)


def _get_pdf_format(paper_size):
    """将纸张配置转换为毫米尺寸，避免依赖 FPDF 的格式表。

    几何真源已搬到 ``utils.page_layout.paper_size_mm``（第四步的「打印
    效果预览」与这里共用同一份纸张表），本函数保留为兼容入口。
    """
    return paper_size_mm(paper_size)


def _resolve_title_nodes(image_files, title_switch_nodes):
    """（兼容入口）章节节点解析，规则见 ``utils.page_layout``。

    ``页名`` 为**原始页码**（如 ``5`` / ``5-r`` 的 ``5``），不是列表下标，
    因此规则里按同名回查图片在最终清单中的下标。

    ⚠️ 语义随输入而定：CLI 直跑时 ``image_files`` 是用户目录的原始文件
    （页码=原书页名）；GUI 链路（``run_print_stage``）传入的清单是按列表
    顺序重新编号的暂存图 ``0001..N``（页码=PDF 页序）。预览侧
    （``print_preview._resolved_nodes``）同样按位置序号解析——两边同口径，
    节点在预览与成品 PDF 中一致。
    """
    return resolve_title_nodes(image_files, title_switch_nodes)
