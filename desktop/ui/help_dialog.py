# -*- coding: utf-8 -*-
"""用户手册对话框：直接渲染 ``docs/guide/*.md``，不引入任何新依赖。

为什么不是「生成 HTML」或「套 QWebEngineView」：

- **生成 HTML** 多一道构建步骤，改了 Markdown 就得重新生成，产物还会和源
  漂移；而 Qt 的 ``setHtml()`` 走的其实也是富文本子集，和 ``setMarkdown()``
  是同一条渲染管线，多绕一圈并没有换来更多样式自由度。
- **QWebEngineView** 会拖进 ``QtWebEngineProcess.exe`` 与百 MB 级资源包，
  与 ``guji.spec`` 现有的 excludes 裁剪策略直接冲突。

``QTextBrowser`` + ``QTextDocument`` 是 Qt 自带的，零新增依赖。实测
（PySide6 6.9.2）本项目的两份指南所需的三个能力它都具备：

1. **GFM 表格** —— ``cli.md`` 有 93 行表格，渲染正常；
2. **相对路径的中文名图片** —— ``gui-guide.md`` 引用 12 张 CJK 文件名截图，
   只要 ``setBaseUrl()`` 指到文档所在目录就能全部加载；
3. **大图自适应** —— 默认按图片原始像素画（会撑出横向滚动条），注入
   ``img { max-width: 100% }`` 后即按视口宽缩放。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QTextBrowser, QVBoxLayout
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import PushButton

from desktop import ui
from desktop.ui import theme as T
from desktop.utils.files import package_dir

#: 手册条目：(键, 分段开关文案, 文件名)。新增手册只改这里。
MANUAL_ENTRIES: tuple[tuple[str, str, str], ...] = (
    ("gui", "桌面端操作", "gui-guide.md"),
    ("cli", "命令行", "cli.md"),
)

#: 文档内联样式。
#:
#: ⚠️ ``img { max-width: 100% }`` 是必须的：Qt 默认按图片原始像素绘制，
#: 不加这条，1500px 宽的截图会把 900px 的视图撑出横向滚动条。
#: 其余只是让代码块/表头贴近设计令牌，去掉也不影响可读性。
_DOC_CSS = f"""
img {{ max-width: 100%; }}
pre {{ background: {T.SURFACE_SOFT}; border: 1px solid {T.BORDER};
       border-radius: {T.RADIUS_SM}px; padding: 6px 8px; }}
code {{ background: {T.SURFACE_SOFT}; }}
th {{ background: {T.SURFACE_SOFT}; }}
h1, h2, h3 {{ color: {T.INK}; }}
a {{ color: {T.ACCENT}; }}
"""


def manual_dir() -> Path:
    """手册目录（源码与打包两种模式下都可用）。

    与 ``package_dir()`` 同源：源码模式下 ``desktop/`` 的上一级就是仓库根，
    打包后数据文件由 ``guji.spec`` 的 ``gui_datas`` 落到 ``_internal/``，
    ``package_dir()`` 在 frozen 下返回 ``_MEIPASS/desktop``，再上一级同样是
    资源根，因此 ``package_dir().parent / "docs" / "guide"`` 两种模式通用。
    """
    return package_dir().parent / "docs" / "guide"


class ManualDialog(QDialog):
    """用户手册：顶部分段开关换文档，下面 ``QTextBrowser`` 渲染。"""

    def __init__(self, parent=None, entry: str | None = None):
        """构建界面并加载默认（或指定）条目。

        entry 为 ``MANUAL_ENTRIES`` 里的键；不传则加载第一项。
        """
        super().__init__(parent)
        self._documents: dict[str, QTextDocument] = {}
        self.setWindowTitle("用户手册")
        self.resize(940, 680)
        self._init_ui()
        entry = entry if entry else MANUAL_ENTRIES[0][0]
        self._switch.set_current(entry)
        self._show_entry(entry)

    # ------------------------------------------------------------------ 界面
    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(T.SPACE_LG, T.SPACE_MD, T.SPACE_LG, T.SPACE_LG)
        root.setSpacing(T.SPACE_MD)

        head = QHBoxLayout()
        head.setSpacing(T.SPACE_MD)
        head.addWidget(
            ui.apply_to(QLabel("用户手册"), T.SIZE_SUBTITLE, bold=True, color=T.INK)
        )
        head.addSpacing(T.SPACE_SM)

        self._switch = ui.SegmentedToggle(
            [(key, text) for key, text, _ in MANUAL_ENTRIES]
        )
        self._switch.current_changed.connect(self._show_entry)
        head.addWidget(self._switch)
        head.addStretch()

        close_btn = PushButton(FIF.CLOSE, "关闭")
        close_btn.setFixedHeight(30)
        close_btn.clicked.connect(self.close)
        head.addWidget(close_btn)
        root.addLayout(head)

        card = ui.Card(padding=T.SPACE_SM, spacing=0)
        self._browser = QTextBrowser()
        self._browser.setObjectName("manualBrowser")
        # 外链（如仓库地址）交给系统浏览器，别在手册里开导航
        self._browser.setOpenExternalLinks(True)
        card.box.addWidget(self._browser)
        root.addWidget(card, 1)

    # ------------------------------------------------------------------ 加载
    def _show_entry(self, key: str) -> None:
        """渲染指定条目；文件缺失时给出可读的占位文案而不是崩掉。"""
        doc = self._documents.get(key)
        if doc is None:
            doc = self._load(key)
            self._documents[key] = doc
        self._browser.setDocument(doc)
        self._browser.verticalScrollBar().setValue(0)

    def _load(self, key: str) -> QTextDocument:
        """把 Markdown 渲染成 ``QTextDocument``。

        必须用 ``QTextDocument`` 而不是 ``QTextBrowser.setMarkdown()``：
        后者是从 ``QTextEdit`` 继承来的，签名只有 ``(self, object)``，
        **没有 features 参数**，无法显式指定 dialect；而且我们需要给文档
        设 baseUrl（解析相对图片）与默认样式表（限制图片宽度）。
        """
        doc = QTextDocument(self)
        doc.setDefaultFont(ui.ui_font(T.SIZE_BODY))
        doc.setDefaultStyleSheet(_DOC_CSS)

        filename = next((f for k, _, f in MANUAL_ENTRIES if k == key), None)
        path = manual_dir() / filename if filename else None
        if path is None or not path.exists():
            doc.setPlainText(
                f"未找到手册文件：{path}\n\n"
                f"请确认 docs/guide/ 目录随程序一起分发。"
            )
            return doc

        text = path.read_text(encoding="utf-8")
        # ⚠️ baseUrl 必须指向文档所在目录，否则 12 张相对路径的截图加载不出来
        doc.setBaseUrl(QUrl.fromLocalFile(f"{path.parent}/"))
        doc.setMarkdown(text)
        return doc
