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
- **变形**（局部光滑形变，处理古籍褶皱/卷曲）：画面上有一个**一圈把手的笼**
  （默认＝覆盖选区的矩形，把手疏密在选项行选 4/8/12 点），**拖某个把手**，
  只有它**附近**的像素跟着走 —— **近处变化大、远处几乎不动**（"像扯弹簧"），
  影响范围**之外**的像素逐字节一动不动。影响范围＝拖动距离的倍数，
  选项行「影响范围」可选紧凑/适中/宽松；
  **点笼线**可就地加一个把手（加完即可拖；加上去不改变形变），
  「重画笼」可手绘任意闭合区域（逐点点击、点回起点闭合、画笼中 Esc 放弃）。
  把手**可以拖到图片外面**（往外拉＝把那块内容往外拉伸）。
  ⚠️ 刻意**不是** GIMP 原版那种"笼内整体一起走"的全局形变：那样拖一个角会把
  整笼拉斜、从其余顶点扯出折痕（用户 2026-10-01 报过），改为局部影响。
  拖动即实时预览（只算影响范围那一小块 + 按屏幕清晰度降采样，见
  :func:`cage_preview_scale`），松手补一帧更清楚的；「应用变形」（或切走
  工具/「完成」）才烘焙进像素（有等待光标）。
  ⚠️ 「应用变形」后**笼留在原地**（``adopt_cage``）：古籍褶皱往往要来回试
  几次，每次都回到全幅矩形笼的话用户得重新圈一遍。
  算法与口径见 ``utils/cage_warp.py``。
  ⚠️ 进这个工具时图片**不铺满视口**（:data:`CAGE_FIT_RATIO`），四周留白
  方便把把手往图外拖。
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
    QLineF, QPointF, QRect, QRectF, QSizeF, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QImage, QKeySequence, QFontMetrics,
    QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QShortcut, QTransform,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QGraphicsEllipseItem, QGraphicsItem,
    QGraphicsLineItem, QGraphicsPathItem, QGraphicsPixmapItem,
    QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsScene,
    QGraphicsTextItem, QGraphicsView, QHBoxLayout, QLabel, QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel, CheckBox, ComboBox, PrimaryPushButton, PushButton,
    Slider, ToggleButton, ToolButton,
)
from qfluentwidgets import FluentIcon as FIF

from desktop.ui import theme as T
from desktop.ui.color_picker import ColorPickerButton
from desktop.ui.fonts import text_font_families
# ⚠️ utils.cage_warp 的 numpy 是**函数内延迟导入**的，模块级 import 不会
#    把 numpy 拖进 GUI 主进程的启动路径（与 desktop/services/rembg_live 同口径）。
from utils.cage_warp import (
    cage_moved, deform_qimage as deform_cage_image,
    perimeter_cage, warp_region,
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
#: 「变形」矩形笼的默认节点疏密（每条边分几段）。
CAGE_PER_SIDE_DEFAULT = 1
#: 可选的节点疏密：1 → 4 点（四角）/ 2 → 8 点 / 3 → 12 点。
CAGE_PER_SIDE_CHOICES = (1, 2, 3)
#: 「影响范围」档位 = **拖动距离的倍数**（决定形变的影响半径）。
#: 下限 2.5 是 ``utils/cage_warp`` 的防自交下限（半径太小 + 拖太远必然把
#: 像素扯出漩涡），所以档位从 2.5 起；倍数越大越"牵连"周围。
#: 用户 2026-10-01 定：默认要"尽量少影响距离远的节点"，所以默认取最紧凑的
#: 上一档。真正的半径换算见 ``EditorCanvas.cage_influence``。
CAGE_REACH_CHOICES = ((2.5, "紧凑"), (4.0, "适中"), (7.0, "宽松"))
CAGE_REACH_DEFAULT = 0
#: 进「变形」时图片占视口的比例——**四周留出可操作空间**。
#: 用户 2026-10-01：图片宽高不要铺满整个操作区（笼节点要能往图外拖，
#: 越靠边越需要留白；也免得笼线贴着控件边缘不好抓）。
CAGE_FIT_RATIO = 0.8
#: 笼节点的视觉直径与命中直径（视图像素）——命中圈比视觉略大，好抓。
CAGE_NODE_VIEW_PX = 11.0
CAGE_HIT_VIEW_PX = 9.0
#: 手绘笼时：点到第一个节点的这个视觉距离内 = 闭合多边形。
CAGE_CLOSE_VIEW_PX = 14.0
#: 拖动中**像素预览**的工作分辨率上限（像素）。
#: 形变是逐像素重映射：整页 4000×3000 全分辨率一次要 **3 秒**（实测拆解见
#: ``utils/cage_warp`` 的模块文档）。⚠️ 形变现在是**局部**的——只算影响半径
#: 那么大的区域（拖 60px 就是 249×234）——所以这个上限只在"影响范围调宽 +
#: 缩着看整页"时才会碰到。
#: 20 万像素 ≈ 0.06s，配 :data:`CAGE_PREVIEW_INTERVAL` 的节拍留出一半
#: 时间去响应/重绘覆盖层（笼线每帧都跟手）。
CAGE_PREVIEW_PIXELS = 200_000
#: **松手后**重算预览的分辨率上限（像素）。松手是"停下来看结果"的时刻，
#: 按屏幕分辨率算（见 :func:`cage_preview_scale`）就够清楚，但别放开到
#: 全分辨率——整页笼在 100% 缩放下那是 3 秒。250 万像素 ≈ 0.6s，
#: 而局部形变（几十万像素）本来就是全分辨率。
CAGE_PREVIEW_SETTLE_PIXELS = 2_500_000
#: 像素预览重算的最小间隔（秒）。一次重映射是 0.06s 量级，不节流的话每个
#: move 事件都会阻塞界面；笼的**覆盖层**（笼线 + 节点）不受此限，每帧都跟手。
CAGE_PREVIEW_INTERVAL = 0.12

#: 左侧工具栏：（键, 图标, 中文名）
TOOLS = (
    ("crop", FIF.CUT, "裁剪"),
    ("transform", FIF.MOVE, "变换"),
    ("cage", FIF.LAYOUT, "变形"),
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
                   region: QImage) -> QImage:
    """把「选区内容经 ``xf`` 变换」烘焙进图片（画布尺寸不变）。

    先把**原区域**填白（内容被挪走/变形后空出来的地方），再在 ``xf``
    变换下把选区快照画回去——与画布上的实时预览（填白底 + 变换浮层）
    所见一致。古籍整页白底，填白视觉上最干净。
    """
    result = image.copy()
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.fillRect(rect, QColor("#ffffff"))
    painter.setTransform(xf)
    painter.drawImage(rect, region)
    painter.end()
    return result


def bake_cage(image: QImage, cage_src, cage_dst, influence=None) -> QImage:
    """把「把手 ``cage_src`` → 把手 ``cage_dst``」的形变烘焙进图片（尺寸不变）。

    与 :func:`bake_transform` 同口径：**影响半径之外**的像素逐字节不动，
    只是这里不是仿射矩阵而是逐像素重映射（见 ``utils.cage_warp``）。
    ⚠️ **保留 alpha**：桌面侧编辑的常常是第三步产物「白底透明 PNG」，
    丢掉 alpha 会让整片透明背景变成不透明黑（用户 2026-10-01 报过）。
    """
    return deform_cage_image(image, cage_src, cage_dst, influence=influence)


def cage_preview_scale(span_x: float, span_y: float,
                       on_screen: float = 1.0,
                       budget_pixels: float = CAGE_PREVIEW_PIXELS) -> float:
    """拖动预览的降采样倍率：清晰度与成本的**取小**。

    两个约束：

    1. **清晰度**：``on_screen`` = 场景 1 单位对应多少**设备像素**
       （= 当前缩放 × dpr）。预览取到这个倍率时，预览图上的 1 像素正好
       落在屏幕 1 设备像素上——看着与原图一样清楚，再取大就是纯浪费。
    2. **成本**：处理面积不超过 ``budget_pixels``。

    缩到 1/3 看整页时清晰度约束直接给出 1/3：比按成本算还省 9 倍工作量，
    而且屏幕上看不出区别（这正是"预览"该有的样子）。

    ``budget_pixels`` 由调用方按场合给：拖动中给
    :data:`CAGE_PREVIEW_PIXELS`（要跟手），松手后给
    :data:`CAGE_PREVIEW_SETTLE_PIXELS`（停下来看结果，宁可慢一点也要清楚）。
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


def _as_point(point) -> QPointF:
    """``QPointF`` / ``(x, y)`` 元组都收。

    笼相关接口两边都可能传（``cage_pending`` 给的是元组、覆盖层给的是
    ``QPointF``），强制调用方记两套只会踩坑。
    """
    if isinstance(point, QPointF):
        return QPointF(point)
    return QPointF(float(point[0]), float(point[1]))


def _project_on_segment(p: QPointF, a: QPointF, b: QPointF):
    """``p`` 在线段 ``ab`` 上的**投影点**与参数 ``t``（0=起点、1=终点）。

    笼边上就地加节点时用：新节点要**精确落在笼线上**（不是落在鼠标像素
    上），否则加点本身就会带来亚像素位移，"加点不改变形变"这条性质就
    不成立了。
    """
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
        #: 「适应窗口」时图片占视口的比例（1.0 = 铺满；见 set_fit_ratio）
        self._fit_ratio = 1.0
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
        # ---- 「变形」（变换笼）状态 ----
        #: 笼的**原始位置**（拖动前），形变映射的左端
        self._cage_home: list[QPointF] | None = None
        #: 笼的**当前节点位置**（拖动后），映射的右端
        self._cage: list[QPointF] | None = None
        #: 矩形笼的节点疏密（每边几段）
        self._cage_per_side = CAGE_PER_SIDE_DEFAULT
        #: 「影响范围」档位（CAGE_REACH_CHOICES 的下标；换算见 cage_influence）
        self._cage_reach = CAGE_REACH_DEFAULT
        #: 手绘笼进行中的顶点（None = 不在画笼模式）
        self._cage_drawing: list[QPointF] | None = None
        #: 手绘笼时的"皮筋"端点（鼠标位置，图片坐标）——点下一个点之前
        #: 先看到线会连到哪，落点才准
        self._cage_cursor = QPointF()
        #: 悬停/拖动中的笼节点下标
        self._cage_node: int | None = None
        #: 像素预览浮层 + 上次重算的时刻（节流用，见 _refresh_cage_preview）
        self._cage_item: QGraphicsPixmapItem | None = None
        self._cage_painted_at = 0.0
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
        self._clear_cage_preview()
        self._xf = QTransform()
        self._xf_touched = False
        self._cage_drawing = None
        self._cage_node = None
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
        if self._tool in ("crop", "transform", "cage"):
            # 换图（应用/撤销/还原都走这里）后选区重新默认全选：
            # 裁剪/变换的语义都是"从当前原图出发"，不是沿用旧图上的框
            self._rect = QRectF(self.image_rect())
            self._xf_pivot = self._rect.center()
        if self._tool == "cage":
            self._reset_cage_geometry()
        self._sync_overlay()

    def refresh(self) -> None:
        """像素被就地改过（擦除）后只刷显示，不动缩放与滚动位置。"""
        if self._item is not None and self._image is not None:
            self._item.setPixmap(QPixmap.fromImage(self._image))

    def replace_image(self, image: QImage) -> None:
        """就地换图（尺寸不变的语义，如文字写入）：不动缩放与滚动位置。"""
        self._image = image
        self.refresh()

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
        self._clear_cage_preview()
        self._cage_drawing = None
        self._cage_node = None
        self._xf = QTransform()
        self._xf_touched = False
        self._xf_reshape = False  # 调整范围是勾选态，换工具即复位
        self._hide_text_outline()
        if tool != "erase":
            self._hide_eraser_ring()
        if tool in ("crop", "transform", "cage") \
                and not self.image_rect().isNull():
            self._rect = QRectF(self.image_rect())
            self._xf_pivot = self._rect.center()
        else:
            self._rect = None
        if tool == "cage":
            self._reset_cage_geometry()
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

    # ------------------------------------------------------------ 变形（变换笼）
    # 口径与算法见 utils/cage_warp.py 的模块文档。画布这边只负责：
    #   ① 维护"笼原位 / 笼当前位置"两组顶点；
    #   ② 拖动时按 CAGE_PREVIEW_PIXELS 降采样出**像素预览**（全分辨率太慢）；
    #   ③ 覆盖层（笼线 + 节点）每帧跟手，覆盖层本身不碰像素。
    def cage_density(self) -> int:
        """矩形笼当前的节点疏密（每边几段）。"""
        return self._cage_per_side

    def set_cage_density(self, per_side: int) -> None:
        """改矩形笼的疏密：按当前选区重建笼（已拖动的节点位置丢弃）。"""
        self._cage_per_side = max(1, int(per_side))
        self.reset_cage()

    def cage_reach(self) -> int:
        """「影响范围」档位下标（见 :data:`CAGE_REACH_CHOICES`）。"""
        return self._cage_reach

    def set_cage_reach(self, index: int) -> None:
        """改「影响范围」：只影响**之后的**拖动，不必丢掉已有的形变。"""
        self._cage_reach = max(0, min(len(CAGE_REACH_CHOICES) - 1, int(index)))

    def cage_influence(self) -> float | None:
        """把「影响范围」档位换算成**绝对影响半径**（图片像素）；没动过则 None。

        档位记的是"拖动距离的倍数"而不是固定像素，是为了让手感一致：拖得远，
        受影响的面积自然大一点，但**相对比例不变**——这正是"像扯弹簧"该有的
        样子（近处变化大、远端几乎不动）。倍数下限由 ``utils.cage_warp`` 的
        防自交判据把着，真给太小也会被自动放宽。
        """
        if self._cage is None or self._cage_home is None:
            return None
        reach = 0.0
        for home, moved in zip(self._cage_home, self._cage):
            reach = max(reach, QLineF(home, moved).length())
        if reach <= 0.0:
            return None
        return reach * CAGE_REACH_CHOICES[self._cage_reach][0]

    def _reset_cage_geometry(self) -> None:
        """（不发信号）把笼重置成覆盖当前选区的矩形，原位=当前位置。"""
        # 笼被重建了，旧笼算出来的预览浮层已经没有意义（它是按旧笼的
        # 外接框裁的图），必须一并撤掉——留着就是一坨错位的像素
        self._clear_cage_preview()
        if self.image_rect().isNull():
            self._cage = None
            self._cage_home = None
            return
        rect = (self._rect or self.image_rect()).normalized()
        points = perimeter_cage(
            (rect.left(), rect.top(), rect.right(), rect.bottom()),
            self._cage_per_side)
        self._cage_home = [QPointF(x, y) for x, y in points]
        self._cage = [QPointF(point) for point in self._cage_home]

    def reset_cage(self) -> None:
        """「重置」：笼回到覆盖当前选区的默认矩形，丢掉未应用的形变。"""
        self._clear_cage_preview()
        self._cage_drawing = None
        self._cage_node = None
        self._reset_cage_geometry()
        self._sync_overlay()
        self._sync_cursor()

    def is_drawing_cage(self) -> bool:
        """是否正处在「重画笼」的手绘状态。"""
        return self._cage_drawing is not None

    def begin_cage_draw(self) -> None:
        """进入手绘笼（GIMP 的「创建或调整笼」）：逐点点击圈区域。"""
        self._clear_cage_preview()
        self._cage_drawing = []
        self._cage_cursor = QPointF()
        self._cage_node = None
        self._sync_overlay()
        self._sync_cursor()

    def cancel_cage_draw(self) -> None:
        """放弃手绘，保留原来的笼（若它已被拖动，预览一并恢复）。"""
        if self._cage_drawing is None:
            return
        self._cage_drawing = None
        self._sync_overlay()
        self._sync_cursor()
        self._refresh_cage_preview(force=True)

    def _close_cage(self) -> None:
        """闭合手绘多边形，把它变成新的笼（原位=当前位置，形变从零开始）。"""
        points = list(self._cage_drawing or [])
        if len(points) < 3:
            return
        self._cage_drawing = None
        self._cage_node = None
        self._cage_home = [QPointF(point) for point in points]
        self._cage = [QPointF(point) for point in points]
        self._clear_cage_preview()
        self._sync_overlay()
        self._sync_cursor()

    def cage_pending(self):
        """未应用的笼形变 ``(笼原位, 笼当前位置)``（(x, y) 元组列表）；无则 None。"""
        if self._cage is None or self._cage_home is None:
            return None
        if len(self._cage) < 3 or len(self._cage) != len(self._cage_home):
            return None
        home = [(point.x(), point.y()) for point in self._cage_home]
        moved = [(point.x(), point.y()) for point in self._cage]
        if not cage_moved(home, moved):
            return None
        return (home, moved)

    def cage_move_node(self, index: int, pos: QPointF) -> None:
        """把第 ``index`` 个笼把手拖到 ``pos``（图片坐标）。

        ⚠️ **允许拖到图片外面**（用户 2026-10-01：「任意点只能向内，不能向外」）。
        往外拖＝把那块内容往外**拉伸**，拉出画布的部分按越界填底。这里只留一个
        "一张图那么远"的宽松上限，免得把手被甩到天外、再也找不回来。
        """
        if self._cage is None or not 0 <= index < len(self._cage):
            return
        limit = self.image_rect()
        offset_x, offset_y = limit.width(), limit.height()
        self._cage[index] = QPointF(
            max(limit.left() - offset_x,
                min(pos.x(), limit.right() + offset_x)),
            max(limit.top() - offset_y,
                min(pos.y(), limit.bottom() + offset_y)))
        self._cage_node = index  # 拖着的这个点保持放大高亮
        self._sync_overlay()
        self._refresh_cage_preview()

    def _hit_cage_node(self, view_pos: QPointF) -> int | None:
        """命中笼节点（视图像素口径，不随缩放变）。"""
        if self._cage is None:
            return None
        for index, point in enumerate(self._cage):
            spot = QPointF(self.mapFromScene(point))
            if QLineF(view_pos, spot).length() <= CAGE_HIT_VIEW_PX:
                return index
        return None

    # ---- 像素预览（降采样 + 节流） ----
    def _clear_cage_preview(self) -> None:
        """丢掉像素预览浮层，并把节流时间戳一并清零。

        ⚠️ 清预览 = 「已经没有待应用的形变了」，所以下一次拖动是**全新的一轮**，
        必须立刻出画。若只删浮层、留下 ``_cage_painted_at``，那么刚
        「重置 / 重画笼 / 应用变形 / 采用笼」完紧接着拖的**第一次**会被
        :data:`CAGE_PREVIEW_INTERVAL` 的窗口吃掉——用户拖了半天画面一动不动，
        松开手才突然跳出来（真实踩到：这就是 ``fit()`` 空转那一类，见
        :meth:`_refresh_cage_preview` 的注释；这里把 reset/adopt 这条路径也堵上）。
        """
        self._cage_painted_at = 0.0
        if self._cage_item is not None:
            self._scene.removeItem(self._cage_item)
            self._cage_item = None

    def _refresh_cage_preview(self, force: bool = False) -> None:
        """重算"形变后"的像素预览（浮层）。

        ⚠️ 三层降本（缺一不可）：形变是逐像素重映射，源图是整页 4000×3000
        时全分辨率一次要 **3 秒**（实测拆解见 ``utils.cage_warp``）。

        - **范围**：形变本身是**局部**的，只算 :func:`warp_region` 给出的
          "影响盘并集外接框"——拖一个把手 60px 就只有 249×234 那么大；
          框外原图直接透出（那里位移场恒等于 0，逐字节等于原图，
          所以既不用整幅快照，也不会在框边留接缝）；
        - **分辨率**：按 :func:`cage_preview_scale` 降采样——它同时卡"屏幕
          上够清楚"和"工作量有上限"。拖动中取 :data:`CAGE_PREVIEW_PIXELS`
          （~0.06s，跟得上手），``force`` 时取 :data:`CAGE_PREVIEW_SETTLE_PIXELS`
          （松手了，停下来看清楚，~0.6s 上限）；
        - **时间**：:data:`CAGE_PREVIEW_INTERVAL` 之内不重复算（``force`` 跳过）。

        笼线/节点（覆盖层）每帧都跟手，与这里的节拍无关。
        """
        if self._image is None or self._cage is None or self._cage_home is None:
            return
        now = time.monotonic()
        if not force and now - self._cage_painted_at < CAGE_PREVIEW_INTERVAL:
            return
        home = [(point.x(), point.y()) for point in self._cage_home]
        moved = [(point.x(), point.y()) for point in self._cage]
        if not cage_moved(home, moved):
            # 没干活就不算"刚画过"：``_clear_cage_preview`` 会把时间戳清零，
            # 否则紧接着的第一次真拖动会被节流窗口吃掉，用户拖了半天画面
            # 一动不动（真实踩到：fit() 里的空转把时间戳刷成了"刚画"）。
            self._clear_cage_preview()
            return
        width, height = self._image.width(), self._image.height()
        influence = self.cage_influence()
        x0, y0, x1, y1 = warp_region(home, moved, influence,
                                     width=width, height=height)
        if x1 <= x0 or y1 <= y0:
            self._clear_cage_preview()
            return

        # 场景 1 单位 = 屏幕上 zoom × dpr 个设备像素（见 cage_preview_scale）
        scale = cage_preview_scale(
            x1 - x0, y1 - y0,
            self._zoom * max(1.0, self.devicePixelRatioF()),
            CAGE_PREVIEW_SETTLE_PIXELS if force else CAGE_PREVIEW_PIXELS)
        if scale >= 1.0:
            source = self._image
        else:
            source = self._image.scaled(
                max(1, int(round(width * scale))),
                max(1, int(round(height * scale))),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        warped = deform_cage_image(
            source,
            [(x * scale, y * scale) for x, y in home],
            [(x * scale, y * scale) for x, y in moved],
            influence=None if influence is None else influence * scale)
        # 取整后按**缩放坐标系**裁框、再按 1/scale 摆回图片坐标：位置与尺寸
        # 都精确对齐（若裁完再按原坐标摆，会有 1/scale 像素的错位）。
        left = int(math.floor(x0 * scale))
        top = int(math.floor(y0 * scale))
        right = min(warped.width(), int(math.ceil(x1 * scale)) + 1)
        bottom = min(warped.height(), int(math.ceil(y1 * scale)) + 1)
        if right <= left or bottom <= top:
            self._clear_cage_preview()
            return
        pixmap = QPixmap.fromImage(
            warped.copy(QRect(left, top, right - left, bottom - top)))
        pixmap.setDevicePixelRatio(1.0)
        if self._cage_item is None:
            self._cage_item = QGraphicsPixmapItem()
            self._cage_item.setZValue(4)  # 底图之上、覆盖层（11+）之下
            self._cage_item.setTransformationMode(
                Qt.TransformationMode.SmoothTransformation)
            self._scene.addItem(self._cage_item)
        self._cage_item.setPixmap(pixmap)
        self._cage_item.setPos(left / scale, top / scale)
        self._cage_item.setScale(1.0 / scale)
        self._cage_painted_at = now

    # ------------------------------------------------------------ 覆盖层
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
        # 「变形」的笼：**原位虚影**（点线，告诉你"原来在哪"）+ **当前位置**
        # （虚线）+ 节点圆点。用两套线是有意的——只画一条的话，把节点拖远
        # 之后就完全看不出内容是从哪儿被扯过来的了。
        self._cage_ghost = QGraphicsPolygonItem()
        self._cage_ghost.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._cage_ghost.setPen(QPen(QColor(T.INK_FAINT), 0, Qt.PenStyle.DotLine))
        self._cage_ghost.setZValue(11)
        self._cage_ghost.hide()
        self._scene.addItem(self._cage_ghost)
        # ⚠️ 当前笼用 **QPainterPath 而不是 QGraphicsPolygonItem**：手绘笼
        #    过程中要画"尚未闭合的折线"，PolygonItem 永远会自动闭合，看起来
        #    像已经圈好了。
        self._cage_poly = QGraphicsPathItem()
        self._cage_poly.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._cage_poly.setPen(QPen(QColor(T.ACCENT), 0, Qt.PenStyle.DashLine))
        self._cage_poly.setZValue(12)
        self._cage_poly.hide()
        self._scene.addItem(self._cage_poly)
        #: 笼节点圆点（数量随手绘/疏密变，按需增删）
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
        if self._tool == "cage" and self._image is not None:
            self._sync_cage_overlay()
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
    @staticmethod
    def _cage_path(points, close: bool) -> QPainterPath:
        """顶点序列 → 路径（``close=True`` 首尾相连成闭合多边形）。"""
        path = QPainterPath()
        if not points:
            return path
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        if close and len(points) >= 3:
            path.closeSubpath()
        return path

    def _sync_cage_overlay(self) -> None:
        """变形工具的覆盖层：原笼虚影 + 当前笼 + 节点圆点。

        种两种状态：

        - **手绘中**（``_cage_drawing``）：画"已点的点 + 到鼠标的皮筋"折线，
          第一个点画得更大（点回它即闭合）；不画原位虚影——正在圈新区域，
          画一个旧笼只会让人以为它已经生效了。
        - **常态**：当前笼（虚线闭合）+ 原笼原位（点线，只有真的拖动过才
          显示；没动过两条线完全重合，画出来只是糊成一条）。
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
        if self._cage_drawing is not None:
            points = list(self._cage_drawing)
            # 皮筋：从最后一点连到鼠标；已点 ≥3 点时再连回起点预览闭合形状
            rubber = points + [QPointF(self._cage_cursor)]
            if len(points) >= 3:
                rubber.append(QPointF(points[0]))
            self._cage_poly.setPath(self._cage_path(rubber, close=False))
            self._cage_poly.setVisible(True)
            self._cage_ghost.setVisible(False)
            self._sync_cage_dots(points, first_marked=True)
            return
        if self._cage is None or len(self._cage) < 3:
            self._cage_poly.setVisible(False)
            self._cage_ghost.setVisible(False)
            self._sync_cage_dots([])
            return
        self._cage_poly.setPath(self._cage_path(list(self._cage), close=True))
        self._cage_poly.setVisible(True)
        moved = self._cage_home is not None and cage_moved(
            [(p.x(), p.y()) for p in self._cage_home],
            [(p.x(), p.y()) for p in self._cage])
        if moved:
            self._cage_ghost.setPolygon(QPolygonF(list(self._cage_home)))
            self._cage_ghost.setVisible(True)
        else:
            self._cage_ghost.setVisible(False)
        self._sync_cage_dots(self._cage)

    def _sync_cage_dots(self, points, first_marked: bool = False) -> None:
        """按顶点数增删/摆放节点圆点（视觉尺寸 = 视图像素 ÷ 当前倍率）。

        悬停/拖动中的节点放大一圈：抓没抓住看圆点大小就知道。
        """
        zoom = max(self._zoom, 1e-6)
        base = CAGE_NODE_VIEW_PX / 2.0 / zoom
        hovered = base * 1.45
        while len(self._cage_dots) < len(points):
            item = QGraphicsEllipseItem()
            item.setZValue(13)
            self._scene.addItem(item)
            self._cage_dots.append(item)
        while len(self._cage_dots) > len(points):
            self._scene.removeItem(self._cage_dots.pop())
        for index, point in enumerate(points):
            item = self._cage_dots[index]
            big = (index == self._cage_node
                   or (first_marked and index == 0))
            radius = hovered if big else base
            item.setRect(QRectF(point.x() - radius, point.y() - radius,
                                radius * 2, radius * 2))
            if first_marked and index == 0:
                # 画笼时首点＝"点我闭合"的把手：换个色 + 描白边
                item.setBrush(QBrush(QColor(T.SURFACE)))
                item.setPen(QPen(QColor(T.ACCENT_HOVER), 0))
            else:
                item.setBrush(QBrush(QColor(T.ACCENT_HOVER if big else T.ACCENT)))
                item.setPen(QPen(QColor("#ffffff"), 0))
            item.setVisible(True)

    def _insert_cage_node(self, view_pos: QPointF) -> int | None:
        """点在笼边上 → 就地插一个把手，返回新把手下标。

        ⚠️ 两处讲究，少一样都会"加点即变"：

        1. 新把手**投到边上**，不是落在鼠标像素上（见 :func:`_project_on_segment`）；
        2. **原位与当前位置插同一个坐标**。形变只由"动过的把手"决定
           （``utils.cage_warp.moved_handles`` 只把 ``位移 > 0`` 的把手当约束），
           所以原位 = 当前位置的新把手**不进方程组**，形变逐字节不变。
           语义上也最顺：新把手抓的是"画面上现在这块内容"，
           接着拖就是继续拉同一块。

        自测盯着这条：加点前后 ``deform`` 逐字节相同（只是多个可拖的把手）。
        """
        if self._cage is None or self._cage_home is None \
                or len(self._cage) < 3:
            return None
        best: tuple[float, int] | None = None
        for index in range(len(self._cage)):
            a = QPointF(self.mapFromScene(self._cage[index]))
            b = QPointF(self.mapFromScene(
                self._cage[(index + 1) % len(self._cage)]))
            distance, _ = _segment_hit(view_pos, a, b)
            if distance <= CAGE_HIT_VIEW_PX * 1.8 \
                    and (best is None or distance < best[0]):
                best = (distance, index)
        if best is None:
            return None
        index = best[1]
        nxt = (index + 1) % len(self._cage)
        inside = self.image_rect()
        spot = self.mapToScene(view_pos.toPoint())
        projected, _t = _project_on_segment(
            QPointF(spot), QPointF(self._cage[index]),
            QPointF(self._cage[nxt]))
        added = QPointF(
            max(inside.left(), min(projected.x(), inside.right())),
            max(inside.top(), min(projected.y(), inside.bottom())))
        self._cage.insert(index + 1, QPointF(added))
        self._cage_home.insert(index + 1, QPointF(added))
        self._clear_cage_preview()  # 只加点没位移：预览等于原图，撤掉更省
        self._sync_overlay()
        return index + 1

    def cage_polygon(self) -> list[QPointF] | None:
        """当前笼的顶点（图片坐标，可能已被拖动）；不足 3 点返回 None。"""
        if self._cage is None or len(self._cage) < 3:
            return None
        return [QPointF(point) for point in self._cage]

    def adopt_cage(self, points) -> None:
        """把 ``points`` 直接立为笼（原位 = 当前位置 = 恒等形变）。

        ``points`` 收 ``QPointF`` 与 ``(x, y)`` 元组（见 :func:`_as_point`）。

        「应用变形」后用：形变已经烧进像素，**笼留在原地**——用户想接着
        微调同一块（古籍褶皱往往要来回试几次），不该逼他重新圈一遍。
        """
        inside = self.image_rect()
        clamped = [
            QPointF(max(inside.left(), min(point.x(), inside.right())),
                    max(inside.top(), min(point.y(), inside.bottom())))
            for point in map(_as_point, points)
        ]
        if len(clamped) < 3:
            self.reset_cage()
            return
        self._clear_cage_preview()
        self._cage_drawing = None
        self._cage_node = None
        self._cage_home = [QPointF(point) for point in clamped]
        self._cage = [QPointF(point) for point in clamped]
        self._sync_overlay()

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
        ``ratio``（见 :data:`CAGE_FIT_RATIO`：进「变形」时图片不顶满视口，
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
        self._refresh_cage_preview()

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
        self._refresh_cage_preview()  # 同上：预览清晰度跟倍率走（有节流）

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
        self._refresh_cage_preview()

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
        if self._tool == "cage" and self._item is not None:
            if self._cage_drawing is not None:
                # 画笼：点一个落点加一个顶点
                self.viewport().setCursor(Qt.CursorShape.CrossCursor)
                return
            index = self._hit_cage_node(view_pos)
            if index != self._cage_node:
                self._cage_node = index  # 悬停中的节点画大一圈
                self._sync_cage_overlay()
            self.viewport().setCursor(
                Qt.CursorShape.SizeAllCursor if index is not None
                else Qt.CursorShape.ArrowCursor)
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
            # 画笼是"点落点"的十字；常态箭头——笼上只有节点能拖，悬停到
            # 节点时由 _update_hover_cursor 换成移动光标
            "cage": (Qt.CursorShape.CrossCursor
                     if self._cage_drawing is not None
                     else Qt.CursorShape.ArrowCursor),
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
        if self._tool == "cage":
            if self._cage_drawing is not None:
                # 手绘笼：逐点圈区域；点回第一个点 = 闭合
                if len(self._cage_drawing) >= 3 and QLineF(
                        event.position(),
                        QPointF(self.mapFromScene(
                            self._cage_drawing[0]))).length() \
                        <= CAGE_CLOSE_VIEW_PX:
                    self._close_cage()
                else:
                    self._cage_drawing.append(QPointF(
                        max(inside.left(), min(pos.x(), inside.right())),
                        max(inside.top(), min(pos.y(), inside.bottom()))))
                    self._cage_cursor = QPointF(pos)
                    self._sync_overlay()
                event.accept()
                return
            index = self._hit_cage_node(event.position())
            if index is None:
                index = self._insert_cage_node(event.position())  # 点笼线加点
            if index is None:
                event.accept()
                return
            self._cage_node = index
            self._mode = ("cage", index)
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
            elif self._tool == "cage" and self._item is not None \
                    and self._cage_drawing is not None:
                # 手绘笼的**皮筋**跟随鼠标：点下一个落点之前先看见线往哪连
                self._cage_cursor = self.mapToScene(event.position().toPoint())
                self._sync_cage_overlay()
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
        elif kind == "cage":
            self.cage_move_node(self._mode[1], pos)
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
        if self._mode and self._mode[0] == "cage":
            # 松手补一次预览：拖动中可能正好被节流窗口跳过，最后一帧不补
            # 的话停在屏幕上的就不是松手位置的结果（所见≠将得）
            self._mode = None
            self._refresh_cage_preview(force=True)
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
        if self._cage_node is not None and self._mode is None:
            self._cage_node = None  # 悬停放大的节点缩回去
            self._sync_overlay()
        self._sync_cursor()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # 就地编辑文字时按键（含 ←/→ 移光标）全部给文本编辑，不走翻页
        if isinstance(self._scene.focusItem(), TextBlockItem):
            super().keyPressEvent(event)
            return
        # 画笼中按 Esc：放弃这次手绘，保留原来的笼
        if self._cage_drawing is not None \
                and event.key() == Qt.Key.Key_Escape:
            self.cancel_cage_draw()
            event.accept()
            return
        # ←/→ 别拿去滚动画布，交还弹窗（与预览弹窗一致：方向键是翻页）
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            event.ignore()
            return
        super().keyPressEvent(event)


# ------------------------------------------------------------------ 弹窗
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
        self.resize(1440, 940)
        self.setMinimumSize(1000, 680)
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
        self._cage_busy = False

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
        """Esc：先吃掉"进行中的手绘笼"，其次结束文字编辑，最后才关窗。

        ⚠️ 关窗 = 放弃本次全部编辑（状态行里写着），画笼画到一半一个 Esc
        把整轮编辑清掉太伤人——所以手绘态优先吃掉这个键（GIMP 同款）。
        """
        if self.canvas.is_drawing_cage():
            self.canvas.cancel_cage_draw()
            return
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
        if tool != "cage":
            self._commit_cage()
        self.canvas.set_tool(tool)
        # 进「变形」时图片不铺满视口，四周留出可操作空间——笼把手要能往
        # 图外拖，越靠边越需要留白（用户 2026-10-01 定）。离开时恢复铺满。
        self.canvas.set_fit_ratio(CAGE_FIT_RATIO if tool == "cage" else 1.0)
        for key, button in self._tool_buttons.items():
            button.setChecked(key == tool)
        layout = self._swap_option_page()
        if tool == "crop":
            self._page_crop(layout)
        elif tool == "transform":
            self._page_transform(layout)
        elif tool == "cage":
            self._page_cage(layout)
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

    def _page_cage(self, layout: QHBoxLayout) -> None:
        self._hint(layout,
                   "拖笼上的把手：那个把手附近的内容跟着走（近处动得多、"
                   "远处几乎不动），影响范围外的像素一动不动；"
                   "把手能拖到图外（往外拉＝拉伸），点笼线可就地加把手，"
                   "「重画笼」手绘任意闭合区域，点回起点闭合（Esc 放弃）")
        combo = ComboBox()
        combo.setFixedWidth(150)
        # NoFocus：别把键盘焦点从画布抢走（Esc 取消画笼要靠画布收键）
        combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for per_side, label in ((1, "4 点（四角）"), (2, "8 点（含边中点）"),
                                (3, "12 点")):
            combo.addItem(label, userData=per_side)
        combo.setCurrentIndex(
            max(0, combo.findData(self.canvas.cage_density())))
        combo.setToolTip("默认矩形笼的把手疏密（每边分几段）；一改就重建笼")
        layout.addWidget(QLabel("把手疏密"))
        layout.addWidget(combo)

        def apply_density(_index: int) -> None:
            value = combo.currentData()
            if value is None:
                return
            if self.canvas.cage_pending() is not None:
                # 重建笼会把已拖的形变丢掉：先把它落地（一个撤销点）
                self._commit_cage()
            self.canvas.set_cage_density(int(value))

        combo.currentIndexChanged.connect(apply_density)

        reach = ComboBox()
        reach.setFixedWidth(96)
        reach.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for index, (_times, label) in enumerate(CAGE_REACH_CHOICES):
            reach.addItem(label, userData=index)
        reach.setCurrentIndex(self.canvas.cage_reach())
        reach.setToolTip(
            "影响范围＝拖动距离的几倍：越紧凑越只动把手附近，越宽松牵连越大。"
            "只影响之后的拖动，不必重来")
        layout.addWidget(QLabel("影响范围"))
        layout.addWidget(reach)
        reach.currentIndexChanged.connect(
            lambda _i: self.canvas.set_cage_reach(int(reach.currentData())))

        draw_btn = PushButton("重画笼")
        draw_btn.setToolTip(
            "手绘一个闭合区域当笼：逐点点击，点回起点（或第一点）闭合；"
            "正在画时按 Esc 放弃。要换处理区域时用它")
        draw_btn.clicked.connect(self._begin_cage_draw)
        layout.addWidget(draw_btn)
        reset_btn = PushButton("重置")
        reset_btn.setToolTip("丢掉未应用的形变，笼回到覆盖整幅的默认矩形")
        reset_btn.clicked.connect(self.canvas.reset_cage)
        layout.addWidget(reset_btn)
        apply_btn = PrimaryPushButton("应用变形")
        apply_btn.setToolTip(
            "把当前形变按全分辨率烘焙进图片（可撤销）；"
            "应用后笼留在原地，方便接着微调")
        apply_btn.clicked.connect(self._commit_cage)
        layout.addWidget(apply_btn)

    def _begin_cage_draw(self) -> None:
        """「重画笼」：先把当前形变落地，再进入手绘（否则重画即丢形变）。"""
        if self.canvas.cage_pending() is not None:
            self._commit_cage()
        self.canvas.begin_cage_draw()

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
        self._image = bake_transform(self._image, rect, xf, region)
        self.canvas.set_image(self._image)

    # ------------------------------------------------------------ 变形
    def _commit_cage(self) -> None:
        """把未应用的**笼形变**烘焙进图片（一个撤销点），笼留在原地。

        「应用变形」按钮、切走工具、「完成」都走这里。形变是逐像素重映射
        （见 ``utils.cage_warp``），按**全分辨率**算——虽然影响是局部的
        （拖 60px 只有 249×234），把影响范围调宽时仍可能到秒级，所以挂
        等待光标；并且**防重入**——等待光标前那一下 ``processEvents``
        会派发排队事件，不防的话一次点击可能触发两遍（第二遍把已经形变过的
        图再形变一次，白丢一个撤销点、结果也不对）。
        """
        if not hasattr(self, "canvas") or self._cage_busy:
            return
        pending = self.canvas.cage_pending()
        if pending is None or self._image is None or self._image.isNull():
            # 没有未应用的形变：预览浮层本来就不存在（它只伴随形变出现），
            # 什么都不用清——这里**刻意不调** reset_cage：本函数在"切走到
            # 非变形工具"时也会被调，那时重建一个笼纯属白干
            return
        polygon = self.canvas.cage_polygon()
        home, moved = pending
        self._push_undo()
        self._cage_busy = True
        try:
            with wait_cursor():
                self._image = bake_cage(self._image, home, moved,
                                        self.canvas.cage_influence())
        finally:
            self._cage_busy = False
        self.canvas.set_image(self._image)
        if polygon is not None:
            # 形变已烧进像素，笼**留在原地**：古籍褶皱往往要来回试几次，
            # 每次应用后都回到全幅矩形笼的话，用户得重新圈一遍
            self.canvas.adopt_cage(polygon)

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
        """「完成」：未应用的变形/变换/未插入的文字一并写入，再应用全部编辑。"""
        self._commit_cage()
        self._commit_transform()
        self._commit_text_blocks()
        self.accept()

    # ------------------------------------------------------------ 对外
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
