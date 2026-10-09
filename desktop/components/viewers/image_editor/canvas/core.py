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

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QFrame, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView,
)

from ..consts import (
    CANVAS_OUTSIDE, CHECKER_DARK, CHECKER_LIGHT, CHECKER_STEP, CLIPPING_DEFAULT,
    DIRECTION_DEFAULT, DISTORT_HARDNESS, DISTORT_SIZE, DISTORT_SPACING,
    DISTORT_STRENGTH, EDIT_FIT_RATIO, ERASER_DEFAULT, GUIDE_DEFAULT,
    INTERPOLATION_DEFAULT, MAX_ZOOM, MIN_RECT_EDGE, MIN_ZOOM,
    PREVIEW_OPACITY_DEFAULT, SEL_FIT_RATIO,
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
        #: 用户手动缩放过？没手动缩放过时窗口 resize 会自动"适应窗口"。
        #: ⚠️ ``fit()`` **不许**把它清掉（曾经清过 ⇒ 提交后的 fitInView 把
        #: 闸门打开，之后任何 resize 都自动重 fit，倍率在 0.99/1.11 之间来回
        #: 跳，看着像"图自己忽大忽小"）。
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
        #: 用户摆过的轴心（图片坐标，跨"提交/换图"保留）。
        #: ⚠️ 每次提交都把它重置成新画布中心的话，反复旋转就变成"绕不同点转"，
        #: 内容越扫越远、画布越撑越大（用户报的"越旋转空白越多、图形越小"）。
        #: ``None`` = 还没摆过（用当前选区中心）。只在「重置」/「还原」时清空。
        self._xf_pivot_saved: QPointF | None = None
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
        #: 底图左上角在图片坐标里的位置。⚠️ **不再是 (0, 0)**：底图（"纸"）按
        #: 烘焙画布（``geometry.transform_region``）摆位，整幅旋转时它会被搬到
        #: 负坐标去（内容转到画外，白纸要跟过去）。
        self._xf_base_origin = QPointF(0.0, 0.0)
        #: 底图图元的缩放（``None`` = 原样）。整幅选区时底图是**纯白一片**，
        #: 用 1×1 白图 + 这个缩放代替"每帧新建一张 12 MP 白图"——
        #: 白纸换个大小只是改个矩阵，不用重铺像素。
        self._xf_base_scale: QPointF | None = None
        #: 建预览那一刻的「方向」选项。方向一变底图就失效（它是按当时的矩阵
        #: 画的结果），_sync_float 据此整块重建，免得画面停在旧方向上骗人。
        self._xf_preview_direction = DIRECTION_DEFAULT
        #: 预览降采样：浮层每帧都要重采样一次，大图按 ``DISTORT_PREVIEW_PIXELS``
        #: 预算缩一版（``_xf_preview_region`` = 缩过的选区，``scale`` = 倍率）。
        self._xf_preview_region: QImage | None = None
        self._xf_preview_scale = 1.0
        #: 浮层上一次渲染用的矩阵。矩阵没变就不重算像素（悬停/光标变化不重采样）。
        self._xf_preview_keyframe: QTransform | None = None
        #: 浮层像素左上角在**预览尺度图片坐标**里的位置（= 变换后选区的外框
        #: 左上角）。浮层的图元变换 = 「除以预览倍率 + 挪到这儿」，是一步纯
        #: 仿射——**矩阵只在渲染像素里用一次**（重复套会造成双重变换）。
        self._xf_preview_origin = QPointF(0.0, 0.0)
        #: 正在拖动统一变换。拖动中用轻量插值出预览（快），松手后按用户选的
        #: 插值补一帧高质量预览——「拖动跟手」与「所见即所得」两边都要。
        self._xf_dragging = False
        #: 有"已预览、还没烘焙"的变换（松手挂起，离开工具才烘焙）。
        #: 见 ``TransformMixin.make_transform_pending``。
        self._xf_pending = False
        #: 变换内容的浮层（跟随 _xf 实时变形，烘焙语义与预览一致）
        self._float_item: QGraphicsPixmapItem | None = None
        #: 「统一变换」的选项（与 _distort_* 同款：画布持有、面板读写）
        #: 插值档位：nohalo（默认）/ linear / cubic / nearest——**全部**走
        #: geometry.warp_placement 的逐像素反向重采样（与烘焙同一条数学）。
        self._xf_interpolation = INTERPOLATION_DEFAULT
        #: 剪裁：adjust（画布跟着内容长）/ clip（保持原画布，超出部分裁掉）/ aspect
        self._xf_clipping = CLIPPING_DEFAULT
        #: 方向：forward（正常，内容搬到框的位置）/ backward（校正——预览与
        #: 烘焙都用**反向**矩阵：框摆到歪掉的那块上，掰正它）
        self._xf_direction = DIRECTION_DEFAULT
        #: 参考线（构图辅助线）
        self._xf_guide = GUIDE_DEFAULT
        #: 预览：显示变换后的内容 / 与原图合成 / 浮层不透明度（%）
        self._xf_show_preview = True
        self._xf_compose_preview = True
        self._xf_preview_opacity = PREVIEW_OPACITY_DEFAULT
        #: 「限制 (Shift)」与「从轴心 (Ctrl)」的逐动作开关
        self._xf_constraints: dict[str, bool] = {}
        self._xf_pivot_ops: dict[str, bool] = {}
        #: 轴心：吸附（靠近中心/角点自动贴上去）/ 锁定（拖不动）
        self._xf_snap_pivot = True
        self._xf_lock_pivot = False
        #: **当前节点**（统一变换里"亮着/激活"的那一个）：角方框/边中方框/
        #: 切变菱形/透视小菱形/``pivot``。悬停与按下共用它，"点哪个节点哪个
        #: 节点亮"就是它；``None`` = 谁都不亮。见 ``_set_handle_focus``。
        self._focus_handle: str | None = None
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        # ⚠️ **不要**设 ``setBackgroundBrush``：``QGraphicsScene.drawBackground``
        #    会把视口整个刷成那个颜色，把 ``paintEvent`` 里铺的棋盘格整块盖掉
        #    （实测：设了就只剩纯色，背景格看不见）。空白处由 paintEvent 的
        #    棋盘格负责。
        self.setBackgroundBrush(Qt.BrushStyle.NoBrush)
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
    def set_image(self, image: QImage | None, refit: bool = True) -> None:
        """装入/替换图片。

        ``refit=True``（缺省）：重新适应窗口（打开、裁剪、撤销/还原都走这条）。
        ``refit=False``：**保持当前倍率**——变换提交后画布会长大一点，重新
        fit 就等于"每次松手都把图缩小一档"，反复旋转会越转越小（用户报的
        "越旋转图形越小"）。所以提交走这条，只换像素、不动视图。
        """
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
        self._border.setPen(self._border_pen())
        self._scene.addItem(self._border)
        self._item = item
        self.setSceneRect(item.boundingRect())
        if refit:
            self.fit()
        if self._tool in ("crop", "transform"):
            # 换图（应用/撤销/还原都走这里）后选区重新默认全选：
            # 裁剪/变换的语义都是"从当前原图出发"，不是沿用旧图上的框
            self._rect = QRectF(self.image_rect())
            # ⚠️ 轴心**不重置**：它记在 ``_xf_pivot_saved`` 里（用户自己摆的）。
            #    每次提交都重置成"新画布中心"的话，反复旋转就变成"绕不同点转"，
            #    内容越扫越远、画布越撑越大（用户报的"四周空白越来越多"）。
            self._xf_pivot = (QPointF(self._xf_pivot_saved)
                              if self._xf_pivot_saved is not None
                              else self._rect.center())
        self._sync_overlay()


    def _border_pen(self) -> QPen:
        """纸边框的画笔：**一律细实线**（cosmetic ⇒ 任何倍率下都是 1.5px）。

        它就是这张纸的原始边界：变换时内容搬走了/转歪了，这圈边**不动**，好当
        参照。⚠️ 变换工具下**不再**画成虚线（用户 2026-10-09 第二轮报障
        「同时存在两个框的虚线，颜色不一样」）——虚线只留给跟着内容转的
        ``_quad`` 变换框，这条实线专门负责标"原始位置和大小"。
        """
        pen = QPen(QColor("#5b6472") if self._tool == "transform"
                   else QColor("#8a93a3"))
        pen.setCosmetic(True)
        pen.setWidthF(1.5 if self._tool == "transform" else 1.0)
        return pen

    def _apply_border_pen(self) -> None:
        """按当前工具刷新纸边框的画笔（换工具/装图时调）。"""
        if self._border is not None:
            self._border.setPen(self._border_pen())

    def _sync_scene_rect(self) -> None:
        """场景矩形**恒定**＝原图矩形：变换预览期间绝不再改。

        ⚠️⚠️ 用户 2026-10-09 口径：「画布画面是不变的」。旧版把场景矩形扩成
        「底图 ∪ 变换浮层」——变换把内容送出原边界时矩形一帧帧长大，而视图是
        ``AlignCenter``：场景矩形变 ⇒ 它的中心变 ⇒ **整幅画面跟着平移**
        （实测视图中心 (498,699)→(674,664)→(639,842)，``mapFromScene(0,0)``
        从 (244,91) 漂到 (172,18)）。用户看到的"格子跟图片相互远离、画布一直
        在漂"就是它。

        "要让浮层跑到画外也看得见"这个初衷**不需要**动场景矩形：场景矩形只管
        滚动条范围，**不影响绘制**——只要控件覆盖得到，画到矩形外的图元照样
        画出来（实测：把内容挪到原图矩形右下方 300px 外，控件里像素依然是页面
        色）。所以这里钉死成原图矩形，画面一动不动。
        """
        if self._item is None:
            return
        rect = QRectF(self.image_rect())
        if self.sceneRect() != rect:
            self.setSceneRect(rect)


    def refresh(self) -> None:
        """像素被就地改过（擦除）后只刷显示，不动缩放与滚动位置。"""
        if self._item is not None and self._image is not None:
            self._item.setPixmap(QPixmap.fromImage(self._image))

    def paintEvent(self, event) -> None:  # noqa: N802
        """铺**「图外素灰 + 图内条纹格」**，再让场景画上去。

        ⚠️ 用户 2026-10-09 口径：「背景是灰色的，**原本图片大小位置固定是条纹
        格子**，图片旋转不再有白色的区域」。所以条纹格只画在 :meth:`image_rect`
        （= 这张图的原始地盘）**里面**，且**不随变换走**——图被挪走/转歪之后，
        原位露出来的就是"格子的老地方"，一眼看出那块已经空了；图外一圈是
        浅底（``CANVAS_OUTSIDE``，用户同日追加「灰色太突兀」后调浅了）。

        旧版把格子铺满整个视口、中间再拿一张**白纸**盖住：纸按旋转外框重铺，
        于是"白底一直在涨、看着像在漂"（用户报障）。现在没有纸，也就没有白底。

        格子**相位锚在图片原点**（不是视口原点），滚动/缩放时格子跟着图走，
        不会在图上"滑来滑去"。
        """
        painter = QPainter(self.viewport())
        area = event.rect()
        painter.fillRect(area, CANVAS_OUTSIDE)   # 图外那圈浅底（见 consts.CANVAS_OUTSIDE）
        # ⚠️ 循环必须夹在**可见区域**里：格子按"图片矩形"铺，但放大到 8× 时
        #    那个矩形在视口坐标里能有几万像素宽，照它迭代＝每次重绘几十万次
        #    drawRect（实测会卡死）。夹完只剩视口那几十格。
        board = self.mapFromScene(self.image_rect()).boundingRect()
        vis = board.intersected(area)
        if self._image is not None and not vis.isEmpty():
            origin = self.mapFromScene(QPointF(0.0, 0.0))
            step = CHECKER_STEP
            painter.save()
            painter.setClipRect(vis)
            painter.fillRect(vis, CHECKER_LIGHT)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(CHECKER_DARK)
            # 起点按"图片原点往左上取整到格线"，这样第 (0,0) 格永远贴着图角。
            row = int((vis.top() - origin.y()) // step)
            y = origin.y() + row * step
            while y <= vis.bottom():
                col = int((vis.left() - origin.x()) // step)
                x = origin.x() + col * step
                while x <= vis.right():
                    if (row + col) % 2:
                        painter.drawRect(QRect(int(x), int(y), step, step))
                    x += step
                    col += 1
                y += step
                row += 1
            painter.restore()
        painter.end()
        super().paintEvent(event)


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
        self._focus_handle = None  # 换工具后没有"当前节点"（高亮环一并收起）
        self._hide_text_outline()
        if tool not in ("erase", "distort"):
            self._hide_eraser_ring()
        if tool in ("crop", "transform") \
                and not self.image_rect().isNull():
            self._rect = QRectF(self.image_rect())
            # 轴心：用户摆过就沿用（换工具不该把它甩回中心）
            self._xf_pivot = (QPointF(self._xf_pivot_saved)
                              if self._xf_pivot_saved is not None
                              else self._rect.center())
        else:
            self._rect = None
        self._apply_border_pen()      # 变换工具下纸边框画成虚线（原图轮廓）
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
