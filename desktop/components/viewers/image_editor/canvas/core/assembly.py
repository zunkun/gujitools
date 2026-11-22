# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""编辑画布 ``EditorCanvas``：**基座 + 各工具 Mixin 的装配点**。"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QFrame, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView,
)

from ...consts import (
    CANVAS_OUTSIDE, CLIPPING_DEFAULT,
    DIRECTION_DEFAULT, DISTORT_HARDNESS, DISTORT_SIZE, DISTORT_SPACING,
    DISTORT_STRENGTH, EDIT_FIT_RATIO, ERASER_DEFAULT, GUIDE_DEFAULT,
    INTERPOLATION_DEFAULT, MAX_ZOOM, MIN_RECT_EDGE, MIN_ZOOM,
    PREVIEW_OPACITY_DEFAULT, SEL_FIT_RATIO,
)
from ...geometry import _transparent_content_bounds
from ...text_item import TextBlockItem
from .border import BorderMixin
from .context import ContextImageMixin
from .image import ImageStateMixin
from .tools import ToolsMixin
from .view import ViewMixin
from .zoom import ZoomMixin
from ..distortion import DistortionMixin
from ..interaction import InteractionMixin
from ..overlay import OverlayMixin
from ..text import TextMixin
from ..transform import TransformMixin

if TYPE_CHECKING:
    from .._host import CanvasHost
else:
    CanvasHost = object


class EditorCanvas(
    ImageStateMixin,
    ContextImageMixin,
    BorderMixin,
    ViewMixin,
    ToolsMixin,
    ZoomMixin,
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
