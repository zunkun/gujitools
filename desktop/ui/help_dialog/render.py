# -*- coding: utf-8 -*-
"""Markdown → HTML 片段与截图路径处理（自 ``desktop/ui/help_dialog.py`` 拆出）。"""

from __future__ import annotations

import base64
import html as html_escape
import re
import urllib.parse
from pathlib import Path

from .paths import MANUAL_ENTRIES

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

    代价是 HTML 变大（13 张 PNG 约 6MB → base64 后约 8MB）。可接受：这只在
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
