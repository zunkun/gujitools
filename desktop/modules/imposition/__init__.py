# -*- coding: utf-8 -*-
"""独立模块「拼图」：与任务流程无关，选一批图片直接拼版并导出。"""

from desktop.modules.imposition.page import ImpositionModulePage

#: 本模块的页面类（约定见 ``desktop.modules._page_factory``）。
PAGE = ImpositionModulePage

__all__ = ["PAGE", "ImpositionModulePage"]
