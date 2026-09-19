# -*- coding: utf-8 -*-
"""第四步「版面编辑器」坐标覆盖必须真的落到 PDF 上（端到端）。

用户实测反馈：预览里把图片拖到别处、缩放好了，生成的 PDF 却还是原来的位置和
大小。根因不在画布、也不在排版，而在**参数过了一遍 JSON**：

    runner 写 args {"page_rects": {1: [x,y,w,h]}}
      → write_json 落盘（JSON 对象的键只能是字符串）
      → 子进程读回 {"1": [x,y,w,h]}
      → functions/print.py 里 page_rects.get(i + 1) 用 **int** 查表 → 永远 None
      → 该页静默回落到 page_margins 自动排版

`plan_print_page(image_rect=...)` 这条纯函数链是好的（print_rect_override 已守），
缺的正是**键类型**这一段。本模块把两种键形态都钉死：
- 纯函数层：_normalize_page_rects 把 "1"/1 都归一成 int，垃圾键丢弃；
- 端到端：用**字符串键**（落盘后的真实形态）跑一次真 PDF，逐页比对
  图片在页面上的落点与尺寸（mm ↔ pt 换算），并确认未覆盖的页仍走自动排版。
"""

NAME = "print_rect_pdf_e2e"
DEPENDS: list[str] = []
TITLE = "逐图坐标覆盖落到 PDF（含 JSON 键归一）"

# 1 mm = 72 / 25.4 pt
MM_TO_PT = 72.0 / 25.4


def run(ctx) -> None:
    from pathlib import Path

    import pymupdf
    from PIL import Image, ImageDraw

    from tests.selftests._context import ok

    from core.args import CommandArgs
    from functions.print import PrintFunction, _normalize_page_rects

    tmp = Path(ctx.tmp) / "rect_pdf_case"
    tmp.mkdir(parents=True, exist_ok=True)

    # ---------------- 1. 纯函数：键归一 ----------------
    ok("字符串键归一为 int（JSON 落盘后的形态）",
       _normalize_page_rects({"1": [1, 2, 3, 4]}) == {1: [1, 2, 3, 4]},
       str(_normalize_page_rects({"1": [1, 2, 3, 4]})))
    ok("int 键原样保留（CLI/YAML 直传的形态）",
       _normalize_page_rects({2: [1, 2, 3, 4]}) == {2: [1, 2, 3, 4]})
    ok("垃圾键丢弃而不是抛错",
       _normalize_page_rects({"x": [1, 2, 3, 4], "3": [0, 0, 1, 1]})
       == {3: [0, 0, 1, 1]})
    ok("None / 非 dict 一律归一成空表",
       _normalize_page_rects(None) == {} and _normalize_page_rects("x") == {})

    # ---------------- 2. 复现「键被 JSON 改成字符串」这个坑 ----------------
    import json

    from desktop.store.json_io import write_json

    cfg = tmp / "run.json"
    write_json(cfg, {"args": {"page_rects": {1: [10, 20, 30, 40]}}})
    back = json.loads(cfg.read_text(encoding="utf-8"))
    got_back = back["args"]["page_rects"]
    ok("（前置）落盘再读回后页号键确实变成了字符串",
       list(got_back.keys()) == ["1"], str(list(got_back.keys())))
    ok("归一后仍能按 int 页号取到坐标（否则覆盖静默失效）",
       _normalize_page_rects(got_back).get(1) == [10, 20, 30, 40],
       str(_normalize_page_rects(got_back)))

    # ---------------- 3. 端到端：字符串键跑真 PDF ----------------
    for n in (1, 2):
        im = Image.new("RGB", (800, 600), "white")
        ImageDraw.Draw(im).rectangle([40, 40, 760, 560], fill=(90, 120, 200))
        im.save(tmp / f"{n}.png")

    rect = [30.0, 40.0, 100.0, 60.0]  # 第 1 页：x/y/w/h mm
    files = [str(tmp / "1.png"), str(tmp / "2.png")]
    ca = CommandArgs(
        command="print", input=str(tmp), output=str(tmp),
        pdf_name="rect.pdf", files=files,
        paper_size="A4", orientation="landscape",
        page_margins=[20, 20, 20, 20],
        title_printing=False, page_number_printing=False,
        # ⚠️ 刻意用**字符串键**：这才是运行配置过完 JSON 之后的真实形态
        page_rects={"1": list(rect)},
    )
    res = PrintFunction(ca).execute()
    pdf_path = tmp / "rect.pdf"
    ok("PDF 生成成功", pdf_path.exists(), str(res))

    doc = pymupdf.open(str(pdf_path))
    ok("PDF 两页（覆盖不增减页）", doc.page_count == 2, str(doc.page_count))
    if doc.page_count >= 2:
        b1 = doc[0].get_image_info()[0]["bbox"]
        x0, y0, x1, y1 = b1
        ok("第 1 页图片落点 == 版面编辑器记录的 x/y（mm→pt）",
           abs(x0 - rect[0] * MM_TO_PT) < 1.0
           and abs(y0 - rect[1] * MM_TO_PT) < 1.0,
           f"got=({x0:.1f},{y0:.1f}) 期望=({rect[0] * MM_TO_PT:.1f},"
           f"{rect[1] * MM_TO_PT:.1f})")
        ok("第 1 页图片尺寸 == 记录的 w/h（缩放生效）",
           abs((x1 - x0) - rect[2] * MM_TO_PT) < 1.0
           and abs((y1 - y0) - rect[3] * MM_TO_PT) < 1.0,
           f"got=({x1 - x0:.1f}x{y1 - y0:.1f}) 期望="
           f"({rect[2] * MM_TO_PT:.1f}x{rect[3] * MM_TO_PT:.1f})")
        # 第 2 页没给坐标：必须与 plan_print_page 的自动排版结果一致
        from utils.page_layout import plan_print_page

        _auto = plan_print_page(
            (800, 600),
            {"paper_size": "A4", "orientation": "landscape",
             "page_margins": [20, 20, 20, 20],
             "title_printing": False, "page_number_printing": False},
            1, 2, image_name="2",
        )
        b2 = doc[1].get_image_info()[0]["bbox"]
        ok("未覆盖的第 2 页仍走自动排版（不与第 1 页坐标串味）",
           abs(b2[0] - _auto.image[0] * MM_TO_PT) < 1.0
           and abs((b2[2] - b2[0]) - _auto.image[2] * MM_TO_PT) < 1.0
           and abs(b2[0] - rect[0] * MM_TO_PT) > 2.0,
           f"第2页=({b2[0]:.1f},w={b2[2] - b2[0]:.1f}) "
           f"自动排版=(x={_auto.image[0] * MM_TO_PT:.1f},"
           f"w={_auto.image[2] * MM_TO_PT:.1f})")
    doc.close()
