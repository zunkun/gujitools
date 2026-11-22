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

from .css import _CSS_TEMPLATE, _css
from .document import _compose_document, generate_manual_html, generate_static_manual
from .opener import (
    _NO_WINDOW_FLAGS,
    _notify_open_failed,
    _open_with_system,
    open_manual,
)
from .paths import (
    MANUAL_ENTRIES,
    STATIC_MANUAL_NAME,
    _HTML_PREFIX,
    _KEEP_RECENT,
    _cleanup_old_manuals,
    manual_dir,
    prefer_static_manual,
    static_manual_path,
)
from .render import (
    _IMG_SRC_RE,
    _absolutize_image_srcs,
    _encode_image_srcs,
    _inline_image_srcs,
    _md_extensions,
    _md_to_fragment,
    _render_entry,
)
from .script import _JS

__all__ = [
    "MANUAL_ENTRIES",
    "STATIC_MANUAL_NAME",
    "generate_manual_html",
    "generate_static_manual",
    "manual_dir",
    "open_manual",
    "prefer_static_manual",
    "static_manual_path",
]
