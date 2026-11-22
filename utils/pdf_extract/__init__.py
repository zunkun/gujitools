# -*- coding: utf-8 -*-
"""源文件页面提取：把 PDF / DjVu 每页渲染成图片并保存。

从 `utils/pdf_utils.py` 拆出（见 docs/dev/refactor-modularity.md §3.B）——
原文件把「PDF → 图片」与「生成 PDF 的绘制辅助」两种职责混在 759 行里。
本模块只管前者，2026-11-22 起再按职责拆成子包：

1. **页码解析** (`pages.parse_pages` / `pages.validate_page_range`)
   支持两种页码选择方式：逗号分隔 + 范围字符串（如 "1,3-5,7"）或 start/end 整数对。

2. **缩放计算** (`pages.calculate_zoom` / `pages.render_zoom`)
   根据页面宽度限制最大输出尺寸（6000px），避免内存溢出；整页渲染另有
   DPI 下限（默认 300），避免没有内嵌图的矢量 PDF 在 zoom=1 时只渲染出 72 DPI。

3. **批量渲染** (`extract.process_page_batch` / `extract.render_pages_parallel`
   / `extract.extract_pdf_optimized`)
   使用 PyMuPDF (fitz) 渲染页面，支持两种模式：
   - quick=True：优先取 PDF 内嵌图片（**自适应**，不满足条件自动降级整页渲染）；
   - quick=False：直接渲染页面为高质量图片。

   quick 的判定见 `quick._embedded_page_image()`：只有「单张内嵌图 + jpg/png 格式 +
   像素不低于整页渲染尺寸」才走快路径，否则降级。这样 jp2/jbig2/CCITT 压缩、
   一页多图、内嵌缩略图这三类情况不会"为了快而变慢或变糊"。

   ⚠️ 并发后端是**多进程**（`ProcessPoolExecutor`），不是线程：PyMuPDF 的
   `get_pixmap` 期间持有 GIL，线程池对渲染**零加速**（实测 6 线程仅 1.15×，
   还把 GUI 拖卡）。详见 `extract.render_pages_parallel` 的说明。

4. **目录遍历** (`extract.run_on_input_directory`)
   支持输入为单个 PDF/DjVu 文件或包含多个 PDF/DjVu 的目录。

5. **DjVu 后端** (`djvu._render_djvu_batch_in_worker`)
   `.djvu/.djv` 用 djvu-rs（纯 Rust 解码，无需 DjVuLibre）逐页解码。
   DjVu 是扫描位图，页面自带原生分辨率，因此**不套 PDF 的 DPI 下限**：
   目标尺寸 = 原生像素 × zoom，仍受 6000px 宽度封顶。

依赖: PyMuPDF (pymupdf)、djvu-rs、Pillow (PIL)。
绘制辅助（字体注册 / 竖排文字 / 左右页判定）在 `utils/pdf_draw.py`。

⚠️ 本 ``__init__`` 只做重导出：既有 ``from utils.pdf_extract import X`` 全部不变，
子模块之间不要反过来导入本包（会形成循环）。
"""

from utils.pdf_extract.constants import (
    DEFAULT_RENDER_DPI,
    DJVU_EXTS,
    IGNORABLE_ANNOT_TYPES,
    JPX_REDUCE_MIN_COVERAGE,
    JPX_SOURCE_EXTS,
    MAX_OUTPUT_WIDTH_PX,
    QUICK_MIN_COVERAGE,
    QUICK_SOURCE_EXTS,
    SOURCE_EXTS,
    WIDE_PAGE_PT,
)
from utils.pdf_extract.djvu import (
    _djvu_target_size,
    _flatten_on_white,
    _render_djvu_batch_in_worker,
    djvu_page_count,
)
from utils.pdf_extract.extract import (
    _render_batch_dispatch,
    document_page_count,
    extract_pdf_optimized,
    extract_single_page,
    process_page_batch,
    render_pages_parallel,
    run_on_input_directory,
)
from utils.pdf_extract.jpx import (
    _decode_jpx_stream,
    _jpx_page_source,
    _jpx_reduce_level,
    _render_jpx_page,
)
from utils.pdf_extract.pages import (
    calculate_zoom,
    is_djvu_path,
    parse_pages,
    render_zoom,
    validate_page_range,
)
from utils.pdf_extract.pdf_batch import _render_batch_in_worker
from utils.pdf_extract.quick import (
    _embedded_page_image,
    _exif_swap_dims,
    _page_scan_block_reason,
    _save_embedded_image,
)
from utils.pdf_extract.render import (
    _render_page,
    _report_batch,
    _save_pil,
    _shrink_mupdf_store,
    report_image_size,
)

__all__ = [
    "DEFAULT_RENDER_DPI",
    "DJVU_EXTS",
    "IGNORABLE_ANNOT_TYPES",
    "JPX_REDUCE_MIN_COVERAGE",
    "JPX_SOURCE_EXTS",
    "MAX_OUTPUT_WIDTH_PX",
    "QUICK_MIN_COVERAGE",
    "QUICK_SOURCE_EXTS",
    "SOURCE_EXTS",
    "WIDE_PAGE_PT",
    "calculate_zoom",
    "document_page_count",
    "djvu_page_count",
    "extract_pdf_optimized",
    "extract_single_page",
    "is_djvu_path",
    "parse_pages",
    "process_page_batch",
    "render_pages_parallel",
    "render_zoom",
    "report_image_size",
    "run_on_input_directory",
    "validate_page_range",
]
