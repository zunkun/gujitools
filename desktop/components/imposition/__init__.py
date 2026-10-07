# -*- coding: utf-8 -*-
"""图片拼版 UI 组件包——按操作逻辑分成两个互不依赖的模块：

- **模块一「选择拼版」**（``page_list.py`` + ``picker.py``）：左列拼版页
  清单与「选择拼版」弹窗——决定**拼哪几张、拼几页**；
- **模块二「拼版操作」**（``canvas.py`` + ``panel.py``）：操作画布与右侧
  控制面板——决定**每页版面怎么摆**；
- ``view.py`` 是两个模块的**装配层**（ImpositionViewWidget）。

控制器在 ``desktop/pages/taskdetail/``：``imposition.py``（共享基元）、
``imposition_pages.py``（模块一）、``imposition_layout.py``（模块二）。

⚠️ 惰性导出（PEP 562），与 ``desktop.components.viewers`` 同一规矩：
详情页的组件不该被启动流程拖出来。
"""

from typing import TYPE_CHECKING

#: 惰性导出的**类型**侧声明（见模块 docstring）：类型检查器看不见 PEP 562 的
#: ``__getattr__``，缺这一段会把下面 ``_LAZY`` 的名字全当成未定义。
#: **只影响类型检查**——运行时的惰性加载照旧。
if TYPE_CHECKING:
    from desktop.components.imposition.canvas import ImpositionCanvas
    from desktop.components.imposition.page_list import ImpositionPageList
    from desktop.components.imposition.panel import ImpositionPanel
    from desktop.components.imposition.picker import ImpositionPickerDialog
    from desktop.components.imposition.view import ImpositionViewWidget

__all__ = [
    "ImpositionCanvas",
    "ImpositionPageList",
    "ImpositionPanel",
    "ImpositionPickerDialog",
    "ImpositionViewWidget",
]

_LAZY = {
    "ImpositionCanvas": ("desktop.components.imposition.canvas", "ImpositionCanvas"),
    "ImpositionPageList": (
        "desktop.components.imposition.page_list", "ImpositionPageList",
    ),
    "ImpositionPanel": ("desktop.components.imposition.panel", "ImpositionPanel"),
    "ImpositionPickerDialog": (
        "desktop.components.imposition.picker", "ImpositionPickerDialog",
    ),
    "ImpositionViewWidget": (
        "desktop.components.imposition.view", "ImpositionViewWidget",
    ),
}


def __getattr__(name: str):
    """按需导入（PEP 562），并缓存进 globals 以免重复走导入系统。"""
    entry = _LAZY.get(name)
    if entry is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(entry[0]), entry[1])
    globals()[name] = value
    return value
