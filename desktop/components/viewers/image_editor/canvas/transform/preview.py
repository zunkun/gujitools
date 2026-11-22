# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""统一变换：预览浮层建立与收尾。"""
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



class TransformPreviewMixin(CanvasHost):
    """统一变换：预览浮层建立与收尾。"""


    # ------------------------------------------------------------ 预览
    def _preview_xf(self, source: QTransform) -> QTransform:
        """把「源帧」变换换算成**预览帧**变换（= 真正会被烘焙的那个）。

        ``方向 = 校正（向后）`` 时烘焙用的是**反向**矩阵（GIMP 的 Corrective
        口径：框摆到歪掉的那一块上，出来的是被掰正的），预览必须跟着取逆，
        否则"看到的内容落在哪儿"和"松手之后落在哪儿"是两回事。正向直接原样。
        """
        if self._xf_direction != "backward":
            return QTransform(source)
        inverse, ok = source.inverted()
        return inverse if ok else QTransform(source)

    def _visual_xf(self) -> QTransform:
        """累计矩阵的**视觉版**：屏幕上"框与内容"真正呈现的那个矩阵。

        正向 = ``_xf`` 本身；**校正（向后）= ``_xf`` 的逆**（与浮层内容、
        烘焙同口径，见 :meth:`_preview_xf`）。覆盖层（四边形框 / 手柄 /
        参考线 / 轴心）与拖拽数学都吃它——旧版框画的是 ``_xf``、内容走的
        是 ``_preview_xf``，校正模式下两套口径各动各的 ⇒「图片和操作框
        方向相反」（用户 2026-10-09 报障）。
        """
        return self._preview_xf(self._xf)

    def _apply_visual(self, visual: QTransform) -> None:
        """把**视觉空间**里算好的矩阵落账回 :attr:`_xf`（唯一写入口）。

        校正（向后）时 ``_xf`` 存的是视觉矩阵的**逆**（烘焙用反向矩阵，
        见 ``_commit_transform`` / ``compose_transform``），所以这里按方向
        取逆；正向原样存。所有变换操作（拖拽与 ``transform_*`` 语义入口）
        都改成"先在视觉空间叠矩阵，再交给这里落账"——矩阵不可逆的病态
        （理论上到不了，透视那边已挡）退回恒等，绝不存一个炸矩阵。
        """
        if self._xf_direction == "backward":
            inverse, ok = visual.inverted()
            self._xf = inverse if ok else QTransform()
        else:
            self._xf = QTransform(visual)
        self._xf_touched = True
        self._xf_auto_fit_pending = True
        # sceneRect 变化可能改变滚动条并触发 resizeEvent。变换期间不能让该
        # resize 自动 fit，否则视图会跟着图片跳动；自动适配由选项在操作结束
        # 后统一执行。
        # ⚠️⚠️ 这里置的必须是 ``_xf_fit_suppressed``（**临时**，由
        #    ``_finish_transform_auto_fit`` 收尾清掉），**不能**是
        #    ``_user_zoomed``（长期意图"用户手动缩放过"）。旧版写成了后者且
        #    从不还原 ⇒ "做过一次变换"就永久关掉了 resize 自动适配与
        #    ``set_fit_ratio`` 的即时生效：旋转 45° 把图从 400×300 烘焙成
        #    494×494 后倍率仍停在旧的 1.92，切到裁剪时图右侧/底部直接被
        #    视口切掉（2026-10-14 用户报障「切裁剪发现图片被裁剪了一部分」）。
        self._xf_fit_suppressed = True
        self._sync_float()
        self._sync_overlay()
        if not self._xf_dragging:
            self._finish_transform_auto_fit()

    def _finish_transform_auto_fit(self) -> None:
        """在一次变换结束后按用户选项适配画布，未启用时保持当前视图倍率。

        ⚠️ 收尾时**必须**把 ``_xf_fit_suppressed`` 清回 False——它是"本次变换
        期间临时抑制 resize 自动适配"，不是长期意图。留着会让此后每一次
        resize / ``set_fit_ratio``（= 切工具时的重新适配）都失效，表现为
        "变换后切到别的工具，图片有一部分在视口外"。
        """
        self._xf_fit_suppressed = False
        if not self._xf_auto_fit_pending:
            return
        self._xf_auto_fit_pending = False
        if self._xf_auto_fit_canvas:
            self.fit()

    def _ensure_transform_preview(self) -> None:
        """锁定选区并搭起实时预览：底图（"纸"）+ 选区内容浮层。

        只在第一次真正抓取时做一次（拿两张快照），后续拖动只改 ``_xf``、
        重新渲染浮层像素、改浮层的图元变换，不动真图。

        两层的分工（2026-10-09 重定，修"只旋转也画错"）：

        * **底图 = 原图矩形那块的"残余"**：原图里**选区之外**的部分照旧，选区
          那块**擦成透明**（用户 2026-10-09：「图片旋转不再有白色的区域」），
          范围**恒定**＝原图矩形、不跟变换走（见 :meth:`_base_target_rect`）。
          ⚠️ 旧版正向留着**整张原图**，于是"图转过来了、原来的图还在原地"
          叠着看——用户报的正是这个；再往后一版又把底图跟着旋转外框长大，
          成了"白底一路涨、看着在漂"（同一用户的下一轮报障）。
        * **浮层 = 变换后的选区内容**：拖动中由图元做变换（
          :meth:`_apply_float_fast`，亚毫秒级），松手 / 首次走逐像素重采样
          （:meth:`_render_float_plane`）。旧版把矩阵在"渲染像素"和"图元变换"
          里各套了一次 ⇒ 内容被转了两遍、还被画布边界裁掉一半（用户报的
          "图片不完整显示"）。
        """
        if self._float_item is not None or self._image is None \
                or self._rect is None:
            return
        # ⚠️ 延迟供像素（2026-10-10「切换卡顿」）：恢复会话进工具时只挂了
        #    矩阵和框，upright 反变换（秒级重活）被推迟到这一刻才算——第一
        #    次真正需要像素（建预览 = 第一次拖动/语义入口）时发信号让弹窗
        #    补（带进度框）。补不上（无数据/失败/取消）就整组放弃，退回
        #    普通会话，本方法继续走"从画布选区拍快照"那条路。
        if self._xf_restore_pending:
            if self._xf_restore_region is None:
                self.restore_pixels_requested.emit()
                if self._xf_restore_region is None:
                    self.abort_content_restore()
            self._xf_restore_pending = False
        # ⚠️ 内容节点恢复会话（2026-10-10）：浮层像素源＝sidecar 反变换出的
        #    upright 内容，选区局部矩形＝rect0（upright 整幅）——**画布不动**，
        #    不像普通会话那样从 ``_image`` 拍快照（用户口径「PB1 作为画布，
        #    PA1 作为可操作区域恢复」）。
        restore = self._xf_restore_region
        if restore is not None:
            rect = QRectF(0, 0, restore.width(), restore.height())
            self._xf_region = QImage(restore)
        else:
            rect = self._rect.normalized()
            self._xf_region = self._image.copy(rect.toRect())
        self._xf_rect = QRectF(rect)
        # 预览降采样：浮层像素按预算缩一版（``TRANSFORM_PREVIEW_PIXELS``）。
        # 拖动中这一版**直接**当浮层画布用（不重采样，见 ``_float_fast_plane``），
        # 所以它同时也是"拖动中看到的清晰度"；松手后它是精确档的采样源。
        area = max(1, self._xf_region.width() * self._xf_region.height())
        self._xf_preview_scale = min(
            1.0, math.sqrt(TRANSFORM_PREVIEW_PIXELS / area))
        if self._xf_preview_scale < 0.999:
            self._xf_preview_region = self._xf_region.scaled(
                max(1, int(round(self._xf_region.width()
                                 * self._xf_preview_scale))),
                max(1, int(round(self._xf_region.height()
                                 * self._xf_preview_scale))),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        else:
            self._xf_preview_region = self._xf_region
        self._xf_preview_direction = self._xf_direction
        # 底图＝原图矩形那块的残余（选区擦透明）；范围恒定，不跟变换走
        self._rebuild_backdrop()
        assert self._item is not None
        self._float_item = QGraphicsPixmapItem()
        self._float_item.setTransformationMode(
            Qt.TransformationMode.SmoothTransformation)
        self._float_item.setZValue(5)
        self._scene.addItem(self._float_item)
        self._sync_float()

    def _set_base_pixmap(self) -> None:
        """把 ``_paint_image`` 贴到底图图元上，按 ``_xf_base_origin`` 摆位。

        ``_xf_base_scale`` 非空时额外套一层缩放——整幅选区时底图是**一片空**
        （选区整块被搬走，没有残余可画），用 1×1 透明图拉大即可，不必为每个
        新尺寸新建一张 12 MP 的图。
        """
        assert self._item is not None
        self._item.setPixmap(QPixmap.fromImage(self._paint_image))
        self._item.setPos(self._xf_base_origin)
        scale = self._xf_base_scale
        self._item.setTransform(
            QTransform() if scale is None
            else QTransform().scale(scale.x(), scale.y()))
        self._item.setVisible(True)
