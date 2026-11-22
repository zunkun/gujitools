# -*- coding: utf-8 -*-
"""壳层根控件 ModuleShell（导航栏 + 页面栈）。

本文件只保留骨架（构造、收尾、按键转发），其余职责按功能分文件
（均位于 desktop/shell/）：

- navigation.NavigationMixin  导航点击槽 / 主题 / 高亮同步 / 展开收回
- task_pages.TaskPagesMixin   任务列表页与惰性详情页的切换、预热
- create_flow.CreateFlowMixin 创建任务页 / 快速任务 / 流程编辑页
- feature_pages.FeaturePagesMixin 独立功能入口页 / 模块页 / 设置页
- constants                   尺寸常量与路由键

（导航栏浅色背板 ``_NavBackdrop`` 与壳层同住本文件。）
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QWidget
from qfluentwidgets import (
    FluentIcon as FIF,
    NavigationInterface,
    NavigationItemPosition,
)

# ⚠️ 壳层住在 desktop 包根而不是 desktop.modules 里：它要挂任务列表页与
# 详情页（desktop.pages），住进 modules 包就破坏了「modules 不依赖 pages」
# 的包边界。方向只允许 shell → modules（拿注册表），绝不反向。
from desktop.pages.tasklist.page import TaskListPage
from desktop.store import TaskStore
from desktop.ui import theme as T
from desktop.shell.constants import (
    NAV_MIN_EXPAND_WINDOW,
    NAV_WIDTH,
    ROUTE_MODULES,
    ROUTE_SETTINGS,
    ROUTE_TASKS,
)
from desktop.shell.create_flow import CreateFlowMixin
from desktop.shell.feature_pages import FeaturePagesMixin
from desktop.shell.navigation import NavigationMixin
from desktop.shell.task_pages import TaskPagesMixin

if TYPE_CHECKING:
    from desktop.pages.createtask.page import CreateTaskPage
    from desktop.pages.modulehub.page import ModuleHubPage
    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.pages.taskflow.page import TaskFlowPage
    from desktop.settings.page import SettingsPage


class _NavBackdrop(QWidget):
    """导航栏背板：给导航区一层浅色底 + 右侧分隔线。

    ⚠️ 为什么需要它（用户 2026-11-03 报「侧边导航太宽、图标没居中」）：
    qfluentwidgets 的 ``NavigationPanel`` 在折叠/展开态（``menu=false``）且
    关闭亚克力时是**完全透明**的（见 ``navigation_interface.qss``），导航栏
    与页面底色（``CANVAS``）连成一片。页面的左内边距（24px）于是被读成
    "导航栏的一部分"，视觉侧栏变成 48+24=72px、图标（中心 24.5px）看着左偏。
    实测导航栏本身仍是官方的 48px、图标居中——**不是宽度 bug**，只是缺边界。

    背板尺寸跟着导航栏走（折叠 48 / 展开 200），所以展开时也不会露馅。
    """

    def __init__(self, nav: NavigationInterface, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(nav)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """浅色底 + 右侧 1px 分隔线（颜色取设计令牌，不写死色值）。"""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(T.SURFACE_SOFT))
        painter.fillRect(
            QRect(self.width() - 1, 0, 1, self.height()), QColor(T.BORDER)
        )


class ModuleShell(
    TaskPagesMixin,
    CreateFlowMixin,
    FeaturePagesMixin,
    NavigationMixin,
    QWidget,
):
    """壳层根控件：左侧导航 + 右侧页面栈。

    对外暴露 :meth:`open_detail` / :meth:`back_to_list` 供 ``MainWindow``
    转发（两者都走栈切换，行为与 ``app.py`` 原来的 ``_open_detail`` /
    ``_back_to_list`` 一致）。
    """

    def __init__(self, store: TaskStore, parent=None):
        """建导航与页面栈，挂上「任务管理」页，模块条目按注册表登记。"""
        super().__init__(parent)
        self.store = store
        self.setObjectName("moduleShell")
        #: 导航栏当前高亮的条目（见 selected_route 的说明）
        self._selected_route = ROUTE_TASKS
        #: PDF 渲染子进程池是否已预热（见 :meth:`_prewarm_pdf_renderer`）
        self._render_prewarmed = False
        # ⚠️ 模块页缓存与「独立功能」入口页必须**先**初始化：下面 addWidget
        #    （列表页）就会触发 ``pages.currentChanged`` → :meth:`_sync_nav_to_page`，
        #    那里按 ``_module_pages`` 判路由归属——晚一步就是 AttributeError
        #    （只在构造期打印、不崩，但属于脏异常）。
        self._module_pages: dict[str, QWidget] = {}
        self._modules_page: ModuleHubPage | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav = NavigationInterface(self, showMenuButton=True, collapsible=True)
        self.nav.setExpandWidth(NAV_WIDTH)
        # ⚠️ **默认折叠**（用户 2026-10-02：「左侧的目录，默认关闭」）。
        #    qfluentwidgets 的默认 displayMode 就是 COMPACT（只剩一列图标），
        #    所以这里**什么都不做**即可——只要别再像以前那样在 resizeEvent
        #    里替用户 expand()。菜单按钮（showMenuButton=True）是展开的唯一入口：
        #    用户点一下变 EXPAND，再点收回。
        #    ⚠️ 光设 ``setMinimumExpandWidth`` 只管"窗口被拖窄时自动收回"，
        #    不会替我们展开（面板只在"菜单按钮不可见"时才自动展开，而本程序
        #    一直显示菜单按钮）——这正是默认折叠能稳住的原因。
        self.nav.setMinimumExpandWidth(NAV_MIN_EXPAND_WINDOW)
        # 导航栏自带白底，与页面底色（CANVAS）区分开；不能让它的亚克力
        # 背景透出桌面（本程序是普通窗口，不是 FluentWindow）。
        self.nav.setAcrylicEnabled(False)
        self._apply_nav_theme()
        # 导航栏本体透明，外面套一层背板给它浅色底和右侧边界（见 _NavBackdrop）
        self._nav_backdrop = _NavBackdrop(self.nav, self)
        root.addWidget(self._nav_backdrop)

        self.pages = QStackedWidget()
        self.pages.setObjectName("pageRoot")
        # ⚠️ 外部（自测）会直接 ``window.pages.setCurrentWidget(page)``
        #    切页，那条路绕过 show_tasks/show_module，导航高亮就会与实际页面
        #    不同步（截图里左边高亮"任务管理"、右边却是别的页）。这里监听栈的
        #    页面变化，把导航选中态**跟着页面走**，两条入口就一致了。
        self.pages.currentChanged.connect(self._sync_nav_to_page)
        root.addWidget(self.pages, 1)

        # ---- 任务管理（原首页）：常驻、启动即建 ----
        self.list_page = TaskListPage(self.store)
        self.pages.addWidget(self.list_page)
        #: 「任务管理」导航条目（自测要点它；也便于将来做快捷键/命令面板）
        # 列表页「创建任务」按钮 → 切到创建任务二级页（不再弹模态窗）
        self.list_page.create_requested.connect(self.open_create)
        # 聚合任务的成员产物在后台汇集完成 → 若详情页正开着它，就地重载
        # （否则用户看到的是"创建了但什么都没有"的空任务）
        self.list_page.aggregate_ready.connect(self._on_aggregate_ready)

        self._tasks_item = self.nav.addItem(
            ROUTE_TASKS,
            FIF.HOME,
            "任务管理",
            onClick=self._tasks_click_handler(),
            position=NavigationItemPosition.TOP,
        )

        # ---- 独立功能（用户 2026-11-17）：**一个**导航条目 + 方块入口页 ----
        # 此前这里为每个模块各摆一个条目（图片提取/检测文本框/去底色/拼图/
        # PDF排版），导航栏被五个功能占满；现在收成一条「独立功能」，点进去
        # 是 :class:`ModuleHubPage`（方块网格，每个方块 = 一个模块入口）。
        # 模块页本身仍是**惰性构造**（见 show_module），入口页只发 key。
        self.nav.addSeparator(position=NavigationItemPosition.TOP)
        self._modules_item = self.nav.addItem(
            ROUTE_MODULES,
            FIF.TILES,
            "独立功能",
            onClick=self._modules_click_handler(),
            position=NavigationItemPosition.TOP,
            tooltip="图片提取 / 检测文本框 / 去底色 / 拼图 / PDF排版 等独立入口",
        )

        # ---- 设置：导航栏**底部**的条目（用户 2026-10-16）----
        # ⚠️ 它**不是** MODULES 里的一员：模块条目清一色是"处理步骤的独立页"
        #    （由 ``SPECS`` 派生），而设置页与处理流程无关。放在底部也正好与
        #    那一列步骤区分开（qfluentwidgets 的 BOTTOM 会自动贴到导航栏底端）。
        self._settings_item = self.nav.addItem(
            ROUTE_SETTINGS,
            FIF.SETTING,
            "设置",
            onClick=self._settings_click_handler(),
            position=NavigationItemPosition.BOTTOM,
            tooltip="存储位置、自动更新与功能开关",
        )

        # ---- 详情页：惰性（同 app.py 原逻辑，构造约 400ms）----
        # ⚠️ 标注成 TaskDetailPage 而不是 QWidget：下面几十处都在用它的专有
        # 成员（set_task / panel_host_of_step / process …）。详情页本身是惰性
        # 导入的（PEP 562，见 desktop/pages/__init__.py），这里用 TYPE_CHECKING
        # 导入只给类型检查看，运行时零开销、惰性不变。
        self._detail_page: TaskDetailPage | None = None
        # ---- 创建任务 / 流程编辑：二级页，同样惰性（都不常走）----
        # 同 _detail_page：标注成各自的真类型（惰性导入只给类型检查看）。
        self._create_page: CreateTaskPage | None = None
        self._flow_page: TaskFlowPage | None = None
        #: 设置页（惰性，同其它二级页）
        self._settings_page: SettingsPage | None = None

    def shutdown_workers(self) -> None:
        """收尾所有页面的后台线程（壳层 + 惰性页 + 已建模块页）。"""
        self.list_page.shutdown_workers()
        if self._detail_page is not None:
            self._detail_page.shutdown_all_workers()
        for page in self._module_pages.values():
            shutdown = getattr(page, "shutdown_workers", None)
            if callable(shutdown):
                try:
                    shutdown()
                except RuntimeError:
                    pass  # 控件已析构

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """←/→ 在详情页内转发翻页（同 app.py 原逻辑，焦点链不消费时兜底）。"""
        key = event.key()
        if (
            key in (Qt.Key.Key_Left, Qt.Key.Key_Right)
            and self._detail_page is not None
            and self.pages.currentWidget() is self._detail_page
        ):
            if self._detail_page.navigate_by_arrow(key == Qt.Key.Key_Right):
                event.accept()
                return
        super().keyPressEvent(event)
