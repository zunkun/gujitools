# -*- coding: utf-8 -*-
"""第四步「预览标注图框与边距」自测：只画在预览、不进 PDF。

背景：需求②要求第四步用虚线框出图片位置、四边标注边距（mm），作为作图
标识；用户拍板「只画在预览」——即只在第四步「打印效果」预览里画，不进入
成品 PDF。本模块钉住这条边界不变量：

1. 入口与唯一绘制函数：``compose_print_page`` 接受 ``annotate`` 开关，
   ``_draw_margin_annotation`` 是唯一画标注的函数；
2. 行为隔离（双向）：``annotate=False`` 不画任何标注（预览里没有红框/红字），
   ``annotate=True`` 画出虚线图框 + 四边 mm 标注；
3. 不污染成品：``functions/print.py`` 的 PDF 生成路径**完全不碰**标注绘制
   （不引用 ``_draw_margin_annotation`` / ``compose_print_page`` / 标注开关），
   带着 ``annotate_margins=True`` 也能正常出 PDF、几何不受影响；
4. 开关接线：``core.command_spec.PRINT_DEFAULTS["annotate_margins"]`` 默认
   False；``preview_worker`` 从 ``print_spec["args"]`` 读该键传给
   ``compose_print_page``。

判据（双向）：标注像素计数，``annotate=False`` 必为 0、``annotate=True`` 必
大于 0——把 ``_draw_margin_annotation`` 改成空函数会红（True 分支不再有红
像素），把开关焊死成「总是画」也会红（False 分支冒出红像素），故守卫不会
「注入后全绿」失效。
"""

import inspect

NAME = "print_annotate_preview"
DEPENDS: list[str] = []
TITLE = "第四步预览标注只画预览不进PDF"

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
    from pathlib import Path

    from PySide6.QtGui import QColor, QImage, QPainter

    from core.command_spec import PRINT_DEFAULTS
    from desktop.workers.preview_worker import (
        _draw_margin_annotation,
        compose_print_page,
    )

    # ---- 1. 入口与唯一绘制函数 ----
    sig = inspect.signature(compose_print_page)
    ok("compose_print_page 接受 annotate 开关",
       "annotate" in sig.parameters, str(list(sig.parameters)))
    ok("_draw_margin_annotation 存在且签名为 (painter, plan, density)",
       callable(_draw_margin_annotation)
       and len(inspect.signature(_draw_margin_annotation).parameters) == 3)

    # ---- 2. 行为隔离（双向）----
    plan = _StubPlan()
    density = 4.0  # 20mm×4 = 80×80px，像素计数的迭代量可接受
    # 纯白源图，避免任何非白像素干扰红像素计数
    white = QImage(100, 100, QImage.Format_RGB32)
    white.fill(QColor("#ffffff"))

    off = compose_print_page(white, plan, px_per_mm=density, annotate=False)
    on = compose_print_page(white, plan, px_per_mm=density, annotate=True)
    cnt_off = _count_annotation_pixels(off)
    cnt_on = _count_annotation_pixels(on)
    ok("annotate=False → 预览无标注红像素", cnt_off == 0, str(cnt_off))
    ok("annotate=True → 预览画出标注（虚线框 + 四边距）", cnt_on > 0, str(cnt_on))

    # 直接调用 _draw_margin_annotation 也应产出红像素（证明其确为绘制者）
    direct = QImage(80, 80, QImage.Format_RGB32)
    direct.fill(QColor("#ffffff"))
    p = QPainter(direct)
    _draw_margin_annotation(p, plan, density)
    p.end()
    ok("直接调用 _draw_margin_annotation 即画出标注",
       _count_annotation_pixels(direct) > 0, str(_count_annotation_pixels(direct)))

    # ---- 3. 不污染成品 PDF ----
    pw_src = Path(__import__(
        "desktop.workers.preview_worker", fromlist=["x"]
    ).__file__).read_text(encoding="utf-8")
    ok("preview_worker 从 print_spec['args'] 读 annotate_margins",
       "annotate_margins" in pw_src)

    fp_src = Path(__import__(
        "functions.print", fromlist=["x"]
    ).__file__).read_text(encoding="utf-8")
    ok("functions/print.py 不引用预览标注绘制函数",
       "_draw_margin_annotation" not in fp_src
       and "compose_print_page" not in fp_src)
    ok("functions/print.py 不把 annotate_margins 当绘制开关",
       "annotate_margins" not in fp_src)

    # 带着 annotate_margins=True（预览专属键）也必须能正常出 PDF，且几何不受影响
    import pymupdf

    from functions.print import PrintFunction
    from utils.page_layout import plan_print_page

    tmp = Path(ctx.tmp) / "annotate_clean"
    img_dir = tmp / "imgs"
    img_dir.mkdir(parents=True, exist_ok=True)
    src_png = img_dir / "0001.png"
    _q = QImage(800, 1200, QImage.Format_RGB32)
    _q.fill(QColor("#f2f2f2"))
    _qp = QPainter(_q)
    _qp.setPen(QColor("#333333"))
    _qp.drawRect(10, 10, 780, 1180)
    _qp.end()
    _q.save(str(src_png))

    pdf_args = {
        # 与 CommandArgs 一致：input/output 必须是 Path
        "input": img_dir,
        "output": tmp / "out",
        "pdf_name": "clean.pdf",
        "paper_size": "A4",
        "orientation": "landscape",
        "page_margins": [15.0, 10.0, 20.0, 10.0],
        "title_printing": False,
        "page_number_printing": False,
        "annotate_margins": True,  # 预览专属键，PDF 不应受影响
        "workers": 1,
    }
    PrintFunction(dict(pdf_args)).execute()
    pdf_path = tmp / "out" / "clean.pdf"
    ok("带 annotate_margins 也能正常生成 PDF", pdf_path.exists(), str(pdf_path))
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
        ok("带 annotate_margins 的 PDF 几何与预览一致（≤1.5pt）",
           abs(bx0 - ex * pt) < 1.5
           and abs(by0 - ey * pt) < 1.5
           and abs((bx1 - bx0) - ew * pt) < 1.5
           and abs((by1 - by0) - eh * pt) < 1.5,
           f"pdf={tuple(round(v, 2) for v in (bx0, by0, bx1, by1))} "
           f"plan={tuple(round(v * pt, 2) for v in expect.image)}")
    finally:
        doc.close()

    # ---- 4. 开关接线 ----
    ok("PRINT_DEFAULTS.annotate_margins 默认 False",
       PRINT_DEFAULTS.get("annotate_margins") is False)
