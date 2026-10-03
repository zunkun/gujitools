# -*- coding: utf-8 -*-
"""自定义矢量图标：补 qfluentwidgets 内置图标里没有的图形（带圆圈的问号）。

为什么不能直接继承 ``FluentIconBase`` 了事
----------------------------------------
``FluentIcon.path()`` 返回的是 **Qt 资源里的文件路径**
``:/qfluentwidgets/images/icons/Xxx_black.svg``，基类两条渲染链都靠
``path.endswith('.svg')`` 判断「是文件还是源码」：

* ``FluentIconBase.icon()``：只有 ``path.endswith('.svg') and color`` 时才包
  ``SvgIconEngine``，否则 ``QIcon(path)`` —— 把 SVG **源码字符串** 当文件名，
  得到一个空图标；
* ``FluentIconBase.render()``：只有 ``endswith('.svg')`` 时才 ``drawSvgIcon``
  （内存渲染），否则同样按文件走 ``QIcon(path).pixmap()``。

所以自绘 SVG 必须 **两个方法都重写**：只重写 ``icon()`` 的话，按钮自绘走的是
``paintEvent → _drawIcon → render()``，而 ``PushButton.paintEvent`` 在
``icon().isNull()`` 时直接 return，结果就是「只剩文字、图标不见了」。

几何
----
24×24 视图，外圈直径与内置 ``INFO`` 图标一致（几乎满幅，r=10、描边 1.6），
问号高度 ~12（与 INFO 里 ``i`` 的高度相当），整体上下居中，不出现内置
``HELP`` / ``QUESTION`` 那种被裁到边框上的偏移。
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QIcon
from qfluentwidgets import Theme
from qfluentwidgets.common.icon import (
    FluentIconBase, SvgIconEngine, drawSvgIcon, getIconColor,
)

__all__ = [
    "CustomIcon",
    "HELP_CIRCLE",
    "SCAN_TEXT_BOX",
    "SvgIcon",
    "resolve_nav_icon",
]

#: 带圆圈的问号：细圆环 + 圆头问号 + 圆点（Fluent regular 的 1.6 描边风格）。
QUESTION_CIRCLE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 24 24">'
    '<g fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" '
    'stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="10"/>'
    '<path d="M9.65 9.66a2.5 2.5 0 1 1 4.7 0q0 1.34-2.35 2.34V14.2"/>'
    '</g>'
    '<circle cx="12" cy="17.5" r="1.15" fill="{c}"/>'
    '</svg>'
)

#: 检测文本框：取景框四角 + 两条文本行（"框出页面上的文字"）。
#:
#: qfluentwidgets 1.11.2 内置图标里没有"扫描 / 检测框"这类图形，``SEARCH``
#: （放大镜）会被读成"查找"。这里用取景框（scan frame）表达"检测"，
#: 框内两条线表达"文本"。几何仍守 24×24、1.6 描边、圆头端点的内置风格，
#: 视觉重量与其它导航条目一致。
SCAN_TEXT_BOX = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 24 24">'
    '<g fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" '
    'stroke-linejoin="round">'
    '<path d="M4 8.5V7a3 3 0 0 1 3-3h1.5"/>'
    '<path d="M15.5 4H17a3 3 0 0 1 3 3v1.5"/>'
    '<path d="M20 15.5V17a3 3 0 0 1-3 3h-1.5"/>'
    '<path d="M8.5 20H7a3 3 0 0 1-3-3v-1.5"/>'
    '<path d="M8 10.5h8"/>'
    '<path d="M8 14h5"/>'
    '</g>'
    '</svg>'
)


class SvgIcon(FluentIconBase):
    """用**内存里的 SVG 源码**造图标（内置 FluentIcon 没有的图形）。

    模板里用 ``{c}`` 占位颜色，由 ``getIconColor(theme)``（black/white）或
    调用方显式给的 ``color`` 填入；深浅色主题自动跟随。
    """

    def __init__(self, template: str):
        self._template = template

    def path(self, theme: Theme = Theme.AUTO) -> str:
        """返回填好颜色的 SVG 源码（不是文件路径）。"""
        return self._template.format(c=getIconColor(theme))

    def icon(self, theme: Theme = Theme.AUTO, color: QColor | str | None = None
             ) -> QIcon:
        """包成 ``QIcon``：必须走 ``SvgIconEngine``，否则得到空图标。"""
        c = QColor(color).name() if color is not None else getIconColor(theme)
        return QIcon(SvgIconEngine(self._template.format(c=c)))

    def render(self, painter, rect, theme: Theme = Theme.AUTO, indexes=None,
               **attributes) -> None:
        """自绘入口（按钮/菜单走这条）：直接把源码交给 ``QSvgRenderer``。"""
        drawSvgIcon(self.path(theme).encode(), painter, rect)


class CustomIcon:
    """自定义图标集合：用法与 ``FluentIcon`` 一致（直接传给按钮等控件）。"""

    HELP_CIRCLE = SvgIcon(QUESTION_CIRCLE)
    SCAN_TEXT_BOX = SvgIcon(SCAN_TEXT_BOX)


#: 常用别名：``HELP_CIRCLE`` 可直接当图标对象传给 ``PushButton`` 等。
HELP_CIRCLE = CustomIcon.HELP_CIRCLE
SCAN_TEXT_BOX = CustomIcon.SCAN_TEXT_BOX


def resolve_nav_icon(name: str):
    """按 ``nav_icon`` 的字符串取导航图标对象（壳层专用入口）。

    - ``"svg:名字"`` → :class:`CustomIcon` 里的自绘图（内置图标没有的图形，
      如检测文本框的取景框）；
    - 其它 → ``FluentIcon`` 的同名成员（历史行为，``spec.nav_icon`` 的注释
      与各步骤的取值都按这个写）。

    名字不存在时**抛 AttributeError**——图标名是代码里写死的常量，写错了
    应该在启动第一时间炸出来，而不是渲染出一列空导航。
    """
    if name.startswith("svg:"):
        return getattr(CustomIcon, name[4:])
    from qfluentwidgets import FluentIcon

    return getattr(FluentIcon, name)
