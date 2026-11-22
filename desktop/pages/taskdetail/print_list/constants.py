# -*- coding: utf-8 -*-
"""print_list 子包共享常量（从原 ``print_list.py`` 拆出）。"""

from __future__ import annotations

#: 「进入第四步」之后多久补生成待打印缩略图（毫秒）。
#: 见 :meth:`PrintListMixin._schedule_print_thumbs_warm`：这笔活只服务
#: 「管理图片」弹窗，不该记在"进页面"的账上。
PRINT_WARM_DELAY_MS = 200
