# -*- coding: utf-8 -*-
"""图片编辑器的**全部模块级常量**（含工具表 :data:`TOOLS`）。

从 ``image_editor.py`` 拆出（2026-10-07），只放常量，不放逻辑。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

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
#: 让"这里能拖"看得见（用户 20:28 定）。
#: 统一变换的手柄按语义取光标：方框=方向缩放、菱形=沿边切变
#: （Split 光标正好是"沿线滑动"的样子）、透视=四向移动。
HOVER_CURSORS = {
    "l": Qt.CursorShape.SizeHorCursor,
    "r": Qt.CursorShape.SizeHorCursor,
    "t": Qt.CursorShape.SizeVerCursor,
    "b": Qt.CursorShape.SizeVerCursor,
    "tl": Qt.CursorShape.SizeFDiagCursor,
    "br": Qt.CursorShape.SizeFDiagCursor,
    "tr": Qt.CursorShape.SizeBDiagCursor,
    "bl": Qt.CursorShape.SizeBDiagCursor,
    # 切变菱形：左右边沿线上下滑（SplitV）、上下边沿线左右滑（SplitH）
    "s_l": Qt.CursorShape.SplitVCursor,
    "s_r": Qt.CursorShape.SplitVCursor,
    "s_t": Qt.CursorShape.SplitHCursor,
    "s_b": Qt.CursorShape.SplitHCursor,
    # 透视小菱形
    "p_tl": Qt.CursorShape.SizeAllCursor,
    "p_tr": Qt.CursorShape.SizeAllCursor,
    "p_br": Qt.CursorShape.SizeAllCursor,
    "p_bl": Qt.CursorShape.SizeAllCursor,
    "center": Qt.CursorShape.SizeAllCursor,
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
    ("transform", FIF.MOVE, "统一变换"),
    ("distort", FIF.BRUSH, "扭曲"),
    ("erase", FIF.ERASE_TOOL, "擦除"),
    ("text", FIF.FONT, "文字"),
)


# ======================================================================
# 统一变换（GIMP「Unified Transform」口径）
#
# 手柄词汇表——**方框=缩放、菱形=切变、角上的小菱形=透视**（GIMP 文档
# 原文："Diamonds for shearing. Squares for scaling. Small diamonds for
# changing perspective, in large squares for Scaling."）：
#
#   * 四角 ``tl/tr/br/bl``          大方框  → **双轴缩放**（锚对角）
#     四角内侧 ``p_tl/p_tr/p_br/p_bl`` 小菱形 → **透视**（只挪这一个角）
#   * 四边中点 ``t/r/b/l``          方框    → **单轴缩放**（锚对边）
#   * 边上 ``s_<边><0|1>``          菱形    → **切变**（沿边拖）
#   * 框内拖 = 移动、框外拖 = 绕轴心旋转、轴心圆点 = 移动轴心
#
# 透视小菱形**与角方框同心**（``PERSP_INSET_VIEW_PX == 0``，用户 2026-10-09
# 口径：「四个边角的菱形要在方块正中心」）。同心之后"角点归谁"改由**半径**分：
# 离角点 ≤ ``PERSP_HIT_VIEW_PX`` 是透视，再往外到 ``CORNER_HIT_VIEW_PX`` 的
# 方形环带仍是双轴缩放 ⇒ 两类手柄仍互不抢（见 ``_hit_transform``）。
# ======================================================================

#: 四角（双轴缩放）
CORNER_HANDLES = ("tl", "tr", "br", "bl")
#: 四边中点（单轴缩放，用户口径里的"中型方框 C"）
SIDE_HANDLES = ("t", "r", "b", "l")
#: 边上的切变菱形：**每边恰好 1 个**（用户 2026-10-09 定：一张图共 4 个切变菱形）。
#: ⚠️ 以前是每边 2 个（1/4 与 3/4 各一）——用户明确只要 1 个，且位置在
#: **¾ 处**、靠近该边**顺时针方向的那个顶点**（见 SHEAR_AT 的长注释）。
SHEAR_HANDLES = tuple(f"s_{edge}" for edge in ("t", "r", "b", "l"))
#: 角内侧的透视小菱形
PERSP_HANDLES = tuple(f"p_{key}" for key in CORNER_HANDLES)

#: 切变菱形沿边的位置（比例口径：0 = 该边的**起点角**、1 = 终点角）。
#:
#: 用户 2026-10-09 口径原话：「四条边各有一个切变小菱形，这些小菱形都在 3/4 处，
#: 左右 y 方向不同，上下 x 方向坐标不同，我的意思是都是靠近四边顶点的顺时针
#: 方向」。四条边的参数化起点这样取（保证 ¾ 落在**顺时针方向那个顶点**附近）：
#:
#:   ``t`` 左边→右边（0=tl）  ``r`` 上边→下边（0=tr）
#:   ``b`` 右边→左边（0=br）  ``l`` 下边→上边（0=bl）
#:
#: 于是：上边菱形偏右（近 tr）、右边偏下（近 br）、下边偏左（近 bl）、
#: 左边偏上（近 tl）——**绕一圈正好是顺时针**，与用户给的那张边示意图一致。
SHEAR_AT = 0.75

#: 边的参数化起点角（``SHEAR_AT`` 的比例就沿这条边量）。
#: ⚠️ 与 ``transform._EDGE_UV`` 的 "起点" 必须一致，否则画在这里、算在那里。
SHEAR_FROM_CORNER = {"t": "tl", "r": "tr", "b": "br", "l": "bl"}

#: 边中方框/切变菱形的视觉尺寸（视图像素）。
#: ⚠️ 切变菱形 2026-10-09 由 11 放大到 **16**：用户报"菱形太小点不着"。
#: 它比边中方框（12）大一圈，是为了在细边上也好瞄（形状本身就是语义，
#: 大一点不改变"菱形=切变"的读法）。
#: ⚠️ 2026-10-09 第二版：边中方框 12 → **16**（用户「四边中间的拉伸方块也
#: 大一些」），与切变菱形**同尺寸**——两类手柄靠形状区分，不靠大小。
SIDE_VIEW_PX = 16.0
#: 切变菱形的视觉半对角线（视图像素）
SHEAR_VIEW_PX = 16.0
#: 角上方框的视觉边长（视图像素）——比边上的方框大一圈，**为了把透视小菱形
#: 整个兜在里面**（"大方框里嵌个小菱形"就是 GIMP 的角手柄样子）。
#: ⚠️ 2026-10-09 由 24 放到 **28**：菱形改成**同心**之后（见
#: ``PERSP_INSET_VIEW_PX``）两边得留出均匀边距，24 的话 22 宽的菱形几乎顶到框边。
CORNER_VIEW_PX = 28.0
#: 透视小菱形的视觉半对角线，以及它沿**框内对角线**向里挪多远（视图像素）。
#: ⚠️ 2026-10-09 由 7 放大到 **11**（用户报"四角被嵌套的菱形太小，无法选中"），
#: 同日再放大到 **16**（用户「菱形大一些」）——现在与切变菱形同尺寸，
#: **四类手柄里的菱形都是一样大**。角上方框 28 ⇒ 16 宽的菱形四周各留 6px。
PERSP_VIEW_PX = 16.0
#: 透视小菱形相对角点的偏置（视图像素）——**0 = 与角方框同心**（用户
#: 2026-10-09 口径）。以前是 8（向框内偏），那时靠"错开"来避免两类手柄抢；
#: 现在改成同心、靠命中半径分（见 ``PERSP_HIT_VIEW_PX`` 的注释）。
#: 保留这个开关而不是删掉，是为了日后想微调偏心时只改一个数。
PERSP_INSET_VIEW_PX = 0.0

#: 手柄命中半径（视图像素）——按"离手柄多远算抓住"判，不随缩放变。
#: ⚠️ 2026-10-09 由 7 提到 **9**：边中方框长到 16（半幅 8）之后，"点到方框
#: 就算"的手感得跟着长，否则方框的四角反而点不着。裁剪/收边共用它。
HANDLE_HIT_VIEW_PX = 9.0
#: 角方框的命中半边长（视图像素的方形判定）。⚠️ 视觉半边长是
#: ``CORNER_VIEW_PX / 2 = 14``，命中取 13 让手感"点到方框就算"。
CORNER_HIT_VIEW_PX = 13.0
#: 切变菱形的命中半径。⚠️ 比通用半径大一圈：菱形在细边上，手感要"一按就着"。
SHEAR_HIT_VIEW_PX = 10.0
#: 透视小菱形的命中半径。⚠️ 菱形与角点**同心**（``PERSP_INSET_VIEW_PX == 0``）
#: 之后，"角点归谁"就由半径分：≤ 本值 ⇒ 透视，往外到 ``CORNER_HIT_VIEW_PX``
#: 的方形环带 ⇒ 双轴缩放。⚠️ **正好等于菱形的视觉半径**
#: （``PERSP_VIEW_PX / 2 = 8``）⇒ 画出来那个菱形**整个**都落在命中圈里
#: （菱形的边距中心最近只有 ``8/√2 ≈ 5.7``），一点不浪费；同时仍
#: **小于** ``CORNER_HIT_VIEW_PX``（13），方框描边那一圈照旧归缩放。
PERSP_HIT_VIEW_PX = 8.0
#: 边手柄（方框/菱形）生效所需的最小边长（视图像素）：
#: 框在屏幕上太小的时候只剩角手柄 + 框内移动，否则一按就误抓切变
EDGE_HANDLE_MIN_VIEW_PX = 56.0

#: 变换选项：插值（烘焙时的像素重采样方式）
#: ``smooth`` 保留在表里给旧调用方，但界面上用 GIMP 的四档
INTERPOLATIONS = (
    ("无光晕", "nohalo"),
    ("线性", "linear"),
    ("立方", "cubic"),
    ("最近邻", "nearest"),
)
INTERPOLATION_DEFAULT = "nohalo"
#: 剪裁：调整（画布跟着内容长） / 裁剪到原画布 / 裁剪到原比例
CLIPPINGS = (
    ("调整", "adjust"),
    ("裁剪到原画布", "clip"),
    ("裁剪到原比例", "aspect"),
)
CLIPPING_DEFAULT = "adjust"
#: 方向：正常（向前，内容动）/ 校正（向后，按反向矩阵烘焙——
#: 扫描件拍歪了把它"掰正"的用法）
DIRECTIONS = (
    ("正常（向前）", "forward"),
    ("校正（向后）", "backward"),
)
DIRECTION_DEFAULT = "forward"

#: 参考线（变换框内的构图辅助线）
GUIDES = (
    ("无", "none"),
    ("三分构图法", "thirds"),
    ("五分构图法", "fifths"),
    ("黄金分割", "golden"),
    ("对角线", "diagonal"),
)
#: 各参考线模式在框内的**沿线比例**（u/v 各一套）
GUIDE_RATIOS = {
    "thirds": (1.0 / 3.0, 2.0 / 3.0),
    "fifths": (0.2, 0.4, 0.6, 0.8),
    "golden": (0.382, 0.618),
}
#: 参考线默认**五分构图**（用户 2026-10-09 定）。
GUIDE_DEFAULT = "fifths"

#: 「限制 (Shift)」的五个动作（勾选 = 拖动时套用该约束）
CONSTRAIN_OPS = ("move", "scale", "rotate", "shear", "perspective")
#: 「从轴心 (Ctrl)」的三个动作
PIVOT_OPS = ("scale", "shear", "perspective")
#: 预览不透明度（%）范围与默认值
PREVIEW_OPACITY_DEFAULT = 100

#: 右侧参数面板宽度（逻辑像素）。控件按**竖排**堆，够放一条滑杆 + 数字。
PANEL_WIDTH = 300

#: 右侧「编辑历史」列表高度（逻辑像素）——步骤多了在里面滚动。
HISTORY_HEIGHT = 150

#: 统一变换**预览**的像素预算。拖动时浮层每帧都要重采样一次，预算越小越跟手；
#: 0.5 Mpx 下线性采样一帧约 30 ms（12 MP 整幅预览曾要 838 ms/帧，拖不动）。
#: 松手后会按用户选的插值再出一帧，所以预览的小降采样不影响最终质量。
TRANSFORM_PREVIEW_PIXELS = 500_000

#: 画布**棋盘格**（"这里是空的"的通用视觉约定）。方格边长按**设备像素**，
#: 不随缩放变；**只画在「原图矩形」里**（见 ``EditorCanvas.paintEvent``）。
CHECKER_STEP = 9
CHECKER_LIGHT = QColor("#f4f5f7")
#: ⚠️ 2026-10-09 由 ``#d9dce1`` 压深一档：画布底改成更浅的 ``CANVAS_OUTSIDE``
#: 之后，原来的暗格(217)和底色几乎同亮度 ⇒ 格子"糊"进背景看不出。压到 205
#: 才让"空出来的那块"仍然是清楚的棋盘。
CHECKER_DARK = QColor("#cdd4db")

#: 画布**版面底色**——「原图矩形」**之外**那一圈（用户 2026-10-09 口径：
#: 「背景是灰色的，原本图片大小位置固定是条纹格子」）。图外素底、图内条纹格，
#: 一眼分得出"哪块是这张图的地盘"。
#: ⚠️ 2026-10-09 两次调整：先是 ``INK_FAINT``(#8B949D)，用户报「灰色太突兀」
#: ——中灰压在浅色 UI 上反差过大；换成 ``BORDER_STRONG``(#C9D1D8) 仍偏灰；
#: 现在定在 **#e3e8ed**：接近窗口底(``ui.theme.CANVAS`` #F3F5F7) 但深一档，
#: 不抢戏；与图片(白纸)靠明度分、与图内棋盘格靠格线分。
CANVAS_OUTSIDE = QColor("#e3e8ed")

#: 历史里第 0 个节点（打开编辑器时的状态）的文案。
HISTORY_ORIGIN_LABEL = "打开"

#: 各功能写进历史时的步骤名（``_push_undo`` 的 label）。
STEP_CROP = "裁剪"
STEP_TRANSFORM = "变换"
STEP_ERASE = "擦除"
STEP_DISTORT = "扭曲"
STEP_TEXT = "文字"
STEP_RESET = "还原"
#: 统一变换面板上的翻转（不是独立工具，但也是一步）
STEP_FLIP = "翻转"
