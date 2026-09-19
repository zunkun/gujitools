# -*- coding: utf-8 -*-
"""第三步 border 级联第四步默认边距。

背景：第三步 crop/rembg 的 border 被烘焙进图片像素后，第四步 print 仍独立用
自己的 page_margins —— 于是「图片内留白 + 页面边距」双重留白。规则（用户拍板）：

- 上游 border **非 None 且非全 0**（即真的加了留白）→ 第四步通用边距默认回落 0；
- 上游未设 border（GUI 第四步独立运行 / CLI）/ border 为 0 → 保持内置默认 20；
- 用户显式给了 page_margins 时一律以用户值为准（默认只是默认）。

本模块钉住两条纯函数：``border_has_padding`` 与 ``effective_page_margin_default``。
"""

NAME = "print_border_cascade"
DEPENDS: list[str] = []
TITLE = "第三步 border 级联第四步默认边距"

from tests.selftests._context import ok


def run(ctx) -> None:
    from core.command_spec import border_has_padding, effective_page_margin_default

    # border_has_padding：是否真的加过留白
    cases = [
        (None, False), ("", False), ("0", False), ("0,0,0,0", False),
        ("0,0", False), ("，", False),
        ("30", True), ("20,30", True), ("0,0,30,0", True),
        ("0,5", True), ("5", True),
    ]
    for val, expect in cases:
        ok(f"border_has_padding({val!r})=={expect}",
           border_has_padding(val) is expect)

    # effective_page_margin_default：级联默认
    ok("上游未设 border → 默认 20",
       effective_page_margin_default(None) == [20, 20, 20, 20])
    ok("上游 border=0 → 默认 20（保留 20，不双重留白也不误删）",
       effective_page_margin_default("0") == [20, 20, 20, 20])
    ok("上游 border 非 0 → 默认 0（避免双重留白）",
       effective_page_margin_default("30") == [0, 0, 0, 0])
    ok("上游 border=20,30 → 默认 0",
       effective_page_margin_default("20,30") == [0, 0, 0, 0])
