# -*- coding: utf-8 -*-
"""第四步页码样式：数字怎么排、前后缀怎么拼。

守住四条不变量：

1. **三种数字样式都排得出来**：中文数字 / 阿拉伯数字 / 干支（六十甲子）；
2. **干支按 60 循环**：1 → 甲子、60 → 癸亥、61 → 甲子（天干 10 与地支 12
   的最小公倍数），不会越界；
3. **前后缀原样拼接**：空前后缀 = 只印数字，程序**不补空格**——想排
   「第 5 页」就自己把前缀写成 ``"第 "``；
4. **参数三层一致**：CLI / 桌面 / guji.yaml 都有 page_number_format /
   prefix / suffix，默认「第X頁」（历史形态，改它会动老任务的成品）。
"""

NAME = "print_number_format"
DEPENDS: list[str] = []
TITLE = "页码样式（中文/阿拉伯/干支）与前后缀"


def run(ctx) -> None:
    import os
    from pathlib import Path

    from tests.selftests._context import ok

    from utils.string_utils import format_page_number, num_to_ganzhi

    # ---- 1. 干支：六十甲子且循环 ----
    ok("干支：1 → 甲子", num_to_ganzhi(1) == "甲子", num_to_ganzhi(1))
    ok("干支：2 → 乙丑", num_to_ganzhi(2) == "乙丑", num_to_ganzhi(2))
    ok("干支：11 → 甲戌（天干回到甲）",
       num_to_ganzhi(11) == "甲戌", num_to_ganzhi(11))
    ok("干支：60 → 癸亥（一轮的末尾）",
       num_to_ganzhi(60) == "癸亥", num_to_ganzhi(60))
    ok("干支：61 → 甲子（按 60 循环，不越界）",
       num_to_ganzhi(61) == "甲子", num_to_ganzhi(61))
    ok("干支：非正数退化成数字（不抛异常、不印空串）",
       num_to_ganzhi(0) == "0" and num_to_ganzhi(-3) == "-3",
       f"{num_to_ganzhi(0)} / {num_to_ganzhi(-3)}")

    # ---- 2. 三种样式 ----
    ok("中文数字：第5頁", format_page_number(5, "chinese", "第", "頁") == "第5頁".replace("5", "五"),
       format_page_number(5, "chinese", "第", "頁"))
    ok("阿拉伯数字：第5頁",
       format_page_number(5, "arabic", "第", "頁") == "第5頁",
       format_page_number(5, "arabic", "第", "頁"))
    ok("干支：第甲子頁",
       format_page_number(1, "ganzhi", "第", "頁") == "第甲子頁",
       format_page_number(1, "ganzhi", "第", "頁"))
    ok("认不出的样式回落中文数字（老配置里可能存着别的值）",
       format_page_number(5, "乱写的", "第", "頁")
       == format_page_number(5, "chinese", "第", "頁"),
       format_page_number(5, "乱写的", "第", "頁"))

    # ---- 3. 前后缀原样拼接、不补空格 ----
    ok("前后缀留空 → 只印数字本身",
       format_page_number(5, "arabic") == "5",
       format_page_number(5, "arabic"))
    ok("空格要用户自己给（程序不补）",
       format_page_number(5, "arabic", "第 ", " 页") == "第 5 页",
       repr(format_page_number(5, "arabic", "第 ", " 页")))
    ok("只给前缀也行", format_page_number(5, "arabic", "P") == "P5",
       format_page_number(5, "arabic", "P"))

    # ---- 4. 排版层：页码文本按参数生成 ----
    from utils.page_layout import plan_print_page

    base_args = {
        "paper_size": "A4", "orientation": "landscape",
        "page_margins": [20, 20, 20, 20],
        "title_printing": False,
        "page_number_printing": True, "page_number_start_page": 1,
        "page_number_base": 0, "page_number_font_size": 20,
        "page_number_color": "0,0,0", "page_number_position": "bottom",
        "page_number_orientation": "vertical",
    }

    def text_of(**extra):
        args = dict(base_args)
        args.update(extra)
        plan = plan_print_page((100, 200), args, 0, 1)
        return plan.page_number.text if plan.page_number else None

    ok("默认就是「第一頁」（历史形态不能变）", text_of() == "第一頁", str(text_of()))
    ok("换阿拉伯数字生效",
       text_of(page_number_format="arabic") == "第1頁",
       str(text_of(page_number_format="arabic")))
    ok("换干支生效",
       text_of(page_number_format="ganzhi") == "第甲子頁",
       str(text_of(page_number_format="ganzhi")))
    ok("改前后缀生效",
       text_of(page_number_format="arabic", page_number_prefix="第 ",
              page_number_suffix=" 页") == "第 1 页",
       str(text_of(page_number_format="arabic", page_number_prefix="第 ",
                   page_number_suffix=" 页")))
    ok("前缀后缀清空 → 只印数字（不被 `or` 兜底成默认）",
       text_of(page_number_format="arabic", page_number_prefix="",
              page_number_suffix="") == "1",
       str(text_of(page_number_format="arabic", page_number_prefix="",
                   page_number_suffix="")))
    ok("页码基数参与计算（base + 当前页）",
       text_of(page_number_format="arabic", page_number_base=9) == "第10頁",
       str(text_of(page_number_format="arabic", page_number_base=9)))

    # ---- 5. 参数三层一致 ----
    from core.command_spec import PRINT_DEFAULTS

    ok("CLI 默认：格式 chinese、前缀「第」、后缀「頁」",
       PRINT_DEFAULTS.get("page_number_format") == "chinese"
       and PRINT_DEFAULTS.get("page_number_prefix") == "第"
       and PRINT_DEFAULTS.get("page_number_suffix") == "頁",
       f"{PRINT_DEFAULTS.get('page_number_format')}/"
       f"{PRINT_DEFAULTS.get('page_number_prefix')}/"
       f"{PRINT_DEFAULTS.get('page_number_suffix')}")

    from desktop.components.panels.print_params import (
        DEFAULT_PARAMS, PAGE_NUMBER_FORMATS,
    )

    ok("桌面表单默认含三个页码样式键",
       {"page_number_format", "page_number_prefix", "page_number_suffix"}
       <= set(DEFAULT_PARAMS))
    ok("桌面默认值与 CLI 一致（不另写一份）",
       DEFAULT_PARAMS["page_number_format"] == PRINT_DEFAULTS["page_number_format"]
       and DEFAULT_PARAMS["page_number_prefix"] == PRINT_DEFAULTS["page_number_prefix"]
       and DEFAULT_PARAMS["page_number_suffix"] == PRINT_DEFAULTS["page_number_suffix"])

    from utils.page_layout import PAGE_NUMBER_FORMATS as VALUE_ORDER

    ok("下拉取值与 utils 的样式枚举一致（防止两边漂移）",
       tuple(v for _, v in PAGE_NUMBER_FORMATS) == tuple(VALUE_ORDER),
       f"{[v for _, v in PAGE_NUMBER_FORMATS]} vs {list(VALUE_ORDER)}")

    import yaml

    root = ctx.project_root if hasattr(ctx, "project_root") else None
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
    template = yaml.safe_load(
        open(os.path.join(str(root), "static", "guji.yaml"), encoding="utf-8")
    )
    block = template.get("print", {})
    ok("模板 print 段显式给出三个页码样式键",
       {"page_number_format", "page_number_prefix", "page_number_suffix"}
       <= set(block),
       f"{sorted(k for k in block if k.startswith('page_number'))}")
    ok("模板值与 CLI 默认值一致",
       block.get("page_number_format") == "chinese"
       and block.get("page_number_prefix") == "第"
       and block.get("page_number_suffix") == "頁",
       f"{block.get('page_number_format')}/{block.get('page_number_prefix')}/"
       f"{block.get('page_number_suffix')}")

    # ---- 6. 面板：导出与回填 ----
    from desktop.components.panels.print_panel import PrintPanel

    panel = PrintPanel()
    args = panel.get_args()
    ok("面板导出三个页码样式键且默认与 CLI 一致",
       args.get("page_number_format") == "chinese"
       and args.get("page_number_prefix") == "第"
       and args.get("page_number_suffix") == "頁",
       f"{args.get('page_number_format')}/{args.get('page_number_prefix')}/"
       f"{args.get('page_number_suffix')}")

    panel._apply_args({
        "page_number_format": "ganzhi",
        "page_number_prefix": "",
        "page_number_suffix": "叶",
    })
    after = panel.get_args()
    ok("回填后：样式改成干支", after.get("page_number_format") == "ganzhi",
       str(after.get("page_number_format")))
    ok("回填后：空前缀被保住（不回落成「第」）",
       after.get("page_number_prefix") == "",
       repr(after.get("page_number_prefix")))
    ok("回填后：后缀生效", after.get("page_number_suffix") == "叶",
       str(after.get("page_number_suffix")))

    # ---- 7. 端到端：真的出一份 PDF，页码按样式排 ----
    # ⚠️ 这条守的是一个**很隐蔽**的坑：`functions/print.py` 给
    # `plan_print_page` 传的是手工挑的 `plan_args` 子集，新参数忘了转进去的
    # 话，PDF 侧会静默用默认值（页码仍是「第一頁」），而自测里凡是直接调
    # `plan_print_page` 的断言**全都还是绿的**——只有真出一次 PDF 才暴露。
    import pymupdf

    from PySide6.QtGui import QColor, QImage

    from functions.print import PrintFunction

    work = Path(ctx.tmp) / "number_format_e2e"
    imgs = work / "imgs"
    imgs.mkdir(parents=True, exist_ok=True)
    pic = QImage(400, 600, QImage.Format_RGB32)
    pic.fill(QColor("#f5f0e6"))
    pic.save(str(imgs / "0001-l.png"))

    PrintFunction({
        "input": imgs, "output": work / "out", "pdf_name": "n.pdf",
        "paper_size": "A4", "orientation": "landscape",
        "page_margins": [20, 20, 20, 20],
        "title_printing": False,
        "page_number_printing": True, "page_number_start_page": 1,
        "page_number_base": 0, "page_number_font_size": 18,
        "page_number_color": "0,0,0", "page_number_position": "bottom",
        "page_number_orientation": "vertical",
        "page_number_format": "ganzhi",
        "page_number_prefix": "第", "page_number_suffix": "葉",
        "workers": 1,
    }).execute()
    produced = work / "out" / "n.pdf"
    ok("端到端：PDF 已生成", produced.exists(), str(produced))
    if produced.exists():
        doc = pymupdf.open(str(produced))
        try:
            flat = "".join(doc[0].get_text().split())
            ok("端到端：成品 PDF 的页码是干支「第甲子葉」",
               flat == "第甲子葉", repr(flat))
        finally:
            doc.close()
