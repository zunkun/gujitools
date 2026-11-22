# -*- coding: utf-8 -*-
"""拼版页清单（原 ``page_list.py`` 拆包）：对外名字在此**显式重导出**。

拆包前 ``from desktop.components.imposition.page_list import X`` 能取到的
类与辅助（含测试引用的私有 ``_PageEntry`` / ``_AddEntry`` / ``_SelectBar``），
这里原样保留——外部 import 路径与名字不变。
"""

from __future__ import annotations

from desktop.components.imposition.page_list.entries import _AddEntry, _PageEntry
from desktop.components.imposition.page_list.list_widget import ImpositionPageList
from desktop.components.imposition.page_list.select_bar import _SelectBar
from desktop.services.imposition import cn_page_label

__all__ = [
    "ImpositionPageList",
    "_PageEntry",
    "_AddEntry",
    "_SelectBar",
    "cn_page_label",
]
