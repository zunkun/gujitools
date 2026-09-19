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

    # ---- 4. 面板：切 area 会刷新 border 默认值 ----
    from desktop.components.panels.rembg_panel import RembgPanel

    panel = RembgPanel()
    try:
        ok("默认（area=1）表单里 border 显示 0",
           panel.border.text().strip() == "0",
           f"{panel.border.text()!r}")
        ok("默认参数导出带 border=0",
           panel.get_args().get("border") == "0",
           str(panel.get_args().get("border")))

        def _set_area(value: int) -> None:
            idx = panel.area.findData(value)
            panel.area.setCurrentIndex(idx)

        # 切到 area=4（整页）→ border 清空（= None）
        _set_area(4)
        ok("切到 area=4 后 border 清空（不设 border）",
           panel.border.text().strip() == "",
           f"{panel.border.text()!r}")
        ok("area=4 导出不带 border 键",
           "border" not in panel.get_args(), str(panel.get_args()))
        # 切回 area=2 → 恢复 0
        _set_area(2)
        ok("切到 area=2 后 border 回到 0",
           panel.border.text().strip() == "0", f"{panel.border.text()!r}")
        ok("area=2 导出 border=0",
           panel.get_args().get("border") == "0")

        # 用户手填过 → area 变化不再覆盖
        panel.border.setText("30")
        panel.border.textEdited.emit("30")
        _set_area(3)
        ok("用户手填 border 后，切 area 不覆盖其输入",
           panel.border.text().strip() == "30", f"{panel.border.text()!r}")
        ok("手填值照样导出",
           panel.get_args().get("border") == "30")

        # 回填空 border → 按 area 补默认；回填非默认值 → 视为用户手填
        panel.apply_args({"area": 2, "border": None})
        ok("回填空 border 时按 area 补默认 0",
           panel.border.text().strip() == "0", f"{panel.border.text()!r}")
        panel.apply_args({"area": 2, "border": "30"})
        ok("回填的显式 border 原样保留",
           panel.border.text().strip() == "30", f"{panel.border.text()!r}")
        # 恢复默认 → 回到 area=1 的 0
        panel.reset_to_default()
        ok("恢复默认后 border 回到 area=1 的默认 0",
           panel.border.text().strip() == "0", f"{panel.border.text()!r}")
    finally:
        panel.deleteLater()
