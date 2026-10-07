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
#: 操作"（图钉/笼把手/四角要能往图外拖，且图边不贴控件边缘才好点）。
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

#: 「变形」网格格距档位（图片像素）——越小网格越密、形变越细腻、解方程越慢。
#: 档位按**真实像素**给，跟图片尺寸无关：20px 一格在 4000px 页面上是
#: 200×150 格 ≈ 3 万顶点（解算 + 采样都在亚秒级），80px 一格则只有 2 千顶点。
MESH_DENSITY_CHOICES = ((20.0, "细（20px 一格）"),
                        (40.0, "标准（40px 一格）"),
                        (80.0, "粗（80px 一格）"))

#: 网格格距默认档（图片像素）。40px 是清晰度与耗时的折中：古籍页码常见
#: 2000~4000px，40px 一格 = 50~100 格/边，足够表现褶皱的连续弯曲。
MESH_DENSITY_DEFAULT = 40.0

#: 进「变形」时图片占视口的比例——**四周留出可操作空间**。
#: 用户 2026-10-01：图片宽高不要铺满整个操作区（图钉要能往图外拖，
#: 越靠边越需要留白；也免得图钉贴着控件边缘不好点）。
DEFORM_FIT_RATIO = 0.8

#: 图钉的视觉直径与命中半径（视图像素）——命中圈比视觉略大，好点。
PIN_NODE_VIEW_PX = 9.0

PIN_HIT_VIEW_PX = 11.0

#: 「校正」四角手柄的视觉半径与命中半径（视图像素）。
QUAD_HANDLE_VIEW_PX = 8.0

QUAD_HIT_VIEW_PX = 12.0

#: 四角手柄画成方块还是圆点（方块更像"框角"，且与图钉圆点区分开）。
#: 「校正」目标矩形的宽高比档位：外接框 / 保持原比例（对边平均长）。
RECTIFY_RATIO_CHOICES = (("bbox", "外接框（尺寸最省）"),
                         ("area", "保持原比例（不变形）"))

RECTIFY_RATIO_DEFAULT = "area"

#: 拖动中**像素预览**的工作分辨率上限（像素）。
#: 形变是逐像素重映射：整页 4000×3000 全分辨率一次要 **3~10 秒**（实测
#: 见 ``utils/puppet_warp`` 的模块文档）。ARAP 的位移场缓慢衰减、整图
#: 96~98% 受影响，所以预算按**整幅图**面积算（裁局部框只省 ~4%）。
#: 20 万像素 ≈ 0.2s，配 :data:`DEFORM_PREVIEW_INTERVAL` 的节拍让图钉
#: （覆盖层）始终跟手。
#:
#: ⚠️ 这个值是"跟手"的第一道闸门。逐像素重映射的实测成本 ≈ **0.7 µs/像素**
#: （重心插值 + 4 点双线性 + 写回；numpy 内存带宽受限，已到实测下界），所以
#: 20 万 ≈ 140ms/帧（偏卡）、12 万 ≈ 72ms（跟手）、8 万 ≈ 43ms（顺滑）。
#: 取 12 万：4000×3000 拖动帧时间压到 ~80ms 量级。画质上形变场是低频的、
#: 预览图再由 Qt 平滑放大，肉眼与原图无差别（早期取 20 万是按"0.2s"估的，
#: 实测偏乐观，正是真机卡顿的来源）。
DEFORM_PREVIEW_PIXELS = 120_000

#: **松手后**重算预览的分辨率上限（像素）。松手是"停下来看结果"的时刻，
#: 按屏幕分辨率算（见 :func:`cage_preview_scale`）就够清楚，但别放开到
#: 全分辨率——整页在 100% 缩放下那是秒级。250 万像素 ≈ 2s。
DEFORM_PREVIEW_SETTLE_PIXELS = 2_500_000

#: 像素预览重算的最小间隔（秒）。一次重映射 ~0.07s 量级，不节流的话每个
#: move 事件都会阻塞界面；节流到略大于单帧成本，既不让队列堆积、又能
#: 跟上鼠标（图钉的**覆盖层**不受此限，每帧都跟手）。
DEFORM_PREVIEW_INTERVAL = 0.08

# ---- 「变换笼」（GIMP 口径）常量 ----
#: 每边默认把手数（矩形笼 = 4 角 + 每边 N 个中点）。
#: 「变换笼」的手柄（把手）视觉半径与命中半径（视图像素）。
CAGE_HANDLE_VIEW_PX = 8.0

CAGE_HIT_VIEW_PX = 12.0

#: 笼边线的命中带宽（视图像素）——边缘本身可拖，用于整体移动笼。
CAGE_EDGE_BAND_VIEW_PX = 8.0

#: 拖动中**像素预览**的分辨率上限（像素）。
#: 笼形变是 RBF 位移场，**局部**（影响半径外逐字节原样，见
#: ``utils.cage_warp``），所以工作量远小于整幅——预算给得比「变形」宽。
CAGE_PREVIEW_PIXELS = 250_000

#: 松手后重算预览的分辨率上限（像素）。
CAGE_PREVIEW_SETTLE_PIXELS = 2_500_000

#: 预览重算的最小间隔（秒）。
CAGE_PREVIEW_INTERVAL = 0.08

#: 进「变换笼」时图片占视口的比例——四周留白，把手要能往图外拖。
CAGE_FIT_RATIO = 0.8

#: 「变换笼」每边把手数档位（4 角固定 + 每边 N 个中点）。
#: 越多越能做出连续的波浪形变，但把手密集时不好点。
CAGE_DENSITY_CHOICES = ((1, "稀疏（每边 1 个）"),
                        (2, "标准（每边 2 个）"),
                        (3, "密集（每边 3 个）"))

CAGE_DENSITY_DEFAULT = 2

#: 左侧工具栏：（键, 图标, 中文名）
TOOLS = (
    ("crop", FIF.CUT, "裁剪"),
    ("transform", FIF.MOVE, "变换"),
    ("deform", FIF.LAYOUT, "变形"),
    ("cage", FIF.TAG, "变换笼"),
    ("rectify", FIF.ZOOM, "校正"),
    ("erase", FIF.ERASE_TOOL, "擦除"),
    ("text", FIF.FONT, "文字"),
)
