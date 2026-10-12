# -*- coding: utf-8 -*-
"""用户操作手册自测：文档、截图、界面控件三者不得互相脱节。

背景：`docs/guide/user-guide.md` 是给最终用户看的操作手册，它最容易悄悄失效：

1. **引用的截图文件不存在** —— 重命名界面或换目录后，文档里全是裂图；
2. **写到的按钮文案在界面上找不到** —— 改了按钮文字，用户按图索骥点不着；
3. **截图目录里堆着没人引用的孤儿图** —— 手册改版后旧图忘删/漏改。

本模块把这三条钉住。所有断言都是「文档说的 ↔ 代码写的 ↔ 磁盘上有的」三方对照，
不涉及像素比对（那需要基线图，代价高且对字体敏感）。

> 2026-10-12 起手册截图改由**人工截取**（旧的 `tests/gui_shot.py --guide`
> 生成流水线已退役删除），因此本模块不再校验截图脚本；「文档 ↔ 界面」与
> 「文档 ↔ 磁盘」两类对照照旧。
"""

NAME = "gui_guide"
DEPENDS: list[str] = []
TITLE = "用户操作手册一致性"

#: 截图目录（2026-10-12 起平铺，不再有 guide/ 子目录）
SHOTS_REL = ("docs", "guide", "screenshots")
#: 除手册外，还会引用截图目录里图片的文档（孤儿检查把它们算作"被引用"）
_SHOT_DOCS = (
    "README.md",
    "docs/guide/user-guide.md",
    "docs/dev/gui/gui-layout.md",
)


def run(ctx) -> None:
    import re
    from pathlib import Path

    from tests.selftests._context import ok

    root = Path(__file__).resolve().parents[2]
    guide_path = root / "docs" / "guide" / "user-guide.md"

    ok("用户操作手册存在", guide_path.exists(), str(guide_path))
    if not guide_path.exists():
        return
    guide = guide_path.read_text(encoding="utf-8")

    # ---- 1. 指南里引用的每个截图都真实存在；目录里没有孤儿图 ----
    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", guide)
    ok("指南引用了截图", len(refs) > 0, f"引用数={len(refs)}")
    missing = [r for r in refs if not (guide_path.parent / r).exists()]
    ok("指南引用的截图全部存在（无裂图）", not missing, f"缺失={missing}")

    shots_dir = root.joinpath(*SHOTS_REL)
    on_disk = {p.name for p in shots_dir.glob("*.png")}
    # 孤儿 = 磁盘上有、但**没有任何文档**引用的图（引用方含 README 与开发文档）
    used: set[str] = set()
    for rel in _SHOT_DOCS:
        doc = root / rel
        if doc.exists():
            used |= {
                Path(r).name
                for r in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", doc.read_text(encoding="utf-8"))
            }
    orphans = sorted(on_disk - used)
    ok("截图目录无孤儿文件（每张都被某份文档引用）",
       not orphans, f"未被引用={orphans}")
    ok("指南引用的截图目录存在且有内容",
       shots_dir.is_dir() and len(on_disk) > 0, str(shots_dir))

    # ---- 2. 指南里点名的按钮/提示文案必须真实存在于 desktop/ ----
    # 只挑「用户要照着点的控件文案」，避免把叙述性词汇也当断言对象
    button_claims = [
        "创建任务", "检测本页", "执行本子任务", "继续执行", "中断执行",
        "生成预览", "提交本次任务", "插入图片", "下载 PDF", "下载本页图片",
        "打开目录", "保存流程", "自动排版", "恢复默认", "选择拼版",
        "删除本页拼版", "复位本页版面", "在流程中启用图片拼版", "编辑图片",
    ]
    desktop_src = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in (root / "desktop").rglob("*.py")
        if "__pycache__" not in str(p)
    )
    absent = [c for c in button_claims if c not in desktop_src]
    ok("指南点名的按钮文案都存在于界面代码", not absent, f"界面里找不到={absent}")

    # 指南点名的**勾选框文案**必须与界面一字不差（2026-10-12 审计：
    # 手册曾写「整页模式：不调用 YOLO」，界面上实际是「整页模式：不做检测」）
    checkbox_claims = ["整页模式：不做检测"]
    bad_checkbox = [c for c in checkbox_claims if c not in desktop_src]
    ok("指南点名的勾选框文案与界面一致", not bad_checkbox, f"界面里找不到={bad_checkbox}")

    # 关键提示文案（用户最需要认出来的那句）
    ok("指南引用了去底色参数变更提示",
       "去底参数已修改" in guide and "去底参数已修改" in desktop_src,
       "提示文案在文档与代码之间不一致")

    # ---- 3. 四个步骤与命令名一一对应（指南不得漏步或臆造步骤）----
    for stage, label in (
        ("extract", "提取"), ("detect", "检测"),
        ("rembg", "去底色"), ("print", "PDF排版"),
    ):
        ok(f"指南覆盖 {label} 步骤（{stage}）",
           label in guide, f"指南里找不到「{label}」")

    # 步骤顺序必须与 desktop.store.STAGES 一致（指南若写反会误导用户）
    from desktop.store import STAGES

    ok("阶段顺序与实现一致", tuple(STAGES) == ("extract", "detect", "rembg", "print"),
       str(STAGES))
    # ⚠️ 找**小节标题**，不要用 guide.find(label)：四个步骤名在开头的总览句里
    # 也出现一次，用 find 会拿总览句的位置当顺序（标题写反也测不出来）。
    heads = [ln for ln in guide.splitlines() if ln.startswith("## ")]
    positions = []
    for label in ("提取图片", "检测文本框", "图片去底色", "PDF排版"):
        found = [i for i, head in enumerate(heads) if label in head]
        positions.append(found[0] if found else -1)
    ok("指南里四个步骤的叙述顺序正确",
       all(p >= 0 for p in positions) and positions == sorted(positions),
       f"{positions}（-1=该步骤没有小节标题）")

    # ---- 4. 指南必须被索引进文档树（否则用户找不到）----
    for index in ("README.md", "docs/README.md", "docs/dev/gui/readme.md"):
        text = (root / index).read_text(encoding="utf-8")
        ok(f"{index} 索引了用户操作手册", "user-guide.md" in text, f"{index} 未收录")

    # ---- 5. 指南必须写明截图出处（读者要知道示范的是哪本书）----
    ok("指南写明了演示所用的古籍", "龍譚精舍叢刻" in guide,
       "指南未说明截图取自哪本古籍")

    # 旧演示书名不应残留在**指南**里（换成真实古籍后最容易漏改的地方）。
    stale_books = ["论语·学而篇", "孟子·梁惠王章句", "诗经·国风", "D:/samples/"]
    leftovers = [s for s in stale_books if s in guide]
    ok("指南无旧演示数据残留", not leftovers, f"残留={leftovers}")

    # ---- 6. 手册里不许出现技术说明（2026-09-19 按用户要求清理过一次）----
    # 读者是不懂命令行的使用者：内部文件名、旧版本行为、配置字段、实现口径、
    # 截图工具说明，全部该留在 docs/dev/gui/user-guide-and-shots.md。
    # 判断标准：**用户能不能照着一句话去做一件事**；不能就是技术说明。
    forbidden = {
        "boxes.json": "内部文件名",
        "print.json": "内部文件名",
        "stages/pdf": "内部路径",
        "title_position": "配置字段",
        "title_orientation": "配置字段",
        "docs/functions": "开发文档链接",
        "gui_shot.py": "退役截图工具名",
        "72 DPI": "旧版本行为",
        "user-guide-and-shots": "开发文档名",
        "gui-guide": "旧文件名",
    }
    hits = [f"{token}（{why}）" for token, why in forbidden.items() if token in guide]
    ok("用户操作手册里没有技术说明（内部文件名/旧行为/实现口径）",
       not hits, "命中=" + "; ".join(hits))

    # ---- 7. 步骤名纯中文；**参数标签「中文（键名）」**（用户 2026-09-23 口径）----
    # 两条不同的规矩，别混：
    # ① **顶部四个步骤名不要英文**（「提取图片 (extract)」→「提取图片」）；
    # ② **参数标签要中文在前、键名放括号里**（「缩放因子（zoom）」）——参数与命令行
    #    一一对应，纯中文有时说不清指的是哪个；带单位的写成「中文(单位)（键名）」。
    # 唯一与键名无关的放行项是**格式名 PDF** 与**单位 mm**。
    from desktop.store import STAGE_LABELS

    allowed = {"PDF"}
    bad_labels = {
        key: words for key, words in (
            (k, re.findall(r"[A-Za-z]+", v)) for k, v in STAGE_LABELS.items()
        ) if set(words) - allowed
    }
    ok("四个步骤名只用中文（允许格式名 PDF）", not bad_labels, str(bad_labels))

    panels_src = (root / "desktop" / "components" / "panels")
    titles = []
    row_labels: list[tuple[str, str]] = []   # (文件, 标签)
    check_texts: list[tuple[str, str]] = []
    for py in sorted(panels_src.glob("*.py")):
        src = py.read_text(encoding="utf-8")
        titles += re.findall(r'^\s{4}title = "([^"]+)"', src, re.M)
        row_labels += [
            (py.name, t) for t in re.findall(r'_add_row\(\s*form,\s*"([^"]+)"', src)
        ]
        check_texts += [
            (py.name, t) for t in re.findall(r'CheckBox\("([^"]+)"\)', src)
        ]

    def _bare_latin(text: str) -> list[str]:
        """括号**外面**的英文词 —— 键名必须待在括号里，不许裸着写。"""
        outside = re.sub(r"（[^）]*）|\([^)]*\)", "", text).replace("PDF", "")
        return re.findall(r"[A-Za-z][A-Za-z_]*", outside)

    latin_titles = [t for t in titles if _bare_latin(t)]
    bare = [f"{f}:{t}" for f, t in row_labels + check_texts if _bare_latin(t)]
    ok("面板标题不含英文键名（格式名 PDF 例外）",
       not latin_titles, str(latin_titles))
    ok("参数标签/勾选项里的英文一律待在括号里（不出现裸英文）",
       not bare, str(bare))

    # 第一步、第三步的参数与命令行一一对应 → 每个标签都必须带（键名）
    keyed_panels = {"extract_panel.py", "rembg_panel.py"}
    missing_key = [f"{f}:{t}" for f, t in row_labels if f in keyed_panels and "（" not in t]
    ok("第一步/第三步的参数标签都带（键名）", not missing_key, str(missing_key))
    ok("面板标题与标签都有内容（别把扫描写成永远为空而假绿）",
       len(titles) >= 4 and len(row_labels) >= 8,
       f"titles={len(titles)} labels={len(row_labels)}")

    # 手册参数表与界面用同一套格式：新写法必须在、旧的裸键名写法不许残留
    expected = ["缩放因子（zoom）", "目标清晰度（dpi）", "输出格式（ext）",
                "快速模式（quick）", "页码范围（pages）",
                "区域模式（area）", "边距(mm)（border）", "输出类型（type）",
                "阈值偏移（offset）", "保留印章（seal）", "印章彩色（sealcolor）"]
    missing_doc = [t for t in expected if t not in guide]
    ok("手册参数表用的是「中文（键名）」格式", not missing_doc,
       f"缺失={missing_doc}")
    legacy = ["缩放因子 zoom", "目标 DPI", "输出格式 ext", "快速模式 quick",
              "页码范围 pages", "area 区域模式", "border 边距", "type 输出类型",
              "offset 阈值偏移", "(seal)", "(sealcolor)"]
    left = [t for t in legacy if t in guide]
    ok("手册参数表已无「中文 + 参数键名」混排", not left, f"残留={left}")

    # ---- 8. 面板标题里的步骤名必须与手册标题一致（改一处漏一处会立刻红）----
    from desktop.components.panels.detect_panel import DetectPanel
    from desktop.components.panels.extract_panel import ExtractPanel
    from desktop.components.panels.print_panel import PrintPanel
    from desktop.components.panels.rembg_panel import RembgPanel

    for panel in (ExtractPanel, DetectPanel, RembgPanel, PrintPanel):
        ok(f"面板标题「{panel.title}」与步骤名一致（{panel.stage}）",
           panel.title == STAGE_LABELS[panel.stage],
           f"面板={panel.title!r} vs 步骤名={STAGE_LABELS[panel.stage]!r}")

    # ---- 9. 用字统一：手册与界面代码不得再出现旧写法「图片拼板」----
    # 2026-10-12 统一为「图片拼版」（流程节点/手册标题/README 同名）；
    # 老流程图的兼容别名留在 bpmn_diagram.STAGE_ALIASES（唯一放行点），
    # 但**新文本**不许再写板。
    alias_line = re.compile(r'"图片拼板"\s*:\s*"imposition"')
    mixed = []
    for p in (root / "desktop").rglob("*.py"):
        if "__pycache__" in str(p):
            continue
        bad = [
            i + 1 for i, line in enumerate(p.read_text(encoding="utf-8").splitlines())
            if "图片拼板" in line and not alias_line.search(line)
        ]
        if bad:
            mixed.append(f"{p.relative_to(root)}:{bad}")
    ok("界面代码无旧写法「图片拼板」（别名表除外）", not mixed, str(mixed))
    ok("用户手册无旧写法「图片拼板」", "图片拼板" not in guide,
       "手册里仍写着「图片拼板」")
