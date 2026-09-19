# -*- coding: utf-8 -*-
"""PDF 工具（兼容层）。

实现已按职责拆开，本模块**只做 re-export**，保留旧导入路径可用：

- `utils/pdf_extract.py` —— PDF → 图片：页码解析、缩放计算、批量渲染、目录遍历；
- `utils/pdf_draw.py` —— 生成 PDF 的绘制辅助：字体注册、竖排文字、左右页判定。

新代码请直接 import 上面两个模块。等所有调用点迁完，本壳即可删除。

⚠️ `parse_margins` / `parse_color` **不在这里** —— 它们本就是转发
`utils.margin_utils.normalize_margin` / `utils.color_utils.parse_color` 的冗余壳，
调用点已改为直接用底层模块（「默认值只保留一份」，见
docs/dev/refactor-modularity.md §3.D）。
"""


from utils.pdf_extract import (  # noqa: F401
    DEFAULT_RENDER_DPI,
    MAX_OUTPUT_WIDTH_PX,
    QUICK_MIN_COVERAGE,
    QUICK_SOURCE_EXTS,
    WIDE_PAGE_PT,
    _embedded_page_image,
    _render_page,
    _save_embedded_image,
    _save_pil,
    calculate_zoom,
    extract_pdf_optimized,
    parse_pages,
    process_page_batch,
    render_pages_parallel,
    render_zoom,
    report_image_size,
    run_on_input_directory,
    validate_page_range,
)

from utils.pdf_draw import (  # noqa: F401
    draw_vertical_text,
    get_page_side_by_start,
    get_page_side_from_name,
    register_fonts,
)

__all__ = [
    "DEFAULT_RENDER_DPI",
    "MAX_OUTPUT_WIDTH_PX",
    "QUICK_MIN_COVERAGE",
    "QUICK_SOURCE_EXTS",
    "WIDE_PAGE_PT",
    "_embedded_page_image",
    "_render_page",
    "_save_embedded_image",
    "_save_pil",
    "calculate_zoom",
    "extract_pdf_optimized",
    "parse_pages",
    "process_page_batch",
    "render_pages_parallel",
    "render_zoom",
    "report_image_size",
    "run_on_input_directory",
    "validate_page_range",
    "draw_vertical_text",
    "get_page_side_by_start",
    "get_page_side_from_name",
    "register_fonts",
]
