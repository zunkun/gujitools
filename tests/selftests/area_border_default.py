# -*- coding: utf-8 -*-
"""第三步（crop / rembg / cropremove）``border`` 的默认值**随 area 变**。

规则（用户确认，与 docs/functions/crop.md 一致）：
- ``area ∈ {1,2,3}`` → ``"0"``：第四步会把图重新排进 A4，第三步再外扩留白
  等于「图片内留白 + 页面边距」双重留白，还会让第四步拿到的图尺寸失真；
- ``area = 4``（整页不检测）→ ``None``：整页输出既不裁剪也无留白，border
  对它没有意义。

⚠️ ``area=2/3`` 下 ``"0"`` 与 ``None`` **不等价**：``"0"`` = 紧裁到文本框
联合外边界，``None`` = 整页原尺寸。这是用户确认过的取舍，本模块把这条
语义钉住，避免有人"顺手把 0 改回 None"。
"""

NAME = "area_border_default"
DEPENDS: list[str] = []
TITLE = "area → border 默认值联动"


def run(ctx) -> None:
    from tests.selftests._context import ok

    from core.command_spec import (
        effective_border_default, effective_page_margin_default,
    )
    from utils.box_geometry import parse_border_mm

    # ---- 1. 规则本身 ----
    ok("area=1/2/3 的 border 默认 = 0（不加留白）",
       [effective_border_default(a) for a in (1, 2, 3)] == ["0", "0", "0"],
       str([effective_border_default(a) for a in (1, 2, 3)]))
    ok("area=4（整页）的 border 默认 = None",
       effective_border_default(4) is None, str(effective_border_default(4)))
    ok("area 缺失/非法时退回 0（按非整页处理）",
       effective_border_default(None) == "0"
       and effective_border_default("x") == "0",
       f"{effective_border_default(None)} / {effective_border_default('x')}")

    # ---- 2. 语义：0 会被解析成"四边 0"，不是 None ----
    ok("area=2/3 的默认值解析成四边 0 的留白（紧裁，不是原尺寸）",
       parse_border_mm(effective_border_default(2), dpi=300) == [0, 0, 0, 0],
       str(parse_border_mm(effective_border_default(2), dpi=300)))
    ok("area=4 的默认值解析成 None（整页不裁剪不加边）",
       parse_border_mm(effective_border_default(4), dpi=300) is None)

    # ---- 3. border=0 不会触发第四步"双重留白"回落 ----
    ok("border=0 时第四步通用边距仍走内置默认（不级联成 0）",
       effective_page_margin_default("0") == effective_page_margin_default(None),
       f"{effective_page_margin_default('0')} vs "
       f"{effective_page_margin_default(None)}")
    ok("border 有值（30）时第四步通用边距才级联为 0",
       effective_page_margin_default("30") == [0.0, 0.0, 0.0, 0.0],
       str(effective_page_margin_default("30")))

    # ---- 4. 参数归属（2026-10-22 大改造）-------------------------------
    # 用户口径：
    #   · 「去底色步骤的 area 和 border 参数去除，直接整个图片去底色」；
    #   · 「检测文本框，增加 area 参数……图片按照 area 切割处理」。
    # 所以：rembg 的命令规格里不许再有 area/border，detect 必须有 area。
    from core.command_spec import COMMAND_SPECS, CROP_AREAS

    rembg_defaults = COMMAND_SPECS["rembg"].defaults
    ok("rembg 命令规格里没有 area/border",
       not ({"area", "border"} & set(rembg_defaults)),
       str(sorted(rembg_defaults)))
    ok("detect 命令规格里保留 area（默认 1，后端逻辑不删）",
       COMMAND_SPECS["detect"].defaults.get("area") == 1,
       str(sorted(COMMAND_SPECS["detect"].defaults)))
    ok("detect 的 area 取值受 CROP_AREAS 约束（1~4）",
       CROP_AREAS == (1, 2, 3, 4), str(CROP_AREAS))

    # 桌面端：第二步面板有 area、第三步面板没有 area/border
    from desktop.components.panels.detect_panel import DetectPanel
    from desktop.components.panels.rembg_panel import RembgPanel

    detect_panel = DetectPanel()
    rembg_panel = RembgPanel()
    try:
        # ⚠️ 2026-10-22 第二轮：界面上不再有 area 控件（默认值在后端常量）。
        ok("detect 面板没有 area 控件、get_args 为空",
           not hasattr(detect_panel, "area") and detect_panel.get_args() == {},
           str(detect_panel.get_args()))
        ok("rembg 面板不再有 area / border",
           not hasattr(rembg_panel, "area") and not hasattr(rembg_panel, "border"))
        ok("rembg 的 get_args 不含 area/border",
           not ({"area", "border"} & set(rembg_panel.get_args())),
           str(sorted(rembg_panel.get_args())))
    finally:
        detect_panel.deleteLater()
        rembg_panel.deleteLater()
