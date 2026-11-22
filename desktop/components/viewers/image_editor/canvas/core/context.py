# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""画布基座：双图编辑的上下文底图。"""
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



class ContextImageMixin(CanvasHost):
    """画布基座：双图编辑的上下文底图。"""



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
