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

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, cast

from PySide6.QtCore import QObject, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFontMetrics,
    QPalette,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMenuBar,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel, CaptionLabel, MSFluentTitleBar

from config import VERSION
from desktop.components.dialog_shell import shell_dialog
from desktop.modules import MODULES
from desktop.store.json_io import read_json, write_json
from desktop.ui import theme as T
from desktop.ui.help_dialog import open_manual
from desktop.ui.icons import resolve_nav_icon
from desktop.ui.toast import show_toast
from desktop.ui.widgets import ProgressLine, apply_to, ui_font
from desktop.utils.files import pending_install_file, updates_dir
from desktop.workers import connect_queued
from utils.data_package import has_update, human_size, read_local_version
from utils.version import is_newer

#: 项目主页（「关于」显示 / 「检查更新」失败时的兜底指引）。
#: ⚠️ 与 ``desktop/workers/update_worker.py::RELEASE_API`` 指同一仓库，
#: 换仓库/组织时两处要一起改。
PROJECT_URL = "https://github.com/zunkun/gujitools"

#: 去底色数据包（YOLO 权重）所在的**另一个仓库**的 release 页（失败时的兜底指引）。
#: ⚠️ 与 ``utils/data_package.py::RELEASE_DOWNLOAD_BASE`` 指同一仓库/同一 tag。
DATA_PACKAGE_URL = "https://github.com/zunkun/gujitrain/releases/tag/database"

#: 顶级菜单与各动作文案。**含 ``&`` 助记符**（显示成下划线，``Alt`` 可唤起）；
#: 集中在这里，自测按这些常量断言（改文案只动一处）。
MENU_FILE = "文件(&F)"
MENU_SINGLE_TASK = "单任务(&S)"
MENU_HELP = "帮助(&H)"
ACTION_CREATE_TASK = "新建任务(&N)"
ACTION_QUIT = "退出(&X)"
ACTION_MANUAL = "帮助文档(&D)"
ACTION_UPDATE = "检查更新(&U)"
#: 「检查更新」菜单项在**发现有新版本**时追加的提示后缀（用户 2026-10-15：启动时
#: 后台自动查，有新版本就在菜单上提示）。版本号放 tooltip 里——菜单项宽度有限，
#: 塞一长串会把「帮助」菜单撑得很宽。
NEW_VERSION_SUFFIX = "　·　有新版本"
#: 「检查更新」的悬停提示（无新版本时的默认文案）
ACTION_UPDATE_TOOLTIP = "联网检查最新版本（直连 + 三个镜像，自动选最快的那条）"
#: 检查/下载期间菜单项的临时文案
ACTION_UPDATE_BUSY = "正在检查更新…"
ACTION_UPDATE_DOWNLOADING = "正在下载更新…"
#: 「检查数据包」菜单项（帮助菜单里，紧跟「检查更新」）。它检查的是**权重仓库**
#: （``zunkun/gujitrain``）``database`` release 里的 ``data.json``，与程序自身
#: 更新是两码事——所以单独一项、单独的控制器（用户 2026-10-16）。
ACTION_DATA_PACKAGE = "更新数据包(&M)"
#: 数据包菜单项的悬停提示（无新版时的默认文案）
ACTION_DATA_PACKAGE_TOOLTIP = (
    "联网检查去底色模型（bookcontent.pt）是否有新版本，可直接下载替换"
)
#: 检查/下载期间菜单项的临时文案
ACTION_DATA_PACKAGE_BUSY = "正在检查数据包…"
ACTION_DATA_PACKAGE_DOWNLOADING = "正在下载数据包…"
ACTION_ABOUT = "关于(&A)"

#: 弹窗按钮文案。⚠️ 主按钮「下载」= **应用内下载**（用户 2026-10-16：不要再跳浏览器
#: 让用户自己下）；「前往下载页」降级为**备用**次按钮（开浏览器，同样这条要求）。
BUTTON_OK = "好的"
BUTTON_DOWNLOAD = "下载"
BUTTON_BROWSER = "前往下载页"
#: 下载进度弹窗的按钮：取消下载
BUTTON_CANCEL = "取消"
#: 安装包下好后的收尾（用户：下好后提示重启，软件装更新）
BUTTON_INSTALL = "立即重启安装"
BUTTON_LATER = "稍后"
#: 下载失败后的重试（会自动换下一条可用线路）
BUTTON_RETRY = "换条线路重试"

#: 「检查更新」成功分支的两种结论
RESULT_LATEST = "latest"  # 本机已是最新
RESULT_NEWER = "newer"  # 有更新版本

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

    - ``ok_text`` 决定**主按钮**的语义：:data:`BUTTON_DOWNLOAD` = 应用内下载、
      :data:`BUTTON_INSTALL` = 立即重启安装、:data:`BUTTON_RETRY` = 换线路重试；
      其余（``BUTTON_OK``）只关窗。
    - ``link`` 非空 ⇒ 正文里附一行**可复制的下载地址**；
    - ``browser_url`` 非空 ⇒ 次按钮「前往下载页」开浏览器（**备用**，用户自己下）。
    """

    title: str
    body: str
    ok_text: str = BUTTON_OK
    link: str = ""
    browser_url: str = ""


def update_result(
    kind: str, *, current: str, latest: dict | None = None
) -> UpdateVerdict:
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
        timing = (
            f"（{float(seconds):.2f}s）" if isinstance(seconds, (int, float)) else ""
        )
        body = f"当前版本：v{current}\n最新版本：{tag}"
        if name and name != tag:
            body += f"（{name}）"
        body += f"\n\n下载线路：{label}{timing}"
        body += f"\n下载地址：{link}"
        if payload.get("prerelease"):
            body += "\n\n注意：这一版是预发布版本。"
        body += (
            f"\n\n点「{BUTTON_DOWNLOAD}」将在程序内自动下载安装包，"
            "下完提示重启安装；"
            f"点「{BUTTON_BROWSER}」打开下载页自行下载（备用）。"
        )
        return UpdateVerdict(f"发现新版本 {tag}", body, BUTTON_DOWNLOAD, link, page)
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


def data_package_result(
    kind: str, *, current: int, latest: dict | None = None
) -> UpdateVerdict:
    """把一次「去底色数据包检查」结果收成 :class:`UpdateVerdict`（纯数据）。

    ``kind`` 取 ``RESULT_LATEST`` / ``RESULT_NEWER`` / 失败分类串。与
    :func:`update_result` 的关键区别：**没有外链备用按钮**——有新版时主按钮是
    :data:`BUTTON_DOWNLOAD`（「下载」），点了由控制器**在程序内**下载并替换，
    而不是开浏览器（用户 2026-10-16：「不要让用户自己去下载」）。

    ``current`` 是**本机已安装版本**（整数）；``latest`` 是检查结果
    （``data_package_worker.fetch_data_json`` 的返回，含 ``info`` 与线路信息）。
    """
    payload = latest or {}
    info = payload.get("info") or {}
    remote = int(info.get("version") or 0)
    if kind == RESULT_NEWER:
        name = str(info.get("name") or "")
        size = human_size(info.get("size"))
        label = str(payload.get("mirror_label") or "直连")
        seconds = payload.get("seconds")
        timing = (
            f"（{float(seconds):.2f}s）" if isinstance(seconds, (int, float)) else ""
        )
        body = f"当前数据包版本：v{current}\n最新数据包版本：v{remote}"
        if name:
            body += f"（{name}）"
        if size:
            body += f"\n文件大小：{size}"
        body += (
            f"\n\n点「{BUTTON_DOWNLOAD}」将经最快线路（{label}{timing}）"
            "自动下载并替换本机模型。\n下载完成后，下次检测会自动用上新模型。"
        )
        return UpdateVerdict("发现新版本数据包", body, BUTTON_DOWNLOAD)
    if kind == RESULT_LATEST:
        body = f"当前数据包版本 v{current} 已是最新。"
        if info.get("name"):
            body += f"\n\n本机模型：{info['name']}"
        return UpdateVerdict("数据包已是最新", body)
    reason = FAILURE_REASONS.get(kind)
    if reason is None:
        if kind.startswith("http:"):
            reason = f"更新服务器返回了错误（HTTP {kind.split(':', 1)[1]}）。"
        else:
            reason = "检查数据包时出了点问题。"
    return UpdateVerdict(
        "检查数据包失败",
        f"{reason}\n\n直连与三个镜像都试过一遍了；稍后可以再试，"
        f"也可以到发布页看看：\n{DATA_PACKAGE_URL}",
    )


def _ready_verdict(tag: str) -> UpdateVerdict:
    """「安装包已就绪」结论（用户 2026-10-16）：主按钮「立即重启安装」，次按钮「稍后」。

    点「立即重启安装」由控制器启动安装器并退出本程序（``_install_and_restart``）；
    「稍后」则把安装包留在用户目录，下次点「检查更新」时可直接安装（免重下）。
    """
    body = (
        f"安装包已下载完成（{tag or '新版本'}）。\n\n"
        f"点「{BUTTON_INSTALL}」将关闭本程序并启动安装程序完成更新；\n"
        f"点「{BUTTON_LATER}」稍后再说——安装包会留着，"
        "下次点「检查更新」可直接安装，无需重新下载。"
    )
    return UpdateVerdict("更新已就绪", body, BUTTON_INSTALL)


def _download_failed_verdict(kind: str, browser_url: str) -> UpdateVerdict:
    """下载失败的结论：主按钮「换条线路重试」，次按钮「前往下载页」（**备用**）。"""
    reason = FAILURE_REASONS.get(kind)
    if reason is None:
        if "sha256" in kind or "ValueError" in kind:
            reason = "下载的安装包校验不通过（可能被网络中间层改写）。"
        else:
            reason = f"下载失败（{kind}）。"
    body = (
        f"{reason}\n\n可以点「{BUTTON_RETRY}」换一条线路重试；"
        f"也可以点「{BUTTON_BROWSER}」自行下载。"
    )
    return UpdateVerdict("更新下载失败", body, BUTTON_RETRY, "", browser_url)


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
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            apply_to(value_label, T.SIZE_BODY, color=T.INK)
            # ⚠️⚠️ 值**不加对齐参数**（用户 2026-10-15 报「关于内容显示不完整」）：
            #    ``QGridLayout.addWidget(w, r, c, alignment)`` 里的对齐参数会让控件
            #    **按自己的 sizeHint 摆放、不再填满单元格**——带自动换行的 QLabel 的
            #    sizeHint 宽度很小，于是长路径/长网址被压成"只看得见 C:"这种一截
            #    （实测截图就是它）。不给对齐即"填满该列"，列本身有 stretch ⇒ 拿到
            #    全部剩余宽度；文字的左右/垂直位置改由标签自己的 alignment 管。
            value_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            # 换行标签必须开 heightForWidth，否则行高只按"一行"算，折下来的第二行
            # 会被裁掉（同一次报障的另一半）。
            policy = value_label.sizePolicy()
            policy.setHeightForWidth(True)
            value_label.setSizePolicy(policy)
            # ⚠️ 键仍要对齐（右对齐 + 贴顶），理由见上一段说明：短键右缘与长键齐平。
            grid.addWidget(
                key_label,
                index,
                0,
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


class _ProgressPanel(QWidget):
    """下载进度弹窗的内容：一行状态文案 + 一根细进度条（``ProgressLine``）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_SM)
        self.label = BodyLabel("准备下载…", self)
        self.label.setWordWrap(True)
        apply_to(self.label, T.SIZE_BODY, color=T.INK)
        # 同 ``_MessagePanel``：换行标签必须开 heightForWidth，弹窗高度才按内容算。
        policy = self.label.sizePolicy()
        policy.setHeightForWidth(True)
        self.label.setSizePolicy(policy)
        self.bar = ProgressLine(self)
        layout.addWidget(self.label)
        layout.addWidget(self.bar)
        layout.addStretch()

    def set_progress(self, percent) -> None:
        """更新进度：``percent < 0`` = 总量未知（进度条切「来回滑动」未知态）。"""
        if percent is None or int(percent) < 0:
            self.bar.setRange(0, 0)
            self.label.setText("正在下载…")
            return
        value = max(0, min(100, int(percent)))
        self.bar.setRange(0, 100)
        self.bar.setValue(value)
        self.label.setText(f"正在下载… {value}%")

    def set_stage(self, text: str) -> None:
        """下载完成后的阶段提示（校验/释放占用/替换/重新加载）：只改文案。

        ⚠️ 这些阶段**总量不可知**（关服务、载模型各要几秒），进度条切成「来回
        滑动」的未知态——比画一根不动的空条更像"在干活"。
        """
        self.bar.setRange(0, 0)
        self.label.setText(text)


class _DownloadProgress:
    """下载进度窗的薄封装（**两个控制器共用**：程序更新 / 数据包）。

    一次下载一个实例：构造即弹窗（非模态，主线程接着收信号），期间用
    :meth:`progress` / :meth:`stage` 刷新，收尾 :meth:`close`。
    ⚠️ 按钮走 ``ok_text=BUTTON_CANCEL``：``shell_dialog`` 的 cancel 按钮在
    ``show_cancel=False`` 时被隐藏，所以"取消"只能占主按钮位。
    """

    def __init__(self, window, title: str, on_cancel) -> None:
        self.panel = _ProgressPanel()
        self.panel.set_progress(-1)      # 起步：总量未知（还没读到 Content-Length）
        self.dialog = shell_dialog(
            title, self.panel, window, size=(560, 160),
            ok_text=BUTTON_CANCEL, show_cancel=False, on_ok=on_cancel,
        )
        self.dialog.show()

    def progress(self, percent) -> None:
        self.panel.set_progress(percent)

    def stage(self, text: str) -> None:
        self.panel.set_stage(text)

    def close(self) -> None:
        self.dialog.close()


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
    #: 「去底色数据包」控制器（自测与"启动时后台静默检查"共用同一个）。
    window.data_package_controller = (  # type: ignore[attr-defined]
        window.menus[MENU_HELP].data_controller
    )
    layout = title_bar.hBoxLayout
    title_label = getattr(title_bar, "titleLabel", None)
    index = (
        (layout.indexOf(title_label) + 1) if title_label is not None else layout.count()
    )
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

    # 「去底色数据包」：查的是**权重仓库**的 database release（见 DataPackageController），
    # 与上面的「检查更新」（程序自身）各管一摊。
    data_action = QAction(ACTION_DATA_PACKAGE, menu)
    data_action.setToolTip(ACTION_DATA_PACKAGE_TOOLTIP)
    data_action.triggered.connect(lambda _checked=False: data_controller.check())
    menu.addAction(data_action)

    menu.addSeparator()
    about = QAction(ACTION_ABOUT, menu)
    about.setMenuRole(QAction.MenuRole.AboutRole)
    about.triggered.connect(lambda _checked=False: open_about(window))
    menu.addAction(about)

    controller = UpdateController(window, update, menu)
    menu.controller = controller  # type: ignore[attr-defined]
    data_controller = DataPackageController(window, data_action, menu)
    menu.data_controller = data_controller  # type: ignore[attr-defined]
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
            if (
                isinstance(widget, QDialog)
                and widget is not window
                and widget.isVisible()
            ):
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
    shell_dialog(
        "关于",
        panel,
        window,
        size=_about_size(window),
        ok_text=BUTTON_OK,
        show_cancel=False,
    ).exec()


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
        #: 检查在途标记（菜单项置灰 + 文案）
        self._checking = False
        #: 下载在途标记（与检查分开：下载期间菜单项也置灰）
        self._downloading = False
        #: 上一次成功检查的 payload（含**四条线路测速排名**；下载走 ranking 里那条线路）
        self._last_payload: dict | None = None
        #: 下载走 ranking 里第几条可用线路（0 = 最快那条；下载失败自动换下一条）
        self._scheme_index = 0
        #: 「正在检查」窗（先弹出来的那个；结果落地或用户取消时关掉）
        self._check_dialog: QDialog | None = None
        #: 下载进度窗（_DownloadProgress；没有下载在跑时为 None）
        self._progress: _DownloadProgress | None = None
        #: 当前下载 worker（「取消」要调它的 ``cancel``）
        self._download: dict = {}
        #: 最近一次"下好但还没装"的安装包记录（tag/path/sha256），供"稍后"后免重下
        self._pending: dict | None = None
        #: 用户点了「取消」：结果回来时静默丢弃，不再弹结果窗
        self._aborted = False
        #: 当前这次检查是**静默**的（启动时后台自动查）：不弹任何窗，只在菜单项上
        #: 挂"有新版本"提示；用户中途点了菜单就转成显式（见 :meth:`check`）。
        self._silent = False
        #: 已知的新版本 tag（空 = 未知/已是最新）——菜单项文案与 tooltip 看它
        self._newer_tag = ""

    # ---- 触发 ----
    def check(self) -> None:
        """查一次 GitHub Release 最新版：**先弹「正在检查」窗，再弹结果窗**。

        用户 2026-10-15：「检查更新，先出弹窗，再反馈结果」——点下去立刻要有可见反馈
        （后台要并发测四条线路，可能几秒），不能像以前那样只有菜单项变灰 + 静默等。

        ⚠️ 若此刻正有一次**静默**检查在飞（启动时自动跑的那次），这里**升级**成显式
        检查（挂上检查窗、结果照常弹），而不是回一句"正在检查"——用户在启动几秒内
        就点菜单是完全正常的事，让他白等一次很没道理；同一次请求两种模式共用。
        """
        if self._checking:
            if self._silent:
                self._silent = False
                self._present_checking()
                return
            show_toast(
                self.window,
                "info",
                "正在检查更新",
                "上一次检查还没结束，请稍候。",
            )
            return
        if self._downloading:
            show_toast(
                self.window, "info", "正在下载更新", "安装包还在下载，请稍候。",
            )
            return
        self._silent = False
        self._aborted = False
        self.action.setEnabled(False)
        self.action.setText(ACTION_UPDATE_BUSY)
        self._present_checking()
        self._start_worker()

    def check_silently(self) -> None:
        """**后台静默**检查一次（启动时自动跑，用户 2026-10-15）。

        与显式检查的三点不同：

        1. **不弹任何窗**（没有「正在检查」窗，也没有结果窗）——启动时不该打扰用户；
        2. **不动菜单项文案**（不置灰、不写"正在检查更新…"）——避免启动瞬间闪一下；
        3. 只有**发现有新版本**时，才在菜单项上挂提示（:data:`NEW_VERSION_SUFFIX`，
           版本号进 tooltip），失败则完全安静（网络不好时别在启动日志里刷错误）。
        """
        if self._checking or self._downloading:
            return  # 显式检查在跑、已有一次静默检查在飞，或在下载安装包
        self._silent = True
        self._aborted = False
        self._start_worker()

    def _start_worker(self) -> None:
        """起一次后台检查（显式/静默共用）：置忙标记 + 接线信号。"""
        self._checking = True
        # ⚠️ 惰性 import：启动期不该为一个"用户可能不点"的菜单项拉进网络模块。
        from desktop.workers.update_worker import UpdateCheckWorker

        self.window.run_worker(
            UpdateCheckWorker,
            lambda worker, thread: (
                connect_queued(self.window, worker.checked, self._on_checked, thread),
                connect_queued(self.window, worker.failed, self._on_failed, thread),
                connect_queued(
                    self.window,
                    thread.finished,
                    lambda *_: self._finish(),
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
            "正在检查更...",
            panel,
            self.window,
            size=(620, 180),
            ok_text="取消",
            show_cancel=False,
            on_ok=self._abort_check,
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
        """拿到 release 原始字段：比版本决定"已是最新 / 有新版本"。

        ⚠️ 同时记下 payload（含**四条线路的测速排名**）并复位线路下标——「换条线路」
        就在这份排名上换，不再重新联网。
        ⚠️ **静默模式**（启动时那次自动检查）只把"有新版本"挂到菜单项上、**不弹任何
        窗**；显式模式才关「正在检查」窗并弹结果（见 :meth:`check` / `check_silently`）。
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
        if self._silent:
            # 菜单提示：有新版本才挂后缀；已是最新就把提示清掉（比如用户在别的
            # 机器上升级后重开程序，提示不该留成"鬼影"）。
            self._newer_tag = tag if kind == RESULT_NEWER else ""
            self._apply_action_text()
            return
        if kind == RESULT_NEWER:
            # 上次点了「稍后」、安装包还躺在用户目录里 ⇒ 直接给「立即重启安装」，
            # 不必重下几百 MB（见 _pending_for / _ready_verdict）。
            pending = self._pending_for(tag)
            if pending is not None:
                self._pending = pending
                self._present(_ready_verdict(tag))
                return
            self._present(self._verdict_for_scheme(self._scheme_index))
            return
        self._present(update_result(kind, current=VERSION, latest=self._last_payload))

    def _on_failed(self, kind) -> None:
        """网络/解析失败：**静默模式**什么都不做；显式模式关窗后给中文原因。"""
        self._finish()
        self._close_check_dialog()
        if self._aborted:
            self._last_payload = None
            return
        self._last_payload = None
        if self._silent:
            # 启动时那次自动检查失败（断网/限流都常见）：安静收场，别弹框打扰。
            # ⚠️ 也**不**清掉已有的"有新版本"提示：这次没查到 ≠ 已经是最新。
            return
        self._present(update_result(str(kind), current=VERSION))

    # ---- 菜单项文案（有新版本时的提示）----
    def _action_text(self) -> str:
        """菜单项当前该显示的文案：下载中显示进行时；已知有新版本时带后缀。"""
        if self._downloading:
            return ACTION_UPDATE_DOWNLOADING
        if self._newer_tag:
            return f"{ACTION_UPDATE}{NEW_VERSION_SUFFIX}"
        return ACTION_UPDATE

    def _apply_action_text(self) -> None:
        """把文案/悬停提示刷成当前状态（版本号放 tooltip，菜单项别撑太宽）。"""
        self.action.setText(self._action_text())
        self.action.setToolTip(
            f"已发现新版本 {self._newer_tag}，点这里看详情并下载"
            if self._newer_tag
            else ACTION_UPDATE_TOOLTIP
        )

    def _finish(self) -> None:
        """解除忙标记并恢复菜单项（**幂等**，见类 docstring）。

        ⚠️ 恢复的是 ``_action_text()`` 而不是写死的 ``ACTION_UPDATE``：静默检查
        发现过新版本时，菜单项该带着"有新版本"的提示留下来。
        """
        if not self._checking:
            return
        self._checking = False
        self.action.setEnabled(True)
        self._apply_action_text()

    # ---- 线路切换（用户 2026-10-15：「下载更新的时候，可以选择测试选择最优方案」）----
    def _usable_schemes(self) -> list[dict]:
        """这次检查里**通了的**线路，按测速从快到慢（第一条就是自动选中的最优）。"""
        payload = self._last_payload or {}
        return [
            item
            for item in (payload.get("ranking") or [])
            if isinstance(item, dict) and item.get("ok")
        ]

    def _verdict_for_scheme(self, index: int) -> UpdateVerdict:
        """把 payload 换成"走第 ``index`` 条线路"，再生成结论文案。"""
        payload = dict(self._last_payload or {})
        schemes = self._usable_schemes()
        if schemes:
            entry = schemes[index % len(schemes)]
            payload.update(
                {
                    "mirror_prefix": entry.get("prefix", ""),
                    "mirror_label": entry.get("label", "直连"),
                    "download_url": entry.get("download_url", ""),
                    "seconds": entry.get("seconds"),
                }
            )
        return update_result(RESULT_NEWER, current=VERSION, latest=payload)

    def _present(self, verdict: UpdateVerdict) -> None:
        """把结论弹出来；主按钮语义由 ``verdict.ok_text`` 决定（见 :class:`UpdateVerdict`）。

        - ``BUTTON_DOWNLOAD`` / ``BUTTON_RETRY`` → **应用内下载**（``_start_app_download``），
          次按钮「前往下载页」= 开浏览器（**备用**，用户自己下）；
        - ``BUTTON_INSTALL`` → 「立即重启安装」（``_install_and_restart``），次按钮「稍后」；
        - 其余 → 只有「好的」。

        ⚠️ ``shell_dialog`` 的按钮点下去**不会**自己关窗，所以回调里先 ``done(0)``，
        再 ``QTimer.singleShot(0, …)`` 把后续动作排到本次点击处理完**之后**执行；
        直接在回调里再 ``exec()`` 会叠出两层模态（外面那层还留在屏幕上）。
        """
        panel = _MessagePanel(verdict.body, verdict.link)
        holder: dict = {}
        # ⚠️ 先窄化到局部变量再进闭包：直接闭包捕获 ``after``（类型含 None）会被
        #    Pyright 判成"可能不可调用"（``reportOptionalCall``）。
        after: Callable[[], None] | None = None
        if verdict.ok_text in (BUTTON_DOWNLOAD, BUTTON_RETRY):
            after = self._start_app_download
        elif verdict.ok_text == BUTTON_INSTALL:
            after = self._install_and_restart
        on_ok = None
        if after is not None:
            action = after

            def _go() -> None:
                dialog = holder.get("dialog")
                if dialog is not None:
                    dialog.done(0)
                QTimer.singleShot(0, action)

            on_ok = _go

        on_cancel: Callable[[], None] | None = None
        cancel_text = BUTTON_BROWSER
        show_cancel = False
        if verdict.ok_text == BUTTON_INSTALL:
            cancel_text = BUTTON_LATER
            show_cancel = True
        elif verdict.browser_url:
            url = verdict.browser_url

            def _open_browser() -> None:
                dialog = holder.get("dialog")
                if dialog is not None:
                    dialog.done(0)
                QDesktopServices.openUrl(QUrl(url))

            on_cancel = _open_browser
            show_cancel = True

        dialog = shell_dialog(
            verdict.title,
            panel,
            self.window,
            # ⚠️ 高度**按内容自适应**：这里只给一个"下限"，真正的尺寸在下面
            #    ``adjustSize()`` 里由正文长短算出来。写死 360 时正文只有三四行、
            #    下面空掉一大片（用户 2026-10-15 截图报「弹窗高度太高，大片空白」）。
            size=(620, 120),
            ok_text=verdict.ok_text,
            cancel_text=cancel_text,
            show_cancel=show_cancel,
            on_ok=on_ok,
            on_cancel=on_cancel,
        )
        holder["dialog"] = dialog
        # ⚠️ 正文是可换行的 BodyLabel，只有拿到宽度后 sizeHint 才准 ⇒ 先布好再
        #    adjustSize（``shell_dialog`` 已经设了最小尺寸，所以不会被缩得更矮）。
        dialog.adjustSize()
        dialog.exec()

    # ---- 应用内下载安装包 + 重启安装（用户 2026-10-16）----
    def _pending_for(self, tag: str) -> dict | None:
        """上次「稍后」留下的安装包记录：tag 一致、文件还在，才算数（免重下）。"""
        if not tag:
            return None
        data = read_json(pending_install_file(), {}) or {}
        if not isinstance(data, dict) or str(data.get("tag") or "") != tag:
            return None
        path = Path(str(data.get("path") or ""))
        if not path.is_file():
            return None
        return data

    def _scheme_download_url(self) -> str:
        """当前该走的下载地址：优先 ranking 里第 ``_scheme_index`` 条可用线路。"""
        payload = self._last_payload or {}
        schemes = self._usable_schemes()
        if schemes:
            entry = schemes[self._scheme_index % len(schemes)]
            url = str(entry.get("download_url") or "")
            if url:
                return url
        return str(payload.get("download_url") or "")

    def _browser_url(self) -> str:
        """「前往下载页」的目标：release 网页（拿不到就用项目主页兜底）。"""
        payload = self._last_payload or {}
        return str(payload.get("html_url") or "") or PROJECT_URL

    def _start_app_download(self) -> None:
        """开始**应用内**下载安装包（走测速排名里当前那条线路）。"""
        payload = self._last_payload or {}
        asset = payload.get("asset") or {}
        url = self._scheme_download_url()
        if not url:
            return
        name = Path(str(asset.get("name") or "")).name or "guji_setup.exe"
        dest = updates_dir() / name
        self._downloading = True
        self.action.setEnabled(False)
        self.action.setText(ACTION_UPDATE_DOWNLOADING)
        self._progress = _DownloadProgress(
            self.window, "正在下载安装包", self._cancel_app_download)

        from desktop.workers.update_worker import AppDownloadWorker

        holder: dict = {}

        def _factory():
            worker = AppDownloadWorker(
                url, dest,
                sha256=str(asset.get("sha256") or ""),
                size=int(asset.get("size") or 0),
            )
            holder["worker"] = worker
            return worker

        def _wire(worker, thread) -> None:
            connect_queued(self.window, worker.progress, self._on_progress, thread)
            connect_queued(self.window, worker.stage, self._on_app_stage, thread)
            connect_queued(
                self.window, worker.finished, self._on_app_downloaded, thread)
            connect_queued(self.window, worker.failed, self._on_app_failed, thread)
            connect_queued(
                self.window, thread.finished, lambda *_: self._finish_download())

        self._download = holder
        self.window.run_worker(_factory, _wire)

    def _on_progress(self, percent) -> None:
        if self._progress is not None:
            self._progress.progress(percent)

    def _on_app_stage(self, code) -> None:
        """下载之后的阶段提示（当前只有"校验安装包完整性"）。"""
        if self._progress is None:
            return
        from desktop.workers.update_worker import APP_UPDATE_STAGES

        self._progress.stage(APP_UPDATE_STAGES.get(str(code), "正在处理…"))

    def _on_app_downloaded(self, result) -> None:
        """安装包下好：记一笔"待安装"记录（供「稍后」免重下），再提示重启安装。"""
        self._finish_download()
        result = result or {}
        tag = str((self._last_payload or {}).get("tag_name") or "")
        record = {
            "tag": tag,
            "path": str(result.get("path") or ""),
            "name": str(result.get("name") or ""),
            "sha256": str(result.get("sha256") or ""),
            "size": int(result.get("size") or 0),
        }
        try:
            updates_dir().mkdir(parents=True, exist_ok=True)
            write_json(pending_install_file(), record)
        except OSError:
            pass      # 记不住只是"下次要重下"，不该挡住"提示重启安装"
        self._pending = record
        self._present(_ready_verdict(tag))

    def _on_app_failed(self, kind) -> None:
        """下载失败：关进度窗、复位菜单项；取消则静默，真失败就换线路给重试。"""
        self._finish_download()
        key = str(kind)
        if key == "cancelled":
            return
        schemes = self._usable_schemes()
        if len(schemes) > 1:
            self._scheme_index = (self._scheme_index + 1) % len(schemes)
        self._present(_download_failed_verdict(key, self._browser_url()))

    def _cancel_app_download(self) -> None:
        """进度窗的「取消」：请 worker 收手（结果回来时按 ``cancelled`` 静默）。"""
        worker = self._download.get("worker")
        if worker is not None:
            worker.cancel()

    def _close_progress(self) -> None:
        progress = self._progress
        self._progress = None
        if progress is not None:
            progress.close()

    def _finish_download(self) -> None:
        """下载收尾（成功/失败/线程结束三条路都会到，**幂等**）。"""
        self._close_progress()
        self._download = {}
        if self._downloading:
            self._downloading = False
            self.action.setEnabled(True)
            self._apply_action_text()

    def _install_and_restart(self) -> None:
        """启动安装器（分离进程）后退出本程序，让安装器接管文件替换。

        ⚠️ 安装器是 **Inno Setup**（见 ``guji_setup.iss``）：不传静默参数——向导里
        由用户自己点「下一步」，比程序替他决定稳；Inno 默认 ``CloseApplications``
        会用 Restart Manager 处理仍占着 ``{app}`` 文件的进程（本程序正在退出，
        交给它兜底）。
        ⚠️ 用**分离**进程（DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP）：本进程
        退出、或用户在终端 Ctrl+C，都不会把安装器一起带走（同 yolo_service 的拉起）。
        """
        path = Path(str((self._pending or {}).get("path") or ""))
        if not path.is_file():
            show_toast(self.window, "error", "安装包不见了",
                       "请重新点「检查更新」下载。")
            return
        try:
            kwargs = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "close_fds": True,
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = 0x00000008 | 0x00000200
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen([str(path)], **kwargs)
        except OSError as exc:
            show_toast(self.window, "error", "安装程序启动失败", str(exc))
            return
        quit_app(self.window)


# ------------------------------------------------------------------ 去底色数据包
class DataPackageController(QObject):
    """「去底色数据包」检查 + 下载的编排者（与 :class:`UpdateController` 各管一摊）。

    流程（用户 2026-10-16）：读权重仓库 ``database`` release 的 ``data.json`` →
    与本机**已装版本**比大小（``utils.data_package``）→ 有新版弹「下载」提示 →
    经最快线路**在程序内下载并替换** ``static/weights/bookcontent.pt``——而不是
    让用户自己去 GitHub 下。检查与下载都在子线程（``window.run_worker``），
    重入防护（``_checking`` / ``_downloading``）与收尾幂等沿用 UpdateController。
    """

    def __init__(self, window, action: QAction, parent=None):
        super().__init__(parent if parent is not None else window)
        self.window = window
        self.action = action
        #: 检查在途标记（菜单项置灰 + 文案）
        self._checking = False
        #: 下载在途标记（与检查分开：下载期间菜单项也置灰）
        self._downloading = False
        #: 静默模式（启动时后台自动查）：不弹窗，只把"有新版本"挂到菜单项上
        self._silent = False
        #: 用户点了检查窗的「取消」：结果回来时静默丢弃
        self._aborted = False
        #: 上一次成功的检查结果（含 info 与 download_url；「下载」用它）
        self._last: dict | None = None
        #: 已知的新版数据包版本号（0 = 未知/已是最新）——菜单项文案与 tooltip 看它
        self._newer_version = 0
        self._check_dialog: QDialog | None = None
        #: 下载进度窗（_DownloadProgress；没有下载在跑时为 None）
        self._progress: _DownloadProgress | None = None
        #: 当前下载 worker（``_cancel_download`` 要调它的 ``cancel``）
        self._download: dict = {}

    # ---- 触发 ----
    def check(self) -> None:
        """查一次数据包最新版：**先弹「正在检查」窗，再弹结果窗**。"""
        if self._checking:
            if self._silent:
                self._silent = False
                self._present_checking()
                return
            show_toast(
                self.window, "info", "正在检查数据包", "上一次检查还没结束，请稍候。"
            )
            return
        if self._downloading:
            show_toast(self.window, "info", "正在下载数据包", "下载进行中，请稍候。")
            return
        self._silent = False
        self._aborted = False
        self.action.setEnabled(False)
        self.action.setText(ACTION_DATA_PACKAGE_BUSY)
        self._present_checking()
        self._start_check()

    def check_silently(self) -> None:
        """**后台静默**检查一次（启动时自动跑）：不弹窗，有新版才挂菜单提示。"""
        if self._checking or self._downloading:
            return
        self._silent = True
        self._aborted = False
        self._start_check()

    def _start_check(self) -> None:
        """起一次后台检查（显式/静默共用）。"""
        self._checking = True
        # ⚠️ 惰性 import：启动期不该为一个"用户可能不点"的菜单项拉进网络模块。
        from desktop.workers.data_package_worker import DataCheckWorker

        self.window.run_worker(
            DataCheckWorker,
            lambda worker, thread: (
                connect_queued(self.window, worker.checked, self._on_checked, thread),
                connect_queued(self.window, worker.failed, self._on_failed, thread),
                connect_queued(
                    self.window,
                    thread.finished,
                    lambda *_: self._finish(),
                ),
            ),
        )

    # ---- 「正在检查」窗（先出） ----
    def _present_checking(self) -> None:
        """弹「正在检查数据包」窗（非模态；按钮是「取消」，点了丢掉这次结果）。"""
        panel = _MessagePanel("正在查询最新数据包......")
        dialog = shell_dialog(
            "正在检查数据包…",
            panel,
            self.window,
            size=(620, 180),
            ok_text=BUTTON_CANCEL,
            show_cancel=False,
            on_ok=self._abort_check,
        )
        self._check_dialog = dialog
        dialog.show()

    def _close_check_dialog(self) -> None:
        dialog = self._check_dialog
        self._check_dialog = None
        if dialog is not None:
            dialog.close()

    def _abort_check(self) -> None:
        """用户点了「取消」：关窗 + 丢掉这次结果（不掐断已发出的请求）。"""
        self._aborted = True
        self._close_check_dialog()
        self._finish()

    # ---- 检查结果 ----
    def _on_checked(self, payload) -> None:
        """拿到 data.json 结果：与本机已装版本比大小，决定"已是最新 / 有新版"。"""
        self._finish()
        self._close_check_dialog()
        if self._aborted:
            self._last = None
            return
        self._last = dict(payload or {})
        info = self._last.get("info") or {}
        remote = int(info.get("version") or 0)
        local = read_local_version()
        kind = RESULT_NEWER if has_update(remote, local) else RESULT_LATEST
        if self._silent:
            # 菜单提示：有新版才挂后缀；已是最新就清掉（别留成"鬼影"）。
            self._newer_version = remote if kind == RESULT_NEWER else 0
            self._apply_action_text()
            return
        self._present(data_package_result(kind, current=local, latest=self._last))

    def _on_failed(self, kind) -> None:
        """检查失败：静默模式什么都不做；显式模式关窗后给中文原因。"""
        self._finish()
        self._close_check_dialog()
        if self._aborted:
            return
        self._last = None
        if self._silent:
            # 启动时那次自动检查失败：安静收场，也不清掉已有的"有新版本"提示。
            return
        self._present(data_package_result(str(kind), current=read_local_version()))

    # ---- 菜单项文案 ----
    def _action_text(self) -> str:
        if self._downloading:
            return ACTION_DATA_PACKAGE_DOWNLOADING
        if self._newer_version:
            return f"{ACTION_DATA_PACKAGE}{NEW_VERSION_SUFFIX}"
        return ACTION_DATA_PACKAGE

    def _apply_action_text(self) -> None:
        self.action.setText(self._action_text())
        self.action.setToolTip(
            f"已发现新版本数据包 v{self._newer_version}，点这里下载替换"
            if self._newer_version
            else ACTION_DATA_PACKAGE_TOOLTIP
        )

    def _finish(self) -> None:
        """解除检查忙标记并恢复菜单项（**幂等**）。"""
        if not self._checking:
            return
        self._checking = False
        self.action.setEnabled(True)
        self._apply_action_text()

    # ---- 结果弹窗（有新版时主按钮「下载」） ----
    def _present(self, verdict: UpdateVerdict) -> None:
        panel = _MessagePanel(verdict.body, verdict.link)
        is_download = verdict.ok_text == BUTTON_DOWNLOAD
        holder: dict = {}
        on_ok = None
        if is_download:
            def _go() -> None:
                dialog = holder.get("dialog")
                if dialog is not None:
                    dialog.done(0)
                QTimer.singleShot(0, self._start_download)

            on_ok = _go
        dialog = shell_dialog(
            verdict.title, panel, self.window,
            size=(640, 120),
            ok_text=verdict.ok_text,
            cancel_text=BUTTON_CANCEL,
            show_cancel=is_download,
            on_ok=on_ok,
        )
        holder["dialog"] = dialog
        dialog.adjustSize()
        dialog.exec()

    # ---- 下载 ----
    def _start_download(self) -> None:
        """开下载：弹进度窗 + 起 :class:`DataDownloadWorker`（子线程）。"""
        payload = self._last or {}
        info = payload.get("info") or {}
        url = str(payload.get("download_url") or "")
        if not url:
            return
        self._downloading = True
        self.action.setEnabled(False)
        self.action.setText(ACTION_DATA_PACKAGE_DOWNLOADING)
        self._progress = _DownloadProgress(
            self.window, "正在下载并替换去底色数据包", self._cancel_download)

        from desktop.workers.data_package_worker import DataDownloadWorker

        holder: dict = {}

        def _factory():
            worker = DataDownloadWorker(url, info)
            holder["worker"] = worker
            return worker

        def _wire(worker, thread) -> None:
            connect_queued(self.window, worker.progress, self._on_progress, thread)
            connect_queued(self.window, worker.stage, self._on_stage, thread)
            connect_queued(self.window, worker.finished, self._on_downloaded, thread)
            connect_queued(self.window, worker.failed, self._on_download_failed, thread)
            connect_queued(
                self.window, thread.finished, lambda *_: self._finish_download()
            )

        self._download = holder
        self.window.run_worker(_factory, _wire)

    def _on_progress(self, percent) -> None:
        if self._progress is not None:
            self._progress.progress(percent)

    def _on_stage(self, code) -> None:
        """下载之后的阶段提示（校验 / 释放占用 / 替换 / 重新加载）。"""
        if self._progress is None:
            return
        # ⚠️ 惰性 import：只是取那份"阶段码 → 文案"的词表（唯一来源）。
        from desktop.workers.data_package_worker import DATA_PACKAGE_STAGES

        self._progress.stage(DATA_PACKAGE_STAGES.get(str(code), "正在处理…"))

    def _on_downloaded(self, result) -> None:
        """下载成功：关进度窗、复位菜单项、给出成功提示。"""
        # 刚装上新模型 ⇒ "有新版本"提示该清掉（否则菜单项会一直催）。
        self._newer_version = 0
        self._finish_download()
        result = result or {}
        body = (
            f"已下载并替换本机模型（版本 v{int(result.get('version') or 0)}），"
            "并已重新加载到内存。\n\n下次检测会直接用上新模型。"
        )
        if result.get("path"):
            body += f"\n\n保存位置：{result['path']}"
        self._present(UpdateVerdict("数据包下载完成", body))

    def _on_download_failed(self, kind) -> None:
        """下载失败（或被取消）：关进度窗、复位菜单项；取消则静默。"""
        self._finish_download()
        key = str(kind)
        if key == "cancelled":
            return
        reason = FAILURE_REASONS.get(key)
        if reason is None:
            if "PermissionError" in key:
                # Windows 上目标权重被别的句柄打开时替换会失败（见 replace_with_retry）
                reason = (
                    "无法替换模型文件（文件可能被占用）。请关闭正在检测的任务后再试。"
                )
            else:
                reason = f"下载失败（{key}）。"
        self._present(UpdateVerdict("数据包下载失败", f"{reason}\n\n稍后可以再试。"))

    def _cancel_download(self) -> None:
        """进度窗的「取消」：请 worker 收手（结果回来时按 ``cancelled`` 静默）。"""
        worker = self._download.get("worker")
        if worker is not None:
            worker.cancel()

    def _close_progress(self) -> None:
        progress = self._progress
        self._progress = None
        if progress is not None:
            progress.close()

    def _finish_download(self) -> None:
        """下载收尾（成功/失败/线程结束三条路都会到，**幂等**）。"""
        self._close_progress()
        self._download = {}
        if self._downloading:
            self._downloading = False
            self.action.setEnabled(True)
            self._apply_action_text()


__all__ = [
    "ACTION_ABOUT",
    "ACTION_CREATE_TASK",
    "ACTION_DATA_PACKAGE",
    "ACTION_MANUAL",
    "ACTION_QUIT",
    "ACTION_UPDATE",
    "BUTTON_BROWSER",
    "BUTTON_DOWNLOAD",
    "BUTTON_INSTALL",
    "DATA_PACKAGE_URL",
    "DataPackageController",
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
    "data_package_result",
    "install_menu_bar",
    "install_title_bar",
    "open_about",
    "quit_app",
    "update_result",
]
