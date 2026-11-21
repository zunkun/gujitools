# -*- coding: utf-8 -*-
"""通用页边距支持负值（用户 2026-11-21）。

用户原话：「PDF排版，通用边距，支持负值，比如当设置 0 的时候，还不合适，
可以继续向负值设置」。也就是说，0 边距仍嫌图小/白边多时，用户要能把图
**顶出纸边**（超出部分被纸张裁掉）——等价于按纸宽放大再裁边。

本模块钉住四层口径：

1. **校验层**（CLI / GUI 共用 ``COMMAND_SPECS["print"].validators``）：
   `page_margins` 一族收负值，区间 [-100, 100]；`title_margins` /
   `page_number_margins` 仍要求非负（负值等于把标题画到纸外，看不见）；
2. **GUI 解析层**（``panels/print_params.parse_margin4``）：区间与校验层
   是同一份常量，界面不会比命令行更宽或更严；
3. **几何真源**（``utils.page_layout.plan_print_page``）：负边距让图片更大、
   落点出纸；而**标题/页码的落点仍夹在纸内**（否则用户会以为"没生效"）；
4. **成品 PDF**：fpdf 能接受出纸的图片框，图片真的比纸面更大。
"""

NAME = "print_margin_negative"
DEPENDS: list[str] = []
TITLE = "通用边距支持负值（图片顶出纸边）"


def run(ctx) -> None:
    from pathlib import Path

    from tests.selftests._context import ok

    from core.args import CommandArgs
    from core.command_spec import (
        PRINT_MARGIN_LIMIT_MM, PRINT_MARGIN_MIN_MM,
    )

    tmp = Path(ctx.tmp) / "print_margin_negative"
    tmp.mkdir(parents=True, exist_ok=True)

    def build(**kw):
        """按 CLI/GUI 共用链路构造并校验 print 参数。"""
        args = CommandArgs(command="print", input=str(tmp), **kw)
        args.validate()
        return args

    # ---- 1. 校验层：通用边距收负值，区间 [-100, 100] ----
    ok("区间常量对称（上界 100 / 下界 -100）",
       PRINT_MARGIN_LIMIT_MM == 100 and PRINT_MARGIN_MIN_MM == -100,
       f"{PRINT_MARGIN_MIN_MM}~{PRINT_MARGIN_LIMIT_MM}")

    got = build(page_margins="-10").get("page_margins")
    ok("page_margins=-10 放行（负值合法）",
       got == [-10.0] * 4, str(got))
    got = build(page_margins="-10,0,0,5").get("page_margins")
    ok("四值混填（含负值）原样保留",
       got == [-10.0, 0.0, 0.0, 5.0], str(got))
    got = build(left_page_margins="-8", right_page_margins="-12").get(
        "left_page_margins")
    ok("左右页专用边距同样收负值", got == [-8.0] * 4, str(got))
    ok("下界端点 -100 放行",
       build(page_margins="-100").get("page_margins") == [-100.0] * 4)

    for bad, why, needle in (
        ("-101", "低于下界", "不能低于"),
        ("101", "超过上界", "不能超过"),
    ):
        try:
            build(page_margins=bad)
        except ValueError as exc:
            ok(f"page_margins={bad} 被拒（{why}）",
               needle in str(exc), str(exc)[:80])
        else:
            ok(f"page_margins={bad} 被拒（{why}）", False, "放行了")

    # 标题/页码「距页边」**不跟着放开**：负值等于把文字画到纸外。
    for key in ("title_margins", "page_number_margins"):
        try:
            build(**{key: "-5"})
        except ValueError as exc:
            ok(f"{key}=-5 仍被拒（负值 = 文字画到纸外）",
               "负数" in str(exc), str(exc)[:80])
        else:
            ok(f"{key}=-5 仍被拒（负值 = 文字画到纸外）", False, "放行了")

    # ---- 2. GUI 解析层：与校验层同一份区间 ----
    from core.command_spec import COMMAND_SPECS

    _sources = COMMAND_SPECS["print"].validators
    ok("print 校验器挂在命令规格上（CLI 与 GUI 共用同一份）",
       len(_sources) == 1)

    from desktop.components.panels.print_params import parse_margin4

    ok("parse_margin4 收下负值单值", parse_margin4("-10") == [-10.0] * 4,
       str(parse_margin4("-10")))
    ok("parse_margin4 收下负值四值",
       parse_margin4("-10,0,0,5") == [-10.0, 0.0, 0.0, 5.0],
       str(parse_margin4("-10,0,0,5")))
    ok("parse_margin4 仍接受全角逗号里的负值",
       parse_margin4("-10，0") == [-10.0, 0.0, -10.0, 0.0],
       str(parse_margin4("-10，0")))
    try:
        parse_margin4("-101")
    except ValueError as exc:
        ok("parse_margin4 拒绝越界负值（界面不比校验宽）",
           "之间" in str(exc), str(exc)[:80])
    else:
        ok("parse_margin4 拒绝越界负值（界面不比校验宽）", False, "放行了")

    # 面板往返：输入 -10 → get_args 原样导出
    from desktop.components.panels.print_panel import PrintPanel

    panel = PrintPanel()
    try:
        panel.page_margins.setText("-10")
        args = panel.get_args()
        ok("打印面板把 -10 原样导出（不被默认值兜回去）",
           args.get("page_margins") == [-10.0] * 4,
           str(args.get("page_margins")))
        panel._apply_args({"page_margins": [-10.0, 0.0, 0.0, 5.0]})
        ok("历史参数里的负边距能回填到表单",
           panel.page_margins.text() == "-10,0,0,5",
           panel.page_margins.text())
    finally:
        panel.deleteLater()

    # ---- 3. 几何真源：负边距 = 图片放大并顶出纸边 ----
    from utils.page_layout import TEXT_MARGIN_MM, plan_print_page

    base = {"paper_size": "A4", "orientation": "landscape"}
    wide = (2400, 800)  # 宽图 → 宽度受限，直接反映可用区变化
    zero = plan_print_page(wide, {**base, "page_margins": [0] * 4}, 0, 1)
    neg = plan_print_page(wide, {**base, "page_margins": [-10] * 4}, 0, 1)

    avail_zero = 297.0 - 2 * TEXT_MARGIN_MM
    avail_neg = 297.0 + 20.0 - 2 * TEXT_MARGIN_MM
    ok("0 边距：图片宽 = 纸宽 − 固定留白",
       abs(zero.image[2] - avail_zero) < 1e-6, str(zero.image[2]))
    ok("−10 边距：可用区比纸面宽 20mm，图片随之变大",
       abs(neg.image[2] - avail_neg) < 1e-6,
       f"{neg.image[2]:.2f} vs {avail_neg:.2f}")
    ok("−10 边距：图片落点顶出纸左边（x 为负）",
       neg.image[0] < 0, f"x={neg.image[0]:.2f}")
    # 宽图是"宽度受限"，纵向仍按可用区居中——负上下边距只是把可用区撑高，
    # 图本身不比纸高，所以 y 照旧留在纸内。
    ok("−10 边距：宽度受限的图纵向仍居中于可用区",
       abs(neg.image[1] - (-10.0 + (230.0 - neg.image[3]) / 2)) < 1e-6,
       f"y={neg.image[1]:.2f} h={neg.image[3]:.2f}")
    ok("出纸量对称：左右各顶出 10mm",
       abs(-neg.image[0] - 10.0) < 1e-6, str(neg.image[0]))

    # ⚠️ 标题/页码不能跟着出纸（否则等于"打开就看不见"）
    titled = dict(base, page_margins=[-10] * 4, title_printing=True,
                  title_text="测试古籍", title_font_size=18,
                  page_number_printing=True, page_number_font_size=12)
    tplan = plan_print_page(wide, titled, 0, 2)
    ok("负边距下标题仍在纸内（落点不跟着出纸）",
       tplan.title is not None and tplan.title.x_mm >= 0
       and tplan.title.y_start_mm >= 0,
       f"x={tplan.title.x_mm if tplan.title else None} "
       f"y={tplan.title.y_start_mm if tplan.title else None}")
    ok("负边距下页码仍在纸内",
       tplan.page_number is not None and tplan.page_number.x_mm >= 0
       and tplan.page_number.y_start_mm >= 0,
       f"x={tplan.page_number.x_mm if tplan.page_number else None} "
       f"y={tplan.page_number.y_start_mm if tplan.page_number else None}")

    # 正常（非负）边距的落点公式一字未改
    legacy = plan_print_page(
        wide, {**base, "page_margins": [20] * 4, "title_printing": True,
               "title_text": "测试古籍", "title_font_size": 18}, 0, 1)
    ok("非负边距下标题落点仍是 ml/2（老任务几何不变）",
       legacy.title is not None and abs(legacy.title.x_mm - 10.0) < 1e-6,
       str(legacy.title.x_mm if legacy.title else None))

    # ---- 4. 成品 PDF：图片真的比纸面大（fpdf 接受出纸的框）----
    from PySide6.QtGui import QColor, QImage, QPainter

    img_dir = tmp / "imgs"
    img_dir.mkdir(parents=True, exist_ok=True)
    for name in ("0001.png", "0002.png"):
        img = QImage(2400, 800, QImage.Format.Format_RGB32)
        img.fill(QColor("#f2f2f2"))
        painter = QPainter(img)
        painter.setPen(QColor("#333333"))
        painter.drawRect(10, 10, 2380, 780)
        painter.end()
        img.save(str(img_dir / name))

    import pymupdf

    from functions.print import PrintFunction

    PrintFunction({  # type: ignore[reportArgumentType]  # 直接喂 dict（运行时按 get 取值）
        "input": img_dir, "output": tmp / "out", "pdf_name": "neg.pdf",
        "paper_size": "A4", "orientation": "landscape",
        "page_margins": "-10", "workers": 1,
        "title_printing": False, "page_number_printing": False,
    }).execute()
    pdf_path = tmp / "out" / "neg.pdf"
    ok("负边距的 PDF 已生成", pdf_path.exists(), str(pdf_path))

    if pdf_path.exists():
        doc = pymupdf.open(str(pdf_path))
        try:
            page_w_pt = doc[0].rect.width
            info = doc[0].get_image_info()[0]
            x0, y0, x1, y1 = info["bbox"]
            pt_per_mm = 72.0 / 25.4
            ok("PDF 页尺寸不变（负边距只放大图片，不改纸张）",
               abs(page_w_pt - 297.0 * pt_per_mm) < 1.0,
               f"{page_w_pt:.1f}pt")
            ok("PDF 里图片确实顶出纸左边（x0 = −10mm）",
               abs(x0 / pt_per_mm + 10.0) < 0.5,
               f"bbox=({x0:.1f},{y0:.1f}) → 左出纸 {-x0 / pt_per_mm:.2f}mm")
            ok("PDF 里图片宽 = 预览几何（≤1.5pt）",
               abs((x1 - x0) - neg.image[2] * pt_per_mm) < 1.5,
               f"pdf={(x1 - x0):.1f}pt plan={neg.image[2] * pt_per_mm:.1f}pt")
            ok("PDF 里图片比纸面宽（说明真的按负边距放大了）",
               (x1 - x0) > page_w_pt,
               f"图 {(x1 - x0):.1f}pt vs 纸 {page_w_pt:.1f}pt")
        finally:
            doc.close()
