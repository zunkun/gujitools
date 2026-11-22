# -*- coding: utf-8 -*-
"""聚合任务创建面板的共享常量（见 :mod:`desktop.components.aggregate_create_panel`）。"""

from __future__ import annotations

#: 成员表格**每页最多**几行（用户 2026-11-18：「最多能 10 条一页显示，多余 10 条
#: 分页显示，但是没有 10 条不能占用 10 条高度」）。表格高度按**当前页实际行数**
#: 算（见 ``_fit_table_height``），不再是一个固定值。
MEMBER_PAGE_SIZE = 10

#: 表头高度（px）：算表格总高 = 表头 + 行数 × 行高。
MEMBER_HEADER_HEIGHT = 38

#: 默认起始节点：用户的典型场景是"各子任务拼版之后合并成一本书"。
DEFAULT_START_STAGE = "imposition"
