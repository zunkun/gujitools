# -*- coding: utf-8 -*-
"""步骤元数据的共享常量：文件过滤串 / 后缀正则 / 自动下钻层数。"""

from __future__ import annotations

import re

#: 认得的图片后缀（选文件时的过滤串与"这是不是图片"的判断共用一份）
IMAGE_FILTER = "图片 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp)"
PDF_FILTER = "PDF/DjVu 文件 (*.pdf *.djvu *.djv)"

#: 从过滤串里抠后缀用的正则：``*.jpg`` → ``.jpg``
_SUFFIX_RE = re.compile(r"\*(\.[A-Za-z0-9]+)")

#: 「顶层找不到、自动往下钻」的最大层数（见 :meth:`StepSpec.nested_listing`）。
#:
#: 2 层是有来历的：图片提取模块的产物固定落在 ``<输出根>/<PDF名>/images/``
#: （``utils.pdf_extract.run_on_input_directory`` 的布局，与 CLI 同源），
#: 用户很自然会把这个**输出根目录**直接拖给「去底色」——那就是"下一层没有、
#: 再下一层有"。更深就没必要猜了。
AUTO_DESCEND_DEPTH = 2
