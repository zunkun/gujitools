# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""统一变换的手柄词汇表常量（从 ``canvas/transform.py`` 拆出）。"""
from __future__ import annotations

from PySide6.QtCore import QPointF

from ...consts import CORNER_HANDLES, PERSP_HANDLES, SHEAR_HANDLES, SIDE_HANDLES


#: 角的参数坐标（u/v ∈ [0, 1]，原点 = 选区左上角）——手柄位置唯一来源
_CORNER_UV = {"tl": (0.0, 0.0), "tr": (1.0, 0.0),
              "br": (1.0, 1.0), "bl": (0.0, 1.0)}
#: 边的参数化：沿线比例 s（0 = 起点角、1 = 终点角）→ (u, v)
_EDGE_UV = {
    "t": lambda s: (s, 0.0),
    "b": lambda s: (s, 1.0),
    "l": lambda s: (0.0, s),
    "r": lambda s: (1.0, s),
}
#: 边 → 两端的角（命中带与切变方向用）
_EDGE_CORNERS = {"t": ("tl", "tr"), "r": ("tr", "br"),
                 "b": ("br", "bl"), "l": ("bl", "tl")}
#: 角的两个相邻角——透视小菱形沿"框内对角线"偏置
_CORNER_NEIGHBOURS = {"tl": ("tr", "bl"), "tr": ("tl", "br"),
                      "br": ("tr", "bl"), "bl": ("tl", "br")}
#: 单轴缩放的锚点：抓某条边时**对边**不动（在选区局部坐标里）
_SIDE_ANCHOR = {
    "l": lambda rect: QPointF(rect.right(), rect.center().y()),
    "r": lambda rect: QPointF(rect.left(), rect.center().y()),
    "t": lambda rect: QPointF(rect.center().x(), rect.bottom()),
    "b": lambda rect: QPointF(rect.center().x(), rect.top()),
}

#: 「从轴心 (Ctrl)」可用的动作；「限制 (Shift)」可用的动作
_PIVOT_KEYS = ("scale", "shear", "perspective")
_CONSTRAIN_KEYS = ("move", "scale", "rotate", "shear", "perspective")

#: 算"节点"的命中名（悬停/点选都高亮它们；整条边带与框内不算节点）
_HANDLE_HITS = frozenset(
    CORNER_HANDLES + SIDE_HANDLES + SHEAR_HANDLES + PERSP_HANDLES)
