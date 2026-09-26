# -*- coding: utf-8 -*-
"""输入健壮性：非法/边界参数要给"人话"，不许静默忽略或抛原生异常（2026-09-26 审计）。

覆盖（每条都对应一个真实会踩到的用法）：

| # | 场景 | 原来的样子 |
|---|---|---|
| G2 | `page_margins: [200,0,200,0]`（A4 高 297mm） | 只校验"非负"，排版算出**负的图片宽高**传给 `pdf.image()` |
| G3 | `page_margins: "abc"` | **静默回落**默认 [20,20,20,20]，用户毫无反馈（同文件里的 title_margins 却会报错） |
| G4 | `files` 写成字符串 | 被**逐字符迭代**，得到一堆单字符路径、全部静默跳过 |
| G5 | `print -i 单张图.png` | `os.listdir` 抛未处理的 `NotADirectoryError` |
| G6 | 只填 `left_page_margins` | 整条奇偶页规则**被静默忽略** |
| G7 | `crop/cropremove --ext jpg` | 无框页硬编码 `.png`，同目录混两种扩展名 |
| G10 | `title_font_size: -10` / `page_number_base: "abc"` | 负字号算到纸外；非数字在 `int()` 处抛未捕获异常 |
| G11 | `crop -i 空目录` | 先花 ~5s / ~350MB 加载 YOLO，然后才报"未找到图片" |
| G13 | `--no-quick` + 配置里 `quick: true` | False 被当"未显式开启"丢掉 → **关不掉** |
| G14 | `--bordr 20`（拼错） | 只打一行警告继续跑，参数落到默认值、退出码 0 |
| G15 | 极小页宽 + 大 zoom | `MAX_OUTPUT_WIDTH_PX // int(page_width)` 除零 |
| - | `--pages "1-2-3"` | 原生 `ValueError: too many values to unpack` |
"""

NAME = "input_robustness"
DEPENDS: list[str] = []
TITLE = "输入健壮性"


def run(ctx) -> None:
    import re
    from pathlib import Path

    from tests.selftests._context import ok

    repo = Path(__file__).resolve().parents[2]

    def code_of(rel: str) -> str:
        raw = (repo / rel).read_text(encoding="utf-8")
        return "\n".join(line.split("#", 1)[0] for line in raw.splitlines())

    work = ctx.tmp / "input_robustness"
    work.mkdir(parents=True, exist_ok=True)
    src = work / "images"
    src.mkdir(exist_ok=True)
    from PIL import Image

    Image.new("RGB", (200, 300), (210, 200, 190)).save(src / "1.jpg")

    from core.args import CommandArgs

    def build(command, **kw):
        args = CommandArgs(command=command, input=str(src), **kw)
        args.validate()
        return args

    # ---- G2：边距上界 ----
    for key in ("page_margins", "left_page_margins", "title_margins"):
        try:
            build("print", **{key: "200"})
        except ValueError as exc:
            ok(f"{key}=200mm 被拒绝（会把可排版区域挤成负数）",
               "不能超过" in str(exc), str(exc)[:70])
        else:
            ok(f"{key}=200mm 被拒绝（会把可排版区域挤成负数）", False, "放行了")
    ok("正常边距仍可用", build("print", page_margins="20").get("page_margins") == [20] * 4)

    # ---- G3：非法边距要报错（不静默回落默认）----
    for key in ("page_margins", "left_page_margins"):
        try:
            build("print", **{key: "abc"})
        except ValueError as exc:
            ok(f"{key}='abc' 报错（不静默变默认值）", key in str(exc), str(exc)[:70])
        else:
            ok(f"{key}='abc' 报错（不静默变默认值）", False, "静默回落了")

    # ---- G10：字号与页码基数 ----
    for kw, key in (({"title_font_size": -10}, "title_font_size"),
                    ({"page_number_font_size": 0}, "page_number_font_size"),
                    ({"page_number_font_size": 9999}, "page_number_font_size")):
        try:
            build("print", **kw)
        except ValueError as exc:
            ok(f"{key}={kw[key]} 被拒绝", key in str(exc), str(exc)[:70])
        else:
            ok(f"{key}={kw[key]} 被拒绝", False, "放行了")
    try:
        build("print", page_number_base="abc")
    except ValueError as exc:
        ok("page_number_base='abc' 抛 ValueError（不是未捕获的 TypeError/ValueError）",
           "page_number_base" in str(exc) or "需要整数" in str(exc), str(exc)[:70])
    else:
        ok("page_number_base='abc' 抛 ValueError（不是未捕获的 TypeError/ValueError）",
           False, "放行了")

    # ---- G4/G5：print 的清单与单文件输入 ----
    from functions.print import _collect_image_files

    try:
        _collect_image_files(src, "不是列表")
    except ValueError as exc:
        ok("files 写成字符串被拒绝（不被逐字符迭代）", "files" in str(exc), str(exc)[:70])
    else:
        ok("files 写成字符串被拒绝（不被逐字符迭代）", False, "放行了")

    text = ctx.tmp / "input_robustness" / "pages.txt"
    text.write_text("0", encoding="utf-8")  # 让 files 清单有内容可点
    one = src / "1.jpg"
    real = ctx.tmp / "input_robustness" / "real.jpg"
    Image.new("RGB", (120, 160), (1, 2, 3)).save(real)
    got = _collect_image_files(src, [str(real)])
    ok("files 清单里的有效路径被采纳", got == [str(real)], str(got))
    got = _collect_image_files(src, ["不存在.jpg"])
    ok("清单里不存在的路径被跳过（不崩）", got == [], str(got))
    # 单文件输入（以前 os.listdir 会抛 NotADirectoryError）
    ok("print 的单文件输入被正确接受",
       _collect_image_files(real) == [str(real)], str(_collect_image_files(real)))

    # ---- G6：只配一侧奇偶边距也要生效 ----
    from utils.page_layout import _margins_for_page

    left_only = _margins_for_page([10, 10, 10, 10], [50, 1, 1, 1], None, 1)
    even = _margins_for_page([10, 10, 10, 10], [50, 1, 1, 1], None, 2)
    ok("只配 left_page_margins：奇数页用它", left_only == (50.0, 1.0, 1.0, 1.0), str(left_only))
    ok("只配 left_page_margins：偶数页回落通用边距", even == (10.0, 10.0, 10.0, 10.0), str(even))

    # ---- G7：crop / cropremove 的后缀跟着 ext 走 ----
    for command in ("crop", "cropremove"):
        args = CommandArgs(command=command, input=str(src), ext="jpg", area=1)
        from functions import get_function

        fn = get_function(command, args, None)
        ok(f"{command} 的输出后缀跟着 ext（不是硬编码 .png）",
           fn.output_suffix == ".jpg", str(fn.output_suffix))
    crop_code = code_of("functions/crop.py")
    ok("crop 的后缀取自 command_args 的 ext", 'self.command_args.get("ext")' in crop_code)
    remove_code = code_of("functions/crop_remove.py")
    ok("cropremove 两条路径共用 output_suffix",
       remove_code.count("self.output_suffix}") >= 2
       and 'f"{image_path.stem}.png"' not in remove_code)
    ok("cropremove 显式要 jpg 时才写 JPEG（默认仍是 PNG）",
       'format="JPEG"' in remove_code and 'format="PNG"' in remove_code)

    # ---- G13：--no-quick 能关掉配置里的 quick ----
    main_code = code_of("cli/__main__.py")
    ok("布尔过滤给 store_false 开关留了例外", "_EXPLICIT_FALSE_KEYS" in main_code)
    ok("该例外登记了 quick", re.search(r'_EXPLICIT_FALSE_KEYS\s*=\s*\{\s*"quick"', main_code) is not None)
    # 护栏盯着"新增 store_false 开关必须登记"
    store_false_dests = set(
        re.findall(r'action="store_false"[^)]*?dest="(\w+)"', (repo / "cli" / "cli_args.py").read_text(encoding="utf-8"), re.S)
    )
    registered = set(re.findall(r'"(\w+)"', re.search(r"_EXPLICIT_FALSE_KEYS\s*=\s*\{([^}]*)\}", main_code).group(1)))
    ok("每个 store_false 开关都登记在例外集合里（不会悄悄失效）",
       store_false_dests <= registered,
       f"未登记={sorted(store_false_dests - registered)}")

    # ---- G14：拼错的参数要报错（不是警告后继续）----
    args_code = code_of("cli/cli_args.py")
    ok("未知参数不再'警告后继续'",
       "警告：忽略未定义参数" not in args_code and "无法识别的参数" in args_code)
    ok("未知参数会给出拼写候选", "_closest_flag" in args_code)

    # ---- G15 / parse_pages ----
    from utils.pdf_extract import calculate_zoom, parse_pages

    ok("极小页宽不触发除零", calculate_zoom(0, 99999) == 1, str(calculate_zoom(0, 99999)))
    for bad in ("1-2-3", "-", "3-", "x"):
        try:
            parse_pages(bad, 10)
        except ValueError as exc:
            ok(f"parse_pages({bad!r}) 给出人话（不是 unpack 报错）",
               "格式" in str(exc) or "非数字" in str(exc), str(exc)[:60])
        else:
            ok(f"parse_pages({bad!r}) 给出人话（不是 unpack 报错）", False, "没报错")
    ok("parse_pages 正常输入不变", parse_pages("3,5-6", 10) == [2, 4, 5])
    ok("parse_pages 容忍多余逗号", parse_pages("1,,3", 10) == [0, 2])

    # ---- G11：空输入不先加载模型 ----
    # ⚠️ 别用 split("warm_up_detect_model") 取前半段：那个名字在**模块 docstring**
    #    里也出现过（注释/docstring 不算"代码"）。直接比两个调用的位置。
    region_code = code_of("functions/text_region.py")
    check_at = region_code.find("if not self._collect_input_files():")
    warm_at = region_code.find("= warm_up_detect_model()")
    ok("先检查输入再加载模型（空目录不白付 ~5s/350MB）",
       0 <= check_at < warm_at, f"check@{check_at} warm@{warm_at}")
