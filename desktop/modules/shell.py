# -*- coding: utf-8 -*-
"""左侧导航壳层：qfluentwidgets 的 ``NavigationInterface`` + 页面栈。

布局照搬 ``FluentWindow`` 的做法（导航栏在左、页面栈在右、拉伸因子给页面栈），
但不继承 ``FluentWindow``——那个类自带标题栏/亚克力/Mica 一整套窗口装饰，
而本程序用的是原生标题栏（``desktop/app.py`` 有最大化/还原尺寸与单例逻辑），
换标题栏会连带影响窗口尺寸夹紧与截图脚本。所以只借它的**布局套路**：

    hBoxLayout { navigationInterface, pageStack( stretch=1 ) }

导航条目分两组：

- ``TOP``：**任务管理**（原 ``TaskListPage``，点任务仍在栈内打开详情页）+
  各独立模块（图片提取 / 去底色 / 拼图，来自 ``desktop.modules.MODULES``）；
- 模块条目全部**惰性构造**：第一次点进去才 ``factory()``，不点不建。

⚠️ 导航栏**默认折叠**（用户 2026-10-02：「左侧的目录，默认关闭」）：启动后
只剩一列图标，正文区拿到整幅宽度；想看到条目文字就点左上角的菜单按钮展开，
再点一次收回。**不要**再在 resizeEvent 里替用户 `expand()`——那会让"默认
关闭"失效（见 :meth:`resizeEvent` 的说明）。

⚠️ 壳层**不 import 任何具体模块页**，只认 :class:`desktop.modules.Module` 的
元数据与工厂——这是「模块独立」在壳层侧的落实：删模块只需要改 ``MODULES``。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QWidget
from qfluentwidgets import (
    FluentIcon as FIF,
    NavigationInterface,
    NavigationItemPosition,
    setThemeColor,
)

from desktop.modules import MODULES, module_by_key
from desktop.pages.tasklist.page import TaskListPage
from desktop.store import TaskStore
from desktop.ui import theme as T
from desktop.ui.icons import resolve_nav_icon

#: 导航栏**折叠**时的宽度（px）。折叠态只剩一列图标，正文区分到剩下的宽度。
#:
#: ⚠️ 这个数不只影响导航栏自己：它是**主窗口最小宽度必须多出来的那一截**
#: （见 ``desktop/app.py::WINDOW_MIN_SIZE``）。壳层是常驻外框，正文区少了这
#: 48px，四个步骤的参数表单就会被挤到 178px（第三步「印章面积阈值」那行的
#: 输入框，实测；没有壳层时是 226px）——`tests/selftests/panel_label_fit.py`
#: 卡的 200px 下限就是这么被踩掉的。
#:
#: 取值来自 qfluentwidgets ``NavigationPanel`` 的 COMPACT 宽度（实测 48，
#: 不随窗口/字体变）。改动导航实现后这里要重新量一次。
NAV_COMPACT_WIDTH = 48

#: 导航栏展开宽度（px）。200 是 qfluentwidgets 的默认展开宽度，够放
#: 「图片提取 / 去底色 / 拼图 / 任务管理」四条中文；再宽会白占预览区。
NAV_WIDTH = 200

#: 允许导航栏**展开**的最小窗口宽度（px）。
#:
#: 传给 ``NavigationPanel.setMinimumExpandWidth``：窗口窄于它时，已经展开的
#: 导航会自动收回（避免在窄窗口里挤掉正文区）。取 720（窗口最小宽度 1080 的
#: 量级）——正常窗口都能展开，只有被拖得极窄时才自动收回。
#:
#: ⚠️ 它**不**负责"启动即展开"：默认是折叠的（用户 2026-10-02 要求），
#: 展开与否由用户点菜单按钮决定。
NAV_MIN_EXPAND_WINDOW = 720

#: 任务管理与详情页的路由键（不是模块，所以不放进 ``MODULES``）
ROUTE_TASKS = "tasks"
ROUTE_DETAIL = "detail"


class ModuleShell(QWidget):
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
        root.addWidget(self.nav)

        self.pages = QStackedWidget()
        self.pages.setObjectName("pageRoot")
        # ⚠️ 外部（gui_shot.py / 自测）会直接 ``window.pages.setCurrentWidget(page)``
        #    切页，那条路绕过 show_tasks/show_module，导航高亮就会与实际页面
        #    不同步（截图里左边高亮"任务管理"、右边却是别的页）。这里监听栈的
        #    页面变化，把导航选中态**跟着页面走**，两条入口就一致了。
        self.pages.currentChanged.connect(self._sync_nav_to_page)
        root.addWidget(self.pages, 1)

        # ---- 任务管理（原首页）：常驻、启动即建 ----
        self.list_page = TaskListPage(self.store)
        self.pages.addWidget(self.list_page)
        #: 「任务管理」导航条目（自测要点它；也便于将来做快捷键/命令面板）
        self._tasks_item = self.nav.addItem(
            ROUTE_TASKS,
            FIF.HOME,
            "任务管理",
            onClick=self._tasks_click_handler(),
            position=NavigationItemPosition.TOP,
        )

        # ---- 独立模块：按注册表登记，全部惰性 ----
        self.nav.addSeparator(position=NavigationItemPosition.TOP)
        self._module_pages: dict[str, QWidget] = {}
        self._module_items: dict[str, object] = {}
        for module in MODULES:
            item = self.nav.addItem(
                module.key,
                resolve_nav_icon(module.icon),
                module.title,
                onClick=self._module_click_handler(module.key),
                position=NavigationItemPosition.TOP,
                tooltip=module.subtitle,
            )
            self._module_items[module.key] = item

        # ---- 详情页：惰性（同 app.py 原逻辑，构造约 400ms）----
        self._detail_page: QWidget | None = None

    # ------------------------------------------------------------------ 点击槽
    def _module_click_handler(self, key: str):
        """生成"点某个模块"的槽。

        ⚠️⚠️ 这里的 ``_checked`` 形参**必须有**（不能省成 ``lambda key=key:``）：
        qfluentwidgets 的 ``NavigationWidget.clicked`` 是 ``Signal(bool)``
        （``clicked.emit(True)``），而 ``NavigationPanel._registerWidget`` 把
        onClick **直接连到这个信号**上——Qt 会把那个 bool 当**第一个位置参数**
        传进来。写成 ``lambda key=module.key: self.show_module(key)`` 的话，
        ``key`` 实际收到的是 ``True``，于是走 ``show_module(True)`` → 注册表里
        找不到 → 安静退回任务管理。

        症状（用户 2026-10-02 实测报障）：「点击左侧的图片提取，显示的还是任务
        管理」——**导航高亮跳一下就回到"任务管理"**，三个模块全都点不开。
        「任务管理」那条当时"能用"纯属巧合（它的槽没有形参，PySide 会把多余的
        参数丢掉），所以只有模块条目坏掉，更容易被当成"模块没实现"。
        """
        return lambda _checked=False: self.show_module(key)

    def _tasks_click_handler(self):
        """生成"点任务管理"的槽（同样要吞掉 clicked 的 bool，理由见上）。"""
        return lambda _checked=False: self.show_tasks()

    # ------------------------------------------------------------------ 主题
    def _apply_nav_theme(self) -> None:
        """把导航栏底色/选中指示器对齐本项目配色。

        qfluentwidgets 的导航栏默认给``setCustomBackgroundColor`` 之类并不存在
        （见 1.5.x API），能调的只有指示器与字体；底色靠窗口样式表统一（
        ``desktop.ui.style`` 已覆盖 ``#moduleShell``）。
        """
        setThemeColor(T.ACCENT)  # 选中指示器/焦点色跟随主色
        font = self.nav.font()
        font.setPixelSize(T.SIZE_BODY)
        self.nav.setFont(font)

    # ------------------------------------------------------------------ 任务
    def show_tasks(self) -> None:
        """切回任务列表页并刷新列表。

        ⚠️ 不去手动 ``setCurrentItem``：切页会触发 ``pages.currentChanged``
        → :meth:`_sync_nav_to_page` 统一同步高亮，单点维护不易漏。
        """
        self.pages.setCurrentWidget(self.list_page)
        self.list_page.refresh()

    @property
    def detail_page(self):
        """任务详情页（惰性构造）。

        保留这个名字：``tests/selftests/_context.py`` 与 ``tests/gui_shot.py``
        都按 ``window.detail_page`` 取页面来操作控件（原来在 MainWindow 上，
        现在壳层转发一层，外部契约不变）。
        """
        return self._ensure_detail_page()

    def _ensure_detail_page(self):
        """首次需要时建详情页、挂进栈并接「返回」信号（同 app.py 原实现）。"""
        if self._detail_page is None:
            from desktop.pages import TaskDetailPage

            page = TaskDetailPage(self.store)
            page.back_requested.connect(self.back_to_list)
            self.pages.addWidget(page)
            self._detail_page = page
        return self._detail_page

    def prewarm_detail_page(self) -> None:
        """预构造详情页骨架与**第一步**面板（同 app.py 原 ``_prewarm_detail_page``）。"""
        page = self._ensure_detail_page()
        first = page.control_stack.widget(0)
        if hasattr(first, "peek") and first.peek() is None:
            first.panel  # noqa: B018 - 触发构造，返回值不用

    def open_detail(self, task_id: str) -> None:
        """打开某个任务的详情页（行为与 ``app.py::_open_detail`` 一致）。"""
        page = self._ensure_detail_page()
        if page.set_task(task_id):
            self.pages.setCurrentWidget(page)
        else:
            busy = page.running_stage is not None or (
                page.process is not None
                and page.process.state() != page.process.NotRunning
            )
            if busy:
                self.pages.setCurrentWidget(page)
            self.list_page.refresh()

    def back_to_list(self) -> None:
        """详情页「返回」→ 切回列表并刷新。"""
        self.show_tasks()

    # ------------------------------------------------------------------ 模块
    def show_module(self, key: str) -> None:
        """切到某个模块页；首次进入时惰性构造。

        找不到该 key（注册表被改过、或旧导航项残留）时安静退回任务管理并提示，
        不让壳层抛异常——导航项是用户能点的东西，任何输入都不该让程序崩。
        """
        module = module_by_key(key)
        if module is None:
            self.show_tasks()
            return
        page = self._module_pages.get(key)
        if page is None:
            page = module.factory()
            self.pages.addWidget(page)
            self._module_pages[key] = page
        # ⚠️ 已经停在这一页时 ``setCurrentWidget`` 不换页、``currentChanged``
        #    也就不发，导航高亮会留灰（用户点了导航项却看不出选中）。
        #    所以这里显式补一次同步，不依赖信号。
        if self.pages.currentWidget() is page:
            self._sync_nav_to_page(0)
        else:
            self.pages.setCurrentWidget(page)

    def module_page(self, key: str) -> QWidget | None:
        """已构造的模块页；**没建过返回 None**（自测用它断言"惰性没被破坏"）。"""
        return self._module_pages.get(key)

    def rebind_store(self, store: TaskStore) -> None:
        """把壳层与**已建页面**上的 store 引用一起换掉（换数据目录用）。

        ⚠️ 必须一起换：壳层自己持一份（惰性详情页构造时取的就是它）、列表页
        持一份、已经建出来的详情页又持一份。只改 ``MainWindow.store`` 而漏掉
        这里，惰性构造的详情页会继续指向**老目录**——表现是"打开的是同名任务
        号的另一个任务"（`tests/selftests/last_stage.py` 就是这么红的：真实数据
        目录里恰好也有 0001，而它停在拼版步）。测试与截图脚本的
        「换 store 指向临时目录」这一手（`_context.prepare` / `gui_shot`）全靠它。
        """
        self.store = store
        self.list_page.store = store
        if self._detail_page is not None:
            self._detail_page.store = store

    def current_route(self) -> str:
        """当前**显示中**页面的路由键。

        ``QStackedWidget`` 里的页面对象与路由的映射在这里反查；模块页按
        ``_module_pages`` 的键匹配，任务列表/详情页按对象身份匹配。
        """
        current = self.pages.currentWidget()
        if current is self.list_page:
            return ROUTE_TASKS
        if current is self._detail_page:
            return ROUTE_DETAIL
        for key, page in self._module_pages.items():
            if page is current:
                return key
        return ""

    def _sync_nav_to_page(self, _index: int) -> None:
        """页面栈换页时，把导航高亮同步到对应条目（见 ``pages.currentChanged``）。

        ⚠️ 详情页**没有**导航条目（它由列表点进去，是"任务管理"的下级），
        所以 ``ROUTE_DETAIL`` 时要把高亮留在「任务管理」上，不能去
        ``setCurrentItem("detail")``——那会静默失败、高亮停在上一项。
        """
        route = self.current_route()
        if not route:
            return
        target = ROUTE_TASKS if route == ROUTE_DETAIL else route
        self._selected_route = target
        try:
            self.nav.setCurrentItem(target)
        except Exception:  # noqa: BLE001 - 条目还没登记完（构造期）不该炸
            pass

    def selected_route(self) -> str:
        """导航栏**当前高亮**的条目路由键。

        ⚠️ ``NavigationInterface`` 没有公开的"取当前项"接口（只有
        ``setCurrentItem``），所以这里自己记一份 ``_selected_route``——
        高亮是我们在 :meth:`_sync_nav_to_page` 里设的，记它准确且无副作用。
        """
        return self._selected_route

    # ------------------------------------------------------------------ 收尾
    def nav_is_expanded(self) -> bool:
        """导航栏当前是否展开（``EXPAND``）。

        测试/截图脚本用它断言"默认是折叠的、点菜单按钮能展开"——qfluentwidgets
        没有公开的 displayMode 读取接口，所以在这里封一层。
        """
        from qfluentwidgets import NavigationDisplayMode

        return self.nav.panel.displayMode == NavigationDisplayMode.EXPAND

    def toggle_nav(self) -> None:
        """展开/收回导航栏（等价于点左上角的菜单按钮）。

        供菜单按钮之外的入口（自测、快捷键、将来的命令面板）复用同一条逻辑：
        折叠时展开、展开时收回，**不改变**默认折叠这条约定。

        ⚠️ 必须走 ``NavigationInterface.toggle()``：``NavigationInterface``
        **只有 ``expand()`` 没有 ``collapse()``**（收回在 ``panel`` 上），
        自己拼 expand/collapse 会踩 ``AttributeError``。
        """
        self.nav.toggle()

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


__all__ = [
    "ModuleShell",
    "NAV_COMPACT_WIDTH",
    "NAV_MIN_EXPAND_WINDOW",
    "NAV_WIDTH",
    "ROUTE_DETAIL",
    "ROUTE_TASKS",
]
