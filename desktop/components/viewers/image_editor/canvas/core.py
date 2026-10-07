# -*- coding: utf-8 -*-
"""编辑画布 ``EditorCanvas``：**基座 + 各工具 Mixin 的装配点**。

从 ``image_editor.py`` 拆出（2026-10-07）。本文件只放：类头（信号）、
``__init__``，以及**与工具无关的基座方法**（装图/取图/缩放适配/工具切换）。
各工具（裁剪/变换/变形/变换笼/校正/擦除/文字）在兄弟模块里以 Mixin 提供，
方法体逐字未改；成员归属由 ``tests/selftests/image_editor_split.py`` 钉住。

⚠️ 信号必须定义在**这个 QObject 子类**上（PySide6 的 ``Signal`` 描述符
要求宿主是 QObject）；Mixin 只 emit，不声明。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QFrame, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView,
)

from desktop.ui import theme as T

from ..consts import (
    EDIT_FIT_RATIO, ERASER_DEFAULT, MAX_ZOOM, MESH_DENSITY_DEFAULT, MIN_RECT_EDGE,
    MIN_ZOOM, RECTIFY_RATIO_DEFAULT, SEL_FIT_RATIO,
)
from ..text_item import TextBlockItem
from .cage import CageMixin
from .deform import DeformMixin
from .interaction import InteractionMixin
from .overlay import OverlayMixin
from .rectify import RectifyMixin
from .text import TextMixin
from .transform import TransformMixin


class EditorCanvas(
    InteractionMixin,
    OverlayMixin,
    TextMixin,
    RectifyMixin,
    CageMixin,
    DeformMixin,
    TransformMixin,
    QGraphicsView,
):
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
        border = getattr(self, "_border", None)
        if border is not None:
            self._scene.removeItem(border)
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
