# -*- coding: utf-8 -*-
"""拼版画布的常量：配色、手柄/旋转钮几何、缩放手感、贴图采样档位。"""

from __future__ import annotations

from desktop.components.imposition.canvas._qt import QColor, Qt

#: 背景恒白（用户口径：拼版不需要纸张，白底就行）
PAGE_COLOR = QColor("#ffffff")
#: 选中框是**虚线**（用户 2026-09-30：默认不显示蓝边，按住操作时才出现虚线）
FRAME_STYLE = Qt.PenStyle.DashLine

FRAME_COLOR = QColor("#0E7C8B")
HANDLE_STROKE = QColor("#0E7C8B")
HANDLE_FILL = QColor("#ffffff")
HANDLE_RADIUS = 5
ROTATE_KNOB_RADIUS = 6
ROTATE_KNOB_GAP = 26  # 旋转钮距框上边的距离（控件像素）
#: 旋转钮的命中半宽（比画出来的圆大一圈）：它是图片**外面**唯一的旋转抓手
#: （用户 2026-10-23：「可以在图片外面……鼠标左键旋转操作」），点太小不好抓
ROTATE_KNOB_HIT = ROTATE_KNOB_RADIUS + 8
#: 弧形箭头画在圆钮**外侧**（用户 2026-11-02：圆里那圈小弧看不清）：
#: 距圆边的半径增量 / 起点角 / 跨度 / 箭头臂长。
#: Qt 角度 0° = 3 点方向；跨度取**负值 = 顺时针**（用户要的旋转方向）；
#: 缺口留在下方，避开引线。
ROTATE_ARC_GAP = 5.0
ROTATE_ARC_START = 210
ROTATE_ARC_SPAN = -240
ROTATE_ARC_BARB = 4.0

_CORNER_CURSORS = [
    Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
    Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
]
_EDGE_CURSORS = [
    Qt.CursorShape.SizeVerCursor, Qt.CursorShape.SizeHorCursor, Qt.CursorShape.SizeVerCursor, Qt.CursorShape.SizeHorCursor,
]
_HANDLE_CURSORS = _CORNER_CURSORS + _EDGE_CURSORS

#: 边手柄索引 → 受影响的边
_EDGE_BY_HANDLE = {4: "top", 5: "right", 6: "bottom", 7: "left"}

#: 框的最小边长（合成像素）：拖到两边重合会让命中判定与后续缩放都失效
MIN_RECT = 4.0
#: 边命中带（控件像素）：距边线这么近就算"拖这条边"，不限边中点
EDGE_HIT_PX = 6

#: 旋转吸附步长（按住 Shift）
SNAP_DEGREES = 15.0

#: **红色对齐线**（用户 2026-09-30：左右两张文本框中心的垂直红色虚线，无论
#: 何时都显示——整体旋转时它就是"转没转歪"的对比基准）
SPINE_COLOR = QColor("#E02020")

#: **成品截图范围框**（用户 2026-09-30：整版旋转时要能看到"截图框"——两图
#: 上下左右四个方向最外侧点组成的虚线框）。与产出图的紧裁范围
#: （``services.imposition.page_bounds``）同一套几何，恒显。
CROP_COLOR = QColor("#5F6368")

#: 滚轮缩放步长（每格 120 的角度增量算一格；与预览弹窗同款手感）
WHEEL_ZOOM_STEP = 1.15
#: 滚轮缩放倍率边界（相对"适配可视区"的基准倍率）：太小会找不到图，
#: 太大缩放期间像素化的图没有参考价值
ZOOM_MIN = 0.2
ZOOM_MAX = 8.0

#: 画布贴图底图的**采样档位**（最长边像素）。源图常见几千像素，而画布把整页
#: 塞进可视区后每张图只剩几百像素：直接 drawImage 是一次大比例双线性缩小，
#: 细节被跳采样（用户 2026-10-24 报「预览页发虚」）。按这几档预缩（每档折半，
#: 见 ``utils...smooth_downscale``），缩放倍率跨档时才重算一次，同档内拖动/
#: 旋转零重采样。超过最大档就直接用原生（再缩不如让 Qt 自己缩）。
DISPLAY_EDGE_STEPS = (600, 1200, 2400)
#: 滚轮连发期间的重绘合并窗口：窗口内最多重绘一帧（约 33fps）
WHEEL_REPAINT_MS = 30
