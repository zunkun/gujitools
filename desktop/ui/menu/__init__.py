# -*- coding: utf-8 -*-
"""窗口顶部菜单栏：**文件 / 编辑 / 独立功能 / 帮助**（原生 ``QMenuBar``）。

为什么是原生菜单栏（而不是自绘 Fluent 菜单条）
--------------------------------------------
qfluentwidgets 1.11.2 **没有** MenuBar 组件（只有 ``RoundMenu`` 这类弹出菜单），
而本程序用的就是原生标题栏（见 ``desktop/shell.py`` 的模块头），所以顶部菜单走
Qt 原生 ``QMenuBar``：与既有窗口装饰同族、自带 ``Alt`` 助记符与键盘导航
（``文件(F)`` 这类写法就是助记符）。**不改窗口尺寸、不动壳层布局**——菜单栏
只吃高度、不吃宽度，因此 ``desktop/app.py::WINDOW_MIN_SIZE`` 的宽度下限与
``tests/selftests/ui/panel_label_fit.py`` 的 200px 断言都不受影响。

菜单项**只做路由与转发**，业务一律复用既有入口：

- 文件 → 新建任务：``shell.open_create()``（含"每次进入复位"，别另建页）；
- 文件 → 快速任务：原生选 PDF → ``shell.quick_task()``（**不经创建页**直接建，
  用户 2026-10-16）；
- 文件 → 退出：``window.close()`` —— **不是** ``QApplication.quit()``（见
  :func:`quit_app` 的说明）；
- 独立功能 → ``<key>``：``shell.show_module(key)``，清单**从 ``MODULES`` 派生**
  （与左侧导航同源同序，本文件不维护第二份清单）；
- 编辑 → 删除选中 / 插入图片 / 下载图片 / 打印图片：全部转发给当前页
  （鸭子类型 ``can_edit_*`` / ``edit_*``；PDF排版四项全开，图片拼版给
  删除/插入，其余步骤给下载/打印，用户 2026-11-01 从预览区顶部按钮行挪进
  菜单栏并扩展到四项）；
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
import types

from desktop.components.dialog_shell import shell_dialog
from desktop.utils.files import pending_install_file, updates_dir
from utils.data_package import read_local_version, resolve_weights

from . import (
    _qt,
    about,
    actions,
    constants,
    data_package,
    installer,
    menus,
    panels,
    titlebar,
    updates,
    verdicts,
)
from ._qt import (
    QAction,
    QApplication,
    QColor,
    QDesktopServices,
    QDialog,
    QFileDialog,
    QFontMetrics,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMenuBar,
    QObject,
    QPalette,
    QTimer,
    QUrl,
    QVBoxLayout,
    QWidget,
    Qt,
    Signal,
)
from .about import _about_size, open_about
from .actions import (
    _can_delete_selected,
    _can_edit_action,
    _current_page,
    _delete_selected,
    _edit_hook,
    _module_slot,
    _run_edit_action,
    open_quick_task,
    quit_app,
)
from .constants import (
    ACTION_ABOUT,
    ACTION_CREATE_TASK,
    ACTION_DATA_PACKAGE,
    ACTION_DATA_PACKAGE_BUSY,
    ACTION_DATA_PACKAGE_DOWNLOADING,
    ACTION_DATA_PACKAGE_TOOLTIP,
    ACTION_DELETE_SELECTED,
    ACTION_DOWNLOAD_IMAGE,
    ACTION_INSERT_IMAGES,
    ACTION_MANUAL,
    ACTION_PRINT_IMAGE,
    ACTION_QUICK_TASK,
    ACTION_QUIT,
    ACTION_UPDATE,
    ACTION_UPDATE_BUSY,
    ACTION_UPDATE_DOWNLOADING,
    ACTION_UPDATE_TOOLTIP,
    BUTTON_BROWSER,
    BUTTON_CANCEL,
    BUTTON_DOWNLOAD,
    BUTTON_INSTALL,
    BUTTON_LATER,
    BUTTON_OK,
    BUTTON_RETRY,
    DATA_PACKAGE_URL,
    EDIT_MENU_ITEMS,
    FAILURE_REASONS,
    MENU_EDIT,
    MENU_FILE,
    MENU_HELP,
    MENU_MODULES,
    NEW_VERSION_SUFFIX,
    PROJECT_URL,
    QUICK_TASK_PICK_TITLE,
    RESULT_LATEST,
    RESULT_NEWER,
    TITLE_BAR_BG,
    TITLE_BAR_FONT_SIZE,
    TITLE_BAR_ROW_HEIGHT,
)
from .data_package import DataPackageController
from .menus import (
    _add_menu,
    build_edit_menu,
    build_file_menu,
    build_help_menu,
    build_modules_menu,
)
from .panels import _AboutPanel, _DownloadProgress, _MessagePanel, _ProgressPanel
from .titlebar import install_menu_bar, install_title_bar
from .updates import UpdateController
from .verdicts import (
    UpdateVerdict,
    _download_failed_verdict,
    _ready_verdict,
    about_rows,
    data_package_result,
    update_result,
)

__all__ = [
    "ACTION_ABOUT",
    "ACTION_CREATE_TASK",
    "ACTION_DATA_PACKAGE",
    "ACTION_DELETE_SELECTED",
    "ACTION_MANUAL",
    "ACTION_QUICK_TASK",
    "ACTION_QUIT",
    "ACTION_UPDATE",
    "BUTTON_BROWSER",
    "BUTTON_DOWNLOAD",
    "BUTTON_INSTALL",
    "DATA_PACKAGE_URL",
    "DataPackageController",
    "FAILURE_REASONS",
    "MENU_EDIT",
    "MENU_FILE",
    "MENU_HELP",
    "MENU_MODULES",
    "PROJECT_URL",
    "QUICK_TASK_PICK_TITLE",
    "RESULT_LATEST",
    "RESULT_NEWER",
    "UpdateController",
    "UpdateVerdict",
    "about_rows",
    "build_edit_menu",
    "build_file_menu",
    "build_help_menu",
    "build_single_task_menu",
    "data_package_result",
    "install_menu_bar",
    "install_title_bar",
    "open_about",
    "open_quick_task",
    "quit_app",
    "update_result",
]


# 兼容层：外部（自测 / 旧脚本）仍按 ``menu.<名字> = …`` 替换本模块顶层的依赖。
# 拆包后这些名字分别住在子模块里，赋值只落在包上不会影响子模块里的函数，所以
# 这里把赋值同步给"定义了同名全局"的子模块，语义与拆包前完全一致。
class _MenuPackage(types.ModuleType):
    """把 ``menu.<名字> = …`` 的赋值同步到子模块里同名的全局变量。"""

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        for module in _SUBMODULES:
            if name in vars(module):
                setattr(module, name, value)


_SUBMODULES = (
    _qt,
    about,
    actions,
    constants,
    data_package,
    installer,
    menus,
    panels,
    titlebar,
    updates,
    verdicts,
)
sys.modules[__name__].__class__ = _MenuPackage
