# -*- coding: utf-8 -*-
"""应用级外观设置：字体、主题色、全局样式表。

只覆盖三类东西，其余交给 qfluentwidgets 自己的绘制，避免和它的
代理/动画打架：

1. 全局字体（中文优先，Windows/Linux 都有回退）；
2. 窗口底色与滚动条：默认的浅灰偏冷、滚动条过粗；
3. 少数原生控件（表格）的描边与圆角。

注意：日志文本域（`#logView`）的样式**不在**这里——qfluentwidgets 的
`TextEdit` 构造时会给控件自身设样式表，控件级优先级高于应用级，写在全局
QSS 里不会生效；它由 `desktop.components.log_panel.apply_log_view_style`
在控件上设置。
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase

from desktop.ui import theme as T


def resolve_font_family() -> str:
    """挑一个系统里存在的中文字体族，避免落到无衬线默认字体。"""
    families = set(QFontDatabase.families())
    for name in (T.FONT_FAMILY, *T.FONT_FALLBACK):
        if name in families:
            return name
    return T.FONT_FAMILY


def apply_app_style(app) -> None:
    """统一字体/主题色/全局样式（在创建主窗口前调用）。"""
    family = resolve_font_family()
    font = QFont(family)
    font.setPixelSize(T.SIZE_BODY)
    app.setFont(font)
    app.setStyleSheet(global_stylesheet())

    try:
        from qfluentwidgets import setThemeColor

        setThemeColor(QColor(T.ACCENT))
    except (ImportError, AttributeError):
        pass


def global_stylesheet() -> str:
    """生成应用全局样式表（底色 / 滚动条 / 表格边框）。

    只给窗口与 #pageRoot 上色，避免把嵌套的 QStackedWidget 刷灰；其余外观
    交给 qfluentwidgets 自绘，不与它的代理/动画打架。字体族不在这里设，
    由 ``apply_app_style`` 通过 ``app.setFont`` 统一指定。
    """
    return f"""
    /* ---- 底色 ----
       注意：只给窗口与页面根节点上色。之前把 QStackedWidget 也写进来，
       结果卡片内部嵌套的 QStackedWidget（预览区/控制区）被刷成灰底，
       在白卡片上露出一块突兀的灰块。 */
    QMainWindow, QWidget#pageRoot {{
        background: {T.CANVAS};
    }}

    /* ---- 滚动条：细一点，不要默认那种宽灰条 ---- */
    QScrollBar:vertical {{
        background: transparent; width: 10px; margin: 2px 2px 2px 0;
    }}
    QScrollBar:horizontal {{
        background: transparent; height: 10px; margin: 0 2px 2px 2px;
    }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: #C9D1D8; border-radius: 4px; min-height: 32px; min-width: 32px;
    }}
    QScrollBar::handle:hover {{ background: #AEB8C1; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* ---- 表格：行高与选中态由控件自身设置，这里只统一边框 ---- */
    QTableWidget#taskTable {{
        background: {T.SURFACE};
        border: 1px solid {T.BORDER};
        border-radius: {T.RADIUS_MD}px;
    }}
    """
