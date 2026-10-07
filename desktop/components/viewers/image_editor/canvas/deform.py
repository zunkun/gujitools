# -*- coding: utf-8 -*-
"""画布 Mixin：**操控变形**（PS 口径：ARAP 三角网格 + 图钉）。

从 ``EditorCanvas`` 拆出（2026-10-07）。方法体逐字未改。
"""
from __future__ import annotations

import time

from PySide6.QtCore import QLineF, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsPixmapItem

from desktop.ui import theme as T
from utils.puppet_warp import (
    ARAP_DRAG_ITERATIONS, ARAP_DRAG_TOLERANCE, build_mesh, drag_cell, grid_cell,
    mesh_moved, nearest_vertex, solve_puppet,
)

from ..consts import (
    DEFORM_PREVIEW_INTERVAL, DEFORM_PREVIEW_PIXELS, DEFORM_PREVIEW_SETTLE_PIXELS,
    PIN_HIT_VIEW_PX, PIN_NODE_VIEW_PX,
)
from ..geometry import bake_puppet, cage_preview_scale
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import CanvasHost
else:
    CanvasHost = object


class DeformMixin(CanvasHost):
    """变形工具：网格/图钉/解算/预览/覆盖层。"""

    # ------------------------------------------------------------ 变形（操控变形）
    # 口径与算法见 utils/puppet_warp.py 的模块文档。画布这边只负责：
    #   ① 维护图钉列表（点加、拖移、Alt/右键删）；
    #   ② 把图钉交给 solve_puppet 解出**形变后的网格顶点**；
    #   ③ 拖动时按 DEFORM_PREVIEW_PIXELS 降采样出**像素预览**（全分辨率太慢）；
    #   ④ 覆盖层（图钉）每帧跟手，覆盖层本身不碰像素。
    def mesh_density(self) -> float:
        """当前网格格距（图片像素档位）。"""
        return self._mesh_cell


    def set_mesh_density(self, cell: float) -> None:
        """改网格格距：**重建网格并清空图钉**（顶点下标全变了，旧钉无意义）。"""
        self._mesh_cell = float(cell)
        self.reset_pins()


    def _ensure_mesh(self) -> None:
        """（不发信号）按当前图片与格距建网格；已建且尺寸/格距没变就复用。"""
        if self._image is None or self._image.isNull():
            self._mesh = None
            return
        width, height = self._image.width(), self._image.height()
        cell = grid_cell(width, height, self._mesh_cell)
        if self._mesh is not None and self._mesh[4] == cell \
                and self._mesh[0].shape[0] > 0:
            return
        self._mesh = build_mesh(width, height, self._mesh_cell)
        self._mesh_moved = None
        self._drag_cache = None   # 网格变了，粗网格缓存一并失效
        self._pins = []
        self._pin_hover = None


    def reset_pins(self) -> None:
        """「重置」：清空所有图钉，丢掉未应用的形变（网格本身保留）。"""
        self._clear_deform_preview()
        self._mesh = None
        self._mesh_moved = None
        self._pins = []
        self._pin_hover = None
        self._ensure_mesh()
        self._sync_overlay()
        self._sync_cursor()


    def pins(self) -> list:
        """当前图钉的副本（``(顶点下标, QPointF)`` 列表）——给自测与外部读。"""
        return [(index, QPointF(point)) for index, point in self._pins]


    def pin_count(self) -> int:
        """当前图钉个数。"""
        return len(self._pins)


    def _solve_pins(self, *, drag: bool = False):
        """按当前图钉解一次 ARAP，返回 ``(vertices_rest, vertices_moved)``。

        没图钉、或图钉全都还在原位上 ⇒ 返回 ``None``（形变 = 恒等，调用方
        据此跳过重采样——这保证了"没钉就逐字节等于原图"）。

        ⚠️ **``drag=True`` 时用"粗网格 + 少迭代"求一个跟手的近似解**：
        ARAP 的解算耗时随顶点数**超线性**增长（实测 7676 顶点 2.1s、
        1989 顶点 0.26s、520 顶点 0.07s），而拖动每次鼠标移动都要重解 ——
        大图上用精网格根本不可能跟手，用户看到的就是"卡死"。粗网格解出的
        是同一根形变"趋势"，松手后再用精网格解到精细（见
        :func:`utils.puppet_warp.drag_cell`，它同时卡"相对倍数"和"顶点数
        绝对上限"两道）。

        像素重采样不在这里做，由 :meth:`_refresh_deform_preview` /
        :func:`bake_puppet` 走。
        """
        if self._mesh is None or self._image is None:
            return None
        if not self._pins:
            return None
        width, height = self._image.width(), self._image.height()
        mesh = self._drag_mesh() if drag else self._mesh
        if mesh is None:
            return None
        vertices, triangles = mesh[0], mesh[1]
        # 图钉按**图片坐标**存，落到哪张网格就吸附到哪张网格的顶点
        targets = []
        for _vertex, point in self._pins:
            k = nearest_vertex(vertices, (point.x(), point.y()))
            targets.append((int(k), (point.x(), point.y())))
        kwargs = {}
        if drag:
            kwargs = {"iterations": ARAP_DRAG_ITERATIONS,
                      "tolerance": ARAP_DRAG_TOLERANCE}
        try:
            moved = solve_puppet(vertices, triangles, targets,
                                 width=width, height=height, **kwargs)
        except Exception:
            # 解算失败（奇异/退化）时退化为恒等，绝不把画布搞崩
            return None
        return vertices, moved, triangles


    def _drag_mesh(self):
        """拖动预览用的**粗网格**（:func:`drag_cell` 给出格距），缓存。

        返回 ``(vertices, triangles, cols, rows, cell)``；格距同时受"相对
        粗化倍数"和"顶点数上限"两条约束（见 ``utils.puppet_warp.drag_cell``）。
        """
        if self._image is None:
            return None
        width, height = self._image.width(), self._image.height()
        cell = drag_cell(width, height, self._mesh_cell)
        if self._drag_cache is not None and self._drag_cache[4] == cell:
            return self._drag_cache
        self._drag_cache = build_mesh(width, height, cell)
        return self._drag_cache


    def pin_add(self, pos: QPointF) -> int | None:
        """在 ``pos``（图片坐标）加一个图钉，返回它在 ``_pins`` 里的下标。

        图钉**吸附到最近的网格顶点**（ARAP 的硬约束只能钉在顶点上）；同一
        顶点已有图钉时不再重复加，直接返回已有的那个。
        """
        self._ensure_mesh()
        if self._mesh is None:
            return None
        vertices = self._mesh[0]
        vertex = nearest_vertex(vertices, (pos.x(), pos.y()))
        for index, (existing, _point) in enumerate(self._pins):
            if existing == vertex:
                return index
        self._pins.append((vertex, QPointF(float(vertices[vertex, 0]),
                                           float(vertices[vertex, 1]))))
        self._clear_deform_preview()
        self._sync_overlay()
        return len(self._pins) - 1


    def pin_remove(self, index: int) -> None:
        """删掉第 ``index`` 个图钉（形变随之重解）。"""
        if not 0 <= index < len(self._pins):
            return
        self._pins.pop(index)
        self._pin_hover = None
        self._clear_deform_preview()
        self._refresh_deform_preview(force=True)
        self._sync_overlay()


    def pin_move(self, index: int, pos: QPointF) -> None:
        """把第 ``index`` 个图钉拖到 ``pos``（图片坐标）。

        ⚠️ **允许拖到图片外面**（用户 2026-10-01：「任意点只能向内，不能向外」）。
        往外拖＝把那块内容往外**拉伸**，拉出画布的部分按越界填底。这里只留一个
        "一张图那么远"的宽松上限，免得图钉被甩到天外、再也找不回来。
        """
        if not 0 <= index < len(self._pins):
            return
        limit = self.image_rect()
        offset_x, offset_y = limit.width(), limit.height()
        clamped = QPointF(
            max(limit.left() - offset_x,
                min(pos.x(), limit.right() + offset_x)),
            max(limit.top() - offset_y,
                min(pos.y(), limit.bottom() + offset_y)))
        vertex, _old = self._pins[index]
        self._pins[index] = (vertex, clamped)
        self._pin_hover = index  # 拖着的这个保持放大高亮
        self._sync_overlay()
        self._refresh_deform_preview()


    def _hit_pin(self, view_pos: QPointF) -> int | None:
        """命中图钉（视图像素口径，不随缩放变）。"""
        for index, (_vertex, point) in enumerate(self._pins):
            spot = QPointF(self.mapFromScene(point))
            if QLineF(view_pos, spot).length() <= PIN_HIT_VIEW_PX:
                return index
        return None


    def pins_pending(self):
        """未应用的形变 ``(vertices_rest, vertices_moved, triangles)``；无则 None。

        「未应用」= 解出的网格确实动过。全都没动时返回 None，调用方据此
        跳过烘焙（不产生多余的撤销点）。
        """
        solved = self._solve_pins()
        if solved is None:
            return None
        vertices, moved, triangles = solved
        if not mesh_moved(vertices, moved):
            return None
        return (vertices, moved, triangles)


    def adopt_pins(self, pin_vertices=None) -> None:
        """「应用变形」后用：把图钉**原地保留**（目标位置 = 新网格的原位）。

        ⚠️ 为什么不清空：古籍褶皱往往要来回试几次，每次应用后都清空图钉的话
        用户得重新钉一遍。保留图钉、并让它们落在**刚烘焙完的图**的原位，
        就可以接着微调同一块。

        ⚠️ ``pin_vertices`` 必须由调用方在 ``set_image`` **之前**快照传入：
        :meth:`set_image` 换图时会把 ``_pins`` 清空（换图后旧钉无意义），
        所以这里不能指望调用时 ``self._pins`` 还在。传 ``None`` 时退回读
        当前 ``self._pins``（兼容直接调用）。
        """
        self._clear_deform_preview()
        self._mesh = None
        self._mesh_moved = None
        self._ensure_mesh()   # 重建网格（图片没变，格距没变 → 复用/重建都行）
        if self._mesh is not None:
            vertices = self._mesh[0]
            source = self._pins if pin_vertices is None else pin_vertices
            self._pins = [
                (vertex, QPointF(float(vertices[vertex, 0]),
                                 float(vertices[vertex, 1])))
                for vertex, _point in source
                if 0 <= vertex < len(vertices)
            ]
        self._sync_overlay()


    # ---- 像素预览（降采样 + 节流） ----
    def _clear_deform_preview(self) -> None:
        """丢掉像素预览浮层，并把节流时间戳一并清零。

        ⚠️ 清预览 = 「已经没有待应用的形变了」，所以下一次拖动是**全新的一轮**，
        必须立刻出画。若只删浮层、留下 ``_deform_painted_at``，那么刚
        「重置 / 应用变形 / 采用图钉」完紧接着拖的**第一次**会被
        :data:`DEFORM_PREVIEW_INTERVAL` 的窗口吃掉——用户拖了半天画面一动不动，
        松开手才突然跳出来（真实踩到：这就是 ``fit()`` 空转那一类，见
        :meth:`_refresh_deform_preview` 的注释；这里把 reset/adopt 这条路径也堵上）。
        """
        self._deform_painted_at = 0.0
        if self._deform_item is not None:
            self._scene.removeItem(self._deform_item)
            self._deform_item = None
        # ⚠️ 底图上被挖空的框必须回填：不清的话预览浮层没了、原图却留着个
        #    白洞（用户会看到"图被啃掉一块"）。
        if self._preview_cutout is not None:
            self._paint_canvas_cutout(None)
        # 浮层没了 → 场景矩形收回图片边界（grow 时曾为图外内容扩过）
        self._sync_scene_rect()


    def _refresh_deform_preview(self, force: bool = False) -> None:
        """重算"形变后"的像素预览（浮层）。

        ⚠️ 两重降本（缺一不可）：形变是逐像素重映射，源图是整页 4000×3000
        时全分辨率一次要秒级（实测见 ``utils.puppet_warp``）。

        - **分辨率**：按 :func:`cage_preview_scale` 降采样——它同时卡"屏幕
          上够清楚"和"工作量有上限"。拖动中取 :data:`DEFORM_PREVIEW_PIXELS`
          （~80ms），``force`` 时取 :data:`DEFORM_PREVIEW_SETTLE_PIXELS`
          （松手了，停下来看清楚）。⚠️ 预算按**整幅图**面积算，因为下面
          ``bake_puppet`` 是拿整张降采样图做的映射；
        - **时间**：:data:`DEFORM_PREVIEW_INTERVAL` 之内不重复算（``force`` 跳过）。

        ⚠️ ``grow=True``：ARAP 网格被拖出原边界时预览**整体重算并显示图外
        那块**——不再按 :func:`mesh_region` 裁框（ARAP 的位移场缓慢衰减、
        整图 96~98% 受影响，裁框只省 ~4%，见 ``utils.puppet_warp``）。浮层
        覆盖"原图 ∪ 图外内容"，底图整张挖空，场景矩形同步扩大。

        图钉（覆盖层）每帧都跟手，与这里的节拍无关。
        """
        if self._tool == "rectify":
            self._refresh_rectify_preview(force=force)
            return
        if self._image is None or self._mesh is None or not self._pins:
            return
        now = time.monotonic()
        if not force and now - self._deform_painted_at < DEFORM_PREVIEW_INTERVAL:
            return
        # force（松手补帧）用精网格解到收敛；拖动中用粗网格近似解（跟手）
        solved = self._solve_pins(drag=not force)
        if solved is None:
            # 没干活就不算"刚画过"：``_clear_deform_preview`` 会把时间戳清零，
            # 否则紧接着的第一次真拖动会被节流窗口吃掉，用户拖了半天画面
            # 一动不动（真实踩到：fit() 里的空转把时间戳刷成了"刚画"）。
            self._clear_deform_preview()
            return
        vertices, moved, triangles = solved
        if not mesh_moved(vertices, moved):
            self._clear_deform_preview()
            return
        width, height = self._image.width(), self._image.height()

        # 场景 1 单位 = 屏幕上 zoom × dpr 个设备像素（见 cage_preview_scale）。
        # ⚠️ 成本预算按**整幅图**的面积算，不是按 mesh_region 的框——因为
        #    bake_puppet 是拿**整张降采样图**去做的映射（不是只处理框内），
        #    所以真实工作量 = width×height×scale²。早前按框面积算，预算
        #    20 万实际会重映射到 27 万（框只占整图 ~95% 也差这么多，因为
        #    scale 被同时乘到了整幅），实测帧时间比预期高 30%（自测/基准
        #    逮到）。这里显式按整图面积给出 scale。
        scale = cage_preview_scale(
            width, height,
            self._zoom * max(1.0, self.devicePixelRatioF()),
            DEFORM_PREVIEW_SETTLE_PIXELS if force else DEFORM_PREVIEW_PIXELS)
        if scale >= 1.0:
            source = self._image
        else:
            source = self._image.scaled(
                max(1, int(round(width * scale))),
                max(1, int(round(height * scale))),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        # grow：图钉被拖出原边界时预览也要把外面那块画出来（否则松手落地
        # 时"画面突然多出一块"，与预览对不上）。
        warped, origin_s = bake_puppet(source, vertices * scale, moved * scale,
                                       triangles, grow=True)
        if warped is None or warped.isNull():
            self._clear_deform_preview()
            return
        pixmap = QPixmap.fromImage(warped)
        pixmap.setDevicePixelRatio(1.0)
        if self._deform_item is None:
            self._deform_item = QGraphicsPixmapItem()
            self._deform_item.setZValue(4)  # 底图之上、覆盖层（11+）之下
            self._deform_item.setTransformationMode(
                Qt.TransformationMode.SmoothTransformation)
            self._scene.addItem(self._deform_item)
        self._deform_item.setPixmap(pixmap)
        self._deform_item.setPos(origin_s[0] / scale, origin_s[1] / scale)
        self._deform_item.setScale(1.0 / scale)
        # ⚠️ 底图上把**整张原图**挖空：grow 后浮层覆盖范围 ≥ 原图，由浮层
        #    完整呈现（含图外那块）；不挖空的话原像素会从浮层底下透出来
        #    （"图片变换了，原图还在背景上面"）。
        self._paint_canvas_cutout(QRect(0, 0, width, height))
        # 场景矩形扩到"原图 ∪ 浮层"，图外那块才看得见
        self._sync_scene_rect()
        self._deform_painted_at = now


    # ---- 「变形」的覆盖层 ----
    def _sync_pin_overlay(self) -> None:
        """变形工具的覆盖层：图钉圆点 + 原点连线。

        与变换/裁剪的覆盖层互斥（:meth:`_sync_overlay` 早返回），所以这里
        先把那些元素全部藏掉，再画自己的。
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
        self._sync_pin_dots()


    def _sync_pin_dots(self) -> None:
        """按图钉数增删/摆放圆点与连线（视觉尺寸 = 视图像素 ÷ 当前倍率）。

        悬停/拖动中的图钉放大一圈：抓没抓住看圆点大小就知道。
        图钉的**原点**（网格参考顶点位置）与当前位置不同时，画一根点线相连
        ——把图钉拖远后才看得出内容是从哪儿被扯过来的。
        """
        zoom = max(self._zoom, 1e-6)
        base = PIN_NODE_VIEW_PX / 2.0 / zoom
        hovered = base * 1.5
        while len(self._pin_dots) < len(self._pins):
            item = QGraphicsEllipseItem()
            item.setZValue(13)
            self._scene.addItem(item)
            self._pin_dots.append(item)
        while len(self._pin_dots) > len(self._pins):
            self._scene.removeItem(self._pin_dots.pop())
        tail_path = QPainterPath()
        vertices = self._mesh[0] if self._mesh is not None else None
        any_tail = False
        for index, (vertex, point) in enumerate(self._pins):
            item = self._pin_dots[index]
            big = (index == self._pin_hover)
            radius = hovered if big else base
            item.setRect(QRectF(point.x() - radius, point.y() - radius,
                                radius * 2, radius * 2))
            item.setBrush(QBrush(QColor(T.ACCENT_HOVER if big else T.ACCENT)))
            item.setPen(QPen(QColor("#ffffff"), 0))
            item.setVisible(True)
            if vertices is not None and 0 <= vertex < len(vertices):
                origin = QPointF(float(vertices[vertex, 0]),
                                 float(vertices[vertex, 1]))
                if QLineF(origin, point).length() > 1e-6:
                    tail_path.moveTo(origin)
                    tail_path.lineTo(point)
                    any_tail = True
        self._pin_tail.setPath(tail_path)
        self._pin_tail.setVisible(any_tail)
