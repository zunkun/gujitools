# -*- coding: utf-8 -*-
"""图片编辑弹窗：裁剪 / 拉伸 / 擦除 / 插入文字（Win10 照片风格）。

从图片预览弹窗（``image_zoom_dialog``）的「编辑」按钮进入，编辑的是
**画布当前整分辨率图**（已含翻转/旋转）；「完成」后写回弹窗画布——满意
就用弹窗原有的「下载」落盘，翻页/关窗即丢弃（预览可能是实时合成的虚拟
图，不是所有页都有文件可回写，所以统一走下载）。

四个工具的行为口径：

- **裁剪**：**默认选中整幅图**，沿四边/四角**任意位置**向内拖收边（整条
  边都是命中带，不只手柄小方块）、拖框中间移动；松手后**视图自动适配新
  选区**（选区变小就放大查看）。不做截图式"拖拽画框"——那是截图的交互，
  裁剪的语义是"从原图里收出想要的部分"（用户 20:05 定）。
- **拉伸**：先拖出一个源区域，再拖右/下边（或角）把区域内容**横向/纵向
  拉伸**（锚定左上）；应用后源区域先填白再把拉伸内容贴回——古籍整页
  白底，填白视觉上最干净。
- **擦除**：按住左键涂抹，圆头笔刷直接改像素（默认白色，古籍页面去污点
  就是涂白；可切黑）。一笔一个撤销点。
- **文字**：点击落点 → 输入文字 → 以当前字号/颜色画上去。每次插入一个
  撤销点。

⚠️ 撤销栈存的是**整图快照**（QImage 写时复制在就地绘制时仍会共享底层数据，
必须 ``copy()``），上限 12 步——4000px 预览约 60MB/步，再多内存吃不消。
"""
from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QImage, QKeySequence, QFontMetrics, QPainter,
    QPen, QPixmap, QShortcut,
)
from PySide6.QtWidgets import (
    QDialog, QFrame, QGraphicsLineItem, QGraphicsPixmapItem,
    QGraphicsRectItem, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel,
    QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    CaptionLabel, PrimaryPushButton, PushButton, RadioButton, Slider,
    ToggleButton, ToolButton,
)
from qfluentwidgets import FluentIcon as FIF

from desktop.ui import theme as T

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
#: 擦除笔刷粗细范围（图片像素）
BRUSH_MIN, BRUSH_MAX, BRUSH_DEFAULT = 4, 160, 24
#: 插入文字字号范围（图片像素高）
TEXT_MIN, TEXT_MAX, TEXT_DEFAULT = 12, 240, 48

#: 左侧工具栏：（键, 图标, 中文名）
TOOLS = (
    ("crop", FIF.CUT, "裁剪"),
    ("stretch", FIF.MOVE, "拉伸"),
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


def stretch_region(image: QImage, src: QRectF, dst: QRectF) -> QImage:
    """把 ``src`` 区域的内容拉伸贴到 ``dst``（画布尺寸不变）。

    先把**源区域**填白再贴拉伸结果：目标比源小时，源区域多出来的部分
    如果留原像素会形成"重影带"；古籍是白底页，填白最干净。
    两个区域都先夹进画布再裁。
    """
    bounds = QRectF(0, 0, image.width(), image.height())
    src = clamp_rect(src, bounds)
    dst = clamp_rect(dst, bounds)
    if src.isEmpty() or dst.isEmpty():
        return image
    region = image.copy(src.toRect())
    result = image.copy()
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.fillRect(src, Qt.GlobalColor.white)
    painter.drawImage(dst, region)
    painter.end()
    return result


def draw_text(image: QImage, pos: QPointF, text: str, px: int,
              color: QColor) -> QImage:
    """在 ``pos``（文字块左上角）画文字（可多行，行距 1.25 倍）；空文本原样返回。"""
    if not text.strip():
        return image
    result = image.copy()
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    font = QFont(T.FONT_FAMILY)
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


# ------------------------------------------------------------------ 画布
class EditorCanvas(QGraphicsView):
    """编辑画布：滚轮缩放、中/右键拖拽平移、左键按工具交互。

    场景坐标 = 图片像素（pixmap 刻意不设 devicePixelRatio，与预览弹窗同
    口径）。选区矩形（裁剪/拉伸共用）几何全部落在**图片坐标系**，缩放
    只影响显示。裁剪与拉伸的交互不同：裁剪**默认全选**只许收边，拉伸
    仍要"拖拽画框"选出源区域。
    """

    #: 擦除一笔开始（弹窗借此压撤销点）
    stroke_started = Signal()
    #: 在文字工具下单击了某个落点（图片坐标，已夹进画布）
    text_requested = Signal(QPointF)

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
        self._rect: QRectF | None = None          # 当前选区（图片坐标）
        self._rect_src: QRectF | None = None      # 拉伸的源区域（选区定格时）
        self._mode: tuple | None = None           # 进行中的拖拽
        self._hover_handle: str | None = None     # 悬停/拖动中的手柄（光标+高亮）
        self._erase_color = QColor("#ffffff")
        self._erase_size = BRUSH_DEFAULT
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QColor(T.SURFACE_SOFT))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        # 悬停就要更新光标形态（默认只在按住时才来 move 事件）
        self.setMouseTracking(True)
        self._build_overlay()
        self._sync_cursor()

    # ------------------------------------------------------------ 装图
    def set_image(self, image: QImage | None) -> None:
        """装入/替换图片并重新适应窗口（裁剪/撤销等"画布换图"也走这里）。"""
        if getattr(self, "_border", None) is not None:
            self._scene.removeItem(self._border)
        self._border = None
        self._rect = None
        self._rect_src = None
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
        if self._tool == "crop":
            # 换图（裁剪应用/撤销/还原都走这里）后裁剪区重新默认全选：
            # 裁剪的语义是"从当前原图收边"，不是沿用旧图上的框
            self._rect = QRectF(self.image_rect())
            self._rect_src = None
        self._sync_overlay()

    def refresh(self) -> None:
        """像素被就地改过（擦除）后只刷显示，不动缩放与滚动位置。"""
        if self._item is not None and self._image is not None:
            self._item.setPixmap(QPixmap.fromImage(self._image))

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
        """切换工具：裁剪默认全选（只许收边），其余清选区、换光标。"""
        self._tool = tool
        self._rect_src = None
        self._mode = None
        if tool == "crop" and not self.image_rect().isNull():
            self._rect = QRectF(self.image_rect())
        else:
            self._rect = None
        self._sync_overlay()
        self._sync_cursor()

    def set_brush(self, size: int, color: QColor) -> None:
        """设置擦除笔刷（图片像素直径与颜色）。"""
        self._erase_size = max(1, int(size))
        self._erase_color = QColor(color)

    def selection(self) -> QRectF | None:
        """当前选区（图片坐标）；不足最小边视为没有。"""
        if self._rect is None:
            return None
        rect = self._rect.normalized()
        if rect.width() < MIN_RECT_EDGE or rect.height() < MIN_RECT_EDGE:
            return None
        return rect

    def stretch_source(self) -> QRectF | None:
        """拉伸的源区域（选区第一次定格时的位置）。"""
        return self._rect_src

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
        visible = (
            self._tool in ("crop", "stretch")
            and self._rect is not None and self._image is not None
        )
        if not visible:
            for item in self._mask:
                item.setVisible(False)
            self._sel_border.setVisible(False)
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

    # ------------------------------------------------------------ 缩放
    def fit(self) -> None:
        """适应窗口（整图完整可见）。"""
        if self._item is None or self.viewport().width() <= 1:
            return  # 控件还没布局：此时 fit 算出来的是脏值，等 resizeEvent 再来
        self.fitInView(self.image_rect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.transform().m11()))
        self._user_zoomed = False
        # ⚠️ 手柄的几何 = 视图像素 ÷ 当前倍率，倍率变了必须重算覆盖层；
        #    不然 set_image 时用脏 viewport 算的小倍率会留下巨型手柄
        #    （离屏渲染抓出来的：手柄有 ~150 视图像素，应为 12）。
        self._sync_overlay()

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
            self._tool in ("crop", "stretch")
            and self._rect is not None
            and self._hover_handle is not None
        )
        for name, item in self._edge_lines.items():
            # 名字包含判断对单边/角手柄都成立："tl" 含 "t""l"、"bl" 含 "b""l"
            item.setVisible(active and name in self._hover_handle)

    def _update_hover_cursor(self, view_pos: QPointF) -> None:
        """未拖拽时的悬停反馈：命中边缘给方向缩放光标 + 边界高亮。"""
        if self._tool not in ("crop", "stretch") or self._item is None:
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
        cursor = {
            # 裁剪默认有框：箭头（手柄收边/框内移动），不是"准备画框"的十字
            "crop": Qt.CursorShape.ArrowCursor,
            "stretch": Qt.CursorShape.CrossCursor,
            "erase": Qt.CursorShape.CrossCursor,
            "text": Qt.CursorShape.IBeamCursor,
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
        if self._tool == "stretch":
            handle = self._hit_handle(event.position())
            self._hover_handle = handle
            self._apply_hover_highlight()
            if handle is not None and self._rect is not None:
                self._mode = ("handle", handle)
            elif self._rect is not None and \
                    self._rect.normalized().contains(pos):
                self._mode = ("move", pos, QPointF(self._rect.topLeft()))
            else:
                self._rect = QRectF(pos, pos)
                self._rect_src = None
                self._mode = ("rubber", pos)
            self._sync_overlay()
            event.accept()
            return
        if self._tool == "erase":
            self.stroke_started.emit()
            self._erase_at(pos, pos)
            self._mode = ("draw", pos)
            event.accept()
            return
        if self._tool == "text":
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
            # 未拖拽：悬停反馈（方向缩放光标 + 边界高亮），需要 mouseTracking
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
        if kind == "rubber":
            self._rect = clamp_rect(QRectF(self._mode[1], pos), inside)
        elif kind == "move":
            start, origin = self._mode[1], self._mode[2]
            delta = pos - start
            moved = self._rect.normalized().translated(delta)
            moved.moveTopLeft(clamp_rect(moved, inside).topLeft())
            self._rect = moved
            if self._rect_src is not None:
                self._rect_src = self._rect_src.translated(delta)
        elif kind == "handle":
            self._resize_rect(self._mode[1], pos)
        elif kind == "draw":
            self._erase_at(self._mode[1], pos)
            self._mode = ("draw", pos)
        self._sync_overlay()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._mode and self._mode[0] == "pan":
            self._mode = None
            self._sync_cursor()
            event.accept()
            return
        if self._mode and self._mode[0] in ("rubber", "move", "handle"):
            # 选区定格：拉伸工具在这里记住源区域（拖手柄拉伸的基准）
            if self._tool == "stretch" and self._rect_src is None:
                self._rect_src = self._rect.normalized()
            refit = self._tool == "crop" and self._mode[0] in ("move", "handle")
            self._mode = None
            self._sync_overlay()
            if refit:
                # 裁剪区变了 → 视图跟着新区域缩放（变小就放大查看）
                self.fit_selection()
            event.accept()
            return
        if self._mode and self._mode[0] == "draw":
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
        """圆头笔刷在图上就地画一段线，并刷新显示。"""
        if self._image is None:
            return
        painter = QPainter(self._image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(self._erase_color, float(self._erase_size))
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
        # 鼠标离开画布：高亮熄灭、光标回到工具默认形态
        self._hover_handle = None
        self._apply_hover_highlight()
        self._sync_cursor()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
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

    def __init__(self, parent=None, image: QImage | None = None):
        super().__init__(parent)
        self.setWindowTitle("图片编辑")
        self.setModal(True)
        # 编辑要看得清字迹：默认开大，并带最小化/最大化按钮（标题栏双击
        # 最大化也随 maximize 按钮生效），用户 20:18 定
        self.resize(1440, 940)
        self.setMinimumSize(1000, 680)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
        )
        base = image if image is not None else QImage()
        # 统一转 ARGB32：rembg 产物可能是调色板 PNG，就地绘制需要真彩格式
        self._original = base.convertToFormat(QImage.Format_ARGB32)
        self._image = self._original.copy()
        self._undo: list[QImage] = []
        self._redo: list[QImage] = []
        self._option_page: QWidget | None = None
        # 文字工具选项的活性引用（插入时现读，见 _text_settings）
        self._text_size: int = TEXT_DEFAULT
        self._text_color: str = "#000000"

        self.canvas = EditorCanvas(self)
        self.canvas.set_image(self._image)
        self.canvas.stroke_started.connect(self._push_undo)
        self.canvas.text_requested.connect(self._insert_text)

        root = QVBoxLayout(self)
        root.setContentsMargins(T.SPACE_MD, T.SPACE_MD, T.SPACE_MD, T.SPACE_MD)
        root.setSpacing(T.SPACE_SM)
        # ⚠️ 两行结构（Win10 照片的布局）：主工具栏一行摆不下撤销/还原/
        #    缩放/四个工具/提示/应用/完成，一行时左侧按钮会被挤出窗口
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
        ):
            QShortcut(seq, self).activated.connect(slot)

    # ------------------------------------------------------------ 构建
    def _build_toolbar_row(self) -> QHBoxLayout:
        """主工具栏：撤销/还原 ｜ 缩放 ｜ 四个工具 ｜ … ｜ 完成。"""
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
            "应用全部编辑并回到预览；满意再用预览弹窗的「下载」保存文件"
        )
        self.done_btn.clicked.connect(self.accept)
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
        """切换工具并重建选项区。"""
        if not hasattr(self, "canvas"):
            return  # 构建期先于画布存在，等 __init__ 末尾再真切换
        self.canvas.set_tool(tool)
        for key, button in self._tool_buttons.items():
            button.setChecked(key == tool)
        layout = self._swap_option_page()
        if tool == "crop":
            self._page_crop(layout)
        elif tool == "stretch":
            self._page_stretch(layout)
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

    def _page_stretch(self, layout: QHBoxLayout) -> None:
        self._hint(layout, "拖拽选出区域，再拖右/下边（角）把内容拉伸，空出处填白")
        apply_btn = PrimaryPushButton("应用拉伸")
        apply_btn.setToolTip("按当前拖出的目标范围拉伸选区内容（可撤销）")
        apply_btn.clicked.connect(self._apply_stretch)
        layout.addWidget(apply_btn)

    def _color_picker(self, on_change, default_black: bool = False) -> tuple[
            RadioButton, RadioButton]:
        """「白/黑」二选一（擦除与文字共用），返回 (白, 黑)。

        只连**白**的 toggled：二选一里切换任何一侧都会触发它，一处连线
        就够。``default_black``：文字默认黑（白纸上黑字），擦除默认白。
        """
        white = RadioButton("白")
        black = RadioButton("黑")
        white.setChecked(not default_black)
        black.setChecked(default_black)
        white.toggled.connect(on_change)
        layout = self._option_page.layout()
        layout.addWidget(QLabel("颜色"))
        layout.addWidget(white)
        layout.addWidget(black)
        return white, black

    def _page_erase(self, layout: QHBoxLayout) -> None:
        self._hint(layout, "按住左键在污点上涂抹（古籍页面去污点=涂白）")
        size_label = CaptionLabel(f"{BRUSH_DEFAULT}px")
        slider = Slider(Qt.Orientation.Horizontal)
        slider.setRange(BRUSH_MIN, BRUSH_MAX)
        slider.setValue(BRUSH_DEFAULT)
        slider.setFixedWidth(160)

        def apply_size(value: int) -> None:
            size_label.setText(f"{value}px")
            self.canvas.set_brush(value, self._erase_picker_color)

        white, black = self._color_picker(
            lambda _=False: self.canvas.set_brush(
                slider.value(), self._erase_picker_color
            )
        )
        self._erase_white = white
        slider.valueChanged.connect(apply_size)
        layout.addWidget(QLabel("笔刷粗细"))
        layout.addWidget(slider)
        layout.addWidget(size_label)
        # 初次进入按默认笔刷生效
        self.canvas.set_brush(BRUSH_DEFAULT, QColor("#ffffff"))

    @property
    def _erase_picker_color(self) -> QColor:
        white = getattr(self, "_erase_white", None)
        if white is not None and not white.isChecked():
            return QColor("#000000")
        return QColor("#ffffff")

    def _page_text(self, layout: QHBoxLayout) -> None:
        self._hint(layout, "点击图片上的落点，输入要插入的文字")
        size_label = CaptionLabel(f"{self._text_size}px")
        slider = Slider(Qt.Orientation.Horizontal)
        slider.setRange(TEXT_MIN, TEXT_MAX)
        slider.setValue(self._text_size)
        slider.setFixedWidth(160)
        slider.valueChanged.connect(
            lambda value: (size_label.setText(f"{value}px"),
                           setattr(self, "_text_size", value))
        )
        white, black = self._color_picker(
            lambda _=False: setattr(
                self, "_text_color",
                "#ffffff" if white.isChecked() else "#000000",
            ),
            default_black=True,  # 白纸上的文字，默认黑
        )
        layout.addWidget(QLabel("字号"))
        layout.addWidget(slider)
        layout.addWidget(size_label)

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
        self._redo.append(self._image.copy())
        self._image = self._undo.pop()
        self.canvas.set_image(self._image)
        self._sync_undo_buttons()

    def _redo_now(self) -> None:
        if not self._redo:
            return
        self._undo.append(self._image.copy())
        self._image = self._redo.pop()
        self.canvas.set_image(self._image)
        self._sync_undo_buttons()

    def _reset_all(self) -> None:
        """还原到打开时的图（还原本身可撤销）。"""
        if self._original.isNull():
            return
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

    def _apply_stretch(self) -> None:
        rect = self._selection()
        src = self.canvas.stretch_source()
        if rect is None or src is None or self._image is None:
            return
        self._push_undo()
        self._image = stretch_region(self._image, src, rect)
        self.canvas.set_image(self._image)

    def _insert_text(self, pos: QPointF) -> None:
        """文字工具点击落点 → 输入 → 画上去（一个撤销点）。"""
        from PySide6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getMultiLineText(
            self, "插入文字", "要插入的文字（可换行）：", "",
        )
        if not ok or not text.strip():
            return
        self._push_undo()
        self._image = draw_text(
            self._image, pos, text, self._text_size, QColor(self._text_color)
        )
        self.canvas.set_image(self._image)

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
