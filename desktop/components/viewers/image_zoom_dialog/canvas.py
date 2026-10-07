# -*- coding: utf-8 -*-
"""预览画布：``ZoomTarget`` 与 ``ZoomableCanvas``。

从 ``image_zoom_dialog.py`` 拆出（2026-10-07）。方法体逐字未改。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QFrame, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView,
)

from desktop.ui import theme as T

from .consts import MAX_ZOOM, MIN_ZOOM, PAN_MARGIN_RATIO, WHEEL_STEP, ZOOM_STOPS
from .icons import display_transform

class ZoomTarget:
    """弹窗某一页的数据来源（宿主在**主线程**里按页现造）。

    ``render`` 会在 **worker 线程**被调用，所以它只能读构造时快照下来的值
    （路径、参数字典……），**不得**碰任何 QWidget——同 ``worker_thread_affinity``
    的约束。
    """

    __slots__ = ("render", "note", "stem", "count", "original", "cap",
                 "save_path", "edit_path", "edit_label")

    def __init__(self, render, note: str = "", stem: str = "", count: int = 1,
                 original=None, cap: int | None = None, save_path=None,
                 edit_path=None, edit_label: str = "编辑图片"):
        """render: ``(edge:int) -> worker``；cap: 渲染密度上限（如原图原生边长）。

        ``save_path``：本页显示的像素**就是**这个真实文件（Path | None）。
        给了它，编辑器「完成」后把编辑结果覆盖回该文件（编辑器加载的也是
        该文件的全分辨率原图，预览的降采样不掺和）；**只允许在"画布显示的
        内容 1:1 就是这个文件"时给**——区域合成（effect）、打印重排、PDF
        矢量页都是虚拟图，写回会把整张文件覆盖成一块裁剪区域，绝不能开。

        ``edit_path``：本页**编辑时要写回的真实文件**（Path | None），
        可以不同于 ``save_path``——区域合成/打印效果这类派生显示，
        显示的不是某个文件的全部像素，但它**派生自**一个真实文件；编辑
        要改的是那个文件（各步骤改动因此串成一条链，最终落到 PDF）。
        不传时回落 ``save_path``（1:1 显示的情形）。两者都为 None 表示
        没有可回写的文件（PDF 矢量页等），右键菜单不提供「编辑图片」。

        ``edit_label``：右键菜单「编辑…」的文案，默认「编辑图片」。拼版
        有「单图 vs 整页组合」之分（2026-10-07 用户定），宿主构造目标时
        分别传「编辑单图」/「编辑整图」；其余步骤保持默认。
        """
        self.render = render
        self.note = note or "预览"
        self.stem = stem or "preview"
        self.count = max(1, int(count))
        self.original = original  # QSize | None：原始像素尺寸（状态条用）
        self.cap = cap            # int | None：超过它渲染没有意义（会白放大）
        self.save_path = Path(save_path) if save_path else None
        self.edit_path = Path(edit_path) if edit_path else self.save_path
        self.edit_label = edit_label


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
        # 页面边缘画一圈**细边框**：白底纸面与画布背景同色系时，没有它就
        # 分不清"哪里是纸、哪里是空"（用户 17:50 报）。
        # ⚠️ 挂成**子项**：旋转/翻转走父项的 setTransform，边框自动跟随；
        # pen 宽 0 = cosmetic（任何缩放级别下都是 1 设备像素的细线，
        # 不会放到 400% 时边框粗得像黑框）。只影响显示——导出/打印的
        # 位图是 compose 的原图，不带这条线。
        border = QGraphicsRectItem(item.boundingRect(), item)
        border.setPen(QPen(QColor("#8a93a3"), 0))
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
    def keyPressEvent(self, event) -> None:  # noqa: N802
        """←/→ 翻页（工具条 tooltip 承诺过的快捷键，此前一直没实现）。

        ⚠️ 主动 ignore 掉：QGraphicsView 默认用方向键**滚动视图**，焦点落在
        画布上时事件到不了对话框，翻页就死了；这里显式放行给父级。
        """
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            event.ignore()
            return
        super().keyPressEvent(event)

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
    def orientation(self) -> QTransform:
        """当前翻转/旋转矩阵（恒等 = 没动过朝向）。

        编辑器回写原图时用它把朝向"烤"进全分辨率原图——见
        ``ImageZoomDialog._edit_image``。
        """
        return display_transform(self._rotation, self._flip_h, self._flip_v)

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
