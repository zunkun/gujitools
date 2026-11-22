# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""画布基座：工具切换与选区 / 恢复像素。"""
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



class ToolsMixin(CanvasHost):
    """画布基座：工具切换与选区 / 恢复像素。"""



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
