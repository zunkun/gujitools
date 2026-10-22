# -*- coding: utf-8 -*-
"""缩略图**懒加载**自测：导入只备首屏 + 查看器按可见窗口补。

用户 2026-10-21：

> 我就是想提取图片，为何这么复杂

在此之前，"建任务"那一刻就把**整本**缩略图渲一遍（2000 页要几分钟后台 CPU），
而只想提取的人根本不需要后半本。现在两件事一起改：

1. **导入只预渲染首屏**（``PREFETCH_PAGES``，24 页），剩下的不渲；
2. **查看器滚到哪补到哪**（``PdfViewerWidget._fill_window``，单页 ~170ms）。

断言线：

1. 导入跑完，缓存里恰好是 ``min(总页数, PREFETCH_PAGES)`` 张（不再是整本）；
2. ``PREFETCH_PAGES`` 远小于一本常见的书（防止有人又把它调回"整本"）；
3. 查看器补图**只补可见窗口 ± 边距**：窗口外的页一张都不渲；
4. 窗口内的页确实被补上（不是"什么也不补"）。
"""

from __future__ import annotations

import time
from pathlib import Path

NAME = "thumb_lazy"
DEPENDS: list[str] = []
TITLE = "缩略图懒加载（导入只备首屏 + 按窗口补）"


def run(ctx) -> None:
    from PySide6.QtWidgets import QApplication

    from desktop.components.viewers.pdf_viewer import PdfViewerWidget
    from desktop.workers.source_thumbnails_worker import (
        PREFETCH_PAGES, SourceThumbnailsWorker,
    )
    from tests.selftests._context import ok, wait_until

    app = ctx.app
    tmp = ctx.tmp / "thumb_lazy"
    tmp.mkdir(parents=True, exist_ok=True)
    pdf = ctx.big_pdf                      # 80 页样例（纯文字，渲得很快）
    pages = 80

    # ---- 1. 导入只预渲染首屏 ----
    ok("懒加载：预渲染上限远小于整本（别再改回\"整本\"）",
       PREFETCH_PAGES <= 32, str(PREFETCH_PAGES))
    out = tmp / "thumbs"
    worker = SourceThumbnailsWorker(pdf, out)
    worker.run()
    produced = len(list(out.glob("*.jpg")))
    ok("导入：只渲了首屏那么多张", produced == min(pages, PREFETCH_PAGES),
       f"{produced} 张（应为 {min(pages, PREFETCH_PAGES)}）")
    ok("导入：确实没有整本渲", produced < pages, f"{produced}/{pages}")

    # ---- 2. 查看器按可见窗口补图 ----
    viewer = PdfViewerWidget()
    # ⚠️ 先把"可见窗口"钉死：离屏环境的视口几何不可靠，本用例测的是
    #    ``_fill_window`` 的窗口算术，不是 Qt 的滚动几何（同 thumbs_chunked）。
    viewer.strip.visible_row_range = lambda: (20, 25)   # type: ignore[method-assign]
    viewer.set_pdf(pdf, cache_dir=tmp / "viewer_thumbs")
    ok("查看器：页数元信息到位（{0} 页）".format(pages),
       wait_until(app, lambda: viewer._thumb_total == pages, timeout=20.0),
       str(viewer._thumb_total))

    lo = 20 - PdfViewerWidget.FILL_WINDOW_MARGIN
    hi = 25 + PdfViewerWidget.FILL_WINDOW_MARGIN
    ok("查看器：窗口内该补的页都补上了",
       wait_until(app, lambda: all(i in viewer._thumb_received
                                   for i in range(20, 26)), timeout=30.0),
       str(sorted(viewer._thumb_received)))
    got = sorted(viewer._thumb_received)
    ok("查看器：只补窗口 ± 边距，窗口外一张都没渲",
       got and min(got) >= lo and max(got) <= hi, f"{got[:3]}…{got[-3:]}")
    ok("查看器：远处的页（第 61 页）没被渲",
       60 not in viewer._thumb_received)

    viewer.shutdown_workers()
    QApplication.processEvents()
