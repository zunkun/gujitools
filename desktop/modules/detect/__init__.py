# -*- coding: utf-8 -*-
"""独立模块「检测文本框」：与任务流程无关，选一批图片直接检测内容框并导出坐标。"""

from desktop.modules.detect.page import DetectModulePage

#: 本模块的页面类（约定见 ``desktop.modules._page_factory``）。
PAGE = DetectModulePage

__all__ = ["PAGE", "DetectModulePage"]
