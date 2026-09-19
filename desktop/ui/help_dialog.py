# -*- coding: utf-8 -*-
"""用户手册：Markdown → HTML → 系统默认浏览器渲染。

为什么不再用 ``QTextBrowser`` / ``QTextDocument`` 直接渲染 Markdown：

- Qt 的 ``setMarkdown()`` 只支持 GFM 的**子集**，表格、围栏代码块、深层嵌套
  列表的渲染都很勉强，长文档读起来发闷；
- ``setHtml()`` 走的是**同一条富文本引擎**，CSS 只是 HTML 的一个小子集
  （没有 flex、没有伪元素、 ``nth-child`` 之类选择器也不全），多绕一圈
  换不来真正的样式自由度；
- ``QWebEngineView`` 能彻底解决，但会拖进 ``QtWebEngineProcess.exe`` 与
  百 MB 级资源包，和 ``guji.spec`` 现有的 excludes 裁剪策略直接冲突。

于是走第三条路：**用 Python 的 ``markdown`` 库（纯 Python、无二进制依赖）
把 ``docs/guide/*.md`` 转成完整 HTML，内嵌匹配应用主题的 CSS，交给系统默认
浏览器打开。**

**两条路，按模式分流**（判据见 ``prefer_static_manual``，是"打包与否"而不是
"文件在不在"）：

| 模式 | 手册来源 | 截图 | 何时用 |
| --- | --- | --- | --- |
| 开发（源码运行） | 每次现渲染到 %TEMP% | 绝对 ``file://`` URL | md 随时在改，改完立刻可见 |
| 打包（生产） | 构建期预生成的 ``desktop/static/manual.html`` | **内联 data URI** | 内容已定死，点开即用 |

生产侧预生成是必须的，不只是"快一点"：``docs/guide/`` 整目录**不进安装包**
（对最终用户无用的 md 与截图，白占体积），所以安装后既读不到 md、也找不到
截图——只有把手册连同截图压成一个自包含 HTML 放进包里才成立。

这样做的好处：

1. **零重量依赖** —— ``markdown`` 纯 Python 单包；且**只有构建环境需要它**，
   打包产物里已把它排除（运行时不渲染 md，缺了它也只是退化成占位提示）；
2. **完整 GFM** —— 表格、围栏代码块、嵌套列表都按规范渲染；
3. **图片永远不碎** —— 开发靠 ``<base>`` 指回 ``docs/guide/``，生产靠内联，
   两种模式都不存在"相对路径解析错"的可能；
4. **样式自由** —— 真实浏览器渲染，CSS 不受 Qt 富文本子集限制；
5. **性能与产物一致** —— 生产端点开就是浏览器那一下，没有首次渲染延迟，
   也不再有"临时文件堆积 + 防缓存文件名"那套绕法。

三条关键实现约束（改动时别踩）：

- **开发模式的 ``<base>`` 必须指向手册目录且带结尾斜杠**：HTML 落在临时目录，
  不设 base 就会把 ``screenshots/guide/*.png`` 解析成碎图；
- **指南之间的互链要改成页内 tab 跳转**：``user-guide.md`` 里有
  ``[cli.md](cli.md)``，浏览器会把 .md 当纯文本显示，必须改写为
  ``#tab-cli`` 交给 JS 切页；
- **打开时只把「原生路径」交给系统，绝不传 ``file:///`` URI**：见
  ``_open_with_system`` 的注释，这是「点了按钮没反应」的元凶。
"""

from __future__ import annotations

import base64
import html as html_escape
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import webbrowser
from pathlib import Path
from string import Template

from desktop.ui import theme as T
from desktop.utils.files import package_dir

#: 手册条目：(键, 分段开关文案, 文件名)。新增手册只改这里。
MANUAL_ENTRIES: tuple[tuple[str, str, str], ...] = (
    ("gui", "桌面端操作", "user-guide.md"),
    ("cli", "命令行", "cli.md"),
)

#: 生成的 HTML 落在临时目录，**文件名带毫秒时间戳、每次都不一样**。
#:
#: ⚠️ 不要改回固定文件名 + ``?v=<时间戳>`` 查询串那套：
#: 1. Windows 上 ``webbrowser.open`` 走的是 ``os.startfile``，``?v=...``
#:    会被当成路径的一部分，实测地址栏里根本看不到查询串（缓存照旧命中）；
#: 2. 固定文件名 + file:// 会被浏览器按 URL 缓存，改了内容用户还是看到旧版
#:    （曾踩：屏幕上一直是原始 markdown，其实是早期一次 fallback 的产物）。
#: 文件名唯一 → URL 天然唯一 → 缓存不可能命中。
#: 代价是每次点会新开一个标签页（不能复用），但「看错内容」比「多开标签」严重得多。
_HTML_PREFIX = "guji_manual_"

#: 保留最近几份历史 HTML，更早的清理掉，避免临时目录里堆一堆文件。
_KEEP_RECENT = 3


def _cleanup_old_manuals() -> None:
    """删掉更早生成的手册 HTML，只留最近 ``_KEEP_RECENT`` 份。"""
    tmp = Path(tempfile.gettempdir())
    try:
        olds = sorted(
            tmp.glob(f"{_HTML_PREFIX}*.html"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    for p in olds[_KEEP_RECENT:]:
        try:
            p.unlink()
        except OSError:
            pass  # 文件被浏览器占着就跳过，下次再清

def manual_dir() -> Path:
    """手册目录（源码与打包两种模式下都可用）。

    与 ``package_dir()`` 同源：源码模式下 ``desktop/`` 的上一级就是仓库根，
    打包后数据文件由 ``guji.spec`` 的 ``gui_datas`` 落到 ``_internal/``，
    ``package_dir()`` 在 frozen 下返回 ``_MEIPASS/desktop``，再上一级同样是
    资源根，因此 ``package_dir().parent / "docs" / "guide"`` 两种模式通用。
    """
    return package_dir().parent / "docs" / "guide"


#: 构建期预生成的自包含手册 HTML，**落在 ``desktop/static/`` 下**。
#:
#: 生产与开发两条路（判据见 ``prefer_static_manual``）：
#:
#: - **开发模式**：``docs/guide/*.md`` 随时在改，每次点按钮现渲染到 %TEMP%，
#:   改完立刻能看到效果；
#: - **打包模式（生产）**：手册内容在构建那一刻就定死了，构建期把它连**截图
#:   一起内联**渲染成单个 HTML 放进包里，运行时直接打开——不渲染、不写临时
#:   文件、不依赖任何外部文件。
#:
#: 内联（data URI）是必须的：``docs/guide/`` 整目录**不进安装包**（md 与截图
#: 对最终用户都没用，还占体积），所以既不能写相对路径、也不能写构建机的绝对
#: ``file://`` 路径。一个自包含文件 = 换台机器/复制出去都不碎图。
STATIC_MANUAL_NAME = "manual.html"


def static_manual_path() -> Path:
    """构建期预生成的自包含手册路径（**只有打包版才有**；可能不存在）。"""
    return package_dir() / "static" / STATIC_MANUAL_NAME


def prefer_static_manual() -> bool:
    """当前是否该走「构建期静态手册」这条路。

    判据是**打包与否（frozen）**，不是「静态文件在不在」：

    - 开发模式：``docs/guide/*.md`` 随时在改，必须每次现渲染，改完立刻能看到
      效果；若按「文件存在」判断，仓库里哪天留了一个 ``manual.html``（手动生成
      过一次、或从安装包里拷回来的），开发者就会一直看到旧内容；
    - 生产模式（PyInstaller 打包后）：手册内容在构建那一刻就定死了，直接打开
      预生成的静态 HTML，不渲染、不写临时文件。

    ``GUJI_MANUAL_STATIC=1`` / ``=0`` 可强制指定，供冒烟与自测用。
    """
    override = os.environ.get("GUJI_MANUAL_STATIC")
    if override is not None and override.strip() != "":
        return override.strip().lower() not in ("0", "false", "no")
    return bool(getattr(sys, "frozen", False))


def _md_extensions() -> list:
    """构造 GFM 扩展实例列表。

    - ``tables``      表格（cli.md 有 93 行表格，缺这条会退化成纯文本管道符）
    - ``fenced_code`` ``` 围栏代码块
    - ``sane_lists``  修掉原生 markdown 对「有序/无序列表相邻」的误判

    ⚠️ **必须传扩展实例，不能传字符串名**。markdown 库按名字加载扩展时走的是
    entry point（``importlib.metadata`` 查已安装发行版的元数据）；frozen 模式
    下 ``.dist-info`` 未必被打进包里，查不到就会退化成
    ``importlib.import_module("tables")`` 然后直接 ImportError——手册在源码
    模式下好好的、一打包就碎。这里静态 import 类再传实例，PyInstaller 能
    静态分析到，完全不依赖运行时元数据。
    """
    from markdown.extensions.fenced_code import FencedCodeExtension
    from markdown.extensions.sane_lists import SaneListExtension
    from markdown.extensions.tables import TableExtension

    return [TableExtension(), FencedCodeExtension(), SaneListExtension()]


def _md_to_fragment(md_text: str) -> str:
    """把一段 Markdown 转成 HTML 片段，并修正指南之间的互链。

    改写规则：

    - ``href="cli.md"`` 之类指向另一份手册的链接 → ``#tab-<key>``，
      交给页面 JS 切成对应标签页（浏览器直接打开 .md 只会显示纯文本）；
    - ``http(s)`` 外链补 ``target="_blank"``，别把手册页顶掉。

    ``markdown`` 库缺失时降级为转义后的纯文本——宁可难看，也不要让
    「用户手册」按钮点下去直接崩掉整个界面。
    """
    try:
        import markdown
    except ImportError:
        return f"<pre>{html_escape.escape(md_text)}</pre>"

    fragment = markdown.markdown(md_text, extensions=_md_extensions())

    # 指南互链 → 页内 tab 跳转
    for key, _label, filename in MANUAL_ENTRIES:
        fragment = fragment.replace(f'href="{filename}"', f'href="#tab-{key}"')

    # 外链新标签打开（负向断言 (?!) 排除刚改写过的 #tab- 锚点）
    fragment = re.sub(
        r'<a href="(?!#)(https?://[^"]*)"',
        r'<a target="_blank" rel="noopener" href="\1"',
        fragment,
    )
    return fragment


#: ``<img ... src="...">`` —— 只取 img 的 src，别误伤别的标签
_IMG_SRC_RE = re.compile(r'(<img[^>]*?\ssrc=")([^"]+)(")')


def _absolutize_image_srcs(fragment: str, guide_dir: Path) -> str:
    """把相对图片路径改写成**绝对的、已百分号编码的** ``file://`` URL。

    ⚠️ 不能只靠 ``<base>`` 让浏览器自己去拼：Markdown 里写的是带中文的
    相对路径（``screenshots/guide/s0-任务列表.png``），靠 base 拼接后要由
    浏览器负责百分号编码，实测部分浏览器拿不到图（页面上有框无图）。
    这里直接算出绝对路径再交给 ``Path.as_uri()``——它内部走
    ``pathname2url``，会把中文编成 ``s0-%E4%BB%BB%E5%8A%A1...``，
    浏览器拿到就是一个能直接打开的 URL，不再有编码歧义。
    """
    def repl(match: re.Match) -> str:
        src = match.group(2)
        # 已经是绝对/内联的（http(s)、data URI、file:、根路径）就不动
        if src.startswith(("http://", "https://", "data:", "file:", "/")):
            return match.group(0)
        target = guide_dir / urllib.parse.unquote(src)
        return f"{match.group(1)}{target.as_uri()}{match.group(3)}"

    return _IMG_SRC_RE.sub(repl, fragment)


def _encode_image_srcs(fragment: str) -> str:
    """把相对图片路径做百分号编码，但**保持相对**（备用：与截图同目录时用）。

    当前两个入口都不用它（开发走绝对 ``file://``、预生成走内联 data URI），
    保留是因为"手册 HTML 与截图同目录"这一形态在外部工具链里仍可能出现
    （例如把 docs 目录整体拷给别人的临时预览），实现只有三行。

    中文名必须预编码：``markdown`` 原样吐出的 ``s0-任务列表.png`` 交给浏览器
    按 URL 解析，部分浏览器取不到图（页面上有框无图）。先 ``unquote`` 再
    ``quote``，对已编码/未编码两种输入都幂等。
    """
    def repl(match: re.Match) -> str:
        src = match.group(2)
        if src.startswith(("http://", "https://", "data:", "file:", "/", "#")):
            return match.group(0)
        encoded = urllib.parse.quote(urllib.parse.unquote(src))
        return f"{match.group(1)}{encoded}{match.group(3)}"

    return _IMG_SRC_RE.sub(repl, fragment)


def _inline_image_srcs(fragment: str, guide_dir: Path) -> str:
    """把图片内联成 ``data:`` URI（构建期预生成的自包含手册用）。

    为什么要内联：``docs/guide/`` 整目录**不进安装包**，安装后既没有
    ``screenshots/guide/*.png``，也不能写构建机的绝对路径。内联之后手册是
    一个自包含文件——复制到任何机器、任何路径都完整显示。

    代价是 HTML 变大（12 张 PNG 约 6MB → base64 后约 8MB）。可接受：这只在
    构建期算一次，装到磁盘上仍是同一个量级，而安装包里的 lzma2 对 PNG 的
    base64 文本仍能压掉约三成。

    读不到的文件保持原样（页面会显示碎图而不是整页崩掉），便于发现漏图。
    """
    def repl(match: re.Match) -> str:
        src = match.group(2)
        if src.startswith(("http://", "https://", "data:", "file:", "/", "#")):
            return match.group(0)
        image = guide_dir / urllib.parse.unquote(src)
        try:
            blob = image.read_bytes()
        except OSError:
            return match.group(0)
        suffix = image.suffix.lower().lstrip(".")
        mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix or "png"
        encoded = base64.b64encode(blob).decode("ascii")
        return f'{match.group(1)}data:image/{mime};base64,{encoded}{match.group(3)}'

    return _IMG_SRC_RE.sub(repl, fragment)


# --------------------------------------------------------------------------- CSS
# ⚠️ 用 string.Template（``$NAME`` 占位）而不是 f-string：CSS 里花括号极多，
#    f-string 要把每个 { } 都写成 {{ }}，可读性直接报废。
#    颜色一律取 desktop/ui/theme.py 的设计令牌，不在这里重复硬编码色值。
#
# 版式（从外到内）：吸顶栏（品牌 + 分段开关 + 打印）→ 1200px 版心 →
# 左侧「纸面」卡片（正文，最大 900px 行宽，长文档才读得下去）+ 右侧吸顶目录。
_CSS_TEMPLATE = Template("""
:root {
  --ink: $INK;
  --ink-soft: $INK_SOFT;
  --ink-faint: $INK_FAINT;
  --bg: $CANVAS;
  --surface: $SURFACE;
  --surface-soft: $SURFACE_SOFT;
  --surface-hover: $SURFACE_HOVER;
  --surface-sunken: $SURFACE_SUNKEN;
  --border: $BORDER;
  --border-soft: $BORDER_SOFT;
  --border-strong: $BORDER_STRONG;
  --accent: $ACCENT;
  --accent-hover: $ACCENT_HOVER;
  --accent-soft: $ACCENT_SOFT;
  --danger: $DANGER;
  --danger-soft: $DANGER_SOFT;
  --radius: ${RADIUS_MD}px;
  --radius-sm: ${RADIUS_SM}px;
  --radius-lg: ${RADIUS_LG}px;
  --toc-w: 272px;
  --shell-w: 1200px;
  --shadow-1: 0 1px 2px rgba(16, 24, 32, 0.05);
  --shadow-2: 0 18px 40px -26px rgba(16, 24, 32, 0.30);
  --shadow-3: 0 10px 26px -16px rgba(16, 24, 32, 0.35);
}

* { box-sizing: border-box; }

html { scroll-behavior: smooth; }

body {
  font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
               "Noto Sans CJK SC", "WenQuanYi Zen Hei", "SimHei", sans-serif;
  font-size: 14.5px;
  line-height: 1.8;
  color: var(--ink);
  background: var(--bg);
  margin: 0;
  padding: 0;
  -webkit-font-smoothing: antialiased;
}

/* ---- 顶栏（吸顶）：品牌 + 分段开关 + 打印 ---- */
.topbar {
  position: sticky;
  top: 0;
  z-index: 60;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(10px) saturate(1.4);
  border-bottom: 1px solid var(--border);
}

.topbar-inner {
  display: flex;
  align-items: center;
  gap: 16px;
  max-width: var(--shell-w);
  margin: 0 auto;
  padding: 11px 32px;
}

.brand { display: flex; align-items: baseline; gap: 9px; white-space: nowrap; }
.brand-mark { font-size: 15px; font-weight: 700; letter-spacing: 0.04em; color: var(--accent); }
.brand-sub { font-size: 12.5px; color: var(--ink-faint); }

.tab-bar {
  display: flex;
  gap: 2px;
  padding: 3px;
  margin-left: 8px;
  border-radius: 999px;
  background: var(--surface-sunken);
}

.tab {
  padding: 6px 18px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--ink-soft);
  font-family: inherit;
  font-size: 13.5px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, box-shadow 0.15s;
}

.tab:hover { color: var(--ink); }
.tab.active {
  background: var(--surface);
  color: var(--accent);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(16, 24, 32, 0.14);
}

.topbar-actions { margin-left: auto; display: flex; gap: 8px; }

.ghost-btn {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
  color: var(--ink-soft);
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}

.ghost-btn:hover { border-color: var(--border-strong); color: var(--accent); }

/* ---- 版心：纸面 + 目录 ---- */
.page { max-width: var(--shell-w); margin: 0 auto; padding: 26px 32px 56px; }

.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--toc-w);
  gap: 32px;
  align-items: start;
}

.paper {
  min-width: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-1);
  padding: 38px 46px 52px;
}

.tab-content { display: none; }
.tab-content.active { display: block; }

.toc {
  position: sticky;
  top: 84px;
  max-height: calc(100vh - 118px);
  overflow-y: auto;
  padding-right: 4px;
}

/* 标题右侧拉一条渐隐细线，把「本页目录」与下面的条目分开 */
.toc-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 12px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.16em;
  color: var(--ink-faint);
  white-space: nowrap;
}

.toc-title::after {
  content: "";
  flex: 1;
  height: 1px;
  background: linear-gradient(to right, var(--border), transparent);
}

/* 整列一条引导线：读起来像大纲，而不是一堆孤零零的文字 */
#toc-nav { position: relative; padding-left: 12px; }

#toc-nav::before {
  content: "";
  position: absolute;
  left: 0;
  top: 5px;
  bottom: 5px;
  width: 2px;
  border-radius: 1px;
  background: var(--border-soft);
}

.toc a {
  position: relative;
  display: block;
  padding: 6px 8px 6px 10px;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.45;
  text-decoration: none;
  transition: color 0.15s, background 0.15s;
}

/* 当前小节：在引导线上叠一段主色（left 负值压回 #toc-nav 的 padding） */
.toc a::before {
  content: "";
  position: absolute;
  left: -12px;
  top: 5px;
  bottom: 5px;
  width: 2px;
  border-radius: 1px;
  background: transparent;
}

.toc a:hover { color: var(--accent); background: var(--surface-soft); }
.toc a.active { color: var(--accent); font-weight: 600; }
.toc a.active::before { background: var(--accent); }

/* 二级（h3）：缩进更多、字号更小、前面加一小段短横，层级一眼分得开 */
.toc a.lv3 {
  padding-left: 22px;
  font-size: 12.5px;
  color: var(--ink-faint);
}

.toc a.lv3::after {
  content: "";
  position: absolute;
  left: 10px;
  top: 50%;
  width: 6px;
  height: 1px;
  background: var(--border-strong);
}

.toc a.lv3.active { color: var(--accent); }

/* ---- 标题 ---- */
h1 {
  font-size: 27px;
  font-weight: 700;
  line-height: 1.4;
  letter-spacing: 0.01em;
  margin: 0 0 14px;
}

h2 {
  position: relative;
  font-size: 20px;
  font-weight: 700;
  margin: 46px 0 16px;
  padding: 0 0 11px 14px;
  border-bottom: 1px solid var(--border-soft);
  scroll-margin-top: 84px;
}

h2::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0.36em;
  width: 4px;
  height: 15px;
  border-radius: 2px;
  background: var(--accent);
}

h3 {
  font-size: 16.5px;
  font-weight: 600;
  margin: 30px 0 10px;
  scroll-margin-top: 84px;
}

h4 { font-size: 14.5px; font-weight: 600; margin: 22px 0 8px; color: var(--ink-soft); }

.h-anchor {
  margin-left: 8px;
  color: var(--border-strong);
  font-weight: 400;
  text-decoration: none;
  opacity: 0;
  transition: opacity 0.15s;
}

h2:hover .h-anchor, h3:hover .h-anchor { opacity: 1; }

p { margin: 11px 0; }
.paper > :first-child { margin-top: 0; }

/* ---- 表格 ---- */
table {
  border-collapse: separate;
  border-spacing: 0;
  width: 100%;
  margin: 20px 0;
  font-size: 13.5px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

th, td {
  padding: 10px 14px;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--border-soft);
}

thead th {
  background: var(--surface-soft);
  font-weight: 600;
  border-bottom: 1px solid var(--border);
}

tbody tr:last-child td { border-bottom: none; }
tbody tr:nth-child(even) td { background: var(--surface-soft); }
tbody tr:hover td { background: var(--surface-hover); }

/* ---- 代码 ---- */
pre {
  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 14px 18px;
  margin: 16px 0;
  overflow-x: auto;
  line-height: 1.6;
}

code {
  font-family: "Cascadia Code", "Cascadia Mono", "Consolas",
               "Courier New", monospace;
  font-size: 12.5px;
}

p code, li code, td code, th code {
  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 5px;
}

pre code { background: none; border: none; padding: 0; }

/* ---- 截图：可点开看原图（1500px 截图在 900px 行宽里必然被压缩）---- */
img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 20px auto;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface);
  box-shadow: var(--shadow-3);
  cursor: zoom-in;
  transition: box-shadow 0.18s, transform 0.18s;
}

img:hover {
  box-shadow: var(--shadow-2);
  transform: translateY(-1px);
}

/* ---- 引用块 ---- */
blockquote {
  margin: 18px 0;
  padding: 12px 20px;
  background: var(--accent-soft);
  border-left: 4px solid var(--accent);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  color: var(--ink-soft);
}

blockquote p { margin: 5px 0; }

/* ---- 列表 ---- */
ul, ol { padding-left: 26px; margin: 11px 0; }
li { margin: 5px 0; }
li > ul, li > ol { margin: 5px 0; }

/* ---- 其他 ---- */
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

hr { border: none; border-top: 1px solid var(--border-soft); margin: 34px 0; }

strong { font-weight: 600; }

.foot {
  margin-top: 24px;
  padding-top: 14px;
  border-top: 1px solid var(--border-soft);
  color: var(--ink-faint);
  font-size: 12.5px;
}

/* 回到顶部 */
.to-top {
  position: fixed;
  right: 30px;
  bottom: 30px;
  width: 40px;
  height: 40px;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--surface);
  color: var(--ink-soft);
  font-size: 16px;
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  box-shadow: var(--shadow-3);
  transition: opacity 0.2s, color 0.2s;
}

.to-top.show { opacity: 1; pointer-events: auto; }
.to-top:hover { color: var(--accent); }

/* 点击截图后的放大浮层 */
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: none;
  align-items: center;
  justify-content: center;
  padding: 28px;
  background: rgba(14, 22, 28, 0.84);
  cursor: zoom-out;
}

.lightbox.open { display: flex; }
.lightbox img {
  max-width: 100%;
  max-height: 100%;
  margin: 0;
  border: none;
  border-radius: var(--radius-sm);
  box-shadow: 0 30px 70px rgba(0, 0, 0, 0.45);
  cursor: zoom-out;
  transform: none;
}

/* 手册文件缺失 / markdown 库缺失时的提示 */
.missing {
  color: var(--danger);
  background: var(--danger-soft);
  padding: 12px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(201, 58, 58, 0.22);
}

/* ---- 窄屏：目录收掉，纸面铺满 ---- */
/* 目录加宽到 272px 后，1260px 以下放不下「纸面 + 目录」两栏（正文会被压到 800px 内） */
@media (max-width: 1260px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .toc { display: none; }
}

@media (max-width: 720px) {
  .topbar-inner { flex-wrap: wrap; gap: 10px; padding: 10px 18px; }
  .topbar-actions { margin-left: 0; }
  .page { padding: 18px 16px 40px; }
  .paper { padding: 24px 20px 36px; border-radius: var(--radius); }
  h1 { font-size: 23px; }
  h2 { font-size: 18px; }
}

/* ---- 打印：去掉chrome，只留正文 ---- */
@media print {
  .topbar, .toc, .to-top, .lightbox { display: none !important; }
  body { background: #FFFFFF; }
  .page { max-width: none; padding: 0; }
  .layout { display: block; }
  .paper { border: none; border-radius: 0; box-shadow: none; padding: 0; }
  img { box-shadow: none; transform: none; }
}
""")


def _css() -> str:
    """把 CSS 模板里的 ``$TOKEN`` 换成 theme.py 的设计令牌。"""
    return _CSS_TEMPLATE.substitute(
        INK=T.INK,
        INK_SOFT=T.INK_SOFT,
        INK_FAINT=T.INK_FAINT,
        CANVAS=T.CANVAS,
        SURFACE=T.SURFACE,
        SURFACE_SOFT=T.SURFACE_SOFT,
        SURFACE_HOVER=T.SURFACE_HOVER,
        SURFACE_SUNKEN=T.SURFACE_SUNKEN,
        BORDER=T.BORDER,
        BORDER_SOFT=T.BORDER_SOFT,
        BORDER_STRONG=T.BORDER_STRONG,
        ACCENT=T.ACCENT,
        ACCENT_HOVER=T.ACCENT_HOVER,
        ACCENT_SOFT=T.ACCENT_SOFT,
        DANGER=T.DANGER,
        DANGER_SOFT=T.DANGER_SOFT,
        RADIUS_MD=T.RADIUS_MD,
        RADIUS_SM=T.RADIUS_SM,
        RADIUS_LG=T.RADIUS_LG,
    )


# ---------------------------------------------------------------------------- JS
# 纯原生 JS，无外部依赖（手册页是 file:// 打开的，绝不能引 CDN）。
# ⚠️ 放大浮层的 <img> 由 JS 动态创建，**不要**在 HTML 里写死一个空的
#    <img ...>：护栏按「<img 」计数核对 12 张截图，多一个空标签就红。
_JS = """
(function () {
  const tocNav = document.getElementById('toc-nav');
  const lightbox = document.getElementById('lightbox');
  const toTop = document.getElementById('to-top');

  // 记住上次看的分段：file:// 页面在 Edge/Chrome 里同样能读写 localStorage，
  // 于是下次点「用户手册」会落回上次那一页，而不是每次都被打回第一页。
  // 存储被禁用（隐私模式等）时静默降级成"每次都从默认页开始"。
  const TAB_STORE_KEY = 'guji.manual.tab';
  const rememberTab = (tabId) => {
    try { localStorage.setItem(TAB_STORE_KEY, tabId); } catch (err) { /* 忽略 */ }
  };
  const recalledTab = () => {
    try { return localStorage.getItem(TAB_STORE_KEY); } catch (err) { return null; }
  };
  const panelOf = (tabId) => document.getElementById('tab-' + tabId);

  // ⚠️ file:// 下文档 origin 是 opaque，history.replaceState 会抛 SecurityError。
  // 必须接住：曾经这个异常**中断了整个处理函数** —— 点目录时 preventDefault 已经
  // 执行（原生锚点跳转被取消），紧随其后的 scrollIntoView 却再也执行不到，
  // 用户看到的就是「点目录没反应 / 跳不过去」；切页签同样会跳过 window.scrollTo(0,0)。
  // 所以：能改就改，改不了（file://）就静默放过，滚动永远不依赖它。
  const setHash = (fragment) => {
    try { history.replaceState(null, null, fragment); } catch (err) { /* file:// 常见 */ }
  };

  const activePanel = () => document.querySelector('.tab-content.active');

  // 目录从**当前激活**的分段里现采 h2/h3 —— 两份手册各自成目录
  function buildToc() {
    if (!tocNav) { return; }
    tocNav.innerHTML = '';
    const panel = activePanel();
    if (!panel) { return; }
    const heads = panel.querySelectorAll('h2, h3');
    // ⚠️ id 必须**按页签加前缀**。曾经用的是无前缀的「sec- + 序号」写法：
    // 两份手册都从 sec-0 开始，于是 sec-0..sec-11 在两个 <section> 里各有一份，
    // 在 CLI 页签点目录时，浏览器按文档顺序跳到**第一个**同名元素——那在隐藏的
    // GUI 页签里（display:none 无法滚动）→ 表现为「点目录跳到别处 / 根本没定位」。
    const prefix = (panel.id || 'tab').replace(/^tab-/, '') + '-sec-';
    for (let i = 0; i < heads.length; i++) {
      const h = heads[i];
      if (!h.id) { h.id = prefix + i; }
      const link = document.createElement('a');
      link.href = '#' + h.id;
      link.textContent = h.textContent;
      link.setAttribute('data-target', h.id);
      if (h.tagName === 'H3') { link.className = 'lv3'; }
      tocNav.appendChild(link);
      if (!h.querySelector('.h-anchor')) {
        const mark = document.createElement('a');
        mark.className = 'h-anchor';
        mark.href = '#' + h.id;
        mark.textContent = '#';
        mark.setAttribute('aria-hidden', 'true');
        h.appendChild(mark);
      }
    }
    spy();
  }

  // 滚动高亮：取「已越过顶栏的最后一个小节」
  function spy() {
    if (!tocNav) { return; }
    const links = tocNav.querySelectorAll('a');
    let best = null;
    for (const link of links) {
      const el = document.getElementById(link.getAttribute('data-target'));
      if (el && el.getBoundingClientRect().top <= 120) { best = link; }
    }
    // 页面刚到顶（还没越过任何小节）时也别让目录一片"无高亮"——落在第一条上
    if (!best && links.length) { best = links[0]; }
    for (const link of links) { link.classList.remove('active'); }
    if (best) { best.classList.add('active'); }
  }

  function activate(tabId) {
    const tabs = document.querySelectorAll('.tab');
    const panels = document.querySelectorAll('.tab-content');
    for (const tab of tabs) {
      tab.classList.toggle('active', tab.dataset.tab === tabId);
    }
    for (const panel of panels) {
      panel.classList.toggle('active', panel.id === 'tab-' + tabId);
    }
    rememberTab(tabId);
    buildToc();
    setHash('#tab-' + tabId);
    window.scrollTo(0, 0);
  }

  for (const tab of document.querySelectorAll('.tab')) {
    tab.addEventListener('click', () => activate(tab.dataset.tab));
  }

  // 正文里指向另一份手册的链接（已在渲染时改写成 #tab-xxx）→ 切页而不是跳锚点
  for (const link of document.querySelectorAll('a[href^="#tab-"]')) {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      activate(link.getAttribute('href').slice(5));
    });
  }

  // 目录点击：显式滚动到小节，而不是只靠原生锚点跳转。
  // 原生跳转会把标题顶到视口最上沿、被吸顶栏盖住（看着像"没定位到"）；
  // 这里由 CSS 的 scroll-margin-top 留出顶栏高度，再把 hash 写回去（可复制链接）。
  if (tocNav) {
    tocNav.addEventListener('click', (event) => {
      const link = event.target.closest
        ? event.target.closest('a[data-target]') : null;
      if (!link) { return; }
      const el = document.getElementById(link.getAttribute('data-target'));
      if (!el) { return; }
      event.preventDefault();
      // 先滚动再动 hash：hash 更新在 file:// 下会抛，万一将来又漏接，
      // 也不能把滚动这件事一起带走。scrollIntoView 若不支持平滑滚动，用
      // 绝对位置兜底（84px = 吸顶栏高度 + 呼吸，与 CSS 的 scroll-margin-top 一致）。
      try {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } catch (err) {
        window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 84);
      }
      setHash('#' + el.id);
    });
  }

  // 点截图放大（900px 行宽里看不清 1500px 的界面截图）
  if (lightbox) {
    document.addEventListener('click', (event) => {
      const target = event.target;
      if (!target || target.tagName !== 'IMG'
          || !target.closest || !target.closest('.paper')) {
        return;
      }
      const big = document.createElement('img');
      big.src = target.src;
      big.alt = target.alt || '';
      lightbox.innerHTML = '';
      lightbox.appendChild(big);
      lightbox.classList.add('open');
    });
    lightbox.addEventListener('click', () => {
      lightbox.classList.remove('open');
      lightbox.innerHTML = '';
    });
  }

  if (toTop) {
    toTop.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  window.addEventListener('scroll', () => {
    if (toTop) { toTop.classList.toggle('show', window.scrollY > 420); }
    spy();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && lightbox) {
      lightbox.classList.remove('open');
      lightbox.innerHTML = '';
    }
  });

  const printBtn = document.getElementById('print-btn');
  if (printBtn) {
    printBtn.addEventListener('click', () => { window.print(); });
  }

  // 启动时定页签，优先级：显式 #tab-x 深链 > 上次看过的页签 > 默认（第一项）
  const deep = location.hash.match(/^#tab-(.+)$/);
  const remembered = recalledTab();
  if (deep && panelOf(deep[1])) {
    activate(deep[1]);
  } else if (remembered && panelOf(remembered)) {
    activate(remembered);
  } else {
    buildToc();
  }
})();
"""


def _render_entry(guide_dir: Path, filename: str, image_mode: str = "absolute") -> str:
    """渲染单个手册条目为 HTML 片段；文件缺失时给出可读占位而不是崩掉。

    ``image_mode`` 决定截图怎么引用（见三个 ``*_image_srcs`` 帮助函数）：

    - ``"absolute"``（开发模式，HTML 落在 %TEMP%）：绝对 ``file://`` URL；
    - ``"inline"``（构建期预生成）：data URI，自包含、不依赖任何外部文件。
    """
    path = guide_dir / filename
    if not path.exists():
        return (
            f'<p class="missing">未找到手册文件：{html_escape.escape(str(path))}'
            f"<br>开发模式请确认仓库里有 docs/guide/；"
            f"打包版应带 desktop/static/manual.html（构建期预生成）。</p>"
        )
    fragment = _md_to_fragment(path.read_text(encoding="utf-8"))
    if image_mode == "inline":
        return _inline_image_srcs(fragment, guide_dir)
    return _absolutize_image_srcs(fragment, guide_dir)


def _compose_document(
    guide_dir: Path,
    active_key: str,
    *,
    image_mode: str,
    generated_note: str,
) -> str:
    """拼出整份手册 HTML（两个入口共用：运行时临时文件 / 构建期预生成）。

    差别只在图片来源，由 ``image_mode`` 决定，避免两套模板各自漂移；
    ``<base>`` 只有绝对路径模式才必须（临时文件得靠它把相对路径拼回手册目录），
    自包含模式给 ``./`` 兜底、实际不参与解析。
    """
    tabs: list[str] = []
    panels: list[str] = []
    for key, label, filename in MANUAL_ENTRIES:
        is_active = key == active_key
        tabs.append(
            f'<button class="tab{" active" if is_active else ""}" '
            f'data-tab="{key}">{html_escape.escape(label)}</button>'
        )
        panels.append(
            f'<section class="tab-content{" active" if is_active else ""}" '
            f'id="tab-{key}">'
            f"{_render_entry(guide_dir, filename, image_mode)}</section>"
        )

    generated_at = time.strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<!-- ⚠️ 绝对不要加 HTML 的 base 标签！片段链接（#sec-8 / #tab-cli）是按它解析的：
     一旦它指向手册目录，点标题旁的 # 锚点就变成"打开 docs/guide 目录"，
     浏览器直接把目录列表当页面显示（真实踩过：用户点标题跳出了目录列表）。
     图片不靠它——开发模式写成绝对 file:// URL，生产模式内联成 data URI。 -->
<title>用户手册 · guji</title>
<style>
{_css()}
</style>
</head>
<body>
<header class="topbar">
<div class="topbar-inner">
<div class="brand"><span class="brand-mark">古籍重製</span><span class="brand-sub">用户手册</span></div>
<nav class="tab-bar">
{"".join(tabs)}
</nav>
<div class="topbar-actions"><button class="ghost-btn" id="print-btn">打印 / 另存为 PDF</button></div>
</div>
</header>
<div class="page">
<div class="layout">
<main class="paper">
{"".join(panels)}
</main>
<aside class="toc"><div class="toc-title">本页目录</div><nav id="toc-nav"></nav></aside>
</div>
<footer class="foot">内容来自 <code>docs/guide/*.md</code>，{generated_note} · 生成于 {generated_at}</footer>
</div>
<button class="to-top" id="to-top" title="回到顶部">↑</button>
<div class="lightbox" id="lightbox"></div>
<script>
{_JS}
</script>
</body>
</html>
"""


def generate_manual_html(entry: str | None = None) -> Path:
    """把手册渲染成一个带分段开关的 HTML 文件（临时目录），返回其路径。

    entry 为 ``MANUAL_ENTRIES`` 里的键，决定默认激活哪个标签页；
    不传则激活第一项。**这是打包版用不到的老路**：打包版读
    ``docs/guide/manual.html``（见 ``generate_static_manual``），只有源码模式
    （没有静态文件）才现渲染到这里。

    ⚠️ ``<base>`` 指向手册目录（带结尾斜杠）是图片能加载的唯一保证：
    Markdown 里写的是 ``screenshots/guide/xxx.png`` 这样的相对路径，
    而 HTML 落在临时目录，不设 base 就会相对临时目录解析成碎图。
    """
    guide_dir = manual_dir().resolve()
    document = _compose_document(
        guide_dir,
        entry or MANUAL_ENTRIES[0][0],
        image_mode="absolute",
        generated_note="点「用户手册」时实时生成",
    )
    # 文件名带毫秒时间戳 → URL 每次都唯一 → 浏览器缓存不可能命中旧版本
    out_path = Path(tempfile.gettempdir()) / f"{_HTML_PREFIX}{int(time.time() * 1000)}.html"
    out_path.write_text(document, encoding="utf-8")
    _cleanup_old_manuals()
    return out_path


def generate_static_manual(output_path: Path | None = None) -> Path:
    """**构建期**把手册渲染成单个自包含 HTML（默认 ``desktop/static/manual.html``）。

    打包版点「用户手册」时直接打开这个文件：不渲染 md、不读截图、不写临时文件。
    自包含（截图内联成 data URI）是硬要求——``docs/guide/`` 整目录**不进安装包**，
    安装后既没有 md 也没有 screenshots，任何外部引用都会变成碎图。

    ⚠️ 源码模式下调用**务必传 ``output_path``**（写进待打包目录），别默认写到
    ``desktop/static/manual.html``——那个位置会被打包版优先打开，万一留在仓库里
    容易让人以为改了 md 就生效（实际必须重新打包）。
    """
    guide_dir = manual_dir().resolve()
    output = Path(output_path) if output_path else static_manual_path()
    document = _compose_document(
        guide_dir,
        MANUAL_ENTRIES[0][0],
        image_mode="inline",
        generated_note="构建时预生成（自包含，无需 docs/guide）",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return output


#: ``cmd /c start`` 用到的进程创建标志：不继承控制台、不进 Job，
#: 关掉主程序时不会把浏览器一起带走。
_NO_WINDOW_FLAGS = (
    getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
)


def _open_with_system(path: Path) -> bool:
    """把文件交给系统默认程序打开，成功返回 True。

    ⚠️ **Windows 上绝不能传 ``file:///...`` URI**（``webbrowser.open(path.as_uri())``
    就是那么干的）。实测（2026-09-19）：``ShellExecute`` 拿到 file:// URI 会走
    **file: 协议处理器**（``HKCR\\file`` → ``CLSID {00000303-...}``），那玩意儿在
    这台机器上没注册成功，``os.startfile`` 于是**卡死不返回**——手册按钮点下去，
    界面冻住、浏览器永远不出现，症状就是用户说的「点用户手册按钮不打开浏览器了」。
    同一台机器上传**原生路径**（``os.startfile(str(path))``）秒开 Edge：原生路径
    走的是**扩展名关联**（``.html`` → 默认浏览器），跟 file: 协议处理器无关。

    失败时逐级回退：原生路径 → Qt ``QDesktopServices``（返回 bool，不挂）→
    ``cmd /c start``（独立进程，挂也挂不到我们界面上）。**回退链里刻意不放
    ``webbrowser.open``**——它在 Windows 上就是 ``os.startfile``，既是最上面那条
    （会挂的），再放一遍没有意义；只有非 Windows 平台才用它。
    """
    if sys.platform == "win32":
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        except OSError:
            pass  # 关联坏了/被策略拦了 → 继续回退

    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            return True
    except Exception:
        pass  # 无 Qt / 无平台插件 → 继续回退

    if sys.platform == "win32":
        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", str(path)],
                creationflags=_NO_WINDOW_FLAGS,
                close_fds=True,
            )
            return True
        except Exception:
            return False

    try:
        return bool(webbrowser.open(path.as_uri()))
    except Exception:
        return False


def _notify_open_failed(path: Path) -> None:
    """所有打开方式都失败时，把路径摆在用户面前（可选中复制），别让人干瞪眼。

    只在真有 QApplication 时弹（纯命令行/自测里调用不弹），弹不出来就算了——
    手册文件已经生成好了，路径也写在返回值和日志里。
    """
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox
    except Exception:
        return
    if QApplication.instance() is None:
        return
    box = QMessageBox(
        QMessageBox.Warning,
        "用户手册",
        "没能唤起系统浏览器，手册已经生成好了。\n"
        "可以复制下面的路径，手动粘到浏览器地址栏（或双击文件）打开：",
        QMessageBox.Ok,
    )
    box.setInformativeText(str(path))
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    box.exec()


def open_manual(entry: str | None = None) -> Path:
    """打开用户手册，返回被打开的 HTML 路径。

    **按模式分流**（见 ``prefer_static_manual``）：

    - 打包版（frozen）：直接打开构建期预生成的 ``docs/guide/manual.html``——
      不渲染、不写临时文件，点下去就只剩开浏览器那一下；万一产物里没有这个
      文件（老包 / 构建步骤没跑到），退回现渲染，功能不受影响；
    - 开发模式：**一律现渲染**到临时目录，改完 md 立刻看到新内容，不会被仓库里
      可能存在的旧静态文件顶掉。

    返回路径是为了调用方（或测试）能拿到产物做进一步处理。
    打不开浏览器时不抛异常——手册文件仍然在，用户可以手动打开，
    界面上会弹一个带路径的提示框。

    ⚠️ 不要给 URL 加 ``?v=<时间戳>`` 去防缓存：Windows 上最终还是要走系统 shell，
    查询串会被当成路径的一部分，实测地址栏里根本不出现。临时文件靠**文件名本身
    带时间戳**（见 ``_HTML_PREFIX``）保证 URL 唯一；静态文件靠"重装即替换"。

    ⚠️ 不要把 ``html_path.as_uri()`` 直接丢给系统（见 ``_open_with_system``）。
    """
    html_path = None
    if prefer_static_manual():
        static = static_manual_path()
        if static.exists():
            html_path = static
    if html_path is None:
        html_path = generate_manual_html(entry)
    if not _open_with_system(html_path):
        _notify_open_failed(html_path)
    return html_path
