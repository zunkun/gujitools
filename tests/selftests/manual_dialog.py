# -*- coding: utf-8 -*-
"""桌面端「用户手册」入口的自测。

方案变更（2026-09-17）：原先是方案 A——``QTextBrowser`` + ``QTextDocument``
直接吃 Markdown。实测下来 Qt 那套富文本引擎对 GFM 的支持只是子集，表格、
围栏代码块、深层嵌套列表的排版都很勉强，长文档读起来发闷；而 ``setHtml()``
走的是同一条渲染管线，换不来真正的样式自由度。

现改为方案 C：**运行时用 Python ``markdown`` 库把 ``docs/guide/*.md`` 转成
完整 HTML（内嵌 CSS），写到临时文件后用系统默认浏览器打开**。零二进制依赖，
完整 GFM，且没有「改了 Markdown 要重新生成产物」的构建步骤。

本护栏因此从「断言 QTextDocument 渲染结果」改为「断言生成的 HTML」，
并钉住新方案的关键不变量——尤其是 **``<base>`` 必须指向手册目录且带结尾
斜杠**，否则 12 张相对路径截图会相对临时文件解析成碎图（这就是旧方案里
baseUrl 配错的同款坑，只是换了层皮）。
"""

import re
import urllib.parse

NAME = "manual_dialog"
DEPENDS: list[str] = []
TITLE = "桌面端用户手册（Markdown → HTML → 系统浏览器）"


def run(ctx) -> None:
    from pathlib import Path

    from tests.selftests._context import ok

    root = Path(__file__).resolve().parents[2]

    # ---- 1. 入口代码必须存在 ----
    help_dialog_py = root / "desktop" / "ui" / "help_dialog.py"
    ok("desktop/ui/help_dialog.py 存在", help_dialog_py.exists(), str(help_dialog_py))

    # 任务列表页 PageHeader 必须接出按钮
    tasklist_page = root / "desktop" / "pages" / "tasklist" / "page.py"
    ok("任务列表页存在", tasklist_page.exists(), str(tasklist_page))
    if tasklist_page.exists():
        page_src = tasklist_page.read_text(encoding="utf-8")
        ok("任务列表页 import open_manual",
           "from desktop.ui.help_dialog import open_manual" in page_src,
           "缺导入")
        ok("任务列表页有 _open_manual 处理器",
           "def _open_manual" in page_src,
           "缺处理函数")
        ok("PageHeader.actions 上接了「用户手册」按钮",
           "用户手册" in page_src and "header.actions.addWidget(manual_button)" in page_src,
           "接线缺失")
        ok("不再持有 ManualDialog 实例（已改为浏览器渲染）",
           "ManualDialog" not in page_src,
           "仍残留 ManualDialog 引用")

    # ---- 1b. 「用户手册」按钮的图标：带圆圈的问号（自绘 SVG）----
    # 内置 FIF.QUESTION 是**被裁到边框上的裸问号**（内置 HELP 更是糊成一团），
    # 且 qfluentwidgets 对「path() 返回 SVG 源码」的支持是残缺的：
    # `icon()` 只在 `path.endswith('.svg') and color` 时包 SvgIconEngine，
    # `render()` 只在 endswith('.svg') 时走内存渲染 —— 其余一律按**文件名**
    # 处理，得到空图标。而 PushButton.paintEvent 在 icon().isNull() 时直接
    # return，界面上就只剩文字、图标凭空消失（只重写一个方法就会踩到）。
    # 静态检查抓不到，下面全是行为断言。
    icons_py = root / "desktop" / "ui" / "icons.py"
    ok("desktop/ui/icons.py 存在（自绘图标）", icons_py.exists(), str(icons_py))
    if tasklist_page.exists():
        ok("「用户手册」用自绘带圆圈问号，不是内置裸问号 FIF.QUESTION",
           "HELP_CIRCLE" in page_src and "FIF.QUESTION" not in page_src,
           "仍在使用 FIF.QUESTION")

    try:
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QImage, QPainter, QPixmap

        from desktop.ui.icons import HELP_CIRCLE
    except Exception as exc:
        ok("desktop.ui.icons 可导入", False, f"{exc!r}")
        return

    def _ink(img, n=32) -> int:
        return sum(1 for y in range(n) for x in range(n)
                   if img.pixelColor(x, y).alpha() > 40)

    ok("desktop.ui.icons 可导入", True, "")
    _ic = HELP_CIRCLE.icon()
    ok("HELP_CIRCLE.icon() 非空（空图标 → 按钮只剩文字）", not _ic.isNull(), "")
    _pma = _ic.pixmap(32, 32)
    ok("HELP_CIRCLE 能出图", not _pma.isNull(), "")
    ok("HELP_CIRCLE 有可见笔画（不是空白画布）",
       _ink(_pma.toImage().convertToFormat(QImage.Format_ARGB32)) > 100,
       "画出来是空的")

    # render() 才是按钮自绘真正走的那条路径（paintEvent → _drawIcon → render）
    _canvas = QPixmap(32, 32)
    _canvas.fill(Qt.transparent)
    _painter = QPainter(_canvas)
    HELP_CIRCLE.render(_painter, QRectF(0, 0, 32, 32))
    _painter.end()
    _rimg = _canvas.toImage().convertToFormat(QImage.Format_ARGB32)
    ok("HELP_CIRCLE.render() 也画得出（按钮自绘走这条）", _ink(_rimg) > 100,
       f"不透明像素={_ink(_rimg)}")
    # 结构：必须是「环」而不是实心饼（圆内镂空），且外圈确实有笔画
    ok("图标是圆环不是实心饼（圆内镂空）",
       _rimg.pixelColor(9, 9).alpha() < 40,
       f"圆内 alpha={_rimg.pixelColor(9, 9).alpha()}")
    ok("外圈有笔画", _rimg.pixelColor(16, 3).alpha() > 40,
       f"圆环顶部 alpha={_rimg.pixelColor(16, 3).alpha()}")

    # ---- 2. 文档源文件必须在 ----
    guide_dir = root / "docs" / "guide"
    ok("docs/guide/ 存在", guide_dir.is_dir(), str(guide_dir))
    ok("docs/guide/gui-guide.md 存在",
       (guide_dir / "gui-guide.md").exists(),
       "操作指南缺失")
    ok("docs/guide/cli.md 存在",
       (guide_dir / "cli.md").exists(),
       "命令行说明缺失")
    ok("docs/guide/screenshots/guide/*.png 至少 12 张",
       sum(1 for _ in (guide_dir / "screenshots" / "guide").glob("*.png")) >= 12,
       "截图缺失")

    # ---- 2b. ⚠️ requirements.txt 必须包含手册用到的第三方包 ----
    # 本轮真正的根因：build.py 当时因为怕 pip 重解析把 CPU 版 torch 顶掉，
    # **故意不用 requirements.gui.txt 整表**，只手写「requirements.txt 之外的
    # GUI 增量」。往 gui 那份里加 markdown 于是对打包毫无作用——yolobuild 环境
    # 里没有 markdown，`collect_submodules('markdown')` 对缺失的包**静默返回
    # 空**，PyInstaller 全程不报错，只有用户点了「用户手册」才看到退化的
    # <pre> 原始 markdown。
    # 现已收敛成一份 requirements.txt，这里从 help_dialog.py 的 import 反推
    # 它依赖哪些第三方顶层包，逐个比对 requirements.txt。
    req_txt = root / "requirements.txt"
    req_src = req_txt.read_text(encoding="utf-8") if req_txt.exists() else ""
    ok("requirements.txt 存在", bool(req_src), str(req_txt))
    ok("不再有 requirements.gui.txt（依赖只有一份，避免两处事实来源）",
       not (root / "requirements.gui.txt").exists(),
       "requirements.gui.txt 又回来了 —— 两份清单必然漂移")

    import ast
    import sys

    help_src = help_dialog_py.read_text(encoding="utf-8")
    third_party: set[str] = set()
    for node in ast.walk(ast.parse(help_src)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                third_party.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            third_party.add(node.module.split(".")[0])
    local_roots = {"desktop", "utils", "core", "cli", "functions", "config", "tests"}
    third_party -= local_roots
    third_party -= set(sys.stdlib_module_names)
    # 编辑器/类型检查用的条件导入不算运行时依赖
    third_party -= {"typing_extensions"}

    ok("反推出 help_dialog 依赖的第三方包（不全为空）",
       bool(third_party),
       f"解析结果={sorted(third_party)}")

    for pkg in sorted(third_party):
        ok(f"requirements.txt 含 {pkg}（否则打包后手册退化）",
           re.search(rf"^\s*{re.escape(pkg)}[\s><=]", req_src, re.M | re.I) is not None,
           f"requirements.txt 缺 {pkg}")

    # build.py 的环境自检探针必须覆盖同一批包：探针通过就直接 return，
    # 后面的 pip install 一次都不跑 —— 漏一个包，老环境永远装不上它。
    build_py = root / "build.py"
    build_src = build_py.read_text(encoding="utf-8") if build_py.exists() else ""
    ok("build.py 存在", bool(build_src), str(build_py))
    for pkg in sorted(third_party):
        ok(f"build.py 环境自检探针含 {pkg}",
           re.search(rf"import[^;\"']*\b{re.escape(pkg)}\b", build_src) is not None,
           f"探针缺 {pkg} —— 已有 yolobuild 环境会跳过安装")

    # ---- 3. guji.spec 必须把 docs/guide 打进 GUI 安装包 ----
    spec = root / "guji.spec"
    spec_src = spec.read_text(encoding="utf-8") if spec.exists() else ""
    ok("guji.spec 存在", spec.exists(), str(spec))
    ok("gui_datas 含 docs/guide 目录",
       "('docs/guide', 'docs/guide')" in spec_src,
       "spec 未打包 docs/guide —— frozen 模式手册找不到文件")
    # ⚠️ 手册的图片在 docs/guide/screenshots/guide/ 子目录下。spec 里写的是
    # 目录元组 `('docs/guide', 'docs/guide')`，靠 PyInstaller 的 os.walk()
    # 递归收集（见 PyInstaller/building/utils.py 的 format_binaries_and_datas）——
    # 所以**不需要**额外写一条 screenshots 的 datas，但也绝不能把这条改成
    # 只收 *.md 的 glob，否则 12 张 PNG 全丢。这条断言钉住「按目录收、不按
    # 后缀收」。
    ok("gui_datas 按整个目录收 docs/guide（不是只收 *.md）",
       re.search(r"\(\s*'docs/guide'\s*,\s*'docs/guide'\s*\)", spec_src) is not None
       and not re.search(r"\(\s*'docs/guide[^']*\*", spec_src),
       "spec 里 docs/guide 的 datas 被改成了 glob —— 子目录截图会丢")

    pre_gui_datas = spec_src.split("gui_datas =")[0]
    # 只数元组条目（以 ( 开头且含 'docs/guide'），不要把注释也统计进来
    cli_docs_guide = sum(
        1 for ln in pre_gui_datas.splitlines()
        if ln.lstrip().startswith("(") and "'docs/guide'" in ln
    )
    ok("CLI datas 没有 docs/guide（避免给 CLI 重复打资源）",
       cli_docs_guide == 0,
       f"CLI datas 多带了 {cli_docs_guide} 条 docs/guide")

    # ---- 4. 真跑一遍 HTML 生成：这是行为断言，静态检查抓不到 ----
    # ⚠️ 一定要断言「扩展类能静态导入」而不是只断言 import markdown：
    # markdown 按字符串名加载扩展走的是 entry point（importlib.metadata），
    # frozen 模式下 dist-info 未必打包进去，源码模式正常、一打包就碎。
    # help_dialog 因此改成静态 import 扩展类，这条护栏就是钉住这件事。
    try:
        import markdown

        from markdown.extensions.fenced_code import FencedCodeExtension
        from markdown.extensions.sane_lists import SaneListExtension
        from markdown.extensions.tables import TableExtension
    except ImportError as exc:
        ok("markdown 及其 GFM 扩展可静态导入", False, f"{exc!r}（pip install markdown）")
        return

    ok("markdown 及其 GFM 扩展可静态导入（frozen 模式才稳）",
       callable(markdown.markdown)
       and callable(TableExtension)
       and callable(FencedCodeExtension)
       and callable(SaneListExtension),
       "扩展类静态导入失败，打包后手册会碎")

    try:
        from desktop.ui.help_dialog import (
            MANUAL_ENTRIES,
            generate_manual_html,
            manual_dir,
        )
    except Exception as exc:
        ok("help_dialog 可导入", False, f"{exc!r}")
        return

    ok("help_dialog 可导入", True, "")
    ok("MANUAL_ENTRIES 至少包含 gui + cli",
       len(MANUAL_ENTRIES) >= 2,
       f"entries={MANUAL_ENTRIES}")
    ok("默认条目为 gui（桌面端操作）",
       MANUAL_ENTRIES[0][0] == "gui",
       f"首项={MANUAL_ENTRIES[0]}")

    html_path = generate_manual_html()
    ok("generate_manual_html 产出了文件", html_path.exists(), str(html_path))
    html = html_path.read_text(encoding="utf-8")

    # ---- 5. 两份指南都得**真正**渲染出来 ----
    # ⚠️ 断言「『桌面端操作指南』这串字在产物里」是不够的：fallback 兜底
    # 把它原样塞进 <pre>{escaped}</pre> 也会通过。必须再断言「# 原文 / ** 加粗
    # / 围栏 ``` 三种 markdown 标记都不在产物里」——否则 `_md_to_fragment`
    # 在 markdown 库不可用时静默走兜底，产出的 HTML 浏览器渲染出来还是
    # 原始 markdown 文本（用户两轮反馈的核心症状），护栏却一路绿灯。
    ok("产物含 gui-guide.md 的标题「桌面端操作指南」",
       "桌面端操作指南" in html, "")
    ok("产物含 cli.md 的标题「CLI 使用说明」",
       "CLI 使用说明" in html, "")

    # ⚠️ 这条是上一轮漏掉的硬断言：markdown 真的转了，原始符号必须消失
    # 注意：必须**剥掉代码块**再查，否则 ``# 操作指南配图`` 之类的 shell 注释
    # 会误判。代码块外的 `# `（行首 + 空格 + 标题）才是 markdown 标题原文。
    gui_section = re.search(
        r'id="tab-gui"[^>]*>(.*?)</section>', html, re.S
    ).group(1)
    cli_section = re.search(
        r'id="tab-cli"[^>]*>(.*?)</section>', html, re.S
    ).group(1)

    def _strip_code_blocks(s: str) -> str:
        # 围栏代码块 ```...```（可能是 <pre><code>...</code></pre> 或裸转义）
        s = re.sub(r'<pre>.*?</pre>', '', s, flags=re.S)
        return s

    gui_visible = _strip_code_blocks(gui_section)
    cli_visible = _strip_code_blocks(cli_section)

    ok("gui 段落不含原始 '# ' 标题符号（markdown 真的转了）",
       not re.search(r'(?<!sub)# [^\s#]', gui_visible),
       "fallback 兜底被触发，浏览器会显示原始 markdown")
    ok("gui 段落不含 '**...**' 加粗原文（markdown 真的转了）",
       "**" not in gui_visible,
       "fallback 兜底被触发")
    ok("gui 段落不含 '```' 围栏标记（markdown 真的转了）",
       "```" not in gui_visible,
       "fallback 兜底被触发")
    ok("gui 段落不含 <pre>{escaped}</pre> 兜底模板字面量",
       "{escaped}" not in gui_section,
       "fallback 模板未替换")
    ok("gui 段落含真实 <h1>",
       re.search(r'<h1[^>]*>[^<]*桌面端操作指南', gui_section) is not None,
       "<h1> 缺失")
    # cli 段落同样不能被兜底（两份手册共用同一条转换路径，但历史上
    # 出现过「只有一份用了真解析」的偏差，所以两边都查）
    ok("cli 段落不含 '**...**' 加粗原文（markdown 真的转了）",
       "**" not in cli_visible,
       "fallback 兜底被触发")
    ok("cli 段落不含 <pre>{escaped}</pre> 兜底模板字面量",
       "{escaped}" not in cli_section,
       "fallback 模板未替换")
    ok("cli 段落含真实 <h1>",
       re.search(r'<h1[^>]*>[^<]*CLI 使用', cli_section) is not None,
       "<h1> 缺失")

    # ---- 6. GFM 能力：表格与围栏代码块 ----
    ok("表格已渲染（含 <table>）", "<table" in html, "")
    ok("围栏代码块已渲染（含 <pre>）", "<pre" in html, "")

    # ---- 7. 12 张截图必须都被引用（cli.md 没有图，所以总数就是 gui 的 12 张）----
    img_count = len(re.findall(r"<img ", html))
    ok("12 张截图都被引用", img_count == 12, f"实际={img_count}")

    # ⚠️ src 必须是**绝对的、已百分号编码的** file:// URL，不能只靠 <base>
    #    让浏览器自己拼：中文文件名（s0-任务列表.png）走 base 拼接时浏览器
    #    未必正确编码，实测页面「有框无图」。曾因此返工，故钉死。
    img_srcs = re.findall(r'<img[^>]*\ssrc="([^"]+)"', html)
    relative = [s for s in img_srcs if not s.startswith("file:///")]
    ok("img src 全是绝对 file:// URL（不依赖 <base> 拼接）",
       bool(img_srcs) and not relative,
       f"残留相对路径: {relative[:2]}")

    hits = 0
    for s in img_srcs:
        local = Path(urllib.parse.unquote(s.replace("file:///", "")))
        hits += local.is_file()
    ok("每张图的绝对 URL 都能命中真实文件",
       hits == len(img_srcs) == 12,
       f"命中 {hits}/{len(img_srcs)}")

    # ---- 8. ⚠️ <base> 是图片能加载的唯一保证 ----
    # 不加 base（或少了结尾斜杠），screenshots/guide/*.png 会相对临时目录
    # 解析 → 12 张图全碎。这条是新方案里最容易被改坏的地方。
    m = re.search(r'<base href="([^"]+)"', html)
    base = m.group(1) if m else ""
    ok("存在 <base> 标签", bool(base), "缺 <base>，截图必然全碎")
    ok("base 是 file:// URL", base.startswith("file:///"), base)
    ok("base 指向 docs/guide/ 且带结尾斜杠（防截图全碎）",
       base.endswith("docs/guide/"),
       base or "<空>")
    ok("base 指向的手册目录真实存在",
       manual_dir().resolve().is_dir(),
       str(manual_dir()))

    # ---- 9. 分段开关与互链改写 ----
    ok("分段开关含 gui 标签", 'data-tab="gui"' in html, "")
    ok("分段开关含 cli 标签", 'data-tab="cli"' in html, "")
    ok("默认激活 gui 标签页",
       'class="tab active" data-tab="gui"' in html, "")
    # ⚠️ 互链改写要**测机制**，不能测「当前文档里恰好有这个链接」：
    # gui-guide.md 曾被整篇重写、[cli.md](cli.md) 那行被顺手删掉，护栏立刻红了
    # 但代码一点没坏——那是内容变动，不是回归。改成拿一段合成 markdown 喂
    # _md_to_fragment，直接断言改写规则生效。
    from desktop.ui.help_dialog import _md_to_fragment

    probe = _md_to_fragment("[命令行说明](cli.md)")
    ok("_md_to_fragment 把 cli.md 改写成 #tab-cli（机制断言）",
       'href="#tab-cli"' in probe,
       f"实际={probe!r}")
    ok("_md_to_fragment 不再输出指向 .md 的链接（浏览器会当纯文本）",
       'href="cli.md"' not in probe,
       f"实际={probe!r}")
    # 产物层面只做负向兜底：手册**彼此之间**的互链不许留 .md 形式
    # （指向 ../functions/*.md 的跨目录链接不在本手册体系内，不算违规——
    # 它是给 `guji help` 用的另一套文档，不在 MANUAL_ENTRIES 里）
    manual_md = {filename for _k, _l, filename in MANUAL_ENTRIES}
    stray = [
        h for h in re.findall(r'href="([^"]*\.md)"', html)
        if h.rsplit("/", 1)[-1] in manual_md
    ]
    ok("产物里手册互链没有残留 .md 形式",
       not stray,
       f"残留: {stray[:3]}")

    # ---- 10. 样式已注入 ----
    ok("CSS 已内嵌（含主题色令牌）", "#0E7C8B" in html, "没找到主题色 ACCENT")
    ok("CSS 含 img 宽度约束（防截图撑破视口）",
       "max-width: 100%" in html,
       "缺 img max-width，1500px 截图会撑出横向滚动条")

    # ---- 11. ⚠️ 文件名必须每次唯一，否则浏览器会缓存 file:// 页面 ----
    # 曾踩：固定文件名 guji_manual.html + 想靠 ?v= 查询串防缓存，结果 Windows
    # 上 webbrowser.open 走 os.startfile，查询串被当路径的一部分，地址栏里
    # 根本没有 ?v=，缓存照旧命中 → 用户看到的是几天前的旧内容。
    path_a = generate_manual_html()
    path_b = generate_manual_html()
    ok("每次生成的 HTML 文件名都不同（防浏览器缓存）",
       path_a != path_b and path_a.exists() and path_b.exists(),
       f"{path_a.name} vs {path_b.name}")

    # ---- 12. 指定 entry 时激活对应标签页 ----
    html_cli = generate_manual_html("cli").read_text(encoding="utf-8")
    ok("entry='cli' 时激活 cli 标签页",
       'class="tab active" data-tab="cli"' in html_cli,
       "默认标签页没跟着 entry 走")
