# -*- coding: utf-8 -*-
"""约定漂移：同一件事只能有一个定义处（2026-09-26 审计的 F 组）。

每条都是"两个地方各写一份、改一处漏一处"的真实隐患：

| # | 漂移 | 后果 |
|---|---|---|
| F1 | argparse 的 `--ext` choices 宣传 tiff，而校验器只允许 jpg/png | 用户按 `--help` 操作反而报错 |
| F2 | 默认渲染 DPI `300` 在 4 个文件里各写一遍 | CLI/GUI/库三方默认值会悄悄分叉 |
| F3 | `core.IMAGE_EXTS`（输出 2 种）与 `utils.IMAGE_EXTS`（输入 8 种）**同名不同义** | 极易互相误用 |
| F4 | `_FONT_EXTS` 三份，`font_setup` 那份多一个 `.otc` | `.otc` 能被体检扫到却不在候选表里 |
| F5 | `pdf_extract` 的签名默认值（zoom=2/quick=False）与规格（1/True）**相反** | "直接调库"与"走 CLI"是两套行为 |
| F6 | `rembg_page` 的默认参数与 `command_spec` 的 rembg 默认值各一份 | 调阈值时只改一处 |
| F7 | `natural_sort_key` 对 `page1`/`page01` 生成相同键 | 输入来自 `iterdir()` → 两次运行页序可能不同 |
| F8 | 字体按"注册名"去重 → 同一字体被注册两遍（`simfang` / `simfang_2`） | PDF 白多嵌一份字体子集 |
"""

NAME = "defaults_drift"
DEPENDS: list[str] = []
TITLE = "约定漂移"


def run(ctx) -> None:
    import inspect
    import re
    from pathlib import Path

    from tests.selftests._context import ok

    repo = Path(__file__).resolve().parents[2]

    def text_of(rel: str) -> str:
        return (repo / rel).read_text(encoding="utf-8")

    # ---- F3：同名不同义的两个 IMAGE_EXTS 必须分开命名 ----
    core_code = text_of("core/command_spec.py")
    ok("core 那边的输出格式枚举已改名（不再与 utils 的输入枚举同名）",
       "OUTPUT_IMAGE_EXTS" in core_code and not re.search(r"^IMAGE_EXTS", core_code, re.M),
       "仍有裸 IMAGE_EXTS 定义")
    ok("utils 那边仍是输入侧的 IMAGE_EXTS", "IMAGE_EXTS = {" in text_of("utils/file_utils.py"))

    # ---- F1：argparse 的 choices 与校验器的枚举一致 ----
    from core.command_spec import OUTPUT_IMAGE_EXTS

    cli_code = text_of("cli/cli_args.py")
    declared = set(re.findall(r'choices=\[([^\]]+)\]', cli_code))
    flat = set()
    for item in declared:
        flat |= {s.strip().strip('"\'').lower() for s in item.split(",") if s.strip()}
    advertised = flat & {"jpg", "png", "tiff", "tif"}
    ok("argparse 宣传的图片格式 ⊆ 校验器允许的格式",
       advertised <= set(OUTPUT_IMAGE_EXTS),
       f"宣传={sorted(advertised)} 允许={sorted(OUTPUT_IMAGE_EXTS)}")
    inline_tuple = '("jpg", "png", "tiff")'
    inline_count = core_code.count(inline_tuple)
    ok("detect 的校验器用共享枚举（不再内联元组）",
       inline_count == 1,
       f"内联元组出现 {inline_count} 次（应只有定义那一次）")

    # ---- F2：默认 DPI 只有一个定义处 ----
    units = text_of("utils/units.py")
    ok("默认 DPI 在 utils/units.py 定义", "DEFAULT_RENDER_DPI = 300" in units)
    for rel in ("core/command_spec.py", "functions/extract.py",
                "desktop/stages/generic_stage.py", "utils/pdf_extract.py"):
        code = text_of(rel)
        ok(f"{rel} 引用 DEFAULT_RENDER_DPI（不裸写 300）",
           "DEFAULT_RENDER_DPI" in code and "or 300" not in code)

    # ---- F4：字体扩展名只有一处 ----
    ok("字体扩展名在 utils/fonts.py 定义（含 .otc）",
       'FONT_EXTS = (".ttf", ".otf", ".ttc", ".otc")' in text_of("utils/fonts.py"))
    for rel in ("utils/font_scan.py", "utils/font_setup.py"):
        code = text_of(rel)
        ok(f"{rel} 从 fonts 取字体扩展名（不再自己写一份）",
           "from utils.fonts import FONT_EXTS" in code
           and '_FONT_EXTS = (' not in code)

    # ---- F5：库层签名默认值必须与规格一致 ----
    from core.command_spec import COMMAND_SPECS
    from utils.pdf_extract import extract_pdf_optimized, render_pages_parallel

    spec = COMMAND_SPECS["extract"].defaults
    sig = inspect.signature(extract_pdf_optimized)
    ok("extract_pdf_optimized 的 zoom 默认值 = 规格值",
       sig.parameters["zoom"].default == spec["zoom"],
       f"{sig.parameters['zoom'].default} vs {spec['zoom']}")
    ok("extract_pdf_optimized 的 quick 默认值 = 规格值",
       sig.parameters["quick"].default == spec["quick"],
       f"{sig.parameters['quick'].default} vs {spec['quick']}")
    ok("render_pages_parallel 的 quick 默认值 = 规格值",
       inspect.signature(render_pages_parallel).parameters["quick"].default
       == spec["quick"])

    # ---- F6：rembg 默认值只有一处（utils/image_utils.py）----
    from utils import image_utils

    rembg_spec = COMMAND_SPECS["rembg"].defaults
    pairs = (
        ("offset", image_utils.REMBG_DEFAULT_OFFSET),
        ("type", image_utils.REMBG_DEFAULT_TYPE),
        ("seal", image_utils.REMBG_DEFAULT_ENABLE_SEAL),
        ("sealcolor", image_utils.REMBG_DEFAULT_SEAL_COLOR),
        ("sealarea", image_utils.REMBG_DEFAULT_SEAL_AREA),
        ("sealmin_sat", image_utils.REMBG_DEFAULT_SEAL_MIN_SAT),
    )
    drift = {k: (rembg_spec[k], v) for k, v in pairs if rembg_spec[k] != v}
    ok("rembg 的规格默认值 = utils 里的常量", not drift, str(drift))
    ok("rembg_page 的签名默认值也用同一批常量",
       "offset: int = REMBG_DEFAULT_OFFSET" in text_of("utils/image_utils.py"))

    # ---- F7：排序键幂等（page1 / page01 不再同键）----
    from utils.sort_utils import natural_sort_key

    a = sorted(["page1.png", "page01.png", "page2.png"], key=natural_sort_key)
    b = sorted(["page01.png", "page2.png", "page1.png"], key=natural_sort_key)
    ok("含同号不同补零的文件名时排序仍然稳定（幂等）", a == b, f"{a} vs {b}")
    ok("数字自然序未被破坏",
       sorted(["p10.png", "p2.png"], key=natural_sort_key) == ["p2.png", "p10.png"])

    # ---- F8：按路径去重，同一字体只注册一次 ----
    from fpdf import FPDF

    from utils.pdf_draw import build_font_chain

    pdf = FPDF()
    c1 = build_font_chain(pdf, texts=["古籍"], preferred=None)
    c2 = build_font_chain(pdf, texts=["0123456789"], preferred=None)
    registered = getattr(pdf, "_guji_font_by_path", {})
    used_names = getattr(pdf, "_guji_font_used", set())
    ok("两条字体链共用同一份注册（不重复 embed）",
       len(registered) == len(used_names), f"{registered} / {used_names}")
    ok("第二条链直接复用注册名（没有 _2 后缀的新名）",
       c2.primary == c1.primary and not any(n.endswith("_2") for n in used_names),
       f"{c1.primary} / {c2.primary} / {sorted(used_names)}")
