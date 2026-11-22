# -*- coding: utf-8 -*-
"""无边框主窗口的自绘标题栏与菜单栏装配（自 ``desktop/ui/menu.py`` 拆出）。"""

from __future__ import annotations

from qfluentwidgets import MSFluentTitleBar

from desktop.ui import theme as T
from desktop.ui.widgets import apply_to, ui_font

from ._qt import (
    QColor,
    QHBoxLayout,
    QLabel,
    QMenuBar,
    QPalette,
    QWidget,
    Qt,
)
from .constants import (
    MENU_EDIT,
    MENU_FILE,
    MENU_HELP,
    MENU_MODULES,
    TITLE_BAR_BG,
    TITLE_BAR_FONT_SIZE,
    TITLE_BAR_ROW_HEIGHT,
)
from .menus import (
    build_edit_menu,
    build_file_menu,
    build_help_menu,
    build_modules_menu,
)

# ------------------------------------------------------------------ 组装
def install_title_bar(window):
    """给**无边框主窗口**装自绘标题栏（图标 / 标题 / 菜单同排），返回标题栏。

    ⚠️⚠️ 为什么必须换成无边框自绘标题栏（用户 2026-10-15：「这个菜单**不要另起
    一行**，要在上面**标题后面**」）：Windows 的原生标题栏由系统绘制，**任何 Qt
    控件都塞不进去**；而 ``QMainWindow`` 自己的菜单栏天生是标题栏**下面的一整行**。
    能做到"菜单和标题同排"的唯一路子是：窗口改无边框（``qframelesswindow`` 的
    ``FramelessMainWindow``）+ 自绘标题栏（qfluentwidgets 的 ``MSFluentTitleBar``，
    自带最小化/最大化/关闭与拖拽）。拖拽、四边缩放、双击最大化、贴边吸附仍由
    **系统原生**命中测试完成（``qframelesswindow`` 处理 ``WM_NCHITTEST`` 与
    ``SC_MOVE``），不是我们手写的近似实现。

    三步接线（顺序有讲究）：

    1. ``setTitleBar``：库钩子，换掉默认标题栏并挂到窗口上（它会 ``raise_()``）；
    2. ``setMenuWidget``：把标题栏放进 ``QMainWindow`` 的**菜单位** ⇒ 它就是窗口
       最上面的一整行，且中央控件会自动让开（实测中央控件 y = 标题栏高），
       不用手工留白；
    3. ``install_menu_bar``：把菜单栏插进标题栏布局的**标题之后**。

    ⚠️ 最后还要手工同步一次标题/图标：``FluentTitleBar`` 是靠
    ``windowTitleChanged / windowIconChanged`` 自动跟随的，而主窗口的
    ``setWindowTitle`` / ``setWindowIcon`` 都在本函数**之前**已经调过——那两个
    信号已经错过了，不同步的话标题栏一片空白（实测）。
    """
    bar = MSFluentTitleBar(window)
    window.setTitleBar(bar)
    # 顶栏整条统一底色（用户要求，见 TITLE_BAR_BG）。
    # ⚠️⚠️ 底色**由我们自己套的容器画**，不是给标题栏设背景：库的标题栏自身不画
    #   背景（实测两条路都不生效——QSS 里塞 background：``QWidget`` 子类默认不画，
    #   开了 ``WA_StyledBackground`` 也被它那一整串 QSS 的渲染路径吞掉；调色板 +
    #   ``setAutoFillBackground`` 同样没反应），而库里那串样式表**不能整体替换**
    #   （会把最小化/最大化/关闭三个按钮的外观一起毁掉，见 desktop/ui/widgets.py::
    #   bold_button 记的同款教训）。所以外面套一层只负责底色的 QWidget：标题栏零
    #   边距铺满它，底色自然透出来（含右侧按钮那一段），整条顶栏一个色。
    holder = QWidget(window)
    holder.setObjectName("appTitleBar")
    holder.setAutoFillBackground(True)
    holder_palette = holder.palette()
    holder_palette.setColor(QPalette.ColorRole.Window, QColor(TITLE_BAR_BG))
    holder.setPalette(holder_palette)
    holder_layout = QHBoxLayout(holder)
    holder_layout.setContentsMargins(0, 0, 0, 0)
    holder_layout.setSpacing(0)
    holder_layout.addWidget(bar)
    window.setMenuWidget(holder)
    install_menu_bar(window)
    bar.setTitle(window.windowTitle())
    icon = window.windowIcon()
    if not icon.isNull():
        bar.setIcon(icon)
    # 标题与菜单**必须同字号、同基线**（用户 2026-10-15：「文字大小一致，即使不一致
    # 也要底部对齐」）。
    # ⚠️⚠️ 库给的 ``bar.titleLabel`` 是 ``CaptionLabel``，带 qfluentwidgets 给标签定义
    #    的样式，**外面改不动它的渲染字号**：``setFont``（控件属性被 QSS 压过）、
    #    祖先样式表 ``#appTitleBar #titleLabel``（Qt 里"控件自身的规则"优先于祖先）、
    #    乃至把样式表设在标签自己身上（qfluentwidgets 的标签样式是在 polish 阶段
    #    再套上去的）——三条路实测都改不了它渲染出来的大小，标题始终比菜单小一截。
    #    所以**自造一个素 QLabel**当标题：它的字体只由我们的 ``apply_to`` 决定，与
    #    菜单条（只受 ``ui_font`` 影响）必然同款；库那个标签只是隐藏、仍留着接
    #    ``windowTitleChanged → setTitle``（隐藏不等于删，删了库内部会出问题）。
    bar.titleLabel.hide()
    title_label = QLabel(window.windowTitle(), bar)
    title_label.setObjectName("appTitleLabel")
    apply_to(title_label, TITLE_BAR_FONT_SIZE, color=T.INK)
    # 与菜单条同高：两边都是"在自己的盒子里垂直居中"，盒高一致 ⇒ 基线一致（见
    # TITLE_BAR_ROW_HEIGHT 的说明）。
    title_label.setFixedHeight(TITLE_BAR_ROW_HEIGHT)
    window.windowTitleChanged.connect(title_label.setText)
    layout = bar.hBoxLayout
    layout.insertWidget(
        layout.indexOf(bar.titleLabel),
        title_label,
        0,
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    )
    # ⚠️ 用 ``setattr`` 挂"库类没有声明过的属性"：``MSFluentTitleBar`` 的存根里没有
    #    ``appTitleLabel``，直接赋值会被 Pyright/Pylance 报
    #    ``reportAttributeAccessIssue``（同 ``desktop/app.py`` 里往 QApplication 上挂
    #    ``_sigint_keepalive`` 的那次处理）。取用方也一律 ``getattr``。
    setattr(bar, "appTitleLabel", title_label)
    window.title_bar = bar
    window.title_bar_holder = holder
    return bar


def install_menu_bar(window) -> QMenuBar:
    """把菜单栏（文件 / 编辑 / 独立功能 / 帮助）插进**标题栏的标题之后**。

    ⚠️ 用 ``QMenuBar(window.titleBar)`` 而**不是** ``window.menuBar()``：
    ``QMainWindow.menuBar()`` 会就地造出**标题栏下面的一整行**空菜单栏——那正是
    用户不要的"另起一行"（而且它一旦被创建就永远占着那一行的位置）。

    插入位置**现算**（``hBoxLayout.indexOf(titleLabel) + 1``）而不是写死索引：
    标题栏布局里还有图标、间距与右侧按钮列，写死数字会在库更新布局时静默错位。

    返回 ``QMenuBar`` 本身；一并留下三样引用：

    - ``window.menu_bar``：自测与外部取菜单栏（**不要再调** ``window.menuBar()``）；
    - ``window.menus``：三个顶级菜单（按文案取），**必须持有**——见下；
    - ``window.update_controller``：更新控制器（自测与将来"启动时检查"共用同一个）。

    ⚠️⚠️ **三个菜单必须留下活引用，且必须显式指定父对象**（2026-10-15 实测踩到）：
    PySide6 把 ``QMenuBar.addMenu("文案")`` 造出来的 ``QMenu`` **交给 Python 持有**
    ——返回的包装对象一旦被回收，C++ 侧的菜单就跟着销毁，而菜单栏上的 action 仍
    指着一个悬空菜单：表现是**菜单条还在、点开却没有内容**，且读它的地方直接抛
    ``RuntimeError: Internal C++ object (QMenu) already deleted``（连读都读不到）。
    所以这里一律 ``QMenu(文案, bar)`` 显式给父 + 用 ``window.menus`` 留引用，
    两道保险都在。别退回 ``bar.addMenu("文案")`` 那种一行写法。
    """
    title_bar = window.titleBar
    bar = QMenuBar(title_bar)
    # 与标题**同字号**（用户 2026-10-15：标题与菜单字大小不一致 ⇒ 统一；
    # 菜单弹窗跟着菜单条走，见 _add_menu 里的 setFont）。
    bar.setFont(ui_font(TITLE_BAR_FONT_SIZE))
    # 与标题同高（见 TITLE_BAR_ROW_HEIGHT）：两边都垂直居中 ⇒ 文字基线对齐。
    bar.setFixedHeight(TITLE_BAR_ROW_HEIGHT)
    # ⚠️ 菜单栏自带一层白底（系统样式按调色板的 Window 色画），会把刚统一好的顶栏
    #    底色截成两截——把 Window 角色设成**全透明**：SourceOver 下空操作色什么都
    #    盖不住，顶栏本色自然透出来；其它角色（文字/hover 高亮）一概不动，选中态与
    #    弹出菜单仍由系统样式画（不动样式表就不会把菜单拉进 QSS 渲染模式）。
    palette = bar.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0, 0))
    bar.setPalette(palette)
    bar.setObjectName("appTitleMenuBar")
    window.menus = {
        MENU_FILE: build_file_menu(bar, window),
        MENU_EDIT: build_edit_menu(bar, window),
        MENU_MODULES: build_modules_menu(bar, window),
        MENU_HELP: build_help_menu(bar, window),
    }
    window.update_controller = window.menus[MENU_HELP].controller  # type: ignore[attr-defined]
    #: 「去底色数据包」控制器（自测与"启动时后台静默检查"共用同一个）。
    #: ⚠️ 用 ``getattr`` 取 ``data_controller``：它是 ``build_help_menu`` 里
    #:    ``setattr`` 挂上去的"库类没声明过的属性"，直接属性访问会被 Pyright 报
    #:    ``reportAttributeAccessIssue``（同上一条 ``update_controller`` 的处理；
    #:    这个文件里"取库类没声明的属性"一律走 ``getattr``）。
    window.data_package_controller = (  # type: ignore[attr-defined]
        getattr(window.menus[MENU_HELP], "data_controller")
    )
    layout = title_bar.hBoxLayout
    title_label = getattr(title_bar, "titleLabel", None)
    index = (
        (layout.indexOf(title_label) + 1) if title_label is not None else layout.count()
    )
    layout.insertWidget(index, bar, 0, Qt.AlignmentFlag.AlignVCenter)
    window.menu_bar = bar
    return bar
