# -*- coding: utf-8 -*-
"""图片编辑器的**全部模块级常量**（含工具表 :data:`TOOLS`）。

从 ``image_editor.py`` 拆出（2026-10-07），只放常量，不放逻辑。
"""
from PySide6.QtCore import Qt

from qfluentwidgets import FluentIcon as FIF

#: 撤销栈深度（步）。每步是整图快照，大图下是拿内存换的。
UNDO_LIMIT = 12

#: 缩放范围（编辑器里放大只为对准细节，没有预览弹窗那套 100% 档位语义）
MIN_ZOOM, MAX_ZOOM = 0.05, 8.0

WHEEL_STEP = 1.15

#: 选区最小边（图片像素）——再小就是误点
MIN_RECT_EDGE = 4.0

#: 手柄的视觉尺寸（视图像素；换算成图片坐标时除以当前倍率）
HANDLE_VIEW_PX = 12.0

#: 边缘命中带宽度（视图像素，以边线为中心向内外各半）——整条边都能抓着
#: 向内拖，不只小方块（用户 20:18 定）
EDGE_BAND_VIEW_PX = 8.0

#: 悬停光标形态（按命中手柄）：边缘/角给对应的方向缩放光标，
#: 让"这里能拖"看得见（用户 20:28 定）
HOVER_CURSORS = {
    "l": Qt.CursorShape.SizeHorCursor,
    "r": Qt.CursorShape.SizeHorCursor,
    "t": Qt.CursorShape.SizeVerCursor,
    "b": Qt.CursorShape.SizeVerCursor,
    "tl": Qt.CursorShape.SizeFDiagCursor,
    "br": Qt.CursorShape.SizeFDiagCursor,
    "tr": Qt.CursorShape.SizeBDiagCursor,
    "bl": Qt.CursorShape.SizeBDiagCursor,
}

#: 松手后适配选区的视口占比（不填满，四周留白好抓边，用户 20:28 定）
SEL_FIT_RATIO = 0.8

#: 「适应窗口」时图片占视口的比例——**任何工具下都四周留白**。
#: 用户 2026-10-02：编辑区不要铺满整个界面，"上下都预留空白地方，方便后续
#: 操作"（图边不贴控件边缘才好点）。
#: 0.8 ⇒ 上下左右各留 ~10% 视口，正好是"顺手"的余量。
EDIT_FIT_RATIO = 0.8

#: 变换轴心圆点的视觉直径（视图像素）
PIVOT_VIEW_PX = 14.0

#: 旋转按住 Shift 时的角度吸附步（度）
ROTATE_SNAP_DEG = 15.0

#: 橡皮擦直径范围（图片像素）
ERASER_MIN, ERASER_MAX, ERASER_DEFAULT = 4, 160, 24

#: 插入文字字号范围（图片像素高）
TEXT_MIN, TEXT_MAX, TEXT_DEFAULT = 12, 240, 48

#: 文字常用色（古籍批注口径：黑墨/白粉/朱批/藏蓝/赭黄/黛绿）——一击即换的
#: 色块，**收在颜色选择器面板里**（用户 2026-10-01：色块不要散在选项行上）。
TEXT_SWATCHES = (
    ("黑墨", "#000000"),
    ("白粉", "#ffffff"),
    ("朱批", "#d32f2f"),
    ("藏蓝", "#1976d2"),
    ("赭黄", "#8d6e63"),
    ("黛绿", "#2e7d32"),
)

#: 左侧工具栏：（键, 图标, 中文名）
TOOLS = (
    ("crop", FIF.CUT, "裁剪"),
    ("transform", FIF.MOVE, "变换"),
    ("erase", FIF.ERASE_TOOL, "擦除"),
    ("text", FIF.FONT, "文字"),
)
