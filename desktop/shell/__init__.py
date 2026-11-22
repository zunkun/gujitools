# -*- coding: utf-8 -*-
"""左侧导航壳层：qfluentwidgets 的 ``NavigationInterface`` + 页面栈。

布局照搬 ``FluentWindow`` 的做法（导航栏在左、页面栈在右、拉伸因子给页面栈），
但不继承 ``FluentWindow``——那个类自带自己的导航栏与页面栈（会与本壳层打架），
我们只借它的**布局套路**。

⚠️ 窗口装饰的现状（2026-10-15 变更）：主窗口是**无边框 + 自绘标题栏**
（``desktop/app.py::MainWindow`` 基类 ``qframelesswindow.FramelessMainWindow``，
标题栏由 ``desktop/ui/menu.py::install_title_bar`` 装配成"图标 / 标题 / 菜单"一排）。
改这一层的原因是"菜单要跟在标题后面、不许另起一行"；壳层本身**不受影响**——
它仍只管导航栏 + 页面栈，且是 ``QMainWindow`` 的中央控件（标题栏占的是"菜单位"，
中央控件自动让开，两者不重叠）。

    hBoxLayout { navBackdrop( navigationInterface ), pageStack( stretch=1 ) }

（背板只负责给导航栏一层浅色底 + 右侧分隔线，见 :class:`_NavBackdrop`。）

导航条目（用户 2026-11-17 起）：

- ``TOP``：**任务管理**（原 ``TaskListPage``，点任务仍在栈内打开详情页）+
  **独立功能**（一条入口，点进去是方块页，每个方块 = 一个模块入口，
  模块清单来自 ``desktop.modules.MODULES``）；
- 模块页与入口页全部**惰性构造**：第一次点进去才 ``factory()``，不点不建。

⚠️ 导航栏**默认折叠**（用户 2026-10-02：「左侧的目录，默认关闭」）：启动后
只剩一列图标，正文区拿到整幅宽度；想看到条目文字就点左上角的菜单按钮展开，
再点一次收回。**不要**再在 resizeEvent 里替用户 `expand()`——那会让"默认
关闭"失效（见 :meth:`resizeEvent` 的说明）。

⚠️ 壳层**不 import 任何具体模块页**，只认 :class:`desktop.modules.Module` 的
元数据与工厂——这是「模块独立」在壳层侧的落实：删模块只需要改 ``MODULES``。

2026-11-22 按职责拆成子包（只搬不改）：

- widget.py        ModuleShell：构造、收尾、按键转发（含导航栏背板）
- navigation.py    导航点击槽 / 主题 / 高亮同步 / 展开收回
- task_pages.py    任务列表页与惰性详情页的切换、预热
- create_flow.py   创建任务页 / 快速任务 / 流程编辑页
- feature_pages.py 独立功能入口页 / 模块页 / 设置页
- constants.py     尺寸常量与路由键

⚠️ 本 ``__init__`` 只做重导出：既有 ``from desktop.shell import X`` 完全不变，
子模块之间不要反过来导入本包（会形成循环）。
"""

from desktop.shell.constants import (
    NAV_COMPACT_WIDTH,
    NAV_MIN_EXPAND_WINDOW,
    NAV_WIDTH,
    ROUTE_CREATE,
    ROUTE_DETAIL,
    ROUTE_FLOW,
    ROUTE_MODULES,
    ROUTE_SETTINGS,
    ROUTE_TASKS,
)
from desktop.shell.widget import ModuleShell, _NavBackdrop

__all__ = [
    "ModuleShell",
    "NAV_COMPACT_WIDTH",
    "NAV_MIN_EXPAND_WINDOW",
    "NAV_WIDTH",
    "ROUTE_CREATE",
    "ROUTE_DETAIL",
    "ROUTE_FLOW",
    "ROUTE_MODULES",
    "ROUTE_SETTINGS",
    "ROUTE_TASKS",
]
