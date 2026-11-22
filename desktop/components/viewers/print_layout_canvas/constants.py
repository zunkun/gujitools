# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module
"""``print_layout_canvas`` 的配色、手柄与旋转常量（各子模块共用）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

# 纸张恒为白底（PDF 纸张即白）；边框/控件用中性色，深浅主题下都清楚
PAGE_COLOR = QColor("#ffffff")
PAGE_BORDER = QColor("#cbd2dc")
# 命中 skip_pages 的页：成品里没有它，编辑时给灰底明确提示（与效果预览同色）
SKIP_COLOR = QColor("#eceff3")
SKIP_INK = QColor("#98a2b3")
IMAGE_STROKE = QColor("#2563eb")
HANDLE_STROKE = QColor("#2563eb")
HANDLE_FILL = QColor("#ffffff")
HANDLE_RADIUS = 6  # 手柄半径（控件像素）

# 手柄光标：0~3 = 四角（左上/右上/右下/左下），4~7 = 四边（上/右/下/左）。
# ⚠️ 四边手柄**只在取消「原比例缩放」时出现**（那时才允许单方向拉伸）。
_CORNER_CURSORS = [
    Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
    Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
]
_EDGE_CURSORS = [
    Qt.CursorShape.SizeVerCursor, Qt.CursorShape.SizeHorCursor,
    Qt.CursorShape.SizeVerCursor, Qt.CursorShape.SizeHorCursor,
]
_HANDLE_CURSORS = _CORNER_CURSORS + _EDGE_CURSORS

#: 边手柄索引 → 受影响的边
_EDGE_BY_HANDLE = {4: "top", 5: "right", 6: "bottom", 7: "left"}

#: 框的最小边长（mm）：拖到两边重合会让命中判定与后续缩放都失效
MIN_RECT_MM = 2.0

#: 画布贴图底图的降采样上限（最长边）。
#:
#: 源图常见 3000~6000px，而画布把整页塞进可视区后每毫米只剩 ~2px：直接
#: `drawImage` 是一次 8~10 倍缩小的**最近邻**采样，古籍的细笔画/淡墨会被
#: 跳采样（用户报「rembg 图放大看还行，PDF 排版页却发虚」）。先把源图平滑
#: 缩到这个上限（一次性、换图才重算），贴图时再平滑缩一档——两档温和缩放
#: 质量接近理论最优；而且每帧只对 ≤2000px 的小图采样，拖框不会掉帧。
DISPLAY_IMAGE_EDGE = 2000

#: 边命中带（控件像素）：距边线这么近就算"拖这条边"，**不限边中点**。
#: 角仍是小圆点邻域（角落优先按对角缩放处理）。
EDGE_HIT_PX = 6

#: 框外上方的旋转钮（与「图片拼版」同款，用户 2026-11-02）：
#: 距框上边的距离 / 圆钮半径 / 命中半宽（比画出来的圆大一圈，点太小不好抓）。
ROTATE_KNOB_GAP = 26
ROTATE_KNOB_RADIUS = 6
ROTATE_KNOB_HIT = ROTATE_KNOB_RADIUS + 8
#: 弧形箭头画在圆钮**外侧**（用户 2026-11-02：圆里那圈小弧看不清）：
#: 距圆边的半径增量 / 起点角 / 跨度 / 箭头臂长。
#: Qt 角度 0° = 3 点方向；跨度取**负值 = 顺时针**（用户要的旋转方向）；
#: 缺口留在下方，避开引线。
ROTATE_ARC_GAP = 5.0
ROTATE_ARC_START = 210
ROTATE_ARC_SPAN = -240
ROTATE_ARC_BARB = 4.0
#: 旋转吸附步长（按住 Shift）
SNAP_DEGREES = 15.0
