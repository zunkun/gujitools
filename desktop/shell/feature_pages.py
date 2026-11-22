# -*- coding: utf-8 -*-
"""独立功能入口页 / 设置页 / 切换数据目录。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

from desktop.modules import MODULES, module_by_key
from desktop.store import TaskStore

if TYPE_CHECKING:
    from desktop.pages.modulehub.page import ModuleHubPage
    from desktop.settings.page import SettingsPage


class FeaturePagesMixin:
    """模块入口页、模块页与设置页的惰性构造和切换。"""

    # ------------------------------------------------------------------ 独立功能
    def modules_page(self) -> ModuleHubPage:
        """「独立功能」入口页（惰性构造；外部截图/自测按这个方法取）。"""
        if self._modules_page is None:
            from desktop.pages.modulehub.page import ModuleHubPage

            # 清单只有一份：入口页的方块 = MODULES（spec 里 nav=True 的派生）。
            # ⚠️ 入口页**不 import** desktop.modules（守住 pages 不反向依赖），
            #    元数据由壳层注入。
            page = ModuleHubPage(MODULES)
            page.module_requested.connect(self.show_module)
            self.pages.addWidget(page)
            self._modules_page = page
        return self._modules_page

    def show_modules(self) -> None:
        """切到「独立功能」入口页（左侧导航那条「独立功能」走这里）。"""
        page = self.modules_page()
        self.pages.setCurrentWidget(page)
        if self.pages.currentWidget() is page:
            self._sync_nav_to_page(0)
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

    # ------------------------------------------------------------------ 设置
    def settings_page(self) -> SettingsPage:
        """设置页（惰性构造；外部截图/自测按这个方法取）。"""
        if self._settings_page is None:
            from desktop.settings.page import SettingsPage

            self._settings_page = SettingsPage()
            self.pages.addWidget(self._settings_page)
        return self._settings_page

    def show_settings(self) -> None:
        """切到设置页（左侧导航栏底部的「设置」条目走这里）。"""
        page = self.settings_page()
        self.pages.setCurrentWidget(page)
        if self.pages.currentWidget() is page:
            self._sync_nav_to_page(0)

    def rebind_store(self, store: TaskStore) -> None:
        """把壳层与**已建页面**上的 store 引用一起换掉（换数据目录用）。

        ⚠️ 必须一起换：壳层自己持一份（惰性详情页构造时取的就是它）、列表页
        持一份、已经建出来的详情页又持一份。只改 ``MainWindow.store`` 而漏掉
        这里，惰性构造的详情页会继续指向**老目录**——表现是"打开的是同名任务
        号的另一个任务"（`tests/selftests/task/last_stage.py` 就是这么红的：真实数据
        目录里恰好也有 0001，而它停在拼版步）。测试的
        「换 store 指向临时目录」这一手（`_context.prepare`）全靠它。
        """
        self.store = store
        self.list_page.store = store
        if self._detail_page is not None:
            self._detail_page.store = store
        for page in (self._create_page, self._flow_page):
            if page is not None:
                page.store = store
