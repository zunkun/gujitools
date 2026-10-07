# -*- coding: utf-8 -*-
"""阶段控制面板集合（按 STAGES 顺序注册）。

⚠️ **一律惰性导出**（PEP 562 模块级 ``__getattr__``）。

四个面板（尤其 ``PrintPanel`` 及其 print_form / print_nodes / print_sections
等子模块）都是**详情页**才用得上的；而本包目录下还住着 ``params_spec`` 这类
列表页也要读的规格表。父包的 ``__init__`` 一执行就会把四个面板全拖进来——
实测启动期因此多加载十几个模块。

改成惰性后 ``from desktop.components.panels import PANEL_CLASSES`` 照旧可用，
只是推迟到真正取用它的那一刻。
"""

from typing import TYPE_CHECKING

#: 惰性导出的**类型**侧声明（见模块 docstring）：类型检查器看不见 PEP 562 的
#: ``__getattr__``（含下面 PANEL_CLASSES 的组装分支），缺这一段会把这些名字
#: 全判成未定义。**只影响类型检查**——运行时仍是按需导入。
if TYPE_CHECKING:
    from desktop.components.panels.base import StagePanel
    from desktop.components.panels.detect_panel import DetectPanel
    from desktop.components.panels.extract_panel import ExtractPanel
    from desktop.components.panels.print_panel import PrintPanel
    from desktop.components.panels.rembg_panel import RembgPanel

    PANEL_CLASSES: tuple[type, ...]

__all__ = [
    "StagePanel",
    "ExtractPanel",
    "DetectPanel",
    "RembgPanel",
    "PrintPanel",
    "PANEL_CLASSES",
]

_LAZY = {
    "StagePanel": ("desktop.components.panels.base", "StagePanel"),
    "ExtractPanel": ("desktop.components.panels.extract_panel", "ExtractPanel"),
    "DetectPanel": ("desktop.components.panels.detect_panel", "DetectPanel"),
    "RembgPanel": ("desktop.components.panels.rembg_panel", "RembgPanel"),
    "PrintPanel": ("desktop.components.panels.print_panel", "PrintPanel"),
}

from desktop.steps.spec import SPECS

#: PANEL_CLASSES 的成员顺序 = **流程主链顺序**（元组要等类都拿到才拼得出来）。
#:
#: ⚠️ 从 ``desktop.steps.spec.SPECS`` 派生，不再手写第二份清单——以前这里是一份
#: 硬编码的类名元组，与 ``STAGES`` 各写各的，加一步就要改两处（且没有任何守卫
#: 能发现漏改）。取 ``role == "stage"`` 的 ``panel`` 字段，并把
#: ``"模块:类名"`` 写法取后半段。
_PANEL_ORDER = tuple(
    spec.panel.split(":")[-1]
    for spec in SPECS
    if spec.role == "stage" and spec.panel
)


def __getattr__(name: str):
    """按需导入面板（PEP 562），并缓存进 globals。"""
    if name == "PANEL_CLASSES":
        value = tuple(__getattr__(item) for item in _PANEL_ORDER)
        globals()["PANEL_CLASSES"] = value
        return value
    entry = _LAZY.get(name)
    if entry is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(entry[0]), entry[1])
    globals()[name] = value
    return value
