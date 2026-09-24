# -*- coding: utf-8 -*-
"""图片预览弹窗：拖拽平移、滚轮/按钮缩放、翻转旋转、下载、翻页。

为什么不把缩放直接做在 ``ImageView`` 上：那是**框编辑**画布——点击选中、
拖拽移动整框、四角缩放、空白拖拽手绘。再叠一层"滚轮缩放 + 拖拽平移"，
两种拖拽立刻打架（拖框 vs 拖画布），而框坐标是 detect/rembg 的实际输出依据，
误操作代价高。所以编辑仍留在原处（固定"适应窗口"），弹窗只做**只读**查看。

渲染密度由弹窗自己算（``_render_edge``：视口物理长边 × ``RENDER_HEADROOM``，
再受宿主给的 ``ZoomTarget.cap`` 与 :data:`MAX_RENDER_EDGE` 约束），宿主只提供
``render(edge) -> worker``。这样「图片按最长边解码」「PDF 按该边长渲染」
「打印效果按该边长反推 px/mm 重新排版」三种口径各归各家，弹窗不必区分。

⚠️ 缩放倍率的语义：**1.0 = 100% = 1 图片像素对 1 设备像素**（QGraphicsView 的
变换比例 = 倍率 ÷ dpr）。所以场景里的 pixmap 刻意**不设** devicePixelRatio
（1 场景单位 = 1 图片像素），否则这套换算会再叠一个 dpr。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QIcon, QImage, QPainter, QPen, QPixmap, QPolygonF, QTransform,
)
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QGraphicsPixmapItem, QGraphicsScene,
    QGraphicsView, QHBoxLayout, QVBoxLayout, QWidget,
)
from qfluentwidgets import CaptionLabel, PrimaryPushButton, PushButton, ToolButton
from qfluentwidgets import FluentIcon as FIF

from desktop.ui import theme as T
from desktop.ui.widgets import apply_to
from desktop.workers import WorkerHost, connect_queued

#: 缩放档位。按档位走而不是连续乘：按钮连点不会累积浮点漂移，步长也可预期
#: （标准看图器的做法）。
ZOOM_STOPS = (
    0.1, 0.125, 0.167, 0.25, 0.333, 0.5, 0.667, 0.75,
    1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0,
)
MIN_ZOOM = ZOOM_STOPS[0]
MAX_ZOOM = ZOOM_STOPS[-1]
#: 滚轮一格的倍率（连续缩放手感，不落档位）
WHEEL_STEP = 1.15

#: 渲染密度余量：图片按"视口物理长边 × 这个倍数"渲染。
#: ⚠️ 它买到的**不是**"放到 150% 也不糊"——倍率是相对**图片自身**像素定义的
#: （1.0 = 一个图片像素对一个设备像素），所以任何 >100% 的显示都是放大，
#: 与源图多少像素无关。余量的真实作用是：100% 时能看到**比窗口大 1.5 倍**的
#: 那块区域，且每个图片像素都精确落在一个设备像素上（可以放心平移看细节）。
RENDER_HEADROOM = 1.5
#: 渲染密度下限：控件还没布局（视口尺寸为 0）时的兜底，也避免小窗下面目全非。
MIN_RENDER_EDGE = 1600
#: 渲染密度上限：4000px 竖页约 45 MB（RGB32），是清晰度与内存的折中。
MAX_RENDER_EDGE = 4000
#: 下载为 JPEG 时的画质
JPEG_QUALITY = 90


def display_transform(rotation: int = 0, flip_h: bool = False,
                      flip_v: bool = False) -> QTransform:
    """翻转/旋转的变换矩阵——**屏幕与导出必须共用这一个**。

    ⚠️ 屏幕侧走 ``QGraphicsPixmapItem.setTransform``、导出侧走
    ``QImage.transformed``。两处若各写一份，改一处就会出现「看到的和下载的
    不一样」（翻转轴或旋转方向不一致）。
    """
    transform = QTransform()
    if flip_h or flip_v:
        transform = transform.scale(
            -1.0 if flip_h else 1.0, -1.0 if flip_v else 1.0
        )
    return transform * QTransform().rotate(float(rotation) % 360.0)


#: 可拖拽留白：每边各留视口的这个比例，图片在任何缩放下都能被拖动。
#:
#: ⚠️ 必须**大于 0**：Qt 的滚动范围 = 内容显示尺寸 − 视口尺寸。图片在适应窗口时
#: 正好铺满视口，范围就是 0，``ScrollHandDrag`` 一点都拖不动（用户报的"不缩放就
#: 不能拖拽移动"）。留白正好等于视口也不行——那是"内容=视口"，范围仍然是 0。
PAN_MARGIN_RATIO = 0.25


def mirrored_rotate_icon() -> QIcon:
    """``FIF.ROTATE`` 的水平镜像 = **逆时针（左旋）**。

    qfluentwidgets 只提供一个旋转图标：ROTATE 的箭头在弧线底部**指向左**，
    即顺时针（右旋）。左旋用它的镜像，两颗按钮的笔触天然一致、只差方向。

    多档位 pixmap 是为了高分屏下不掉清晰度（图标源是 SVG，按需渲染）。
    """
    source = FIF.ROTATE.icon()
    icon = QIcon()
    for edge in (16, 20, 24, 32, 48):
        icon.addPixmap(
            source.pixmap(QSize(edge, edge)).transformed(
                QTransform().scale(-1.0, 1.0)
            )
        )
    return icon


#: 自绘图标的颜色：与 FluentIcon 在浅色主题下的渲染色一致（图标源是
#: ``Rotate_black.svg`` 这类黑描边）。应用目前只有浅色主题（app.py setTheme(LIGHT)），
#: 所以固定一个色即可；真要支持深色主题，这里跟着主题取色。
ICON_COLOR = QColor(0, 0, 0)


def _flip_pixmap(size: int, horizontal: bool, color: QColor) -> QPixmap:
    """画一个"镜像轴 + 两个相对三角"的翻转图标（水平/垂直只差 90° 旋转）。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(size / 2.0, size / 2.0)
    if not horizontal:
        painter.rotate(90)
    painter.translate(-size / 2.0, -size / 2.0)
    margin, center, gap = size * 0.10, size / 2.0, size * 0.07
    pen = QPen(color, max(1.0, size * 0.055), Qt.PenStyle.DashLine)
    pen.setDashPattern([1.6, 1.4])   # 默认虚线在这个尺寸下太碎，改长一点
    painter.setPen(pen)
    painter.drawLine(QPointF(center, margin), QPointF(center, size - margin))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF([
        QPointF(margin, margin), QPointF(center - gap, center),
        QPointF(margin, size - margin),
    ]))
    painter.drawPolygon(QPolygonF([
        QPointF(size - margin, margin), QPointF(center + gap, center),
        QPointF(size - margin, size - margin),
    ]))
    painter.end()
    return pixmap


def flip_icon(horizontal: bool = True, color: QColor | None = None) -> QIcon:
    """翻转按钮的图标（水平/垂直 = 同一个图形转 90°）。

    qfluentwidgets 没有可用的翻转图标：``SEARCH_MIRROR`` 是"带镜子的放大镜"，
    语义不对；``SYNC`` 是循环箭头。自绘还有个好处——一对图标笔触完全一致，
    且按需渲染，任意 dpr 下都锐利。
    """
    icon = QIcon()
    for edge in (16, 20, 24, 32, 48):
        icon.addPixmap(_flip_pixmap(edge, horizontal, color or ICON_COLOR))
    return icon


def save_image(image: QImage, path: str | Path,
               quality: int = JPEG_QUALITY) -> bool:
    """把 QImage 写到磁盘：``.jpg``/``.jpeg`` 走有损（quality），其余交给 Qt。

    单独抽出来是为了可测——保存对话框在离屏环境里弹不出来。
    """
    target = Path(path)
    if target.suffix.lower() in (".jpg", ".jpeg"):
        return bool(image.save(str(target), "JPEG", quality))
    return bool(image.save(str(target)))


class ZoomTarget:
    """弹窗某一页的数据来源（宿主在**主线程**里按页现造）。

    ``render`` 会在 **worker 线程**被调用，所以它只能读构造时快照下来的值
    （路径、参数字典……），**不得**碰任何 QWidget——同 ``worker_thread_affinity``
    的约束。
    """

    __slots__ = ("render", "note", "stem", "count", "original", "cap")

    def __init__(self, render, note: str = "", stem: str = "", count: int = 1,
                 original=None, cap: int | None = None):
        """render: ``(edge:int) -> worker``；cap: 渲染密度上限（如原图原生边长）。"""
        self.render = render
        self.note = note or "预览"
        self.stem = stem or "preview"
        self.count = max(1, int(count))
        self.original = original  # QSize | None：原始像素尺寸（状态条用）
        self.cap = cap            # int | None：超过它渲染没有意义（会白放大）


class ZoomableCanvas(QGraphicsView):
    """缩放画布：滚轮以光标为锚点缩放、左键拖拽平移、双击切换适应/100%。"""

    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        """初始化场景、拖拽平移与锚点缩放（锚点由 QGraphicsView 原生支持）。"""
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item: QGraphicsPixmapItem | None = None
        self._image: QImage | None = None
        self._zoom = 1.0
        self._rotation = 0
        self._flip_h = False
        self._flip_v = False
        #: 用户是否手动缩放过。没动过就在换图/旋转/改窗大小时自动"适应窗口"，
        #: 动过就保持倍率（只看当前这块，别把用户拽回全局视图）。
        self._user_zoomed = False
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        # ⚠️ 用 NoAnchor：缩放锚点由 set_zoom 自己算（见那里的说明），别让 Qt
        # 的 AnchorUnderMouse 插一脚再被覆盖。
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QColor(T.SURFACE_SOFT))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # ⚠️ 不接收焦点：方向键要留给弹窗翻页（QGraphicsView 默认会用它们滚动画布）
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumSize(420, 320)

    # ------------------------------------------------------------------ 状态
    @property
    def has_image(self) -> bool:
        """当前是否已装入图片。"""
        return self._item is not None and self._image is not None

    @property
    def zoom(self) -> float:
        """当前缩放倍率（1.0 = 100% = 1 图片像素对 1 设备像素）。"""
        return self._zoom

    # ------------------------------------------------------------------ 装图
    def set_image(self, image: QImage | None) -> None:
        """装入图片并复位（适应窗口、清空翻转旋转）。"""
        self._scene.clear()
        self._item = None
        self._image = None if image is None or image.isNull() else image
        self._rotation, self._flip_h, self._flip_v = 0, False, False
        self._user_zoomed = False
        if self._image is None:
            self._sync_scene_rect()
            return
        pixmap = QPixmap.fromImage(self._image)
        # ⚠️ 刻意不设 devicePixelRatio：让 1 场景单位 = 1 图片像素，
        # 倍率换算才干净（zoom = 变换比例 × dpr，见 _sync_zoom）。
        pixmap.setDevicePixelRatio(1.0)
        item = QGraphicsPixmapItem(pixmap)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._scene.addItem(item)
        self._item = item
        self._apply_item_transform()
        self.fit()

    def clear(self) -> None:
        """卸载图片（关窗时释放大图内存）。"""
        self._scene.clear()
        self._item = None
        self._image = None
        self._sync_scene_rect()

    # ------------------------------------------------------------------ 缩放
    def fit(self) -> None:
        """适应窗口：整图完整可见（保持宽高比）。"""
        if self._item is None or self.viewport().width() <= 1:
            return
        rect = self.image_rect()   # ⚠️ 用图片占位，不能用被扩展过的 sceneRect
        if rect.isEmpty():
            return
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._user_zoomed = False
        self._sync_zoom()
        self._sync_scene_rect()

    def set_zoom(self, zoom: float, anchor_pos: QPointF | None = None) -> None:
        """设置缩放倍率。

        ``anchor_pos`` 是**视口坐标**下的不动点（滚轮传光标位置）；不传则以
        视口中心为不动点。

        ⚠️ 刻意**不用** Qt 的 ``AnchorUnderMouse``：它依赖私有的
        ``lastMouseEventPosition``，弹窗刚打开就滚轮时那个值可能是陈旧的
        （实测会退化成左上角），缩放会突然跳到一边。这里自己按"锚点处的场景
        点在缩放前后保持不动"来算，结果只取决于传入的位置，既可预期也可测。
        """
        if self._item is None:
            return
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, float(zoom)))
        if abs(zoom - self._zoom) < 1e-6:
            return
        if anchor_pos is None:
            anchor_pos = QPointF(self.viewport().rect().center())
        anchor_scene = self.mapToScene(anchor_pos.toPoint())
        previous = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        try:
            factor = zoom / self._zoom
            self.scale(factor, factor)
            # 缩放时滚动量不变 → 场景点整体被缩成 1/factor。把这段偏差按**场景
            # 单位**平移回视图变换上，锚点就精确回到光标处。
            # ⚠️ 别用 ``centerOn`` 补这段偏差：它内部把滚动量取整，实测残留
            # ~0.9px 漂移且随步数累积；``translate`` 改的是连续变换，实测 0 漂移。
            moved = self.mapToScene(anchor_pos.toPoint())
            self.translate(moved.x() - anchor_scene.x(),
                           moved.y() - anchor_scene.y())
        finally:
            self.setTransformationAnchor(previous)
        self._zoom = zoom
        self._user_zoomed = True
        self.zoom_changed.emit(self._zoom)
        # 可拖范围随缩放变化：缩小时要给出留白（否则拖不动），放大时留白收回
        self._sync_scene_rect()

    def zoom_in(self) -> None:
        """放大到下一档。"""
        self._step_stop(forward=True)

    def zoom_out(self) -> None:
        """缩小到上一档。"""
        self._step_stop(forward=False)

    def _step_stop(self, forward: bool) -> None:
        """跳到相邻档位（档位表是唯一事实来源，别在这里另算步长）。"""
        stops = ZOOM_STOPS if forward else tuple(reversed(ZOOM_STOPS))
        reference = self._zoom * (1.001 if forward else 0.999)
        for stop in stops:
            hit = stop > reference if forward else stop < reference
            if hit:
                self.set_zoom(stop)
                return
        self.set_zoom(MAX_ZOOM if forward else MIN_ZOOM)

    def _sync_zoom(self) -> None:
        """从当前变换反推倍率（fitInView 这类外部改过变换后必须校准）。

        倍率 = 变换比例 × dpr：场景 1 单位是 1 图片像素，经变换放大 s 倍落到
        逻辑像素、再乘 dpr 落成设备像素，所以"每个图片像素占多少设备像素"
        就是 s·dpr。
        """
        dpr = self.devicePixelRatioF() or 1.0
        self._zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.transform().m11() * dpr))
        self.zoom_changed.emit(self._zoom)

    def image_rect(self) -> QRectF:
        """图片在**场景坐标**里的实际占位（1 场景单位 = 1 图片像素）。

        ⚠️ 与 ``sceneRect()`` 区分：场景矩形为了"没缩放也能拖"会被**居中扩展**
        到至少视口那么大（见 :meth:`_sync_scene_rect`），所以几何/朝向判断一律
        用本方法，只有滚动范围与 fitInView 的留白才看 ``sceneRect()``。
        """
        if self._item is None:
            return QRectF()
        return self._item.mapRectToScene(self._item.boundingRect())

    # ------------------------------------------------------------------ 朝向
    def rotate_clockwise(self) -> None:
        """顺时针旋转 90°。"""
        self._rotate(90)

    def rotate_counterclockwise(self) -> None:
        """逆时针旋转 90°。"""
        self._rotate(-90)

    def _rotate(self, degrees: int) -> None:
        if self._item is None:
            return
        self._rotation = (self._rotation + int(degrees)) % 360
        self._after_orient_change()

    def flip_horizontal(self) -> None:
        """水平翻转（左右镜像）。"""
        self._flip(horizontal=True)

    def flip_vertical(self) -> None:
        """垂直翻转（上下镜像）。"""
        self._flip(horizontal=False)

    def _flip(self, horizontal: bool) -> None:
        if self._item is None:
            return
        if horizontal:
            self._flip_h = not self._flip_h
        else:
            self._flip_v = not self._flip_v
        self._after_orient_change()

    def _after_orient_change(self) -> None:
        """翻转/旋转后：没手动缩放过就重新适应窗口，否则保持倍率并居中。"""
        self._apply_item_transform()
        if self._user_zoomed:
            self.centerOn(self.image_rect().center())
        else:
            self.fit()

    # ------------------------------------------------------------------ 交互
    def wheelEvent(self, event) -> None:  # noqa: N802
        """滚轮缩放：以**光标下的那一点**为锚点（自己算，见 set_zoom）。"""
        delta = event.angleDelta().y()
        if not delta or self._item is None:
            return super().wheelEvent(event)
        notches = delta / 120.0
        self.set_zoom(self._zoom * (WHEEL_STEP ** notches), event.position())
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """双击在「100%」与「适应窗口」之间切换。"""
        if self._item is None or event.button() != Qt.MouseButton.LeftButton:
            return super().mouseDoubleClickEvent(event)
        if abs(self._zoom - 1.0) > 1e-6:
            self.set_zoom(1.0)
        else:
            self.fit()
        event.accept()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if not self._user_zoomed:
            self.fit()
        else:
            # 手动缩放过就只刷新留白：视口变大/变小，"可拖到哪儿"跟着变
            self._sync_scene_rect()

    # ------------------------------------------------------------------ 导出
    def export_image(self) -> QImage | None:
        """导出用图：已应用翻转/旋转的**整分辨率**图（缩放的屏幕比例不参与）。"""
        if self._image is None:
            return None
        if not (self._rotation or self._flip_h or self._flip_v):
            return self._image
        return self._image.transformed(
            display_transform(self._rotation, self._flip_h, self._flip_v),
            Qt.TransformationMode.SmoothTransformation,
        )

    # ------------------------------------------------------------------ 内部
    def _apply_item_transform(self) -> None:
        if self._item is None:
            return
        self._item.setTransform(
            display_transform(self._rotation, self._flip_h, self._flip_v)
        )
        self._sync_scene_rect()

    def _sync_scene_rect(self) -> None:
        """场景矩形 = 图片占位，居中**外加可拖留白**，好让不缩放也能拖。

        ⚠️ 留白必须让"内容显示尺寸 > 视口尺寸"，否则 Qt 算出的滚动范围是 0，
        ``ScrollHandDrag`` 拖不动任何东西（用户报的"不缩放就不能拖拽移动"）。
        图片在适应窗口时正好铺满视口，所以居中部分补出来的范围恰好为 0 ——
        必须额外再加 ``PAN_MARGIN_RATIO`` 视口的留白。

        ⚠️ 留白依赖**当前缩放**（场景单位 vs 逻辑像素），所以 `set_zoom` /
        `resizeEvent` / `fit` 之后都要重算；且 ``fit()`` 必须用
        :meth:`image_rect` 而不是本方法设的场景矩形，否则会越 fit 越小。
        """
        if self._item is None:
            self._scene.setSceneRect(QRectF())
            return
        rect = self.image_rect()
        scale = self.transform().m11() or 1.0
        view_w = self.viewport().width() / scale
        view_h = self.viewport().height() / scale
        pad_x = max(0.0, (view_w - rect.width()) / 2.0) + view_w * PAN_MARGIN_RATIO
        pad_y = max(0.0, (view_h - rect.height()) / 2.0) + view_h * PAN_MARGIN_RATIO
        self._scene.setSceneRect(rect.adjusted(-pad_x, -pad_y, pad_x, pad_y))


class ImageZoomDialog(QDialog, WorkerHost):
    """图片预览弹窗：拖拽平移、滚轮/按钮缩放、翻转旋转、下载、翻页。"""

    def __init__(self, parent=None, factory=None, max_edge: int = MAX_RENDER_EDGE):
        """``factory(index) -> ZoomTarget | None``，在**主线程**里现造该页来源。"""
        super().__init__(parent)
        self._init_worker_host()
        self._factory = factory
        self._max_edge = int(max_edge)
        self._index = 0
        self._target: ZoomTarget | None = None
        self._token = None  # 渲染令牌：只认最新一次请求的结果
        self.setWindowTitle("图片预览")
        self.setModal(False)
        self.resize(1120, 800)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(T.SPACE_LG, T.SPACE_MD, T.SPACE_LG, T.SPACE_MD)
        layout.setSpacing(T.SPACE_SM)

        # ⚠️ 先造画布再造工具条：工具条的按钮要连画布的方法
        self.canvas = ZoomableCanvas(self)
        self.canvas.zoom_changed.connect(self._on_zoom_changed)
        layout.addLayout(self._build_toolbar())
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self._build_status())
        self._sync_controls()

    # ------------------------------------------------------------------ 构建
    def _build_toolbar(self) -> QHBoxLayout:
        """工具条：缩放 / 适应 · 朝向 · 翻页 · 下载。"""
        row = QHBoxLayout()
        row.setSpacing(T.SPACE_SM)

        self.zoom_out_btn = ToolButton(FIF.ZOOM_OUT)
        self.zoom_out_btn.setToolTip("缩小（滚轮向下 / − 键）")
        self.zoom_out_btn.clicked.connect(self.canvas.zoom_out)
        self.zoom_label = CaptionLabel("100%")
        self.zoom_label.setToolTip("当前显示比例")
        self.zoom_label.setFixedWidth(52)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_in_btn = ToolButton(FIF.ZOOM_IN)
        self.zoom_in_btn.setToolTip("放大（滚轮向上 / + 键）")
        self.zoom_in_btn.clicked.connect(self.canvas.zoom_in)
        row.addWidget(self.zoom_out_btn)
        row.addWidget(self.zoom_label)
        row.addWidget(self.zoom_in_btn)

        row.addSpacing(T.SPACE_MD)
        self.fit_btn = PushButton(FIF.FIT_PAGE, "适应窗口")
        self.fit_btn.setToolTip("整图完整可见（快捷键 0）")
        self.fit_btn.clicked.connect(self.canvas.fit)
        self.actual_btn = PushButton("100%")
        self.actual_btn.setToolTip("一个图片像素对一个屏幕像素（快捷键 1）")
        self.actual_btn.clicked.connect(self._zoom_actual)
        row.addWidget(self.fit_btn)
        row.addWidget(self.actual_btn)

        row.addSpacing(T.SPACE_MD)
        self.rotate_ccw_btn = PushButton(mirrored_rotate_icon(), "左旋")
        self.rotate_ccw_btn.setToolTip("逆时针旋转 90°")
        self.rotate_ccw_btn.clicked.connect(self.canvas.rotate_counterclockwise)
        self.rotate_cw_btn = PushButton(FIF.ROTATE, "右旋")
        self.rotate_cw_btn.setToolTip("顺时针旋转 90°（快捷键 R）")
        self.rotate_cw_btn.clicked.connect(self.canvas.rotate_clockwise)
        self.flip_h_btn = PushButton(flip_icon(True), "水平翻转")
        self.flip_h_btn.setToolTip("左右镜像（非破坏性，只影响显示与下载）")
        self.flip_h_btn.clicked.connect(self.canvas.flip_horizontal)
        self.flip_v_btn = PushButton(flip_icon(False), "垂直翻转")
        self.flip_v_btn.setToolTip("上下镜像（非破坏性，只影响显示与下载）")
        self.flip_v_btn.clicked.connect(self.canvas.flip_vertical)
        row.addWidget(self.rotate_ccw_btn)
        row.addWidget(self.rotate_cw_btn)
        row.addWidget(self.flip_h_btn)
        row.addWidget(self.flip_v_btn)

        row.addStretch(1)
        self.prev_btn = ToolButton(FIF.LEFT_ARROW)
        self.prev_btn.setToolTip("上一页（← 键）")
        self.prev_btn.clicked.connect(lambda: self._goto(-1))
        self.page_label = CaptionLabel("")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_btn = ToolButton(FIF.RIGHT_ARROW)
        self.next_btn.setToolTip("下一页（→ 键）")
        self.next_btn.clicked.connect(lambda: self._goto(1))
        row.addWidget(self.prev_btn)
        row.addWidget(self.page_label)
        row.addWidget(self.next_btn)

        row.addSpacing(T.SPACE_MD)
        self.download_btn = PrimaryPushButton(FIF.DOWNLOAD, "下载")
        self.download_btn.setToolTip("把整分辨率图片另存为 PNG（无损）或 JPEG")
        self.download_btn.clicked.connect(self._download)
        row.addWidget(self.download_btn)
        return row

    def _build_status(self) -> QWidget:
        """状态条：左边是本页说明（页面/尺寸），右边是临时提示（已保存…）。"""
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(T.SPACE_MD)
        self.note_label = CaptionLabel("")
        apply_to(self.note_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.tip_label = CaptionLabel("")
        apply_to(self.tip_label, T.SIZE_CAPTION, color=T.INK_SOFT)
        self.tip_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self.note_label, 1)
        row.addWidget(self.tip_label)
        return bar

    # ------------------------------------------------------------------ 对外
    def show_for(self, factory=None, index: int = 0) -> None:
        """打开/翻到某一页。``factory(index) -> ZoomTarget | None``（主线程现造）。"""
        if factory is not None:
            self._factory = factory
        if self._factory is None:
            return
        target = self._factory(int(index))
        if target is None:
            self._token = None
            self._target = None
            self.canvas.clear()
            self.note_label.setText("没有可预览的图片")
            self._sync_controls()
            return
        self._target = target
        self._index = int(index)
        self._render()

    # ------------------------------------------------------------------ 渲染
    def _render_edge(self) -> int:
        """本页渲染密度 = 视口**物理**长边 × 余量。

        约束顺序（**先下限、再全局上限、最后宿主的硬上限**）：下限是"控件还没
        布局"时的兜底；``ZoomTarget.cap``（如位图的原生边长）必须最后生效且
        能低于下限——宿主说"这图只有 900px"时，渲到 1600 只是白放大还白占内存。

        语义：100% 是"一个图片像素对一个设备像素"，所以这个密度决定的是
        **100% 时能看到多大一块**（约 1.5 个窗口），而不是"放大到多少倍还不糊"。
        """
        viewport = self.canvas.viewport()
        dpr = self.canvas.devicePixelRatioF() or 1.0
        longest = max(viewport.width(), viewport.height()) * dpr
        edge = max(MIN_RENDER_EDGE, int(round(longest * RENDER_HEADROOM)))
        edge = min(edge, self._max_edge)
        if self._target is not None and self._target.cap:
            edge = min(edge, int(self._target.cap))
        return max(1, edge)

    def _render(self) -> None:
        """起一个后台渲染。``render`` 在 worker 线程里跑，只读快照。"""
        target = self._target
        if target is None:
            return
        edge = self._render_edge()
        self.canvas.clear()
        self.note_label.setText("正在渲染…")
        self.tip_label.setText("")
        self._sync_controls()  # 渲染期间处理图的按钮先禁用（翻页不受影响）
        token = self._token = object()
        self.run_worker(
            lambda: target.render(edge),
            lambda worker, thread: (
                connect_queued(
                    self, worker.finished,
                    lambda _p, image, _s, t=token: self._display(t, image),
                    thread,
                ),
                connect_queued(
                    self, worker.failed,
                    lambda _p, msg, t=token: self._failed(t, msg),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _display(self, token, image) -> None:
        """渲染就绪：装图并刷新状态（迟到的旧结果直接丢弃）。"""
        if token is not self._token:
            return
        self.canvas.set_image(image)
        self._on_zoom_changed(self.canvas.zoom)
        self._sync_controls()
        self.note_label.setText(self._note_text(image))

    def _failed(self, token, msg: str) -> None:
        """渲染失败：只在还是最新一次请求时报错。"""
        if token is not self._token:
            return
        self.canvas.clear()
        self.note_label.setText(f"渲染失败：{msg}")
        self._sync_controls()

    def _note_text(self, image) -> str:
        """状态条说明：页面信息 ｜ 原始尺寸 ｜ 本页渲染尺寸。"""
        parts = [self._target.note if self._target else "预览"]
        original = self._target.original if self._target else None
        if original is not None:
            parts.append(f"原始 {original.width()}×{original.height()}")
        parts.append(f"渲染 {image.width()}×{image.height()}")
        return " ｜ ".join(parts)

    # ------------------------------------------------------------------ 交互
    def _on_zoom_changed(self, zoom: float) -> None:
        self.zoom_label.setText(f"{zoom * 100:.0f}%")

    def _zoom_actual(self) -> None:
        """100%：一个图片像素对一个屏幕像素。"""
        self.canvas.set_zoom(1.0)

    def _goto(self, delta: int) -> None:
        """翻页：夹在两端（不回绕、不越界），越界即无动作。"""
        if self._target is None or self._target.count <= 1:
            return
        index = max(0, min(self._target.count - 1, self._index + int(delta)))
        if index != self._index:
            self.show_for(index=index)

    def _sync_controls(self) -> None:
        """按"能不能翻页 / 有没有图"开关按钮，别留死按钮。

        ⚠️ 翻页按钮**不看** ``has_image``：渲染是异步的（PDF 高密度要几百毫秒），
        若把翻页也绑在"有图"上，连点下一页时中途会突然点不动。翻页只由
        位置决定，处理图的按钮（缩放/翻转/下载）才要求有图。
        """
        target = self._target
        count = target.count if target else 1
        has_image = self.canvas.has_image
        self.prev_btn.setEnabled(count > 1 and self._index > 0)
        self.next_btn.setEnabled(count > 1 and self._index < count - 1)
        self.page_label.setText(
            f"第 {self._index + 1}/{count} 页" if count > 1 else ""
        )
        for button in (
            self.zoom_out_btn, self.zoom_in_btn, self.fit_btn, self.actual_btn,
            self.rotate_ccw_btn, self.rotate_cw_btn, self.flip_h_btn,
            self.flip_v_btn, self.download_btn,
        ):
            button.setEnabled(has_image)

    def _download(self) -> None:
        """把**整分辨率**（已应用翻转/旋转）的图另存到磁盘。"""
        image = self.canvas.export_image()
        if image is None or image.isNull():
            self.tip_label.setText("没有可下载的图片")
            return
        stem = self._target.stem if self._target else "preview"
        suggested = str(Path.home() / f"{stem}.png")
        path, selected = QFileDialog.getSaveFileName(
            self, "保存图片", suggested,
            "PNG 图片（无损） (*.png);;JPEG 图片（有损，画质 90） (*.jpg *.jpeg)",
        )
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(
                ".jpg"
                if "jpg" in selected.lower() or "jpeg" in selected.lower()
                else ".png"
            )
        if save_image(image, target):
            self.tip_label.setText(f"已保存：{target}")
        else:
            self.tip_label.setText(f"保存失败：{target}")

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """快捷键：←/→ 翻页、+/- 缩放、0 适应窗口、1 原始比例、R 旋转。

        Esc 交给 QDialog 自己处理（关窗）。
        """
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_PageUp):
            self._goto(-1)
            return
        if key in (Qt.Key.Key_Right, Qt.Key.Key_PageDown):
            self._goto(1)
            return
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.canvas.zoom_in()
            return
        if key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self.canvas.zoom_out()
            return
        if key == Qt.Key.Key_0:
            self.canvas.fit()
            return
        if key == Qt.Key.Key_1:
            self._zoom_actual()
            return
        if key == Qt.Key.Key_R:
            self.canvas.rotate_clockwise()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        """关窗即作废在飞的渲染并释放大图（一张 4000px 预览约 45MB）。"""
        self._token = None
        self.shutdown_workers()
        self.canvas.clear()
        super().closeEvent(event)


class ZoomPopupMixin:
    """宿主侧混入：双击大图打开图片预览弹窗。

    子类需要实现 :meth:`_zoom_target` 与 :meth:`_zoom_index`，并在
    ``__init__`` 里调 :meth:`_init_zoom_popup`。
    """

    #: 弹窗实例（懒建）。类属性给个 None 兜底：子类可能在 _init_zoom_popup
    #: 之前（如构造中途换数据）就调到 close_zoom_popup。
    _zoom_dialog: "ImageZoomDialog | None" = None

    def _init_zoom_popup(self, view) -> None:
        """把 ``view``（``ImageView``）的双击接到弹窗上。"""
        self._zoom_dialog = None
        view.double_clicked.connect(self._open_zoom_popup)

    def _open_zoom_popup(self) -> None:
        """打开弹窗；没有可预览的页时静默返回。"""
        index = self._zoom_index()
        if self._zoom_target(index) is None:
            return
        if self._zoom_dialog is None:
            self._zoom_dialog = ImageZoomDialog(
                self.window() or self, factory=self._zoom_target
            )
        dialog = self._zoom_dialog
        # 先 show 再 show_for：视口有了真实尺寸，渲染密度才算得准
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.show_for(index=index)

    def close_zoom_popup(self) -> None:
        """内容被换掉时关掉弹窗（弹窗里那页是打开时的快照，留着就是旧数据）。"""
        if self._zoom_dialog is not None:
            self._zoom_dialog.close()

    # ---- 子类实现 ----
    def _zoom_index(self) -> int:
        """当前选中页下标（0 基）。"""
        raise NotImplementedError

    def _zoom_target(self, index: int) -> ZoomTarget | None:
        """第 index 页的数据来源；不可预览时返回 None。"""
        raise NotImplementedError
