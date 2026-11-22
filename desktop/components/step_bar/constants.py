# -*- coding: utf-8 -*-
"""步骤条的共享常量与状态配色（见 :mod:`desktop.components.step_bar`）。"""

from __future__ import annotations

from desktop.ui import theme as T

# 状态色统一取自 ui.theme，保证与列表页状态胶囊一致
ACCENT = T.ACCENT
GREEN = T.SUCCESS
RED = T.DANGER
AMBER = T.WARNING
GRAY = T.INK_FAINT
#: 「图上画了、但还没有对应功能」的节点在步骤条上的副标题（2026-10-05）
UNMAPPED_DETAIL = "未接入"

# 状态 → (徽标填充, 徽标描边, 徽标文字, 标题色, 副标题色)
_STATUS_COLORS = {
    "pending": (T.SURFACE, "#C8C6C4", T.INK_SOFT, T.INK_SOFT, T.INK_FAINT),
    "running": (ACCENT, ACCENT, T.SURFACE, ACCENT, ACCENT),
    "success": (GREEN, GREEN, T.SURFACE, T.INK, GREEN),
    "failed": (RED, RED, T.SURFACE, RED, RED),
    "cancelled": (T.SURFACE, AMBER, AMBER, T.INK, AMBER),
}

_BADGE = 26  # 徽标直径
_CONNECTOR_W = 38  # 连接线宽度（含箭头）
_BYPASS_CLEAR = (
    28  # 绕行线上下竖线离拼版节点左右缘的距离（用户 2026-09-30：别贴着按钮拐弯）
)
# 所有节点的**统一默认宽度**（用户 2026-09-30：所有节点设置一个默认宽度，
# 生效/不生效、选择/未选择都不改变宽度——状态只表达在徽标与副标题上）。
# 只是下限：状态副标题更长时节点仍可以变宽（文字走省略号兜底）。
_NODE_MIN_W = 140

_STATUS_LABELS = {
    "pending": "未执行",
    "running": "执行中",
    "success": "成功",
    "failed": "失败",
    "cancelled": "已中断",
}
