# -*- coding: utf-8 -*-
"""「预览标注图框与边距」已移除的回归守卫。

背景：原先第四步有个 ``annotate_margins`` 开关——在「打印效果」预览里用
虚线框出图片位置、四边标注边距（mm）。用户后来**删掉了这个参数**：第四步
版面编辑器里可以直接拖拽图框，边框本来就看得到，再画一层红色标注既冗余
又碍眼（2026-09-22 移除）。

本模块钉住"确实移除干净"，防止哪天有人又把它加回来：

1. ``compose_print_page`` 不再接受 ``annotate`` 开关，预览里**不再出现**
   任何标注红像素；
2. 绘制函数 ``_draw_margin_annotation`` 已不存在；
3. 参数三层（CLI 默认 / 桌面表单 / guji.yaml 模板）都不再有这个键；
4. 成品 PDF 的生成路径不碰它（这条原本就有，保留）；
5. 顺带保留一条有价值的几何断言：**PDF 与预览同几何**（≤1.5pt）。
"""

import inspect

NAME = "print_annotate_preview"
DEPENDS: list[str] = []
TITLE = "预览标注已移除（图框可拖拽，不再画红框）"

from tests.selftests._context import ok


def _count_annotation_pixels(image) -> int:
    """数出预览位图里"标注红"的像素数（图框 #e0533d + 标签 #b4331f 同系红）。"""
    count = 0
    w, h = image.width(), image.height()
    for y in range(h):
        for x in range(w):
            c = image.pixelColor(x, y)
            # 红系：R 高、G/B 低（白底 255/255/255 不会命中，缩放后的灰图也不命中）
            if c.red() > 150 and c.green() < 120 and c.blue() < 100:
                count += 1
    return count


class _StubPlan:
    """最小 plan 桩：只暴露 compose_print_page 实际读取的属性。"""

    page_w_mm = 20.0
    page_h_mm = 20.0
    image = (4.0, 4.0, 12.0, 12.0)  # x_mm, y_mm, w_mm, h_mm
    skipped = False
    title = None
    page_number = None


def run(ctx) -> None:
    import os
    from pathlib import Path

    from PySide6.QtGui import QColor, QImage

    import desktop.workers.preview_worker as pw
    from core.command_spec import PRINT_DEFAULTS
    from desktop.workers.preview_worker import compose_print_page

    # ---- 1. 开关与绘制函数都已消失 ----
    sig = inspect.signature(compose_print_page)
    ok("compose_print_page 不再接受 annotate 开关",
       "annotate" not in sig.parameters, str(list(sig.parameters)))
    ok("标注绘制函数 _draw_margin_annotation 已删除",
       not hasattr(pw, "_draw_margin_annotation"))
    ok("preview_worker 源码里不再有 annotate_margins",
       "annotate_margins" not in Path(pw.__file__).read_text(encoding="utf-8"))

    # ---- 2. 预览里不再出现标注红像素 ----
    plan = _StubPlan()
    density = 4.0  # 20mm×4 = 80×80px，像素计数的迭代量可接受
    white = QImage(100, 100, QImage.Format_RGB32)
    white.fill(QColor("#ffffff"))
    rendered = compose_print_page(white, plan, px_per_mm=density)
    ok("预览位图里没有标注红框/红字",
       _count_annotation_pixels(rendered) == 0,
       str(_count_annotation_pixels(rendered)))

    # ---- 3. 参数三层都不再有这个键 ----
    ok("CLI 默认不含 annotate_margins",
       "annotate_margins" not in PRINT_DEFAULTS,
       f"{sorted(PRINT_DEFAULTS)[:4]}…")

    from desktop.components.panels.print_params import DEFAULT_PARAMS

    ok("桌面表单默认不含 annotate_margins",
       "annotate_margins" not in DEFAULT_PARAMS)

    import yaml

    root = ctx.project_root if hasattr(ctx, "project_root") else None
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
    template = yaml.safe_load(
        open(os.path.join(str(root), "static", "guji.yaml"), encoding="utf-8")
    )
    ok("模板 print 段不含 annotate_margins",
       "annotate_margins" not in template.get("print", {}))

    # ---- 4. 成品 PDF 的生成路径不碰它 ----
    fp_src = Path(__import__(
        "functions.print", fromlist=["x"]
    ).__file__).read_text(encoding="utf-8")
    ok("functions/print.py 不引用预览标注绘制函数",
       "_draw_margin_annotation" not in fp_src
       and "compose_print_page" not in fp_src)
    ok("functions/print.py 不把 annotate_margins 当绘制开关",
       "annotate_margins" not in fp_src)

    # ---- 5. PDF 与预览同几何（保留下来的有价值断言）----
    import pymupdf

    from functions.print import PrintFunction
    from utils.page_layout import plan_print_page

    tmp = Path(ctx.tmp) / "annotate_removed"
    img_dir = tmp / "imgs"
    img_dir.mkdir(parents=True, exist_ok=True)
    src_png = img_dir / "0001.png"
    _q = QImage(800, 1200, QImage.Format_RGB32)
    _q.fill(QColor("#f2f2f2"))
    _q.save(str(src_png))

    pdf_args = {
        "input": img_dir,
        "output": tmp / "out",
        "pdf_name": "clean.pdf",
        "paper_size": "A4",
        "orientation": "landscape",
        "page_margins": [15.0, 10.0, 20.0, 10.0],
        "title_printing": False,
        "page_number_printing": False,
        "workers": 1,
    }
    PrintFunction(dict(pdf_args)).execute()
    pdf_path = tmp / "out" / "clean.pdf"
    ok("不带预览专属键也能正常生成 PDF", pdf_path.exists(), str(pdf_path))
    doc = pymupdf.open(str(pdf_path))
    try:
        ok("PDF 页数与条目一致", doc.page_count == 1, str(doc.page_count))
        info = doc[0].get_image_info()[0]
        bx0, by0, bx1, by1 = info["bbox"]
        pt = 72.0 / 25.4
        expect = plan_print_page(
            (800, 1200),
            {
                "paper_size": "A4", "orientation": "landscape",
                "page_margins": [15.0, 10.0, 20.0, 10.0],
            },
            0, 1,
        )
        ex, ey, ew, eh = expect.image
        ok("PDF 几何与预览一致（≤1.5pt）",
           abs(bx0 - ex * pt) < 1.5
           and abs(by0 - ey * pt) < 1.5
           and abs((bx1 - bx0) - ew * pt) < 1.5
           and abs((by1 - by0) - eh * pt) < 1.5,
           f"pdf={tuple(round(v, 2) for v in (bx0, by0, bx1, by1))} "
           f"plan={tuple(round(v * pt, 2) for v in expect.image)}")
    finally:
        doc.close()
