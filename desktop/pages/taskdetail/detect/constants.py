# -*- coding: utf-8 -*-
"""detect 子包共享常量（从原 ``detect.py`` 拆出）。"""

from __future__ import annotations
#: 信息条尾注：按本次框的来源（origin）标注。⚠️ `_apply_boxes` 与
#: `_show_boxes_info` 必须共用这一份——apply_boxes 的 info_text 也会写
#: 信息条，两处后缀不一致时后写的会覆盖先写的（曾丢过「（手动）」标记）。
ORIGIN_SUFFIX = {
    "manual": "（手动）",
    "auto": "",
    "fullpage": "（整页，未检测）",
}
