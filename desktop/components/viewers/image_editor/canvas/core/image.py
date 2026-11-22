# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""画布基座：装图 / 换图与渲染模式。"""
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



class ImageStateMixin(CanvasHost):
    """画布基座：装图 / 换图与渲染模式。"""



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
