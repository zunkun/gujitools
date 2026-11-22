# -*- coding: utf-8 -*-
"""详情页顶部步骤条：编号/对勾徽标 + 连接箭头 + 主副标题。

设计要点：
- 每一步 = 圆形徽标（编号或 ✓）+ 标题 + 状态副标题，用形状表达"第几步"；
- 步骤之间用带箭头的连接线连起来，已完成的线段变色，直观表达先后顺序；
  连接线由 **StepBar 底层统一画**、从节点框**后面**穿过——节点框有实底
  （``_StepItem.pill`` / 拼版节点自己画），框内那截线被遮住，线自然"从
  框后面出发"，不用再对齐框边缘；
- 节点框：所有节点**同一套外观**——SURFACE 实底 + 浅色描边 + 高亮底色，
  选中/当前只有底色变化、**没有边框差异**（用户 2026-09-30：其他节点即使
  选中也没有 border，只有背景色；拼版节点生效与否样式统一）；
- 状态色：未执行（灰）· 执行中（蓝）· 成功（绿）· 失败（红）· 已中断（橙）；
- 整步可点击切换，带悬停底色，避免按钮样式的标签堆叠感。

对外接口（兼容旧调用）：
- ``buttons``：StepItem 列表（长度 = 步骤数）；
- ``_completed``：已完成步骤下标集合；
- ``set_steps`` / ``set_current`` / ``mark_completed`` / ``current_changed``。

⚠️ 2026-11-22 起按职责拆成子包：常量/配色 ``constants``、节点控件
``widgets``、连接线与绕行绘制 ``drawing``、主体 ``bar``。本 ``__init__`` 只做
重导出——既有 ``from desktop.components.step_bar import X`` 全部不变；子模块
之间不要反过来导入本包（会形成循环）。
"""

from desktop.components.step_bar.bar import StepBar
from desktop.components.step_bar.constants import (
    ACCENT,
    AMBER,
    GRAY,
    GREEN,
    RED,
    UNMAPPED_DETAIL,
    _BADGE,
    _BYPASS_CLEAR,
    _CONNECTOR_W,
    _NODE_MIN_W,
    _STATUS_COLORS,
    _STATUS_LABELS,
)
from desktop.components.step_bar.drawing import _rounded_polyline
from desktop.components.step_bar.widgets import (
    StepItem,
    _Connector,
    _ElidedLabel,
    _ImpositionNode,
    _StepBadge,
)

__all__ = [
    "StepBar",
    "StepItem",
    "ACCENT",
    "AMBER",
    "GRAY",
    "GREEN",
    "RED",
    "UNMAPPED_DETAIL",
    "_BADGE",
    "_BYPASS_CLEAR",
    "_CONNECTOR_W",
    "_Connector",
    "_ElidedLabel",
    "_ImpositionNode",
    "_NODE_MIN_W",
    "_STATUS_COLORS",
    "_STATUS_LABELS",
    "_StepBadge",
    "_rounded_polyline",
]
