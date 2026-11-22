# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""画布基座：缩放适配。"""
from __future__ import annotations

from typing import TYPE_CHECKING

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
from ..distortion import DistortionMixin
from ..interaction import InteractionMixin
from ..overlay import OverlayMixin
from ..text import TextMixin
from ..transform import TransformMixin

if TYPE_CHECKING:
    from .._host import CanvasHost
else:
    CanvasHost = object



class ZoomMixin(CanvasHost):
    """画布基座：缩放适配。"""



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
