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

from PySide6.QtCore import QObject, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QGridLayout, QMenu, QMenuBar, QVBoxLayout, QWidget,
)
from qfluentwidgets import BodyLabel, CaptionLabel

from config import VERSION
from desktop.components.dialog_shell import shell_dialog
from desktop.modules import MODULES
from desktop.ui import theme as T
from desktop.ui.help_dialog import open_manual
from desktop.ui.icons import resolve_nav_icon
from desktop.ui.toast import show_toast
from desktop.ui.widgets import apply_to
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
    """
    payload = latest or {}
    if kind == RESULT_NEWER:
        tag = str(payload.get("tag_name") or "")
        name = str(payload.get("name") or "").strip()
        link = str(payload.get("html_url") or "") or PROJECT_URL
        body = f"当前版本：v{current}\n最新版本：{tag}"
        if name and name != tag:
            body += f"（{name}）"
        body += f"\n\n下载地址：{link}"
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
        f"{reason}\n\n稍后可以再试；也可以到项目主页看最新版本：\n{PROJECT_URL}",
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
            # ⚠️⚠️ 键**右对齐**、值左对齐，且**两者都 AlignTop**（2026-10-15 用户
            #    截图报「关于没对齐」）：
            #    - 键名长短不一（「版本」2 字 vs「程序名称」4 字），左对齐会让短键
            #      右侧空一大段、值列看着忽远忽近；右对齐后键的右缘齐平、值与键紧邻；
            #    - 值列**必须与键同款 AlignTop**：只给键 AlignTop、值走默认对齐时，
            #      值是"填满整格再垂直居中"，行一高两者就不在同一基线上——这正是
            #      旧版看着错位的原因。
            grid.addWidget(
                key_label, index, 0,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            )
            grid.addWidget(
                value_label, index, 1,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            )
        grid.setColumnStretch(1, 1)
        # ⚠️ 末尾兜一条弹性行：本面板在 ``shell_dialog`` 里是按 stretch=1 摆的，
        #    不兜住多余高度的话 QGridLayout 会把空白**摊到每一行上**（实测行距被
        #    撑到 ~75px，四行散成一大片）；内容该紧凑地贴顶。
        grid.setRowStretch(len(rows), 1)


# ------------------------------------------------------------------ 组装
def install_menu_bar(window) -> QMenuBar:
    """给主窗口装上菜单栏（``MainWindow.__init__`` 调一次）。

    返回 ``QMenuBar`` 本身（自测拿它读菜单结构）；一并留下两样引用：

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
    bar = window.menuBar()
    window.menus = {
        MENU_FILE: build_file_menu(bar, window),
        MENU_SINGLE_TASK: build_single_task_menu(bar, window),
        MENU_HELP: build_help_menu(bar, window),
    }
    window.update_controller = window.menus[MENU_HELP].controller  # type: ignore[attr-defined]
    return bar


def _add_menu(bar: QMenuBar, title: str) -> QMenu:
    """建一个**显式父对象**的顶级菜单并挂到菜单栏上（理由见 ``install_menu_bar``）。"""
    menu = QMenu(title, bar)
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
        for widget in app.topLevelWidgets():
            if isinstance(widget, QDialog) and widget is not window \
                    and widget.isVisible():
                widget.close()
    window.close()


def open_about(window) -> None:
    """「关于」：程序名 / 版本 / 数据目录 / 项目地址。"""
    panel = _AboutPanel(about_rows(window))
    # 四行紧凑贴顶（对齐修好后多余高度都兜在末尾弹性行上），弹窗不用留太高。
    shell_dialog("关于", panel, window, size=(600, 300),
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

    # ---- 触发 ----
    def check(self) -> None:
        """查一次 GitHub Release 最新版（防重入；网络在子线程）。"""
        if self._checking:
            show_toast(
                self.window, "info", "正在检查更新",
                "上一次检查还没结束，请稍候。",
            )
            return
        self._checking = True
        self.action.setEnabled(False)
        self.action.setText(ACTION_UPDATE_BUSY)
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

    # ---- 结果 ----
    def _on_checked(self, payload) -> None:
        """拿到 release 原始字段：比版本决定"已是最新 / 有新版本"。"""
        self._finish()
        tag = str((payload or {}).get("tag_name") or "")
        kind = RESULT_NEWER if is_newer(tag, VERSION) else RESULT_LATEST
        self._present(update_result(kind, current=VERSION, latest=payload))

    def _on_failed(self, kind) -> None:
        """网络/解析失败：按分类给中文原因。"""
        self._finish()
        self._present(update_result(str(kind), current=VERSION))

    def _finish(self) -> None:
        """解除忙标记并恢复菜单项（**幂等**，见类 docstring）。"""
        if not self._checking:
            return
        self._checking = False
        self.action.setEnabled(True)
        self.action.setText(ACTION_UPDATE)

    def _present(self, verdict: UpdateVerdict) -> None:
        """把结论弹出来（主按钮：有新版本时是「前往下载」）。"""
        panel = _MessagePanel(verdict.body, verdict.link)
        on_ok = None
        if verdict.link and verdict.ok_text == BUTTON_DOWNLOAD:
            on_ok = lambda: QDesktopServices.openUrl(QUrl(verdict.link))  # noqa: E731
        shell_dialog(
            verdict.title, panel, self.window, size=(620, 330),
            ok_text=verdict.ok_text, show_cancel=False, on_ok=on_ok,
        ).exec()


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
    "open_about",
    "quit_app",
    "update_result",
]
