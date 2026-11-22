# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""统一变换：拖动中的浮层快档与落账。"""
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



class TransformFloatMixin(CanvasHost):
    """统一变换：拖动中的浮层快档与落账。"""


    def _preview_placement_xf(self) -> QTransform:
        """浮层像素矩阵：**预览尺度选区局部坐标 → 预览尺度图片坐标**。

        就是烘焙矩阵（``选区局部坐标 → 图片坐标``，见 ``compose_transform``
        里的 ``placed``）的降采样版本：``S(k) ∘ placed ∘ S(1/k)``。两边的
        ``S`` 一个都不能少——只缩结果的话，``warp_placement`` 里的目标外框
        按未缩放的尺度算，12 MP 时每帧都要重采样整幅（实测 1756 ms/帧）。

        ``warp_placement`` 用它算出来的 ``(x0, y0)`` = 变换后选区的外框左上角
        （在预览图片坐标里），浮层据此摆位（见 :meth:`_float_placement`）。

        ⚠️⚠️ **Qt 的 ``A * B`` 是"先 A 后 B"**（行向量约定），所以"先降采样、
        再套变换、最后放大回预览尺度"要写成 ``S(1/k) * placed * S(k)``。旧版写
        成了 ``S(k) * placed * S(1/k)``——数学记号里 ``S(k) ∘ placed ∘ S(1/k)``
        是对的，但落到 QTransform 上左右正好颠倒，于是矩阵整体变成
        ``placed(k·u)/k``：**平移量被多除了一个 k**。k=1（选区 ≤0.5 MP）时
        看不出来，图一大（k≈0.6）内容就整体偏 ``t·(1/k−1)``——用户报的
        「操作框跟图片分离、格子跟图片相互远离」正是它（600×800 只有 0.48 MP，
        所以旧自测一直是绿的 ⇒ 判据必须用**大于预览预算**的图）。

        ⚠️ 这个矩阵**只用来渲染浮层像素**（即松手后的精确档）。旧版又拿它当
        浮层图元的 transform 用了一遍 ⇒ 内容被转两遍、还被固定大小的画布裁掉
        一半（用户报的"旋转后图片不完整显示"）。拖动中的图元矩阵是另一条
        （见 :meth:`_float_fast_xf`），两者的口径**故意不同**。
        """
        scale = max(self._xf_preview_scale, 1e-6)
        return (QTransform().scale(1.0 / scale, 1.0 / scale)
                * self._placed_xf()
                * QTransform().scale(scale, scale))

    def _float_placement(self) -> QTransform:
        """浮层图元的变换：预览尺度像素 → 图片坐标（**纯缩放 + 平移**）。

        浮层像素活在"图片坐标 ÷ ``_xf_preview_scale``"里、左上角在
        ``_xf_preview_origin``，所以这里只需"挪回原位、再放大回去"。变换本身
        已经在像素里烘好了，这里**再套一次就是双重变换**。

        ⚠️ 这是**精确档**（松手 / 首次）的口径；拖动中像素没有烘过，变换必须
        由图元承担 ⇒ 那时用 :meth:`_float_fast_xf`（带旋转/切变/透视）。
        """
        scale = max(self._xf_preview_scale, 1e-6)
        origin = self._xf_preview_origin
        return (QTransform().scale(1.0 / scale, 1.0 / scale)
                * QTransform().translate(origin.x(), origin.y()))

    def _float_fast_xf(self) -> QTransform:
        """**拖动中**浮层图元的变换：预览缩放的**区域局部坐标** → 图片坐标。

        ``_xf_preview_region`` 是选区原图按 ``_xf_preview_scale`` 缩出来的，
        它的像素 ``u`` 对应选区局部的 ``u / k``，所以"区域局部 → 图片"= 先
        ``S(1/k)`` 再 ``placed``（见 :meth:`_placed_xf`）。

        ⚠️⚠️ 同样要按 Qt 的"**先左后右**"来写：``S(1/k) * placed``。旧版写成
        ``placed * S(1/k)`` ⇒ 变成 ``placed(u)/k``，平移量被多除一个 k，拖动中
        的内容同样偏出去（与 :meth:`_preview_placement_xf` 是同一个错，两处
        必须一起改，否则松手会跳）。

        ⚠️ 与 :meth:`_float_placement` 的区别就是**它自带变换本身**（旋转/切变/
        透视都在里面）：那边像素烘过了、图元只能缩放平移；这边像素是原图、
        变换必须由图元做。混用 = 内容被转两遍或被原地不动。
        """
        scale = max(self._xf_preview_scale, 1e-6)
        return (QTransform().scale(1.0 / scale, 1.0 / scale)
                * self._placed_xf())

    def _float_fast_plane(self) -> QImage:
        """**拖动中**的浮层像素：预览缩放的选区**原图**，越界部分按裁剪掩膜。

        ⚠️ 为什么不再逐像素重采样（见 :meth:`_render_float_plane`）：那是
        150–450 ms/帧 的量级（实测 12 MP 选区 `linear` 158 ms、`nohalo` 442 ms），
        拖动根本跟不上——用户报的"旋转不能实时"就是这个。改成"像素不重采样、
        变换交给图元"之后由 Qt 光栅器做，**实测 0.4–1.5 ms/帧**；而且只重采样
        一趟（不再"缩小→再放大"），**画面反而比逐像素预览更清晰**。

        代价是插值只能用 Qt 的平滑档（双线性），吃不到用户的 `nohalo/cubic`
        选项——所以松手那一帧仍然走精确档，"预览 == 烘焙"的判据一点没松
        （见 :meth:`finish_transform_drag`）。

        裁剪（``clip`` / ``aspect`` 档）在拖动中同样要生效，否则内容会溢出
        到画布外、松手一瞬间又"跳"回去。拖动的图元矩阵是仿射/投影，
        把裁剪矩形**逆映射回区域局部坐标**会得到一个平行四边形，用
        ``QPainterPath`` 掩膜即可（实测 +0.5–1 ms/帧）。
        """
        region = (self._xf_preview_region if self._xf_preview_region is not None
                  else self._xf_region)
        if region is None or region.isNull():
            return region
        clip = self._plane_clip_rect()
        if clip is None:
            return region
        local, ok = self._float_fast_xf().inverted()
        if not ok:                                # 病态矩阵：宁可不裁
            return region
        path = QPainterPath()
        path.addRect(clip)
        # ⚠️ 要清掉的是**裁剪矩形之外**的部分。``setClipPath`` 是把笔限制在
        #    路径**之内**，直接配 ``CompositionMode_Clear`` 会清反（实测
        #    "该留的透明、该清的留着"，画面看着像内容整块消失）——所以先取
        #    补集路径再清，与 :meth:`_cut_plane` 的四块补集同一个意思。
        outside = QPainterPath()
        outside.addRect(QRectF(region.rect()))
        masked = region.copy()
        painter = QPainter(masked)
        painter.setClipPath(outside.subtracted(local.map(path)),
                            Qt.ClipOperation.ReplaceClip)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(QRectF(masked.rect()), QColor(0, 0, 0, 0))
        painter.end()
        return masked

    def _apply_float_fast(self) -> None:
        """拖动中的浮层：换像素 + 让图元承担变换，**不做逐像素重采样**。

        ⚠️ 最后必须把"已重采样"的判据 :attr:`_xf_preview_keyframe` 清掉：
        拖动一结束（``_xf_dragging`` 变 False）:meth:`_sync_float` 就会看到
        判据为空、重出一帧**精确**结果。不清的话会留着这张"原图 + 图元变换"
        的快照，而图元矩阵下一秒被换成 :meth:`_float_placement`（坐标口径
        完全不同）⇒ 画面跳变。
        """
        assert self._float_item is not None
        self._float_item.setPixmap(QPixmap.fromImage(self._float_fast_plane()))
        self._float_item.setTransform(self._float_fast_xf())
        self._xf_preview_keyframe = None

    def _render_float_plane(self) -> None:
        """（重）画浮层：**变换后的选区内容**（空白处透明）。—— **精确档**。

        ⚠️ 只在这里碰"浮层的像素"，别在 ``_sync_float`` 里画整幅变换——
        ``_sync_float`` 每次鼠标移动都会被调到，而逐像素重采样是大头。
        画布取 ``warp_placement`` 给的外框，所以内容搬到画外也**不会被裁**。

        ⚠️ 本方法只在**非拖动**时被调用（``_sync_float`` 拖动中走
        :meth:`_apply_float_fast`）：逐像素重采样一帧 150–450 ms，拖动根本
        跟不上。所以这里直接用用户选的插值出**与烘焙同一套数学**的结果，
        不存在"拖动中先用轻量档垫一下"的分支了。
        """
        if self._float_item is None or self._xf_rect is None \
                or self._xf_region is None:
            return
        region = (self._xf_preview_region if self._xf_preview_region is not None
                  else self._xf_region)
        warp = warp_placement(
            region, self._preview_placement_xf(), self._xf_interpolation)
        if warp is None:                      # 取消 / 病态矩阵：不画内容
            warp = (QImage(), 0, 0)
        image, x0, y0 = warp
        # ⚠️ ``warp_placement`` 回来的 ``(x0, y0)`` 在**预览尺度**坐标里（矩阵的
        #    输出系），而 :attr:`_xf_preview_origin` 与 :meth:`_float_placement`、
        #    :meth:`_cut_plane` 的口径都是**图片坐标** ⇒ 这里除一次降采样倍率。
        #    不除的话浮层会被挪走 ``x0·(1−1/k)`` 那么多（图越大偏得越狠）。
        self._xf_preview_origin = QPointF(
            x0 / max(self._xf_preview_scale, 1e-6),
            y0 / max(self._xf_preview_scale, 1e-6))
        image = self._cut_plane(image)
        self._float_item.setPixmap(QPixmap.fromImage(image))
        self._xf_preview_keyframe = self._preview_placement_xf()

    def _cut_plane(self, image: QImage) -> QImage:
        """按 :meth:`_plane_clip_rect` 把浮层越界的内容抹成透明（同烘焙）。

        浮层像素坐标 ``p`` 与图片坐标 ``i`` 的关系是 ``i = (p + 原点) / 倍率``
        （见 :meth:`_float_placement`），所以"画布矩形"换算到浮层里就是
        ``倍率 × 画布 − 原点``；四块补集各清一次，不必引 QPainterPath。
        """
        clip = self._plane_clip_rect()
        if clip is None or image.isNull() or self._image is None:
            return image
        scale = max(self._xf_preview_scale, 1e-6)
        origin = self._xf_preview_origin
        keep = QRectF(scale * clip.x() - origin.x(),
                      scale * clip.y() - origin.y(),
                      scale * clip.width(), scale * clip.height())
        inside = keep.intersected(QRectF(image.rect()))
        if inside == keep:
            return image
        bounds = QRectF(image.rect())
        cut = image.copy()
        painter = QPainter(cut)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Clear)
        for part in (
            QRectF(bounds.left(), bounds.top(),
                   bounds.width(), inside.top() - bounds.top()),
            QRectF(bounds.left(), inside.bottom(),
                   bounds.width(), bounds.bottom() - inside.bottom()),
            QRectF(bounds.left(), inside.top(),
                   inside.left() - bounds.left(), inside.height()),
            QRectF(inside.right(), inside.top(),
                   bounds.right() - inside.right(), inside.height()),
        ):
            if part.width() > 0 and part.height() > 0:
                painter.fillRect(part, QColor(0, 0, 0, 0))
        painter.end()
        return cut

    def finish_transform_drag(self) -> None:
        """松手：把预览从"拖动快档"升回**精确档**（与烘焙同一套数学）。

        拖动中像素不重采样、变换交给图元（亚毫秒级，见
        :meth:`_apply_float_fast`）；松手瞬间图不再动，这一次重采样只做一遍
        （用户看不到卡），于是**松手后看到的预览就是烘焙结果**——"预览 ==
        烘焙"的判据一点没松。
        """
        if not self._xf_dragging:
            return
        self._xf_dragging = False
        # 拖动中是"原图 + 图元变换"，松手要重出一帧精确结果 ⇒ 判据清零
        self._xf_preview_keyframe = None
        self._sync_float()
        self._finish_transform_auto_fit()

    def _sync_float(self) -> None:
        """浮层跟随累计矩阵 + 预览开关（不透明度 / 显示预览 / 合成预览）。

        两条**故意不同**的路（用户 2026-10-09 报障「只旋转不能实时渲染」）：
        ``_xf_dragging`` 为真 = 拖动中 ⇒ :meth:`_apply_float_fast`（像素不重采样、
        变换交给图元，亚毫秒级）；为假 = 首次 / 松手后 ⇒ :meth:`_render_float_plane`
        出**与烘焙同一套数学**的精确结果。松手时 :meth:`finish_transform_drag`
        会把 ``_xf_dragging`` 关掉并让判据失效，于是立刻补上精确那一帧。

        方向切换时底图会失效（它按"那一刻的矩阵"画好了结果），所以这里发
        现方向与建预览时不一致就整块重建——否则画面会停在旧方向上骗人。
        ⚠️ 恢复会话的浮层源（upright）要**跨重建保留**：重建只是换方向，
        不是结束恢复。
        """
        if self._float_item is None or self._xf_rect is None:
            return
        if self._xf_preview_direction != self._xf_direction:
            restore = self._xf_restore_region
            self._clear_transform_preview()
            self._xf_restore_region = restore
            self._ensure_transform_preview()
            return
        # 底图范围恒定（= 原图矩形），拖动中不会长大 ⇒ 这里几乎恒不触发；
        # 只有"选区被换掉"（整幅 ↔ 局部）时才要重铺残影
        if self._backdrop_needs_resize():
            self._rebuild_backdrop()
        if self._xf_dragging:
            self._apply_float_fast()
        else:
            # ⚠️ 只有**重采样结果**真变了才重算像素（判据 = 那个矩阵，含降采样）；
            #    没变就只挪图元，省掉一次逐像素重采样。
            if self._xf_preview_keyframe != self._preview_placement_xf():
                self._render_float_plane()
            # ⚠️ 图元只做**摆位**（缩放 + 平移）：变换已经在像素里烘好了
            self._float_item.setTransform(self._float_placement())
        self._float_item.setOpacity(
            max(0.0, min(1.0, self._xf_preview_opacity / 100.0)))
        self._float_item.setVisible(bool(self._xf_show_preview))
        # 「合成预览」关掉 = 只看变形的那一块，「纸」也一并藏起来
        if self._item is not None:
            self._item.setVisible(bool(self._xf_compose_preview))
        # 变换把选区送出原边界时，浮层会跑到图片外——扩场景矩形才看得见
        self._sync_scene_rect()
        # ⚠️ 边框跟随内容四至边界（2026-10-13 用户口径「边框并不是固定不变
        #    的，应该根据图片四至边界扩大和缩小」）：拖动中每帧跟手。
        self._sync_border()
