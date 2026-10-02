# -*- coding: utf-8 -*-
"""独立模块「去底色」：与任务流程无关，选一个图片目录直接批量去底色。"""

from desktop.modules.rembg.page import RembgModulePage

#: 本模块的页面类（约定见 ``desktop.modules._page_factory``）。
PAGE = RembgModulePage

__all__ = ["PAGE", "RembgModulePage"]
