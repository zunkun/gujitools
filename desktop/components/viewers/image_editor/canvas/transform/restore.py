# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""统一变换：内容恢复会话与清理。"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QLineF, QPointF, QRect, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QColor, QImage, QPainter, QPainterPath, QPixmap, QPolygonF, QTransform,
)
from PySide6.QtWidgets import QApplication, QGraphicsPixmapItem

from ...consts import (
    CLIPPINGS, CORNER_HANDLES, CORNER_HIT_VIEW_PX, CORNER_VIEW_PX, DIRECTIONS,
    EDGE_BAND_VIEW_PX, EDGE_HANDLE_MIN_VIEW_PX, GUIDE_RATIOS, GUIDES,
    HANDLE_HIT_VIEW_PX, INTERPOLATIONS, PERSP_HANDLES, PERSP_HIT_VIEW_PX,
    PERSP_INSET_VIEW_PX, PERSP_VIEW_PX, PIVOT_VIEW_PX, ROTATE_SNAP_DEG,
    SHEAR_AT, SHEAR_HANDLES, SHEAR_HIT_VIEW_PX, SHEAR_VIEW_PX, SIDE_HANDLES,
    SIDE_VIEW_PX, TRANSFORM_PREVIEW_PIXELS,
)
from ...geometry import (
    _dist_to_segment, clamp_rect, flip_transform, mapped_bounds, quad_point,
    quad_to_quad_transform, rotate_about, scale_about, shear_about,
    transform_region, warp_placement,
)
from ..overlay import _style_node
from .constants import (
    _CONSTRAIN_KEYS, _CORNER_NEIGHBOURS, _CORNER_UV, _EDGE_CORNERS, _EDGE_UV,
    _HANDLE_HITS, _PIVOT_KEYS, _SIDE_ANCHOR,
)
from .helpers import (
    _axis_ratio, _blank_image, _center_crop_rect, _diamond, _on_diagonal,
    _perspective_step, _snap_45,
)

if TYPE_CHECKING:
    from .._host import CanvasHost
else:
    CanvasHost = object



class TransformRestoreMixin(CanvasHost):
    """统一变换：内容恢复会话与清理。"""


    def _clear_transform_preview(self) -> None:
        """撤掉预览浮层并把底图恢复成真像素（矩阵不动，见 reset_transform）。"""
        self._xf_auto_fit_pending = False
        # ⚠️ 临时抑制标志一并清掉：撤预览＝变换结束（取消/重置/换工具/换图
        # 都走这里）。不清的话用户"转一下又按重置"就会永久失去 resize 适配。
        self._xf_fit_suppressed = False
        if self._float_item is not None:
            self._scene.removeItem(self._float_item)
            self._float_item = None
        if self._paint_image is not None:
            self._paint_image = None
            self._xf_region = None
            self._xf_preview_region = None
            self._xf_preview_scale = 1.0
            self._xf_preview_keyframe = None
            self._xf_rect = None
            self.refresh()
        self._xf_restore_region = None   # 恢复会话一并结束（换图/换工具/重置）
        self._xf_restore_pending = False  # 延迟供像素的"挂起"也一样结束
        if self._item is not None:
            self._item.setVisible(True)   # 「合成预览」关掉过的话要还回来
            self._item.setPos(0.0, 0.0)   # 向后预览的底图被挪过位置，要还回来
            self._item.setTransform(QTransform())   # 1×1 空底的拉伸也要还
        self._xf_base_origin = QPointF(0.0, 0.0)
        self._xf_base_scale = None
        self._xf_preview_origin = QPointF(0.0, 0.0)
        # 浮层没了 → 场景矩形收回图片边界（变换曾把浮层送出图外时扩过）
        self._sync_scene_rect()
        self._sync_border()   # 边框一并收回图片边界（虚线框跟随四至）

    def reset_transform(self) -> None:
        """「重置」：丢弃未应用的变换，选区回到整幅、轴心回到中心。"""
        self._clear_transform_preview()
        self._xf = QTransform()
        self._xf_touched = False
        self._xf_pivot_saved = None      # 重置连轴心一起归位
        if not self.image_rect().isNull():
            self._rect = QRectF(self.image_rect())
            self._xf_pivot = self._rect.center()
        self._sync_overlay()

    def transform_pending(self) -> tuple[QRectF, QTransform, QImage] | None:
        """未应用的变换 ``(选区, 矩阵, 选区像素快照)``；没有则 None。"""
        if (not self._xf_touched or self._xf_rect is None
                or self._xf_region is None):
            return None
        return (QRectF(self._xf_rect), QTransform(self._xf),
                QImage(self._xf_region))

    # ---- 内容节点恢复（二次编辑，2026-10-10） ----
    def consume_content_restore(self) -> None:
        """标记 sidecar 恢复已处理（无数据/失败/完成）：本会话不再触发。"""
        self._content_restore_done = True

    def rearm_content_restore(self) -> None:
        """内容节点仍有效时，允许下次进变换工具**重新触发** sidecar 恢复。

        恢复会话没拖就切走（切到裁剪没裁/文字/擦除/扭曲——都不改图片边缘），
        再切回「统一变换」时 PA1 框要重新挂上（用户 2026-10-10 口径）。
        ``_content_restore_done`` 是"已处理过"的一次性闸门，这里把它退回；
        弹窗重进 ``_on_content_restore_requested`` 时节点数据还在，
        重新武装是零成本的（只挂框/矩阵，反变换依旧延迟到首次拖动）。
        真裁剪/撤销/翻转已把节点整组作废（``_content_state=None``），
        弹窗侧不会走到重挂——这里只管放行信号。
        """
        self._content_restore_done = False

    def begin_restored_transform(self, xf: QTransform,
                                 region: QImage | None = None,
                                 rect0: QRectF | None = None) -> None:
        """把恢复出来的矩阵挂成**未触摸**的待定变换（画布保持文件原样）。

        用户 2026-10-10 口径：「编辑 PB1 图片的时候，正常显示的是 PB1；
        执行统一形变的时候，PB1 要作为画布，PA1 要作为可操作的区域恢复」：

        * **画布（``_image``）一个像素都不换**：仍是落盘文件 PB1（内容四边形
          PA1 已烘焙在内、四角透明）；
        * ``region``（upright 内容，sidecar 反变换产物）成为浮层像素源，
          选区局部矩形＝rect0（upright 整幅）；纸面清空，浮层正好盖在 PB1
          里已烘焙的内容上——视觉与打开时完全一致（零跳变）；
        * 矩阵 ``xf``＝**画布系**总量矩阵（弹窗已把 sidecar 的文件系 V 平移
          到 PB1 坐标）：框/手柄/轴心立刻落在 PA1 四边形上（＝上次保存前
          的操作状态）；
        * ⚠️ ``_xf_touched`` **保持 False**：用户不再动就没有任何烘焙（切
          工具/「完成」都不重采样，零代次损失）；一旦拖动，走正常挂起→
          烘焙链，烘焙输入＝upright、矩阵＝总量 ⇒ 每次保存只损失一次
          重采样代次。

        ⚠️⚠️ **延迟供像素**（2026-10-10「切换卡顿」）：``region`` 为 ``None``
        时**只**挂矩阵、框（``rect0``＝sidecar 里的 rect0，必传）和轴心——
        **不**建预览、**不**算 upright 反变换（那是秒级重活，之前每次进
        变换工具都要等它，用户报的正是这个）。像素推迟到第一次建预览
        （＝第一次拖动）时由 :meth:`_ensure_transform_preview` 经
        ``restore_pixels_requested`` 向弹窗要。之前把反变换算好再调
        ``begin_restored_transform(seed, upright)`` 的旧入口原样可用。
        """
        if self._tool != "transform" or self._image is None:
            return
        if region is None:
            if rect0 is None or rect0.isEmpty():
                return
            self._xf_restore_pending = True
            self._xf_restore_region = None
            self._xf_rect = QRectF(rect0)
            self._xf = QTransform(xf)
            self._xf_pivot = self._xf_rect.center()
            self._sync_overlay()
            return
        if not region.isNull():
            self._xf_restore_region = QImage(region)
        self._xf_restore_pending = False
        # ⚠️ **不建预览**（2026-10-13「统一变换切换卡顿」）：缓存命中路径
        #    以前进工具那一刻就 ``_ensure_transform_preview()``——底图重铺
        #    （整幅 copy + 擦选区）+ 浮层精确渲染（逐像素重采样 150–450ms）
        #    全在切换里。现在与"延迟供像素"的裸挂路径同款：只挂区域/框/
        #    矩阵/轴心（零等待），预览推迟到第一次真正需要（首次拖动，
        #    ``_ensure_transform_preview`` 看到 ``_xf_restore_region`` 非
        #    None、``_xf_restore_pending`` False，直接用它搭预览）。
        self._xf_rect = QRectF(0, 0, region.width(), region.height())
        self._xf = QTransform(xf)
        if self._xf_rect is not None:
            # 轴心换到 rect0（upright 局部坐标）中心：视觉上＝内容四边形
            # 中心，旋转/缩放的语义与"保存前那一刻"一致。
            self._xf_pivot = self._xf_rect.center()
        self._sync_overlay()
