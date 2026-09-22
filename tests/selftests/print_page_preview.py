# -*- coding: utf-8 -*-
"""第四步「打印效果」预览自测：几何真源、与成品 PDF 一致、只画不落盘。

背景：第四步原来是「图片瀑布流 + 说明」——用户看到的是**图片本身**，
右侧那一大堆纸张/边距/标题/页码参数只有点了「生成 PDF」才知道长什么样，
试错成本极高。改成左缩略图 + 右效果预览后，必须守住三条不变量：

1. **几何只有一份**：预览用的 `utils.page_layout.plan_print_page` 必须就是
   `functions/print.py` 生成 PDF 时用的那份——本模块直接生成一次 PDF，用
   PyMuPDF 读回图片实际落点，与 plan 逐值比对；
2. **只是效果**：效果预览不得写出任何文件（尤其不得生成 PDF）；
3. **参数真的生效**：纸张/方向/边距/标题/页码变化后，预览位图随之改变。
"""

import time

NAME = "print_page_preview"
DEPENDS: list[str] = []
TITLE = "第四步打印效果预览"


def _tmp_png(path, w: int, h: int):
    """造一张纯白测试图（QPainter 随手画两笔，便于肉眼区分）。"""
    from PySide6.QtGui import QColor, QImage, QPainter

    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor("#f2f2f2"))
    painter = QPainter(img)
    painter.setPen(QColor("#333333"))
    painter.drawRect(10, 10, w - 20, h - 20)
    painter.end()
    img.save(str(path))
    return path


def _wait_new_image(widget, app, previous, timeout: float = 20.0):
    """等效果预览加载完成，返回新的 QPixmap（previous 用于区分旧图）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        pm = widget.view._pixmap
        if pm is not None and (
            previous is None or (pm.width(), pm.height()) != previous
        ):
            app.processEvents()
            return pm
        time.sleep(0.05)
    return widget.view._pixmap


def run(ctx) -> None:
    from pathlib import Path

    from PySide6.QtWidgets import QAbstractItemView

    from tests.selftests._context import ok, pump

    from desktop.components.viewers.print_preview import PrintPreviewWidget
    from desktop.components.viewers.thumb_strip import ThumbStrip
    from desktop.workers.preview_worker import (
        compose_print_page, preview_px_per_mm,
    )
    from utils.page_layout import (
        TEXT_INSET_MM, TEXT_MARGIN_MM, TEXT_SIDE_OFFSET_MM,
        plan_print_page, print_page_size_mm,
    )

    app = ctx.app
    tmp = Path(ctx.tmp) / "print_page_preview"
    tmp.mkdir(parents=True, exist_ok=True)

    # ---- 1. 纸张/方向 ----
    ok("A4 横版 = 297×210mm", print_page_size_mm("A4", "landscape") == (297.0, 210.0))
    ok("A4 竖版 = 210×297mm", print_page_size_mm("A4", "portrait") == (210.0, 297.0))
    ok("fpdf 的 P/L 写法同样认得",
       print_page_size_mm("A4", "L") == (297.0, 210.0)
       and print_page_size_mm("a4", "P") == (210.0, 297.0))

    # ---- 2. 图片落点 ----
    args = {
        "paper_size": "A4", "orientation": "landscape",
        "page_margins": [10.0, 10.0, 10.0, 10.0],
    }
    plan = plan_print_page((800, 1200), args, 0, 1)
    x, y, w, h = plan.image
    # 可用区宽 = 297 - 左右页边距 - 2×TEXT_MARGIN_MM，高 = 210 - 上下页边距。
    # ⚠️ 别把算好的数（如 261）写死在断言里：TEXT_MARGIN_MM 一改这里就假失败，
    # 而且是"看起来像几何错了"的那种假失败。一律从常量推导。
    avail_w = 297.0 - 10.0 - 10.0 - 2 * TEXT_MARGIN_MM
    expect_scale = 190.0 / 1200
    ok("图片等比缩放受高度限制",
       abs(w - 800 * expect_scale) < 1e-6 and abs(h - 190.0) < 1e-6,
       f"w={w} h={h}")
    ok("图片在可用区内水平居中",
       abs(x - (10 + TEXT_MARGIN_MM + (avail_w - w) / 2)) < 1e-6, f"x={x}")
    ok("图片垂直居中于版心", abs(y - 10.0) < 1e-6, f"y={y}")
    ok("未开标题/页码时两段文字都是 None",
       plan.title is None and plan.page_number is None)

    # ---- 3. 标题与页码 ----
    full = dict(args)
    full.update({
        "title_printing": True, "title_text": "测试古籍",
        "title_font_size": 18, "title_position": "top",
        "title_orientation": "vertical",
        "page_number_printing": True, "page_number_font_size": 12,
        "page_number_base": 0,
    })
    plan2 = plan_print_page((800, 1200), full, 2, 5)
    ok("标题按章节前的最后一个节点取值（无节点时用 title_text）",
       plan2.title is not None and plan2.title.text == "测试古籍",
       str(plan2.title))
    ok("页码为「第…頁」且按物理页序 + base",
       plan2.page_number is not None and plan2.page_number.text == "第三頁",
       str(plan2.page_number))
    ok("标题/页码默认竖排且同侧",
       plan2.title.vertical and plan2.page_number.vertical
       and plan2.side == "left", str(plan2.side))
    ok("竖排在页边、横排另有基线",
       plan2.title.baseline_mm is None
       and plan2.title.x_mm < 10.0, str(plan2.title.x_mm))

    # 奇偶页边距
    odd_even = dict(full)
    odd_even.update({
        "left_page_margins": [5.0, 5.0, 5.0, 30.0],
        "right_page_margins": [5.0, 30.0, 5.0, 5.0],
    })
    left_page = plan_print_page((800, 1200), odd_even, 0, 2)   # 第 1 页（奇）
    right_page = plan_print_page((800, 1200), odd_even, 1, 2)  # 第 2 页（偶）
    ok("奇数页用 left_page_margins、偶数页用 right_page_margins",
       left_page.image[0] > right_page.image[0],
       f"{left_page.image[0]:.2f} vs {right_page.image[0]:.2f}")

    # ---- 3b. 标题/页码「距页边」（左右可不同，允许压在图片上）----
    from utils.page_layout import POINTS_PER_MM, text_block_width_mm, text_insets

    ok("距页边：空值一律是 None（= 沿用旧行为）",
       text_insets(None) is None and text_insets("") is None
       and text_insets("   ") is None)
    ok("距页边：单值补四边", text_insets("10") == [10.0] * 4, str(text_insets("10")))
    ok("距页边：两值 = 上下,左右",
       text_insets("2,14") == [2.0, 14.0, 2.0, 14.0], str(text_insets("2,14")))
    ok("距页边：四值 = 上,右,下,左",
       text_insets("2,14,2,10") == [2.0, 14.0, 2.0, 10.0],
       str(text_insets("2,14,2,10")))
    ok("距页边：非法值不抛异常（宽松，校验归入口层）",
       text_insets("abc") is None, str(text_insets("abc")))

    # 未配置 → 老行为分支：左页 ml/2、右页 page_w - mr + TEXT_SIDE_OFFSET_MM、
    # 纵向 mt + TEXT_INSET_MM。⚠️ 三个修正量已归零，但断言仍要**从常量推导**
    # 而不是写死 4.0 / 12.0 —— 写死的后果是改一次常量就收获一批"看起来像
    # 几何错了"的假失败（本轮就踩到）。
    legacy_l = plan_print_page((800, 1200), full, 0, 2)
    legacy_r = plan_print_page((800, 1200), full, 1, 2)
    ok("未配置距页边 → 左页仍是 ml/2",
       abs(legacy_l.title.x_mm - 5.0) < 1e-6, str(legacy_l.title.x_mm))
    ok("未配置距页边 → 右页 = mr - TEXT_SIDE_OFFSET_MM",
       abs((297.0 - legacy_r.title.x_mm) - (10.0 - TEXT_SIDE_OFFSET_MM)) < 1e-6,
       str(297.0 - legacy_r.title.x_mm))
    ok("未配置距页边 → 纵向 = 页边距 + TEXT_INSET_MM",
       abs(legacy_l.title.y_start_mm - (10.0 + TEXT_INSET_MM)) < 1e-6,
       str(legacy_l.title.y_start_mm))

    # 配置了 → 距纸张边界的绝对距离；左页取左值、右页取右值
    inset_args = dict(full, title_margins=[2, 14, 2, 10],
                      page_number_margins=[2, 14, 2, 10])
    ins_l = plan_print_page((800, 1200), inset_args, 0, 2)
    ins_r = plan_print_page((800, 1200), inset_args, 1, 2)
    ok("左页标题距左边界 = 左值（文字轮廓左边缘就是落点）",
       abs(ins_l.title.x_mm - 10.0) < 1e-6, str(ins_l.title.x_mm))
    # ⚠️ 右页口径（用户明确要求）：填的是**文字轮廓右边缘**到纸边的距离，
    # 而落点 x 是字形左边缘、文字还往右占一个块宽（竖排 = 一个字宽），
    # 所以 x 必须再往左退一个块宽。不退的话右轮廓到纸边是「右值 + 字宽」，
    # 文字比设定值多缩一个字宽。
    _title_w = text_block_width_mm(ins_r.title.text, ins_r.title.char_h_mm,
                                   ins_r.title.vertical)
    ok("右页标题的**轮廓右边缘**距右边界 = 右值（不是落点 x 到纸边）",
       abs((297.0 - (ins_r.title.x_mm + _title_w)) - 14.0) < 1e-6,
       f"轮廓右边距 = {297.0 - (ins_r.title.x_mm + _title_w):.4f}，"
       f"落点 x 到纸边 = {297.0 - ins_r.title.x_mm:.4f}")
    ok("右页落点确实退了一个字宽（否则文字会比设定值多缩一格）",
       abs((297.0 - ins_r.title.x_mm) - (14.0 + _title_w)) < 1e-6,
       f"落点右边距 {297.0 - ins_r.title.x_mm:.4f} vs 右值+字宽 "
       f"{14.0 + _title_w:.4f}")
    ok("左右值不同 → 两侧落点确实不同",
       abs((297.0 - ins_r.title.x_mm) - ins_l.title.x_mm) > 1.0)
    _num_w = text_block_width_mm(ins_r.page_number.text,
                                ins_r.page_number.char_h_mm,
                                ins_r.page_number.vertical)
    ok("页码同样按左右值落点（左取轮廓左缘、右取轮廓右缘）",
       abs(ins_l.page_number.x_mm - 10.0) < 1e-6
       and abs((297.0 - (ins_r.page_number.x_mm + _num_w)) - 14.0) < 1e-6,
       f"右页页码轮廓右边距 = "
       f"{297.0 - (ins_r.page_number.x_mm + _num_w):.4f}")
    ok("position=top → 距上边界 = 上值",
       abs(ins_l.title.y_start_mm - 2.0) < 1e-6, str(ins_l.title.y_start_mm))

    # 页码在底部：文字块底边距下边界 = 下值
    num_char_h = 12.0 / POINTS_PER_MM
    num_block_bottom = ins_l.page_number.y_start_mm + len("第一頁") * num_char_h
    ok("页码在底部 → 距下边界 = 下值",
       abs((210.0 - num_block_bottom) - 2.0) < 1e-6,
       str(210.0 - num_block_bottom))

    # ⚠️ 契约（用户明确要求）：填了「距页边」**不再收窄图片让位**——用户填的
    # 是"文字离纸边多远"，就按这个距离画，**允许文字压在图片上**。
    # 图片左右始终只留固定的 TEXT_MARGIN_MM（未配置时竖排文字/页码的落点，
    # 也是老任务输出的既定几何）。
    title_char_h = 18.0 / POINTS_PER_MM

    # 先验"用户要的结果"：宽图（横向铺满可用宽度）+ 距左 30mm → 文字确实落在
    # 图片范围内，而且仍在用户设的距离上（没被"自动避让"顶到图片外）
    wide_full = dict(full, title_margins=[2, 2, 2, 30])
    overlap = plan_print_page((2400, 800), wide_full, 0, 2)
    ok("距左调大 → 文字按用户设的距离落点",
       abs(overlap.title.x_mm - 30.0) < 1e-6, str(overlap.title.x_mm))
    ok("文字允许压在图片上（不再自动避让到图片外）",
       overlap.title.x_mm > overlap.image[0]
       and overlap.title.x_mm + title_char_h
       < overlap.image[0] + overlap.image[2],
       f"文字 {overlap.title.x_mm:.2f}~{overlap.title.x_mm + title_char_h:.2f}，"
       f"图片 {overlap.image[0]:.2f}~"
       f"{overlap.image[0] + overlap.image[2]:.2f}")

    # 再验"图片没被收窄"：填了距页边与没填时几何完全相同
    ok("填了距页边 → 图片大小与未配置时完全一致",
       abs(ins_l.image[0] - legacy_l.image[0]) < 1e-6
       and abs(ins_l.image[2] - legacy_l.image[2]) < 1e-6
       and abs(ins_l.image[3] - legacy_l.image[3]) < 1e-6,
       f"x/w {ins_l.image[0]:.2f}/{ins_l.image[2]:.2f} vs "
       f"{legacy_l.image[0]:.2f}/{legacy_l.image[2]:.2f}")
    ok("图片左右只留固定的 TEXT_MARGIN_MM",
       abs(ins_l.text_reserve_mm - TEXT_MARGIN_MM) < 1e-6,
       str(ins_l.text_reserve_mm))
    ok("距页边改大也不影响图片大小",
       abs(overlap.image[2]
           - plan_print_page((2400, 800), full, 0, 2).image[2]) < 1e-6)

    # ---- 4. skip_pages ----
    skipped = plan_print_page(
        (800, 1200), dict(full, skip_pages=["2"]), 1, 3, image_name="0002"
    )
    ok("命中 skip_pages 的页标记 skipped", skipped.skipped)
    ok("未命中的页不标记 skipped",
       not plan_print_page(
           (800, 1200), dict(full, skip_pages=["2"]), 2, 3, image_name="0003"
       ).skipped)
    ok("带侧别的写法按页名回查",
       plan_print_page(
           (800, 1200), dict(full, skip_pages=["2-r"]), 1, 3, image_name="0002-r"
       ).skipped)

    # ---- 5. 与成品 PDF 逐值比对（预览几何 == PDF 几何）----
    import pymupdf

    from functions.print import PrintFunction

    img_dir = tmp / "imgs"
    img_dir.mkdir(parents=True, exist_ok=True)
    _tmp_png(img_dir / "0001.png", 800, 1200)
    # 第二张：第 5b 节要验**右页**（第 2 页）的文字轮廓右边距，必须有 2 页
    _tmp_png(img_dir / "0002.png", 800, 1200)

    pdf_args = {
        # 与 CommandArgs 一致：input/output 必须是 Path，不是字符串
        "input": img_dir,
        "output": tmp / "out",
        "pdf_name": "parity.pdf",
        "paper_size": "A4",
        "orientation": "landscape",
        "page_margins": "15,10,20,10",
        "title_printing": False,
        "page_number_printing": False,
        "workers": 1,
    }
    PrintFunction(dict(pdf_args)).execute()
    pdf_path = tmp / "out" / "parity.pdf"
    ok("测试 PDF 已生成", pdf_path.exists(), str(pdf_path))

    expect = plan_print_page(
        (800, 1200),
        {
            "paper_size": "A4", "orientation": "landscape",
            "page_margins": [15.0, 10.0, 20.0, 10.0],
        },
        0,
        1,
    )
    doc = pymupdf.open(str(pdf_path))
    try:
        info = doc[0].get_image_info()[0]
        bx0, by0, bx1, by1 = info["bbox"]
        pt_per_mm = 72.0 / 25.4
        ex, ey, ew, eh = expect.image
        ok("PDF 中图片落点与预览几何一致（≤1.5pt）",
           abs(bx0 - ex * pt_per_mm) < 1.5
           and abs(by0 - ey * pt_per_mm) < 1.5
           and abs((bx1 - bx0) - ew * pt_per_mm) < 1.5
           and abs((by1 - by0) - eh * pt_per_mm) < 1.5,
           f"pdf={tuple(round(v, 2) for v in (bx0, by0, bx1, by1))} "
           f"plan={tuple(round(v * pt_per_mm, 2) for v in expect.image)}")
        ok("PDF 页尺寸与预览纸张一致",
           abs(doc[0].rect.width - expect.page_w_mm * pt_per_mm) < 1.0
           and abs(doc[0].rect.height - expect.page_h_mm * pt_per_mm) < 1.0,
           f"{doc[0].rect.width:.1f}x{doc[0].rect.height:.1f}")
    finally:
        doc.close()

    # ---- 5b. 带「距页边」时，成品 PDF 与预览仍逐值一致 ----
    # 这一条是防止 functions/print.py 偷偷抄一份公式：抄了就会漂移
    inset_pdf_args = dict(pdf_args, pdf_name="parity_inset.pdf")
    inset_pdf_args.update({
        "title_printing": True, "title_text": "测试古籍",
        "title_font_size": 18, "title_position": "top",
        "title_orientation": "vertical",
        "page_number_printing": True, "page_number_font_size": 12,
        "title_margins": "2,14,2,10", "page_number_margins": "2,14,2,10",
    })
    PrintFunction(dict(inset_pdf_args)).execute()
    pdf_path2 = tmp / "out" / "parity_inset.pdf"
    ok("带距页边的 PDF 已生成", pdf_path2.exists(), str(pdf_path2))

    expect2 = plan_print_page(
        (800, 1200),
        {
            "paper_size": "A4", "orientation": "landscape",
            "page_margins": [15.0, 10.0, 20.0, 10.0],
            "title_printing": True, "title_text": "测试古籍",
            "title_font_size": 18, "title_position": "top",
            "title_orientation": "vertical",
            "page_number_printing": True, "page_number_font_size": 12,
            "title_margins": [2, 14, 2, 10],
            "page_number_margins": [2, 14, 2, 10],
        },
        0,
        1,
    )
    doc2 = pymupdf.open(str(pdf_path2))
    try:
        info2 = doc2[0].get_image_info()[0]
        bx0, by0, bx1, by1 = info2["bbox"]
        pt_per_mm = 72.0 / 25.4
        ex, ey, ew, eh = expect2.image
        ok("带距页边时 PDF 图片落点仍与预览一致（≤1.5pt）",
           abs(bx0 - ex * pt_per_mm) < 1.5
           and abs(by0 - ey * pt_per_mm) < 1.5
           and abs((bx1 - bx0) - ew * pt_per_mm) < 1.5
           and abs((by1 - by0) - eh * pt_per_mm) < 1.5,
           f"pdf={tuple(round(v, 2) for v in (bx0, by0, bx1, by1))} "
           f"plan={tuple(round(v * pt_per_mm, 2) for v in expect2.image)}")

        # ⚠️ 右页（第 2 页）的**文字轮廓右边缘**——本轮核心契约的端到端验收。
        # 用户填「右 14mm」时，成品 PDF 里的标题/页码轮廓右边必须离纸右边
        # 14mm（±1.5pt），而不是 14mm + 一个字宽。
        #
        # 这条与上面「右页标题的轮廓右边缘」那条**层次不同**：上面读的是
        # `plan_print_page` 算出的值（几何真源），这条读的是**成品 PDF 里的
        # 真实字形 bbox**（PyMuPDF 反向解析）。它防的是「print.py 抄了第二份
        # 公式」——预览侧算对、fpdf 那边少退一个块宽，只有这条会露馅。
        # 注：注入「去掉 - block_w」时它不会红，因为几何真源一改、上游断言
        # 先失败、模块提前中止；这不是它失效，而是分层防御的正常表现。
        expect2_r = plan_print_page(
            (800, 1200),
            {
                "paper_size": "A4", "orientation": "landscape",
                "page_margins": [15.0, 10.0, 20.0, 10.0],
                "title_printing": True, "title_text": "测试古籍",
                "title_font_size": 18, "title_position": "top",
                "title_orientation": "vertical",
                "page_number_printing": True, "page_number_font_size": 12,
                "title_margins": [2, 14, 2, 10],
                "page_number_margins": [2, 14, 2, 10],
            },
            1,
            2,
        )
        ok("（前置）该页确实是右页", expect2_r.side == "right", expect2_r.side)
        page2 = doc2[1]
        page_w_pt = page2.rect.width
        # 用 get_text 的字形 bbox 取整串轮廓：竖排文字逐字落在同一列，
        # 取所有字符 x1 的最大值即轮廓右边。
        _chars = [
            ch
            for block in page2.get_text("rawdict")["blocks"]
            if block.get("type") == 0
            for line in block["lines"]
            for span in line["spans"]
            for ch in span["chars"]
        ]
        ok("右页能读回文字（否则断言无意义）", bool(_chars), str(len(_chars)))
        if _chars:
            right_edge_pt = max(ch["bbox"][2] for ch in _chars)
            right_gap_mm = (page_w_pt - right_edge_pt) / pt_per_mm
            ok("右页文字轮廓右边距右纸边 = 14mm（±1.5pt）",
               abs(right_gap_mm - 14.0) < 1.5,
               f"实测 {right_gap_mm:.2f}mm（若为 14+字宽 ≈ 20.3mm 说明漏退块宽）")
    finally:
        doc2.close()

    # ---- 6. 效果合成只画内存，不落盘 ----
    from PySide6.QtGui import QImage

    source = _tmp_png(tmp / "src.png", 800, 1200)
    src_img = QImage(str(source))
    pdf_count_before = len(list(tmp.rglob("*.pdf")))
    before = sorted(str(p) for p in tmp.rglob("*"))
    page_img = compose_print_page(src_img, expect)
    sk_img = compose_print_page(src_img, skipped)
    after = sorted(str(p) for p in tmp.rglob("*"))
    ok("效果预览不写出任何文件", before == after,
       str(sorted(set(after) - set(before))))
    ok("效果预览不生成 PDF",
       len(list(tmp.rglob("*.pdf"))) == pdf_count_before,
       str([p.name for p in tmp.rglob("*.pdf")]))
    ok("效果位图尺寸按纸张比例",
       page_img.width() == round(
           expect.page_w_mm * preview_px_per_mm(
               expect.page_w_mm, expect.page_h_mm)
       )
       and page_img.width() > page_img.height(),
       f"{page_img.width()}x{page_img.height()}")
    ok("跳过页画出的是留白提示页（与正常页不同）",
       sk_img.size() == page_img.size()
       and sk_img.pixelColor(2, 2) != page_img.pixelColor(2, 2))

    # ---- 7. 控件结构：左缩略图 + 右效果 ----
    widget = PrintPreviewWidget(params_provider=lambda: dict(full))
    try:
        ok("左缩略图条 + 右大图，且 list 是 strip 的兼容别名",
           isinstance(widget.strip, ThumbStrip)
           and widget.list is widget.strip
           and widget.view is not None)
        ok("第四步缩略图条可拖动排序，通用 ThumbStrip 默认不可拖动",
           widget.strip.dragDropMode()
           == QAbstractItemView.DragDropMode.InternalMove
           and ThumbStrip().dragDropMode()
           == QAbstractItemView.DragDropMode.NoDragDrop)
        ok("默认停在「版面编辑」（可拖拽/缩放的画布）",
           widget._mode == "layout" and widget.canvas is not None)
        # 「打印效果」「原图」仍是同一控件上的另两个视图，可随时切回
        ok("三视图齐备：版面编辑 / 打印效果 / 原图",
           widget.toggle.current() == "layout"
           and widget.toggle.is_item_enabled("effect")
           and widget.toggle.is_item_enabled("original"))

        png_a = _tmp_png(tmp / "0001.png", 800, 1200)
        png_b = _tmp_png(tmp / "0002.png", 900, 1300)
        widget.set_entries([
            {"file": str(png_a), "label": "0001"},
            {"file": str(png_b), "label": "0002"},
        ])
        ok("左侧缩略图条按条目建项", widget.strip.count() == 2)
        ok("count() 与 entries() 一致",
           widget.count() == 2
           and [Path(e["file"]).stem for e in widget.entries()]
           == ["0001", "0002"])

        # 版面编辑：默认用「当前参数自动排版出的框」初始化，用户再微调
        _rect0 = widget.canvas.current_rect()
        ok("版面编辑初始框来自自动排版（在页面内且非空）",
           len(_rect0) == 4 and _rect0[2] > 0 and _rect0[3] > 0
           and _rect0[0] >= 0 and _rect0[1] >= 0, str(_rect0))

        # 切到「打印效果」看整页效果（含标题/页码），与后续断言保持一致
        widget._set_mode("effect")
        first = _wait_new_image(widget, app, None)
        ok("效果预览已渲染", first is not None and first.width() > 0)
        ok("效果页是横版（A4 landscape）", first.width() > first.height(),
           f"{first.width()}x{first.height()}")
        ok("说明行明确「不会生成 PDF」",
           "不会生成 PDF" in widget.caption.text(), widget.caption.text())

        # 切竖版 → 纸张变化必须反映到预览
        widget._params_provider = lambda: dict(full, orientation="portrait")
        widget.refresh_display()
        second = _wait_new_image(widget, app, (first.width(), first.height()))
        ok("改成竖版后效果页随之变竖",
           second is not None and second.height() > second.width(),
           f"{second.width()}x{second.height()}")

        # 切「原图」→ 显示图片本身（比例 = 图片自身比例）
        widget._params_provider = lambda: dict(full)
        widget._set_mode("original")
        third = _wait_new_image(widget, app, (second.width(), second.height()))
        ok("「原图」显示图片本身（不再是纸张比例）",
           third is not None
           and abs(third.height() / third.width() - 1200 / 800) < 0.02,
           f"{third.width()}x{third.height()}")

        # 参数非法 → 退回原图并给出原因，不弹窗不抛异常
        def _bad_params():
            raise ValueError("颜色格式应为 r,g,b")

        widget._params_provider = _bad_params
        widget._set_mode("effect")
        widget.refresh_display()
        pump(app, 4)
        ok("参数非法时不抛异常，说明行给出原因",
           "参数暂不合法" in widget.caption.text(), widget.caption.text())

        # 拖动排序：QListWidget 的 model 不支持编程式 moveRow（返回 False），
        # 真实拖放只能人工验证；这里用 Qt 内部拖放的等价动作
        # （takeItem + insertItem）走同一条 rowsMoved → 同步链路。
        seen = []
        widget._params_provider = lambda: dict(full)
        widget.order_changed.connect(lambda: seen.append(1))
        moved = widget.strip.takeItem(1)
        widget.strip.insertItem(0, moved)
        widget._on_strip_order_changed()
        pump(app, 2)
        ok("顺序变化后 order_changed 已发出", bool(seen), str(seen))
        ok("顺序变化后 entries() 同步",
           [Path(e["file"]).stem for e in widget.entries()] == ["0002", "0001"],
           str([Path(e["file"]).stem for e in widget.entries()]))
        ok("缩略图条文字顺序也同步",
           [widget.strip.item(i).text() for i in range(widget.strip.count())]
           == ["0002", "0001"],
           str([widget.strip.item(i).text() for i in range(widget.strip.count())]))

        # 删除选中
        widget.strip.item(0).setSelected(True)
        widget.remove_selected()
        ok("删除后列表与缓存同步",
           widget.strip.count() == 1 and widget.count() == 1)
        ok("未选中时给出提示而不是静默",
           _hint_of(widget) == "请先在左侧缩略图条选中要删除的图片。")
    finally:
        widget.deleteLater()

    # 顺序变化的转发开关：前三步的页序由数据层决定，不该被拖动打乱
    plain_strip = ThumbStrip()
    forwarded: list[int] = []
    plain_strip.order_changed.connect(lambda: forwarded.append(1))
    plain_strip._on_rows_moved()
    plain_strip.set_reorderable(True)
    plain_strip._on_rows_moved()
    try:
        ok("ThumbStrip 仅在可排序时转发顺序变化",
           forwarded == [1], str(forwarded))
    finally:
        plain_strip.deleteLater()

    # ---- 7b. 面板接线：标题/页码「距页边」（勾选框 + 两行通栏输入框）----
    # 早先是一个「上,右,下,左」文本框：四个数字挤一行，用户没法确认哪个是哪个。
    # 用户最终指定的形态：**就两行，每行一个通栏输入框**——
    #   第一行「左右边距：」一个框（横向那份距离，左页贴左纸边、右页贴右纸边）
    #   第二行「上边距：」/「下边距：」一个框（纵向那份距离）
    from desktop.components.panels.print_panel import PrintPanel
    from PySide6.QtWidgets import QFormLayout

    panel = PrintPanel()
    try:
        sides = [key for key, _label in panel.INSET_SIDES]
        ok("距页边的四个方向顺序固定为 上,右,下,左",
           sides == ["top", "right", "bottom", "left"], str(sides))

        # ⚠️ 核心契约：每段**恰好两行**，横向那行**只有一个框**
        for which, name, cross_key, cross_label, absent in (
            ("title", "标题", "top", "上边距", "bottom"),
            ("page_number", "页码", "bottom", "下边距", "top"),
        ):
            blk = panel._inset_block(which)
            widgets = blk["widgets"]
            ok(f"{name}距页边恰好两行（左右边距 + {cross_label}）",
               set(widgets) == {"side", "cross"}, str(sorted(widgets)))
            ok(f"{name}横向那行只有一个框（左页右页共用一个值）",
               widgets["side"].value() == blk["spins"]["left"].value() ==
               blk["spins"]["right"].value(),
               f"side={widgets['side'].value()} "
               f"left={blk['spins']['left'].value()} "
               f"right={blk['spins']['right'].value()}")
            ok(f"{name}横向框的 left/right 是**同一个控件对象**"
               f"（不是两个框凑出来的）",
               blk["spins"]["left"] is blk["spins"]["right"]
               and blk["spins"]["left"] is widgets["side"])
            ok(f"{name}纵向那行就是 {cross_label}（{cross_key}）",
               blk["spins"][cross_key] is widgets["cross"], str(sorted(blk["spins"])))
            ok(f"{name}不再露用不到的「{'下' if absent == 'bottom' else '上'}边距」框",
               absent not in blk["spins"], str(sorted(blk["spins"])))

        # ⚠️ 「距页边」的默认值**只有两处输入**（用户指定）：
        #   - 横向：左右各 10mm；
        #   - 纵向：跟随 page_margins —— 标题的「上」= page_margins[0]、
        #     页码的「下」= page_margins[2]，文字与图片**贴同一条边**。
        # 桌面端打开就该是一份明确的配置，而不是「沿用 CLI 时代 left/2、
        # right-6 那套猜出来的老行为」；显式写 null 才回落到那套老行为。
        from core.command_spec import DEFAULT_PAGE_MARGINS, TEXT_SIDE_MARGIN_MM

        for which, name, cross_expect in (
            ("title", "标题", float(DEFAULT_PAGE_MARGINS[0])),
            ("page_number", "页码", float(DEFAULT_PAGE_MARGINS[2])),
        ):
            block = panel._inset_block(which)
            ok(f"{name}距页边默认已启用：横向 {TEXT_SIDE_MARGIN_MM:g}mm、"
               f"纵向 {cross_expect:g}mm（跟随 page_margins）",
               block["enabled"].isChecked()
               and all(w.isEnabled() for w in block["widgets"].values())
               and block["widgets"]["side"].value() == TEXT_SIDE_MARGIN_MM
               and block["widgets"]["cross"].value() == cross_expect,
               f"勾选={block['enabled'].isChecked()} "
               f"横向={block['widgets']['side'].value()} "
               f"纵向={block['widgets']['cross'].value()}")
        # ⚠️ 导出的仍是**四元素** [上,右,下,左]，但界面只摆用得上的那个纵向
        # 分量：标题不摆「下」→ 补 0，页码不摆「上」→ 补 0（底层永远读不到，
        # 见 utils.page_layout 的 `_text_anchor`）。所以落到参数里是
        # [top,10,0,10] / [0,10,bottom,10]，不是四个一样的数
        # ——这是个容易写错断言的地方（曾经写成四个 10）。
        ok("默认导出：横向 10mm、纵向跟随 page_margins，缺席分量恒 0",
           panel.get_args().get("title_margins")
           == [float(DEFAULT_PAGE_MARGINS[0]), 10.0, 0.0, 10.0]
           and panel.get_args().get("page_number_margins")
           == [0.0, 10.0, float(DEFAULT_PAGE_MARGINS[2]), 10.0],
           f"{panel.get_args().get('title_margins')} / "
           f"{panel.get_args().get('page_number_margins')}")

        # ---- 启用后取值 ----
        panel.set_inset("title", [2, 14, 2, 10])
        ok("勾选自定义后输入区可用",
           all(w.isEnabled() for w in panel._inset_block("title")["widgets"].values()))
        # ⚠️ 横向只有一个框，回填 [左=10, 右=14] 时取**左页值**：左页贴左纸边、
        # 右页贴右纸边，界面就是一个对称值。（若按 spins 键逐个回填，
        # 后写的 right=14 会覆盖 left=10——曾经真的这样。）
        blk = panel._inset_block("title")
        ok("横向框回填取左页值 10（不被右页值 14 覆盖）",
           blk["widgets"]["side"].value() == 10.0,
           str(blk["widgets"]["side"].value()))
        ok("纵向框回填它真正会用的那个值（标题 = 距上 = 2）",
           blk["widgets"]["cross"].value() == 2.0,
           str(blk["widgets"]["cross"].value()))
        # ⚠️ 参数契约仍是四元素 [上,右,下,左]；界面没摆的那个纵向分量（标题的
        # 「下」/ 页码的「上」）在底层**永远读不到**，导出时补 0——绝不能把框的
        # 显示初值 2.0 混进参数，否则配置里会躺着一个用户看不见的数
        # （旧实现四个框全摆，看不出这个毛病；收成两行以后才暴露）。
        got = panel.get_args().get("title_margins")
        ok("标题导出 [上=2,右=10,下=0,左=10]（横向一个值、缺席的「下」补 0）",
           got == [2.0, 10.0, 0.0, 10.0], str(got))
        hint = panel._inset_block("title")["hint"].text()
        ok("释义行说清横向是一个对称值、且口径是「文字轮廓」边缘",
           "文字轮廓距左右纸边各 10" in hint and "距上 2" in hint, hint)

        # 页码：纵向是「距下」，「上」补 0
        panel.set_inset("page_number", [2, 14, 2, 10])
        got = panel.get_args().get("page_number_margins")
        ok("页码导出 [上=0,右=10,下=2,左=10]（界面缺席的「上」补 0）",
           got == [0.0, 10.0, 2.0, 10.0], str(got))
        ok("页码释义说「距下」",
           "距下 2" in panel._inset_block("page_number")["hint"].text(),
           panel._inset_block("page_number")["hint"].text())

        # ---- 「位置」「文字方向」两个参数已从桌面端删除 ----
        # 用户原话：「既然有位置：上面/下面……动态调整啊，你不会啊，要不然就
        # 取消"位置"和"文字方向"两个参数，默认标题在上面，页码在下面」。
        # 采取后一种：古籍的书名在版框之上、页码在版心之下，都是竖排定式，
        # 摆成下拉只会让人以为可以乱选（而且和「上边距/下边距」两行天然矛盾）。
        for attr in ("title_position", "title_orientation",
                     "page_number_position", "page_number_orientation"):
            ok(f"面板不再有 {attr} 控件",
               not hasattr(panel, attr), f"仍有 {attr}")
        _labels = []
        for _form in panel.findChildren(QFormLayout):
            for _row in range(_form.rowCount()):
                _item = _form.itemAt(_row, QFormLayout.LabelRole)
                if _item is not None and _item.widget() is not None:
                    _labels.append(_item.widget().text())
        ok("表单里不再出现「位置」「文字方向」两行",
           "位置" not in _labels and "文字方向" not in _labels,
           str(_labels))

        # 没历史参数时，导出的是固定的「标题在上、页码在下、两者竖排」
        # ⚠️ 这条断言要真能测到固定表，前提是**面板默认参数表里没有这四个键**：
        # 早先 DEFAULT_PARAMS 还带着它们，`__init__` 一复位就把固定值填进
        # `_fixed_layout_echo`，于是「固定表」这条路径根本没被走到——注入
        # 「把固定表改反」时全绿，守卫形同虚设（实测踩到过）。
        from desktop.components.panels.print_params import DEFAULT_PARAMS

        _stray = sorted(
            k for k in ("title_position", "title_orientation",
                        "page_number_position", "page_number_orientation")
            if k in DEFAULT_PARAMS
        )
        ok("面板默认参数表已不再带「位置/文字方向」（否则固定表形同虚设）",
           not _stray, f"仍存在：{_stray}")

        fresh = panel.get_args()
        ok("未回填历史 → 位置固定为标题 top / 页码 bottom",
           fresh.get("title_position") == "top"
           and fresh.get("page_number_position") == "bottom",
           f"{fresh.get('title_position')} / {fresh.get('page_number_position')}")
        ok("未回填历史 → 文字方向固定为两者竖排",
           fresh.get("title_orientation") == "vertical"
           and fresh.get("page_number_orientation") == "vertical",
           f"{fresh.get('title_orientation')} / {fresh.get('page_number_orientation')}")

        # ⚠️ 历史里的非固定值必须**原样保留**：桌面端没给用户改这两个键的
        # 入口，就不能顺手帮他"修正"——老任务存的是 horizontal，进第四步
        # 什么都没动，参数暂存却把它写成 vertical，是最难查的那类漂移。
        panel._apply_args({
            "title_position": "bottom", "title_orientation": "horizontal",
            "page_number_position": "top", "page_number_orientation": "horizontal",
        })
        echo = panel.get_args()
        ok("回填历史后，导出仍原样保留历史的位置/方向（不被固定值改写）",
           (echo.get("title_position"), echo.get("title_orientation"),
            echo.get("page_number_position"),
            echo.get("page_number_orientation"))
           == ("bottom", "horizontal", "top", "horizontal"),
           f"{echo.get('title_position')}/{echo.get('title_orientation')} "
           f"{echo.get('page_number_position')}/{echo.get('page_number_orientation')}")
        # 恢复默认要回到固定值（用户明确说"默认标题在上面，页码在下面"）
        panel.reset_to_default()
        back = panel.get_args()
        ok("恢复默认后回到固定的「标题上/页码下、竖排」",
           (back.get("title_position"), back.get("page_number_position"),
            back.get("title_orientation"), back.get("page_number_orientation"))
           == ("top", "bottom", "vertical", "vertical"),
           f"{back.get('title_position')}/{back.get('page_number_position')}")

        # ---- 距页边的两行不受上述删除影响（纵向键固定：标题距上、页码距下）----
        for which, name, vertical_label in (
            ("title", "标题", "距上"),
            ("page_number", "页码", "距下"),
        ):
            panel._apply_args({f"{which}_margins": [2, 14, 2, 10]})
            widgets = panel._inset_block(which)["widgets"]
            ok(f"{name}参数行仍是固定的两行（左右边距 + {vertical_label[1]}边距）",
               set(widgets) == {"side", "cross"}, str(sorted(widgets)))
            ok(f"{name}释义恒说「{vertical_label}」",
               vertical_label in panel._inset_block(which)["hint"].text(),
               panel._inset_block(which)["hint"].text())
            ok(f"{name}回填后值不丢",
               widgets["side"].value() == 10.0 and widgets["cross"].value() == 2.0,
               f"side={widgets['side'].value()} cross={widgets['cross'].value()}")

        panel._apply_args({"title_margins": [2, 14, 2, 10],
                           "page_number_margins": [2, 14, 2, 10]})

        # ---- 取消启用 / 简写 / 回填 ----
        panel.set_inset("title", None)
        ok("取消勾选后不导出距页边",
           panel.get_args().get("title_margins") is None)
        ok("取消勾选后释义说明回到老行为",
           "老行为" in panel._inset_block("title")["hint"].text(),
           panel._inset_block("title")["hint"].text())
        panel._apply_args({"title_margins": [2, 14, 2, 10]})
        ok("历史参数能回填两个框（横向取左值 10、纵向取距上 2）",
           panel._inset_block("title")["widgets"]["side"].value() == 10.0
           and panel._inset_block("title")["widgets"]["cross"].value() == 2.0,
           str(panel.inset("title")))
        panel._apply_args({"title_margins": [2, 14]})
        ok("简写 [上下,左右] 补全成四值（横向取左值 14）",
           panel.inset("title") == [2.0, 14.0, 0.0, 14.0], str(panel.inset("title")))
        panel._apply_args({"title_margins": None})
        ok("None 回填 → 取消勾选",
           panel.inset("title") is None
           and not panel._inset_block("title")["enabled"].isChecked())

        # ---- 行序与标签（控件先建、行后加，顺序最容易写错，已踩过一次）----
        forms = panel.findChildren(QFormLayout)

        def _find(widget):
            """返回 (所属表单, 行号, 行标签文本)；找不到返回 (None, -1, None)。"""
            for form in forms:
                for row in range(form.rowCount()):
                    for role in (QFormLayout.FieldRole, QFormLayout.LabelRole,
                                 QFormLayout.SpanningRole):
                        item = form.itemAt(row, role)
                        if item is not None and item.widget() is widget:
                            lab = form.itemAt(row, QFormLayout.LabelRole)
                            text = None
                            if lab is not None and lab.widget() is not None:
                                text = lab.widget().text()
                            return form, row, text
            return None, -1, None

        block = panel._inset_block("title")
        form_s, row_side, lab_side = _find(block["widgets"]["side"])
        _, row_cross, lab_cross = _find(block["widgets"]["cross"])
        # 「位置」「文字方向」两行已删除，行序改以「距页边」勾选框为基准
        # （它就在两行参数之前，且是能直接查到的控件；`title_font_size` 包在
        #  `_spin_with_unit` 的盒子里，`_find` 查不到）
        form_h, row_hint, _ = _find(block["hint"])
        _, row_check, _ = _find(block["enabled"])
        ok("「距页边」两行排在标题参数之后（没跑到字体大小前面）",
           row_side > row_check > -1 and form_s is not None,
           f"距页边@{row_side} 勾选框@{row_check}")
        # ⚠️ 先断言「分两行」再断言行标签：把两行挤回同一行时，后加的那行
        # 会把控件从原行**搬走**、原行标签变成空——若先测标签，报出来的是
        # 「标签是 None」，掩盖了「挤成一行」这个真实语义（已踩）。
        ok("两行是**分开的两行**（不是挤在一行里）",
           row_cross == row_side + 1, f"左右@{row_side} 纵向@{row_cross}")
        ok("行标签就是「左右边距：」/「上边距：」（用户指定的叫法，带冒号）",
           lab_side == "左右边距：" and lab_cross == "上边距：",
           f"{lab_side!r} / {lab_cross!r}")
        ok("页码那块纵向标签是「下边距：」",
           _find(panel._inset_block("page_number")["widgets"]["cross"])[2]
           == "下边距：",
           str(_find(panel._inset_block("page_number")["widgets"]["cross"])[2]))
        ok("勾选框 → 左右边距 → 上边距 → 释义行，顺序正确且同区",
           row_check + 1 == row_side and form_h is form_s
           and row_hint == row_cross + 1,
           f"勾选@{row_check} 左右@{row_side} 纵向@{row_cross} 释义@{row_hint}")

        # 输入框要**通栏**（与「古籍名称」等输入框同宽），不是一排小格子。
        # ⚠️ 判据用布局跑完后的 width()：这里已 show + processEvents，
        # QFormLayout 会把字段列拉到整行宽（未布局时读到的是脏值，已踩）。
        panel.resize(340, 900)  # 参数卡片的最窄宽度
        app.processEvents()
        pump(app, 4)
        for which, name in (("title", "标题"), ("page_number", "页码")):
            widgets = panel._inset_block(which)["widgets"]
            for key, label in (("side", "左右边距"), ("cross", "上/下边距")):
                box = widgets[key]
                ok(f"{name}「{label}」输入框是通栏宽（≥ 面板宽 - 标签列 - 余量）",
                   box.width() >= panel.width() - 100,
                   f"宽 {box.width()}px，面板 {panel.width()}px")
            # 且不存在"一排多个框"的残留：横向只有 1 个框
            ok(f"{name}横向那一行没有第二个输入框",
               len({id(s) for s in (widgets["side"],)}) == 1)
    finally:
        panel.deleteLater()

    # ---- 8. 缩略图来源：条目自带 thumb / provider / 原图 ----
    widget2 = PrintPreviewWidget()
    try:
        entry = {"file": str(png_a), "label": "0001"}
        ok("无 thumb/provider 时直接用条目图片",
           widget2._thumb_path_for(entry) == Path(str(png_a)))
        ok("条目自带 thumb 优先",
           widget2._thumb_path_for(dict(entry, thumb={"path": str(png_b)}))
           == Path(str(png_b)))
        widget2._thumb_provider = lambda _p: str(png_b)
        ok("provider 作为次选",
           widget2._thumb_path_for(entry) == Path(str(png_b)))
        widget2._thumb_provider = lambda _p: None
        ok("provider 返回 None 时回退条目图片",
           widget2._thumb_path_for(entry) == Path(str(png_a)))
    finally:
        widget2.deleteLater()

    # ---- 8b. 预览字体：不能是裸 QFont() 的 generic 族 ----
    # 裸 QFont() 在离屏/缺字体环境落到 "Sans Serif" 且无字体库，中文会画成
    # 空心方框（标题/页码是中文竖排，画不出字等于功能缺失）。
    from PySide6.QtGui import QFontDatabase

    from desktop.workers.preview_worker import _pick_preview_font

    fam = _pick_preview_font(18).family()
    generic = {"", "Sans Serif", "Serif", "Monospace", "Cursive", "Fantasy"}
    available = set(QFontDatabase.families())
    chosen_ok = fam not in generic or not available
    ok("预览字体优先选中文字体，而非 generic 兜底",
       chosen_ok, f"family={fam!r} 可用族={sorted(available)[:5]}")

    # ---- 8b'. PDF 内容（标题/页码）字体必须**仿宋优先** ----
    # 必须与 PDF 侧 register_fonts 按**文件路径**取到的 simfang.ttf 对齐；
    # 若沿用界面候选（Windows 上雅黑打头），就会出现"预览是雅黑、导出是仿宋"，
    # 所见即所得直接破掉。两份候选用途不同，不许合并。
    from desktop.workers.preview_worker import _pick_content_font
    from utils.fonts import cjk_font_families, content_font_families

    first_content = content_font_families()[0]
    ok("内容字体候选以仿宋/衬线打头",
       first_content in ("FangSong", "Noto Serif CJK SC", "Songti SC"),
       f"{content_font_families()[:3]}")
    ok("内容候选与界面候选是两份独立列表（防被合并）",
       tuple(content_font_families()) != tuple(cjk_font_families()),
       f"内容 {content_font_families()[:2]} / 界面 {cjk_font_families()[:2]}")
    # 本机装了仿宋时，内容字体必须真的挑到它（离屏环境无字体库时跳过）
    if available:
        content_fam = _pick_content_font(18).family()
        ok("内容字体实际挑到仿宋", content_fam in ("FangSong", "FangSong_GB2312", "SimFang"),
           f"family={content_fam!r}")

    # ---- 8c. 竖排里的拉丁字符：整段旋转 90°，不拆成"每字母一格" ----
    # 竖排惯例：汉字等宽字符一字一格；`Happiness` 这类 ASCII 段整体旋转 90°
    # （读起来是自上而下的一个竖条）。拆成九格会挤成一条竖线且认不出来。
    from desktop.workers.preview_worker import _draw_print_text
    from utils.page_layout import (
        PrintTextSpec, vertical_advance_mm, vertical_extent_mm, vertical_runs,
    )

    ok("竖排分段：汉字一格一格、英文整段",
       vertical_runs("呵呵Happiness") == [("呵呵", False), ("Happiness", True)],
       str(vertical_runs("呵呵Happiness")))
    ok("竖排分段：数字/半角符号也归入旋转段",
       vertical_runs("第1頁A") == [("第", False), ("1", True), ("頁", False),
                                   ("A", True)],
       str(vertical_runs("第1頁A")))
    ok("纯汉字串不产生旋转段",
       all(not rotated for _chunk, rotated in vertical_runs("龍譚精舍叢刻")))
    # 高度：汉字 1 格，拉丁段按字宽估算（0.55 格/字符）
    ok("竖排高度：拉丁段不再按「每字母一格」计",
       abs(vertical_extent_mm("呵呵Happiness", 1.0)
           - (2 + 9 * 0.55)) < 1e-6,
       str(vertical_extent_mm("呵呵Happiness", 1.0)))
    ok("纯汉字的竖排高度 = 字数 × 字高",
       abs(vertical_extent_mm("呵呵呵", 2.0) - 6.0) < 1e-6)
    ok("旋转段推进 = 字符数 × 0.55 格",
       abs(vertical_advance_mm("Happiness", 1.0, True) - 4.95) < 1e-6)

    # ---- 8c-2. 绘制端步进：旋转段用渲染端实测宽度 ----
    # LATIN_ADVANCE_RATIO(0.55) 只是占位估算；数字/下划线长段实际 ≈0.5 字宽，
    # 按 0.55 步进会在旋转段与后续汉字之间留出一条空隙（实测 bug：
    # 「Harvard_drs_435580539_龍譚…」英文段后多出约 1 字高的空白）。
    from utils.page_layout import vertical_chunk_advance_mm

    ok("绘制步进：旋转段优先用渲染端实测宽度",
       abs(vertical_chunk_advance_mm("1234", 1.0, True, 2.0) - 2.0) < 1e-6,
       str(vertical_chunk_advance_mm("1234", 1.0, True, 2.0)))
    ok("绘制步进：实测缺失时回落到 0.55 估算",
       abs(vertical_chunk_advance_mm("1234", 1.0, True, None) - 2.2) < 1e-6,
       str(vertical_chunk_advance_mm("1234", 1.0, True, None)))
    ok("绘制步进：汉字段仍是一字一格（忽略实测值）",
       abs(vertical_chunk_advance_mm("呵呵", 2.0, False, 99.0) - 4.0) < 1e-6)

    # 绘制契约（确定性）：用假 painter 记录"画了哪些串、有没有旋转"
    class _SpyPainter:
        """只记录调用的假 painter（不真画），用于断言排版动作。"""

        def __init__(self):
            self.calls: list = []

        def setFont(self, font):
            # _draw_print_text 取 painter.font() 做 QFontMetrics（旋转段实测
            # 步进），spy 必须把字体存下来。⚠️ 存 `_font`——存 `font` 会把
            # 下面的 font() 方法遮蔽成 QFont 实例属性（QFont 不可调用）。
            self._font = font

        def font(self):
            return self._font

        def setPen(self, *_a):
            pass

        def save(self):
            self.calls.append(("save",))

        def restore(self):
            self.calls.append(("restore",))

        def translate(self, x, y):
            self.calls.append(("translate", round(float(x), 2), round(float(y), 2)))

        def rotate(self, deg):
            self.calls.append(("rotate", float(deg)))

        def drawText(self, _point, text):
            self.calls.append(("text", str(text)))

    spec = PrintTextSpec(
        text="呵呵Happiness", x_mm=10.0, y_start_mm=10.0, char_h_mm=8.0,
        vertical=True, font_size_pt=24.0, color=(0, 0, 0),
    )
    spy = _SpyPainter()
    _draw_print_text(spy, spec, 1.0)
    texts = [call[1] for call in spy.calls if call[0] == "text"]
    ok("预览：英文整段一次画完（不是每个字母一次）",
       texts == ["呵", "呵", "Happiness"], str(texts))
    ok("预览：英文段外面套了 旋转 90° 的 save/restore",
       ("save",) in spy.calls and ("restore",) in spy.calls
       and ("rotate", 90.0) in spy.calls,
       str([c for c in spy.calls if c[0] in ("save", "restore", "rotate")]))
    ok("预览：汉字不旋转",
       len([c for c in spy.calls if c[0] == "rotate"]) == 1,
       str([c for c in spy.calls if c[0] == "rotate"]))

    # 成品 PDF 侧：拉丁段读回来必须是**一个**文本块（拆成九格会变成九行）
    mixed_args = dict(pdf_args, pdf_name="vertical_mixed.pdf")
    mixed_args.update({
        "title_printing": True, "title_text": "呵呵Happiness",
        "title_font_size": 24, "title_position": "top",
        "title_orientation": "vertical",
        "page_number_printing": False,
    })
    PrintFunction(dict(mixed_args)).execute()
    mixed_pdf = tmp / "out" / "vertical_mixed.pdf"
    ok("混排标题的 PDF 已生成", mixed_pdf.exists(), str(mixed_pdf))
    doc3 = pymupdf.open(str(mixed_pdf))
    try:
        # 逐行取：既能看"分成几行"，也能看每行的书写方向（dir）
        lines = [
            line
            for block in doc3[0].get_text("rawdict")["blocks"]
            if block.get("type") == 0
            for line in block["lines"]
        ]

        def _line_text(line) -> str:
            return "".join(
                ch["c"] for span in line["spans"] for ch in span["chars"]
            )

        # ⚠️ 只断言"拉丁段占一行"、"总行数很少"：逐字母排版会变成 9+ 行。
        # 不要断言字串长度——PyMuPDF 对旋转文本的抽取有损耗（末尾字可能丢），
        # 拿长度当判据会把"方向写反"误报成"被拆成一格一格"（已踩）。
        latin_lines = [ln for ln in lines if "Happi" in _line_text(ln)]
        ok("PDF：拉丁段是一整行（不是每字母一行）",
           len(latin_lines) == 1 and len(lines) <= 4,
           str([_line_text(ln) for ln in lines]))
        if latin_lines:
            line = latin_lines[0]
            ok("PDF：拉丁段自上而下排（书写方向 = 向下）",
               tuple(round(float(v), 3) for v in line["dir"]) == (0.0, 1.0),
               str(line["dir"]))
            ys = [
                ch["bbox"][1]
                for span in line["spans"] for ch in span["chars"]
            ]
            ok("PDF：首字母在最上、末字母在最下（顺着往下读）",
               ys == sorted(ys) and ys[-1] > ys[0],
               f"{[round(y, 1) for y in ys[:3]]} … {round(ys[-1], 1)}")
            bw = line["bbox"][2] - line["bbox"][0]
            bh = line["bbox"][3] - line["bbox"][1]
            ok("PDF：拉丁段是旋转 90° 的竖条（高 ≫ 宽）",
               bh > bw * 2, f"{bw:.1f}x{bh:.1f}pt")
        cjk_lines = [ln for ln in lines if "呵" in _line_text(ln)]
        ok("PDF：汉字仍是一字一格（各自成行）",
           len(cjk_lines) == 2, str([_line_text(ln) for ln in lines]))
    finally:
        doc3.close()

    # ---- 9. 密度与缩略图尺寸 ----
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QIcon, QImage, QPixmap

    ok("效果预览密度有上下限（不会为超大纸分配巨图）",
       2.0 <= preview_px_per_mm(297, 210) <= 8.0
       and preview_px_per_mm(2000, 2000) == 2.0,
       str(preview_px_per_mm(297, 210)))

    # 解码边必须按**图标框的长边**取。ImageListWorker 的 edge 是"最长边"语义，
    # 竖开本古籍页受高度约束：取框宽（旧实现 96）时，1600x2800 的页面解码成
    # 55x96，缩略图只占条目宽度的一半（用户反馈「缩略图占用宽度太小」）。
    ok("缩略图解码边长取 ThumbStrip 的框长边（不是框宽）",
       PrintPreviewWidget.THUMB_EDGE == ThumbStrip.DECODE_EDGE
       and ThumbStrip.DECODE_EDGE
       == max(ThumbStrip.ICON_SIZE.width(), ThumbStrip.ICON_SIZE.height()),
       f"{PrintPreviewWidget.THUMB_EDGE}")

    # 契约：竖开本页面（宽高比 0.578，实测自《龍譚精舍叢刻》）的缩略图，
    # 必须占条目宽度的 60% 以上——否则就是"框没吃满宽度"的回归。
    portrait = _tmp_png(tmp / "portrait.png", 1156, 2000)  # ratio 0.578
    decoded = QImage(str(portrait)).scaled(
        ThumbStrip.DECODE_EDGE, ThumbStrip.DECODE_EDGE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    shown = QIcon(QPixmap.fromImage(decoded)).pixmap(
        QSize(ThumbStrip.ICON_SIZE)
    )
    ratio = shown.width() / max(ThumbStrip.GRID_SIZE.width(), 1)
    ok("竖开本页面的缩略图占条目宽度 ≥60%（不再只有一半）",
       ratio >= 0.6, f"{shown.width()}/{ThumbStrip.GRID_SIZE.width()}={ratio:.0%}")

    # 控件宽度要放得下网格 + 竖向滚动条，否则会多出一条横向滚动条
    ok("缩略图条宽度容得下网格与滚动条",
       ThumbStrip.STRIP_WIDTH >= ThumbStrip.GRID_SIZE.width() + 16,
       f"{ThumbStrip.STRIP_WIDTH} vs {ThumbStrip.GRID_SIZE.width()}")

    # ---- 10. 宿主接线：详情页必须把打印面板参数交给效果预览 ----
    # ⚠️ 这一条是**集成级**断言，不是控件级：组件自测（上面那些）都自带
    # params_provider，测不出「宿主忘了传」。上一版就是这样漏的——界面永远
    # 显示"未接入打印参数，已显示原图"，标题/页码/纸张效果一概看不到。
    detail = ctx.d
    ok("详情页把打印面板参数接给了效果预览",
       getattr(detail.print_preview, "_params_provider", None) is not None,
       "PrintPreviewWidget(params_provider=...) 漏传")
    spec, note = detail.print_preview._print_spec(0, Path("0001.png"))
    ok("宿主提供的参数能直接构成 print_spec（无回退提示）",
       spec is not None and note == "",
       f"spec={spec is not None} note={note!r}")

    ok("详情页效果预览的缩略图条沿用 ThumbStrip 的固定宽度",
       detail.print_preview.strip.width() == ThumbStrip.STRIP_WIDTH,
       str(detail.print_preview.strip.width()))


def _hint_of(widget) -> str:
    """触发一次空选删除，捕获 hint 文案。"""
    messages = []
    widget.hint.connect(messages.append)
    widget.remove_selected()
    return messages[0] if messages else ""
