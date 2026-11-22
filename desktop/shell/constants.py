# -*- coding: utf-8 -*-
"""导航壳层的尺寸常量与路由键。"""

from __future__ import annotations

#: 导航栏**折叠**时的宽度（px）。折叠态只剩一列图标，正文区分到剩下的宽度。
#:
#: ⚠️ 这个数不只影响导航栏自己：它是**主窗口最小宽度必须多出来的那一截**
#: （见 ``desktop/app.py::WINDOW_MIN_SIZE``）。壳层是常驻外框，正文区少了这
#: 48px，四个步骤的参数表单就会被挤到 178px（第三步「印章面积阈值」那行的
#: 输入框，实测；没有壳层时是 226px）——`tests/selftests/ui/panel_label_fit.py`
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
#: 「创建任务」二级页（2026-10-06：原为模态弹窗）
ROUTE_CREATE = "create"
#: 「任务流程编辑」二级页（详情页页头进入）
ROUTE_FLOW = "flow"
#: 「设置」页（左侧导航栏**底部**的条目，用户 2026-10-16）
ROUTE_SETTINGS = "settings"
#: 「独立功能」入口页（用户 2026-11-17：左侧导航收成一条，模块页都是它的下级）
ROUTE_MODULES = "modules"

#: 这两个页面**没有**自己的导航条目（它们是「任务管理」的下级，像详情页一样）
_SUBROUTES = (ROUTE_DETAIL, ROUTE_CREATE, ROUTE_FLOW)
