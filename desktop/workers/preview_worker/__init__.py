# -*- coding: utf-8 -*-
"""PDF/图片渲染：整页大图、页缩略图（带磁盘缓存）与去底色效果合成。

区域合成（rembg 预览）在本线程内完成，避免主线程处理原始分辨率大图导致卡顿。

⚠️ 2026-11-22 起拆成子包（compose / constants / fonts / print_page /
doc_cache / worker）。本 ``__init__`` 只做重导出：既有
``from desktop.workers.preview_worker import X`` 全部不变；子模块之间不要
反过来导入本包（会形成循环）。
"""

from __future__ import annotations

from .compose import (
    compose_outputs_horizontal,
    compose_region_output,
    region_canvas_specs,
)
from .constants import (
    MM_PER_PT,
    PRINT_PREVIEW_MAX_PX_PER_MM,
    PRINT_PREVIEW_MIN_PX_PER_MM,
    PRINT_PREVIEW_TARGET_EDGE,
    THUMB_YIELD_RATIO,
)
from .doc_cache import (
    _get_shared_document,
    _PDF_DOC_CACHE,
    _PDF_DOC_CACHE_MAX,
    close_cached_documents,
)
from .fonts import (
    _pick_content_font,
    _pick_font,
    _pick_preview_font,
    _QT_FONT_FILES,
    preview_text_font,
    qt_family_for_file,
)
from .print_page import (
    _draw_print_text,
    compose_print_page,
    preview_px_per_mm,
)
from .worker import PreviewWorker

__all__ = [
    "MM_PER_PT",
    "PRINT_PREVIEW_MAX_PX_PER_MM",
    "PRINT_PREVIEW_MIN_PX_PER_MM",
    "PRINT_PREVIEW_TARGET_EDGE",
    "PreviewWorker",
    "THUMB_YIELD_RATIO",
    "close_cached_documents",
    "compose_outputs_horizontal",
    "compose_print_page",
    "compose_region_output",
    "preview_px_per_mm",
    "preview_text_font",
    "qt_family_for_file",
    "region_canvas_specs",
]
