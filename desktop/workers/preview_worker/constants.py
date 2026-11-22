# -*- coding: utf-8 -*-
"""``preview_worker`` 的共享常量。"""

from __future__ import annotations

# 打印效果预览的基准分辨率：让整页落在 ~1600px 长边，既能看清标题/页码
# 又不至于为一张预览图分配几十 MB
PRINT_PREVIEW_TARGET_EDGE = 1600
PRINT_PREVIEW_MIN_PX_PER_MM = 2.0
PRINT_PREVIEW_MAX_PX_PER_MM = 8.0

#: 渲染一页缩略图之后让出 GIL 的比例（让出时间 = 刚花掉的时间 × 这个值）。
#:
#: ⚠️ **只在进程内兜底时用**（``pdf_render_service.offloaded()`` 为假）：那时
#: PyMuPDF 渲染整段持 GIL，不让出的话 GUI 只能捡到 ~2% 的时间片。出进程渲染
#: 时一秒都不睡——睡只会让整本缩略图白慢一倍，界面根本不需要这个时间片。
THUMB_YIELD_RATIO = 0.5

#: 1pt = 25.4/72 mm。字体像素大小必须走「pt → mm → px」这条换算，
#: 不能直接用 setPointSizeF——见 ``preview_text_font`` 的说明。
MM_PER_PT = 25.4 / 72.0
