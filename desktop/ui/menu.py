# -*- coding: utf-8 -*-
"""窗口顶部菜单栏：**文件 / 单任务 / 帮助**（原生 ``QMenuBar``）。

为什么是原生菜单栏（而不是自绘 Fluent 菜单条）
--------------------------------------------
qfluentwidgets 1.11.2 **没有** MenuBar 组件（只有 ``RoundMenu`` 这类弹出菜单），
而本程序用的就是原生标题栏（见 ``desktop/shell.py`` 的模块头），所以顶部菜单走
Qt 原生 ``QMenuBar``：与既有窗口装饰同族、自带 ``Alt`` 助记符与键盘导航
（``文件(F)`` 这类写法就是助记符）。**不改窗口尺寸、不动壳层布局**——菜单栏
只吃高度、不吃宽度，因此 ``desktop/app.py::WINDOW_MIN_SIZE`` 的宽度下限与
``tests/selftests/panel_label_fit.py`` 的 200px 断言都不受影响。

菜单项**只做路由与转发**，业务一律复用既有入口：

- 文件 → 新建任务：``shell.open_create()``（含"每次进入复位"，别另建页）；
- 文件 → 退出：``window.close()`` —— **不是** ``QApplication.quit()``（见
  :func:`quit_app` 的说明）；
- 单任务 → ``<key>``：``shell.show_module(key)``，清单**从 ``MODULES`` 派生**
  （与左侧导航同源同序，本文件不维护第二份清单）；
- 帮助 → 帮助文档：``desktop/ui/help_dialog.py::open_manual()``。

新增的只有「检查更新」与「关于」两件事：前者在子线程查 GitHub Release
（``desktop/workers/update_worker.py``），版本比较是纯规则
（``utils/version.py``）；两者都用项目统一的弹窗外壳
（``desktop/components/dialog_shell.py::shell_dialog``——AGENTS 明确别用
qfluentwidgets 的 ``Dialog``，它只支持"字符串 + 两个按钮"）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, cast

from PySide6.QtCore import QObject, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction, QColor, QDesktopServices, QFontMetrics, QPalette,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QGridLayout, QHBoxLayout, QLabel, QMenu, QMenuBar,
    QVBoxLayout, QWidget,
)
from qfluentwidgets import BodyLabel, CaptionLabel, MSFluentTitleBar

from config import VERSION
from desktop.components.dialog_shell import shell_dialog
from desktop.modules import MODULES
from desktop.ui import theme as T
from desktop.ui.help_dialog import open_manual
from desktop.ui.icons import resolve_nav_icon
from desktop.ui.toast import show_toast
from desktop.ui.widgets import apply_to, ui_font
from desktop.workers import connect_queued
from utils.version import is_newer

#: 项目主页（「关于」显示 / 「检查更新」失败时的兜底指引）。
#: ⚠️ 与 ``desktop/workers/update_worker.py::RELEASE_API`` 指同一仓库，
#: 换仓库/组织时两处要一起改。
PROJECT_URL = "https://github.com/zunkun/gujitools"

#: 顶级菜单与各动作文案。**含 ``&`` 助记符**（显示成下划线，``Alt`` 可唤起）；
#: 集中在这里，自测按这些常量断言（改文案只动一处）。
MENU_FILE = "文件(&F)"
MENU_SINGLE_TASK = "单任务(&S)"
MENU_HELP = "帮助(&H)"
ACTION_CREATE_TASK = "新建任务(&N)"
ACTION_QUIT = "退出(&X)"
ACTION_MANUAL = "帮助文档(&D)"
ACTION_UPDATE = "检查更新(&U)"
ACTION_UPDATE_BUSY = "正在检查更新…"
ACTION_ABOUT = "关于(&A)"

#: 弹窗按钮文案（结果弹窗只有"知道了"或"前往下载"两种）
BUTTON_OK = "好的"
BUTTON_DOWNLOAD = "前往下载"

#: 「检查更新」成功分支的两种结论
RESULT_LATEST = "latest"   # 本机已是最新
RESULT_NEWER = "newer"     # 有更新版本

#: 失败分类 → 中文原因。⚠️ 词表与 ``update_worker.kind`` **一一对应**（别各写一份）。
FAILURE_REASONS = {
    "network": "连不上更新服务器（可能是断网，或网络策略拦了 api.github.com）。",
    "not_found": "没找到发布记录（仓库或发布可能已调整）。",
    "rate_limited": "请求过于频繁，被 GitHub 限流了。",
    "bad_json": "服务器返回的内容无法解析。",
}


# ------------------------------------------------------------------ 数据（纯函数）
@dataclass(frozen=True)
class UpdateVerdict:
    """一次检查更新该呈现什么（纯数据，自测直接断言它，不碰控件）。

    ``link`` 非空 ⇒ 主按钮是「前往下载」（点了开浏览器）；为空 ⇒ 只有「好的」。
    """

    title: str
    body: str
    ok_text: str = BUTTON_OK
    link: str = ""


def update_result(kind: str, *, current: str,
                  latest: dict | None = None) -> UpdateVerdict:
    """把一次检查结果收成 :class:`UpdateVerdict`。

    ``kind`` 取 ``RESULT_LATEST`` / ``RESULT_NEWER`` / 失败分类串
    （``network`` / ``not_found`` / ``rate_limited`` / ``bad_json`` / ``http:<code>``）。

    ⚠️ 正文**不用 markdown 粗体**（``**…**``）：内容面板是普通 QLabel，星号会
    原样显示出来（与 ``_ask_overwrite`` 同款教训）。

    线路（用户 2026-10-15：「github 容易被 ban，所以可以使用代理……检测更新，下载
    更新的时候，可以选择测试选择最优方案」）：worker 已经把**四条线路（直连 + 三个
    gh-proxy 镜像）都测过速**，``latest`` 里带着 ``mirror_label`` / ``download_url`` /
    ``ranking``——这里把它们写进正文：用户看得见这次走的是哪条、多快，下载地址也是
    **拼过该线路前缀**的那个（不然给了地址还是被 ban）。
    """
    payload = latest or {}
    if kind == RESULT_NEWER:
        tag = str(payload.get("tag_name") or "")
        name = str(payload.get("name") or "").strip()
        page = str(payload.get("html_url") or "") or PROJECT_URL
        label = str(payload.get("mirror_label") or "直连")
        link = str(payload.get("download_url") or "") or page
        seconds = payload.get("seconds")
        timing = f"（{float(seconds):.2f}s）" if isinstance(seconds, (int, float)) else ""
        body = f"当前版本：v{current}\n最新版本：{tag}"
        if name and name != tag:
            body += f"（{name}）"
        body += f"\n\n下载线路：{label}{timing}"
        body += f"\n下载地址：{link}"
        ranking = [item for item in (payload.get("ranking") or [])
                   if isinstance(item, dict) and item.get("ok")]
        if len(ranking) > 1:
            body += "\n\n可以点「换条线路」换一条镜像（检查时四条线路都测过速）。"
        if payload.get("prerelease"):
            body += "\n\n注意：这一版是预发布版本。"
        return UpdateVerdict(f"发现新版本 {tag}", body, BUTTON_DOWNLOAD, link)
    if kind == RESULT_LATEST:
        tag = str(payload.get("tag_name") or "")
        link = str(payload.get("html_url") or "") or PROJECT_URL
        body = f"当前版本 v{current} 已是最新。"
        if tag:
            body += f"\n\n最新发布：{tag}\n{link}"
        return UpdateVerdict("已是最新版本", body)
    reason = FAILURE_REASONS.get(kind)
    if reason is None:
        if kind.startswith("http:"):
            reason = f"更新服务器返回了错误（HTTP {kind.split(':', 1)[1]}）。"
        else:
            reason = "检查更新时出了点问题。"
    return UpdateVerdict(
        "检查更新失败",
        f"{reason}\n\n直连与三个镜像都试过一遍了；稍后可以再试，"
        f"也可以到项目主页看最新版本：\n{PROJECT_URL}",
    )


def about_rows(window=None) -> list[tuple[str, str]]:
    """「关于」弹窗的行（``(键, 值)``）。纯数据，自测直接断言。

    版本取 ``config.VERSION``（**唯一来源**）；程序名取窗口标题（不 import
    ``desktop.app``——那会与本模块形成循环导入）；数据目录取 ``window.store.root``
    （没有 store 时省略该行）。
    """
    name = str(window.windowTitle() or "") if window is not None else ""
    rows = [("程序名称", name or "古籍重製"), ("版本", f"v{VERSION}")]
    store = getattr(window, "store", None)
    root = getattr(store, "root", None)
    if root:
        rows.append(("数据目录", str(root)))
    rows.append(("项目地址", PROJECT_URL))
    return rows


# ------------------------------------------------------------------ 面板
class _MessagePanel(QWidget):
    """结果弹窗的内容：一段可换行的正文 + 可选的可选中链接。"""

    def __init__(self, body: str, link: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_SM)
        text = BodyLabel(body, self)
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        apply_to(text, T.SIZE_BODY, color=T.INK)
        # ⚠️ 换行标签必须开 ``heightForWidth``：**弹窗高度按内容算**（见
        #    ``UpdateController._present`` 的 ``adjustSize``）时，Qt 才会把"折行后要
        #    多高"算进 sizeHint；不开的话算出来只有一行的身高，弹窗照样要么顶到内容
        #    （裁字）要么按写死高度留一大片空白（用户 2026-10-15 截图报「高度太高」）。
        policy = text.sizePolicy()
        policy.setHeightForWidth(True)
        text.setSizePolicy(policy)
        layout.addWidget(text)
        if link:
            hint = CaptionLabel(link, self)
            hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            apply_to(hint, T.SIZE_CAPTION, color=T.INK_FAINT)
            layout.addWidget(hint)
        layout.addStretch()


class _AboutPanel(QWidget):
    """「关于」的内容：键值两列表格（值可选中，便于复制版本号/路径）。"""

    def __init__(self, rows: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(T.SPACE_LG)
        grid.setVerticalSpacing(T.SPACE_SM)
        for index, (key, value) in enumerate(rows):
            key_label = BodyLabel(key, self)
            apply_to(key_label, T.SIZE_BODY, color=T.INK_SOFT)
            value_label = BodyLabel(value, self)
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            apply_to(value_label, T.SIZE_BODY, color=T.INK)
            # ⚠️⚠️ 值**不加对齐参数**（用户 2026-10-15 报「关于内容显示不完整」）：
            #    ``QGridLayout.addWidget(w, r, c, alignment)`` 里的对齐参数会让控件
            #    **按自己的 sizeHint 摆放、不再填满单元格**——带自动换行的 QLabel 的
            #    sizeHint 宽度很小，于是长路径/长网址被压成"只看得见 C:"这种一截
            #    （实测截图就是它）。不给对齐即"填满该列"，列本身有 stretch ⇒ 拿到
            #    全部剩余宽度；文字的左右/垂直位置改由标签自己的 alignment 管。
            value_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            # 换行标签必须开 heightForWidth，否则行高只按"一行"算，折下来的第二行
            # 会被裁掉（同一次报障的另一半）。
            policy = value_label.sizePolicy()
            policy.setHeightForWidth(True)
            value_label.setSizePolicy(policy)
            # ⚠️ 键仍要对齐（右对齐 + 贴顶），理由见上一段说明：短键右缘与长键齐平。
            grid.addWidget(
                key_label, index, 0,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            )
            grid.addWidget(value_label, index, 1)
        grid.setColumnStretch(1, 1)
        # 键列不参与拉伸（宽度按最长的键名定），否则键与值之间会空出一大段。
        grid.setColumnStretch(0, 0)
        # ⚠️ 末尾兜一条弹性行：本面板在 ``shell_dialog`` 里是按 stretch=1 摆的，
        #    不兜住多余高度的话 QGridLayout 会把空白**摊到每一行上**（实测行距被
        #    撑到 ~75px，四行散成一大片）；内容该紧凑地贴顶。
        grid.setRowStretch(len(rows), 1)


#: 顶部标题栏（图标 / 标题 / 菜单那一整条）的底色。
#:
#: 用户 2026-10-15：「'文件' 等这些菜单有白色背景色，跟原本颜色不一致，因此顶部
#: 区域背景色建议改成一致的，区别于系统其他地方的灰色」——所以整条顶栏统一到这
#: 一个色（菜单栏自身改透明，见 ``install_menu_bar``），并取**白**：白色是"窗口装饰"
#: 那一档（左侧导航栏也是白），与正文区的灰底 ``T.CANVAS`` 一眼分得开；标题栏若跟
#: 正文同灰，看上去就像正文的一部分、没有"标题栏"的样子。
TITLE_BAR_BG = T.SURFACE

#: 顶栏与菜单栏共用的字号（用户 2026-10-15：标题「古籍重製」与菜单字大小不一致，
#: 要求"改成一样大小、文字对齐"）。
#: ⚠️ 光字号一样还不够——两边控件的**行高**也要一样，否则各自垂直居中后基线会错开
#: 一两像素（用户口径："即使不一致，也要底部对齐"）。所以再钉一个统一行高。
TITLE_BAR_FONT_SIZE = T.SIZE_BODY
TITLE_BAR_ROW_HEIGHT = 24


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
        layout.indexOf(bar.titleLabel), title_label, 0,
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
    """把菜单栏（文件 / 单任务 / 帮助）插进**标题栏的标题之后**。

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
        MENU_SINGLE_TASK: build_single_task_menu(bar, window),
        MENU_HELP: build_help_menu(bar, window),
    }
    window.update_controller = window.menus[MENU_HELP].controller  # type: ignore[attr-defined]
    layout = title_bar.hBoxLayout
    title_label = getattr(title_bar, "titleLabel", None)
    index = (layout.indexOf(title_label) + 1) if title_label is not None else layout.count()
    layout.insertWidget(index, bar, 0, Qt.AlignmentFlag.AlignVCenter)
    window.menu_bar = bar
    return bar


def _add_menu(bar: QMenuBar, title: str) -> QMenu:
    """建一个**显式父对象**的顶级菜单并挂到菜单栏上（理由见 ``install_menu_bar``）。"""
    menu = QMenu(title, bar)
    # 弹出菜单是**独立窗口**，字体不继承菜单条 ⇒ 显式跟随，免得下拉里的字与顶栏
    # 不一致（用户 2026-10-15 要求顶栏文字统一）。
    menu.setFont(bar.font())
    bar.addMenu(menu)
    return menu


def build_file_menu(bar: QMenuBar, window) -> QMenu:
    """「文件」：新建任务 / （分隔线）/ 退出。"""
    menu = _add_menu(bar, MENU_FILE)
    create = QAction(ACTION_CREATE_TASK, menu)
    # ⚠️ 吞掉 triggered 的 bool：``QAction.triggered`` 是 ``triggered(bool)``，
    #    直接连无参 lambda 也能用，但显式写出来才不会被下次改成带参槽时咬到。
    create.triggered.connect(lambda _checked=False: window.shell.open_create())
    menu.addAction(create)
    menu.addSeparator()
    quit_action = QAction(ACTION_QUIT, menu)
    # ⚠️ macOS 的原生菜单栏由系统接管「退出」，登记角色才不会跑错位置；
    #    Windows/Linux 无副作用（菜单栏就在窗口内）。
    quit_action.setMenuRole(QAction.MenuRole.QuitRole)
    quit_action.triggered.connect(lambda _checked=False: quit_app(window))
    menu.addAction(quit_action)
    return menu


def build_single_task_menu(bar: QMenuBar, window) -> QMenu:
    """「单任务」：**从 ``MODULES`` 派生**（顺序/文案/图标与左侧导航同源）。

    ⚠️ 这里**不**再写一份清单：左侧导航栏遍历的是同一个 ``MODULES``
    （``desktop/modules/__init__.py`` 由 ``NAV_STEPS`` 派生），所以"导航里有的
    菜单里都有"，改模块只改 ``steps/spec.py`` 一处。
    """
    menu = _add_menu(bar, MENU_SINGLE_TASK)
    for module in MODULES:
        action = QAction(resolve_nav_icon(module.icon).icon(), module.title, menu)
        action.setToolTip(module.subtitle)
        action.triggered.connect(_module_slot(window, module.key))
        menu.addAction(action)
    return menu


def build_help_menu(bar: QMenuBar, window) -> QMenu:
    """「帮助」：帮助文档 / 检查更新 / 关于。

    返回的菜单上挂着 ``controller``（更新控制器）——``install_menu_bar`` 从它取
    出来放到 ``window.update_controller``，这样"检查更新"只有**一个**实例
    （忙标记、菜单项文案都在它身上，两个实例会各转各的）。
    """
    menu = _add_menu(bar, MENU_HELP)
    manual = QAction(ACTION_MANUAL, menu)
    # ⚠️ 不给「帮助文档」设 MenuRole：PySide6 的 ``QAction.MenuRole`` **没有**
    #    ``HelpRole``（实测只有 NoRole/TextHeuristicRole/ApplicationSpecificRole/
    #    AboutQtRole/AboutRole/PreferencesRole/QuitRole），保持默认的启发式即可。
    manual.triggered.connect(lambda _checked=False: open_manual())
    menu.addAction(manual)

    update = QAction(ACTION_UPDATE, menu)
    update.triggered.connect(lambda _checked=False: controller.check())
    menu.addAction(update)

    menu.addSeparator()
    about = QAction(ACTION_ABOUT, menu)
    about.setMenuRole(QAction.MenuRole.AboutRole)
    about.triggered.connect(lambda _checked=False: open_about(window))
    menu.addAction(about)

    controller = UpdateController(window, update, menu)
    menu.controller = controller      # type: ignore[attr-defined]
    return menu


def _module_slot(window, key: str):
    """生成"点某个独立任务"的槽（吞掉 triggered 的 bool，理由见 ``build_file_menu``）。"""
    return lambda _checked=False: window.shell.show_module(key)


def quit_app(window) -> None:
    """「退出」：先收掉非模态子弹窗，再 ``window.close()``。

    ⚠️⚠️ **不能用 ``QApplication.quit()``**：它只退事件循环、**不触发**
    ``closeEvent``，而 QProcess 子进程与后台线程的收尾全挂在
    ``MainWindow.closeEvent``（→ ``shell.shutdown_workers()``）这条链上；
    绕过去就会出现 ``worker_host`` 里写的「QThread 运行中被析构 → Qt abort」。
    """
    app = QApplication.instance()
    if app is not None:
        # 强制告诉类型检查器，这是 QApplication 而不是 QCoreApplication
        app = cast(QApplication, app)
        for widget in app.topLevelWidgets():
            if isinstance(widget, QDialog) and widget is not window \
                    and widget.isVisible():
                widget.close()
    window.close()


def _about_size(window) -> tuple[int, int]:
    """「关于」弹窗的尺寸：**按内容算宽**，别让长路径/长网址被挤成半截。

    ⚠️ 用户 2026-10-15 报「关于内容显示不完整」的另一半：写死 600 宽时，值列只有
    ~460px，而 Windows 路径这种**没有空格的长串**在 QLabel 的
    ``setWordWrap(True)`` 下不会折行（Qt 只在词边界断行）⇒ 直接被裁成半截。
    所以按"最长的键 + 最长的值"的字体宽度把弹窗撑开（宽度钳在 560~900 之间：
    再窄放不下键值对，再宽在小屏上会顶出去——``shell_dialog`` 仍会按屏幕夹一次）。
    """
    rows = about_rows(window)
    metrics = QFontMetrics(ui_font(T.SIZE_BODY))
    key_w = max((metrics.horizontalAdvance(k) for k, _ in rows), default=0)
    value_w = max((metrics.horizontalAdvance(v) for _, v in rows), default=0)
    # 面板左右边距（shell_dialog 用 SPACE_XL）+ 键值间距（SPACE_LG）+ 一点余量
    width = key_w + value_w + 2 * T.SPACE_XL + T.SPACE_LG + 24
    return (max(560, min(900, int(width))), 180)


def open_about(window) -> None:
    """「关于」：程序名 / 版本 / 数据目录 / 项目地址。"""
    panel = _AboutPanel(about_rows(window))
    # 四行紧凑贴顶（对齐修好后多余高度都兜在末尾弹性行上），宽度按内容算
    # （见 _about_size：长路径不能被压成半截）。
    shell_dialog("关于", panel, window, size=_about_size(window),
                 ok_text=BUTTON_OK, show_cancel=False).exec()


# ------------------------------------------------------------------ 检查更新
class UpdateController(QObject):
    """「检查更新」的编排者：一次一个请求，结果用弹窗汇报。

    三条硬约束：

    1. **重入防护**：连点菜单不叠出第二个请求（``_checking``），期间菜单项
       **置灰**并改名「正在检查更新…」，用户看得见"正在跑"；
    2. **网络在子线程**（``window.run_worker``，见 ``WorkerHost``）；
    3. **收尾幂等**：``_finish`` 由 worker 信号与线程结束两条路都会调到，
       重复调用只生效一次。
    """

    def __init__(self, window, action: QAction, parent=None):
        super().__init__(parent if parent is not None else window)
        self.window = window
        self.action = action
        self._checking = False
        #: 上一次成功检查的 payload（"换条线路"要在它的 ranking 上换线，不再重新联网）
        self._last_payload: dict | None = None
        #: 当前展示的是 ranking 里第几条可用线路（0 = 最快那条）
        self._scheme_index = 0
        #: 「正在检查」窗（先弹出来的那个；结果落地或用户取消时关掉）
        self._check_dialog: QDialog | None = None
        #: 用户点了「取消」：结果回来时静默丢弃，不再弹结果窗
        self._aborted = False

    # ---- 触发 ----
    def check(self) -> None:
        """查一次 GitHub Release 最新版：**先弹「正在检查」窗，再弹结果窗**。

        用户 2026-10-15：「检查更新，先出弹窗，再反馈结果」——点下去立刻要有可见反馈
        （后台要并发测四条线路，可能几秒），不能像以前那样只有菜单项变灰 + 静默等。
        """
        if self._checking:
            show_toast(
                self.window, "info", "正在检查更新",
                "上一次检查还没结束，请稍候。",
            )
            return
        self._checking = True
        self._aborted = False
        self.action.setEnabled(False)
        self.action.setText(ACTION_UPDATE_BUSY)
        self._present_checking()
        # ⚠️ 惰性 import：启动期不该为一个"用户可能不点"的菜单项拉进网络模块。
        from desktop.workers.update_worker import UpdateCheckWorker

        self.window.run_worker(
            UpdateCheckWorker,
            lambda worker, thread: (
                connect_queued(self.window, worker.checked, self._on_checked, thread),
                connect_queued(self.window, worker.failed, self._on_failed, thread),
                connect_queued(
                    self.window, thread.finished, lambda *_: self._finish(),
                ),
            ),
        )

    # ---- 「正在检查」窗（先出） ----
    def _present_checking(self) -> None:
        """弹「正在检查更新」窗（**非模态**：检查在子线程，主线程得能继续收信号）。

        ⚠️ 用 ``show()`` 而不是 ``exec()``：``exec()`` 会把主线程压进嵌套事件循环，
        这里没必要（结果本来就走信号回主线程），而且非模态才允许用户点「取消」改主意。
        ⚠️ 它的按钮是**「取消」**：点了就关窗并**丢掉这次结果**（见 ``_abort_check``），
        不然用户关掉了窗、几秒后又冒出一个结果窗，像是"点了没反应还自己弹东西"。
        """
        panel = _MessagePanel("正在查询检查最新版......")
        dialog = shell_dialog(
            "正在检查更...", panel, self.window, size=(620, 180),
            ok_text="取消", show_cancel=False, on_ok=self._abort_check,
        )
        self._check_dialog = dialog
        dialog.show()

    def _close_check_dialog(self) -> None:
        """关掉「正在检查」窗（结果落地 / 用户取消时都要关，别留着）。"""
        dialog = getattr(self, "_check_dialog", None)
        self._check_dialog = None
        if dialog is not None:
            dialog.close()

    def _abort_check(self) -> None:
        """用户点了「正在检查」窗的「取消」：关窗 + **丢掉这次结果**。

        ⚠️ 只是"不看结果"，**不掐断**已经发出去的请求（子线程里是并发 HTTP，掐断
        要额外的取消协议，收益不值当）；结果回来时 ``_on_checked`` 看到 ``_aborted``
        就静默收尾。
        """
        self._aborted = True
        self._close_check_dialog()
        self._finish()

    # ---- 结果 ----
    def _on_checked(self, payload) -> None:
        """拿到 release 原始字段：先关「正在检查」窗，再比版本弹结果。

        ⚠️ 同时记下 payload（含**四条线路的测速排名**）并复位线路下标——「换条线路」
        就在这份排名上换，不再重新联网。
        """
        self._finish()
        self._close_check_dialog()
        if self._aborted:
            self._last_payload = None
            return
        self._last_payload = dict(payload or {})
        self._scheme_index = 0
        tag = str(self._last_payload.get("tag_name") or "")
        kind = RESULT_NEWER if is_newer(tag, VERSION) else RESULT_LATEST
        if kind == RESULT_NEWER:
            self._present(self._verdict_for_scheme(self._scheme_index))
            return
        self._present(update_result(kind, current=VERSION,
                                    latest=self._last_payload))

    def _on_failed(self, kind) -> None:
        """网络/解析失败：先关「正在检查」窗，再按分类给中文原因。"""
        self._finish()
        self._close_check_dialog()
        if self._aborted:
            self._last_payload = None
            return
        self._last_payload = None
        self._present(update_result(str(kind), current=VERSION))

    def _finish(self) -> None:
        """解除忙标记并恢复菜单项（**幂等**，见类 docstring）。"""
        if not self._checking:
            return
        self._checking = False
        self.action.setEnabled(True)
        self.action.setText(ACTION_UPDATE)

    # ---- 线路切换（用户 2026-10-15：「下载更新的时候，可以选择测试选择最优方案」）----
    def _usable_schemes(self) -> list[dict]:
        """这次检查里**通了的**线路，按测速从快到慢（第一条就是自动选中的最优）。"""
        payload = self._last_payload or {}
        return [
            item for item in (payload.get("ranking") or [])
            if isinstance(item, dict) and item.get("ok")
        ]

    def _verdict_for_scheme(self, index: int) -> UpdateVerdict:
        """把 payload 换成"走第 ``index`` 条线路"，再生成结论文案。"""
        payload = dict(self._last_payload or {})
        schemes = self._usable_schemes()
        if schemes:
            entry = schemes[index % len(schemes)]
            payload.update({
                "mirror_prefix": entry.get("prefix", ""),
                "mirror_label": entry.get("label", "直连"),
                "download_url": entry.get("download_url", ""),
                "seconds": entry.get("seconds"),
            })
        return update_result(RESULT_NEWER, current=VERSION, latest=payload)

    def _next_scheme(self) -> None:
        """「换条线路」：在测速排名里换下一条可用线路，换完**再弹一次**结论。

        ⚠️ 换线路**不重新联网**（排名是刚才那次检查测出来的），所以它是瞬时的；
        想看新的测速结果就再点一次菜单的「检查更新」（那会重测四条）。
        """
        schemes = self._usable_schemes()
        if len(schemes) < 2:
            return
        self._scheme_index = (self._scheme_index + 1) % len(schemes)
        self._present(self._verdict_for_scheme(self._scheme_index))

    def _present(self, verdict: UpdateVerdict) -> None:
        """把结论弹出来（有新版本时：主按钮「前往下载」，次按钮**「换条线路」**）。

        ⚠️ 「换条线路」走 ``on_cancel``，而 ``shell_dialog`` 的 cancel 按钮点下去
        只会调我们的回调、**不会**自己关窗——所以回调用 ``QTimer.singleShot(0, …)``
        把"关掉当前窗 + 再弹一次"排到本次点击处理完**之后**执行；直接在回调里再
        ``exec()`` 会叠出两层模态（外面那层还留在屏幕上）。
        """
        panel = _MessagePanel(verdict.body, verdict.link)
        on_ok = None
        if verdict.link and verdict.ok_text == BUTTON_DOWNLOAD:
            on_ok = lambda: QDesktopServices.openUrl(QUrl(verdict.link))  # noqa: E731
        has_alternatives = (
            verdict.ok_text == BUTTON_DOWNLOAD and len(self._usable_schemes()) > 1
        )
        holder: dict = {}
        # ⚠️ 注释里写清类型：``on_cancel`` 先给 None、有条件才换成函数，直接
        #    ``on_cancel = None`` + 分支里 ``def on_cancel()`` 会被 Pyright 判成
        #    "None 不可赋给 () -> None"（``reportAssignmentType``）。
        on_cancel: Callable[[], None] | None = None
        if has_alternatives:
            def _switch_scheme() -> None:
                dialog = holder.get("dialog")
                if dialog is not None:
                    dialog.done(0)
                QTimer.singleShot(0, self._next_scheme)

            on_cancel = _switch_scheme

        dialog = shell_dialog(
            verdict.title, panel, self.window,
            # ⚠️ 高度**按内容自适应**：这里只给一个"下限"，真正的尺寸在下面
            #    ``adjustSize()`` 里由正文长短算出来。写死 360 时正文只有三四行、
            #    下面空掉一大片（用户 2026-10-15 截图报「弹窗高度太高，大片空白」）。
            size=(620, 120),
            ok_text=verdict.ok_text,
            cancel_text="换条线路",
            show_cancel=has_alternatives,
            on_ok=on_ok,
            on_cancel=on_cancel,
        )
        holder["dialog"] = dialog
        # ⚠️ 正文是可换行的 BodyLabel，只有拿到宽度后 sizeHint 才准 ⇒ 先布好再
        #    adjustSize（``shell_dialog`` 已经设了最小尺寸，所以不会被缩得更矮）。
        dialog.adjustSize()
        dialog.exec()


__all__ = [
    "ACTION_ABOUT",
    "ACTION_CREATE_TASK",
    "ACTION_MANUAL",
    "ACTION_QUIT",
    "ACTION_UPDATE",
    "FAILURE_REASONS",
    "MENU_FILE",
    "MENU_HELP",
    "MENU_SINGLE_TASK",
    "PROJECT_URL",
    "RESULT_LATEST",
    "RESULT_NEWER",
    "UpdateController",
    "UpdateVerdict",
    "about_rows",
    "build_file_menu",
    "build_help_menu",
    "build_single_task_menu",
    "install_menu_bar",
    "install_title_bar",
    "open_about",
    "quit_app",
    "update_result",
]
