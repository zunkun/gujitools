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

#: PANEL_CLASSES 的成员顺序 = STAGES 顺序（元组要等四个类都拿到才拼得出来）
_PANEL_ORDER = ("ExtractPanel", "DetectPanel", "RembgPanel", "PrintPanel")


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
