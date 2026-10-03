# -*- coding: utf-8 -*-
"""图片编辑弹窗：裁剪 / 擦除 / 插入文字（Win10 照片风格）。

从图片预览弹窗（``image_zoom_dialog``）的「编辑」按钮进入，编辑的是
**画布当前整分辨率图**（已含翻转/旋转）；「完成」后写回弹窗画布。宿主
给 ``save_back=True``（画布显示 1:1 对应真实文件）时，「完成」= 直接
**原子覆盖原图片文件**；虚拟预览（区域合成/打印重排/PDF 页）没有文件
可回写，维持"满意用「下载」落盘、翻页/关窗即丢弃"的旧行为。

五个工具的行为口径：

- **裁剪**：**默认选中整幅图**，沿四边/四角**任意位置**向内拖收边（整条
  边都是命中带，不只手柄小方块）、拖框中间移动；松手后**视图自动适配新
  选区**（选区变小就放大查看）。不做截图式"拖拽画框"——那是截图的交互，
  裁剪的语义是"从原图里收出想要的部分"（用户 20:05 定）。
- **变换**（GIMP「统一变换」口径，处理古籍褶皱/歪斜）：**默认选中整幅
  图**，拖角=缩放（Shift 等比）、拖边=切变、框内拖=移动、框外拖=**绕
  轴心旋转**（Shift 每 15° 吸附）；轴心圆点可拖动，「从轴心」勾选后
  缩放/切变也以轴心为锚。勾选「**调整范围**」后沿边拖动**收小要处理的
  区域**（收完自动回到变换模式）——小范围修褶皱就是"收小区域 → 旋转/
  切变把它正回来"。拖动即实时预览（原区域填白，变换后的内容以
  浮层显示）；「应用变换」（或切走工具/「完成」）才烘焙进像素——原
  区域填白、只把选区内容按仿射矩阵画回去，画布尺寸不变，**区域外的
  像素一动不动**。一批一个撤销点。
- **变形**（**PS 操控变形 Puppet Warp 口径**，处理古籍褶皱/卷曲/线段倾斜）：
  在图上**打图钉**（点一下放一个）→ 拖某个图钉，**它附近的内容跟着走、
  离得越远动得越少、没被钉住的远处几乎不动**（"像扯弹簧"/"像揉面团"）。
  - **加图钉**：工具激活时直接点图上的位置；点已有图钉附近＝选中它而不是
    新建（吸附半径 :data:`PIN_HIT_VIEW_PX`）。
  - **删图钉**：`Alt`+点，或右键点。
  - **图钉拖到图外**：允许（往外拉＝把那块内容往外拉伸），越界部分填底。
  - **网格疏密**：算法把图片切成三角网格，格距在选项行选（见
    :data:`MESH_DENSITY_CHOICES`）；越密越细腻、解方程越慢。
  - ⚠️ **边框自动锚定**：ARAP 能量对整体平移/旋转不变，只钉一个图钉时整张
    网格会"一起漂移"（实测每个顶点都平移 14px）。所以默认把**图片四边**
    视为固定（PS 的做法），拖内部图钉时边框被拉住，形变才收敛成"近处大、
    远处为零"（见 ``utils.puppet_warp.solve_puppet``）。
  - 拖动即实时预览（只算动过的网格凸包包围盒 + 按屏幕清晰度降采样，见
    :func:`cage_preview_scale`），松手补一帧更清楚的；「应用变形」（或切走
    工具/「完成」）才烘焙进像素（有等待光标）。
  - ⚠️ 「应用变形」后**图钉留在原地**（``adopt_pins``）：古籍褶皱往往要来回
    试几次，每次应用后都清空图钉的话用户得重新钉一遍。
  算法与口径见 ``utils/puppet_warp.py``。
  ⚠️ 进这个工具时图片**不铺满视口**（:data:`DEFORM_FIT_RATIO`），四周留白
  方便把图钉往图外拖。
- **擦除**：按住左键涂抹把污点**擦成白底**（古籍页面去污点就是涂白）；
  直径在选项行可调；光标处有**实圈指示**，直径恒等于实际擦除直径
  （所见即所擦）。一笔一个撤销点。
  （原「拉伸」与笔刷配色已按用户 2026-10-01 要求移除；同日按 GIMP
  变换笼方案重新实现为上面的「变形」。）
- **文字**：点击落点 → 画布上**就地输入**（光标可见，点已有块可继续
  编辑）→ 选项行可调字体 family / 字号 / **颜色选择器**（对整块即时
  生效，样式是段落属性，与手机作图App同口径）→ 鼠标悬停在文字上出现
  **边界虚线框**，按住拖动整块移动（虚线框跟随，松手即消失）→
  「插入文字」把块写进图片（切走工具或点「完成」时未插入的块也自动
  写入）。一个批次一个撤销点。

  选项行的字体下拉**以中文字体为主**、只带几个常用西文字体（系统字体库
  动辄两三百个族，全列出来反而找不到"仿宋"，见 `ui.fonts`）；颜色是
  **一个按钮**，常用色块收在它弹出的面板里（见 `ui.color_picker`）。

  ⚠️ 样式改动作用在"**当前样式块**"（``EditorCanvas.style_target_block``）
  上，而不是"场景焦点项"：选项行的控件（尤其 qfluentwidgets 的 Slider，
  它是 ``StrongFocus``）一被点击就会抢走键盘焦点，场景焦点项随之变 None，
  按焦点项找块的话**改字号/颜色全部落空**（用户 2026-10-01 报障）。

⚠️ 撤销栈存的是**整图快照**（QImage 写时复制在就地绘制时仍会共享底层数据，
必须 ``copy()``），上限 12 步——4000px 预览约 60MB/步，再多内存吃不消。
"""
from __future__ import annotations

import contextlib
import math
import time

from PySide6.QtCore import (
    QLineF, QPointF, QRect, QRectF, QSize, QSizeF, Qt, QThread, QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QImage, QKeySequence, QFontMetrics,
    QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QShortcut, QTransform,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QGraphicsEllipseItem, QGraphicsItem,
    QGraphicsLineItem, QGraphicsPathItem, QGraphicsPixmapItem,
    QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsScene,
    QGraphicsTextItem, QGraphicsView, QHBoxLayout, QLabel, QProgressDialog,
    QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    CaptionLabel, CheckBox, ComboBox, PrimaryPushButton, PushButton,
    Slider, ToggleButton, ToolButton,
)
from qfluentwidgets import FluentIcon as FIF

from desktop.ui import theme as T
from desktop.ui.color_picker import ColorPickerButton
from desktop.ui.fonts import text_font_families
from desktop.ui.window_size import apply_window_size
from desktop.workers.worker_host import connect_queued
# ⚠️ utils.puppet_warp 的 numpy/scipy 是**函数内延迟导入**的，模块级 import
#    不会把它们拖进 GUI 主进程的启动路径（与 desktop/services/rembg_live
#    同口径）。这里只取函数引用，真正解算时才 import numpy/scipy。
from utils.puppet_warp import (
    ARAP_DRAG_ITERATIONS, ARAP_DRAG_TOLERANCE,
    build_mesh, drag_cell, grid_cell, mesh_moved, nearest_vertex,
    puppet_warp_qimage, solve_puppet,
)
# ⚠️ 变换笼（GIMP 口径，与上面的 PS 操控变形**并存**，是两个独立工具）。
#    同样只取函数引用，numpy 在函数内延迟导入。
from utils.cage_warp import (
    cage_moved, deform_qimage, moved_handles, perimeter_cage,
)
from utils.perspective import (
    quad_moved, rectify_qimage, rectify_region,
)

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


# ------------------------------------------------------------------ 纯逻辑
def clamp_rect(rect: QRectF, bounds: QRectF) -> QRectF:
    """把矩形夹进边界内（先平移、超界再缩边）；空矩形原样返回。"""
    if rect.isNull():
        return rect
    rect = rect.normalized()
    width = min(rect.width(), bounds.width())
    height = min(rect.height(), bounds.height())
    x = max(bounds.left(), min(rect.left(), bounds.right() - width))
    y = max(bounds.top(), min(rect.top(), bounds.bottom() - height))
    return QRectF(x, y, width, height)


# ------------------------------------------------------------------ 变换数学
# ⚠️ PySide6 的 QTransform 复合约定（离屏实测）：
#   * ``(A * B).map(p)`` = **先 A 后 B**（与 QPainter 的调用顺序一致）；
#   * 链式 builder ``translate(c).rotate(a).translate(-c)`` 恰好是"绕 c 旋转"；
#   * ``shear(sh, sv)``：x' = x + sh·y，y' = y + sv·x；rotate 正角度 = 顺时针
#     （y 向下坐标系）。下面的组合全按这套语义写，并有自测盯着。
def rotate_about(point: QPointF, degrees: float) -> QTransform:
    """绕 ``point`` 旋转 ``degrees``（正=顺时针）。"""
    t = QTransform()
    t.translate(point.x(), point.y())
    t.rotate(degrees)
    t.translate(-point.x(), -point.y())
    return t


def scale_about(point: QPointF, sx: float, sy: float) -> QTransform:
    """绕 ``point`` 缩放（sx/sy 为 0 会退化，调用方保证非零）。"""
    t = QTransform()
    t.translate(point.x(), point.y())
    t.scale(sx, sy)
    t.translate(-point.x(), -point.y())
    return t


def shear_about(point: QPointF, sh: float, sv: float) -> QTransform:
    """绕 ``point`` 切变：水平 sh（x 随 y 斜切）、垂直 sv（y 随 x 斜切）。"""
    t = QTransform()
    t.translate(point.x(), point.y())
    t.shear(sh, sv)
    t.translate(-point.x(), -point.y())
    return t


def bake_transform(image: QImage, rect: QRectF, xf: QTransform,
                   region: QImage, grow: bool = False):
    """把「选区内容经 ``xf`` 变换」烘焙进图片。

    ``grow=False``（旧行为）：画布尺寸不变——先把**原区域**填白（内容被挪走/
    变形后空出来的地方），再在 ``xf`` 变换下把选区快照画回去。古籍整页白底，
    填白视觉上最干净。

    ``grow=True``（用户 2026-10-02）：「图片倾斜后一部分区域超出原本边界，
    现在会被截掉」——**不截**。最终画布 = 「原图边界 ∪ 变换后选区的外框」
    （:func:`transform_region`）。返回 ``(QImage, (ox, oy))``，``(ox, oy)`` =
    新画布左上角在原坐标系里的位置（可为负）。
    """
    if not grow:
        result = image.copy()
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(rect, QColor("#ffffff"))
        painter.setTransform(xf)
        painter.drawImage(rect, region)
        painter.end()
        return result
    # grow：新画布 = 原图 ∪ 变换后选区外框
    ox, oy, width, height = transform_region(image, rect, xf)
    # 底图：不透明图填白（与旧行为一致：古籍白纸），带 alpha 的图填透明
    transparent = image.hasAlphaChannel() and _image_has_alpha(image)
    base = QImage(width, height, QImage.Format.Format_ARGB32)
    base.fill(QColor(0, 0, 0, 0) if transparent else QColor("#ffffff"))
    painter = QPainter(base)
    painter.drawImage(-ox, -oy, image)
    painter.end()
    painter = QPainter(base)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    # 原选区在新画布里的位置：先填白（把被挪走的原内容擦掉），再画变换结果
    painter.translate(-ox, -oy)
    painter.fillRect(rect, QColor("#ffffff"))
    painter.setTransform(xf, True)
    painter.drawImage(rect, region)
    painter.end()
    return base, (ox, oy)


def _image_has_alpha(image: QImage) -> bool:
    """源图是否**真有透明像素**（决定 grow 底图填透明还是填白）。见画布同款。

    不能用 ``hasAlphaChannel()`` 单判——ARGB32 格式"有通道"不代表真有透明
    像素（整幅全不透明时填透明会在 Windows 上显成黑）。
    """
    if image.isNull():
        return False
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    raw = bytes(rgba.constBits())
    step = rgba.width() * 4
    for y in range(rgba.height()):
        row = raw[y * step:(y + 1) * step]
        if row[3::4].count(255) != rgba.width():
            return True
    return False


def transform_region(image: QImage, rect: QRectF, xf: QTransform):
    """``grow`` 模式的目标画布：``(ox, oy, width, height)``。

    用户口径（2026-10-02）：「一切以新图为准，新图什么样就什么样，老图不要了」
    ——最终图 = **变换后内容的完整外框**，而不是"原图 ∪ 变换后"。

    内容 = ①变换后的选区（仿射把矩形映成平行四边形，落在四角外接框内）
    ∪ ②**选区之外**原本就留着的那部分原图（选区整体移走时这块为空）。
    选区原位被移走、内容被填白，所以**不再算进外框**——若按"原图边界"取并，
    整体平移就会凭空多出一条填白边（用户要的正是把它去掉）。
    """
    corners = [rect.topLeft(), rect.topRight(),
               rect.bottomRight(), rect.bottomLeft()]
    mapped = [xf.map(point) for point in corners]
    xs = [point.x() for point in mapped]
    ys = [point.y() for point in mapped]
    # ⚠️ 用 `round` 而不是 `floor/ceil`：拖拽平移量是**浮点**（鼠标到像素的
    # 映射会带小数点，实测 −30.048465），floor(−30.048)=−31、ceil(169.952)
    # =170 ⇒ 凭空多出 1px 画布。四舍五入到最近像素才是"内容真正占了几列"，
    # 因为渲染时半像素会被夹到边界上、不会多出可分辨的一列。
    x0 = round(min(xs))
    y0 = round(min(ys))
    x1 = round(max(xs))
    y1 = round(max(ys))
    # 选区之外的原图内容仍存在（部分选区变换时）：把"原图 − 选中矩形"的
    # 四块残余内容并进来。注意：残余是**未变换的原图矩形**，按内容真实占用
    # 取整——用 `floor/ceil` 向外扩一列，原图的边界列才不会被切掉；这里
    # 不用 `round`（`round` 是给变换后坐标用的，见上）。
    sel = rect.normalized()
    for bx0, by0, bx1, by1 in (
        (0.0, 0.0, sel.left(), image.height()),        # 左残条
        (sel.right(), 0.0, image.width(), image.height()),  # 右残条
        (sel.left(), 0.0, sel.right(), sel.top()),     # 上残条
        (sel.left(), sel.bottom(), sel.right(), image.height()),  # 下残条
    ):
        if bx1 - bx0 <= 0 or by1 - by0 <= 0:
            continue
        x0 = min(x0, math.floor(bx0))
        y0 = min(y0, math.floor(by0))
        x1 = max(x1, math.ceil(bx1))
        y1 = max(y1, math.ceil(by1))
    return x0, y0, max(1, x1 - x0), max(1, y1 - y0)


def bake_puppet(image: QImage, vertices_rest, vertices_moved,
                triangles, grow=False, progress=None):
    """把「网格 ``vertices_rest`` → ``vertices_moved``」的形变烘焙进图片。

    与 :func:`bake_transform` 同口径：**没动过的网格区域**逐字节不动，只是
    这里不是仿射矩阵，而是 ARAP 三角网格逐像素重映射（PS 操控变形口径，
    见 ``utils.puppet_warp``）。
    ⚠️ **保留 alpha**：桌面侧编辑的常常是第三步产物「白底透明 PNG」，
    丢掉 alpha 会让整片透明背景变成不透明黑（用户 2026-10-01 报过）。

    ``grow=True``：图钉拖出原边界时不裁，画布放大，返回 ``(QImage, (ox, oy))``
    （用户 2026-10-02：「超出原本区域的不要截，最终结果按最后图片的范围」）。

    ``progress`` 透传（见 ``utils.puppet_warp.puppet_warp``）；被中止时
    返回 ``None``。
    """
    return puppet_warp_qimage(image, vertices_rest, vertices_moved, triangles,
                              grow=grow, progress=progress)


def cage_preview_scale(span_x: float, span_y: float,
                       on_screen: float = 1.0,
                       budget_pixels: float = DEFORM_PREVIEW_PIXELS) -> float:
    """拖动预览的降采样倍率：清晰度与成本的**取小**。

    两个约束：

    1. **清晰度**：``on_screen`` = 场景 1 单位对应多少**设备像素**
       （= 当前缩放 × dpr）。预览取到这个倍率时，预览图上的 1 像素正好
       落在屏幕 1 设备像素上——看着与原图一样清楚，再取大就是纯浪费。
    2. **成本**：处理面积不超过 ``budget_pixels``。

    缩到 1/3 看整页时清晰度约束直接给出 1/3：比按成本算还省 9 倍工作量，
    而且屏幕上看不出区别（这正是"预览"该有的样子）。

    ``budget_pixels`` 由调用方按场合给：拖动中给
    :data:`DEFORM_PREVIEW_PIXELS`（要跟手），松手后给
    :data:`DEFORM_PREVIEW_SETTLE_PIXELS`（停下来看结果，宁可慢一点也要清楚）。
    """
    area = max(1.0, float(span_x) * float(span_y))
    budget = math.sqrt(float(budget_pixels) / area)
    return max(1e-3, min(1.0, float(on_screen), budget))


@contextlib.contextmanager
def wait_cursor():
    """耗时操作期间挂等待光标。

    ⚠️ 必须 ``processEvents`` 一下，否则光标要等界面回到事件循环才换，
    而那时的等待已经结束了（等于没挂）。调用方负责别在里面重入。
    """
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    QApplication.processEvents()
    try:
        yield
    finally:
        QApplication.restoreOverrideCursor()


class _BakeWorker(QThread):
    """把**全分辨率烘焙**放到后台线程跑，并用进度对话框报告进度。

    为什么需要它（用户 2026-10-01 报"程序卡死崩溃，不能实时查看"）：
    ``deform_qimage`` / ``puppet_warp_qimage`` 是逐像素重映射，整页
    4000×3000 要 3~15 秒、12000×9000 到分钟级。**同步**跑会把 GUI 主线程
    钉死——界面不重绘、不响应点击，用户看到的就是"卡死/崩溃"（其实是假死）。

    做法：把"重活"（``work(params, progress)`` 返回结果）丢进本线程；工作
    函数通过 ``progress(done, total)`` 回调报进度，主线程每来一次就把
    ``QProgressDialog`` 往前推一格并 ``processEvents``（保持"取消"按钮可点）。
    主线程序列化地与工作线程通信：只传不可变的参数与结果，避免共享可变状态。

    ``progress`` 返回 ``False``（用户点了取消），工作函数应尽快返回 ``None``；
    本线程据此把结果标为"已取消"。
    """

    #: 进度回调在工作线程里被调用 → 用信号转发到主线程更新对话框
    ticked = Signal(int, int)
    #: 工作函数**抛异常**时发出（``str``），主线程据此报错而不是假装取消
    #: （见 :meth:`run` —— 异常绝不能一路逃出 ``run``）
    failed = Signal(str)

    def __init__(self, work, params: dict, parent=None):
        super().__init__(parent)
        self._work = work
        self._params = params
        self.cancelled = False
        self.result = None
        #: 工作函数抛出的异常对象（主线程读），``None`` 表示没出错
        self.error: Exception | None = None

    def cancel(self) -> None:
        """请求取消（主线程调；工作函数下次回调进度时即中止）。"""
        self.cancelled = True

    def progress(self, done: int, total: int):
        """工作函数调用的进度回调；返回 False 表示用户已请求取消。"""
        self.ticked.emit(int(done), int(total))
        return not self.cancelled

    def run(self) -> None:  # noqa: D102（QThread 入口）
        # ⚠️ **必须**在这里捕获所有异常（用户可见的"崩溃"头号来源）：
        #   ``run`` 是被 C++ 调用的虚函数，Python 异常直接逃出去只会打一段
        #   stderr（PySide6 6.9 实测，进程**存活**），但 ``self.result`` 停在
        #   ``None`` 而 ``cancelled`` 是 ``False`` —— 调用方
        #   （:func:`run_with_progress`）据此返回 ``None``，上层
        #   （``_commit_deform`` 等）就会把它当成"**用户取消**"，弹掉撤销点
        #   并且**一声不吭**。用户点了 20 秒，什么都没发生，也没提示。
        #   ⇒ 存下异常并置位 failed，让调用方弹错误框、退回撤销点。
        try:
            self.result = self._work(self._params, self.progress)
        except Exception as exc:      # noqa: BLE001（兜底，不透传）
            self.error = exc
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        # MemoryError / 其它 BaseException（如 QThread 被中断）也一并拦住：
        # 任何逃逸都会让调用方误判成"取消"，比崩掉更难排查。
        except BaseException as exc:  # noqa: BLE001
            self.error = exc
            self.failed.emit(f"{type(exc).__name__}: {exc}")


def run_with_progress(parent: QWidget | None, title: str, label: str,
                      work, params: dict):
    """在后台线程跑 ``work(params, progress)`` 并显示进度对话框。

    返回工作结果；被用户取消时返回 ``None``。``work`` 必须是**纯计算**
    （只用到形参，不碰 Qt 部件/画布），这样才能安全地放进工作线程。
    小任务（预估很快）也不亏：线程启动 + 对话框开销在毫秒级。

    ⚠️ 工作函数**抛异常**时**重新抛出**（``raise worker.error``），
    调用方负责弹错误框并退回撤销点。绝不能把它折叠成 ``None`` ——
    ``None`` 的既定含义是"用户取消"，混同的结果是"点了 20 秒什么都没发生
    且无提示"（用户报过的现象，见 :meth:`_BakeWorker.run`）。

    ⚠️ 本函数**不吞异常、也不留孤儿线程**：整体 ``try/finally``，
    ``finally`` 里 ``cancel() + wait()``。异常逃出等待循环时若不收尾，
    worker 会变成孤儿线程，而它是被 ``parent``（编辑器对话框）持有的 ——
    对话框一析构就是 ``QThread: Destroyed while thread is still running``，
    **Qt 直接 abort 整个进程**（本项目 ``worker_host`` 已记过这条）。
    """
    worker = _BakeWorker(work, params, parent)
    dialog = QProgressDialog(label, "取消", 0, 100, parent)
    dialog.setWindowTitle(title)
    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    dialog.setMinimumDuration(300)       # 快任务不闪一下对话框
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    dialog.setValue(0)
    # ⚠️ ``QProgressDialog.close()`` **也会**发 ``canceled``（实测 Qt6），
    #    不区分的话"正常跑完 → close"会被当成用户取消，结果白丢。
    #    用一个闸门：只有对话框还开着时的 canceled 才算真取消。
    state = {"done": False}

    def on_cancel() -> None:
        if not state["done"]:
            worker.cancel()

    dialog.canceled.connect(on_cancel)

    def on_tick(done: int, total: int) -> None:
        if total > 0:
            dialog.setValue(min(100, int(done * 100 / total)))

    def on_failed(message: str) -> None:
        state["error"] = message

    # ⚠️ 显式排队连接：**不依赖**"PySide6 给无接收者的闭包自动建 proxy 并
    #   queued 连接"这一隐式行为。实测（子线程真实 emit + 主线程 wait/processEvents
    #   循环）当前 PySide6 6.9.2 确实跑在主线程，但那是版本相关的实现细节；
    #   一旦某个版本按 Auto→Direct 处理，就会在工作线程里碰
    #   ``dialog.setValue``，而此刻主线程正在 ``processEvents`` 里操作同一个
    #   对话框 ⇒ 两个线程摸同一个 widget，Windows 上是访问违例。
    #   项目约定（``desktop/workers/worker_host.connect_queued``）也是这条。
    #   中继对象必须挂在**主线程内的 QObject** 上，所以 ``parent`` 为 None
    #   时退回"直接连"（本函数的所有实际调用方都传了对话框）。
    if parent is not None:
        connect_queued(parent, worker.ticked, on_tick, worker)
        connect_queued(parent, worker.failed, on_failed, worker)
    else:
        worker.ticked.connect(on_tick)
        worker.failed.connect(on_failed)
    error: Exception | None = None
    cancelled = False
    result = None
    try:
        worker.start()
        # 主线程等它跑完，但每 50ms 醒一次让事件循环处理重绘/取消点击
        while not worker.wait(50):
            QApplication.processEvents()
        # 线程已停，此刻才能安全收尾（worker.error / result 已定型）。
        # ⚠️ **必须在这里读 `cancelled`**：下面的 `finally` 为了兜底会调
        #   `worker.cancel()`，那会把"正常跑完"也标成取消。
        state["done"] = True          # 先封住 canceled，再正常关闭
        error = worker.error
        cancelled = worker.cancelled
        result = worker.result
    finally:
        # 兜底：异常路径下也要确保线程结束、对话框销毁，绝不留孤儿
        state["done"] = True
        worker.cancel()
        worker.wait()
        dialog.close()
        dialog.deleteLater()
    if error is not None:
        raise error
    if cancelled:
        return None
    return result


def _bake_cage_work(params: dict, progress):
    """后台线程里的笼形变烘焙（纯计算，不碰 Qt 部件）。

    见 :func:`run_with_progress`：只读 ``params``、只写返回值，形变本身由
    ``utils.cage_warp.deform_qimage`` 完成（QImage 是隐式共享的值对象，
    在工作线程里用/生成是安全的——这里全程不触碰任何 QWidget/画布）。

    ``grow=True``：内容被拖出原边界时**不裁**，返回 ``(QImage, (ox, oy))``
    （用户 2026-10-02：「超出原本区域的不要截，最终结果要按最后图片的范围」）。
    """
    return deform_qimage(params["image"], params["src"], params["dst"],
                         grow=True, progress=progress)


def _bake_puppet_work(params: dict, progress):
    """后台线程里的 ARAP 形变烘焙（纯计算，不碰 Qt 部件）。见上。

    ``grow=True``：图钉被拖出原边界时**不裁**，返回 ``(QImage, (ox, oy))``
    （用户 2026-10-02：「超出原本区域的不要截」）。
    """
    return bake_puppet(params["image"], params["vertices"], params["moved"],
                       params["triangles"], grow=True, progress=progress)


def draw_text(image: QImage, pos: QPointF, text: str, px: int,
              color: QColor, family: str | None = None) -> QImage:
    """在 ``pos``（文字块左上角）画文字（可多行，行距 1.25 倍）；空文本原样返回。

    ``family`` 缺省用主题字体；文字块（就地编辑）烧进图片时传块当时的
    family，保证"所见即所得"。
    """
    if not text.strip():
        return image
    result = image.copy()
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    font = QFont(family or T.FONT_FAMILY)
    font.setPixelSize(max(1, int(px)))
    painter.setFont(font)
    painter.setPen(QPen(color))
    metrics = QFontMetrics(font)
    step = max(1, int(px * 1.25))
    for row, line_text in enumerate(text.splitlines() or [""]):
        # drawText(QPointF) 的 y 是**基线**：pos 约定为文字块左上角，
        # 每行要往下挪一个 ascent（多行再叠 1.25 倍行距）
        baseline = pos + QPointF(0, row * step + metrics.ascent())
        painter.drawText(baseline, line_text)
    painter.end()
    return result


def _project_on_segment(p: QPointF, a: QPointF, b: QPointF):
    """``p`` 在线段 ``ab`` 上的**投影点**与参数 ``t``（0=起点、1=终点）。"""
    ab = b - a
    length_sq = ab.x() * ab.x() + ab.y() * ab.y()
    if length_sq < 1e-12:
        return (QPointF(a), 0.0)
    t = max(0.0, min(1.0, (
        (p.x() - a.x()) * ab.x() + (p.y() - a.y()) * ab.y()) / length_sq))
    return (a + ab * t, t)


def _segment_hit(p: QPointF, a: QPointF, b: QPointF) -> tuple[float, float]:
    """点到线段的**最短距离**与**落点参数** ``t``（0=起点、1=终点）。"""
    point, t = _project_on_segment(p, a, b)
    return (QLineF(p, point).length(), t)


def _dist_to_segment(p: QPointF, a: QPointF, b: QPointF) -> float:
    """点到线段的最短距离（视图像素口径的边命中带用）。"""
    return _segment_hit(p, a, b)[0]


class TextBlockItem(QGraphicsTextItem):
    """画布上的待插入文字块：就地编辑（光标可见），按住拖动整体移动。

    交互口径：**单击**进编辑态放光标（QGraphicsTextItem 原生），**按住
    拖动**超过阈值 = 移动整块。刻意不复用 ``ItemIsMovable``——它与文本
    编辑的"按住选字"打架，这里按位移阈值自己分流。拖动全程由画布的
    **边界虚线框**跟随（悬停即显示、松手即消失），用户随时知道"这一块
    会被整体挪走"（用户 2026-10-01：手机作图式文字）。
    """

    #: 按下后位移超过该值（图片像素）判定为拖动，否则视为点击放光标
    DRAG_THRESHOLD = 4.0

    def __init__(self, pos: QPointF, px: int, color: QColor, family: str):
        super().__init__()
        self.setPos(pos)
        # 文档默认有 4px 边距，会让"烧进图片"的位置比屏幕所见偏右下
        self.document().setDocumentMargin(0.0)
        font = QFont(family)
        font.setPixelSize(max(1, int(px)))
        self.setFont(font)
        self.setDefaultTextColor(color)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self._moving = False
        self._press_scene = QPointF()
        self._canvas: "EditorCanvas | None" = None  # add_text_block 回填

    def apply_style(self, family: str, px: int, color: QColor) -> None:
        """选项行改字体/字号/颜色时对块即时生效（编辑中也能改）。

        ⚠️ 是**整块**生效：setFont/setDefaultTextColor 作用于整个文档，
        与手机作图App一致——样式是段落属性，不做逐字混排。
        """
        font = self.font()
        font.setFamily(family)
        font.setPixelSize(max(1, int(px)))
        self.setFont(font)
        self.setDefaultTextColor(color)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._moving = False
            self._press_scene = event.scenePos()
            if self._canvas is not None:
                self._canvas._move_text_outline(self)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if (event.buttons() & Qt.MouseButton.LeftButton
                and (self._moving
                     or (event.scenePos() - self._press_scene)
                     .manhattanLength() > self.DRAG_THRESHOLD)):
            delta = event.scenePos() - self._press_scene
            self._moving = True
            self.setPos(self.pos() + delta)
            self._press_scene = event.scenePos()
            if self._canvas is not None:
                self._canvas._move_text_outline(self)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._moving:
            self._moving = False
            if self._canvas is not None:
                self._canvas._hide_text_outline()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # Esc 结束编辑（块保留，可再拖动/再编辑）；不冒泡去关弹窗
        if event.key() == Qt.Key.Key_Escape:
            self.clearFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        # 报备"当前样式块"：选项行改字体/字号/颜色时作用在它身上。不能靠
        # 场景焦点项现查——选项行控件（尤其 Slider）一被点就把焦点抢走。
        if self._canvas is not None:
            self._canvas._active_text_block = self

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        # 空块（点了落点没打字）失焦即自删，不留隐形占位
        if not self.toPlainText().strip():
            if self._canvas is not None and self._canvas._active_text_block is self:
                self._canvas._active_text_block = None
            QTimer.singleShot(0, self.deleteLater)


# ------------------------------------------------------------------ 画布
class EditorCanvas(QGraphicsView):
    """编辑画布：滚轮缩放、中/右键拖拽平移、左键按工具交互。

    场景坐标 = 图片像素（pixmap 刻意不设 devicePixelRatio，与预览弹窗同
    口径）。选区矩形（裁剪）几何全部落在**图片坐标系**，缩放只影响显示。
    裁剪不做"拖拽画框"：**默认全选**，只许收边/框内移动。
    """

    #: 擦除一笔开始（弹窗借此压撤销点）
    stroke_started = Signal()
    #: 在文字工具下单击了某个落点（图片坐标，已夹进画布）
    text_requested = Signal(QPointF)
    #: 「调整范围」收边完成（弹窗借此取消勾选，自动回到变换模式）
    reshape_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item: QGraphicsPixmapItem | None = None
        self._image: QImage | None = None
        self._zoom = 1.0
        self._tool = "crop"
        #: 用户是否手动缩放过。没动过就随窗口 resize 自动"适应窗口"——
        #: ⚠️ 没有它，弹窗刚打开（布局未定）时 fit 算出的脏尺寸会把大图
        #: 缩成指甲盖大小且再也不修正（用户截图报过）。
        self._user_zoomed = False
        #: 「适应窗口」时图片占视口的比例（1.0 = 铺满；见 set_fit_ratio）。
        #: 缺省即留白（EDIT_FIT_RATIO），用户 2026-10-02：「编辑区不要铺满整个
        #: 界面，上下都要预留空白」——所有工具通用，不只是变形/变换笼。
        self._fit_ratio = EDIT_FIT_RATIO
        self._rect: QRectF | None = None          # 当前选区（图片坐标）
        self._mode: tuple | None = None           # 进行中的拖拽
        self._hover_handle: str | None = None     # 悬停/拖动中的手柄（光标+高亮）
        self._erase_size = ERASER_DEFAULT
        self._eraser_pos = QPointF()   # 橡皮擦圈当前位置（图片坐标）
        #: **当前样式作用块**：选项行改字体/字号/颜色时作用在它身上。由
        #: 新建/聚焦/点击文字块时刷新（见 TextBlockItem.focusInEvent）。
        #: ⚠️ 不能用"场景焦点项"代替：选项行的 Slider 是 StrongFocus，一拖
        #: 就把焦点抢走，焦点项变 None，样式改动全部落空（用户报障过）。
        self._active_text_block: TextBlockItem | None = None
        # ---- 变换工具状态 ----
        #: 累计仿射矩阵（图片坐标 → 当前位置）；恒等 = 没动过
        self._xf = QTransform()
        #: 轴心（**选区局部坐标**，显示时经 _xf 映到画布）
        self._xf_pivot = QPointF()
        #: 发生过任何变换操作（区分"真变换"与"动了手但没动矩阵"）
        self._xf_touched = False
        #: 从轴心缩放/切变（旋转永远绕轴心）
        self._xf_about_pivot = False
        #: 「调整范围」模式：拖手柄收小变换区域而不是缩放内容
        #: （小范围修褶皱的入口：先框住褶皱，再旋转/切变把它正回来）
        self._xf_reshape = False
        #: 预览三件套：锁定的选区 / 选区像素快照 / 填白后的底图
        self._xf_rect: QRectF | None = None
        self._xf_region: QImage | None = None
        self._paint_image: QImage | None = None
        #: 变换内容的浮层（跟随 _xf 实时变形，烘焙语义与预览一致）
        self._float_item: QGraphicsPixmapItem | None = None
        # ---- 「变形」（PS 操控变形 Puppet Warp）状态 ----
        #: 三角网格的**参考顶点**（图片像素坐标，建好就不变），
        #: ``(vertices, triangles, cols, rows, cell)``；懒建，见 _ensure_mesh
        self._mesh: tuple | None = None
        #: 网格格距（图片像素档位，见 MESH_DENSITY_CHOICES）
        self._mesh_cell = MESH_DENSITY_DEFAULT
        #: 图钉列表：``[(顶点下标, QPointF 当前目标位置), ...]``。
        #: 顶点下标由 ``nearest_vertex`` 把用户点击吸附到最近网格顶点得到；
        #: 目标位置是用户拖到的地方（**允许在图外**，用来看图钉本体画在哪）。
        self._pins: list[tuple[int, QPointF]] = []
        #: 解算出来的**当前网格顶点位置**（拖动后），烘焙/预览的映射右端；
        #: None = 还没解过（等于参考网格，恒等）
        self._mesh_moved = None
        #: 拖动预览用的**粗网格**缓存（格距见 utils.puppet_warp.drag_cell）
        self._drag_cache: tuple | None = None
        #: 悬停中的图钉下标
        self._pin_hover: int | None = None
        #: 像素预览浮层 + 上次重算的时刻（节流用，见 _refresh_deform_preview）
        self._deform_item: QGraphicsPixmapItem | None = None
        self._deform_painted_at = 0.0
        #: 形变预览时**底图上被挖空的矩形**（图片坐标，整数）：浮层盖住的这块
        #: 在底图里被填白（透明图填透明），否则原像素会从形变结果底下透出来
        #: ——用户 2026-10-02 报的"图片变换了，原图还在背景上面"就是这个重影。
        #: 每帧按新框回填旧框、再挖新框（见 _paint_canvas_cutout）。
        self._preview_cutout: QRect | None = None
        #: 源图是否真有透明像素的缓存（None = 还没算过；见 _has_alpha）
        self._alpha_known: bool | None = None
        # ---- 「变换笼」（GIMP 口径）状态 ----
        #: 笼把手：``[(原位 QPointF, 当前位置 QPointF), ...]``，闭合顺序。
        #: 进工具时 = 贴图边的矩形笼（≡ 没动过）；拖任一把手即产生形变。
        self._cage_handles: list[tuple[QPointF, QPointF]] = []
        #: 每边把手数档位（见 CAGE_DENSITY_CHOICES）
        self._cage_per_side = 2
        #: 悬停中的把手下标
        self._cage_hover: int | None = None
        #: 拖动中的把手下标（None = 拖的是整体/边走）
        self._cage_drag: int | None = None
        #: 拖整体时记下的"按下点 → 当时的把手快照"
        self._cage_drag_origin: tuple[QPointF, list] | None = None
        #: 笼形变的像素预览浮层 + 节流时间戳
        self._cage_preview_item: QGraphicsPixmapItem | None = None
        self._cage_preview_at = 0.0
        # ---- 「校正」（四点透视摆正）状态 ----
        #: 源四边形四个角（图片坐标，顺序 左上/右上/右下/左下）。
        #: 进工具时 = 整幅图四角（≡ 没动过）；拖任一角即产生校正。
        self._rect_quad: list[QPointF] = []
        #: 目标矩形宽高比口径（见 RECTIFY_RATIO_CHOICES）
        self._rectify_ratio = RECTIFY_RATIO_DEFAULT
        #: 拖过的角下标（None = 没拖过）
        self._rect_drag: int | None = None
        #: 悬停中的角下标
        self._rect_hover: int | None = None
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QColor(T.SURFACE_SOFT))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        # 悬停就要更新光标形态（默认只在按住时才来 move 事件）
        self.setMouseTracking(True)
        # ⚠️ 必须 StrongFocus：就地文字块靠「视图持有键盘焦点 → 转发给场景
        #    焦点项」才能收到输入；NoFocus 会让打字全部落空（用户报
        #    「文字不能编辑，输入没效果」，2026-10-01）。方向键翻页由
        #    keyPressEvent 显式 ignore 保持不变。
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._build_overlay()
        self._sync_cursor()

    # ------------------------------------------------------------ 装图
    def set_image(self, image: QImage | None) -> None:
        """装入/替换图片并重新适应窗口（裁剪/撤销等"画布换图"也走这里）。"""
        if getattr(self, "_border", None) is not None:
            self._scene.removeItem(self._border)
        self._border = None
        self._rect = None
        # 换图后文字块/变换预览都失效，一并清掉（应用/撤销/还原都走这里）
        self.clear_text_blocks()
        self._clear_transform_preview()
        self._clear_deform_preview()
        self._clear_cage_preview()
        self._xf = QTransform()
        self._xf_touched = False
        self._mesh = None          # 换图后网格重建（新尺寸/新格距）
        self._mesh_moved = None
        self._pins = []
        self._pin_hover = None
        # 换图后笼失效（新尺寸）：清掉，进工具时按新图重建
        self._cage_handles = []
        self._cage_hover = None
        self._cage_drag = None
        self._cage_drag_origin = None
        # 换图后四边形失效（新尺寸）：清掉，进工具时按新图重建
        self._rect_quad = []
        self._rect_hover = None
        self._rect_drag = None
        # 换图后形变预览的"挖空"与 alpha 缓存都失效（新图、新像素）
        self._preview_cutout = None
        self._alpha_known = None
        if self._item is not None:
            self._scene.removeItem(self._item)
            self._item = None
        self._image = None if image is None or image.isNull() else image
        if self._image is None:
            self._sync_overlay()
            return
        pixmap = QPixmap.fromImage(self._image)
        pixmap.setDevicePixelRatio(1.0)
        item = QGraphicsPixmapItem(pixmap)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._scene.addItem(item)
        # 纸边细框（cosmetic：任何倍率下都是 1 设备像素），白纸与背景才分得开
        self._border = QGraphicsRectItem(item.boundingRect())
        self._border.setPen(QPen(QColor("#8a93a3"), 0))
        self._scene.addItem(self._border)
        self._item = item
        self.setSceneRect(item.boundingRect())
        self.fit()
        if self._tool in ("crop", "transform", "deform"):
            # 换图（应用/撤销/还原都走这里）后选区重新默认全选：
            # 裁剪/变换的语义都是"从当前原图出发"，不是沿用旧图上的框
            self._rect = QRectF(self.image_rect())
            self._xf_pivot = self._rect.center()
        if self._tool == "deform":
            self._ensure_mesh()
        if self._tool == "cage":
            self._ensure_cage()
        self._sync_overlay()

    def _sync_scene_rect(self) -> None:
        """把场景矩形扩到"底图 ∪ 形变预览浮层"。

        grow 模式下形变预览会画到原图边界**之外**，若场景矩形仍等于图片
        边界（``set_image`` 里设的），图外那块会被视口裁掉、看不见（滚不
        过去）。这里取并集后恢复；没有浮层时退化为图片边界。
        """
        if self._item is None:
            return
        rect = self._item.boundingRect()
        if self._deform_item is not None:
            rect = rect.united(self._deform_item.sceneBoundingRect())
        if self._cage_preview_item is not None:
            rect = rect.united(self._cage_preview_item.sceneBoundingRect())
        if self._float_item is not None:
            rect = rect.united(self._float_item.sceneBoundingRect())
        self.setSceneRect(rect)

    def refresh(self) -> None:
        """像素被就地改过（擦除）后只刷显示，不动缩放与滚动位置。"""
        if self._item is not None and self._image is not None:
            self._item.setPixmap(QPixmap.fromImage(self._image))
            # ⚠️ 重刷底图会连同"挖空"一起抹掉：形变预览的浮层还盖在上面，
            #    底图恢复原样就会从浮层底下透出旧内容（重影重新出现）。
            #    这里把上次挖空的框重新挖一遍（见 _paint_canvas_cutout）。
            if self._preview_cutout is not None:
                self._paint_canvas_cutout(self._preview_cutout)

    def replace_image(self, image: QImage) -> None:
        """就地换图（尺寸不变的语义，如文字写入）：不动缩放与滚动位置。"""
        self._image = image
        self._alpha_known = None   # 像素变了，透明判定要重算
        self.refresh()

    def _paint_canvas_cutout(self, rect: QRect | None) -> None:
        """把底图重画成"原图 + 指定矩形挖空"，供形变预览浮层盖住。

        为什么需要它（用户 2026-10-02 报："拖动图片变化形态，图片变换了，
        但是原图片还是在背景上面"）：形变预览是**局部浮层**，底图仍是一整
        张原图。往图外拖/向内推时，形变结果会让开一些位置，那些位置底图里
        的**旧像素就透出来了**——看上去像两张图叠着。变换工具早就有这个
        处理（把选区填白再画浮层），这里把同一口径搬到形变工具。

        ⚠️ 调用方传的是**整张原图** ``QRect(0, 0, width, height)``，不是
        "受影响的小框"：grow 之后浮层已经被移到任意 ``origin``（可能为负），
        形变过的内容会离开原来的位置；只挖局部小框的话，凡是浮层没盖住、
        但原图里有旧像素的地方都会透出来。整块挖空最稳。

        ``rect`` = 要挖空的框（图片坐标，整数）。旧框若与它不同要先按
        ``self._image`` 重铺（回填旧框），否则拖远后旧框的白洞留在原地。
        透明源图挖成透明（保持"白底透明 PNG"不变成白块）。
        """
        if self._item is None or self._image is None:
            return
        canvas = self._image.copy()
        if rect is not None:
            clipped = rect.intersected(
                QRect(0, 0, canvas.width(), canvas.height()))
            if not clipped.isEmpty():
                painter = QPainter(canvas)
                # 源图带 alpha ⇒ 挖成透明；不透明源图 ⇒ 填白（与变换/烘焙填白一致）
                fill = (QColor(0, 0, 0, 0) if self._has_alpha()
                        else QColor("#ffffff"))
                painter.setCompositionMode(
                    QPainter.CompositionMode.CompositionMode_Source)
                painter.fillRect(clipped, fill)
                painter.end()
        pixmap = QPixmap.fromImage(canvas)
        pixmap.setDevicePixelRatio(1.0)
        self._item.setPixmap(pixmap)
        self._preview_cutout = rect

    def _has_alpha(self) -> bool:
        """源图是否有**真的透明像素**（决定形变挖空填透明还是填白）。

        不能用 ``hasAlphaChannel()`` 单判——ARGB32 格式"有 alpha 通道"不代表
        真有透明像素（整幅全不透明时填透明会在 Windows 上显成黑）。这里实际
        扫一遍 alpha：整幅不透明 ⇒ 填白；有任一透明像素 ⇒ 填透明。

        ⚠️ 结果**按图缓存**（``_alpha_known``）：整页扫 alpha 是 O(像素)，
        每帧调用会白白吃掉几十毫秒（预览要跟手）。换图/就地改像素时失效。
        """
        if self._alpha_known is not None:
            return self._alpha_known
        if self._image is None:
            return False
        rgba = self._image.convertToFormat(QImage.Format.Format_RGBA8888)
        raw = bytes(rgba.constBits())
        step = rgba.width() * 4
        result = False
        for y in range(rgba.height()):
            row = raw[y * step:(y + 1) * step]
            if row[3::4].count(255) != rgba.width():
                result = True
                break
        self._alpha_known = result
        return result

    @property
    def image(self) -> QImage | None:
        return self._image

    def image_rect(self) -> QRectF:
        """图片占位（= 场景坐标，1 场景单位 = 1 图片像素）。"""
        if self._image is None:
            return QRectF()
        return QRectF(0, 0, self._image.width(), self._image.height())

    # ------------------------------------------------------------ 工具
    def set_tool(self, tool: str) -> None:
        """切换工具：裁剪/变换/变形默认全选，其余清选区、换光标。"""
        self._tool = tool
        self._mode = None
        self._clear_transform_preview()
        self._clear_deform_preview()
        self._clear_cage_preview()
        self._pin_hover = None
        self._cage_hover = None
        self._cage_drag = None
        self._cage_drag_origin = None
        self._xf = QTransform()
        self._xf_touched = False
        self._xf_reshape = False  # 调整范围是勾选态，换工具即复位
        self._hide_text_outline()
        if tool != "erase":
            self._hide_eraser_ring()
        if tool in ("crop", "transform", "deform") \
                and not self.image_rect().isNull():
            self._rect = QRectF(self.image_rect())
            self._xf_pivot = self._rect.center()
        else:
            self._rect = None
        if tool == "deform":
            self._ensure_mesh()
        elif tool == "cage":
            self._ensure_cage()
        elif tool == "rectify":
            self._rect_quad = []      # 换工具进来 = 从整幅四角重新开始
            self._ensure_quad()
            self._rect_hover = None
            self._rect_drag = None
        self._sync_overlay()
        self._sync_cursor()

    def set_eraser(self, size: int) -> None:
        """设置橡皮擦直径（图片像素）；擦除固定涂白，没有颜色可选。"""
        self._erase_size = max(1, int(size))
        # 圈已在屏上（悬停中/拖抹中）就按新直径重画，光标与笔刷同步变大变小
        if any(item.isVisible() for item in self._eraser_ring):
            self._move_eraser_ring(self._eraser_pos)

    def selection(self) -> QRectF | None:
        """当前选区（图片坐标）；不足最小边视为没有。"""
        if self._rect is None:
            return None
        rect = self._rect.normalized()
        if rect.width() < MIN_RECT_EDGE or rect.height() < MIN_RECT_EDGE:
            return None
        return rect

    # ------------------------------------------------------------ 文字块
    def add_text_block(self, pos: QPointF, px: int, color: QColor,
                       family: str) -> TextBlockItem:
        """在落点放一个可就地编辑的文字块并给它焦点（光标闪烁）。

        ⚠️ 顺便把键盘焦点拿回视图：场景焦点项的输入要靠「视图持有键盘
        焦点 → keyPressEvent 转发」这条链，视图没焦点时打字全落空。
        """
        item = TextBlockItem(pos, px, color, family)
        item._canvas = self  # 拖动时让画布的边界虚线框跟随
        item.setZValue(20)
        self._scene.addItem(item)
        self._active_text_block = item
        self.setFocus()
        item.setFocus()
        return item

    def _move_text_outline(self, block: TextBlockItem) -> None:
        """文字块**边界虚线框**挪到块身（悬停/拖动中可见，松手即隐）。

        用户 2026-10-01：鼠标放在文字上要有"这一块的范围"线段，拖动时
        跟着走，释放就消失——拖的是整块，不是光标。
        """
        rect = block.mapRectToScene(block.boundingRect())
        self._text_outline.setRect(rect)
        self._text_outline.setVisible(True)

    def _hide_text_outline(self) -> None:
        self._text_outline.hide()

    def _text_block_at(self, pos: QPointF) -> TextBlockItem | None:
        """落点处的文字块（按块的边界矩形命中，与虚线框口径一致）。"""
        for block in self.text_blocks():
            if block.boundingRect().contains(block.mapFromScene(pos)):
                return block
        return None

    def text_blocks(self) -> list[TextBlockItem]:
        """画布上所有待插入文字块。"""
        return [i for i in self._scene.items()
                if isinstance(i, TextBlockItem)]

    def focused_text_block(self) -> TextBlockItem | None:
        """正在编辑的文字块（场景焦点项；键盘输入路由用）。"""
        item = self._scene.focusItem()
        return item if isinstance(item, TextBlockItem) else None

    def style_target_block(self) -> TextBlockItem | None:
        """选项行改样式时作用的那一块：优先正在编辑的，其次"当前样式块"。

        ⚠️ 与 :meth:`focused_text_block` 分开是刻意的：点选项行的滑杆/按钮
        会抢走键盘焦点，此时"正在编辑"已经没了，但用户**期望**改动仍落在他
        刚点的那个文字块上（用户 2026-10-01 报"字号不生效"就是这个原因）。
        """
        block = self.focused_text_block()
        if block is not None:
            return block
        block = self._active_text_block
        if block is None:
            return None
        try:
            alive = block.scene() is self._scene
        except RuntimeError:  # 空块失焦自删，C++ 对象已回收
            alive = False
        if not alive:
            self._active_text_block = None
            return None
        return block

    def focus_text_block(self, block: TextBlockItem | None = None) -> None:
        """把键盘焦点还给文字块（颜色面板关掉后接着打字用）。"""
        block = block if block is not None else self.style_target_block()
        if block is None or block.scene() is not self._scene:
            return
        self.setFocus()
        block.setFocus()

    def clear_text_blocks(self) -> None:
        """清掉所有文字块（插入/换图/关编辑时）。"""
        self._hide_text_outline()
        self._active_text_block = None
        for item in self.text_blocks():
            self._scene.removeItem(item)
            item.deleteLater()

    # ------------------------------------------------------------ 变换
    def set_transform_about_pivot(self, about: bool) -> None:
        """「从轴心」：缩放/切变以轴心为锚（旋转永远绕轴心）。"""
        self._xf_about_pivot = bool(about)

    def set_transform_reshape(self, on: bool) -> None:
        """「调整范围」模式：拖手柄/边=收小变换区域，而不是缩放内容。

        进入时必须丢掉未应用的变换预览——浮层与填白底都是按**旧区域**
        快照做的，区域一变它们就与画布对不上了。退出（收边完成/取消
        勾选）后保留收小的区域，下一次拖动即以它为变换对象。
        """
        on = bool(on)
        if on and (self._xf_touched or self._float_item is not None):
            self._clear_transform_preview()
            self._xf = QTransform()
            self._xf_touched = False
        self._xf_reshape = on
        self._sync_overlay()
        self._sync_cursor()

    def _ensure_transform_preview(self) -> None:
        """锁定选区并搭起实时预览：底图填白 + 选区快照浮层。

        只在第一次真正抓取时做一次（拿两张整图快照），后续拖动只改
        ``_xf`` 与浮层的 transform，不再碰像素。
        """
        if self._float_item is not None or self._image is None \
                or self._rect is None:
            return
        rect = self._rect.normalized()
        self._xf_rect = QRectF(rect)
        self._xf_region = self._image.copy(rect.toRect())
        self._paint_image = self._image.copy()
        painter = QPainter(self._paint_image)
        painter.fillRect(rect, QColor("#ffffff"))
        painter.end()
        self._item.setPixmap(QPixmap.fromImage(self._paint_image))
        self._float_item = QGraphicsPixmapItem(
            QPixmap.fromImage(self._xf_region))
        self._float_item.setZValue(5)
        self._scene.addItem(self._float_item)
        self._sync_float()

    def _sync_float(self) -> None:
        """浮层跟随累计矩阵：选区像素 (u,v) → 原图坐标 → 画布位置。"""
        if self._float_item is None or self._xf_rect is None:
            return
        tl = self._xf_rect.topLeft()
        # (A*B) 先 A 后 B：先平移到选区原位，再套累计矩阵
        self._float_item.setTransform(
            QTransform().translate(tl.x(), tl.y()) * self._xf)
        # 变换把选区送出原边界时，浮层会跑到图片外——扩场景矩形才看得见
        # （用户 2026-10-02：超出原边界的内容不能丢）
        self._sync_scene_rect()

    def _clear_transform_preview(self) -> None:
        """撤掉预览浮层并把底图恢复成真像素（矩阵不动，见 reset_transform）。"""
        if self._float_item is not None:
            self._scene.removeItem(self._float_item)
            self._float_item = None
        if self._paint_image is not None:
            self._paint_image = None
            self._xf_region = None
            self._xf_rect = None
            self.refresh()
        # 浮层没了 → 场景矩形收回图片边界（变换曾把浮层送出图外时扩过）
        self._sync_scene_rect()

    def reset_transform(self) -> None:
        """「重置」：丢弃未应用的变换，选区回到整幅、轴心回到中心。"""
        self._clear_transform_preview()
        self._xf = QTransform()
        self._xf_touched = False
        if not self.image_rect().isNull():
            self._rect = QRectF(self.image_rect())
            self._xf_pivot = self._rect.center()
        self._sync_overlay()

    def transform_pending(self) -> tuple[QRectF, QTransform, QImage] | None:
        """未应用的变换 ``(选区, 矩阵, 选区像素快照)``；没有则 None。"""
        if (not self._xf_touched or self._xf_rect is None
                or self._xf_region is None):
            return None
        return (QRectF(self._xf_rect), QTransform(self._xf),
                QImage(self._xf_region))

    # ---- 变换操作（拖拽处理器与自测共用的语义级入口） ----
    def transform_move(self, dx: float, dy: float) -> None:
        """整体平移 ``dx, dy``（图片像素）。"""
        self._ensure_transform_preview()
        # 先已有的变换，再平移：(T * Move) 先 T 后 Move
        self._xf = self._xf * QTransform().translate(dx, dy)
        self._xf_touched = True
        self._sync_float()
        self._sync_overlay()

    def transform_rotate(self, degrees: float) -> None:
        """绕**轴心当前视觉位置**旋转（轴心保持不动）。"""
        self._ensure_transform_preview()
        center = self._xf.map(self._xf_pivot)
        self._xf = self._xf * rotate_about(center, degrees)
        self._xf_touched = True
        self._sync_float()
        self._sync_overlay()

    def transform_scale(self, sx: float, sy: float,
                        anchor: QPointF | None = None) -> None:
        """缩放（局部空间，锚点缺省=轴心；sx/sy 是相对当前内容的倍率）。"""
        self._ensure_transform_preview()
        point = QPointF(anchor) if anchor is not None else self._xf_pivot
        sx = sx if abs(sx) > 1e-6 else 1.0
        sy = sy if abs(sy) > 1e-6 else 1.0
        # 局部操作发生在累计矩阵**之前**：(S * T) 先 S 后 T
        self._xf = scale_about(point, sx, sy) * self._xf
        self._xf_touched = True
        self._sync_float()
        self._sync_overlay()

    def transform_shear(self, edge: str, k: float) -> None:
        """拖边切变：``edge`` 是被抓的边（l/r/t/b），``k`` 是切变系数，
        对边为锚（抓右边往下拖 = 内容随 x 增大而下斜）。"""
        self._ensure_transform_preview()
        self._apply_shear(edge, k, self._xf)
        self._xf_touched = True
        self._sync_float()
        self._sync_overlay()

    def _apply_shear(self, edge: str, k: float, x_start: QTransform) -> None:
        """在 ``x_start`` 基础上叠一次切变（拖拽中按拖动起点取绝对量）。"""
        rect = self._xf_rect.normalized()
        if edge in ("l", "r"):
            anchor_x = rect.right() if edge == "l" else rect.left()
            sv = -k if edge == "l" else k
            self._xf = shear_about(
                QPointF(anchor_x, rect.top()), 0.0, sv) * x_start
        else:
            anchor_y = rect.bottom() if edge == "t" else rect.top()
            sh = -k if edge == "t" else k
            self._xf = shear_about(
                QPointF(rect.left(), anchor_y), sh, 0.0) * x_start

    # ------------------------------------------------------------ 变形（操控变形）
    # 口径与算法见 utils/puppet_warp.py 的模块文档。画布这边只负责：
    #   ① 维护图钉列表（点加、拖移、Alt/右键删）；
    #   ② 把图钉交给 solve_puppet 解出**形变后的网格顶点**；
    #   ③ 拖动时按 DEFORM_PREVIEW_PIXELS 降采样出**像素预览**（全分辨率太慢）；
    #   ④ 覆盖层（图钉）每帧跟手，覆盖层本身不碰像素。
    def mesh_density(self) -> float:
        """当前网格格距（图片像素档位）。"""
        return self._mesh_cell

    def set_mesh_density(self, cell: float) -> None:
        """改网格格距：**重建网格并清空图钉**（顶点下标全变了，旧钉无意义）。"""
        self._mesh_cell = float(cell)
        self.reset_pins()

    def _ensure_mesh(self) -> None:
        """（不发信号）按当前图片与格距建网格；已建且尺寸/格距没变就复用。"""
        if self._image is None or self._image.isNull():
            self._mesh = None
            return
        width, height = self._image.width(), self._image.height()
        cell = grid_cell(width, height, self._mesh_cell)
        if self._mesh is not None and self._mesh[4] == cell \
                and self._mesh[0].shape[0] > 0:
            return
        self._mesh = build_mesh(width, height, self._mesh_cell)
        self._mesh_moved = None
        self._drag_cache = None   # 网格变了，粗网格缓存一并失效
        self._pins = []
        self._pin_hover = None

    def reset_pins(self) -> None:
        """「重置」：清空所有图钉，丢掉未应用的形变（网格本身保留）。"""
        self._clear_deform_preview()
        self._mesh = None
        self._mesh_moved = None
        self._pins = []
        self._pin_hover = None
        self._ensure_mesh()
        self._sync_overlay()
        self._sync_cursor()

    def pins(self) -> list:
        """当前图钉的副本（``(顶点下标, QPointF)`` 列表）——给自测与外部读。"""
        return [(index, QPointF(point)) for index, point in self._pins]

    def pin_count(self) -> int:
        """当前图钉个数。"""
        return len(self._pins)

    def _solve_pins(self, *, drag: bool = False):
        """按当前图钉解一次 ARAP，返回 ``(vertices_rest, vertices_moved)``。

        没图钉、或图钉全都还在原位上 ⇒ 返回 ``None``（形变 = 恒等，调用方
        据此跳过重采样——这保证了"没钉就逐字节等于原图"）。

        ⚠️ **``drag=True`` 时用"粗网格 + 少迭代"求一个跟手的近似解**：
        ARAP 的解算耗时随顶点数**超线性**增长（实测 7676 顶点 2.1s、
        1989 顶点 0.26s、520 顶点 0.07s），而拖动每次鼠标移动都要重解 ——
        大图上用精网格根本不可能跟手，用户看到的就是"卡死"。粗网格解出的
        是同一根形变"趋势"，松手后再用精网格解到精细（见
        :func:`utils.puppet_warp.drag_cell`，它同时卡"相对倍数"和"顶点数
        绝对上限"两道）。

        像素重采样不在这里做，由 :meth:`_refresh_deform_preview` /
        :func:`bake_puppet` 走。
        """
        if self._mesh is None or self._image is None:
            return None
        if not self._pins:
            return None
        width, height = self._image.width(), self._image.height()
        mesh = self._drag_mesh() if drag else self._mesh
        if mesh is None:
            return None
        vertices, triangles = mesh[0], mesh[1]
        # 图钉按**图片坐标**存，落到哪张网格就吸附到哪张网格的顶点
        targets = []
        for _vertex, point in self._pins:
            k = nearest_vertex(vertices, (point.x(), point.y()))
            targets.append((int(k), (point.x(), point.y())))
        kwargs = {}
        if drag:
            kwargs = {"iterations": ARAP_DRAG_ITERATIONS,
                      "tolerance": ARAP_DRAG_TOLERANCE}
        try:
            moved = solve_puppet(vertices, triangles, targets,
                                 width=width, height=height, **kwargs)
        except Exception:
            # 解算失败（奇异/退化）时退化为恒等，绝不把画布搞崩
            return None
        return vertices, moved, triangles

    def _drag_mesh(self):
        """拖动预览用的**粗网格**（:func:`drag_cell` 给出格距），缓存。

        返回 ``(vertices, triangles, cols, rows, cell)``；格距同时受"相对
        粗化倍数"和"顶点数上限"两条约束（见 ``utils.puppet_warp.drag_cell``）。
        """
        if self._image is None:
            return None
        width, height = self._image.width(), self._image.height()
        cell = drag_cell(width, height, self._mesh_cell)
        if self._drag_cache is not None and self._drag_cache[4] == cell:
            return self._drag_cache
        self._drag_cache = build_mesh(width, height, cell)
        return self._drag_cache

    def pin_add(self, pos: QPointF) -> int | None:
        """在 ``pos``（图片坐标）加一个图钉，返回它在 ``_pins`` 里的下标。

        图钉**吸附到最近的网格顶点**（ARAP 的硬约束只能钉在顶点上）；同一
        顶点已有图钉时不再重复加，直接返回已有的那个。
        """
        self._ensure_mesh()
        if self._mesh is None:
            return None
        vertices = self._mesh[0]
        vertex = nearest_vertex(vertices, (pos.x(), pos.y()))
        for index, (existing, _point) in enumerate(self._pins):
            if existing == vertex:
                return index
        self._pins.append((vertex, QPointF(float(vertices[vertex, 0]),
                                           float(vertices[vertex, 1]))))
        self._clear_deform_preview()
        self._sync_overlay()
        return len(self._pins) - 1

    def pin_remove(self, index: int) -> None:
        """删掉第 ``index`` 个图钉（形变随之重解）。"""
        if not 0 <= index < len(self._pins):
            return
        self._pins.pop(index)
        self._pin_hover = None
        self._clear_deform_preview()
        self._refresh_deform_preview(force=True)
        self._sync_overlay()

    def pin_move(self, index: int, pos: QPointF) -> None:
        """把第 ``index`` 个图钉拖到 ``pos``（图片坐标）。

        ⚠️ **允许拖到图片外面**（用户 2026-10-01：「任意点只能向内，不能向外」）。
        往外拖＝把那块内容往外**拉伸**，拉出画布的部分按越界填底。这里只留一个
        "一张图那么远"的宽松上限，免得图钉被甩到天外、再也找不回来。
        """
        if not 0 <= index < len(self._pins):
            return
        limit = self.image_rect()
        offset_x, offset_y = limit.width(), limit.height()
        clamped = QPointF(
            max(limit.left() - offset_x,
                min(pos.x(), limit.right() + offset_x)),
            max(limit.top() - offset_y,
                min(pos.y(), limit.bottom() + offset_y)))
        vertex, _old = self._pins[index]
        self._pins[index] = (vertex, clamped)
        self._pin_hover = index  # 拖着的这个保持放大高亮
        self._sync_overlay()
        self._refresh_deform_preview()

    def _hit_pin(self, view_pos: QPointF) -> int | None:
        """命中图钉（视图像素口径，不随缩放变）。"""
        for index, (_vertex, point) in enumerate(self._pins):
            spot = QPointF(self.mapFromScene(point))
            if QLineF(view_pos, spot).length() <= PIN_HIT_VIEW_PX:
                return index
        return None

    def pins_pending(self):
        """未应用的形变 ``(vertices_rest, vertices_moved, triangles)``；无则 None。

        「未应用」= 解出的网格确实动过。全都没动时返回 None，调用方据此
        跳过烘焙（不产生多余的撤销点）。
        """
        solved = self._solve_pins()
        if solved is None:
            return None
        vertices, moved, triangles = solved
        if not mesh_moved(vertices, moved):
            return None
        return (vertices, moved, triangles)

    def adopt_pins(self, pin_vertices=None) -> None:
        """「应用变形」后用：把图钉**原地保留**（目标位置 = 新网格的原位）。

        ⚠️ 为什么不清空：古籍褶皱往往要来回试几次，每次应用后都清空图钉的话
        用户得重新钉一遍。保留图钉、并让它们落在**刚烘焙完的图**的原位，
        就可以接着微调同一块。

        ⚠️ ``pin_vertices`` 必须由调用方在 ``set_image`` **之前**快照传入：
        :meth:`set_image` 换图时会把 ``_pins`` 清空（换图后旧钉无意义），
        所以这里不能指望调用时 ``self._pins`` 还在。传 ``None`` 时退回读
        当前 ``self._pins``（兼容直接调用）。
        """
        self._clear_deform_preview()
        self._mesh = None
        self._mesh_moved = None
        self._ensure_mesh()   # 重建网格（图片没变，格距没变 → 复用/重建都行）
        if self._mesh is not None:
            vertices = self._mesh[0]
            source = self._pins if pin_vertices is None else pin_vertices
            self._pins = [
                (vertex, QPointF(float(vertices[vertex, 0]),
                                 float(vertices[vertex, 1])))
                for vertex, _point in source
                if 0 <= vertex < len(vertices)
            ]
        self._sync_overlay()

    # ---- 「变换笼」（GIMP 口径）----
    #: 笼把手的位置口径与 ``utils.cage_warp`` 一致：``(原位, 当前位置)`` 两个
    #: 序列，闭合顺序。原位 = 进工具时贴图边的矩形；当前位置 = 用户拖到的
    #: 地方（**允许在图外**，往外拖 = 拉伸）。
    def _ensure_cage(self) -> None:
        """（不发信号）没笼时按当前整幅图建一个（贴图边的矩形笼）。"""
        if self._image is None or self._image.isNull():
            self._cage_handles = []
            return
        if self._cage_handles:
            return
        rect = self.image_rect()
        handles = perimeter_cage(
            (rect.left(), rect.top(), rect.right(), rect.bottom()),
            self._cage_per_side)
        # perimeter_cage 给的是单序列 (x, y) 元组（原位）；当前位置初始 = 原位
        self._cage_handles = [
            (QPointF(float(x), float(y)), QPointF(float(x), float(y)))
            for x, y in handles
        ]

    def reset_cage(self) -> None:
        """「重置」：把手回到整幅图原位（丢掉未应用的形变）。"""
        self._clear_cage_preview()
        self._cage_handles = []
        self._cage_drag = None
        self._cage_hover = None
        self._cage_drag_origin = None
        self._ensure_cage()
        self._sync_cage_overlay()
        self._sync_cursor()
        self._refresh_cage_preview(force=True)

    def cage_density(self) -> int:
        """当前每边把手数档位。"""
        return self._cage_per_side

    def set_cage_density(self, per_side: int) -> None:
        """改每边把手数：**重建笼并清掉未应用的形变**（把手序号全变了）。"""
        self._cage_per_side = max(1, int(per_side))
        self.reset_cage()

    def cage(self) -> list:
        """当前把手副本 ``[(原位, 当前位置), ...]``——给自测与外部读。"""
        self._ensure_cage()
        return [(QPointF(a), QPointF(b)) for a, b in self._cage_handles]

    def cage_source(self) -> list[QPointF]:
        """把手**原位**序列（形变映射的左端）。"""
        self._ensure_cage()
        return [QPointF(a) for a, _b in self._cage_handles]

    def cage_target(self) -> list[QPointF]:
        """把手**当前位置**序列（形变映射的右端）。"""
        self._ensure_cage()
        return [QPointF(b) for _a, b in self._cage_handles]

    def cage_pending(self):
        """未应用的笼形变 ``(cage_src, cage_dst)``；没动过返回 ``None``。

        口径与 :meth:`pins_pending` 一致：只有"把手真的动过"才算待应用。
        """
        if self._image is None or self._image.isNull():
            return None
        self._ensure_cage()
        if not self._cage_handles:
            return None
        src = self.cage_source()
        dst = self.cage_target()
        if not cage_moved([(p.x(), p.y()) for p in src],
                          [(p.x(), p.y()) for p in dst]):
            return None
        return src, dst

    def _clamp_cage_pos(self, pos: QPointF) -> QPointF:
        """把手位置夹进「图片矩形 ± 一个图宽」的宽松范围。

        ⚠️ 与 :meth:`pin_move` / :meth:`quad_move` 同口径：允许拖到图外
        （往外＝拉伸），但留一个"一张图那么远"的上限，免得把手被甩到天外、
        再也找不回来。**无上界还会放大两处内存失控**：形变后的画布按落点
        外扩（``grow``），把手飘到几万像素外 ⇒ 画布膨胀几个数量级。
        """
        limit = self.image_rect()
        offset_x, offset_y = limit.width(), limit.height()
        return QPointF(
            max(limit.left() - offset_x, min(pos.x(), limit.right() + offset_x)),
            max(limit.top() - offset_y, min(pos.y(), limit.bottom() + offset_y)))

    def cage_move(self, index: int, pos: QPointF) -> None:
        """把第 ``index`` 个把手拖到 ``pos``（图片坐标，允许图外）。"""
        self._ensure_cage()
        if not (0 <= index < len(self._cage_handles)):
            return
        origin, _cur = self._cage_handles[index]
        self._cage_handles[index] = (origin, self._clamp_cage_pos(pos))
        self._sync_cage_overlay()
        self._refresh_cage_preview()

    def cage_move_all(self, delta: QPointF) -> None:
        """整体平移笼（拖边/拖笼内部）：把所有把手在**按下时的快照**上位移。

        必须基于快照位移，不能逐帧累加——否则每帧都从"当前值"再位移一次，
        手一停位置就漂（浮点累积）。
        """
        if self._cage_drag_origin is None:
            return
        _start, snapshot = self._cage_drag_origin
        self._cage_handles = [
            (a, self._clamp_cage_pos(QPointF(b.x() + delta.x(), b.y() + delta.y())))
            for a, b in snapshot]
        self._sync_cage_overlay()
        self._refresh_cage_preview()

    def _hit_cage_handle(self, view_point: QPointF) -> int | None:
        """命中哪个把手（视口坐标，按当前倍率换算命中半径）。"""
        if not self._cage_handles:
            return None
        radius = CAGE_HIT_VIEW_PX
        best, best_d2 = None, radius * radius
        for i, (_origin, cur) in enumerate(self._cage_handles):
            vp = QPointF(self.mapFromScene(cur))
            d2 = (vp.x() - view_point.x()) ** 2 + (vp.y() - view_point.y()) ** 2
            if d2 <= best_d2:
                best, best_d2 = i, d2
        return best

    def _hit_cage_body(self, scene_point: QPointF) -> bool:
        """命中笼内部/边（用于整体平移）。用原位上构建的多边形判定。"""
        if not self._cage_handles:
            return False
        poly = QPolygonF([a for a, _b in self._cage_handles])
        if poly.containsPoint(scene_point, Qt.FillRule.OddEvenFill):
            return True
        # 边缘带宽：到任一条边的距离在阈值内也算（贴着边拖更好抓）
        tol = CAGE_EDGE_BAND_VIEW_PX / max(1e-6, self._zoom)
        n = len(poly)
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            if _dist_to_segment(scene_point, a, b) <= tol:
                return True
        return False

    # ---- 「校正」（四点透视摆正） ----
    def _ensure_quad(self) -> None:
        """（不发信号）没四边形时按当前整幅图建一个（四角 = 图四角）。"""
        if self._image is None or self._image.isNull():
            self._rect_quad = []
            return
        if self._rect_quad:
            return
        rect = self.image_rect()
        self._rect_quad = [QPointF(rect.left(), rect.top()),
                      QPointF(rect.right(), rect.top()),
                      QPointF(rect.right(), rect.bottom()),
                      QPointF(rect.left(), rect.bottom())]

    def reset_quad(self) -> None:
        """「重置」：四角回到整幅图四角（丢掉未应用的校正）。"""
        self._clear_deform_preview()
        self._rect_quad = []
        self._rect_drag = None
        self._rect_hover = None
        self._ensure_quad()
        self._sync_quad_overlay()
        self._sync_cursor()

    def quad(self) -> list:
        """当前四边形四角副本（``QPointF`` 列表）——给自测与外部读。"""
        self._ensure_quad()
        return [QPointF(p) for p in self._rect_quad]

    def rectify_ratio(self) -> str:
        """目标矩形宽高比口径（见 RECTIFY_RATIO_CHOICES）。"""
        return self._rectify_ratio

    def set_rectify_ratio(self, mode: str) -> None:
        """改目标矩形口径：只影响**之后的**预览，不必丢掉当前四角。"""
        self._rectify_ratio = mode
        self._refresh_deform_preview(force=True)
        self._sync_quad_overlay()

    def quad_move(self, index: int, pos: QPointF) -> None:
        """把第 ``index`` 个角拖到 ``pos``（图片坐标）。

        ⚠️ **允许拖到图片外面**（四角要能框住"拍摄时把纸张也拍进来了"的
        边界）。只留一个"一张图那么远"的宽松上限，免得角点被甩丢。
        """
        self._ensure_quad()
        if not 0 <= index < 4:
            return
        limit = self.image_rect()
        off_x, off_y = limit.width(), limit.height()
        clamped = QPointF(
            max(limit.left() - off_x, min(pos.x(), limit.right() + off_x)),
            max(limit.top() - off_y, min(pos.y(), limit.bottom() + off_y)))
        self._rect_quad[index] = clamped
        self._rect_hover = index
        self._sync_quad_overlay()
        self._refresh_deform_preview()

    def _hit_quad(self, view_pos: QPointF) -> int | None:
        """命中四角手柄（视图像素口径，不随缩放变）。"""
        self._ensure_quad()
        for index, point in enumerate(self._rect_quad):
            spot = QPointF(self.mapFromScene(point))
            if QLineF(view_pos, spot).length() <= QUAD_HIT_VIEW_PX:
                return index
        return None

    def quad_pending(self):
        """未应用的校正 ``(quad, mode)``；四角没动过则 None。"""
        self._ensure_quad()
        if len(self._rect_quad) != 4:
            return None
        rect = self.image_rect()
        rest = [(rect.left(), rect.top()), (rect.right(), rect.top()),
                (rect.right(), rect.bottom()), (rect.left(), rect.bottom())]
        if not quad_moved(rest, [(p.x(), p.y()) for p in self._rect_quad]):
            return None
        return ([(p.x(), p.y()) for p in self._rect_quad], self._rectify_ratio)

    def _sync_quad_overlay(self) -> None:
        """四角手柄的显隐与位置刷新（只在「校正」工具下显示）。"""
        show = (self._tool == "rectify" and self._item is not None
                and len(self._rect_quad) == 4)
        if not show:
            self._rect_poly.hide()
            for item in self._rect_dots:
                item.hide()
            return
        self._rect_poly.show()
        path = QPainterPath()
        path.moveTo(self._rect_quad[0])
        for point in self._rect_quad[1:]:
            path.lineTo(point)
        path.closeSubpath()
        self._rect_poly.setPath(path)
        half = QUAD_HANDLE_VIEW_PX / max(self._zoom, 1e-6)
        for index, item in enumerate(self._rect_dots):
            point = self._rect_quad[index]
            item.setRect(QRectF(point.x() - half, point.y() - half,
                                half * 2, half * 2))
            big = index == self._rect_hover
            item.setBrush(QBrush(QColor(T.ACCENT_HOVER if big else T.ACCENT)))
            item.show()

    # ---- 像素预览（降采样 + 节流） ----
    def _clear_deform_preview(self) -> None:
        """丢掉像素预览浮层，并把节流时间戳一并清零。

        ⚠️ 清预览 = 「已经没有待应用的形变了」，所以下一次拖动是**全新的一轮**，
        必须立刻出画。若只删浮层、留下 ``_deform_painted_at``，那么刚
        「重置 / 应用变形 / 采用图钉」完紧接着拖的**第一次**会被
        :data:`DEFORM_PREVIEW_INTERVAL` 的窗口吃掉——用户拖了半天画面一动不动，
        松开手才突然跳出来（真实踩到：这就是 ``fit()`` 空转那一类，见
        :meth:`_refresh_deform_preview` 的注释；这里把 reset/adopt 这条路径也堵上）。
        """
        self._deform_painted_at = 0.0
        if self._deform_item is not None:
            self._scene.removeItem(self._deform_item)
            self._deform_item = None
        # ⚠️ 底图上被挖空的框必须回填：不清的话预览浮层没了、原图却留着个
        #    白洞（用户会看到"图被啃掉一块"）。
        if self._preview_cutout is not None:
            self._paint_canvas_cutout(None)
        # 浮层没了 → 场景矩形收回图片边界（grow 时曾为图外内容扩过）
        self._sync_scene_rect()

    def _clear_cage_preview(self) -> None:
        """丢掉变换笼的像素预览浮层，并把节流时间戳一并清零。

        与 :meth:`_clear_deform_preview` 同理：清预览 = 「已经没有待应用的
        形变了」，下一次拖动是全新一轮，必须立刻出画（否则重置/应用后紧接着
        拖的第一次会被节流窗口吃掉）。
        """
        self._cage_preview_at = 0.0
        if self._cage_preview_item is not None:
            self._scene.removeItem(self._cage_preview_item)
            self._cage_preview_item = None
        # ⚠️ 同 :meth:`_clear_deform_preview`：底图上被挖空的框必须回填，
        #    否则预览浮层没了、原图却留着个白洞。
        if self._preview_cutout is not None:
            self._paint_canvas_cutout(None)
        # 浮层没了 → 场景矩形收回图片边界（grow 时曾为图外内容扩过）
        self._sync_scene_rect()

    def _refresh_cage_preview(self, force: bool = False) -> None:
        """重算变换笼的像素预览浮层。

        与 :meth:`_refresh_deform_preview` 同构：

        - **范围**：``grow=True`` 时形变结果可能落到原图边界**之外**，所以预览
          按**整幅图**降采样后整体重算（:func:`deform_qimage` 的 grow 模式），
          浮层覆盖"原图 ∪ 图外内容"；底图整张挖空，由浮层完整呈现（用户
          2026-10-02：「超出原本区域的不要截，最终结果按最后图片的范围」）。
          场景矩形同步扩到浮层范围，图外那块才看得见；
        - **分辨率**：按 :func:`cage_preview_scale` 降采样，拖动中取
          :data:`CAGE_PREVIEW_PIXELS`，``force``（松手）取
          :data:`CAGE_PREVIEW_SETTLE_PIXELS`；
        - **时间**：:data:`CAGE_PREVIEW_INTERVAL` 之内不重复算（``force`` 跳过）。

        笼把手（覆盖层）每帧都跟手，与这里的节拍无关。
        """
        if self._image is None or not self._cage_handles:
            self._clear_cage_preview()
            return
        src = self.cage_source()
        dst = self.cage_target()
        src_xy = [(p.x(), p.y()) for p in src]
        dst_xy = [(p.x(), p.y()) for p in dst]
        if not cage_moved(src_xy, dst_xy):
            self._clear_cage_preview()
            return
        now = time.monotonic()
        if not force and now - self._cage_preview_at < CAGE_PREVIEW_INTERVAL:
            return
        width, height = self._image.width(), self._image.height()
        # grow 后内容可能落到原边界之外，预览也必须把外面那块画出来（否则
        # 松手落地时"画面突然多出一块"，与预览对不上）。所以这里按**整幅图**
        # 的预算降采样（同 deform），而不是只算影响框。
        scale = cage_preview_scale(
            width, height,
            self._zoom * max(1.0, self.devicePixelRatioF()),
            CAGE_PREVIEW_SETTLE_PIXELS if force else CAGE_PREVIEW_PIXELS)
        scale = min(1.0, scale)
        if scale >= 1.0:
            source = self._image
            src_s = [(p.x(), p.y()) for p in src]
            dst_s = [(p.x(), p.y()) for p in dst]
        else:
            source = self._image.scaled(
                max(1, int(round(width * scale))),
                max(1, int(round(height * scale))),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            src_s = [(p.x() * scale, p.y() * scale) for p in src]
            dst_s = [(p.x() * scale, p.y() * scale) for p in dst]
        preview, origin_s = deform_qimage(source, src_s, dst_s, grow=True)
        if preview is None or preview.isNull():
            self._clear_cage_preview()
            return
        pixmap = QPixmap.fromImage(preview)
        pixmap.setDevicePixelRatio(1.0)
        if self._cage_preview_item is None:
            self._cage_preview_item = QGraphicsPixmapItem()
            self._cage_preview_item.setZValue(4)  # 底图之上、覆盖层（11+）之下
            self._cage_preview_item.setTransformationMode(
                Qt.TransformationMode.SmoothTransformation)
            self._scene.addItem(self._cage_preview_item)
        self._cage_preview_item.setPixmap(pixmap)
        self._cage_preview_item.setPos(origin_s[0] / scale, origin_s[1] / scale)
        self._cage_preview_item.setScale(1.0 / scale)
        # ⚠️ 底图上把**原图整块**挖空：形变结果（含图外那块）由浮层完整呈现，
        #    底图若不挖空，原内容会从浮层底下透出来（用户 2026-10-02 报的重影）。
        #    grow 后浮层覆盖范围 ≥ 原图，所以直接挖整张原图即可。
        self._paint_canvas_cutout(QRect(0, 0, width, height))
        # 场景矩形要扩到"原图 ∪ 浮层"：否则图外那块内容被视口裁掉、看不见
        # （用户 2026-10-02：超出原边界的内容不能丢——预览也要看得见）。
        self._sync_scene_rect()
        self._cage_preview_at = now

    def _refresh_deform_preview(self, force: bool = False) -> None:
        """重算"形变后"的像素预览（浮层）。

        ⚠️ 两重降本（缺一不可）：形变是逐像素重映射，源图是整页 4000×3000
        时全分辨率一次要秒级（实测见 ``utils.puppet_warp``）。

        - **分辨率**：按 :func:`cage_preview_scale` 降采样——它同时卡"屏幕
          上够清楚"和"工作量有上限"。拖动中取 :data:`DEFORM_PREVIEW_PIXELS`
          （~80ms），``force`` 时取 :data:`DEFORM_PREVIEW_SETTLE_PIXELS`
          （松手了，停下来看清楚）。⚠️ 预算按**整幅图**面积算，因为下面
          ``bake_puppet`` 是拿整张降采样图做的映射；
        - **时间**：:data:`DEFORM_PREVIEW_INTERVAL` 之内不重复算（``force`` 跳过）。

        ⚠️ ``grow=True``：ARAP 网格被拖出原边界时预览**整体重算并显示图外
        那块**——不再按 :func:`mesh_region` 裁框（ARAP 的位移场缓慢衰减、
        整图 96~98% 受影响，裁框只省 ~4%，见 ``utils.puppet_warp``）。浮层
        覆盖"原图 ∪ 图外内容"，底图整张挖空，场景矩形同步扩大。

        图钉（覆盖层）每帧都跟手，与这里的节拍无关。
        """
        if self._tool == "rectify":
            self._refresh_rectify_preview(force=force)
            return
        if self._image is None or self._mesh is None or not self._pins:
            return
        now = time.monotonic()
        if not force and now - self._deform_painted_at < DEFORM_PREVIEW_INTERVAL:
            return
        # force（松手补帧）用精网格解到收敛；拖动中用粗网格近似解（跟手）
        solved = self._solve_pins(drag=not force)
        if solved is None:
            # 没干活就不算"刚画过"：``_clear_deform_preview`` 会把时间戳清零，
            # 否则紧接着的第一次真拖动会被节流窗口吃掉，用户拖了半天画面
            # 一动不动（真实踩到：fit() 里的空转把时间戳刷成了"刚画"）。
            self._clear_deform_preview()
            return
        vertices, moved, triangles = solved
        if not mesh_moved(vertices, moved):
            self._clear_deform_preview()
            return
        width, height = self._image.width(), self._image.height()

        # 场景 1 单位 = 屏幕上 zoom × dpr 个设备像素（见 cage_preview_scale）。
        # ⚠️ 成本预算按**整幅图**的面积算，不是按 mesh_region 的框——因为
        #    bake_puppet 是拿**整张降采样图**去做的映射（不是只处理框内），
        #    所以真实工作量 = width×height×scale²。早前按框面积算，预算
        #    20 万实际会重映射到 27 万（框只占整图 ~95% 也差这么多，因为
        #    scale 被同时乘到了整幅），实测帧时间比预期高 30%（自测/基准
        #    逮到）。这里显式按整图面积给出 scale。
        scale = cage_preview_scale(
            width, height,
            self._zoom * max(1.0, self.devicePixelRatioF()),
            DEFORM_PREVIEW_SETTLE_PIXELS if force else DEFORM_PREVIEW_PIXELS)
        if scale >= 1.0:
            source = self._image
        else:
            source = self._image.scaled(
                max(1, int(round(width * scale))),
                max(1, int(round(height * scale))),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        # grow：图钉被拖出原边界时预览也要把外面那块画出来（否则松手落地
        # 时"画面突然多出一块"，与预览对不上）。
        warped, origin_s = bake_puppet(source, vertices * scale, moved * scale,
                                       triangles, grow=True)
        if warped is None or warped.isNull():
            self._clear_deform_preview()
            return
        pixmap = QPixmap.fromImage(warped)
        pixmap.setDevicePixelRatio(1.0)
        if self._deform_item is None:
            self._deform_item = QGraphicsPixmapItem()
            self._deform_item.setZValue(4)  # 底图之上、覆盖层（11+）之下
            self._deform_item.setTransformationMode(
                Qt.TransformationMode.SmoothTransformation)
            self._scene.addItem(self._deform_item)
        self._deform_item.setPixmap(pixmap)
        self._deform_item.setPos(origin_s[0] / scale, origin_s[1] / scale)
        self._deform_item.setScale(1.0 / scale)
        # ⚠️ 底图上把**整张原图**挖空：grow 后浮层覆盖范围 ≥ 原图，由浮层
        #    完整呈现（含图外那块）；不挖空的话原像素会从浮层底下透出来
        #    （"图片变换了，原图还在背景上面"）。
        self._paint_canvas_cutout(QRect(0, 0, width, height))
        # 场景矩形扩到"原图 ∪ 浮层"，图外那块才看得见
        self._sync_scene_rect()
        self._deform_painted_at = now

    def _refresh_rectify_preview(self, force: bool = False) -> None:
        """重算「校正」的像素预览：把四角框住的区域透视摆正后贴回原位置。

        ⚠️ 与「变形」的预览不同：校正会**改变尺寸**（摆正后是目标矩形），
        所以浮层不是"贴原尺寸的框"，而是"贴在源四边形的框里、显示摆正后的
        内容"——所见即应用后那块的去向（应用后整图会被换成摆正图）。
        """
        if self._image is None:
            self._clear_deform_preview()
            return
        pending = self.quad_pending()
        if pending is None:
            self._clear_deform_preview()
            return
        now = time.monotonic()
        if not force and now - self._deform_painted_at < DEFORM_PREVIEW_INTERVAL:
            return
        quad, mode = pending
        width, height = self._image.width(), self._image.height()
        x0, y0, _out_w, _out_h = rectify_region(quad, width, height, mode=mode)
        # 同 deform：预算按**整幅图**面积算（rectify_qimage 也是拿整张降采样
        # 图去重的映射，真实工作量 = width×height×scale²，见上方说明）。
        scale = cage_preview_scale(
            width, height,
            self._zoom * max(1.0, self.devicePixelRatioF()),
            DEFORM_PREVIEW_SETTLE_PIXELS if force else DEFORM_PREVIEW_PIXELS)
        if scale >= 1.0:
            source = self._image
            quad_scaled = quad
        else:
            source = self._image.scaled(
                max(1, int(round(width * scale))),
                max(1, int(round(height * scale))),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            quad_scaled = [(px * scale, py * scale) for px, py in quad]
        try:
            warped = rectify_qimage(source, quad_scaled, out_size=None,
                                    mode=mode)
        except ValueError:
            self._clear_deform_preview()
            return
        pixmap = QPixmap.fromImage(warped)
        pixmap.setDevicePixelRatio(1.0)
        if self._deform_item is None:
            self._deform_item = QGraphicsPixmapItem()
            self._deform_item.setZValue(4)
            self._deform_item.setTransformationMode(
                Qt.TransformationMode.SmoothTransformation)
            self._scene.addItem(self._deform_item)
        self._deform_item.setPixmap(pixmap)
        self._deform_item.setPos(x0, y0)
        self._deform_item.setScale(1.0 / scale)
        self._deform_painted_at = now

    def _build_overlay(self) -> None:
        """遮罩 4 块 + 选区边框 + 8 手柄，建好藏起来，按需显示。"""
        self._border = None  # 纸边框（set_image 建）
        mask_brush = QBrush(QColor(0, 0, 0, 110))
        self._mask: list[QGraphicsRectItem] = []
        for _ in range(4):
            item = QGraphicsRectItem()
            item.setBrush(mask_brush)
            item.setPen(QPen(Qt.PenStyle.NoPen))
            item.setZValue(10)
            item.hide()
            self._scene.addItem(item)
            self._mask.append(item)
        self._sel_border = QGraphicsRectItem()
        self._sel_border.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._sel_border.setPen(QPen(QColor(T.ACCENT), 0, Qt.PenStyle.DashLine))
        self._sel_border.setZValue(11)
        self._sel_border.hide()
        self._scene.addItem(self._sel_border)
        # 变换工具的**四边形**选框（跟随累计矩阵变形，虚线同款样式）
        self._quad = QGraphicsPolygonItem()
        self._quad.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._quad.setPen(QPen(QColor(T.ACCENT), 0, Qt.PenStyle.DashLine))
        self._quad.setZValue(11)
        self._quad.hide()
        self._scene.addItem(self._quad)
        self._handles: dict[str, QGraphicsRectItem] = {}
        handle_pen = QPen(QColor("#ffffff"), 0)
        handle_brush = QBrush(QColor(T.ACCENT))
        for name in ("tl", "t", "tr", "l", "r", "bl", "b", "br"):
            item = QGraphicsRectItem()
            item.setBrush(handle_brush)
            item.setPen(handle_pen)
            item.setZValue(12)
            item.hide()
            self._scene.addItem(item)
            self._handles[name] = item
        # 悬停/拖动中的**边界高亮线**（每条选区边一根；可见性由
        # _apply_hover_highlight 管，几何在 _sync_overlay 里跟选区走）
        self._edge_lines: dict[str, QGraphicsLineItem] = {}
        edge_pen = QPen(QColor(T.ACCENT), 0)
        edge_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        for name in ("l", "r", "t", "b"):
            item = QGraphicsLineItem()
            item.setPen(edge_pen)
            item.setZValue(13)
            item.hide()
            self._scene.addItem(item)
            self._edge_lines[name] = item
        # 变换**轴心**圆点（画在最上层，可拖动）
        self._pivot_item = QGraphicsEllipseItem()
        self._pivot_item.setBrush(QBrush(QColor(T.ACCENT)))
        self._pivot_item.setPen(QPen(QColor("#ffffff"), 0))
        self._pivot_item.setZValue(14)
        self._pivot_item.hide()
        self._scene.addItem(self._pivot_item)
        # 橡皮擦**光标圈**：直径恒等于实际擦除直径（场景坐标 = 图片像素，
        # 缩放天然跟随），圈到哪里擦到哪里（用户 2026-10-01：光标大小要和
        # 划线一致）。外圈深色 3 设备像素 + 内圈白 1 设备像素，白纸黑底都
        # 看得见；pen 用 cosmetic——线宽按设备像素，任何缩放下都是恒定细线。
        self._eraser_ring: list[QGraphicsEllipseItem] = []
        for color, width in (("#3a3f4b", 3.0), ("#ffffff", 1.0)):
            item = QGraphicsEllipseItem()
            pen = QPen(QColor(color))
            pen.setCosmetic(True)
            pen.setWidthF(width)
            item.setPen(pen)
            item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            item.setZValue(15)
            item.hide()
            self._scene.addItem(item)
            self._eraser_ring.append(item)
        # 文字块**边界虚线框**：悬停在块上/拖动中显示"这一块的范围"，
        # 松手即消失（用户 2026-10-01 手机作图式文字）
        self._text_outline = QGraphicsRectItem()
        self._text_outline.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._text_outline.setPen(QPen(QColor(T.ACCENT), 0, Qt.PenStyle.DashLine))
        self._text_outline.setZValue(18)
        self._text_outline.hide()
        self._scene.addItem(self._text_outline)
        # 「变形」的**图钉**：每个图钉一根"钉子"（原点→当前位置的细线，
        # 拖远时看得出内容被从哪儿扯过来）+ 一个圆点。钉子用区分色，
        # 拖远时不会和图片内容糊在一起。
        self._pin_tail = QGraphicsPathItem()
        self._pin_tail.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        tail_pen = QPen(QColor(T.INK_FAINT), 0, Qt.PenStyle.DotLine)
        tail_pen.setCosmetic(True)
        self._pin_tail.setPen(tail_pen)
        self._pin_tail.setZValue(11)
        self._pin_tail.hide()
        self._scene.addItem(self._pin_tail)
        #: 图钉圆点（数量随用户增删，按需增删）
        self._pin_dots: list[QGraphicsEllipseItem] = []
        # 「校正」的**四角手柄**：一个四边形轮廓 + 4 个方块角点。
        # 轮廓画源四边形（要摆正的区域），方块是抓点。
        self._rect_poly = QGraphicsPathItem()
        self._rect_poly.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        quad_pen = QPen(QColor(T.ACCENT), 0, Qt.PenStyle.DashLine)
        quad_pen.setCosmetic(True)
        self._rect_poly.setPen(quad_pen)
        self._rect_poly.setZValue(13)
        self._rect_poly.hide()
        self._scene.addItem(self._rect_poly)
        #: 四个方块角点
        self._rect_dots: list[QGraphicsRectItem] = []
        for _ in range(4):
            item = QGraphicsRectItem()
            item.setPen(QPen(QColor("#ffffff"), 0))
            item.setBrush(QBrush(QColor(T.ACCENT)))
            item.setZValue(14)
            item.hide()
            self._scene.addItem(item)
            self._rect_dots.append(item)
        # 「变换笼」的**边框**：闭合折线（原位实线 + 当前位置虚线）。
        # 原位实线让人看见"笼本来贴在哪"，当前位置虚线是拖到的地方。
        self._cage_src_poly = QGraphicsPathItem()
        self._cage_src_poly.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        src_pen = QPen(QColor(T.INK_FAINT), 0, Qt.PenStyle.DotLine)
        src_pen.setCosmetic(True)
        self._cage_src_poly.setPen(src_pen)
        self._cage_src_poly.setZValue(11)
        self._cage_src_poly.hide()
        self._scene.addItem(self._cage_src_poly)
        self._cage_dst_poly = QGraphicsPathItem()
        self._cage_dst_poly.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        dst_pen = QPen(QColor(T.ACCENT), 0, Qt.PenStyle.DashLine)
        dst_pen.setCosmetic(True)
        self._cage_dst_poly.setPen(dst_pen)
        self._cage_dst_poly.setZValue(12)
        self._cage_dst_poly.hide()
        self._scene.addItem(self._cage_dst_poly)
        #: 笼把手圆点（数量随密度档位变，按需增删）
        self._cage_dots: list[QGraphicsEllipseItem] = []

    def _move_eraser_ring(self, pos: QPointF, show: bool = True) -> None:
        """橡皮擦圈挪到 ``pos``（图片坐标，圈心 = 笔刷中心 = 光标处）。"""
        self._eraser_pos = QPointF(pos)
        radius = self._erase_size / 2.0
        rect = QRectF(pos.x() - radius, pos.y() - radius,
                      self._erase_size, self._erase_size)
        for item in self._eraser_ring:
            item.setRect(rect)
            item.setVisible(show and self._item is not None)

    def _hide_eraser_ring(self) -> None:
        for item in self._eraser_ring:
            item.hide()

    def _handle_boxes(self, rect: QRectF) -> dict[str, QRectF]:
        """8 个手柄的图片坐标框（视觉尺寸 = 视图像素 ÷ 当前倍率）。"""
        hs = HANDLE_VIEW_PX / max(self._zoom, 1e-6)
        cx, cy = rect.center().x(), rect.center().y()
        anchors = {
            "tl": rect.topLeft(), "t": QPointF(cx, rect.top()),
            "tr": rect.topRight(), "l": QPointF(rect.left(), cy),
            "r": QPointF(rect.right(), cy), "bl": rect.bottomLeft(),
            "b": QPointF(cx, rect.bottom()), "br": rect.bottomRight(),
        }
        return {
            name: QRectF(point.x() - hs / 2, point.y() - hs / 2, hs, hs)
            for name, point in anchors.items()
        }

    def _sync_overlay(self) -> None:
        """按当前选区刷新遮罩/边框/手柄几何与可见性。"""
        if (self._tool == "transform" and self._rect is not None
                and self._image is not None):
            self._sync_transform_overlay()
            return
        if self._tool == "deform" and self._image is not None:
            self._sync_pin_overlay()
            return
        if self._tool == "cage" and self._image is not None:
            self._sync_cage_overlay()
            return
        if self._tool == "rectify" and self._image is not None:
            self._sync_quad_overlay()
            return
        visible = (
            self._tool == "crop"
            and self._rect is not None and self._image is not None
        )
        if not visible:
            for item in self._mask:
                item.setVisible(False)
            self._sel_border.setVisible(False)
            self._quad.setVisible(False)
            self._pivot_item.setVisible(False)
            self._cage_src_poly.setVisible(False)
            self._cage_dst_poly.setVisible(False)
            for item in self._cage_dots:
                item.setVisible(False)
            for item in self._handles.values():
                item.setVisible(False)
            for item in self._edge_lines.values():
                item.setVisible(False)
            return
        rect = self._rect.normalized()
        full = self.image_rect()
        # 遮罩 = 选区外的四块（夹一下防越界出负宽）
        self._mask[0].setRect(QRectF(
            full.left(), full.top(), full.width(),
            max(0.0, rect.top() - full.top())))
        self._mask[1].setRect(QRectF(
            full.left(), rect.bottom(), full.width(),
            max(0.0, full.bottom() - rect.bottom())))
        self._mask[2].setRect(QRectF(
            full.left(), rect.top(), max(0.0, rect.left() - full.left()),
            rect.height()))
        self._mask[3].setRect(QRectF(
            rect.right(), rect.top(),
            max(0.0, full.right() - rect.right()), rect.height()))
        for item in self._mask:
            item.setVisible(True)
        self._sel_border.setRect(rect)
        self._sel_border.setVisible(True)
        self._quad.setVisible(False)
        self._pivot_item.setVisible(False)
        for name, box in self._handle_boxes(rect).items():
            self._handles[name].setRect(box)
            self._handles[name].setVisible(True)
        # 边缘高亮线的几何跟着选区走（可见性由悬停/拖动状态管）
        lines = {
            "l": QLineF(rect.topLeft(), rect.bottomLeft()),
            "r": QLineF(rect.topRight(), rect.bottomRight()),
            "t": QLineF(rect.topLeft(), rect.topRight()),
            "b": QLineF(rect.bottomLeft(), rect.bottomRight()),
        }
        for name, line in lines.items():
            item = self._edge_lines[name]
            pen = item.pen()
            pen.setWidthF(3.0 / max(self._zoom, 1e-6))  # 恒 ≈3 视图像素
            item.setPen(pen)
            item.setLine(line)
        self._apply_hover_highlight()

    def _transform_quad(self) -> dict[str, QPointF]:
        """变换后选区四角（图片坐标）：8 手柄与命中测试的几何来源。"""
        rect = (self._xf_rect or self._rect).normalized()
        xf = self._xf
        return {
            "tl": xf.map(rect.topLeft()), "tr": xf.map(rect.topRight()),
            "br": xf.map(rect.bottomRight()), "bl": xf.map(rect.bottomLeft()),
        }

    def _sync_transform_overlay(self) -> None:
        """变换工具的覆盖层：四边形选框 + 8 手柄（跟随矩阵变形）+ 轴心。"""
        for item in self._mask:
            item.setVisible(False)
        self._sel_border.setVisible(False)
        for item in self._edge_lines.values():
            item.setVisible(False)
        corners = self._transform_quad()
        quad = QPolygonF([corners["tl"], corners["tr"],
                          corners["br"], corners["bl"], corners["tl"]])
        self._quad.setPolygon(quad)
        self._quad.setVisible(True)
        hs = HANDLE_VIEW_PX / max(self._zoom, 1e-6)
        points = {
            "tl": corners["tl"], "tr": corners["tr"],
            "bl": corners["bl"], "br": corners["br"],
            "t": QPointF((corners["tl"].x() + corners["tr"].x()) / 2,
                         (corners["tl"].y() + corners["tr"].y()) / 2),
            "b": QPointF((corners["bl"].x() + corners["br"].x()) / 2,
                         (corners["bl"].y() + corners["br"].y()) / 2),
            "l": QPointF((corners["tl"].x() + corners["bl"].x()) / 2,
                         (corners["tl"].y() + corners["bl"].y()) / 2),
            "r": QPointF((corners["tr"].x() + corners["br"].x()) / 2,
                         (corners["tr"].y() + corners["br"].y()) / 2),
        }
        for name, point in points.items():
            self._handles[name].setRect(
                QRectF(point.x() - hs / 2, point.y() - hs / 2, hs, hs))
            self._handles[name].setVisible(True)
        pivot = self._xf.map(self._xf_pivot)
        pr = PIVOT_VIEW_PX / 2.0 / max(self._zoom, 1e-6)
        self._pivot_item.setRect(
            QRectF(pivot.x() - pr, pivot.y() - pr, pr * 2, pr * 2))
        self._pivot_item.setVisible(True)


    # ---- 「变形」的覆盖层 ----
    def _sync_pin_overlay(self) -> None:
        """变形工具的覆盖层：图钉圆点 + 原点连线。

        与变换/裁剪的覆盖层互斥（:meth:`_sync_overlay` 早返回），所以这里
        先把那些元素全部藏掉，再画自己的。
        """
        for item in self._mask:
            item.setVisible(False)
        self._sel_border.setVisible(False)
        self._quad.setVisible(False)
        self._pivot_item.setVisible(False)
        for item in self._handles.values():
            item.setVisible(False)
        for item in self._edge_lines.values():
            item.setVisible(False)
        self._sync_pin_dots()

    def _sync_pin_dots(self) -> None:
        """按图钉数增删/摆放圆点与连线（视觉尺寸 = 视图像素 ÷ 当前倍率）。

        悬停/拖动中的图钉放大一圈：抓没抓住看圆点大小就知道。
        图钉的**原点**（网格参考顶点位置）与当前位置不同时，画一根点线相连
        ——把图钉拖远后才看得出内容是从哪儿被扯过来的。
        """
        zoom = max(self._zoom, 1e-6)
        base = PIN_NODE_VIEW_PX / 2.0 / zoom
        hovered = base * 1.5
        while len(self._pin_dots) < len(self._pins):
            item = QGraphicsEllipseItem()
            item.setZValue(13)
            self._scene.addItem(item)
            self._pin_dots.append(item)
        while len(self._pin_dots) > len(self._pins):
            self._scene.removeItem(self._pin_dots.pop())
        tail_path = QPainterPath()
        vertices = self._mesh[0] if self._mesh is not None else None
        any_tail = False
        for index, (vertex, point) in enumerate(self._pins):
            item = self._pin_dots[index]
            big = (index == self._pin_hover)
            radius = hovered if big else base
            item.setRect(QRectF(point.x() - radius, point.y() - radius,
                                radius * 2, radius * 2))
            item.setBrush(QBrush(QColor(T.ACCENT_HOVER if big else T.ACCENT)))
            item.setPen(QPen(QColor("#ffffff"), 0))
            item.setVisible(True)
            if vertices is not None and 0 <= vertex < len(vertices):
                origin = QPointF(float(vertices[vertex, 0]),
                                 float(vertices[vertex, 1]))
                if QLineF(origin, point).length() > 1e-6:
                    tail_path.moveTo(origin)
                    tail_path.lineTo(point)
                    any_tail = True
        self._pin_tail.setPath(tail_path)
        self._pin_tail.setVisible(any_tail)

    # ---- 「变换笼」的覆盖层 ----
    def _sync_cage_overlay(self) -> None:
        """变换笼的覆盖层：原位虚点线 + 当前位置虚线 + 把手圆点。

        与变形/变换/校正的覆盖层互斥（:meth:`_sync_overlay` 早返回），所以
        这里先把那些元素全部藏掉，再画自己的。
        """
        for item in self._mask:
            item.setVisible(False)
        self._sel_border.setVisible(False)
        self._quad.setVisible(False)
        self._pivot_item.setVisible(False)
        for item in self._handles.values():
            item.setVisible(False)
        for item in self._edge_lines.values():
            item.setVisible(False)
        self._sync_cage_dots()

    def _sync_cage_dots(self) -> None:
        """按把手数增删/摆放圆点与两条闭合折线（视觉尺寸 = 视图像素 ÷ 倍率）。

        悬停/拖动中的把手放大一圈：抓没抓住看圆点大小就知道。原位（笼贴图
        边的矩形）画点线、当前位置画虚线——拖出去之后一眼能看出内容是从哪
        儿被扯过来的（RBF 笼的影响半径围绕原位，与 puppet warp 语义相同）。
        """
        self._ensure_cage()
        zoom = max(self._zoom, 1e-6)
        base = CAGE_HANDLE_VIEW_PX / 2.0 / zoom
        hovered = base * 1.5
        while len(self._cage_dots) < len(self._cage_handles):
            item = QGraphicsEllipseItem()
            item.setPen(QPen(QColor("#ffffff"), 0))
            item.setZValue(13)
            self._scene.addItem(item)
            self._cage_dots.append(item)
        while len(self._cage_dots) > len(self._cage_handles):
            self._scene.removeItem(self._cage_dots.pop())
        src_path = QPainterPath()
        dst_path = QPainterPath()
        src_pts = [a for a, _b in self._cage_handles]
        dst_pts = [b for _a, b in self._cage_handles]
        if src_pts:
            src_path.moveTo(src_pts[0])
            dst_path.moveTo(dst_pts[0])
            for pt in src_pts[1:]:
                src_path.lineTo(pt)
            for pt in dst_pts[1:]:
                dst_path.lineTo(pt)
            src_path.closeSubpath()
            dst_path.closeSubpath()
        self._cage_src_poly.setPath(src_path)
        self._cage_dst_poly.setPath(dst_path)
        moved = any(QLineF(a, b).length() > 1e-6
                    for a, b in self._cage_handles)
        self._cage_src_poly.setVisible(bool(src_pts) and moved)
        self._cage_dst_poly.setVisible(bool(dst_pts))
        for index, (_origin, point) in enumerate(self._cage_handles):
            item = self._cage_dots[index]
            big = (index == self._cage_hover) or (index == self._cage_drag)
            radius = hovered if big else base
            item.setRect(QRectF(point.x() - radius, point.y() - radius,
                                radius * 2, radius * 2))
            item.setBrush(QBrush(QColor(T.ACCENT_HOVER if big else T.ACCENT)))
            item.setVisible(True)

    def _hit_transform(self, view_pos: QPointF) -> str:
        """变换工具命中测试（视图像素口径，不随缩放变）。

        优先级：轴心 → 角手柄 → 边手柄 → 框内（移动）→ 框外（旋转）。
        """
        if self._rect is None:
            return "outside"
        corners = self._transform_quad()
        pivot = self._xf.map(self._xf_pivot)
        pivot_v = self.mapFromScene(pivot)
        if (QLineF(view_pos, QPointF(pivot_v)).length()
                <= PIVOT_VIEW_PX / 2.0 + 3.0):
            return "pivot"
        view = {name: QPointF(self.mapFromScene(pt))
                for name, pt in corners.items()}
        # 角：方形盒；边：中线点盒 + 整条边的距离带（拖着顺手）
        box = HANDLE_VIEW_PX * 0.9
        for name, pt in view.items():
            if abs(view_pos.x() - pt.x()) <= box \
                    and abs(view_pos.y() - pt.y()) <= box:
                return name
        edges = {
            "t": (view["tl"], view["tr"]), "r": (view["tr"], view["br"]),
            "b": (view["br"], view["bl"]), "l": (view["bl"], view["tl"]),
        }
        for name, (a, b) in edges.items():
            mid = (a + b) / 2.0
            if (QLineF(view_pos, mid).length()
                    <= HANDLE_VIEW_PX * 0.9):
                return name
        for name, (a, b) in edges.items():
            if _dist_to_segment(view_pos, a, b) <= EDGE_BAND_VIEW_PX:
                return name
        scene = self.mapToScene(view_pos.toPoint())
        if QPolygonF([corners["tl"], corners["tr"],
                      corners["br"], corners["bl"]]).containsPoint(
                scene, Qt.FillRule.OddEvenFill):
            return "inside"
        return "outside"

    # ------------------------------------------------------------ 缩放
    def fit(self, ratio: float | None = None) -> None:
        """适应窗口（整图完整可见）；``ratio`` < 1 时四周留白。

        留白的做法是把"要装进去的矩形"按比例放大——图片因此只占视口的
        ``ratio``（见 :data:`DEFORM_FIT_RATIO`：进「变形」时图片不顶满视口，
        用户才有地方把笼把手往图外拖）。
        """
        if self._item is None or self.viewport().width() <= 1:
            return  # 控件还没布局：此时 fit 算出来的是脏值，等 resizeEvent 再来
        rect = self.image_rect()
        if ratio is None:
            ratio = self._fit_ratio
        ratio = max(0.2, min(1.0, float(ratio)))
        if ratio < 1.0 and not rect.isNull():
            grow_x = rect.width() * (1.0 / ratio - 1.0) / 2.0
            grow_y = rect.height() * (1.0 / ratio - 1.0) / 2.0
            rect = rect.adjusted(-grow_x, -grow_y, grow_x, grow_y)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.transform().m11()))
        self._user_zoomed = False
        # ⚠️ 手柄的几何 = 视图像素 ÷ 当前倍率，倍率变了必须重算覆盖层；
        #    不然 set_image 时用脏 viewport 算的小倍率会留下巨型手柄
        #    （离屏渲染抓出来的：手柄有 ~150 视图像素，应为 12）。
        self._sync_overlay()
        # 变形预览的清晰度是跟着倍率定的（见 cage_preview_scale）：倍率变了
        # 就重算一次，缩着看整页时能省下几十倍工作量
        self._refresh_deform_preview()

    def set_fit_ratio(self, ratio: float) -> None:
        """设「适应窗口」时图片占视口的比例（1.0 = 铺满，< 1 = 四周留白）。

        只在用户**没手动缩放过**时立刻生效——手动缩放是明确意图，不该被悄悄
        改掉；但他下次点「适应窗口」或改窗口大小时就按新比例来。
        """
        self._fit_ratio = max(0.2, min(1.0, float(ratio)))
        if not self._user_zoomed:
            self.fit()

    def zoom_in(self) -> None:
        """放大一档（工具栏按钮用；无档位表，连续乘 1.25）。"""
        self.set_zoom(self._zoom * 1.25)

    def zoom_out(self) -> None:
        """缩小一档。"""
        self.set_zoom(self._zoom / 1.25)

    def set_zoom(self, zoom: float, anchor_view: QPointF | None = None) -> None:
        """锚点缩放（同预览弹窗的 translate 补偿法，缩放不漂移）。"""
        if self._item is None:
            return
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, float(zoom)))
        if abs(zoom - self._zoom) < 1e-6:
            return
        if anchor_view is None:
            anchor_view = QPointF(self.viewport().rect().center())
        anchor_scene = self.mapToScene(anchor_view.toPoint())
        factor = zoom / self._zoom
        self.scale(factor, factor)
        moved = self.mapToScene(anchor_view.toPoint())
        self.translate(moved.x() - anchor_scene.x(),
                       moved.y() - anchor_scene.y())
        self._zoom = zoom
        self._user_zoomed = True
        self._sync_overlay()  # 手柄视觉尺寸不随缩放变，几何要重算
        self._refresh_deform_preview()  # 同上：预览清晰度跟倍率走（有节流）

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if not self._user_zoomed:
            self.fit()  # 用户没动过缩放：窗口怎么变都保持整图可见

    def fit_selection(self) -> None:
        """视图适配当前选区（选区约占视口 80%，四周留出可操作白边）。

        裁剪区收小后松手时调用——选区变小了就要放大查看（用户 20:18 定）。
        ⚠️ 不填满视口：顶满时选区边界贴着视口边缘，看不到上下文、手柄
        也挤在边上不好抓（用户 20:28 定"缩放至选区时留出边距"）。
        视图从此锚定选区（``_user_zoomed``），窗口 resize 不再拉回整图。
        """
        if self._item is None or self._rect is None:
            return
        rect = self._rect.normalized()
        if rect.isEmpty() or self.viewport().width() <= 1:
            return
        zoom = SEL_FIT_RATIO * min(
            self.viewport().width() / max(1.0, rect.width()),
            self.viewport().height() / max(1.0, rect.height()),
        )
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        self.resetTransform()
        self.scale(zoom, zoom)
        self.centerOn(rect.center())
        self._zoom = zoom
        self._user_zoomed = True
        self._sync_overlay()
        self._refresh_deform_preview()

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if not delta or self._item is None:
            return super().wheelEvent(event)
        self.set_zoom(self._zoom * (WHEEL_STEP ** (delta / 120.0)),
                      event.position())
        event.accept()

    # ------------------------------------------------------------ 交互
    def _apply_hover_highlight(self) -> None:
        """悬停/拖动中的边高亮：命中角手柄时相邻两条边一起亮。"""
        active = (
            self._tool in ("crop", "transform")
            and self._rect is not None
            and self._hover_handle is not None
            and (self._tool == "crop" or self._xf_reshape)
        )
        for name, item in self._edge_lines.items():
            # 名字包含判断对单边/角手柄都成立："tl" 含 "t""l"、"bl" 含 "b""l"
            item.setVisible(active and name in self._hover_handle)

    def _update_hover_cursor(self, view_pos: QPointF) -> None:
        """未拖拽时的悬停反馈：命中边缘给方向缩放光标 + 边界高亮。"""
        if self._tool == "deform" and self._item is not None:
            index = self._hit_pin(view_pos)
            if index != self._pin_hover:
                self._pin_hover = index  # 悬停中的图钉画大一圈
                self._sync_pin_overlay()
            self.viewport().setCursor(
                Qt.CursorShape.SizeAllCursor if index is not None
                else Qt.CursorShape.CrossCursor)
            return
        if self._tool == "rectify" and self._item is not None:
            index = self._hit_quad(view_pos)
            if index != self._rect_hover:
                self._rect_hover = index  # 悬停中的角点画大一圈
                self._sync_quad_overlay()
            self.viewport().setCursor(
                Qt.CursorShape.SizeAllCursor if index is not None
                else Qt.CursorShape.CrossCursor)
            return
        if self._tool == "cage" and self._item is not None:
            index = self._hit_cage_handle(view_pos)
            if index != self._cage_hover:
                self._cage_hover = index  # 悬停中的把手画大一圈
                self._sync_cage_overlay()
            scene = self.mapToScene(view_pos.toPoint())
            on_body = index is not None or self._hit_cage_body(scene)
            self.viewport().setCursor(
                Qt.CursorShape.SizeAllCursor if on_body
                else Qt.CursorShape.CrossCursor)
            return
        if self._tool == "transform" and not self._xf_reshape \
                and self._item is not None:
            hit = self._hit_transform(view_pos)
            if hit in HOVER_CURSORS:
                cursor = HOVER_CURSORS[hit]  # 角/边：方向光标
            elif hit in ("pivot", "inside"):
                cursor = Qt.CursorShape.SizeAllCursor
            elif hit == "outside":
                cursor = Qt.CursorShape.CrossCursor  # 框外拖 = 旋转
            else:
                cursor = Qt.CursorShape.ArrowCursor
            self.viewport().setCursor(cursor)
            return
        if self._tool not in ("crop", "transform") or self._item is None:
            if self._hover_handle is not None:
                self._hover_handle = None
                self._apply_hover_highlight()
            self._sync_cursor()
            return
        handle = self._hit_handle(view_pos)
        if handle != self._hover_handle:
            self._hover_handle = handle
            self._apply_hover_highlight()
        if handle is not None:
            cursor = HOVER_CURSORS.get(handle, Qt.CursorShape.ArrowCursor)
        elif self._rect is not None and \
                self._rect.normalized().contains(
                    self.mapToScene(view_pos.toPoint())):
            cursor = Qt.CursorShape.OpenHandCursor  # 框内 = 可拖动整体
        else:
            cursor = Qt.CursorShape.ArrowCursor
        self.viewport().setCursor(cursor)

    def _sync_cursor(self) -> None:
        """按工具换光标：擦除藏系统光标——实圈就是光标（直径=擦除直径）。"""
        if self._tool == "erase":
            self.viewport().setCursor(Qt.CursorShape.BlankCursor)
            return
        cursor = {
            # 裁剪默认有框：箭头（手柄收边/框内移动），不是"准备画框"的十字
            "crop": Qt.CursorShape.ArrowCursor,
            "text": Qt.CursorShape.IBeamCursor,
            # 变形是"点一下放图钉"的十字；悬停到已有图钉时由
            # _update_hover_cursor 换成移动光标
            "deform": Qt.CursorShape.CrossCursor,
            # 校正是"拖四角"的十字；悬停到角点换移动光标
            "rectify": Qt.CursorShape.CrossCursor,
            # 变换笼是"拖把手"的十字；悬停到把手/笼身换移动光标
            "cage": Qt.CursorShape.CrossCursor,
        }.get(self._tool, Qt.CursorShape.ArrowCursor)
        self.viewport().setCursor(cursor)

    def _hit_handle(self, view_pos: QPointF) -> str | None:
        """手柄/边缘命中测试（全部按视图像素，不随缩放变）。

        不只认 8 个小方块：**整条边**都在命中带内（带宽 EDGE_BAND_VIEW_PX，
        以边线为中心向内外各半），四角的双边交叠区是角手柄——沿边任意
        位置都能抓着向内拖（用户 20:18 定："四边大部分区域都可以向内移动"）。
        """
        if self._rect is None:
            return None
        rect = self.mapFromScene(self._rect.normalized()).boundingRect()
        band = EDGE_BAND_VIEW_PX
        x, y = view_pos.x(), view_pos.y()
        h = ("l" if abs(x - rect.left()) <= band
             else ("r" if abs(x - rect.right()) <= band else ""))
        v = ("t" if abs(y - rect.top()) <= band
             else ("b" if abs(y - rect.bottom()) <= band else ""))
        if h and v:
            return v + h  # tl / tr / bl / br（与手柄命名一致）
        if h and rect.top() - band <= y <= rect.bottom() + band:
            return h
        if v and rect.left() - band <= x <= rect.right() + band:
            return v
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        button = event.button()
        if button in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            # ⚠️ 「变形」工具里，右键点在图钉上 = 删图钉（先于 pan 兜底）：
            #    否则右键永远被当成平移，图钉删不掉（用户文档写了右键删钉）
            if button == Qt.MouseButton.RightButton and self._tool == "deform" \
                    and self._item is not None:
                index = self._hit_pin(event.position())
                if index is not None:
                    self.pin_remove(index)
                    event.accept()
                    return
            self._mode = ("pan", event.position())
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if button != Qt.MouseButton.LeftButton or self._item is None:
            return super().mousePressEvent(event)
        pos = self.mapToScene(event.position().toPoint())
        inside = self.image_rect()
        if self._tool == "crop":
            # 裁剪不做"拖拽画框"（那是截图的交互）：默认全选，只能收边/移动
            handle = self._hit_handle(event.position())
            self._hover_handle = handle
            self._apply_hover_highlight()
            if handle is not None:
                self._mode = ("handle", handle)
            elif self._rect is not None and \
                    self._rect.normalized().contains(pos):
                self._mode = ("move", pos, QPointF(self._rect.topLeft()))
            # 图外/遮罩上按下：不响应（想调框请拖手柄或框内）
            self._sync_overlay()
            event.accept()
            return
        if self._tool == "transform":
            if self._xf_reshape:
                # 「调整范围」：交互与裁剪同款（整条边命中带 + 框内移动），
                # 只是松手后不应用，区域留给变换用
                handle = self._hit_handle(event.position())
                self._hover_handle = handle
                self._apply_hover_highlight()
                if handle is not None:
                    self._mode = ("handle", handle)
                elif self._rect is not None and \
                        self._rect.normalized().contains(pos):
                    self._mode = ("move", pos, QPointF(self._rect.topLeft()))
                self._sync_overlay()
                event.accept()
                return
            hit = self._hit_transform(event.position())
            if hit == "outside":
                # 松手前没建过预览的话，这次按下也不产生任何变换
                self._ensure_transform_preview()
                if self._float_item is None:
                    event.accept()
                    return
                center = self._xf.map(self._xf_pivot)
                angle0 = math.degrees(math.atan2(
                    pos.y() - center.y(), pos.x() - center.x()))
                self._mode = ("xf_rotate", self._xf, center, angle0)
            elif hit == "pivot":
                inv, _ = self._xf.inverted()
                self._mode = ("xf_pivot", inv)
            else:
                self._ensure_transform_preview()
                if self._float_item is None:
                    event.accept()
                    return
                if hit in ("tl", "tr", "bl", "br"):
                    rect = self._xf_rect.normalized()
                    opposite = {"tl": rect.bottomRight(),
                                "tr": rect.bottomLeft(),
                                "bl": rect.topRight(),
                                "br": rect.topLeft()}[hit]
                    anchor = (self._xf_pivot if self._xf_about_pivot
                              else QPointF(opposite))
                    inv, _ = self._xf.inverted()
                    self._mode = (
                        "xf_scale", self._xf, inv.map(pos), QPointF(anchor))
                elif hit in ("t", "b", "l", "r"):
                    self._mode = ("xf_shear", self._xf, pos, hit)
                else:  # 框内 = 移动
                    self._mode = ("xf_move", self._xf, pos)
            event.accept()
            return
        if self._tool == "deform":
            # 变形（操控变形）：点到已有图钉 = 拖它；点空白 = 放一个新图钉
            # （新图钉立即进入拖动状态，松手即落在点到的位置）。
            index = self._hit_pin(event.position())
            alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
            if index is not None and alt:
                self.pin_remove(index)          # Alt+点 = 删图钉
                event.accept()
                return
            if index is None:
                if alt:
                    event.accept()              # Alt+点空白：不动
                    return
                index = self.pin_add(pos)
                if index is None:
                    event.accept()
                    return
                self.pin_move(index, pos)       # 新图钉立即跟手
            self._pin_hover = index
            self._mode = ("deform", index)
            self._sync_overlay()
            event.accept()
            return
        if self._tool == "cage":
            # 变换笼（GIMP 口径）：点把手 = 拖它；点笼内/边 = 整体平移；
            # 点空白 = 不动（避免误把笼甩走）。
            self._ensure_cage()
            index = self._hit_cage_handle(event.position())
            if index is None and self._hit_cage_body(pos):
                index = -1  # 整体平移的哨兵
            if index is None:
                event.accept()
                return
            if index >= 0:
                self._cage_hover = index
                self._cage_drag = index
            else:
                self._cage_hover = None
                self._cage_drag = None
            self._cage_drag_origin = (pos, [(a, QPointF(b))
                                            for a, b in self._cage_handles])
            self._mode = ("cage", index)
            self._sync_overlay()
            event.accept()
            return
        if self._tool == "rectify":
            # 校正（四点透视摆正）：拖四角。点在角上才拖，点空白不动
            # （避免误拖把四角搞乱；要放整幅就用「重置」）。
            self._ensure_quad()
            index = self._hit_quad(event.position())
            if index is None:
                event.accept()
                return
            self._rect_hover = index
            self._rect_drag = index
            self._mode = ("rect", index)
            self._sync_overlay()
            event.accept()
            return
        if self._tool == "erase":
            self.stroke_started.emit()
            self._erase_at(pos, pos)
            self._move_eraser_ring(pos)
            self._mode = ("draw", pos)
            event.accept()
            return
        if self._tool == "text":
            hit = self._scene.itemAt(pos, QTransform())
            if isinstance(hit, TextBlockItem):
                # 点在已有文字块上：交给场景路由（放光标/选字/按住拖动）——
                # 每次点击都新建块的话，旧块就永远进不了编辑态（用户报
                # 「文字不能编辑」，2026-10-01）
                super().mousePressEvent(event)
                return
            clamped = QPointF(
                max(inside.left(), min(pos.x(), inside.right())),
                max(inside.top(), min(pos.y(), inside.bottom())),
            )
            self.text_requested.emit(clamped)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._mode is None:
            if self._scene.mouseGrabberItem() is not None:
                # 文字块拖拽中（按下时已把事件送进场景、块抓住了鼠标）：
                # move 必须继续转发给场景——在这里当悬停消费掉的话，块
                # 永远收不到 move，"按住拖动"就是死的（用户报「鼠标放在
                # 文字上面可以移动」，2026-10-01）
                super().mouseMoveEvent(event)
                event.accept()
                return
            # 未拖拽：橡皮擦圈/文字边界框跟随鼠标 + 悬停反馈（需要 mouseTracking）
            if self._tool == "erase" and self._item is not None:
                self._move_eraser_ring(
                    self.mapToScene(event.position().toPoint()))
            elif self._tool == "text" and self._item is not None:
                block = self._text_block_at(
                    self.mapToScene(event.position().toPoint()))
                if block is not None:
                    self._move_text_outline(block)
                else:
                    self._hide_text_outline()
            self._update_hover_cursor(event.position())
            event.accept()
            return
        kind = self._mode[0]
        if kind == "pan":
            delta = event.position() - self._mode[1]
            self._mode = ("pan", event.position())
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return
        pos = self.mapToScene(event.position().toPoint())
        inside = self.image_rect()
        if kind == "xf_move":
            _, x_start, start = self._mode
            delta = pos - start
            self._xf = x_start * QTransform().translate(delta.x(), delta.y())
            self._xf_touched = True
        elif kind == "xf_rotate":
            _, x_start, center, angle0 = self._mode
            angle = math.degrees(math.atan2(
                pos.y() - center.y(), pos.x() - center.x()))
            delta = (angle - angle0 + 180.0) % 360.0 - 180.0
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                delta = round(delta / ROTATE_SNAP_DEG) * ROTATE_SNAP_DEG
            # 旋转发生在累计矩阵之后（轴心是视觉位置）：(T * R) 先 T 后 R
            self._xf = x_start * rotate_about(center, delta)
            self._xf_touched = True
        elif kind == "xf_scale":
            _, x_start, p0_local, anchor = self._mode
            inv, _ = x_start.inverted()
            cur = inv.map(pos)
            sx = ((cur.x() - anchor.x()) / (p0_local.x() - anchor.x())
                  if abs(p0_local.x() - anchor.x()) > 1e-6 else 1.0)
            sy = ((cur.y() - anchor.y()) / (p0_local.y() - anchor.y())
                  if abs(p0_local.y() - anchor.y()) > 1e-6 else 1.0)
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                sx = sy = (sx + sy) / 2.0  # 等比
            self._xf = scale_about(anchor, sx, sy) * x_start
            self._xf_touched = True
        elif kind == "xf_shear":
            _, x_start, start, edge = self._mode
            inv, _ = x_start.inverted()
            delta = inv.map(pos) - inv.map(start)
            rect = self._xf_rect.normalized()
            if edge in ("l", "r"):
                k = delta.y() / rect.width()
            else:
                k = delta.x() / rect.height()
            self._apply_shear(edge, k, x_start)
            self._xf_touched = True
        elif kind == "xf_pivot":
            inv = self._mode[1]
            self._xf_pivot = clamp_rect(
                QRectF(inv.map(pos), QSizeF(0, 0)),
                self._xf_rect.normalized()).topLeft()
        elif kind == "move":
            start, origin = self._mode[1], self._mode[2]
            delta = pos - start
            moved = self._rect.normalized().translated(delta)
            moved.moveTopLeft(clamp_rect(moved, inside).topLeft())
            self._rect = moved
        elif kind == "handle":
            self._resize_rect(self._mode[1], pos)
        elif kind == "deform":
            self.pin_move(self._mode[1], pos)
        elif kind == "cage":
            index = self._mode[1]
            if index is None:
                # 拖整体/边：基于按下时的快照做位移（不逐帧累加，见 cage_move_all）
                if self._cage_drag_origin is not None:
                    start = self._cage_drag_origin[0]
                    self.cage_move_all(pos - start)
            else:
                self.cage_move(index, pos)
        elif kind == "rect":
            self.quad_move(self._mode[1], pos)
        elif kind == "draw":
            self._erase_at(self._mode[1], pos)
            self._move_eraser_ring(pos)
            self._mode = ("draw", pos)
        self._sync_float()
        self._sync_overlay()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._mode and self._mode[0] == "pan":
            self._mode = None
            self._sync_cursor()
            event.accept()
            return
        if self._mode and self._mode[0] in ("move", "handle"):
            # move/handle 只在裁剪与变换「调整范围」下出现；两者松手都
            # 把视图适配到新选区（变小就放大，修褶皱要对准那一小块）
            was_reshape = self._tool == "transform" and self._xf_reshape
            self._mode = None
            if was_reshape:
                self._xf_reshape = False
                # 轴心跟随新区域中心：后续旋转/缩放绕"褶皱那块"的中心
                self._xf_pivot = self._rect.normalized().center()
                self.reshape_finished.emit()  # 弹窗取消勾选，回到变换
            self._sync_overlay()
            self.fit_selection()
            event.accept()
            return
        if self._mode and self._mode[0] == "draw":
            self._mode = None
            event.accept()
            return
        if self._mode and self._mode[0] == "deform":
            # 松手补一次预览：拖动中可能正好被节流窗口跳过，最后一帧不补
            # 的话停在屏幕上的就不是松手位置的结果（所见≠将得）
            self._mode = None
            self._refresh_deform_preview(force=True)
            event.accept()
            return
        if self._mode and self._mode[0] == "rect":
            self._mode = None
            self._rect_drag = None
            self._refresh_deform_preview(force=True)
            self._sync_quad_overlay()
            event.accept()
            return
        if self._mode and self._mode[0] == "cage":
            # 松手补一次预览：拖动中可能正好被节流窗口跳过，最后一帧不补
            # 的话停在屏幕上的就不是松手位置的结果（所见≠将得）
            self._mode = None
            self._cage_drag = None
            self._cage_drag_origin = None
            self._refresh_cage_preview(force=True)
            self._sync_cage_overlay()
            event.accept()
            return
        if self._mode and self._mode[0].startswith("xf_"):
            self._mode = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _resize_rect(self, handle: str, pos: QPointF) -> None:
        """拖手柄改选区（对边/对角锚定不动），夹进画布、保住最小边。"""
        rect = QRectF(self._rect.normalized())
        inside = self.image_rect()
        if "l" in handle:
            rect.setLeft(max(
                inside.left(), min(pos.x(), rect.right() - MIN_RECT_EDGE)))
        if "r" in handle:
            rect.setRight(min(
                inside.right(), max(pos.x(), rect.left() + MIN_RECT_EDGE)))
        if "t" in handle:
            rect.setTop(max(
                inside.top(), min(pos.y(), rect.bottom() - MIN_RECT_EDGE)))
        if "b" in handle:
            rect.setBottom(min(
                inside.bottom(), max(pos.y(), rect.top() + MIN_RECT_EDGE)))
        self._rect = rect

    def _erase_at(self, start: QPointF, end: QPointF) -> None:
        """橡皮擦在图上就地擦一段（涂白；古籍页面去污点=涂白），刷新显示。"""
        if self._image is None:
            return
        painter = QPainter(self._image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor("#ffffff"), float(self._erase_size))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        if start == end:
            painter.drawPoint(start)
        else:
            painter.drawLine(start, end)
        painter.end()
        self.refresh()

    def leaveEvent(self, event) -> None:  # noqa: N802
        # 鼠标离开画布：高亮熄灭、橡皮擦圈/文字边界框隐藏、光标回默认
        self._hover_handle = None
        self._hide_eraser_ring()
        self._hide_text_outline()
        self._apply_hover_highlight()
        if self._pin_hover is not None and self._mode is None:
            self._pin_hover = None  # 悬停放大的图钉缩回去
            self._sync_overlay()
        if self._cage_hover is not None and self._mode is None:
            self._cage_hover = None  # 悬停放大的把手缩回去
            self._sync_overlay()
        self._sync_cursor()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # 就地编辑文字时按键（含 ←/→ 移光标）全部给文本编辑，不走翻页
        if isinstance(self._scene.focusItem(), TextBlockItem):
            super().keyPressEvent(event)
            return
        # ←/→ 别拿去滚动画布，交还弹窗（与预览弹窗一致：方向键是翻页）
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            event.ignore()
            return
        super().keyPressEvent(event)


# ------------------------------------------------------------------ 弹窗
#: 图片编辑弹窗的**期望**尺寸与最小尺寸（逻辑像素）。落地前一律经
#: ``apply_window_size`` 夹进屏幕可用区域，所以这两个值是"上限"而不是承诺
#: （1920×1080 @125% 的机器上可用高只有 824，940 会被任务栏吃掉一截）。
#: 自测按这两个常量算期望值，别再在测试里写死 1440×940。
EDITOR_SIZE = QSize(1440, 940)
EDITOR_MIN_SIZE = QSize(1000, 680)


class ImageEditorDialog(QDialog):
    """图片编辑弹窗：顶部工具/选项行 + 中央画布 + 底部状态行。

    ``accepted`` 后用 :meth:`result_image` 取编辑结果；关闭/拒绝即放弃。
    """

    def __init__(self, parent=None, image: QImage | None = None,
                 save_back: bool = False):
        super().__init__(parent)
        # 本页有真实文件可回写（宿主预览弹窗传入）：「完成」= 直接覆盖原图
        # 文件，而不是"回画布再自己下载"。只影响文案，行为在弹窗侧。
        self._save_back = bool(save_back)
        self.setWindowTitle("图片编辑")
        self.setModal(True)
        # 编辑要看得清字迹：默认开大，并带最小化/最大化按钮（标题栏双击
        # 最大化也随 maximize 按钮生效），用户 20:18 定
        # ✳️ 但默认尺寸与最小尺寸都要先夹进屏幕可用区域：1440×940 / 1000×680
        # 在 1920×1080 @125%（逻辑可用 1536×824）下都会被任务栏吃掉一截，
        # 高缩放的笔记本上最小尺寸甚至比可用区域还大、用户连拖小都做不到。
        apply_window_size(self, EDITOR_SIZE, EDITOR_MIN_SIZE)
        # ⚠️ 显式设置窗口旗标时必须把 CloseButtonHint 一并给上：只给
        #    min/max 不给 close，Windows 标题栏的关闭按钮会失效（用户报障
        #    "编辑弹窗关闭按钮不生效"，2026-10-01）。
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        base = image if image is not None else QImage()
        # 统一转 ARGB32：rembg 产物可能是调色板 PNG，就地绘制需要真彩格式
        self._original = base.convertToFormat(QImage.Format_ARGB32)
        self._image = self._original.copy()
        self._undo: list[QImage] = []
        self._redo: list[QImage] = []
        self._option_page: QWidget | None = None
        # 文字工具选项的活性引用（插入时现读，见 _commit_text_blocks）
        self._text_size: int = TEXT_DEFAULT
        self._text_color: str = "#000000"
        self._text_family: str = T.FONT_FAMILY
        self._erase_size: int = ERASER_DEFAULT
        #: 全分辨率形变烘焙中（等待光标前会 processEvents，防重入）
        self._deform_busy = False
        #: 全分辨率透视校正中（同上，防重入）
        self._rectify_busy = False
        #: 全分辨率变换笼烘焙中（同上，防重入）
        self._cage_busy = False
        #: 「完成」整体处理中（防**双击重入**：后台烘焙的 ``processEvents``
        #: 会派发排队的第二次点击，三个 busy 标志各自只挡同名方法、挡不住它，
        #: 详见 :meth:`_finish`）
        self._finishing = False

        self.canvas = EditorCanvas(self)
        self.canvas.set_image(self._image)
        self.canvas.stroke_started.connect(self._push_undo)
        self.canvas.text_requested.connect(self._spawn_text_block)

        root = QVBoxLayout(self)
        root.setContentsMargins(T.SPACE_MD, T.SPACE_MD, T.SPACE_MD, T.SPACE_MD)
        root.setSpacing(T.SPACE_SM)
        # ⚠️ 两行结构（Win10 照片的布局）：主工具栏一行摆不下撤销/还原/
        #    缩放/五个工具/提示/应用/完成，一行时左侧按钮会被挤出窗口
        #    （用户 19:36 截图报"左上边有按钮隐藏掉了"）。
        # ⚠️ _option_row 必须先建：_build_toolbar_row 末尾的 _set_tool
        #    就会往里插第一份选项页。
        self._option_row = QHBoxLayout()
        self._option_row.setSpacing(T.SPACE_SM)
        root.addLayout(self._build_toolbar_row())
        # 第二行：随工具切换的上下文选项（提示/滑杆/应用按钮）
        root.addLayout(self._option_row)
        root.addWidget(self.canvas, 1)
        root.addWidget(self._build_status())
        # ⚠️ 不要在这里再调 _set_tool("crop")：_build_toolbar_row 末尾已经
        #    调过一次。调两次会遗弃一份旧选项页——removeWidget+deleteLater
        #    在构造期不生效，旧页就以默认几何 (0,0,100,30) 悬在左上角，
        #    盖住撤销按钮（用户截图报"左上角有个按钮被隐藏了"）。

        for seq, slot in (
            (QKeySequence("Ctrl+Z"), self._undo_now),
            (QKeySequence("Ctrl+Y"), self._redo_now),
            (QKeySequence(Qt.Key.Key_Escape), self._escape),
        ):
            QShortcut(seq, self).activated.connect(slot)

    def _escape(self) -> None:
        """Esc：先结束文字编辑，然后才关窗。

        ⚠️ 关窗 = 放弃本次全部编辑（状态行里写着），正在打字时一个 Esc
        把整轮编辑清掉太伤人——所以文字编辑态优先吃掉这个键。
        """
        block = self.canvas.focused_text_block()
        if block is not None:
            block.clearFocus()
            return
        self.reject()

    # ------------------------------------------------------------ 构建
    def _build_toolbar_row(self) -> QHBoxLayout:
        """主工具栏：撤销/还原 ｜ 缩放 ｜ 五个工具 ｜ … ｜ 完成。"""
        row = QHBoxLayout()
        row.setSpacing(T.SPACE_SM)
        self.undo_btn = ToolButton(FIF.RETURN)
        self.undo_btn.setToolTip("撤销上一步（Ctrl+Z）")
        self.undo_btn.clicked.connect(self._undo_now)
        self.redo_btn = ToolButton(FIF.SYNC)
        self.redo_btn.setToolTip("重做（Ctrl+Y）")
        self.redo_btn.clicked.connect(self._redo_now)
        self.reset_btn = PushButton("还原")
        self.reset_btn.setToolTip("放弃全部编辑，回到打开时的样子（可撤销）")
        self.reset_btn.clicked.connect(self._reset_all)
        row.addWidget(self.undo_btn)
        row.addWidget(self.redo_btn)
        row.addWidget(self.reset_btn)

        row.addSpacing(T.SPACE_MD)
        self.zoom_out_btn = ToolButton(FIF.ZOOM_OUT)
        self.zoom_out_btn.setToolTip("缩小（滚轮向下）")
        self.zoom_out_btn.clicked.connect(self.canvas.zoom_out)
        self.zoom_in_btn = ToolButton(FIF.ZOOM_IN)
        self.zoom_in_btn.setToolTip("放大（滚轮向上）")
        self.zoom_in_btn.clicked.connect(self.canvas.zoom_in)
        self.fit_btn = PushButton("适应窗口")
        self.fit_btn.setToolTip("整图完整可见")
        self.fit_btn.clicked.connect(self.canvas.fit)
        row.addWidget(self.zoom_out_btn)
        row.addWidget(self.zoom_in_btn)
        row.addWidget(self.fit_btn)

        row.addSpacing(T.SPACE_MD)
        # 工具按钮用 ToggleButton：选中态有主色高亮（用户 20:18 定"选中后
        # 有相应颜色高亮"），PushButton 的 checked 视觉不明显
        self._tool_buttons: dict[str, ToggleButton] = {}
        for key, icon, label in TOOLS:
            button = ToggleButton(icon, label)
            button.setChecked(False)
            button.setToolTip(f"{label}工具")
            button.clicked.connect(lambda _=False, k=key: self._set_tool(k))
            self._tool_buttons[key] = button
            row.addWidget(button)

        row.addStretch(1)
        self.done_btn = PrimaryPushButton(FIF.SAVE, "完成")
        self.done_btn.setToolTip(
            "应用全部编辑并**覆盖原图片**"
            if self._save_back else
            "应用全部编辑并回到预览；满意再用预览弹窗的「下载」保存文件"
        )
        self.done_btn.clicked.connect(self._finish)
        row.addWidget(self.done_btn)
        self._set_tool("crop")  # 填充第二行选项（工具按钮已就位）
        return row

    # ------------------------------------------------------------ 选项行
    def _swap_option_page(self) -> QWidget:
        """换掉第二行整块工具选项区：整页 deleteLater，子控件一起释放。

        ⚠️ 旧页必须先 ``hide()``：``deleteLater`` 要等事件循环才有实效，
        在此期间旧页还挂在弹窗上，不藏起来的话会以默认几何 (0,0) 压在
        工具栏上（用户报的"左上角按钮被隐藏"就是它）。
        """
        if self._option_page is not None:
            self._option_row.removeWidget(self._option_page)
            self._option_page.hide()
            self._option_page.deleteLater()
            self._option_page = None
        page = QWidget(self)
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_SM)
        self._option_page = page
        self._option_row.insertWidget(0, page, 1)
        return layout

    def _set_tool(self, tool: str) -> None:
        """切换工具并重建选项区；离开文字/变换工具前把进行中的工作写进图。"""
        if not hasattr(self, "canvas"):
            return  # 构建期先于画布存在，等 __init__ 末尾再真切换
        if tool != "text":
            self._commit_text_blocks()
        if tool != "transform":
            self._commit_transform()
        if tool != "deform":
            self._commit_deform()
        if tool != "rectify":
            self._commit_rectify()
        if tool != "cage":
            self._commit_cage()
        self.canvas.set_tool(tool)
        # 图片**永不铺满视口**：四周恒留白（用户 2026-10-02 定：编辑区不要
        # 铺满整个界面，上下预留空白方便操作）。变形/变换笼的把手、校正的
        # 四角常要往图外拖，留白更多一点；其它工具也留出同样的余量，视线与
        # 手柄不会贴控件边缘。
        self.canvas.set_fit_ratio(
            DEFORM_FIT_RATIO if tool in ("deform", "cage") else EDIT_FIT_RATIO)
        for key, button in self._tool_buttons.items():
            button.setChecked(key == tool)
        layout = self._swap_option_page()
        if tool == "crop":
            self._page_crop(layout)
        elif tool == "transform":
            self._page_transform(layout)
        elif tool == "deform":
            self._page_deform(layout)
        elif tool == "cage":
            self._page_cage(layout)
        elif tool == "rectify":
            self._page_rectify(layout)
        elif tool == "erase":
            self._page_erase(layout)
        elif tool == "text":
            self._page_text(layout)

    @staticmethod
    def _hint(layout: QHBoxLayout, text: str) -> None:
        label = CaptionLabel(text)
        label.setTextColor(T.INK_FAINT)
        layout.addWidget(label, 1)

    def _page_crop(self, layout: QHBoxLayout) -> None:
        self._hint(layout,
                   "默认选中整幅图：沿四边/四角任意位置向内拖收小选区，"
                   "拖框中间移动；松手后视图自动放大到新选区")
        apply_btn = PrimaryPushButton("应用裁剪")
        apply_btn.setToolTip("把画布裁成当前选区（可撤销）")
        apply_btn.clicked.connect(self._apply_crop)
        layout.addWidget(apply_btn)

    def _page_transform(self, layout: QHBoxLayout) -> None:
        self._hint(layout, "拖角=缩放（Shift 等比）· 拖边=切变 · 框内拖=移动"
                           " · 框外拖=绕轴心旋转（Shift 每 15°）；轴心圆点可拖动")
        reshape = CheckBox("调整范围")
        reshape.setToolTip(
            "勾选后沿边拖动收小要处理的区域（收完自动回到变换模式）——"
            "小范围修褶皱：先框住褶皱，再旋转/切变把它正回来"
        )
        reshape.setChecked(self.canvas._xf_reshape)
        reshape.toggled.connect(self.canvas.set_transform_reshape)
        self.canvas.reshape_finished.connect(
            lambda: reshape.setChecked(False))
        layout.addWidget(reshape)
        check = CheckBox("从轴心缩放/切变")
        check.setChecked(self.canvas._xf_about_pivot)
        check.toggled.connect(self.canvas.set_transform_about_pivot)
        layout.addWidget(check)
        reset_btn = PushButton("重置")
        reset_btn.setToolTip("丢弃未应用的变换，选区回到整幅（不动已应用的编辑）")
        reset_btn.clicked.connect(self.canvas.reset_transform)
        layout.addWidget(reset_btn)
        apply_btn = PrimaryPushButton("应用变换")
        apply_btn.setToolTip("把当前变换烘焙进图片：原区域填白（可撤销）")
        apply_btn.clicked.connect(self._commit_transform)
        layout.addWidget(apply_btn)

    def _page_deform(self, layout: QHBoxLayout) -> None:
        self._hint(layout,
                   "点图放图钉 → 拖图钉：附近内容跟着走（近处动得多、远处"
                   "几乎不动，四边默认钉住）；Alt+点或右键删图钉；"
                   "图钉可拖到图外（往外拉＝拉伸）")
        combo = ComboBox()
        combo.setFixedWidth(150)
        # NoFocus：别把键盘焦点从画布抢走
        combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for cell, label in MESH_DENSITY_CHOICES:
            combo.addItem(label, userData=cell)
        combo.setCurrentIndex(
            max(0, combo.findData(self.canvas.mesh_density())))
        combo.setToolTip(
            "网格格距：越小越细腻、解算越慢。改档会**清空图钉**，"
            "所以有未应用的形变时先把当前形变落地")
        layout.addWidget(QLabel("网格疏密"))
        layout.addWidget(combo)

        def apply_density(_index: int) -> None:
            value = combo.currentData()
            if value is None:
                return
            if self.canvas.pins_pending() is not None:
                # 重建网格会把图钉清掉、已解的形变也就丢了：先落地（一个撤销点）
                self._commit_deform()
            self.canvas.set_mesh_density(float(value))

        combo.currentIndexChanged.connect(apply_density)

        reset_btn = PushButton("重置")
        reset_btn.setToolTip("清空所有图钉，丢掉未应用的形变")
        reset_btn.clicked.connect(self.canvas.reset_pins)
        layout.addWidget(reset_btn)
        apply_btn = PrimaryPushButton("应用变形")
        apply_btn.setToolTip(
            "把当前形变按全分辨率烘焙进图片（可撤销）；"
            "应用后图钉留在原地，方便接着微调")
        apply_btn.clicked.connect(self._commit_deform)
        layout.addWidget(apply_btn)

    def _page_cage(self, layout: QHBoxLayout) -> None:
        self._hint(layout,
                   "拖笼上的把手：只有把手附近的像素跟着走（远处逐字节不动）；"
                   "向外拉＝拉伸、向内推＝压缩；拖边/拖笼内＝整体平移；"
                   "把手可拖到图外")
        combo = ComboBox()
        combo.setFixedWidth(160)
        combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for per_side, label in CAGE_DENSITY_CHOICES:
            combo.addItem(label, userData=per_side)
        combo.setCurrentIndex(
            max(0, combo.findData(self.canvas.cage_density())))
        combo.setToolTip(
            "每边把手数：越多越能做出精细的局部形变。改档会**重建笼并丢掉"
            "未应用的形变**，所以有未应用的形变时先落地")
        layout.addWidget(QLabel("把手密度"))
        layout.addWidget(combo)

        def apply_density(_index: int) -> None:
            value = combo.currentData()
            if value is None:
                return
            if self.canvas.cage_pending() is not None:
                # 重建笼会把形变清掉：先落地（一个撤销点）
                self._commit_cage()
            self.canvas.set_cage_density(int(value))

        combo.currentIndexChanged.connect(apply_density)

        reset_btn = PushButton("重置")
        reset_btn.setToolTip("把手回到整幅图原位，丢掉未应用的形变")
        reset_btn.clicked.connect(self.canvas.reset_cage)
        layout.addWidget(reset_btn)
        apply_btn = PrimaryPushButton("应用形态")
        apply_btn.setToolTip(
            "把当前笼形变按全分辨率烘焙进图片（可撤销）；"
            "应用后把手留在原地，方便接着微调")
        apply_btn.clicked.connect(self._commit_cage)
        layout.addWidget(apply_btn)

    def _page_rectify(self, layout: QHBoxLayout) -> None:
        self._hint(layout,
                   "拖四个角框住要摆正的页面（拍摄角度/装订倾斜）："
                   "整页会被拉成矩形——四角默认压在图片四角，"
                   "往外拖可把拍进来的桌面也框进去")
        combo = ComboBox()
        combo.setFixedWidth(180)
        combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for mode, label in RECTIFY_RATIO_CHOICES:
            combo.addItem(label, userData=mode)
        combo.setCurrentIndex(
            max(0, combo.findData(self.canvas.rectify_ratio())))
        combo.setToolTip(
            "摆正后的目标矩形：「外接框」尺寸最省；「保持原比例」按对边"
            "平均长定宽高，内容不拉胖压扁（摆正书页推荐）")
        layout.addWidget(QLabel("目标尺寸"))
        layout.addWidget(combo)

        def apply_mode(_index: int) -> None:
            value = combo.currentData()
            if value is not None:
                self.canvas.set_rectify_ratio(str(value))

        combo.currentIndexChanged.connect(apply_mode)

        reset_btn = PushButton("重置")
        reset_btn.setToolTip("四角回到整幅图四角，丢掉未应用的校正")
        reset_btn.clicked.connect(self.canvas.reset_quad)
        layout.addWidget(reset_btn)
        apply_btn = PrimaryPushButton("应用校正")
        apply_btn.setToolTip(
            "把框住的区域透视摆正并替换整图（尺寸变为目标矩形，可撤销）")
        apply_btn.clicked.connect(self._commit_rectify)
        layout.addWidget(apply_btn)

    def _page_erase(self, layout: QHBoxLayout) -> None:
        self._hint(layout, "按住左键在污点上涂抹，把它擦成白底（古籍页面去污点）")
        size_label = CaptionLabel(f"{self._erase_size}px")
        slider = Slider(Qt.Orientation.Horizontal)
        slider.setRange(ERASER_MIN, ERASER_MAX)
        slider.setValue(self._erase_size)
        slider.setFixedWidth(160)

        def apply_size(value: int) -> None:
            size_label.setText(f"{value}px")
            self._erase_size = value
            self.canvas.set_eraser(value)

        slider.valueChanged.connect(apply_size)
        layout.addWidget(QLabel("橡皮擦大小"))
        layout.addWidget(slider)
        layout.addWidget(size_label)
        # 初次进入按默认大小生效
        self.canvas.set_eraser(self._erase_size)

    def _page_text(self, layout: QHBoxLayout) -> None:
        self._hint(layout, "点击图片落点就地输入（光标可见）；样式对**整块**"
                           "即时生效；悬停文字出现虚线框，按住可拖动整块；"
                           "「插入文字」把文字写进图片")
        # 字体：**中文字体为主** + 几个常用西文（用户 2026-10-01 定：系统字体
        # 库里两三百个族全列出来，中文反而被淹没、翻半天找不到"仿宋"）
        combo = ComboBox()
        combo.setFixedWidth(170)
        for family in text_font_families():
            combo.addItem(family, userData=family)
        combo.setCurrentIndex(max(0, combo.findData(self._text_family)))
        if combo.currentData():  # 存的族名不在清单里时以清单首项为准，别错位
            self._text_family = combo.currentData()
        combo.setToolTip("文字字体（中文字体为主）")
        layout.addWidget(QLabel("字体"))
        layout.addWidget(combo)

        size_label = CaptionLabel(f"{self._text_size}px")
        slider = Slider(Qt.Orientation.Horizontal)
        slider.setRange(TEXT_MIN, TEXT_MAX)
        slider.setValue(self._text_size)
        slider.setFixedWidth(160)
        # ⚠️ NoFocus：qfluentwidgets 的 Slider 默认是 StrongFocus，一拖就把
        # 键盘焦点从画布抢走——就地编辑的文字块随之丢焦点、光标消失。
        # （改样式走"当前样式块"后功能上已不依赖焦点，但保住光标体验更好。）
        slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        slider.setToolTip("文字大小（图片像素）")
        layout.addWidget(QLabel("字号"))
        layout.addWidget(slider)
        layout.addWidget(size_label)

        # 颜色：常用色块与任意色**都收在这一个按钮弹出的面板里**（用户
        # 2026-10-01：色块不要在外面，要在颜色选择器里面，且要好看）
        layout.addWidget(QLabel("颜色"))
        picker = ColorPickerButton(QColor(self._text_color), TEXT_SWATCHES,
                                   parent=self)
        layout.addWidget(picker)

        def style_changed() -> None:
            block = self.canvas.style_target_block()
            if block is not None:
                block.apply_style(
                    self._text_family, self._text_size,
                    QColor(self._text_color))

        combo.currentIndexChanged.connect(
            lambda _index: (
                setattr(self, "_text_family",
                        combo.currentData() or self._text_family),
                style_changed()))
        slider.valueChanged.connect(
            lambda value: (setattr(self, "_text_size", value),
                           size_label.setText(f"{value}px"), style_changed()))
        picker.colorChanged.connect(
            lambda color: (setattr(self, "_text_color", color.name()),
                           style_changed()))
        # 颜色面板关掉后把键盘焦点还给文字块，接着打字不中断
        picker.panelClosed.connect(self.canvas.focus_text_block)

        insert_btn = PrimaryPushButton("插入文字")
        insert_btn.setToolTip("把画布上的文字块写进图片（可撤销）")
        insert_btn.clicked.connect(self._commit_text_blocks)
        layout.addWidget(insert_btn)

    # ------------------------------------------------------------ 撤销
    def _report_bake_error(self, exc: Exception) -> None:
        """把烘焙失败转成**用户能看懂**的提示（InfoBar），并把技术细节打到日志。

        为什么不静默：烘焙失败时若什么都不说，界面看起来就是"点了没反应"
        ——用户已经报过好几次"程序卡死/崩溃"，而这类静默失败会让他们更加
        确信程序崩了。宁可多弹一条提示。

        常见原因换成人话（``MemoryError`` 是大图下最常见的，见
        ``_bake_puppet_work`` 的内存说明）：

        - ``MemoryError``：图片太大，内存不够——建议先裁剪或缩小再处理；
        - ``LinAlgError`` / 奇异：把图钉或把手分开一点再试；
        - ``ValueError``：当前形状退化（如四角共线），换个操作。
        """
        if isinstance(exc, MemoryError):
            title = "图片太大，处理失败"
            content = ("这张图按全分辨率处理需要的内存超出可用量，"
                       "操作没有生效。可以先裁剪到需要处理的区域，或缩小后重试。")
        elif type(exc).__name__ == "LinAlgError":
            title = "形状退化，操作没有生效"
            content = "当前的控制点重合或共线，解不出结果。把它们分开一点再试。"
        else:
            title = "操作失败"
            content = f"没有生效：{type(exc).__name__}。详细信息见日志。"
        try:
            import traceback
            traceback.print_exception(type(exc), exc, exc.__traceback__)
        except Exception:      # noqa: BLE001（日志失败绝不能连带崩掉提示）
            pass
        try:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error(title=title, content=content, parent=self,
                          position=InfoBarPosition.BOTTOM_RIGHT, duration=5000)
        except Exception:      # noqa: BLE001（无宿主/组件缺失时降级为控制台）
            print(f"[图片编辑] {title}：{exc}")

    def _push_undo(self) -> None:
        """把当前状态压入撤销栈（必须在任何破坏性操作**之前**调用）。"""
        if self._image is None or self._image.isNull():
            return
        self._undo.append(self._image.copy())
        if len(self._undo) > UNDO_LIMIT:
            self._undo.pop(0)
        self._redo.clear()
        self._sync_undo_buttons()

    def _undo_now(self) -> None:
        if not self._undo:
            return
        # 正在就地编辑文字时不撤图：Ctrl+Z 被弹窗快捷键截走，这里必须
        # 让位——不然想撤一个字却把整张图连同文字块一起退掉了
        if self.canvas.focused_text_block() is not None:
            return
        # 撤销换图会作废画布上的文字块（它们不在撤销历史里）
        self.canvas.clear_text_blocks()
        self._redo.append(self._image.copy())
        self._image = self._undo.pop()
        self.canvas.set_image(self._image)
        self._sync_undo_buttons()

    def _redo_now(self) -> None:
        if not self._redo:
            return
        if self.canvas.focused_text_block() is not None:
            return  # 同 _undo_now：文字编辑中不让 Ctrl+Y 动图
        self.canvas.clear_text_blocks()
        self._undo.append(self._image.copy())
        self._image = self._redo.pop()
        self.canvas.set_image(self._image)
        self._sync_undo_buttons()

    def _reset_all(self) -> None:
        """还原到打开时的图（还原本身可撤销）。"""
        if self._original.isNull():
            return
        self.canvas.clear_text_blocks()
        if self._undo and self._image is not None:
            self._undo.append(self._image.copy())
            if len(self._undo) > UNDO_LIMIT:
                self._undo.pop(0)
        self._image = self._original.copy()
        self._redo.clear()
        self.canvas.set_image(self._image)
        self._sync_undo_buttons()

    def _sync_undo_buttons(self) -> None:
        self.undo_btn.setEnabled(bool(self._undo))
        self.redo_btn.setEnabled(bool(self._redo))

    # ------------------------------------------------------------ 应用
    def _selection(self) -> QRectF | None:
        rect = self.canvas.selection()
        if rect is None:
            return None
        return clamp_rect(rect, self.canvas.image_rect())

    def _apply_crop(self) -> None:
        rect = self._selection()
        if rect is None or self._image is None:
            return
        self._push_undo()
        self._image = self._image.copy(rect.toRect())
        self.canvas.set_image(self._image)

    # ------------------------------------------------------------ 变换
    def _commit_transform(self) -> None:
        """把未应用的变换烘焙进图片（一个撤销点）；没有变换就只清预览。

        「应用变换」按钮、切走工具、「完成」都走这里——预览即所见，
        烘焙结果与浮层显示一致（原区域填白 + 变换后的选区内容）。
        """
        if not hasattr(self, "canvas"):
            return
        pending = self.canvas.transform_pending()
        if pending is None:
            self.canvas.reset_transform()
            return
        rect, xf, region = pending
        self._push_undo()
        # grow：旋转/倾斜把选区送出原边界时不截，画布放大到「原图 ∪ 变换后」
        image, _origin = bake_transform(self._image, rect, xf, region, grow=True)
        self._image = image
        self.canvas.set_image(self._image)

    # ------------------------------------------------------------ 变形
    def _commit_deform(self) -> None:
        """把未应用的**变形**烘焙进图片（一个撤销点），图钉留在原地。

        「应用变形」按钮、切走工具、「完成」都走这里。形变是 ARAP 网格逐像素
        重映射（PS 操控变形口径，见 ``utils.puppet_warp``），按**全分辨率**算
        ——大图上要秒级到分钟级，所以放到**后台线程**跑并显示进度对话框
        （用户 2026-10-01 报"卡死/崩溃"：同步跑会把主线程钉死、界面假死）；
        并且**防重入**——本函数在"切走到非变形工具"时也会被调，重入会把已经
        形变过的图再形变一次，白丢一个撤销点、结果也不对。
        """
        if not hasattr(self, "canvas") or self._deform_busy:
            return
        pending = self.canvas.pins_pending()
        if pending is None or self._image is None or self._image.isNull():
            # 没有未应用的形变：预览浮层本来就不存在（它只伴随形变出现），
            # 什么都不用清——这里**刻意不调** reset_pins：本函数在"切走到
            # 非变形工具"时也会被调，那时清空图钉纯属白干
            return
        vertices, moved, triangles = pending
        self._push_undo()
        # ⚠️ set_image 换图会把 _pins 清空，所以**先**快照图钉顶点下标，
        #    烘焙完再原样钉回新网格（见 adopt_pins 的说明）
        pin_vertices = list(self.canvas.pins())
        self._deform_busy = True
        try:
            baked = run_with_progress(
                self, "应用变形", "正在把操控变形烘焙进图片……",
                _bake_puppet_work,
                {"image": self._image, "vertices": vertices,
                 "moved": moved, "triangles": triangles})
        except Exception as exc:      # noqa: BLE001（要提示用户，不是吞掉）
            # 烘焙失败（内存不足 / 方程组退化）：退回撤销点并**明确报错**。
            # ⚠️ 绝不能静默返回——用户点了 20 秒却什么都没发生、连按钮都
            #   没反应，只会以为程序卡了（这正是用户报过的现象）。
            self._undo.pop()
            self._sync_undo_buttons()
            self._report_bake_error(exc)
            return
        finally:
            self._deform_busy = False
        if baked is None:
            # 用户取消：不落地，退回撤销点（等于什么都没发生）
            self._undo.pop()
            self._sync_undo_buttons()
            return
        # grow：返回 (QImage, (ox, oy))；换图后网格按新图重建，坐标天然对齐
        image, _origin = baked
        self._image = image
        self.canvas.set_image(self._image)
        # 形变已烧进像素，图钉**留在原地**：古籍褶皱往往要来回试几次，
        # 每次应用后都清空的话用户得重新钉一遍
        self.canvas.adopt_pins(pin_vertices)

    def _commit_cage(self) -> None:
        """把未应用的**变换笼**形变烘焙进图片（一个撤销点），把手留在原地。

        「应用形态」按钮、切走工具、「完成」都走这里。笼形变是 RBF 位移场
        逐像素重映射（GIMP 变换笼口径的**局部**实现，见 ``utils.cage_warp``），
        按**全分辨率**算——虽然影响是局部的（只重采样影响框内），大图上仍是
        秒级，所以挂等待光标；并且**防重入**——等待光标前那一下
        ``processEvents`` 会派发排队事件，不防的话一次点击可能触发两遍。
        """
        if not hasattr(self, "canvas") or self._cage_busy:
            return
        pending = self.canvas.cage_pending()
        if pending is None or self._image is None or self._image.isNull():
            # 没有未应用的形变：预览浮层本来就不存在。**刻意不调** reset_cage：
            # 本函数在"切走到非笼工具"时也会被调，那时清空把手纯属白干。
            return
        src, dst = pending
        self._push_undo()
        self._cage_busy = True
        try:
            baked = run_with_progress(
                self, "应用形态", "正在把变换笼形变烘焙进图片……",
                _bake_cage_work,
                {"image": self._image,
                 "src": [(p.x(), p.y()) for p in src],
                 "dst": [(p.x(), p.y()) for p in dst]})
        except Exception as exc:      # noqa: BLE001（要提示用户，不是吞掉）
            # 同 _commit_deform：失败必须**明确报错**，不能静默当成取消
            self._undo.pop()
            self._sync_undo_buttons()
            self._report_bake_error(exc)
            return
        finally:
            self._cage_busy = False
        if baked is None:
            # 用户取消（或退化）：不落地，退回撤销点（等于什么都没发生）
            self._undo.pop()
            self._sync_undo_buttons()
            return
        # grow 模式下结果是 (QImage, (ox, oy))：(ox, oy) = 新画布左上角在原
        # 坐标系里的位置（可为负）。换图后笼按**新图**重建，坐标天然对齐，
        # 不需要手动平移——但要把"是否扩大过"记下来（见下）。
        image, origin = baked
        self._image = image
        self.canvas.set_image(self._image)
        # 形变已烧进像素：笼回到贴图边原位（重置即身份），可以接着拖第二次。
        # ⚠️ set_image 换图会把笼清空，所以这里必须显式重建，否则切回来时
        #    画布上无笼可拖。
        if self.canvas._tool == "cage":
            self.canvas.reset_cage()

    def _commit_rectify(self) -> None:
        """把四角框住的区域透视摆正，替换整图（一个撤销点）。

        ⚠️ 与「变形」不同：校正**改变图片尺寸**（摆正后是目标矩形），
        所以这里是"换一张图"而不是"在原图上重采样"。换图后四角回到新图的
        四角（原位），可以接着校第二次。「应用校正」按钮、切走工具都走这里。
        """
        if not hasattr(self, "canvas") or self._rectify_busy:
            return
        pending = self.canvas.quad_pending()
        if pending is None or self._image is None or self._image.isNull():
            return
        quad, mode = pending
        self._push_undo()
        self._rectify_busy = True
        try:
            with wait_cursor():
                done = rectify_qimage(self._image, quad, mode=mode)
        except ValueError:
            # ⚠️ 四角退化（完全共线 / 两点重合 / 极细长）时 ``rectify_qimage``
            #   **抛 ValueError 而不是返回 null 图**（实测三种退化输入都抛）。
            #   这里若不接住：异常一路逸出 Qt 槽函数，且更隐蔽的是——
            #   **上面压入的撤销点永远不会被弹出**，撤销历史从此错位
            #   （用户按一次 Ctrl+Z 会"什么都没发生"）。必须成对处理。
            self._undo.pop()
            return
        finally:
            self._rectify_busy = False
        if done.isNull():
            # 退化（四角近似共线）：不落地，退回撤销点（等于什么都没发生）
            self._undo.pop()
            return
        self._image = done
        self.canvas.set_image(self._image)   # 换图 → 四角按新图重建

    # ------------------------------------------------------------ 文字
    def _spawn_text_block(self, pos: QPointF) -> None:
        """文字工具点击落点 → 画布上生成文字块就地编辑（光标可见）。"""
        if self._image is None or self._image.isNull():
            return
        self.canvas.add_text_block(
            pos, self._text_size, QColor(self._text_color),
            self._text_family,
        )

    def _commit_text_blocks(self) -> None:
        """把画布上非空文字块写进图片（一个批次一个撤销点），然后清块。"""
        if not hasattr(self, "canvas"):
            return
        blocks = self.canvas.text_blocks()
        payload = [
            (b.pos(), b.toPlainText(), b.font().pixelSize(),
             QColor(b.defaultTextColor()), b.font().family())
            for b in blocks if b.toPlainText().strip()
        ]
        self.canvas.clear_text_blocks()
        if not payload or self._image is None or self._image.isNull():
            return
        self._push_undo()
        for pos, text, px, color, family in payload:
            self._image = draw_text(
                self._image, pos, text, px, color, family)
        self.canvas.replace_image(self._image)

    def _finish(self) -> None:
        """「完成」：未应用的形变/变换/校正/未插入的文字一并写入，再应用全部编辑。

        ⚠️ **必须整体防重入**：上面每一步各有一层自己的 busy 标志，但它们
        只互相挡住**同名**方法，挡不住「完成」被整体重入。而"完成"路径上
        一定有 ``processEvents``（后台烘焙的等待循环），它会把**排队的第二
        次点击**派发进来 ⇒ 嵌套进第二个 ``_finish``：此时 ``_cage_busy``
        还是 False（第一步是 ``_commit_rectify``），于是**两个 worker + 两个
        进度对话框**同时在跑；嵌套层先 ``accept()`` 关窗，外层继续往已经
        关闭的对话框上 ``set_image()``。快速双击「完成」就能触发。
        """
        if getattr(self, "_finishing", False):
            return
        self._finishing = True
        try:
            self._commit_rectify()
            self._commit_deform()
            self._commit_cage()
            self._commit_transform()
            self._commit_text_blocks()
            self.accept()
        finally:
            self._finishing = False

    # ------------------------------------------------------------ 对外
    def closeEvent(self, event) -> None:  # noqa: N802（Qt 回调）
        """关闭时确保**没有在飞的后台线程**。

        ⚠️ 烘焙 worker 以对话框为 ``parent``。若在它还在跑的时候对话框被
        析构，Qt 会直接 **abort 整个进程**
        （``QThread: Destroyed while thread is still running``）。
        正常流程里 :func:`run_with_progress` 自己同步等线程结束，但
        ``processEvents`` 期间用户仍可能关窗/宿主强制退出，所以这里要兜底。

        同时清画布：撤销栈是**整图快照**，大图下最多 12 份（见 ``UNDO_LIMIT``），
        关窗后必须释放，不能靠 Python GC（Qt 侧 C++ 对象不由引用计数托管）。
        """
        self._deform_busy = self._cage_busy = self._rectify_busy = False
        self._finishing = True
        try:
            self.canvas.clear()
        except Exception:      # noqa: BLE001（销毁期清理不该再抛）
            pass
        super().closeEvent(event)

    def result_image(self) -> QImage | None:
        """编辑结果（无图时 None；是否采纳由调用方的 exec 结果决定）。"""
        if self._image is None or self._image.isNull():
            return None
        return self._image

    def _build_status(self) -> QWidget:
        """状态行：左边是提醒，右边是当前图片尺寸。"""
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        hint = CaptionLabel(
            "「完成」应用编辑并覆盖原图片；直接关闭弹窗 = 放弃本次全部编辑"
            if self._save_back else
            "「完成」应用编辑并回到预览；直接关闭弹窗 = 放弃本次全部编辑"
        )
        hint.setTextColor(T.INK_FAINT)
        self.size_label = CaptionLabel("")
        self.size_label.setTextColor(T.INK_SOFT)
        row.addWidget(hint, 1)
        row.addWidget(self.size_label)
        if self._image is not None:
            self.size_label.setText(
                f"{self._image.width()} × {self._image.height()} px"
            )
        return bar
