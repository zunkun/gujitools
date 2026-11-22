"""
图片目录 → PDF：纸张/方向/页边距、标题与页码、双页左右标注。

本模块同时被 CLI（``guji run print``）与 GUI 的 print 阶段复用。页序完全由
数据层决定：GUI 把列表顺序作为 ``files`` 清单传进来，这里照单执行，不再解析
文件名；CLI 独立用法（无清单）才回退按文件名排序。

子模块（按职责）::

    constants   打印分辨率 / 二值处理 / fpdf 压缩级别
    image       图片加载与颜色模式收敛
    overrides   逐图坐标/旋转覆盖归一与位图旋转
    files       待打印清单收集与页序推导
    drawing     把排版计划画到 PDF 上
    execute     PrintFunction（参数收集与写页）

本包的 ``__init__`` 显式重导出全部名字，`from functions.print import X`
与拆分前完全一致。
"""

from __future__ import annotations

from functions.print.constants import (
    PRINT_IMAGE_DPI,
    PRINT_IMAGE_ZLIB_LEVEL,
    PRINT_KEEP_BINARY,
    _BINARY_LUT,
)
from functions.print.drawing import (
    _draw_plan_text,
    _get_pdf_format,
    _resolve_title_nodes,
)
from functions.print.execute import PrintFunction
from functions.print.files import _collect_image_files
from functions.print.image import (
    _flatten_alpha,
    _is_binary_l,
    _is_grayscale,
    _load_image,
)
from functions.print.overrides import (
    _normalize_page_rects,
    _normalize_page_rotations,
    _rotate_pil,
)

__all__ = [
    "PRINT_IMAGE_DPI",
    "PRINT_IMAGE_ZLIB_LEVEL",
    "PRINT_KEEP_BINARY",
    "PrintFunction",
]
