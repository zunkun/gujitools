# -*- coding: utf-8 -*-
"""第四步「版面编辑器」逐图坐标覆盖：plan_print_page 的 image_rect。

背景：第四步要支持在 A4 纸上拖拽/缩放图片，记录每张图的 [x,y,w,h] mm 坐标，
生成 PDF 时直接作图片框（所见即所得）。``plan_print_page`` 是唯一几何事实来源
（预览与成品共用），故覆盖逻辑必须落在它身上，且：

- 给定 image_rect（页面 mm，与 plan.image 同源）→ 直接作为图片框，不重算；
- image_rect 超出页面 / 非法 → 回落到 page_margins 自动排版（不静默用坏值）；
- 覆盖只影响图片框；标题/页码几何（取决于 page_margins）不受影响。
"""

NAME = "print_rect_override"
DEPENDS: list[str] = []
TITLE = "第四步逐图坐标覆盖 plan_print_page"

from tests.selftests._context import ok


def run(ctx) -> None:
    from utils.page_layout import plan_print_page

    args = {
        "paper_size": "A4",
        "orientation": "landscape",  # A4 横版：297 x 210 mm
        "page_margins": [20, 20, 20, 20],
        "title_printing": True,
        "title_text": "测试",
        "title_font_size": 20,
        "page_number_printing": True,
        "page_number_start_page": 1,
        "page_number_font_size": 20,
    }
    img = (1000, 1400)

    auto = plan_print_page(img, args, 0, 1, image_name="p")
    # 自动排版：图片应被夹在 20mm 边距内
    ax, ay, aw, ah = auto.image
    ok("自动排版图片框在页面内",
       ax >= 19.9 and ay >= 19.9 and ax + aw <= 297.1 and ay + ah <= 210.1,
       str(auto.image))

    # 1) 给定坐标 → 原样采用
    rect = [10.0, 10.0, 50.0, 50.0]
    plan = plan_print_page(img, args, 0, 1, image_name="p", image_rect=rect)
    ok("给定 image_rect 直接作为图片框", plan.image == tuple(rect), str(plan.image))

    # 2) 标题/页码几何不受覆盖影响（仍取决于 page_margins）
    ok("覆盖不影响标题生成", plan.title is not None)
    ok("覆盖不影响页码生成", plan.page_number is not None)

    # 3) 越界 → 回落自动排版（不静默用坏值）
    oob = [250.0, 0.0, 100.0, 100.0]  # 250+100=350 > 297 越界
    plan_oob = plan_print_page(img, args, 0, 1, image_name="p", image_rect=oob)
    ok("越界 image_rect 回落自动排版",
       plan_oob.image != tuple(oob) and plan_oob.image == auto.image,
       str(plan_oob.image))

    # 4) 非法（长度不足）→ 回落自动排版
    bad = [5.0]
    plan_bad = plan_print_page(img, args, 0, 1, image_name="p", image_rect=bad)
    ok("非法 image_rect 回落自动排版", plan_bad.image == auto.image,
       str(plan_bad.image))

    # 5) 零宽/零高 → 回落自动排版
    zero = [10.0, 10.0, 0.0, 50.0]
    plan_zero = plan_print_page(img, args, 0, 1, image_name="p", image_rect=zero)
    ok("零宽 image_rect 回落自动排版", plan_zero.image == auto.image,
       str(plan_zero.image))
