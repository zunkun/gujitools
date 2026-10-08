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

#: 扭曲笔刷默认参数（图片像素 / 百分比）
DISTORT_SIZE, DISTORT_HARDNESS = 117, 50
DISTORT_STRENGTH, DISTORT_SPACING = 50, 10

#: 实时预览的像素预算与瓦片尺寸（预览按此降采样，逐帧只重渲染脏瓦片）
DISTORT_PREVIEW_PIXELS = 2_000_000
DISTORT_PREVIEW_TILE = 128

#: 单帧最多上传多少块预览瓦片——鼠标跳一下会一次脏掉很多块，
#: 全传完就是一次可感知的卡顿（剩下的留给下一帧）。
DISTORT_PREVIEW_TILES_PER_TICK = 16

#: 单帧最多**重渲染**多少个预览像素。脏区可以一下子很大（鼠标猛地一跳、
#: 或系统把一串 move 并成一个事件），一次渲染完就是一帧卡顿；超预算的部分
#: 整段留给下一次 tick，于是每帧成本恒定。实测局部脏区 ~3 千像素约 0.8 ms。
DISTORT_PREVIEW_RENDER_PIXELS = 60_000

#: 提交时同步渲染的像素上限；超过则移入后台线程 + 进度对话框。
#: 实测 12 MP 图整页（8.9 Mpx）三次插值约 9 秒，局部笔划（0.1 Mpx）0.2 秒。
DISTORT_SYNC_RENDER_PIXELS = 4_000_000

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

#: 顶部**功能选择**条：（键, 图标, 中文名）。切功能 = 换右侧参数面板。
TOOLS = (
    ("crop", FIF.CUT, "裁剪"),
    ("transform", FIF.MOVE, "变换"),
    ("distort", FIF.BRUSH, "扭曲"),
    ("erase", FIF.ERASE_TOOL, "擦除"),
    ("text", FIF.FONT, "文字"),
)

#: 右侧参数面板宽度（逻辑像素）。控件按**竖排**堆，够放一条滑杆 + 数字。
PANEL_WIDTH = 300

#: 右侧「编辑历史」列表高度（逻辑像素）——步骤多了在里面滚动。
HISTORY_HEIGHT = 150

#: 历史里第 0 个节点（打开编辑器时的状态）的文案。
HISTORY_ORIGIN_LABEL = "打开"

#: 各功能写进历史时的步骤名（``_push_undo`` 的 label）。
STEP_CROP = "裁剪"
STEP_TRANSFORM = "变换"
STEP_ERASE = "擦除"
STEP_DISTORT = "扭曲"
STEP_TEXT = "文字"
STEP_RESET = "还原"
