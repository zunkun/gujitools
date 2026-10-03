# -*- coding: utf-8 -*-
"""独立功能模块包：**左侧导航**里的每个条目对应一个模块。

设计目标（用户 2026-10-02 要求）：
「使用 qfluentwidget 组件，左侧开发「图片提取 / 去底色 / 拼图」等模块功能，
这些功能**独立**，但是**复用先有功能**。」

两个关键词决定了这一层的形状：

- **独立**：每个模块是一个自包含的 ``QWidget`` 页面，只依赖
  ``desktop.components.*`` / ``desktop.services.*`` / ``functions.*`` 这些
  **共享底座**；模块之间**零 import 依赖**，也不依赖 ``TaskDetailPage``
  （那条「任务 → 四步」的重编排流程）。删掉一个模块只需从 :data:`MODULES`
  里去掉一行，其余代码一行都不用动。
- **复用**：模块页面**不重新发明控件**——参数表单直接用现成的
  ``ExtractPanel`` / ``RembgPanel``，拼版用现成的 ``ImpositionViewWidget`` +
  ``ImpositionPanel``，执行直接调 ``functions.get_function()``。新增模块的
  成本因此只有「选文件 + 放控件 + 起线程」这一层胶水。

壳层（``desktop/modules/shell.py``）只从本模块拿**元数据**（key/标题/图标/
工厂），从不 import 具体页面——工厂是惰性的，只有用户真正点进某个模块时
才触发那个页面的 import。这与 ``desktop.pages`` 的 PEP 562 惰性导出同一套路：
启动时不该为「用户可能不点」的模块付构造/导入开销。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from desktop.steps.spec import NAV_STEPS, spec_by_key


@dataclass(frozen=True)
class Module:
    """左侧导航的一个模块条目（纯元数据，不含任何控件/导入）。

    - ``key``：唯一路由键，同时用作 ``QStackedWidget`` 的寻址依据；
    - ``title``：导航栏文案；
    - ``icon``：``nav_icon`` 字符串（``FluentIcon`` 成员名或 ``svg:名字`` 自绘图），
      壳层经 ``desktop.ui.icons.resolve_nav_icon`` 解析成图标对象
      （延迟到壳层再取，避免这里 import 重物）；
    - ``subtitle``：页头副标题；
    - ``factory``：``() -> QWidget``，**首次进入该模块时才调用**。
    """

    key: str
    title: str
    icon: str
    subtitle: str
    factory: Callable[[], object]


def _page_factory(key: str):
    """按 key 造一个**惰性**工厂：点进那个模块时才 import 它的页面包。

    命名约定（只有这一条，别再加登记表）：模块 ``key`` 对应包
    ``desktop.modules.<key>``，且该包必须导出一个 ``PAGE``——它的页面类。
    于是"新增一个模块" = 写一个包 + 在 ``desktop.steps.spec.SPECS`` 加一条
    ``nav=True`` 的 spec，**壳层与本文件都不用动**。

    ⚠️ 用 ``importlib`` 而不是"在顶层 import 每个页面"：启动时不该为「用户可能
    不点」的模块付构造/导入开销（与 ``desktop.pages`` 的 PEP 562 惰性导出同理）。
    """

    def build():
        import importlib

        return importlib.import_module(f"desktop.modules.{key}").PAGE()

    return build


#: 左侧导航的模块清单（顺序即显示顺序）。
#:
#: ⚠️ **不是独立的一份清单**：它按 ``desktop.steps.spec.NAV_STEPS``（``SPECS`` 里
#: ``nav=True`` 者的**已排序** key 列表）逐个取 spec 派生——标题取 ``nav_name()``
#: （**不是** ``title``：导航那一列有自己的文案，见 ``StepSpec.nav_title``）、
#: 悬停提示取 ``nav_tip()``、图标取 ``nav_icon``。
#: 一个步骤"要不要进左侧导航"由它自己的 spec 说（``nav``），而不是在这里再写
#: 第二遍（以前正是两处并存，文案已经漂过一次：导航写「图片提取」、流程条写
#: 「提取图片」，改一处忘一处）。
#:
#: ⚠️ **遍历 ``NAV_STEPS`` 而不是 ``SPECS``**：显示顺序由 ``StepSpec.nav_order``
#: 决定（"生成PDF" 排最后），而 ``NAV_STEPS`` 是唯一算好这个顺序的地方。这里直接
#: 遍历 ``SPECS`` 会拿到书写顺序 ⇒ ``nav_order`` 形同虚设（``modules_shell`` 的
#: "注册表 = NAV_STEPS 派生（顺序一致）"就是守这条的）。
#:
#: 2026-10-02：四条主链步骤 + 拼版**全部**有了独立模块页，故这里现在是 5 条。
#: 判断依据永远是 ``spec.nav``，本文件不维护数量（``modules_shell`` 自测也按
#: ``NAV_STEPS`` 派生校验，不写死数字）。
MODULES: tuple[Module, ...] = tuple(
    Module(
        key=spec.key,
        title=spec.nav_name(),
        icon=spec.nav_icon,
        subtitle=spec.nav_tip(),
        factory=_page_factory(spec.key),
    )
    for spec in (spec_by_key(key) for key in NAV_STEPS)
)


def module_by_key(key: str) -> Module | None:
    """按路由键取模块元数据；不存在返回 None（调用方自己决定怎么提示）。"""
    for module in MODULES:
        if module.key == key:
            return module
    return None


__all__ = ["MODULES", "Module", "module_by_key"]
