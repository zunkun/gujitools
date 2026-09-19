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

import base64
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
    ok("docs/guide/user-guide.md 存在",
       (guide_dir / "user-guide.md").exists(),
       "用户操作手册缺失")
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

    # ---- 3. 打包策略：**docs/guide 不进包**，手册改成构建期预生成的自包含 HTML ----
    # 方案演进（2026-09-19）：原先把 docs/guide 整目录（md + 6MB 截图）打进包、
    # 运行时再渲染。现在改成构建期渲染一次、截图内联成 data URI，产物只有一个
    # desktop/static/manual.html；md 与截图对最终用户没用，不再进安装包。
    spec = root / "guji.spec"
    spec_src = spec.read_text(encoding="utf-8") if spec.exists() else ""
    ok("guji.spec 存在", spec.exists(), str(spec))
    ok("gui_datas 不再打包 docs/guide（改由构建期预生成自包含手册）",
       "('docs/guide', 'docs/guide')" not in spec_src,
       "spec 仍在打包 docs/guide —— 安装包会白带 6MB 截图")
    ok("gui_datas 收 desktop/static（预生成的手册落在这里）",
       "('desktop/static', 'desktop/static')" in spec_src)
    # 只看代码行：注释里会解释"为什么不再收集 markdown"，别把注释当代码
    spec_code = "\n".join(
        ln for ln in spec_src.splitlines() if not ln.lstrip().startswith("#")
    )
    ok("excludes 排掉了 markdown（只有构建期渲染需要它）",
       "'markdown'" in spec_code
       and "collect_submodules('markdown')" not in spec_code,
       "spec 仍在收集 markdown")

    pre_gui_datas = spec_src.split("gui_datas =")[0]
    # 只数元组条目（以 ( 开头且含 'docs/guide'），不要把注释也统计进来
    cli_docs_guide = sum(
        1 for ln in pre_gui_datas.splitlines()
        if ln.lstrip().startswith("(") and "'docs/guide'" in ln
    )
    ok("CLI datas 从来没有 docs/guide（避免给 CLI 重复打资源）",
       cli_docs_guide == 0,
       f"CLI datas 多带了 {cli_docs_guide} 条 docs/guide")

    build_src = (root / "build.py").read_text(encoding="utf-8")
    ok("build.py 在构建流程里预生成手册",
       "build_manual_html" in build_src and "generate_static_manual" in build_src,
       "build.py 没有调用 generate_static_manual —— 打包版会退化成运行时渲染")
    ok("build.py 预生成的是自包含版本（落 desktop/static）",
       '"desktop" / "static"' in build_src.replace("_internal", ""),
       "预生成路径不在 desktop/static 下")

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
    # ⚠️ 断言「『用户操作手册』这串字在产物里」是不够的：fallback 兜底
    # 把它原样塞进 <pre>{escaped}</pre> 也会通过。必须再断言「# 原文 / ** 加粗
    # / 围栏 ``` 三种 markdown 标记都不在产物里」——否则 `_md_to_fragment`
    # 在 markdown 库不可用时静默走兜底，产出的 HTML 浏览器渲染出来还是
    # 原始 markdown 文本（用户两轮反馈的核心症状），护栏却一路绿灯。
    ok("产物含 user-guide.md 的标题「用户操作手册」",
       "用户操作手册" in html, "")
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
       re.search(r'<h1[^>]*>[^<]*用户操作手册', gui_section) is not None,
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

    # ---- 8. ⚠️ 绝对不要 <base>：片段链接会被解析到目录上 ----
    # 曾经为"让相对截图路径能解析"加过 <base href="file:///…/docs/guide/">，
    # 结果片段链接（#sec-8 这种）按 base 解析 → 点标题旁的 # 锚点等于打开
    # **docs/guide 目录**，浏览器直接把目录列表当页面显示（用户真的截了图来报）。
    # 图片不靠 base：开发模式写绝对 file:// URL（下面第 8b 节验），生产内联。
    ok("页面里没有 base 标签（有它就会把 #锚点 解析成目录 URL）",
       re.search(r"<base\b", html) is None,
       "出现了 base 标签 —— 点标题会跳到目录列表")
    # 旧 bug 的特征串：片段链接被解析到手册目录上（→ 浏览器列目录）
    ok("页面里没有指向目录的片段链接（旧 bug 的特征串）",
       "docs/guide/#" not in html and "guide/#" not in html)
    from desktop.ui import help_dialog as _hd8
    ok("标题锚点是纯片段链接（JS 里以 '#' 开头赋值，不经 base 解析）",
       "link.href = '#'" in _hd8._JS and "mark.href = '#'" in _hd8._JS)

    # ---- 8b. 开发模式的截图必须是绝对 file:// 且真能打开 ----
    # 没有 base 之后，图片路径只能靠绝对 URL——这条是 8 节的配套保证。
    dev_srcs = re.findall(r'<img[^>]*?\ssrc="([^"]+)"', html)
    ok("开发模式 12 张截图都是绝对 file:// URL",
       len(dev_srcs) == 12 and all(s.startswith("file:///") for s in dev_srcs),
       "; ".join(s[:36] for s in dev_srcs[:3]))
    ok("这些绝对 URL 都能命中真实文件",
       all(Path(urllib.parse.unquote(s[8:])).is_file() for s in dev_srcs),
       "; ".join(s[:60] for s in dev_srcs
                 if not Path(urllib.parse.unquote(s[8:])).is_file())[:120])
    ok("手册目录真实存在", manual_dir().resolve().is_dir(), str(manual_dir()))

    # ---- 9. 分段开关与互链改写 ----
    ok("分段开关含 gui 标签", 'data-tab="gui"' in html, "")
    ok("分段开关含 cli 标签", 'data-tab="cli"' in html, "")
    ok("默认激活 gui 标签页",
       'class="tab active" data-tab="gui"' in html, "")
    # ⚠️ 互链改写要**测机制**，不能测「当前文档里恰好有这个链接」：
    # user-guide.md 曾被整篇重写、[cli.md](cli.md) 那行被顺手删掉，护栏立刻红了
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

    # ---- 13. ⚠️ 打开方式：交给系统的必须是**原生路径**，不是 file:// URI ----
    # 真实故障（2026-09-19）：`open_manual` 一直用
    # `webbrowser.open(html_path.as_uri())`，ShellExecute 拿到 file:// URI 会走
    # **file: 协议处理器**（HKCR\file → CLSID {00000303-...}），那东西在部分机器上
    # 没注册成功 → `os.startfile` **卡死不返回**：界面冻住、浏览器永远不出现
    # （用户报「点用户手册按钮不打开浏览器了」）。同一台机器上传原生路径秒开。
    # 这条护栏钉住「Windows 上第一跳必须是 os.startfile(原生路径)，且不再调用
    # 会挂的 webbrowser.open」——纯注释挡不住回归，这里用行为断言。
    import os as _os
    import sys as _sys

    from desktop.ui import help_dialog as _hd

    if _sys.platform == "win32" and hasattr(_os, "startfile"):
        calls: dict[str, str] = {}
        real_startfile = _hd.os.startfile
        real_wb_open = _hd.webbrowser.open

        def _fake_startfile(target, *a, **kw):
            calls["startfile"] = str(target)

        def _fake_wb_open(url, *a, **kw):
            calls["webbrowser"] = str(url)
            return True

        _hd.os.startfile = _fake_startfile
        _hd.webbrowser.open = _fake_wb_open
        try:
            opened_path = _hd.open_manual()
        finally:
            _hd.os.startfile = real_startfile
            _hd.webbrowser.open = real_wb_open

        target = calls.get("startfile", "")
        ok("Windows 上第一跳是 os.startfile", bool(target), "压根没调用 os.startfile")
        ok("传给系统的不是 file:// URI（file: 协议处理器会卡死）",
           bool(target) and not target.lower().startswith("file:"),
           f"实际={target!r}")
        ok("传的是真实存在的原生路径",
           bool(target) and Path(target).is_file(),
           f"实际={target!r}")
        ok("不再走 webbrowser.open（Windows 上它会挂）",
           "webbrowser" not in calls,
           f"意外调用={calls.get('webbrowser')!r}")
        ok("open_manual 返回的正是被打开的那个文件",
           str(opened_path) == target,
           f"返回={opened_path} 打开={target}")
    else:
        ok("非 Windows 平台仍用 webbrowser（本机是 Windows，跳过行为断言）",
           True, _sys.platform)


    # ---- 14. 生产/开发分流：打包版打开**预生成的静态手册** ----
    # 开发时 docs 随时在改，必须每次现渲染；打包后内容已定死，直接打开静态页。
    # 判据是 frozen（不是"静态文件在不在"），否则仓库里残留一个 manual.html
    # 就会让开发者一直看到旧内容。
    import os
    import tempfile

    from desktop.ui import help_dialog as hd

    ok("开发（非 frozen）模式不启用静态手册", hd.prefer_static_manual() is False,
       f"frozen={getattr(__import__('sys'), 'frozen', False)}")
    os.environ["GUJI_MANUAL_STATIC"] = "1"
    try:
        ok("GUJI_MANUAL_STATIC=1 可强制走静态（冒烟/自测用）",
           hd.prefer_static_manual() is True)
    finally:
        os.environ.pop("GUJI_MANUAL_STATIC", None)

    tmpdir = Path(tempfile.mkdtemp(prefix="guji_static_manual_"))
    static_file = tmpdir / "manual.html"
    hd.generate_static_manual(static_file)
    static_html = static_file.read_text(encoding="utf-8")

    ok("静态手册生成成功且非空", static_html.startswith("<!DOCTYPE html>"),
       static_html[:40])
    ok("静态手册也不带 base 标签（同 8 节：它会把 #锚点 变成目录 URL）",
       re.search(r"<base\b", static_html) is None)
    ok("静态手册标注了「构建时预生成」",
       "构建时预生成" in static_html)

    static_srcs = re.findall(r'<img[^>]*?\ssrc="([^"]+)"', static_html)
    ok("静态手册 12 张截图都在", len(static_srcs) == 12, f"{len(static_srcs)} 张")
    # ⚠️ 核心不变量：安装包不含 docs/guide，图片必须**内联**，任何外部引用
    # （相对路径 / 构建机绝对路径）到了用户机器上都是碎图。
    ok("静态手册截图全部内联（data: URI）",
       all(s.startswith("data:image/") for s in static_srcs),
       "; ".join(s[:40] for s in static_srcs if not s.startswith("data:image/")))
    ok("静态手册没有任何外部图片引用",
       'src="file:' not in static_html and "src=\"screenshots/" not in static_html)
    ok("静态手册没有引用 md 文档（安装包里没有 docs/guide）",
       'href="cli.md"' not in static_html
       and 'href="user-guide.md"' not in static_html)
    ok("内联图片是真 PNG（base64 解码后校验文件头）",
       all(base64.b64decode(s.split(",", 1)[1]).startswith(b"\x89PNG")
           for s in static_srcs),
       "有内联图片不是 PNG")

    # 打包模式：open_manual 必须直接打开静态文件；文件缺失时退回现渲染
    _real_static_path = hd.static_manual_path
    _real_open = hd._open_with_system
    opened: dict = {}
    hd.static_manual_path = lambda: static_file
    hd._open_with_system = lambda p: opened.setdefault("path", p) or True
    os.environ["GUJI_MANUAL_STATIC"] = "1"
    try:
        got = hd.open_manual()
        ok("打包模式：open_manual 直接打开预生成的静态手册",
           got == static_file and opened.get("path") == static_file,
           f"返回={got} 打开={opened.get('path')}")

        static_file.unlink()
        opened.clear()
        fallback = hd.open_manual()
        ok("打包模式但产物里没静态手册：退回运行时临时渲染（不留白屏）",
           fallback.name.startswith(hd._HTML_PREFIX) and fallback.is_file(),
           str(fallback))
    finally:
        hd.static_manual_path = _real_static_path
        hd._open_with_system = _real_open
        os.environ.pop("GUJI_MANUAL_STATIC", None)

    # ---- 15. 右侧目录定位（点目录必须滚到对应小节）----
    # 曾经的 bug：标题 id 是 JS 按 'sec-' + 序号 现赋的，两份手册都从 sec-0 开始
    # → id 跨页签撞车。在 CLI 页签点目录，浏览器跳到**隐藏的 GUI 页签**里同名
    # 元素（display:none 无法滚动）→ 表现为「跳到别处 / 没定位」。
    source = help_dialog_py.read_text(encoding="utf-8")
    # 只看代码行：注释里为了说明来龙去脉会引用旧写法，不该被当成"还在用"
    code_only = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith(("//", "*", "#"))
    )
    ok("目录 id 按页签加前缀（避免跨页签撞 id）",
       "'-sec-'" in code_only and "prefix + i" in code_only,
       "仍在使用无前缀的 sec-N")
    ok("目录点击有显式滚动处理（原生锚点会被吸顶栏盖住）",
       "tocNav.addEventListener('click'" in code_only
       and "scrollIntoView" in code_only)
    ok("标题留了吸顶栏的偏移量（scroll-margin-top）",
       code_only.count("scroll-margin-top") >= 2,
       f"出现 {code_only.count('scroll-margin-top')} 次")

    # ---- 16. 手册页 JS：let/const、页签记忆、外链新开 ----
    js = hd._JS
    ok("手册页 JS 用 let/const（不再出现 var）", "var " not in js,
       "仍有 var 声明")
    ok("手册页记住上次看的分段（localStorage 读写）",
       "localStorage.setItem" in js and "localStorage.getItem" in js,
       "没有页签记忆逻辑")
    ok("启动定页签的优先级：深链 > 记忆 > 默认",
       "const deep" in js.replace("#tab-(.+)", "const deep")
       or ("location.hash.match" in js and "remembered" in js),
       "缺少启动定页签逻辑")

    # 外链必须新标签打开（浏览器里把手册页顶掉会很烦）；手册之间的互链走页内跳转
    fragment = hd._md_to_fragment(
        "[外部站点](https://example.com/doc)\n\n[命令行手册](cli.md)\n"
    )
    ok("外链带上 target=_blank（不在当前页打开）",
       'href="https://example.com/doc"' in fragment
       and 'target="_blank"' in fragment,
       fragment[:160])
    ok("手册互链改写成页内 tab 跳转（浏览器打开 .md 只会显示纯文本）",
       'href="#tab-cli"' in fragment, fragment[:160])

    # ---- 17. 右栏版式：宽度、引导线、二级标记（都因"太窄/层级弱"返工过）----
    css = hd._css()
    # 不用正则：这行要的就是 "--toc-w: 236px"，切一刀最直观
    toc_width = (
        css.split("--toc-w:", 1)[1].split(";", 1)[0].strip()
        if "--toc-w:" in css else ""
    )
    ok("目录栏够宽（>= 220px，中文标题才不会普遍折成两行）",
       toc_width.endswith("px") and int(toc_width[:-2]) >= 220,
       f"实际 {toc_width or '未定义'}")
    ok("整列有引导线（否则一堆孤立条目看不出层级）",
       "#toc-nav::before" in css and "#toc-nav { position: relative" in css)
    ok("二级条目有独立标记（短横 + 更小字号）",
       ".toc a.lv3::after" in css and ".toc a.lv3 {" in css)
    ok("窄屏会收掉目录（加宽后断点也要跟着提）",
       re.search(r"@media \(max-width: 12\d\dpx\)", css) is not None,
       "断点没跟着目录宽度调整")

    # ---- 18. 调版式不必跑 19 分钟完整打包 ----
    ok("build.py 提供 --manual-only（只重生成手册 + 刷新部署/安装包）",
       "--manual-only" in build_src and "refresh_manual_only" in build_src,
       "缺少只刷手册的入口")

    # ---- 19. 目录点击：file:// 下 replaceState 会抛，绝不能让它中断滚动 ----
    # 实测：file:// 文档 origin 是 opaque，history.replaceState 抛 SecurityError。
    # 曾经的顺序是 preventDefault → replaceState → scrollIntoView，异常一来
    # 滚动就永远执行不到（用户看到的正是"点目录没反应"）。
    # 只看代码行：注释里解释"file:// 下 replaceState 会抛"不该被当成调用
    js_code = "\n".join(
        line for line in js.splitlines() if not line.lstrip().startswith("//")
    )
    ok("replaceState 只出现在 setHash 里（统一接住 file:// 的 SecurityError）",
       js_code.count("history.replaceState") == 1
       and "catch (err)" in js_code.split("history.replaceState")[0][-260:],
       f"出现 {js_code.count('history.replaceState')} 次")
    handler = js_code[js_code.index("tocNav.addEventListener"):]
    handler = handler[:handler.index("setHash('#'")]
    ok("目录点击先 scrollIntoView、再动 hash（顺序反了会丢滚动）",
       "scrollIntoView" in handler, "scrollIntoView 不在 setHash 之前")
    ok("scrollIntoView 有绝对位置兜底（不支持平滑滚动时也能跳）",
       "window.scrollTo(0, el.getBoundingClientRect().top" in js)
