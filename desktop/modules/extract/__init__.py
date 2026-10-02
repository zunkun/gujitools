# -*- coding: utf-8 -*-
"""独立模块「图片提取」：与任务流程无关，选一个 PDF 直接提取全部页面为图片。"""

from desktop.modules.extract.page import ExtractModulePage

#: 本模块的页面类。⚠️ 名字必须是 ``PAGE``——壳层按 ``desktop.modules.<key>.PAGE``
#: 惰性取（见 ``desktop.modules._page_factory``），不认别的名字也不认别的路径。
PAGE = ExtractModulePage

__all__ = ["PAGE", "ExtractModulePage"]
