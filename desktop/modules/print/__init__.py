# -*- coding: utf-8 -*-
"""独立模块「生成 PDF」：与任务流程无关，选一批成品图直接合成 PDF。"""

from desktop.modules.print.page import PrintModulePage

#: 本模块的页面类（约定见 ``desktop.modules._page_factory``）。
PAGE = PrintModulePage

__all__ = ["PAGE", "PrintModulePage"]
