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
把 ``docs/guide/*.md`` 转成完整 HTML，内嵌匹配应用主题的 CSS，写到临时文件
后用系统默认浏览器打开。**

这样做的好处：

1. **零重量依赖** —— ``markdown`` 是纯 Python 单包，不引入 Qt 之外的二进制；
2. **完整 GFM** —— 表格、围栏代码块、嵌套列表都按规范渲染；
3. **图片照旧可用** —— 靠 ``<base>`` 把文档基准指向 ``docs/guide/``，
   12 张相对路径的中文名截图正常加载，Markdown 里的写法一个字都不用改；
4. **样式自由** —— 真实浏览器渲染，CSS 不受 Qt 富文本子集限制；
5. **不做构建步骤** —— HTML 是**运行时**生成的，改了 Markdown 重新打开
   手册就是新的，不存在产物与源漂移的问题。

两条关键实现约束（改动时别踩）：

- **``<base>`` 必须指向手册目录且带结尾斜杠**：否则
  ``screenshots/guide/*.png`` 会相对临时文件解析，全变成碎图。
- **指南之间的互链要改成页内 tab 跳转**：``gui-guide.md`` 里有
  ``[cli.md](cli.md)``，浏览器会把 .md 当纯文本显示，必须改写为
  ``#tab-cli`` 交给 JS 切页。
"""

from __future__ import annotations

import html as html_escape
import re
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
    ("gui", "桌面端操作", "gui-guide.md"),
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


# --------------------------------------------------------------------------- CSS
# ⚠️ 用 string.Template（``$NAME`` 占位）而不是 f-string：CSS 里花括号极多，
#    f-string 要把每个 { } 都写成 {{ }}，可读性直接报废。
#    颜色一律取 desktop/ui/theme.py 的设计令牌，不在这里重复硬编码色值。
_CSS_TEMPLATE = Template("""
:root {
  --ink: $INK;
  --ink-soft: $INK_SOFT;
  --bg: $CANVAS;
  --surface: $SURFACE;
  --surface-soft: $SURFACE_SOFT;
  --border: $BORDER;
  --accent: $ACCENT;
  --accent-soft: $ACCENT_SOFT;
  --danger: $DANGER;
  --radius: ${RADIUS_MD}px;
  --radius-sm: ${RADIUS_SM}px;
}

* { box-sizing: border-box; }

body {
  font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
               "Noto Sans CJK SC", "WenQuanYi Zen Hei", "SimHei", sans-serif;
  font-size: 14px;
  line-height: 1.75;
  color: var(--ink);
  background: var(--bg);
  margin: 0;
  padding: 0;
}

.wrap { max-width: 940px; margin: 0 auto; padding: 0 32px 96px; }

/* ---- 顶部分段开关（吸顶） ---- */
.tab-bar {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  gap: 4px;
  padding: 12px 32px;
  margin: 0 -32px 28px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.tab {
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--ink-soft);
  font-family: inherit;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.tab:hover { background: var(--surface-soft); color: var(--ink); }
.tab.active { background: var(--accent); color: #FFFFFF; }

.tab-content { display: none; }
.tab-content.active { display: block; }

/* ---- 标题 ---- */
h1 {
  font-size: 25px;
  font-weight: 600;
  margin: 0 0 18px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--border);
}

h2 { font-size: 20px; font-weight: 600; margin: 36px 0 14px; }
h3 { font-size: 16px; font-weight: 600; margin: 26px 0 10px; }
h4 { font-size: 14px; font-weight: 600; margin: 20px 0 8px; color: var(--ink-soft); }

p { margin: 10px 0; }

/* ---- 表格 ---- */
table {
  border-collapse: collapse;
  width: 100%;
  margin: 18px 0;
  font-size: 13px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

th, td {
  border: 1px solid var(--border);
  padding: 9px 13px;
  text-align: left;
  vertical-align: top;
}

th { background: var(--surface-soft); font-weight: 600; }
tr:nth-child(even) td { background: #FAFBFC; }

/* ---- 代码 ---- */
pre {
  background: var(--surface-soft);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 13px 16px;
  margin: 14px 0;
  overflow-x: auto;
  line-height: 1.55;
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

/* ---- 截图 ---- */
/* max-width 是必须的：1500px 宽的截图不缩会撑出横向滚动条 */
img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 16px 0;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface);
}

/* ---- 引用块 ---- */
blockquote {
  margin: 16px 0;
  padding: 10px 18px;
  background: var(--accent-soft);
  border-left: 4px solid var(--accent);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  color: var(--ink-soft);
}

blockquote p { margin: 5px 0; }

/* ---- 列表 ---- */
ul, ol { padding-left: 26px; margin: 10px 0; }
li { margin: 5px 0; }
li > ul, li > ol { margin: 5px 0; }

/* ---- 其他 ---- */
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

hr { border: none; border-top: 1px solid var(--border); margin: 30px 0; }

strong { font-weight: 600; }

/* 手册文件缺失 / markdown 库缺失时的提示 */
.missing {
  color: var(--danger);
  background: #FBEAEA;
  padding: 12px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid #F0C9C9;
}
""")


def _css() -> str:
    """把 CSS 模板里的 ``$TOKEN`` 换成 theme.py 的设计令牌。"""
    return _CSS_TEMPLATE.substitute(
        INK=T.INK,
        INK_SOFT=T.INK_SOFT,
        CANVAS=T.CANVAS,
        SURFACE=T.SURFACE,
        SURFACE_SOFT=T.SURFACE_SOFT,
        BORDER=T.BORDER,
        ACCENT=T.ACCENT,
        ACCENT_SOFT=T.ACCENT_SOFT,
        DANGER=T.DANGER,
        RADIUS_MD=T.RADIUS_MD,
        RADIUS_SM=T.RADIUS_SM,
    )


# ---------------------------------------------------------------------------- JS
_JS = """
(function () {
  function activate(tabId) {
    var tabs = document.querySelectorAll('.tab');
    var pans = document.querySelectorAll('.tab-content');
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].classList.toggle('active', tabs[i].dataset.tab === tabId);
    }
    for (var j = 0; j < pans.length; j++) {
      pans[j].classList.toggle('active', pans[j].id === 'tab-' + tabId);
    }
    if (history.replaceState) { history.replaceState(null, null, '#tab-' + tabId); }
    window.scrollTo(0, 0);
  }

  var tabs = document.querySelectorAll('.tab');
  for (var i = 0; i < tabs.length; i++) {
    tabs[i].addEventListener('click', function () { activate(this.dataset.tab); });
  }

  // 正文里指向另一份手册的链接（已改写成 #tab-xxx）→ 切页而不是跳锚点
  var links = document.querySelectorAll('a[href^="#tab-"]');
  for (var k = 0; k < links.length; k++) {
    links[k].addEventListener('click', function (e) {
      e.preventDefault();
      activate(this.getAttribute('href').slice(5));
    });
  }

  // 支持 #tab-cli 这样的深链直达
  var m = location.hash.match(/^#tab-(.+)$/);
  if (m) { activate(m[1]); }
})();
"""


def _render_entry(guide_dir: Path, filename: str) -> str:
    """渲染单个手册条目为 HTML 片段；文件缺失时给出可读占位而不是崩掉。"""
    path = guide_dir / filename
    if not path.exists():
        return (
            f'<p class="missing">未找到手册文件：{html_escape.escape(str(path))}'
            f"<br>请确认 docs/guide/ 目录随程序一起分发。</p>"
        )
    fragment = _md_to_fragment(path.read_text(encoding="utf-8"))
    # 图片路径改绝对 URL（带中文名必须预编码，只靠 <base> 浏览器取不到）
    return _absolutize_image_srcs(fragment, guide_dir)


def generate_manual_html(entry: str | None = None) -> Path:
    """把全部手册渲染成一个带分段开关的 HTML 文件，返回其路径。

    entry 为 ``MANUAL_ENTRIES`` 里的键，决定默认激活哪个标签页；
    不传则激活第一项。

    ⚠️ ``<base>`` 指向手册目录（带结尾斜杠）是图片能加载的唯一保证：
    Markdown 里写的是 ``screenshots/guide/xxx.png`` 这样的相对路径，
    而 HTML 落在临时目录，不设 base 就会相对临时目录解析成碎图。
    """
    guide_dir = manual_dir().resolve()
    active_key = entry or MANUAL_ENTRIES[0][0]

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
            f'id="tab-{key}">{_render_entry(guide_dir, filename)}</section>'
        )

    base_href = guide_dir.as_uri().rstrip("/") + "/"
    document = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<base href="{base_href}">
<title>用户手册 · guji</title>
<style>
{_css()}
</style>
</head>
<body>
<div class="wrap">
<nav class="tab-bar">
{"".join(tabs)}
</nav>
{"".join(panels)}
</div>
<script>
{_JS}
</script>
</body>
</html>
"""
    # 文件名带毫秒时间戳 → URL 每次都唯一 → 浏览器缓存不可能命中旧版本
    out_path = Path(tempfile.gettempdir()) / f"{_HTML_PREFIX}{int(time.time() * 1000)}.html"
    out_path.write_text(document, encoding="utf-8")
    _cleanup_old_manuals()
    return out_path


def open_manual(entry: str | None = None) -> Path:
    """生成手册 HTML 并用系统默认浏览器打开，返回该文件路径。

    返回路径是为了调用方（或测试）能拿到产物做进一步处理。
    浏览器打不开时 ``webbrowser.open`` 只是返回 False，不抛异常——
    手册文件仍然生成好了，用户可以手动打开。

    ⚠️ 不要给 URL 加 ``?v=<时间戳>`` 去防缓存：Windows 上
    ``webbrowser.open`` 最终走 ``os.startfile``，查询串会被当成路径的
    一部分，实测地址栏里根本不出现。防缓存靠的是**文件名本身带时间戳**
    （见 ``_HTML_PREFIX``），每次都是新 URL。
    """
    html_path = generate_manual_html(entry)
    webbrowser.open(html_path.as_uri())
    return html_path
