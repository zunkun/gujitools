# -*- coding: utf-8 -*-
"""四个顶级菜单的组装（自 ``desktop/ui/menu.py`` 拆出）。"""

from __future__ import annotations

from desktop.modules import MODULES
from desktop.ui.help_dialog import open_manual
from desktop.ui.icons import resolve_nav_icon

from ._qt import QAction, QMenu, QMenuBar
from .actions import (
    _can_edit_action,
    _module_slot,
    _run_edit_action,
    open_quick_task,
    quit_app,
)
from .about import open_about
from .constants import (
    ACTION_ABOUT,
    ACTION_CREATE_TASK,
    ACTION_DATA_PACKAGE,
    ACTION_DATA_PACKAGE_TOOLTIP,
    ACTION_MANUAL,
    ACTION_QUICK_TASK,
    ACTION_QUIT,
    ACTION_UPDATE,
    EDIT_MENU_ITEMS,
    MENU_EDIT,
    MENU_FILE,
    MENU_HELP,
    MENU_MODULES,
)
from .data_package import DataPackageController
from .updates import UpdateController

def _add_menu(bar: QMenuBar, title: str) -> QMenu:
    """建一个**显式父对象**的顶级菜单并挂到菜单栏上（理由见 ``install_menu_bar``）。"""
    menu = QMenu(title, bar)
    # 弹出菜单是**独立窗口**，字体不继承菜单条 ⇒ 显式跟随，免得下拉里的字与顶栏
    # 不一致（用户 2026-10-15 要求顶栏文字统一）。
    menu.setFont(bar.font())
    bar.addMenu(menu)
    return menu


def build_file_menu(bar: QMenuBar, window) -> QMenu:
    """「文件」：新建任务 / 快速任务 / （分隔线）/ 退出。"""
    menu = _add_menu(bar, MENU_FILE)
    create = QAction(ACTION_CREATE_TASK, menu)
    # ⚠️ 吞掉 triggered 的 bool：``QAction.triggered`` 是 ``triggered(bool)``，
    #    直接连无参 lambda 也能用，但显式写出来才不会被下次改成带参槽时咬到。
    create.triggered.connect(lambda _checked=False: window.shell.open_create())
    menu.addAction(create)
    quick = QAction(ACTION_QUICK_TASK, menu)
    quick.triggered.connect(lambda _checked=False: open_quick_task(window))
    menu.addAction(quick)
    menu.addSeparator()
    quit_action = QAction(ACTION_QUIT, menu)
    # ⚠️ macOS 的原生菜单栏由系统接管「退出」，登记角色才不会跑错位置；
    #    Windows/Linux 无副作用（菜单栏就在窗口内）。
    quit_action.setMenuRole(QAction.MenuRole.QuitRole)
    quit_action.triggered.connect(lambda _checked=False: quit_app(window))
    menu.addAction(quit_action)
    return menu


def build_edit_menu(bar: QMenuBar, window) -> QMenu:
    """「编辑」：删除选中 / 插入图片 / 下载图片 / 打印图片（用户 2026-11-01）。

    菜单层**不做业务判断**：是否可点、做什么全交给当前页（鸭子类型调
    ``can_edit_<能力>`` / ``edit_<能力>``，命名见 :data:`EDIT_MENU_ITEMS`）。
    页面没实现某项能力 ⇒ 该项置灰（不认识当前页时四项全灰）。这样菜单不必
    import 具体页面，PDF排版、图片拼版、去底色、检测、提取各自按能力接。

    ⚠️ 启用状态在 ``aboutToShow`` 现问：选中项/当前步是用户随时变的，缓存会过期。
    """
    menu = _add_menu(bar, MENU_EDIT)
    actions: dict[str, QAction] = {}
    for capability, text, tooltip in EDIT_MENU_ITEMS:
        action = QAction(text, menu)
        action.setToolTip(tooltip)
        action.triggered.connect(
            lambda _checked=False, c=capability: _run_edit_action(window, c)
        )
        menu.addAction(action)
        actions[capability] = action

    def _sync_enabled() -> None:
        for capability, action in actions.items():
            action.setEnabled(_can_edit_action(window, capability))

    menu.aboutToShow.connect(_sync_enabled)
    return menu


def build_modules_menu(bar: QMenuBar, window) -> QMenu:
    """「独立功能」：**从 ``MODULES`` 派生**（顺序/文案/图标与入口页同源）。

    ⚠️ 这里**不**再写一份清单：左侧导航的「独立功能」入口页遍历的是同一个
    ``MODULES``（``desktop/modules/__init__.py`` 由 ``NAV_STEPS`` 派生），所以
    "入口页里有的菜单里都有"，改模块只改 ``steps/spec.py`` 一处。
    """
    menu = _add_menu(bar, MENU_MODULES)
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
