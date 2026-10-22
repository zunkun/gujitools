# -*- coding: utf-8 -*-
"""2026-10-22：**area 参数已从整个项目移除**。

用户口径：「移除所有 area 相关代码，不再有 area；识别出文本框后，把文本框
裁剪出来。cli 中 crop cropremove 中的 area 相关参数也不再需要。」

本模块把这件事钉住：
- 命令规格（crop / cropremove / detect / rembg）里都不许再出现 ``area``；
- 常量 ``CROP_AREAS`` / ``WHOLE_PAGE_AREA`` / ``DETECT_DEFAULT_AREA`` 已删除；
- CLI 的 crop / cropremove 不再注册 ``--area``；
- 桌面面板没有 area 控件；
- border 默认恒为紧裁（"0"），不再随 area 变化。
"""

NAME = "area_border_default"
DEPENDS: list[str] = []
TITLE = "area 已移除 / border 默认紧裁"


def run(ctx) -> None:
    from tests.selftests._context import ok

    import core.command_spec as spec
    from core.command_spec import COMMAND_SPECS, effective_page_margin_default
    from utils.box_geometry import parse_border_mm

    # ---- 1. 常量与函数已删除 ----
    for name in ("CROP_AREAS", "WHOLE_PAGE_AREA", "DETECT_DEFAULT_AREA",
                 "AREA_WHOLE_PAGE", "effective_border_default"):
        ok(f"core.command_spec 不再导出 {name}", not hasattr(spec, name))

    # ---- 2. 命令规格里没有 area ----
    for command in ("crop", "cropremove", "detect", "rembg"):
        defaults = COMMAND_SPECS[command].defaults
        ok(f"{command} 命令规格里没有 area",
           "area" not in defaults, str(sorted(defaults)))

    # ---- 3. CLI 不再注册 --area ----
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "cli" / "cli_args.py"
    ).read_text(encoding="utf-8")
    ok("CLI 源码里不再出现 --area", '"--area"' not in source)
    ok("CLI 不再 import CROP_AREAS", "CROP_AREAS" not in source)

    # ---- 4. border 默认紧裁：语义仍是「四边 0」 ----
    ok("border 默认 \"0\" 解析成四边 0（紧裁，不是原尺寸）",
       parse_border_mm("0", dpi=300) == [0, 0, 0, 0],
       str(parse_border_mm("0", dpi=300)))
    ok("border=0 时第四步通用边距仍走内置默认（不级联成 0）",
       effective_page_margin_default("0") == effective_page_margin_default(None))
    ok("border 有值（30）时第四步通用边距才级联为 0",
       effective_page_margin_default("30") == [0.0, 0.0, 0.0, 0.0],
       str(effective_page_margin_default("30")))

    # ---- 5. 桌面面板没有 area ----
    from desktop.components.panels.detect_panel import DetectPanel
    from desktop.components.panels.rembg_panel import RembgPanel

    detect_panel = DetectPanel()
    rembg_panel = RembgPanel()
    try:
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
