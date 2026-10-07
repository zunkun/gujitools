# -*- coding: utf-8 -*-
"""画布 Mixin：**变换笼**（GIMP 口径：RBF 局部光滑形变）。

从 ``EditorCanvas`` 拆出（2026-10-07）。方法体逐字未改。
"""
from __future__ import annotations

import time
from typing import cast

from PySide6.QtCore import QLineF, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsPixmapItem

from desktop.ui import theme as T
from utils.cage_warp import cage_moved, deform_qimage, perimeter_cage

from ..consts import (
    CAGE_EDGE_BAND_VIEW_PX, CAGE_HANDLE_VIEW_PX, CAGE_HIT_VIEW_PX,
    CAGE_PREVIEW_INTERVAL, CAGE_PREVIEW_PIXELS, CAGE_PREVIEW_SETTLE_PIXELS,
)
from ..geometry import _dist_to_segment, cage_preview_scale
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import CanvasHost
else:
    CanvasHost = object


class CageMixin(CanvasHost):
    """变换笼工具：把手/命中/拖动/预览/覆盖层。"""

    # ---- 「变换笼」（GIMP 口径）----
    #: 笼把手的位置口径与 ``utils.cage_warp`` 一致：``(原位, 当前位置)`` 两个
    #: 序列，闭合顺序。原位 = 进工具时贴图边的矩形；当前位置 = 用户拖到的
    #: 地方（**允许在图外**，往外拖 = 拉伸）。
    def _ensure_cage(self) -> None:
        """（不发信号）没笼时按当前整幅图建一个（贴图边的矩形笼）。"""
        if self._image is None or self._image.isNull():
            self._cage_handles = []
            return
        if self._cage_handles:
            return
        rect = self.image_rect()
        handles = perimeter_cage(
            (rect.left(), rect.top(), rect.right(), rect.bottom()),
            self._cage_per_side)
        # perimeter_cage 给的是单序列 (x, y) 元组（原位）；当前位置初始 = 原位
        self._cage_handles = [
            (QPointF(float(x), float(y)), QPointF(float(x), float(y)))
            for x, y in handles
        ]


    def reset_cage(self) -> None:
        """「重置」：把手回到整幅图原位（丢掉未应用的形变）。"""
        self._clear_cage_preview()
        self._cage_handles = []
        self._cage_drag = None
        self._cage_hover = None
        self._cage_drag_origin = None
        self._ensure_cage()
        self._sync_cage_overlay()
        self._sync_cursor()
        self._refresh_cage_preview(force=True)


    def cage_density(self) -> int:
        """当前每边把手数档位。"""
        return self._cage_per_side


    def set_cage_density(self, per_side: int) -> None:
        """改每边把手数：**重建笼并清掉未应用的形变**（把手序号全变了）。"""
        self._cage_per_side = max(1, int(per_side))
        self.reset_cage()


    def cage(self) -> list:
        """当前把手副本 ``[(原位, 当前位置), ...]``——给自测与外部读。"""
        self._ensure_cage()
        return [(QPointF(a), QPointF(b)) for a, b in self._cage_handles]


    def cage_source(self) -> list[QPointF]:
        """把手**原位**序列（形变映射的左端）。"""
        self._ensure_cage()
        return [QPointF(a) for a, _b in self._cage_handles]


    def cage_target(self) -> list[QPointF]:
        """把手**当前位置**序列（形变映射的右端）。"""
        self._ensure_cage()
        return [QPointF(b) for _a, b in self._cage_handles]


    def cage_pending(self):
        """未应用的笼形变 ``(cage_src, cage_dst)``；没动过返回 ``None``。

        口径与 :meth:`pins_pending` 一致：只有"把手真的动过"才算待应用。
        """
        if self._image is None or self._image.isNull():
            return None
        self._ensure_cage()
        if not self._cage_handles:
            return None
        src = self.cage_source()
        dst = self.cage_target()
        if not cage_moved([(p.x(), p.y()) for p in src],
                          [(p.x(), p.y()) for p in dst]):
            return None
        return src, dst


    def _clamp_cage_pos(self, pos: QPointF) -> QPointF:
        """把手位置夹进「图片矩形 ± 一个图宽」的宽松范围。

        ⚠️ 与 :meth:`pin_move` / :meth:`quad_move` 同口径：允许拖到图外
        （往外＝拉伸），但留一个"一张图那么远"的上限，免得把手被甩到天外、
        再也找不回来。**无上界还会放大两处内存失控**：形变后的画布按落点
        外扩（``grow``），把手飘到几万像素外 ⇒ 画布膨胀几个数量级。
        """
        limit = self.image_rect()
        offset_x, offset_y = limit.width(), limit.height()
        return QPointF(
            max(limit.left() - offset_x, min(pos.x(), limit.right() + offset_x)),
            max(limit.top() - offset_y, min(pos.y(), limit.bottom() + offset_y)))


    def cage_move(self, index: int, pos: QPointF) -> None:
        """把第 ``index`` 个把手拖到 ``pos``（图片坐标，允许图外）。"""
        self._ensure_cage()
        if not (0 <= index < len(self._cage_handles)):
            return
        origin, _cur = self._cage_handles[index]
        self._cage_handles[index] = (origin, self._clamp_cage_pos(pos))
        self._sync_cage_overlay()
        self._refresh_cage_preview()


    def cage_move_all(self, delta: QPointF) -> None:
        """整体平移笼（拖边/拖笼内部）：把所有把手在**按下时的快照**上位移。

        必须基于快照位移，不能逐帧累加——否则每帧都从"当前值"再位移一次，
        手一停位置就漂（浮点累积）。
        """
        if self._cage_drag_origin is None:
            return
        _start, snapshot = self._cage_drag_origin
        self._cage_handles = [
            (a, self._clamp_cage_pos(QPointF(b.x() + delta.x(), b.y() + delta.y())))
            for a, b in snapshot]
        self._sync_cage_overlay()
        self._refresh_cage_preview()


    def _hit_cage_handle(self, view_point: QPointF) -> int | None:
        """命中哪个把手（视口坐标，按当前倍率换算命中半径）。"""
        if not self._cage_handles:
            return None
        radius = CAGE_HIT_VIEW_PX
        best, best_d2 = None, radius * radius
        for i, (_origin, cur) in enumerate(self._cage_handles):
            vp = QPointF(self.mapFromScene(cur))
            d2 = (vp.x() - view_point.x()) ** 2 + (vp.y() - view_point.y()) ** 2
            if d2 <= best_d2:
                best, best_d2 = i, d2
        return best


    def _hit_cage_body(self, scene_point: QPointF) -> bool:
        """命中笼内部/边（用于整体平移）。用原位上构建的多边形判定。"""
        if not self._cage_handles:
            return False
        poly = QPolygonF([a for a, _b in self._cage_handles])
        if poly.containsPoint(scene_point, Qt.FillRule.OddEvenFill):
            return True
        # 边缘带宽：到任一条边的距离在阈值内也算（贴着边拖更好抓）
        tol = CAGE_EDGE_BAND_VIEW_PX / max(1e-6, self._zoom)
        # ⚠️ 边遍历直接用 _cage_handles（``poly`` 就是由它构造的）：QPolygonF
        #    没有 __len__/__getitem__/可迭代的注解，走 points = list(poly) 那条
        #    路要靠"运行时靠鸭子类型"（PySide6 确实支持，但注解里没有）。
        points = [a for a, _b in self._cage_handles]
        n = len(points)
        for i in range(n):
            a, b = points[i], points[(i + 1) % n]
            if _dist_to_segment(scene_point, a, b) <= tol:
                return True
        return False


    def _clear_cage_preview(self) -> None:
        """丢掉变换笼的像素预览浮层，并把节流时间戳一并清零。

        与 :meth:`_clear_deform_preview` 同理：清预览 = 「已经没有待应用的
        形变了」，下一次拖动是全新一轮，必须立刻出画（否则重置/应用后紧接着
        拖的第一次会被节流窗口吃掉）。
        """
        self._cage_preview_at = 0.0
        if self._cage_preview_item is not None:
            self._scene.removeItem(self._cage_preview_item)
            self._cage_preview_item = None
        # ⚠️ 同 :meth:`_clear_deform_preview`：底图上被挖空的框必须回填，
        #    否则预览浮层没了、原图却留着个白洞。
        if self._preview_cutout is not None:
            self._paint_canvas_cutout(None)
        # 浮层没了 → 场景矩形收回图片边界（grow 时曾为图外内容扩过）
        self._sync_scene_rect()


    def _refresh_cage_preview(self, force: bool = False) -> None:
        """重算变换笼的像素预览浮层。

        与 :meth:`_refresh_deform_preview` 同构：

        - **范围**：``grow=True`` 时形变结果可能落到原图边界**之外**，所以预览
          按**整幅图**降采样后整体重算（:func:`deform_qimage` 的 grow 模式），
          浮层覆盖"原图 ∪ 图外内容"；底图整张挖空，由浮层完整呈现（用户
          2026-10-02：「超出原本区域的不要截，最终结果按最后图片的范围」）。
          场景矩形同步扩到浮层范围，图外那块才看得见；
        - **分辨率**：按 :func:`cage_preview_scale` 降采样，拖动中取
          :data:`CAGE_PREVIEW_PIXELS`，``force``（松手）取
          :data:`CAGE_PREVIEW_SETTLE_PIXELS`；
        - **时间**：:data:`CAGE_PREVIEW_INTERVAL` 之内不重复算（``force`` 跳过）。

        笼把手（覆盖层）每帧都跟手，与这里的节拍无关。
        """
        if self._image is None or not self._cage_handles:
            self._clear_cage_preview()
            return
        src = self.cage_source()
        dst = self.cage_target()
        src_xy = [(p.x(), p.y()) for p in src]
        dst_xy = [(p.x(), p.y()) for p in dst]
        if not cage_moved(src_xy, dst_xy):
            self._clear_cage_preview()
            return
        now = time.monotonic()
        if not force and now - self._cage_preview_at < CAGE_PREVIEW_INTERVAL:
            return
        width, height = self._image.width(), self._image.height()
        # grow 后内容可能落到原边界之外，预览也必须把外面那块画出来（否则
        # 松手落地时"画面突然多出一块"，与预览对不上）。所以这里按**整幅图**
        # 的预算降采样（同 deform），而不是只算影响框。
        scale = cage_preview_scale(
            width, height,
            self._zoom * max(1.0, self.devicePixelRatioF()),
            CAGE_PREVIEW_SETTLE_PIXELS if force else CAGE_PREVIEW_PIXELS)
        scale = min(1.0, scale)
        if scale >= 1.0:
            source = self._image
            src_s = [(p.x(), p.y()) for p in src]
            dst_s = [(p.x(), p.y()) for p in dst]
        else:
            source = self._image.scaled(
                max(1, int(round(width * scale))),
                max(1, int(round(height * scale))),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            src_s = [(p.x() * scale, p.y() * scale) for p in src]
            dst_s = [(p.x() * scale, p.y() * scale) for p in dst]
        # grow=True 恒返回 (QImage, (ox, oy)) 二元组；deform_qimage 刻意不加返回
        # 注解（多形态返回），故此处 cast 收窄以便解包。
        preview, origin_s = cast(
            "tuple[QImage, tuple[float, float]]",
            deform_qimage(source, src_s, dst_s, grow=True))
        if preview is None or preview.isNull():
            self._clear_cage_preview()
            return
        pixmap = QPixmap.fromImage(preview)
        pixmap.setDevicePixelRatio(1.0)
        if self._cage_preview_item is None:
            self._cage_preview_item = QGraphicsPixmapItem()
            self._cage_preview_item.setZValue(4)  # 底图之上、覆盖层（11+）之下
            self._cage_preview_item.setTransformationMode(
                Qt.TransformationMode.SmoothTransformation)
            self._scene.addItem(self._cage_preview_item)
        self._cage_preview_item.setPixmap(pixmap)
        self._cage_preview_item.setPos(origin_s[0] / scale, origin_s[1] / scale)
        self._cage_preview_item.setScale(1.0 / scale)
        # ⚠️ 底图上把**原图整块**挖空：形变结果（含图外那块）由浮层完整呈现，
        #    底图若不挖空，原内容会从浮层底下透出来（用户 2026-10-02 报的重影）。
        #    grow 后浮层覆盖范围 ≥ 原图，所以直接挖整张原图即可。
        self._paint_canvas_cutout(QRect(0, 0, width, height))
        # 场景矩形要扩到"原图 ∪ 浮层"：否则图外那块内容被视口裁掉、看不见
        # （用户 2026-10-02：超出原边界的内容不能丢——预览也要看得见）。
        self._sync_scene_rect()
        self._cage_preview_at = now


    # ---- 「变换笼」的覆盖层 ----
    def _sync_cage_overlay(self) -> None:
        """变换笼的覆盖层：原位虚点线 + 当前位置虚线 + 把手圆点。

        与变形/变换/校正的覆盖层互斥（:meth:`_sync_overlay` 早返回），所以
        这里先把那些元素全部藏掉，再画自己的。
        """
        for item in self._mask:
            item.setVisible(False)
        self._sel_border.setVisible(False)
        self._quad.setVisible(False)
        self._pivot_item.setVisible(False)
        for item in self._handles.values():
            item.setVisible(False)
        for item in self._edge_lines.values():
            item.setVisible(False)
        self._sync_cage_dots()


    def _sync_cage_dots(self) -> None:
        """按把手数增删/摆放圆点与两条闭合折线（视觉尺寸 = 视图像素 ÷ 倍率）。

        悬停/拖动中的把手放大一圈：抓没抓住看圆点大小就知道。原位（笼贴图
        边的矩形）画点线、当前位置画虚线——拖出去之后一眼能看出内容是从哪
        儿被扯过来的（RBF 笼的影响半径围绕原位，与 puppet warp 语义相同）。
        """
        self._ensure_cage()
        zoom = max(self._zoom, 1e-6)
        base = CAGE_HANDLE_VIEW_PX / 2.0 / zoom
        hovered = base * 1.5
        while len(self._cage_dots) < len(self._cage_handles):
            item = QGraphicsEllipseItem()
            item.setPen(QPen(QColor("#ffffff"), 0))
            item.setZValue(13)
            self._scene.addItem(item)
            self._cage_dots.append(item)
        while len(self._cage_dots) > len(self._cage_handles):
            self._scene.removeItem(self._cage_dots.pop())
        src_path = QPainterPath()
        dst_path = QPainterPath()
        src_pts = [a for a, _b in self._cage_handles]
        dst_pts = [b for _a, b in self._cage_handles]
        if src_pts:
            src_path.moveTo(src_pts[0])
            dst_path.moveTo(dst_pts[0])
            for pt in src_pts[1:]:
                src_path.lineTo(pt)
            for pt in dst_pts[1:]:
                dst_path.lineTo(pt)
            src_path.closeSubpath()
            dst_path.closeSubpath()
        self._cage_src_poly.setPath(src_path)
        self._cage_dst_poly.setPath(dst_path)
        moved = any(QLineF(a, b).length() > 1e-6
                    for a, b in self._cage_handles)
        self._cage_src_poly.setVisible(bool(src_pts) and moved)
        self._cage_dst_poly.setVisible(bool(dst_pts))
        for index, (_origin, point) in enumerate(self._cage_handles):
            item = self._cage_dots[index]
            big = (index == self._cage_hover) or (index == self._cage_drag)
            radius = hovered if big else base
            item.setRect(QRectF(point.x() - radius, point.y() - radius,
                                radius * 2, radius * 2))
            item.setBrush(QBrush(QColor(T.ACCENT_HOVER if big else T.ACCENT)))
            item.setVisible(True)
