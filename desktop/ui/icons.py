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
    FluentIconBase,
    SvgIconEngine,
    drawSvgIcon,
    getIconColor,
)

__all__ = [
    "CustomIcon",
    "HELP_CIRCLE",
    "PDF_FILE",
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
    "</g>"
    '<circle cx="12" cy="17.5" r="1.15" fill="{c}"/>'
    "</svg>"
)

#: 检测文本框（导航"检测"步骤用）：四角取景框 + 中间方框 + 一条贯穿的横线。
#:
#: 按用户给的 ``icons8-scan-50.png`` 描摹：源图就是 50×50 网格、描边 2、
#: 平头端 + 直角，所以 ``viewBox`` 直接用 ``0 0 50 50``——viewBox 只是内部
#: 坐标系，渲染时会自动缩放到目标矩形（导航里是硬编码的 16×16），
#: 坐标可以对着源图直接量、直接改，数值大小不影响最终尺寸。
#:
#: ⚠️ **别用 ``<text>``**：``QSvgRenderer`` 渲染 ``<text>`` 依赖 QPainter
#:    字体，放大时会整个丢字，且打包后字体不可控。
SCAN_TEXT_BOX = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" '
    'viewBox="0 0 50 50">'
    '<g fill="none" stroke="{c}" stroke-width="2">'
    # 四角取景框（L 形，臂长 5.75）
    '<path d="M5 10.75V5h5.75"/>'
    '<path d="M45 10.75V5h-5.75"/>'
    '<path d="M5 39.25V45h5.75"/>'
    '<path d="M45 39.25V45h-5.75"/>'
    # 中间方框：上沿 + 两侧竖边（竖边到横线为止）
    '<path d="M14 34V11H36V34"/>'
    # 贯穿的横线
    '<path d="M4.25 33H45.75"/>'
    # 横线下方的小托盘（方框的下半段）
    '<path d="M14 36V39H36V36"/>'
    "</g>"
    "</svg>"
)


#: PDF 文件：文档轮廓 + 折角 + Acrobat 飘带标志。
#:
#: 为什么不用现成的：qfluentwidgets 1.11.2 内置的 174 个图标里没有 PDF，
#: 最接近的 ``DOCUMENT`` 是**纯空白文档**——放进"生成 PDF"这一步、
#: "选择 PDF"按钮、空状态插图里都会被读成"文档"，而不是 PDF。
#:
#: ⚠️⚠️ **改大这个图标前必读**（用户 2026-10-03 踩过）：
#:
#: 1. **改 ``viewBox`` 不会让图标变大。** viewBox 只是**内部坐标系**，
#:    Qt 渲染时把整个 viewBox 缩放到调用方给的矩形（导航里是**硬编码的
#:    16×16**，见 qfluentwidgets ``navigation_widget.py`` 的
#:    ``drawIcon(..., QRectF(11.5+pl, 10, 16, 16))``，API 改不了）。
#:    把 24 改成 50 视觉上**完全一样**，只会连带把描边压细。
#:    要真放大只能改库或换控件——不是改 SVG 能解决的。
#:
#: 2. **16px 是本图标的最小可用尺寸**：笔画要够粗才不会糊。
#:    实测（tests 探针，16px 渲染后数深色像素占比）：
#:    旧的自绘"PDF 三字"版是 **30.5%** —— 三个字母挤在 8px 里、彼此粘连，
#:    用户报"PDF 文字成了一坨"；换成当前这版（文档框 + Acrobat 飘带）
#:    只有 **11.3%**，16px 下轮廓与飘带都清晰可辨。
#:    ⚠️ 这也是**别退回"挤三个字母"写法**的原因：字母在小尺寸下密度太高。
#:
#: 3. **不能用 ``<text>``**：``QSvgRenderer`` 渲染 ``<text>`` 依赖 QPainter
#:    字体，放大时会整个丢字（实测 64px 只剩文档框），且打包后字体不可控。
#:
#: ⚠️ **色彩适配**（本项目特有）：原图是"黑标志 + 白纸"。我们把它套在深浅
#: 色主题的按钮/导航上，所以：文档轮廓的**白填充改成 ``none``**（透明底）、
#: 所有黑色改成 ``{c}`` 占位，由 ``getIconColor(theme)`` 填色。
#: ⚠️ 文档轮廓的 ``stroke-width=30`` 是按这份 533 坐标网格给的比例
#:    （≈5.6% 图宽，与其它图标 1.6/24 同量级），换坐标系时要一起换算。
PDF_FILE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 533.333 533.333">'
    # Acrobat 飘带标志（实心）
    '<path fill="{c}" d="M438.548,307.021c-7.108-7.003-22.872-10.712-46.86-11.027'
    'c-16.238-0.179-35.782,1.251-56.339,4.129c-9.205-5.311-18.691-11.091-26.139'
    '-18.051c-20.033-18.707-36.755-44.673-47.175-73.226c0.679-2.667,1.257-5.011,'
    '1.795-7.403c0,0,11.284-64.093,8.297-85.763c-0.411-2.972-0.664-3.834-1.463'
    '-6.144l-0.98-2.518c-3.069-7.079-9.087-14.58-18.522-14.171l-5.533-0.176'
    'l-0.152-0.003c-10.521,0-19.096,5.381-21.347,13.424c-6.842,25.226,0.218,62.964,'
    '13.012,111.842l-3.275,7.961c-9.161,22.332-20.641,44.823-30.77,64.665l-1.317,'
    '2.581c-10.656,20.854-20.325,38.557-29.09,53.554l-9.05,4.785c-0.659,0.348'
    '-16.169,8.551-19.807,10.752c-30.862,18.427-51.313,39.346-54.706,55.946'
    'c-1.08,5.297-0.276,12.075,5.215,15.214l8.753,4.405c3.797,1.902,7.801,2.866,'
    '11.903,2.866c21.981,0,47.5-27.382,82.654-88.732c40.588-13.214,86.799'
    '-24.197,127.299-30.255c30.864,17.379,68.824,29.449,92.783,29.449'
    'c4.254,0,7.921-0.406,10.901-1.194c4.595-1.217,8.468-3.838,10.829-7.394'
    'c4.648-6.995,5.591-16.631,4.329-26.497C443.417,313.113,441.078,309.493,'
    '438.548,307.021z M110.233,423.983c4.008-10.96,19.875-32.627,43.335-51.852'
    'c1.475-1.196,5.108-4.601,8.435-7.762C137.47,403.497,121.041,419.092,'
    '110.233,423.983z M249.185,104.003c7.066,0,11.085,17.81,11.419,34.507'
    'c0.333,16.698-3.572,28.417-8.416,37.088c-4.012-12.838-5.951-33.073-5.951'
    '-46.304C246.237,129.294,245.942,104.003,249.185,104.003z M207.735,332.028'
    'c4.922-8.811,10.043-18.103,15.276-27.957c12.756-24.123,20.812-42.999,26.812'
    '-58.514c11.933,21.71,26.794,40.167,44.264,54.955c2.179,1.844,4.488,3.698,'
    '6.913,5.547C265.474,313.088,234.769,321.637,207.735,332.028z M431.722,330.027'
    'c-2.164,1.353-8.362,2.135-12.349,2.135c-12.867,0-28.787-5.883-51.105-15.451'
    'c8.575-0.635,16.438-0.957,23.489-0.957c12.906,0,16.729-0.056,29.349,3.163'
    'S433.885,328.674,431.722,330.027z"/>'
    # 文档轮廓 + 右上折角（透明底，避免压在深色主题上出现白块）
    '<path fill="none" stroke="{c}" stroke-width="30" stroke-linejoin="round"'
    ' d="M470.538,103.87L396.13,29.463C379.925,13.258,347.917,0,325,0H75'
    'C52.083,0,33.333,18.75,33.333,41.667v450c0,22.916,18.75,41.666,41.667,41.666'
    'h383.333c22.916,0,41.666-18.75,41.666-41.666V175'
    'C500,152.083,486.742,120.074,470.538,103.87z M446.968,127.44'
    'c1.631,1.631,3.255,3.633,4.833,5.893h-85.134V48.2c2.261,1.578,4.263,3.203,'
    '5.893,4.833L446.968,127.44z"/>'
    "</svg>"
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

    def icon(self, theme: Theme = Theme.AUTO, color: QColor | str | None = None) -> QIcon:
        """包成 ``QIcon``：必须走 ``SvgIconEngine``，否则得到空图标。"""
        c = QColor(color).name() if color is not None else getIconColor(theme)
        return QIcon(SvgIconEngine(self._template.format(c=c)))

    def render(self, painter, rect, theme: Theme = Theme.AUTO, indexes=None, **attributes) -> None:
        """自绘入口（按钮/菜单走这条）：直接把源码交给 ``QSvgRenderer``。"""
        drawSvgIcon(self.path(theme).encode(), painter, rect)


class CustomIcon:
    """自定义图标集合：用法与 ``FluentIcon`` 一致（直接传给按钮等控件）。"""

    HELP_CIRCLE = SvgIcon(QUESTION_CIRCLE)
    SCAN_TEXT_BOX = SvgIcon(SCAN_TEXT_BOX)
    PDF_FILE = SvgIcon(PDF_FILE)


#: 常用别名：``HELP_CIRCLE`` 可直接当图标对象传给 ``PushButton`` 等。
HELP_CIRCLE = CustomIcon.HELP_CIRCLE
SCAN_TEXT_BOX = CustomIcon.SCAN_TEXT_BOX
PDF_FILE = CustomIcon.PDF_FILE


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
