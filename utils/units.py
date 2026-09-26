# -*- coding: utf-8 -*-
"""长度单位换算常量（mm / inch / pt 互转的唯一定义处）。

这些值此前在 ``utils/page_layout.py``、``utils/pdf_utils.py``、
``functions/print.py`` 各写一份（``MM_PER_INCH = 25.4`` 三处、
``POINTS_PER_MM`` 两处），``utils/box_geometry.py`` 里还散着裸的 ``25.4``。
换算常量是**客观值**，本来就不该有第二份——改一处漏两处时又查不出来
（值都一样，不会报错，只会悄悄各走各的）。

依赖方向：本模块不 import 任何东西，是 ``utils`` 的最底层，任何层都可引用。
"""

from __future__ import annotations

# 1 英寸 = 25.4 毫米（国际标准，不是可调参数）
MM_PER_INCH = 25.4
# 1 毫米 = 多少点（pt）。PDF 的排版单位是 pt（1pt = 1/72 inch），
# 而 print 阶段的几何一律用 mm（fpdf unit="mm"），两者换算只此一处。
POINTS_PER_MM = 72.0 / MM_PER_INCH


def mm_to_px(mm: float, dpi: float) -> float:
    """毫米 → 像素（按给定 DPI）。"""
    return float(mm) * float(dpi) / MM_PER_INCH


def px_to_mm(px: float, dpi: float) -> float:
    """像素 → 毫米（按给定 DPI）。"""
    return float(px) * MM_PER_INCH / float(dpi)


#: 扫描件渲染/保存的默认 DPI（**唯一定义处**）。
#: ⚠️ 以前这个 300 在 4 个文件里各写一遍（`utils/pdf_extract.py`、
#: `core/command_spec.py` 的 `extract.dpi` 默认值、`functions/extract.py`、
#: `desktop/stages/generic_stage.py`），改一处必漏几处，CLI/GUI/库三方默认值
#: 会悄悄分叉（2026-09-26 审计）。
DEFAULT_RENDER_DPI = 300
#: 1 英寸 = 72 点（PDF 排版单位）。poppler/PyMuPDF 的默认渲染分辨率也是 72dpi，
#: 「zoom=1」在 PDF 语境里就等于 72dpi —— 别在业务代码里裸写 72。
POINTS_PER_INCH = 72.0
