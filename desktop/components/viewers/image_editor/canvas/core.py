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

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QFrame, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView,
)

from ..consts import (
    CANVAS_OUTSIDE, CLIPPING_DEFAULT,
    DIRECTION_DEFAULT, DISTORT_HARDNESS, DISTORT_SIZE, DISTORT_SPACING,
    DISTORT_STRENGTH, EDIT_FIT_RATIO, ERASER_DEFAULT, GUIDE_DEFAULT,
    INTERPOLATION_DEFAULT, MAX_ZOOM, MIN_RECT_EDGE, MIN_ZOOM,
    PREVIEW_OPACITY_DEFAULT, SEL_FIT_RATIO,
)
from ..geometry import _transparent_content_bounds
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
    裁剪不做"拖拽画框"：**默认全选**，拖边收边、拖框内平移图片和选区。

    ⚠️ 裁剪是**非破坏性**的：这里画的始终是**原图**，收边只是让选区外多一层
    变暗的遮罩（``overlay._sync_overlay`` 每帧按选区重算，所以向外拖时那块
    区域立刻重新露出来）。真正的 ``QImage.copy`` 由弹窗在**切走裁剪工具 /
    点「完成」**时才做（``dialog_commit._commit_crop``）——于是裁剪线在整段
    编辑过程中都能来回推拉，而不会被上一次的"落定"顶死在边界上。
    """

    #: 擦除一笔开始（弹窗借此压撤销点）
    stroke_started = Signal()
    #: 在文字工具下单击了某个落点（图片坐标，已夹进画布）
    text_requested = Signal(QPointF)
    #: 「调整范围」收边完成（弹窗借此取消勾选，自动回到变换模式）
    reshape_finished = Signal()
    #: 裁剪框拖完松手（弹窗据此**记下**选区；像素不动，裁剪仍是"待定"）
    crop_selection_changed = Signal()
    #: 变换拖完松手（弹窗借此**立即**把变换烘焙进像素 = 松手即应用）
    transform_committed = Signal()
    #: 进入变换工具（弹窗据此从 sidecar 恢复"内容四角节点"，2026-10-10）
    content_restore_requested = Signal()
    #: 恢复会话第一次真正需要像素（第一次建预览/拖动）：upright 反变换是
    #: 秒级重活，弹窗在此刻才算它（带进度框），算完调
    #: :meth:`provide_restore_pixels` 补回来（2026-10-10「切换卡顿」）。
    restore_pixels_requested = Signal()
    context_image_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item: QGraphicsPixmapItem | None = None
        self._context_item: QGraphicsPixmapItem | None = None
        self._context_border: QGraphicsRectItem | None = None
        self._context_image: QImage | None = None
        #: 非活动图的**实际显示外接矩形**（场景坐标，含旋转）——场景矩形
        #: 的并集按它算（见 set_context_image）
        self._context_display_rect: QRectF | None = None
        #: 非活动图片的 **QPixmap 缓存**（2026-10-13「切换不丝滑」）：
        #: ``QPixmap.fromImage`` 对大图是一次全图转换（12 MP 几十毫秒），
        #: 而换图层/裁剪/撤销都会重摆 context 图元。按 **QImage 包装对象的
        #: 身份**缓存并持有引用（防止 id 复用假命中）：换图层时弹窗侧会
        #: 存进新的 QImage 包装（捕获即新包装），身份变了缓存自然失效，
        #: 不会拿旧像素骗人。
        self._context_pixmap_cache: dict[int, tuple[QImage, QPixmap]] = {}
        #: 非活动图的**非透明内容框**缓存（同 :meth:`_content_bounds_of`）：
        #: 按 ``cacheKey`` 存 ``(QImage, bounds|None)``，换层/换图重建图元时
        #: 不必每次重扫整图 alpha。
        self._context_bounds_cache: dict[int, tuple[QImage, Any]] = {}
        self._content_bounds_cache_image: QImage | None = None
        self._content_bounds_cache_key: int | None = None
        self._content_bounds_cache: tuple[int, int, int, int] | None = None
        self._context_offset = QPointF()
        self._context_scale_x = 1.0
        self._context_scale_y = 1.0
        self._context_rotation = 0.0
        self._image: QImage | None = None
        self._crop_offset = QPointF()
        #: 原文件在场景坐标里占的矩形（裁剪/平移的固定上界，
        #: 见 :meth:`set_source_extent`）；``None``＝退回当前图大小。
        self._source_extent: QRectF | None = None
        self._zoom = 1.0
        self._tool = "crop"
        #: 用户是否手动缩放过。没动过就随窗口 resize 自动"适应窗口"——
        #: ⚠️ 没有它，弹窗刚打开（布局未定）时 fit 算出的脏尺寸会把大图
        #: 缩成指甲盖大小且再也不修正（用户截图报过）。
        #: 用户手动缩放过？没手动缩放过时窗口 resize 会自动"适应窗口"。
        #: ⚠️ ``fit()`` **不许**把它清掉（曾经清过 ⇒ 提交后的 fitInView 把
        #: 闸门打开，之后任何 resize 都自动重 fit，倍率在 0.99/1.11 之间来回
        #: 跳，看着像"图自己忽大忽小"）。
        #: ⚠️⚠️**只有"用户自己缩放过"才能置位**（``set_zoom``/``fit_selection``）。
        #:    变换链曾拿它当"变换期间的临时抑制"：``_apply_visual`` 里置位、
        #:    压制 sceneRect 变化引发的 resize 自动 fit——但**从不还原**，
        #:    于是"做过一次变换"就永久关掉了 resize 适配与 ``set_fit_ratio``
        #:    的即时生效（2026-10-14 用户报障「旋转 45° 后切裁剪，图片右侧
        #:    和底部被切掉」：图已从 400×300 烘焙成 494×494，倍率仍是旧的
        #:    1.92，494×494 只剩 451×354 落在视口内）。临时抑制改用
        #:    ``_xf_fit_suppressed``，用完即清。
        self._user_zoomed = False
        #: 「变换操作进行中」＝临时抑制 resize 自动适配（**不是**用户缩放）。
        #: 只在一次变换落账期间为真，由 :meth:`_finish_transform_auto_fit`
        #: 收尾时清掉；语义与 ``_user_zoomed`` 严格分开——后者是长期意图。
        self._xf_fit_suppressed = False
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
        self._xf_auto_fit_canvas = False
        self._xf_auto_fit_pending = False
        #: 从轴心缩放/切变（旋转永远绕轴心）
        self._xf_about_pivot = False
        #: 「调整范围」模式：拖手柄收小变换区域而不是缩放内容
        #: （小范围修褶皱的入口：先框住褶皱，再旋转/切变把它正回来）
        self._xf_reshape = False
        #: 预览三件套：锁定的选区 / 选区像素快照 / 填白后的底图
        self._xf_rect: QRectF | None = None
        self._xf_region: QImage | None = None
        #: 内容节点恢复会话（2026-10-10）：浮层像素源＝sidecar 反变换出的
        #: **upright 内容**。⚠️ 画布（``_image``）保持文件原样一个像素不换
        #: （用户口径「PB1 作为画布，PA1 作为可操作区域」），只有浮层与
        #: 矩阵来自恢复数据。``None`` = 普通会话（浮层取自画布选区）。
        self._xf_restore_region: QImage | None = None
        #: 恢复会话**延迟供像素**（2026-10-10「切换卡顿」）：True = 框/手柄已按
        #: 种子矩阵挂好，但 upright 反变换还没算（进入工具零等待）；第一次
        #: 建预览（:meth:`TransformMixin._ensure_transform_preview`）时发
        #: ``restore_pixels_requested``，弹窗算完经 :meth:`provide_restore_pixels`
        #: 补回，或 :meth:`abort_content_restore` 放弃。
        self._xf_restore_pending = False
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
        #    会把视口整个刷成那个颜色，把 ``paintEvent`` 里铺的素色底整块盖掉
        #    （实测：设了就只剩纯色，背景底色看不见）。空白处由 paintEvent 的
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
        self._crop_offset = QPointF()
        # ⚠️ 换图 ⇒ 原文件基准重置为**这张新图自己**（裁剪/撤销/应用都走
        #    这里）。不清的话上一张图登记的上界会一直留着，裁剪框就能拖到
        #    新图外面去——正是"不应该超过图片外"要防的。
        self._source_extent = None
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
        pixmap = self._cached_pixmap(self._image)
        item = QGraphicsPixmapItem(pixmap)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._scene.addItem(item)
        # 纸边细框（cosmetic：任何倍率下都是 1 设备像素），白纸与背景才分得开
        self._border = QGraphicsRectItem(item.boundingRect())
        self._border.setPen(self._border_pen())
        # 层序：边框压在自己图上、又必须在变换浮层（z=5）之下
        self._border.setZValue(1)
        self._scene.addItem(self._border)
        self._item = item
        self._item.setZValue(0)
        self._show_context_image()
        self._sync_scene_rect()
        if refit:
            self.fit()
        self._sync_item_render_mode()
        if self._tool in ("crop", "transform"):
            # 换图（应用/撤销/还原都走这里）后选区重新默认全选：
            # 透明扩展画布只包含定位留白，默认框仍应贴合实际图片内容。
            self._rect = QRectF(self.image_rect())
            bounds = self._content_rect()
            if bounds is not None:
                self._rect = bounds.translated(self.image_rect().topLeft())
            # ⚠️ 轴心**不重置**：它记在 ``_xf_pivot_saved`` 里（用户自己摆的）。
            #    每次提交都重置成"新画布中心"的话，反复旋转就变成"绕不同点转"，
            #    内容越扫越远、画布越撑越大（用户报的"四周空白越来越多"）。
            self._xf_pivot = (QPointF(self._xf_pivot_saved)
                              if self._xf_pivot_saved is not None
                              else self._rect.center())
        self._sync_border()
        self._sync_overlay()


    def set_context_image(
        self,
        image: QImage | None,
        offset: QPointF = QPointF(),
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        rotation: float = 0.0,
    ) -> None:
        """在活动图旁显示可点击切换、但不直接编辑的另一张图。

        场景矩形的并集按 :attr:`_context_display_rect` 算。它取图元的实际场景
        外接矩形，因此包含版面旋转后的扩展范围；否则旋转图像的角会落在场景
        矩形之外，被视口裁掉。
        """
        self._context_image = (
            image if image is not None and not image.isNull() else None
        )
        self._context_offset = QPointF(offset)
        self._context_scale_x = max(0.01, float(scale_x))
        self._context_scale_y = max(0.01, float(scale_y))
        self._context_rotation = float(rotation)
        self._context_display_rect = None
        self._show_context_image()
        # ⚠️ ``keep_view=True``：换层**必须**同步滚动范围（两张图的并集变了，
        # 不同步就滚不到另一张，2026-10-13 报障），走保画面的老路径。
        self._sync_scene_rect(keep_view=True)
        self.update()

    def _context_pixmap(self) -> QPixmap | None:
        """非活动图片的 QPixmap（与活动层共用小型缓存）。"""
        if self._context_image is None:
            return None
        return self._cached_pixmap(self._context_image)

    def _cached_pixmap(self, image: QImage) -> QPixmap:
        """同一张图在活动/非活动层间切换时复用 QPixmap，避免重复全图转换。"""
        key = int(image.cacheKey())
        entry = self._context_pixmap_cache.get(key)
        if entry is not None:
            return entry[1]
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(1.0)
        self._context_pixmap_cache[key] = (image, pixmap)
        while len(self._context_pixmap_cache) > 4:
            self._context_pixmap_cache.pop(next(iter(self._context_pixmap_cache)))
        return pixmap

    def _refresh_cached_pixmap(self, image: QImage) -> QPixmap:
        """像素被就地改写后刷新这张图对应的显示缓存。"""
        for key, entry in list(self._context_pixmap_cache.items()):
            if entry[0] is image:
                del self._context_pixmap_cache[key]
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(1.0)
        self._context_pixmap_cache[int(image.cacheKey())] = (image, pixmap)
        return pixmap

    def _content_rect(self) -> QRectF | None:
        """Return nontransparent image bounds, cached until its QImage changes."""
        image = self._image
        if image is None:
            return None
        key = int(image.cacheKey())
        if (self._content_bounds_cache_image is not image
                or self._content_bounds_cache_key != key):
            self._content_bounds_cache_image = image
            self._content_bounds_cache_key = key
            self._content_bounds_cache = _transparent_content_bounds(image)
        bounds = self._content_bounds_cache
        return QRectF(*bounds) if bounds is not None else None

    def _show_context_image(self) -> None:
        self._context_display_rect = None
        if self._context_item is not None:
            self._scene.removeItem(self._context_item)
            self._context_item = None
        if self._context_border is not None:
            self._scene.removeItem(self._context_border)
            self._context_border = None
        if self._context_image is None or self._item is None:
            return
        pixmap = self._context_pixmap()
        if pixmap is None:
            return
        item = QGraphicsPixmapItem(pixmap)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        item.setPos(self._context_offset)
        item.setTransform(QTransform.fromScale(
            self._context_scale_x, self._context_scale_y,
        ))
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setRotation(self._context_rotation)
        # ⚠️⚠️ **外框取"非透明内容"，不是整张 pixmap**（2026-10-14 用户报障
        #    「裁剪框把 Left 移走后切到 Right，Left 虚线框被放大」）：
        #    ``_commit_crop`` 的"移动"分支会用透明边距把像素挪进一张**更大**
        #    的图里（内容不动、四周留白），整张 pixmap 的外框于是比看得见的
        #    内容大一圈——留白朝上/右时，虚线框正好撑到另一张图那边去，看着
        #    就是"框串到隔壁图上"。
        #    活动图早就是内容口径（裁剪下 ``_sync_border`` 走 ``_content_rect``，
        #    无预览时 ``_display_bounds`` 同款），这里补齐 ⇒ 两侧口径一致，
        #    ``_content_scene_rect`` 的并集也不再白撑一圈透明留白。
        self._context_display_rect = self._map_content_bounds(item)
        # ⚠️ 层序（2026-10-13「重叠时操作谁谁在上层」）：非活动图 -1、
        #    活动图 0、活动图边框 1、变换浮层 5——**活动图永远盖住非活动
        #    图**，点击非活动图露出的部分即切换，切完它就到上层。
        item.setZValue(-1)
        self._scene.addItem(item)
        self._context_item = item
        # 非活动图也有自己的虚线边框（跟随它的显示外框，含旋转/ghost 外扩）
        border = QGraphicsRectItem(self._context_display_rect)
        border.setPen(self._border_pen())
        border.setZValue(-1)
        self._scene.addItem(border)
        self._context_border = border

    def _map_content_bounds(self, item: QGraphicsPixmapItem) -> QRectF:
        """图元**非透明内容**的外框（场景坐标）。

        用 ``item.mapToScene`` 逐角映射（``QGraphicsItem`` 只有
        ``mapToScene``/``mapRect``→polygon，没有 ``mapRect``）把图片坐标里的
        内容框摆到场景坐标——所以带版面旋转的图也能算对（旋转后不再是矩形，
        取四个角的外接矩形，与 :meth:`sceneBoundingRect` 同一口径）。
        整幅不透明（普通扫描件）或缺 numpy 时退回图元外接矩形＝旧行为。
        """
        whole = item.sceneBoundingRect()
        image = self._context_image
        if image is None or image.isNull():
            return whole
        bounds = self._content_bounds_of(image)
        if bounds is None:
            return whole
        rect = QRectF(*bounds)
        corners = (rect.topLeft(), rect.topRight(),
                   rect.bottomRight(), rect.bottomLeft())
        mapped = [item.mapToScene(point) for point in corners]
        xs = [point.x() for point in mapped]
        ys = [point.y() for point in mapped]
        return QRectF(min(xs), min(ys),
                      max(xs) - min(xs), max(ys) - min(ys))

    def _content_bounds_of(self, image: QImage):
        """非透明内容框，按 ``cacheKey`` 缓存（扫描一次整图 alpha）。

        换层/换图都会重建非活动图元，12 MP 上每次重扫约 10 ms；缓存后
        同一张图只扫一次。判据用 ``cacheKey``（像素被改写即失效）。
        """
        key = int(image.cacheKey())
        entry = self._context_bounds_cache.get(key)
        if entry is not None and entry[0] is image:
            return entry[1]
        bounds = _transparent_content_bounds(image)
        self._context_bounds_cache[key] = (image, bounds)
        while len(self._context_bounds_cache) > 4:
            self._context_bounds_cache.pop(next(iter(self._context_bounds_cache)))
        return bounds

    def context_image_at(self, scene_pos: QPointF) -> bool:
        """返回场景坐标是否命中非活动图片。"""
        if self._context_item is None:
            return False
        return self._context_item.boundingRect().contains(
            self._context_item.mapFromScene(scene_pos)
        )

    def _border_pen(self) -> QPen:
        """图片边框画笔：**虚线**（cosmetic ⇒ 任何倍率下都是 1px 虚线）。

        ⚠️ 2026-10-13 用户口径：边框改**虚线**，且"并不是固定不变的，应该
        根据图片四至边界扩大和缩小"——矩形由 :meth:`_sync_border` 维护：
        活动图跟随当前显示范围（含挂起变换的外扩），非活动图跟随自己的
        显示外框。
        """
        pen = QPen(QColor("#5b6472") if self._tool == "transform"
                   else QColor("#8a93a3"))
        pen.setCosmetic(True)
        pen.setWidthF(1.0)
        pen.setStyle(Qt.PenStyle.DashLine)
        return pen

    def _apply_border_pen(self) -> None:
        """按当前工具刷新纸边框的画笔（换工具/装图时调）。"""
        if self._border is not None:
            self._border.setPen(self._border_pen())

    def _display_bounds(self) -> QRectF:
        """活动图**当前内容**的紧凑外框（图片坐标）——虚线边框的依据。

        用户 2026-10-13 口径：框要**包裹单张图片本身**——单图旋转 45°，
        框就是旋转后内容的外接框（√2 比例），**位置跟着内容移动**，不是
        钉死在原矩形上。所以：有挂起变换预览时＝变换后内容的紧凑外框
        （整幅内容选区时底图是一片空白，**不算**进外框；局部选区时选区外的
        原图残余还在画面上，要并进来）；没有预览时＝非透明内容的实际外框，
        不把裁剪位移产生的透明留白算进图片边界。
        """
        float_item = getattr(self, "_float_item", None)
        if float_item is None or float_item.pixmap().isNull():
            image_rect = self.image_rect()
            bounds = self._content_rect()
            if bounds is not None:
                return bounds.translated(image_rect.topLeft())
            return QRectF(image_rect)
        if self._xf_preview_keyframe is not None:
            float_xf = self._float_placement()
        else:
            float_xf = self._float_fast_xf()
        pixmap = float_item.pixmap()
        bounds = float_xf.mapRect(
            QRectF(0, 0, pixmap.width(), pixmap.height()))
        if not self._backdrop_is_whole() and self._paint_image is not None:
            bounds = bounds.united(self._base_current_rect())
        return bounds

    def _sync_border(self) -> None:
        """边框矩形跟随活动图当前显示范围（见 :meth:`_display_bounds`）。"""
        if self._border is None or self._image is None:
            return
        if self._tool == "crop" and self._item is not None:
            # 裁剪移动/变换扩画布可能在像素图周围留下透明边距；虚线框仍应
            # 包住可见图片，而不是整个透明画布。边框与图元共享本地坐标变换。
            bounds = self._content_rect()
            if bounds is None:
                bounds = self._item.boundingRect()
            self._border.setRect(bounds)
            self._border.setPos(self._item.pos())
            self._border.setTransform(self._item.transform())
            return
        self._border.setRect(self._display_bounds())
        # _display_bounds() 已是场景坐标；清除裁剪模式跟随图片图元的本地
        # 坐标变换，避免工具切换时把旧偏移再次叠加到边框上。
        self._border.setPos(0.0, 0.0)
        self._border.setTransform(QTransform())

    def _sync_scene_rect(self, keep_view: bool = False) -> None:
        """场景矩形＝两图**当前显示范围**的并集（滚动条够得到全部内容）。

        2026-10-13 用户报障「右侧图向右移一段后切到左侧，右侧显示不全」：
        矩形只圈基准矩形时，被变换搬出去的 content 落在矩形外 ⇒ 滚动条
        够不着，永远看不全。现在并集里放的是**显示范围**：

        - 活动图：:meth:`_display_bounds`（无预览＝图片矩形；有挂起预览＝
          变换后内容的紧凑外框）；
        - 非活动图：:attr:`_context_display_rect`（图元的实际场景外接矩形，
          含版面旋转）。

        ⚠️ 两侧口径一致 ⇒ 换层前后并集是**同一块版面**，画面不跳（2026-10-13
        的切换跳动修复保持不变）。
        ⚠️ **拖动中冻结**（2026-10-09 的旧病：矩形一帧帧跟着浮层长大，画面
        跟着漂）：松手后 ``finish_transform_drag`` 会再刷一次，那时才扩。
        ⚠️ 换矩形时用 :meth:`_set_scene_rect_keeping_view` **保持画面不动**。

        参数 ``keep_view``：**换层等"必须同步滚动范围"的场景**传 True
        （走原来的保画面路径，2026-10-13 的"切层不跳"依赖它）；默认 False 时，
        「是否自动缩放画布」关闭就**整个不调** ``setSceneRect``——
        2026-10-14 用户口径「彻底关闭后，松鼠标也不要自动缩放**和平移**」。
        ⚠️ 为何不能"换个方式调再摆回去"：本视图设了 ``setAlignment``
        （AlignCenter），``setSceneRect`` **调用本身**就重排视口（实测额外
        平移 27px），而视口小于场景时 ``centerOn`` 被对齐钳制、居中对齐下
        滚动条又不代表真实位置 ⇒ 临时改 alignment／事后 centerOn／还原
        滚动条／按位移补偿四版补救**全部无效**（恒 27px）。不调才是可靠的。
        """
        if self._item is None:
            return
        if getattr(self, "_xf_dragging", False):
            return
        if not keep_view and not self._xf_auto_fit_canvas:
            return
        rect = self._content_scene_rect()
        if (self._context_item is not None
                and self._xf_auto_fit_pending
                and not self._xf_auto_fit_canvas):
            # 变换让内容扩出场景时保留旧视口可见范围，确保 QGraphicsView
            # 有足够滚动余量维持同一视口中心，而不是被滚动范围夹回内容中心。
            rect = rect.united(
                self.mapToScene(self.viewport().rect()).boundingRect())
        self._set_scene_rect_keeping_view(rect)

    def _content_scene_rect(self) -> QRectF:
        """当前图片内容范围，不含为保持视口位置而保留的空白场景范围。"""
        if self._context_item is None:
            # ⚠️ **单图模式维持旧口径**：矩形钉住原图矩形（2026-10-09「转多
            #    少圈画面都不动」——单图时场景常小于视口，AlignCenter 会跟着
            #    矩形中心走，矩形一扩画面就漂）。浮层跑出矩形的部分照常画得
            #    出来，只是滚不到——这是单图模式的既有取舍。
            return QRectF(self.image_rect())
        # 双图：并集圈住**两图当前显示范围**（内容再远也滚得到）
        rect = QRectF(self._display_bounds())
        context = (QRectF(self._context_display_rect)
                   if self._context_display_rect is not None
                   else self._context_item.sceneBoundingRect())
        return rect.united(context)

    def _set_scene_rect_keeping_view(self, rect: QRectF) -> None:
        """换场景矩形但**画面不动**（把原视口中心的场景点重新摆回中心）。

        ``setSceneRect`` 只改滚动范围；滚动值锚在矩形原点上，矩形原点一变，
        同样的滚动值就对应到别的场景位置（画面整体漂移——2026-10-09 报障的
        "格子跟图片相互远离"就是这个）。所以改完立刻把同一个场景点居中回来。
        """
        if self.sceneRect() == rect:
            return
        center = self.mapToScene(self.viewport().rect().center())
        self.setSceneRect(rect)
        self.centerOn(center)


    def refresh(self) -> None:
        """像素被就地改过（擦除）后只刷显示，不动缩放与滚动位置。"""
        if self._item is not None and self._image is not None:
            self._item.setPixmap(self._refresh_cached_pixmap(self._image))

    def paintEvent(self, event) -> None:  # noqa: N802
        """整个视口铺**一层素色浅底**，再让场景画上去。

        ⚠️ 2026-10-13 用户口径：「去除底层方块格子」。旧版（2026-10-09）
        图内铺棋盘格当透明指示、双图模式扩到两图并集当"稳定的底层画布"，
        用户最终不要格子了——现在只剩一个纯色底（``CANVAS_OUTSIDE``），
        透明区域露的就是它；图片边界仍有纸边细框（``_border``，cosmetic
        细线），"哪块是图的地盘"照样分得清，图外与图内同色、不再有格子。
        """
        painter = QPainter(self.viewport())
        painter.fillRect(event.rect(), CANVAS_OUTSIDE)
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
        """图片占位（场景坐标；裁剪拖动预览会临时平移）。"""
        if self._image is None:
            return QRectF()
        return QRectF(
            self._crop_offset.x(), self._crop_offset.y(),
            self._image.width(), self._image.height(),
        )

    def _sync_item_render_mode(self) -> None:
        """按当前倍率切换图元采样方式：≥100% 用**最近邻**，<100% 用平滑。

        ⚠️ 100% 以下是大图缩小，平滑采样才不出锯齿/摩尔纹；100% 以上已经没有
        更多像素可看，继续平滑只会把像素糊成一团（用户 2026-10-25：「编辑里
        放大后发虚」）。像素级放大按像素格显示，是编辑器的通行做法。
        """
        if self._item is None:
            return
        mode = (
            Qt.TransformationMode.FastTransformation
            if self._zoom >= 1.0
            else Qt.TransformationMode.SmoothTransformation
        )
        if self._item.transformationMode() != mode:
            self._item.setTransformationMode(mode)

    def set_source_extent(self, rect: QRectF) -> None:
        """登记**原始文件**在场景坐标里占的矩形，作为裁剪/平移的固定上界。

        ⚠️⚠️ 裁剪框的上界**不能**取 :meth:`image_rect`（用户 2026-10-15
        报障「图片裁剪框不应该超过图片外」「斜对角扩张能扩张无限大」）。
        ``image_rect`` 跟着 ``_crop_offset`` 走，而"框内平移 + 落定"会把
        偏移量加进新图尺寸 ⇒ 每循环一次图就大一圈（实测 200×120 →
        400×240 → 600×360 线性发散），角手柄再往外拖就把这条发散边界当成
        合法上界——"扩张无限大"正是这么来的。

        这里把**原文件当初占的那块矩形**记成固定值（与平移无关）。入口
        ``_trim_transparent_edges`` 收紧过透明边时，收紧后的图被摆在
        ``(0,0)``，原文件却占 ``(-dx, -dy, 源宽, 源高)`` ⇒ 矩形**带负
        原点**，用户正好能把裁剪框拖回原始大小（同一报障的后半句）。
        """
        self._source_extent = QRectF(rect).normalized()

    def source_extent_rect(self) -> QRectF:
        """裁剪框允许达到的最大矩形（**场景坐标**）。

        = 图片当前左上角 + :attr:`_source_extent`（后者记的是**原文件相对
        收紧后图片**的矩形：入口 ``_trim_transparent_edges`` 裁掉 ``(dx,dy)``
        透明边时就是 ``(-dx,-dy, 源宽, 源高)``，没裁过就是 ``(0,0,w,h)``）。

        ⚠️ 为什么要"位置跟图片走"：框内平移（``crop_move``）会把图片拖到
        场景别处，若边界锚在原点，平移后框立刻被夹死／夹空，等于把平移功能
        废掉（2026-10-15 用户报障「图片移动被你改没了」）。所以只锁**尺寸**
        （原文件宽高，跨轮不累积），位置跟随图片当前左上角。

        于是三条同时成立：①框的宽高**恒不超过原文件**；②入口收紧过透明边
        时原文件比当前图大 ⇒ 能把框拖回**原始大小**；③框内平移照常可用。
        """
        if self._image is None:
            return QRectF()
        extent = self._source_extent or QRectF(
            0.0, 0.0, float(self._image.width()), float(self._image.height()))
        return QRectF(self._crop_offset.x() + extent.left(),
                      self._crop_offset.y() + extent.top(),
                      extent.width(), extent.height())

    def crop_offset(self) -> QPointF:
        """裁剪工具中图片相对原点的待定位移。"""
        return QPointF(self._crop_offset)


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
            image_rect = self.image_rect()
            bounds = self._content_rect()
            self._rect = (bounds.translated(image_rect.topLeft())
                          if bounds is not None else QRectF(image_rect))
            # 轴心：用户摆过就沿用（换工具不该把它甩回中心）
            self._xf_pivot = (QPointF(self._xf_pivot_saved)
                              if self._xf_pivot_saved is not None
                              else self._rect.center())
        else:
            self._rect = None
        self._apply_border_pen()      # 变换工具下纸边框画成虚线（原图轮廓）
        self._sync_border()
        self._sync_overlay()
        self._sync_cursor()
        # ⚠️ 内容节点恢复（2026-10-10）：进入变换工具且 sidecar 还没恢复过
        #    时通知弹窗——由它读 ``(rect0, V)``、把像素反变换回 upright 后
        #    调 :meth:`begin_restored_transform`（框/手柄落在内容四边形上）。
        #    恢复过/无 sidecar 时弹窗会 consume，这里不再重复发。
        if tool == "transform" and not self.image_rect().isNull() \
                and not getattr(self, "_content_restore_done", False):
            self.content_restore_requested.emit()

    def provide_restore_pixels(self, upright: QImage) -> None:
        """弹窗把延迟计算的 upright 内容补回来（:meth:`abort_content_restore`
        的反面）。调用方是 :meth:`TransformMixin._ensure_transform_preview`
        发出 ``restore_pixels_requested`` 后被同步回调的弹窗槽——像素一到，
        预览就能照常搭起来。"""
        if upright is None or upright.isNull():
            return
        self._xf_restore_region = QImage(upright)
        self._xf_restore_pending = False

    def abort_content_restore(self) -> None:
        """放弃恢复会话（sidecar 缺失/损坏/反变换失败）：退回普通会话。

        延迟供像素模式下框已经按 rect0 挂出来了，这里要把那套"挂起"状态
        整体撤掉——框弹回整幅、矩阵归零，与"从来没有 sidecar"一致
        （口径：宁可不恢复，也不能错恢复）。"""
        self._xf_restore_pending = False
        self._xf_restore_region = None
        self._xf_rect = None
        self._xf = QTransform()
        self._xf_touched = False
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


    def reset_selection(self) -> None:
        """选区恢复到整幅图，**像素一个都不动**。

        两种场景用：

        - 弹窗丢掉一次**待定**裁剪（Ctrl+Z 优先退掉的就是它，参数页也有
          「重置选区」）——像素本来就没被裁，框弹回整幅就等于反悔成功；
        - 选区被拖成小于 ``MIN_RECT_EDGE`` 的"废框"时的兜底。

        ⚠️ 与 :meth:`set_tool` 的差别只在于**不动工具、不清变换预览**，所以
        拿它撤销"待定裁剪"是安全的（不会把正在预览的变换一起掀掉）。
        """
        if self._tool in ("crop", "transform") and self._image is not None:
            if self._tool == "crop" and self._crop_offset != QPointF():
                self._crop_offset = QPointF()
                if self._item is not None:
                    self._item.setPos(0, 0)
                self._sync_border()
                self._sync_scene_rect()
            image_rect = self.image_rect()
            bounds = self._content_rect()
            self._rect = (bounds.translated(image_rect.topLeft())
                          if bounds is not None else QRectF(image_rect))
            self._xf_pivot = (QPointF(self._xf_pivot_saved)
                              if self._xf_pivot_saved is not None
                              else self._rect.center())
        self._sync_overlay()


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
        rect = self._content_scene_rect()
        if self.sceneRect() != rect:
            self.setSceneRect(rect)
        if ratio is None or isinstance(ratio, bool) \
                or not isinstance(ratio, (int, float)):
            ratio = self._fit_ratio
        ratio = max(0.2, min(1.0, float(ratio)))
        if ratio < 1.0 and not rect.isNull():
            grow_x = rect.width() * (1.0 / ratio - 1.0) / 2.0
            grow_y = rect.height() * (1.0 / ratio - 1.0) / 2.0
            rect = rect.adjusted(-grow_x, -grow_y, grow_x, grow_y)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.centerOn(rect.center())
        self._zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.transform().m11()))
        # 手柄的几何 = 视图像素 ÷ 当前倍率，倍率变了必须重算覆盖层；
        #    不然 set_image 时用脏 viewport 算的小倍率会留下巨型手柄
        #    （离屏渲染抓出来的：手柄有 ~150 视图像素，应为 12）。
        self._sync_item_render_mode()
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
        self._sync_item_render_mode()  # ≥100% 按像素格显示（放大不发虚）
        self._sync_overlay()  # 手柄视觉尺寸不随缩放变，几何要重算


    def fit_selection(self) -> None:
        """视图适配当前选区（选区约占视口 80%，四周留出可操作白边）。

        裁剪区收小后松手时调用——选区变小了就要放大查看（用户 20:18 定）。
        ⚠️ 不填满视口：顶满时选区边界贴着视口边缘，看不到上下文、手柄
        也挤在边上不好抓（用户 20:28 定"缩放至选区时留出边距"）。
        视图从此锚定选区（``_user_zoomed``），窗口 resize 不再拉回整图。

        ⚠️⚠️ **受「是否自动缩放画布」开关约束**（2026-10-14 用户报障
        「选择一张图片，画布自动缩放，导致选择图片位置发生变化；这个开关
        没有生效」）：本方法**直接** ``resetTransform`` + ``scale`` +
        ``centerOn``，等价于一次 fit ⇒ 开关为假时它也照做，用户勾没勾完全
        没区别（实测选区 600×800 时 zoom 从 0.3885 直接翻到 0.7810，整整
        一倍，"选择"一下画面就跳）。开关的语义是"**别自动改我的视图**"，
        变换链上的 :meth:`TransformMixin._finish_transform_auto_fit` 早已
        认它，这里补齐 ⇒ 关闭时不动视图（用户自己滚轮缩放）。
        """
        if not self._xf_auto_fit_canvas:
            return
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
        self._sync_item_render_mode()
        self._sync_overlay()
