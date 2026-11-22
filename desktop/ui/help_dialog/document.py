# -*- coding: utf-8 -*-
"""拼装完整手册 HTML 并落盘（自 ``desktop/ui/help_dialog.py`` 拆出）。"""

from __future__ import annotations

import html as html_escape
import tempfile
import time
from pathlib import Path

from config import VERSION

from .css import _css
from .paths import (
    MANUAL_ENTRIES,
    _HTML_PREFIX,
    _cleanup_old_manuals,
    manual_dir,
    static_manual_path,
)
from .render import _render_entry
from .script import _JS

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
    #: 手册里显示的**程序版本**（用户 2026-10-15：帮助文档内容要有版本号）。
    #: ⚠️ 取 ``config.VERSION``（唯一来源）而不是写死在 md/模板里：开发模式每次点
    #: 「使用手册」都现渲染，看到的就是当前源码的版本；打包版在构建期烘进静态
    #: manual.html，与安装包里的程序版本天然一致，不会出现"手册说 v2.0.3、程序是
    #: v2.0.4"。两个入口共用本函数，所以只在这里注入一处。
    version_text = f"v{VERSION}"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<!-- ⚠️ 绝对不要加 HTML 的 base 标签！片段链接（#sec-8 / #tab-cli）是按它解析的：
     一旦它指向手册目录，点标题旁的 # 锚点就变成"打开 docs/guide 目录"，
     浏览器直接把目录列表当页面显示（真实踩过：用户点标题跳出了目录列表）。
     图片不靠它——开发模式写成绝对 file:// URL，生产模式内联成 data URI。 -->
<title>用户手册 · guji {version_text}</title>
<style>
{_css()}
</style>
</head>
<body>
<header class="topbar">
<div class="topbar-inner">
<div class="brand"><span class="brand-mark">古籍重製</span><span class="brand-sub">用户手册 · {version_text}</span></div>
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
<footer class="foot">内容来自 <code>docs/guide/*.md</code>，{generated_note} · 版本 {version_text} · 生成于 {generated_at}</footer>
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
