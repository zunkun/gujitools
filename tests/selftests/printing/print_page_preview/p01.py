# -*- coding: utf-8 -*-
"""1. 纸张/方向 / 2. 图片落点 / 3. 标题与页码 / 3b. 标题/页码「距页边」（左右可不同，允许压在图片上） / 4. skip_pages / 4b. 标题切换节点：预览按 **PDF 页序（列表位置）** 解析（2026-09-29 回归） / 5. 与成品 PDF 逐值比对（预览几何 == PDF 几何） / 5b. 带「距页边」时，成品 PDF 与预览仍逐值一致 / 6. 效果合成只画内存，不落盘"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import _tmp_png, ROOT
    from utils.page_layout import POINTS_PER_MM, text_block_width_mm, text_insets
    from pathlib import Path
    from functions.print import PrintFunction
    from PySide6.QtGui import QColor, QImage, QPainter
    from utils.page_layout import (
        TEXT_INSET_MM, TEXT_MARGIN_MM, TEXT_SIDE_OFFSET_MM,
        plan_print_page, print_page_size_mm,
    )
    from typing import cast
    from desktop.workers.preview_worker import (
        compose_print_page, preview_px_per_mm,
    )
    from tests.selftests._context import module_source_text
    from tests.selftests._context import ok, pump
    import pymupdf
    from utils.page_layout import resolve_title_nodes
    ok("A4 横版 = 297×210mm", print_page_size_mm("A4", "landscape") == (297.0, 210.0))
    ok("A4 竖版 = 210×297mm", print_page_size_mm("A4", "portrait") == (210.0, 297.0))
    ok("fpdf 的 P/L 写法同样认得",
       print_page_size_mm("A4", "L") == (297.0, 210.0)
       and print_page_size_mm("a4", "P") == (210.0, 297.0))
    st.args = {
        "paper_size": "A4", "orientation": "landscape",
        "page_margins": [10.0, 10.0, 10.0, 10.0],
    }
    plan = plan_print_page((800, 1200), st.args, 0, 1)
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
    st.full = dict(st.args)
    st.full.update({
        "title_printing": True, "title_text": "测试古籍",
        "title_font_size": 18, "title_position": "top",
        "title_orientation": "vertical",
        "page_number_printing": True, "page_number_font_size": 12,
        "page_number_base": 0,
    })
    plan2 = plan_print_page((800, 1200), st.full, 2, 5)
    ok("标题按章节前的最后一个节点取值（无节点时用 title_text）",
       plan2.title is not None and plan2.title.text == "测试古籍",
       str(plan2.title))
    ok("页码为「第…頁」且按物理页序 + base",
       plan2.page_number is not None and plan2.page_number.text == "第三頁",
       str(plan2.page_number))
    _title2 = plan2.title
    _pn2 = plan2.page_number
    assert _title2 is not None and _pn2 is not None  # 上两条 ok 已断言二者存在
    ok("标题/页码默认竖排且同侧",
       _title2.vertical and _pn2.vertical
       and plan2.side == "left", str(plan2.side))
    ok("竖排在页边、横排另有基线",
       _title2.baseline_mm is None
       and _title2.x_mm < 10.0, str(_title2.x_mm))

    # 奇偶页边距
    odd_even = dict(st.full)
    odd_even.update({
        "left_page_margins": [5.0, 5.0, 5.0, 30.0],
        "right_page_margins": [5.0, 30.0, 5.0, 5.0],
    })
    left_page = plan_print_page((800, 1200), odd_even, 0, 2)   # 第 1 页（奇）
    right_page = plan_print_page((800, 1200), odd_even, 1, 2)  # 第 2 页（偶）
    ok("奇数页用 left_page_margins、偶数页用 right_page_margins",
       left_page.image[0] > right_page.image[0],
       f"{left_page.image[0]:.2f} vs {right_page.image[0]:.2f}")
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
    legacy_l = plan_print_page((800, 1200), st.full, 0, 2)
    legacy_r = plan_print_page((800, 1200), st.full, 1, 2)
    assert legacy_l.title is not None and legacy_r.title is not None  # full 开了标题
    ok("未配置距页边 → 左页仍是 ml/2",
       abs(legacy_l.title.x_mm - 5.0) < 1e-6, str(legacy_l.title.x_mm))
    ok("未配置距页边 → 右页 = mr - TEXT_SIDE_OFFSET_MM",
       abs((297.0 - legacy_r.title.x_mm) - (10.0 - TEXT_SIDE_OFFSET_MM)) < 1e-6,
       str(297.0 - legacy_r.title.x_mm))
    ok("未配置距页边 → 纵向 = 页边距 + TEXT_INSET_MM",
       abs(legacy_l.title.y_start_mm - (10.0 + TEXT_INSET_MM)) < 1e-6,
       str(legacy_l.title.y_start_mm))

    # 配置了 → 距纸张边界的绝对距离；左页取左值、右页取右值
    inset_args = dict(st.full, title_margins=[2, 14, 2, 10],
                      page_number_margins=[2, 14, 2, 10])
    ins_l = plan_print_page((800, 1200), inset_args, 0, 2)
    ins_r = plan_print_page((800, 1200), inset_args, 1, 2)
    assert (ins_l.title is not None and ins_r.title is not None
            and ins_l.page_number is not None
            and ins_r.page_number is not None)  # inset_args 开了标题与页码
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
    wide_full = dict(st.full, title_margins=[2, 2, 2, 30])
    overlap = plan_print_page((2400, 800), wide_full, 0, 2)
    assert overlap.title is not None  # wide_full 开了标题
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
           - plan_print_page((2400, 800), st.full, 0, 2).image[2]) < 1e-6)
    st.skipped = plan_print_page(
        (800, 1200), dict(st.full, skip_pages=["2"]), 1, 3, image_name="0002"
    )
    ok("命中 skip_pages 的页标记 skipped", st.skipped.skipped)
    ok("未命中的页不标记 skipped",
       not plan_print_page(
           (800, 1200), dict(st.full, skip_pages=["2"]), 2, 3, image_name="0003"
       ).skipped)
    ok("带侧别的写法按页名回查",
       plan_print_page(
           (800, 1200), dict(st.full, skip_pages=["2-r"]), 1, 3, image_name="0002-r"
       ).skipped)
    from utils.page_layout import resolve_title_nodes

    node_args = dict(st.full, title_switch_nodes=[[2, "卷二"]])
    stems = ["0001", "0002", "0003"]
    resolved = resolve_title_nodes(stems, node_args["title_switch_nodes"])
    ok("节点按页名解析到清单下标（第 2 页）",
       bool(resolved) and resolved[0][0] == 1, str(resolved))
    _t1 = plan_print_page((800, 1200), node_args, 0, 3, image_name="0001",
                          sorted_nodes=resolved)
    _t2 = plan_print_page((800, 1200), node_args, 1, 3, image_name="0002",
                          sorted_nodes=resolved)
    _t3 = plan_print_page((800, 1200), node_args, 2, 3, image_name="0003",
                          sorted_nodes=resolved)
    assert (_t1.title is not None and _t2.title is not None
            and _t3.title is not None)  # 节点页都有标题
    ok("节点页起标题切换且延续到后续页",
       _t1.title.text == "测试古籍" and _t2.title.text == "卷二"
       and _t3.title.text == "卷二",
       f"{_t1.title.text} / {_t2.title.text} / {_t3.title.text}")
    _fallback = plan_print_page(
        (800, 1200), node_args, 1, 3, image_name="0002")
    assert _fallback.title is not None  # node_args 开了标题
    ok("不传清单解析结果时节点整体失效（兜底语义：调用方必须传 sorted_nodes）",
       _fallback.title.text == "测试古籍")
    # 条目页名有缺口（3..5）时，节点 1 必须命中**列表第 1 项**（位置语义）
    gap_resolved = resolve_title_nodes(
        ["1", "2", "3"], [[1, "首页标题"]])  # _resolved_nodes 的输入形态
    ok("位置序号解析：节点 1 命中列表第 1 项（哪怕条目页名是 3/4/5）",
       bool(gap_resolved) and gap_resolved[0][0] == 0, str(gap_resolved))
    _gap_plan = plan_print_page(
        (800, 1200), dict(st.full, title_switch_nodes=[[1, "首页标题"]]),
        0, 3, image_name="0003",           # 该条目的真实页名是 3
        sorted_nodes=resolve_title_nodes(["1", "2", "3"], [[1, "首页标题"]]),
    )
    assert _gap_plan.title is not None  # 该页有节点标题
    ok("缺口页名条目（页名 3 的第 1 项）页面标题 = 节点标题",
       _gap_plan.title.text == "首页标题", str(_gap_plan.title))
    # ⚠️ print_preview 2026-10-07 起是**子包**：读源码要合起包内所有文件看。
    from tests.selftests._context import module_source_text

    pv_src = module_source_text(
        ROOT,
        "desktop/components/viewers/print_preview",
    )
    pw_src = (ROOT
              / "desktop" / "workers" / "preview_worker.py"
              ).read_text(encoding="utf-8")
    ok("print_spec 携带解析好的 nodes、worker 透传给 plan_print_page",
       '"nodes": self._resolved_nodes(args)' in pv_src
       and 'sorted_nodes=self.print_spec.get("nodes")' in pw_src)
    ok("_resolved_nodes 用列表位置序号解析（不是条目页名）",
       "stems = [str(i + 1) for i in range(len(self._entries_cache))]" in pv_src)
    import pymupdf

    from functions.print import PrintFunction

    img_dir = st.tmp / "imgs"
    img_dir.mkdir(parents=True, exist_ok=True)
    _tmp_png(img_dir / "0001.png", 800, 1200)
    # 第二张：第 5b 节要验**右页**（第 2 页）的文字轮廓右边距，必须有 2 页
    _tmp_png(img_dir / "0002.png", 800, 1200)

    st.pdf_args: dict[str, object] = {
        # 与 CommandArgs 一致：input/output 必须是 Path，不是字符串
        "input": img_dir,
        "output": st.tmp / "out",
        "pdf_name": "parity.pdf",
        "paper_size": "A4",
        "orientation": "landscape",
        "page_margins": "15,10,20,10",
        "title_printing": False,
        "page_number_printing": False,
        "workers": 1,
    }
    PrintFunction(dict(st.pdf_args)).execute()  # type: ignore[reportArgumentType]  # 测试直接喂 dict（运行时按 get 取值，与 ArgsProvider 协议兼容）
    pdf_path = st.tmp / "out" / "parity.pdf"
    ok("测试 PDF 已生成", pdf_path.exists(), str(pdf_path))

    st.expect = plan_print_page(
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
        ex, ey, ew, eh = st.expect.image
        ok("PDF 中图片落点与预览几何一致（≤1.5pt）",
           abs(bx0 - ex * pt_per_mm) < 1.5
           and abs(by0 - ey * pt_per_mm) < 1.5
           and abs((bx1 - bx0) - ew * pt_per_mm) < 1.5
           and abs((by1 - by0) - eh * pt_per_mm) < 1.5,
           f"pdf={tuple(round(v, 2) for v in (bx0, by0, bx1, by1))} "
           f"plan={tuple(round(v * pt_per_mm, 2) for v in st.expect.image)}")
        ok("PDF 页尺寸与预览纸张一致",
           abs(doc[0].rect.width - st.expect.page_w_mm * pt_per_mm) < 1.0
           and abs(doc[0].rect.height - st.expect.page_h_mm * pt_per_mm) < 1.0,
           f"{doc[0].rect.width:.1f}x{doc[0].rect.height:.1f}")
    finally:
        doc.close()
    inset_pdf_args = dict(st.pdf_args, pdf_name="parity_inset.pdf")
    inset_pdf_args.update({
        "title_printing": True, "title_text": "测试古籍",
        "title_font_size": 18, "title_position": "top",
        "title_orientation": "vertical",
        "page_number_printing": True, "page_number_font_size": 12,
        "title_margins": "2,14,2,10", "page_number_margins": "2,14,2,10",
    })
    PrintFunction(dict(inset_pdf_args)).execute()  # type: ignore[reportArgumentType]  # 同上：dict 与 ArgsProvider 协议运行时兼容
    pdf_path2 = st.tmp / "out" / "parity_inset.pdf"
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
        from typing import cast

        _rawdict = cast(dict, page2.get_text("rawdict"))  # pymupdf 存根把 rawdict 标成 str，运行时是 dict
        _chars = [
            ch
            for block in _rawdict["blocks"]
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
    from PySide6.QtGui import QImage

    source = _tmp_png(st.tmp / "src.png", 800, 1200)
    src_img = QImage(str(source))
    pdf_count_before = len(list(st.tmp.rglob("*.pdf")))
    before = sorted(str(p) for p in st.tmp.rglob("*"))
    page_img = compose_print_page(src_img, st.expect)
    sk_img = compose_print_page(src_img, st.skipped)
    after = sorted(str(p) for p in st.tmp.rglob("*"))
    ok("效果预览不写出任何文件", before == after,
       str(sorted(set(after) - set(before))))
    ok("效果预览不生成 PDF",
       len(list(st.tmp.rglob("*.pdf"))) == pdf_count_before,
       str([p.name for p in st.tmp.rglob("*.pdf")]))
    ok("效果位图尺寸按纸张比例",
       page_img.width() == round(
           st.expect.page_w_mm * preview_px_per_mm(
               st.expect.page_w_mm, st.expect.page_h_mm)
       )
       and page_img.width() > page_img.height(),
       f"{page_img.width()}x{page_img.height()}")
    ok("跳过页画出的是留白提示页（与正常页不同）",
       sk_img.size() == page_img.size()
       and sk_img.pixelColor(2, 2) != page_img.pixelColor(2, 2))

