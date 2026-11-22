# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""画布基座：刷新与绘制。"""
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



class ViewMixin(CanvasHost):
    """画布基座：刷新与绘制。"""



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
