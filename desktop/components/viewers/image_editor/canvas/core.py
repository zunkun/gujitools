# -*- coding: utf-8 -*-
"""编辑画布 ``EditorCanvas``：**基座 + 各工具 Mixin 的装配点**。

从 ``image_editor.py`` 拆出（2026-10-07）。本文件只放：类头（信号）、
``__init__``，以及**与工具无关的基座方法**（装图/取图/缩放适配/工具切换）。
各工具（裁剪/变换/扭曲/擦除/文字）在兄弟模块里以 Mixin 提供，
方法体逐字未改；成员归属由 ``tests/selftests/image_editor_split.py`` 钉住。

⚠️ 信号必须定义在**这个 QObject 子类**上（PySide6 的 ``Signal`` 描述符
要求宿主是 QObject）；Mixin 只 emit，不声明。
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QFrame, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView,
)

from desktop.ui import theme as T

from ..consts import (
    DISTORT_HARDNESS, DISTORT_SIZE, DISTORT_SPACING, DISTORT_STRENGTH,
    EDIT_FIT_RATIO, ERASER_DEFAULT, MAX_ZOOM, MIN_RECT_EDGE, MIN_ZOOM,
    SEL_FIT_RATIO,
)
from ..text_item import TextBlockItem
from .interaction import InteractionMixin
from .overlay import OverlayMixin
from .text import TextMixin
from .transform import TransformMixin
from .distortion import DistortionMixin


class EditorCanvas(
    InteractionMixin,
    OverlayMixin,
    TextMixin,
    TransformMixin,
    DistortionMixin,
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
    #: 裁剪框拖完松手（弹窗借此**立即**把图裁成当前选区 = 松手即应用）
    crop_committed = Signal()
    #: 变换拖完松手（弹窗借此**立即**把变换烘焙进像素 = 松手即应用）
    transform_committed = Signal()

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
        self._eraser_pos = QPointF()   # 笔刷圈当前位置（图片坐标）
        self._distort_size = DISTORT_SIZE
        self._distort_hardness = DISTORT_HARDNESS
        self._distort_strength = DISTORT_STRENGTH
        self._distort_spacing = DISTORT_SPACING
        self._distort_mode = "move"
        self._distort_interpolation = "cubic"
        self._distort_high_quality_preview = True
        self._distort_realtime = True
        self._distort_stroke_origin: QImage | None = None
        #: 这一笔的位移场 / 等距落点采样器（拖动时增量累加，松手只渲染包围盒）
        self._distort_field: Any = None
        self._distort_sampler: Any = None
        #: 提交中：挡住重复落笔（否则前台右键/左键能插进后台提交里）
        self._distort_busy = False
        self._distort_preview_image: QImage | None = None
        self._distort_preview_items: dict[tuple[int, int], QGraphicsPixmapItem] = {}
        self._distort_preview_dirty_tiles: set[tuple[int, int]] = set()
        #: 本帧累积出来的待重渲染区域（预览尺度，[left, top, right, bottom]）
        self._distort_preview_dirty_rect: list[float] | None = None
        self._distort_preview_timer: QTimer | None = None
        self._distort_preview_pending_end: QPointF | None = None
        self._distort_preview_scale_x = 1.0
        self._distort_preview_scale_y = 1.0
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
        self._clear_distortion_preview()
        self._xf = QTransform()
        self._xf_touched = False
        self._distort_stroke_origin = None
        self._distort_field = None
        self._distort_sampler = None
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
        if self._tool in ("crop", "transform"):
            # 换图（应用/撤销/还原都走这里）后选区重新默认全选：
            # 裁剪/变换的语义都是"从当前原图出发"，不是沿用旧图上的框
            self._rect = QRectF(self.image_rect())
            self._xf_pivot = self._rect.center()
        self._sync_overlay()


    def _sync_scene_rect(self) -> None:
        """把场景矩形扩到"底图 ∪ 变换浮层"。

        变换把选区送出原边界时浮层会跑到图片外，场景矩形取并集后才看得见；
        没有浮层时退化为图片边界。
        """
        if self._item is None:
            return
        rect = self._item.boundingRect()
        if self._float_item is not None:
            rect = rect.united(self._float_item.sceneBoundingRect())
        self.setSceneRect(rect)


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

    @property
    def tool(self) -> str:
        """当前工具键（``crop``/``transform``/``distort``/``erase``/``text``）。

        弹窗侧只读用（例如 ``stroke_started`` 到达时判断该记成"擦除"还是
        "扭曲"），刻意不给 setter——换工具一律走 :meth:`set_tool`。
        """
        return self._tool


    def image_rect(self) -> QRectF:
        """图片占位（= 场景坐标，1 场景单位 = 1 图片像素）。"""
        if self._image is None:
            return QRectF()
        return QRectF(0, 0, self._image.width(), self._image.height())


    # ------------------------------------------------------------ 工具
    def set_tool(self, tool: str) -> None:
        """切换工具：裁剪/变换默认全选，其余清选区、换光标。"""
        if self._tool == "distort" and self._distort_stroke_origin is not None:
            self._finish_distortion_stroke()
        self._tool = tool
        self._mode = None
        self._clear_transform_preview()
        self._xf = QTransform()
        self._xf_touched = False
        self._xf_reshape = False  # 调整范围是勾选态，换工具即复位
        self._hide_text_outline()
        if tool not in ("erase", "distort"):
            self._hide_eraser_ring()
        if tool in ("crop", "transform") \
                and not self.image_rect().isNull():
            self._rect = QRectF(self.image_rect())
            self._xf_pivot = self._rect.center()
        else:
            self._rect = None
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
        ``ratio``（缺省 0.8，上下左右各留约 10% 视口）。

        ⚠️ ``ratio`` 收到**非数**（``bool``）时按缺省处理：``clicked`` 这类
        信号会顺手塞一个 ``checked`` 布尔进来，而 ``float(False) == 0.0``
        会被夹成下限 ⇒ 图被缩成视口的 1/4（用户 2026-10-08 报障）。
        接线侧已用 lambda 挡掉，这里再兜一层，免得以后又有人直接
        ``button.clicked.connect(canvas.fit)``。
        """
        if self._item is None or self.viewport().width() <= 1:
            return  # 控件还没布局：此时 fit 算出来的是脏值，等 resizeEvent 再来
        rect = self.image_rect()
        if ratio is None or isinstance(ratio, bool) \
                or not isinstance(ratio, (int, float)):
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
