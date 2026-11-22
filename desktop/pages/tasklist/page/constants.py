# -*- coding: utf-8 -*-
"""任务列表页的文案常量。"""

from __future__ import annotations

from desktop.ui import theme as T

# 状态文案统一取自 ui.theme，避免各处各自维护一份
STATUS_LABELS = T.STATUS_LABELS

#: 页头副标题的默认文案；导入期间会被「正在导入 · …」临时顶掉（见 _show_import_status）
HEADER_SUBTITLE = "创建任务后按流程节点依次处理"
