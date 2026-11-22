# -*- coding: utf-8 -*-
"""壳层的导航交互：点击槽、主题、高亮同步、展开 / 收回。"""

from __future__ import annotations

from qfluentwidgets import setThemeColor

from desktop.ui import theme as T
from desktop.shell.constants import (
    ROUTE_CREATE,
    ROUTE_DETAIL,
    ROUTE_FLOW,
    ROUTE_MODULES,
    ROUTE_SETTINGS,
    ROUTE_TASKS,
    _SUBROUTES,
)


class NavigationMixin:
    """导航条目点击、高亮与展开状态。"""

    # ------------------------------------------------------------------ 点击槽
    def _modules_click_handler(self):
        """生成"点独立功能入口"的槽。

        ⚠️ ``_checked`` 形参**必须有**：qfluentwidgets 的
        ``NavigationWidget.clicked`` 是 ``Signal(bool)``，onClick 直连这个信号，
        Qt 会把那个 bool 当**第一个位置参数**传进来。写成无参 lambda 会让
        ``show_module(True)`` 之类静默退回任务管理（用户 2026-10-02 实测报障，
        守卫见 ``modules_shell`` 自测第 6a 节）。
        """
        return lambda _checked=False: self.show_modules()

    def _tasks_click_handler(self):
        """生成"点任务管理"的槽（同样要吞掉 clicked 的 bool，理由见上）。"""
        return lambda _checked=False: self.show_tasks()

    def _settings_click_handler(self):
        """生成"点设置"的槽（同样要吞掉 clicked 的 bool，理由见上）。"""
        return lambda _checked=False: self.show_settings()

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
    def _release_module_buffers(self, keep=None) -> None:
        """切走独立功能页：把其余模块页预览区的位图放掉（用户 2026-11-21）。

        模块页是常驻实例（切回来不重建），但预览区的大图与缩略图位图没有
        必要一直攥着。``keep`` 是**马上要显示**的那一页，不能放（它的
        ``showEvent`` 也不会再触发，放了就一直是空白）。
        """
        for page in self._module_pages.values():
            if page is keep:
                continue
            release = getattr(page, "release_buffers", None)
            if callable(release):
                try:
                    release()
                except RuntimeError:
                    pass  # 控件已析构

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
        if current is self._create_page:
            return ROUTE_CREATE
        if current is self._flow_page:
            return ROUTE_FLOW
        if self._settings_page is not None and current is self._settings_page:
            return ROUTE_SETTINGS
        if self._modules_page is not None and current is self._modules_page:
            return ROUTE_MODULES
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
        # 换页即释放：除了**当前正显示**的那个模块页，其余模块页预览区的
        # 位图都放掉（用户 2026-11-21「离开就释放」）。当前页不能放——它的
        # ``showEvent`` 已经跑过，放了就一直是空白。
        self._release_module_buffers(keep=self.pages.currentWidget())
        # 详情/创建/流程三个页面都没有自己的导航条目，高亮一律留在「任务管理」；
        # 模块页是「独立功能」的**下级**（2026-11-17 起导航里没有逐模块条目），
        # 高亮留在那条「独立功能」上；设置页与入口页有自己的条目，照实高亮。
        if route in _SUBROUTES:
            target = ROUTE_TASKS
        elif route in self._module_pages:
            target = ROUTE_MODULES
        else:
            target = route
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
