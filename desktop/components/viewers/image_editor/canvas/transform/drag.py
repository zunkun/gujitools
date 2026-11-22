# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""统一变换：拖拽开始与应用。"""
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



class TransformDragMixin(CanvasHost):
    """统一变换：拖拽开始与应用。"""


    # ---- 拖拽状态机（交互 Mixin 调用；都返回/更新 self._mode 的形状） ----
    def _begin_transform_drag(self, hit: str, pos: QPointF,
                              modifiers) -> tuple | None:
        """按命中结果进入一次统一变换拖拽；返回 ``_mode`` 元组（None = 不拖）。

        锚点、起始点一律取**按下瞬间的快照**：拖动过程中每次都从快照重算
        （而不是在上一帧结果上叠加），所以来回甩鼠标不会累积误差，松手回到
        原位也能精确复原。
        """
        # ⚠️ 延迟供像素的那次等待里有模态进度框（processEvents），用户可能
        #    已经松开了左键——那个 release 被进度框的事件循环吃掉了，画布
        #    永远等不到；不查的话"拖动"会一直挂着，鼠标移动就跟着变形。
        #    ⚠️ 只在**这次按下真的经历了等待**时才查（ waited）：测试用裸
        #    构造的 QMouseEvent 不经过 Qt 的按钮状态机，一律查会把它们误杀。
        waited_for_restore = (self._xf_restore_pending
                              and self._xf_restore_region is None)
        # ⚠️⚠️ **先置拖动态、再建预览**（2026-10-14「双图统一变换首次点击
        #    卡顿」实测修）：``_ensure_transform_preview`` 末尾会调
        #    ``_sync_float()`` 建浮层第一帧，而 :meth:`_sync_float` 是按
        #    ``_xf_dragging`` 分岔的——为假走 :meth:`_render_float_plane`
        #    的**逐像素精确重采样**。旧版把 ``_xf_dragging = True`` 放在
        #    ensure **之后**，于是首次拖动白白先出一帧精确结果（12 MP 实测
        #    **467 ms**），紧接着第一次 move 就走 :meth:`_apply_float_fast`
        #    把整帧覆盖掉——那 467 ms 纯浪费且全卡在按下瞬间（用户报障：
        #    "初次点击图片移动卡顿，几秒后正常"；第二次拖动只要 462 ms，
        #    且切层后必重来一次，与"每张图初次都卡"完全吻合）。
        #    现在拖动态先立起来 ⇒ 建预览就走快档（图元承担变换，亚毫秒），
        #    精确档仍然只在 :meth:`finish_transform_drag`（松手）出一次，
        #    "预览 == 烘焙"的判据一点没松。
        self._xf_dragging = True
        try:
            self._ensure_transform_preview()
        except Exception:
            # 建预览失败不能把画布永久留在"拖动中"（否则之后所有
            # ``_sync_float`` 都退化成快档、松手也不补精确帧）
            self._xf_dragging = False
            raise
        if self._float_item is None or self._xf_rect is None:
            self._xf_dragging = False
            return None
        if waited_for_restore and not (
                QApplication.mouseButtons() & Qt.MouseButton.LeftButton):
            self._xf_dragging = False
            return None
        # 按下的节点立刻成为"激活节点"（高亮跟随），不冒泡到移动/旋转
        self._set_handle_focus(hit if hit in _HANDLE_HITS else None)
        rect = self._xf_rect.normalized()
        # ⚠️ 拖拽数学全程在**视觉空间**里做（快照 = 视觉矩阵）：鼠标逆映射、
        #    透视四角、旋转中心全按屏幕上看到的框算；落账时经
        #    :meth:`_apply_visual` 按方向存回 ``_xf``。旧版快照 ``_xf``、
        #    框画的是 ``_preview_xf``，校正模式下鼠标和框各走各的。
        v_start = self._visual_xf()
        inverse, _ = v_start.inverted()
        if hit == "pivot":
            if self._xf_lock_pivot:
                return None
            return ("xf_pivot", inverse)
        if hit in PERSP_HANDLES:
            quad = [v_start.map(point)
                    for point in self._transform_local_corners()]
            return ("xf_persp", v_start, quad,
                    CORNER_HANDLES.index(hit[2:]))
        if hit in CORNER_HANDLES:
            opposite = {"tl": rect.bottomRight(), "tr": rect.bottomLeft(),
                        "bl": rect.topRight(), "br": rect.topLeft()}[hit]
            anchor = (self._xf_pivot if self._from_pivot("scale", modifiers)
                      else QPointF(opposite))
            return ("xf_scale", v_start, inverse.map(pos), anchor, hit)
        if hit in SIDE_HANDLES:
            anchor = (self._xf_pivot if self._from_pivot("scale", modifiers)
                      else self._transform_side_anchor(hit))
            return ("xf_scale1", v_start, inverse.map(pos), anchor, hit)
        if hit in SHEAR_HANDLES:
            # 切变按"光标总共挪了多远"算，所以快照**光标点**（不是菱形中心）：
            # 菱形只占边的 ¾ 处一小块，用户抓的其实是整条边，被抓的那一点
            # 必须跟着光标走——否则鼠标在菱形上按下后一移，边会跳一下。
            # ⚠️ 存进 mode 的点必须是**选区局部坐标**（过一次视觉矩阵的逆），
            #    否则拖动时"局部位移"会把矩阵的平移量一起算进去（实测抓
            #    ¾ 处的菱形拖 60px，被抓的边跑了 560px）。
            return ("xf_shear", v_start, inverse.map(pos), hit[2])
        if hit in ("inside", "center"):
            return ("xf_move", v_start, pos)
        center = v_start.map(self._xf_pivot)            # 框外 = 绕轴心旋转
        angle0 = math.degrees(math.atan2(
            pos.y() - center.y(), pos.x() - center.x()))
        return ("xf_rotate", v_start, center, angle0)

    def _apply_transform_drag(self, mode: tuple, pos: QPointF,
                              modifiers) -> None:
        """把一次拖拽应用到**视觉矩阵**（每种模式都从"按下快照"重算）。

        各分支先在视觉空间里算出 ``visual``，末尾统一经
        :meth:`_apply_visual` 按方向落账回 ``_xf``——正向行为与旧版逐位
        一致（视觉矩阵 = ``_xf``），校正（向后）模式从此框随鼠标走。
        """
        kind = mode[0]
        if kind == "xf_pivot":
            inverse = mode[1]
            assert self._xf_rect is not None
            point = clamp_rect(
                QRectF(inverse.map(pos), QSizeF(0, 0)),
                self._xf_rect.normalized()).topLeft()
            self._xf_pivot = self._snap_pivot(point) if self._xf_snap_pivot \
                else point
            # 记进"用户摆过的轴心"：提交/换工具/换图后仍然绕它转
            # （``core._xf_pivot_saved``——不这样，反复旋转会越转越小）
            self._xf_pivot_saved = QPointF(self._xf_pivot)
            # 拖轴心**不改矩阵**（浮层原样），只把轴心圆点挪过去
            self._sync_overlay()
            return
        v_start, visual = mode[1], None
        if kind == "xf_move":
            start = mode[2]
            delta = pos - start
            if self._constrain("move", modifiers):
                delta = _snap_45(delta)
            visual = v_start * QTransform().translate(delta.x(), delta.y())
        elif kind == "xf_rotate":
            _, v_start, center, angle0 = mode
            angle = math.degrees(math.atan2(
                pos.y() - center.y(), pos.x() - center.x()))
            delta = (angle - angle0 + 180.0) % 360.0 - 180.0
            if self._constrain("rotate", modifiers):
                delta = round(delta / ROTATE_SNAP_DEG) * ROTATE_SNAP_DEG
            # 旋转发生在视觉矩阵之后（轴心是视觉位置）：(V * R) 先 V 后 R
            visual = v_start * rotate_about(center, delta)
        elif kind in ("xf_scale", "xf_scale1"):
            _, v_start, p0_local, anchor, hit = mode
            inverse, _ = v_start.inverted()
            current = inverse.map(pos)
            sx = _axis_ratio(current.x(), p0_local.x(), anchor.x())
            sy = _axis_ratio(current.y(), p0_local.y(), anchor.y())
            if kind == "xf_scale1":
                # 单轴：只有垂直于被抓那条边的那个轴动，另一个轴锁死
                if hit in ("l", "r"):
                    sy = 1.0
                else:
                    sx = 1.0
            elif self._constrain("scale", modifiers):
                sx = sy = (sx + sy) / 2.0            # 等比（GIMP 的 Scale 约束）
            # 局部操作发生在视觉矩阵**之前**：(S * V) 先 S 后 V
            visual = scale_about(anchor, sx, sy) * v_start
        elif kind == "xf_shear":
            _, v_start, start_local, edge = mode
            inverse, _ = v_start.inverted()
            # ``start_local`` 与 ``pos`` 都换到**选区局部坐标**再作差：这样得到的
            # 是"光标在框内走了多远"，与边本身当前被摆到哪里无关。
            delta = inverse.map(pos) - start_local
            assert self._xf_rect is not None
            rect = self._xf_rect.normalized()
            # 系数 = 光标沿边方向的位移 ÷ **这条边自身的方向跨度**。
            # 抓右/左边是**水平切变**（y' = y + sh·x）：要让右缘整条下移 d，
            # sh 必须是 d/**宽度**（用高度算的话右缘只会挪 d·w/h，跟手差一截）。
            # 抓上/下边同理用**高度**（x' = x + sv·y）。
            k = (delta.y() / rect.width() if edge in ("l", "r")
                 else delta.x() / rect.height())
            visual = self._apply_shear(
                edge, k, v_start, self._from_pivot("shear", modifiers))
        elif kind == "xf_persp":
            _, v_start, quad, index = mode
            target = QPointF(pos)
            if self._constrain("perspective", modifiers):
                target = _on_diagonal(quad, index, target)
            assert self._xf_rect is not None
            step = _perspective_step(v_start, quad, index, target,
                                     self._xf_rect)
            if step is not None:                     # 退化 / 病态：这一步不动
                visual = v_start * step
        if visual is None:
            return
        self._apply_visual(visual)

    def _apply_shear(self, edge: str, k: float, x_start: QTransform,
                     from_pivot: bool = False) -> QTransform:
        """在 ``x_start`` 基础上叠一次切变，**返回新矩阵**（不直接落账）。

        调用方（语义入口/拖拽）拿到结果后经 :meth:`_apply_visual` 按方向
        写回 ``_xf``。``x_start`` 一律传**视觉矩阵**。

        ``from_pivot=False``（GIMP 默认）：**对边固定**，抓的这条边整条平移；
        ``from_pivot=True``：绕轴心切变，两边反向各走一半。
        """
        assert self._xf_rect is not None
        if from_pivot:
            pivot = QPointF(self._xf_pivot)
            if edge in ("l", "r"):
                return shear_about(
                    pivot, 0.0, k if edge == "r" else -k) * x_start
            return shear_about(
                pivot, k if edge == "b" else -k, 0.0) * x_start
        anchor = self._shear_anchor(edge)      # 对边整条不动
        if edge in ("l", "r"):
            sv = -k if edge == "l" else k
            return shear_about(anchor, 0.0, sv) * x_start
        sh = -k if edge == "t" else k
        return shear_about(anchor, sh, 0.0) * x_start
