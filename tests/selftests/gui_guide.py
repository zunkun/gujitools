# -*- coding: utf-8 -*-
"""用户操作手册自测：文档、截图、界面控件三者不得互相脱节。

背景：`docs/guide/user-guide.md` 是给最终用户看的操作手册，它最容易悄悄失效：

1. **引用的截图文件不存在** —— 重命名界面或换目录后，文档里全是裂图；
2. **写到的按钮文案在界面上找不到** —— 改了按钮文字，用户按图索骥点不着；
3. **截图生成脚本引用的控件名在面板上不存在** —— `gui_shot.py --guide`
   只为截图而写，跑挂了没人发现（`--guide` 不是主自测的一部分）。

本模块把这三条钉住。所有断言都是「文档说的 ↔ 代码写的 ↔ 磁盘上有的」三方对照，
不涉及像素比对（那需要基线图，代价高且对字体敏感）。
"""

NAME = "gui_guide"
DEPENDS: list[str] = []
TITLE = "用户操作手册一致性"


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

    # ---- 1. 指南里引用的每个截图都真实存在 ----
    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", guide)
    ok("指南引用了截图", len(refs) > 0, f"引用数={len(refs)}")
    missing = [r for r in refs if not (guide_path.parent / r).exists()]
    ok("指南引用的截图全部存在（无裂图）", not missing, f"缺失={missing}")

    # 截图目录里不应有「文档没用到」的孤儿图（多半是改名后漏改文档）
    shots_dir = guide_path.parent / "screenshots" / "guide"
    on_disk = {p.name for p in shots_dir.glob("*.png")}
    used = {Path(r).name for r in refs}
    orphans = sorted(on_disk - used)
    ok("操作截图目录无孤儿文件（每张都被文档引用）",
       not orphans, f"未被引用={orphans}")
    ok("指南引用的截图目录存在且有内容",
       shots_dir.is_dir() and len(on_disk) > 0, str(shots_dir))

    # ---- 2. 指南里点名的按钮/提示文案必须真实存在于 desktop/ ----
    # 只挑「用户要照着点的控件文案」，避免把叙述性词汇也当断言对象
    button_claims = [
        "导入 PDF", "检测本页", "执行本子任务", "继续执行", "中断执行",
        "生成预览", "提交本次任务", "恢复默认配置", "放弃本次修改", "插入图片",
        "下载 PDF", "打开目录",
    ]
    desktop_src = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in (root / "desktop").rglob("*.py")
        if "__pycache__" not in str(p)
    )
    absent = [c for c in button_claims if c not in desktop_src]
    ok("指南点名的按钮文案都存在于界面代码", not absent, f"界面里找不到={absent}")

    # 关键提示文案（用户最需要认出来的那句）
    ok("指南引用了去底色参数变更提示",
       "去底参数已修改" in guide and "去底参数已修改" in desktop_src,
       "提示文案在文档与代码之间不一致")

    # ---- 3. 截图脚本必须能支撑指南（不真跑，只做结构性校验）----
    shot_src = (root / "tests" / "gui_shot.py").read_text(encoding="utf-8")
    ok("截图脚本提供 --guide 模式", "--guide" in shot_src, "缺少指南截图入口")
    ok("截图脚本支持 --guide", "shoot_guide" in shot_src)

    # 脚本里每个 snapshot 文件名都应与磁盘上的截图对应（少一张就是文档引了不存在的图）
    script_names = set(re.findall(r'"(s\d-[^"]+\.png)"', shot_src))
    ok("截图脚本产出的文件名与磁盘一致",
       script_names == on_disk,
       f"仅脚本有={sorted(script_names - on_disk)} 仅磁盘有={sorted(on_disk - script_names)}")

    # ---- 4. 四个步骤与命令名一一对应（指南不得漏步或臆造步骤）----
    for stage, label in (
        ("extract", "提取"), ("detect", "检测"),
        ("rembg", "去底色"), ("print", "生成 PDF"),
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
    for label in ("提取图片", "检测文本框", "图片去底色", "生成 PDF"):
        found = [i for i, head in enumerate(heads) if label in head]
        positions.append(found[0] if found else -1)
    ok("指南里四个步骤的叙述顺序正确",
       all(p >= 0 for p in positions) and positions == sorted(positions),
       f"{positions}（-1=该步骤没有小节标题）")

    # ---- 5. 指南必须被索引进文档树（否则用户找不到）----
    # ⚠️ 指南已从 docs/gui/ 迁到 docs/guide/；技术细节留在 docs/dev/gui/。
    # 这里断言「三份索引都收录了指南」，一旦目录再迁，索引漏改就会红。
    for index in ("README.md", "docs/README.md", "docs/dev/gui/readme.md"):
        text = (root / index).read_text(encoding="utf-8")
        ok(f"{index} 索引了用户操作手册", "user-guide.md" in text, f"{index} 未收录")

    # ---- 6. 演示数据契约：真实古籍优先 + 演示页常量 ----
    ok("截图脚本会优先使用真实古籍 PDF",
       "find_real_pdf" in shot_src and "REAL_PDF_PREFERRED" in shot_src,
       "缺少真实 PDF 探测逻辑")
    ok("截图脚本保留占位图回退（换机器也能跑）",
       "make_fake_page_image" in shot_src and "演示数据回退" in shot_src,
       "缺少回退路径")

    # 演示页常量必须存在，且指南里提到的页码要与它一致
    page_match = re.search(r"^DEMO_PAGE\s*=\s*(\d+)", shot_src, re.M)
    ok("截图脚本定义了 DEMO_PAGE 常量", page_match is not None,
       "找不到 DEMO_PAGE，演示页会失控")
    if page_match:
        demo_page = page_match.group(1)
        # ⚠️ 用户明确要求演示不用第 3 页（版面偏空），第 4 页是当前选择。
        # 这条断言防止有人手滑改回去。
        ok("演示页不是第 3 页", demo_page != "3",
           f"DEMO_PAGE={demo_page}，第 3 页版面偏空不适合做演示")
        ok("指南写明的演示页与 DEMO_PAGE 一致",
           f"第 {demo_page} 页" in guide,
           f"DEMO_PAGE={demo_page}，但指南里找不到「第 {demo_page} 页」")

    # 旧演示书名不应残留在**指南**里（换成真实古籍后最容易漏改的地方）。
    # ⚠️ 只查指南，不查 gui_shot.py —— 脚本里其余两条任务（做到一半的、刚导入的）
    # 故意用占位路径与合成书名，那是设计，不是残留。
    stale_books = ["论语·学而篇", "孟子·梁惠王章句", "诗经·国风", "D:/samples/"]
    leftovers = [s for s in stale_books if s in guide]
    ok("指南无旧演示数据残留", not leftovers, f"残留={leftovers}")

    # 指南应当点名真实演示古籍（否则读者不知道示范的是哪本书）
    ok("指南写明了演示所用的古籍", "龍譚精舍叢刻" in guide,
       "指南未说明截图取自哪本古籍")

    # ---- 7. 灌入的演示数据必须自洽：检测框换算后要落在缩略图内 ----
    # 背景（真实踩过的坑）：灌演示数据时把 `image_size` 记成了**缩略图**尺寸，
    # 而检测框是**阶段图**坐标。`_page_thumb_for` 用
    # `sx = 缩略图宽 / image_size 宽` 换算框；sx 恒等于 1 时，框会按阶段图
    # 坐标去裁缩略图 → 越界裁出纯白，界面表现为「左侧缩略图一直没加载出来」。
    # 这类故障不抛异常、不留日志，只有看图才发现，所以必须用行为断言钉住。
    _assert_demo_thumbs_not_blank(ctx, root, ok)



    # ---- 8. 手册里不许出现技术说明（2026-09-19 按用户要求清理过一次）----
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
        "gui_shot.py": "截图工具（维护说明）",
        "72 DPI": "旧版本行为",
        "user-guide-and-shots": "开发文档名",
        "gui-guide": "旧文件名",
    }
    hits = [f"{token}（{why}）" for token, why in forbidden.items() if token in guide]
    ok("用户操作手册里没有技术说明（内部文件名/旧行为/实现口径）",
       not hits, "命中=" + "; ".join(hits))

    # ---- 9. 步骤名纯中文；**参数标签「中文（键名）」**（用户 2026-09-23 口径）----
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

    # ---- 10. 面板标题里的步骤名必须与手册标题一致（改一处漏一处会立刻红）----
    from desktop.components.panels.detect_panel import DetectPanel
    from desktop.components.panels.extract_panel import ExtractPanel
    from desktop.components.panels.print_panel import PrintPanel
    from desktop.components.panels.rembg_panel import RembgPanel

    for panel in (ExtractPanel, DetectPanel, RembgPanel, PrintPanel):
        ok(f"面板标题「{panel.title}」与步骤名一致（{panel.stage}）",
           panel.title == STAGE_LABELS[panel.stage],
           f"面板={panel.title!r} vs 步骤名={STAGE_LABELS[panel.stage]!r}")

def _assert_demo_thumbs_not_blank(ctx, root, ok) -> None:
    """跑一遍演示数据灌入 + 缩略图合成，确认没有「全白缩略图」。

    不复用 GUI，只走数据层：TaskStore + PageListMixin._page_thumb_for +
    compose_region_output。这样在 offscreen 无界面环境下也能跑。
    """
    import os
    import tempfile
    from pathlib import Path

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtGui import QImageReader

    from desktop.pages.taskdetail.manifest import PageListMixin
    from desktop.store import TaskStore
    from desktop.workers.preview_worker import compose_region_output

    sys_path_added = False
    try:
        import gui_shot
    except ImportError:
        import sys

        tests_dir = str(root / "tests")
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
            sys_path_added = True
        try:
            import gui_shot
        except ImportError as exc:
            ok("演示数据自检可加载 gui_shot", False, f"{exc!r}")
            return

    root_tmp = Path(tempfile.mkdtemp(prefix="guji_guide_chk_"))
    store = TaskStore(root_tmp)
    task_ids = gui_shot.seed(store)
    task_id = task_ids[0]

    class _Probe(PageListMixin):
        def __init__(self, store_, task_id_, pdf_page_count):
            self.store = store_
            self.task_id = task_id_
            self.pdf_page_count = pdf_page_count

    probe = _Probe(store, task_id, 6)

    extract_dir = Path(store.extract_output_dir(task_id))
    pages = sorted(extract_dir.glob("[0-9][0-9][0-9].*"))
    ok("演示数据灌入了阶段图", len(pages) > 0,
       f"extract 目录为空：{extract_dir}")
    if not pages:
        return

    blank: list[str] = []
    checked = 0
    for page_file in pages[:3]:
        key = page_file.stem
        meta = store.image_size(task_id, key)
        if not meta:
            blank.append(f"{key}(无 image_size)")
            continue
        entry = store.detect_boxes_entry(task_id, key)
        if not entry:
            continue
        boxes, _origin = entry
        for box in boxes[:2]:
            if not box:
                continue
            spec = probe._page_thumb_for(str(page_file), box, 1, None)
            if not isinstance(spec, dict):
                continue
            eff = spec.get("effect") or {}
            reader = QImageReader(spec["path"])
            reader.setAutoTransform(True)
            image = reader.read()
            if image.isNull():
                blank.append(f"{key}(缩略图读取失败)")
                continue
            outs = compose_region_output(
                image, eff.get("boxes", []), int(eff.get("area", 1)),
                eff.get("border"), dpi=int(eff.get("dpi", 300)),
            )
            checked += 1
            for out in outs:
                if out.isNull() or out.width() < 2 or out.height() < 2:
                    blank.append(f"{key}(合成结果无效)")
                    continue
                # 采样判断是否几乎全白：真版面文字密，深色占比通常 >10%
                total = dark = 0
                for y in range(0, out.height(), 5):
                    for x in range(0, out.width(), 5):
                        c = out.pixelColor(x, y)
                        total += 1
                        if c.red() < 200 and c.green() < 200 and c.blue() < 200:
                            dark += 1
                ratio = dark * 100 // max(total, 1)
                if ratio < 2:
                    blank.append(f"{key}(深色仅 {ratio}%，疑越界裁白)")

    ok("演示缩略图合成有可校验样本", checked > 0,
       "没有检测框可用，检查 save_detect_boxes 是否写入")
    ok("演示缩略图无全白（检测框与缩略图坐标自洽）", not blank,
       f"异常={blank}")

    if sys_path_added:
        import sys

        sys.path.remove(str(root / "tests"))

