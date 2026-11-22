# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""统一变换：手柄局部几何与焦点环。"""
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



class TransformHandlesMixin(CanvasHost):
    """统一变换：手柄局部几何与焦点环。"""


    # ------------------------------------------------------------ 手柄几何
    def _transform_local_rect(self) -> QRectF | None:
        """变换对象矩形（原图坐标）：拖起来之后是锁定快照，之前是当前选区。"""
        rect = self._xf_rect if self._xf_rect is not None else self._rect
        return None if rect is None else rect.normalized()

    def _transform_local_corners(self) -> list[QPointF]:
        """四个角在**原图坐标**里的位置，顺序 = ``tl/tr/br/bl``。"""
        rect = self._transform_local_rect()
        assert rect is not None          # 调用方都已判过选区非空
        return [rect.topLeft(), rect.topRight(),
                rect.bottomRight(), rect.bottomLeft()]

    def _transform_local_handles(self) -> dict[str, QPointF]:
        """全部手柄在**原图坐标**里的位置（透视小菱形不含偏置，见下）。"""
        rect = self._transform_local_rect()
        assert rect is not None
        width, height = rect.width(), rect.height()

        def at(u: float, v: float) -> QPointF:
            return QPointF(rect.x() + width * u, rect.y() + height * v)

        points = {name: at(*uv) for name, uv in _CORNER_UV.items()}
        for name, (u, v) in (("t", (0.5, 0.0)), ("b", (0.5, 1.0)),
                             ("l", (0.0, 0.5)), ("r", (1.0, 0.5))):
            points[name] = at(u, v)
        # 每边 1 个切变菱形，参数化起点 = 该边"顺时针那侧"的角（见 consts.SHEAR_AT）
        for edge, param in _EDGE_UV.items():
            points[f"s_{edge}"] = at(*param(SHEAR_AT))
        return points

    def _transform_handle_points(self) -> dict[str, QPointF]:
        """全部手柄的**场景坐标**（= 原图坐标经 ``_xf``）。

        透视小菱形按 ``PERSP_INSET_VIEW_PX`` 沿"框内对角线"偏置——现在是
        **0（与角方框同心）**，用户 2026-10-09 口径：「四个边角的菱形要在方块
        正中心」。偏置量除以当前倍率，缩放到任何倍率下视觉大小都一致。
        """
        world = {name: self._visual_xf().map(point)
                 for name, point in self._transform_local_handles().items()}
        if PERSP_INSET_VIEW_PX > 0.0:
            # 只有需要微调偏心时才走这段（见 consts 该常量的说明）；同心时
            # 菱形中心直接就是角点，不绕这一圈。
            inset = PERSP_INSET_VIEW_PX / max(self._zoom, 1e-6)
            for key in CORNER_HANDLES:
                corner = world[key]
                direction = QPointF(0.0, 0.0)
                for neighbour in _CORNER_NEIGHBOURS[key]:
                    step = world[neighbour] - corner
                    length = math.hypot(step.x(), step.y())
                    if length > 1e-6:
                        direction += QPointF(step.x() / length, step.y() / length)
                length = math.hypot(direction.x(), direction.y())
                if length > 1e-9:
                    direction = QPointF(direction.x() / length,
                                        direction.y() / length) * inset
                world[f"p_{key}"] = corner + direction
        else:
            for key in CORNER_HANDLES:
                world[f"p_{key}"] = world[key]
        return world

    def _edge_handles_active(self, corners: dict[str, QPointF] | None = None
                             ) -> bool:
        """边上的方框/菱形这份要不要"接管"命中（框太小就只留角手柄）。

        框在屏幕上比手柄还小时，4 个缩放方框 + 8 个切变菱形会糊成一团，
        随便一按就把内容斜掉——那种情况下只保留角手柄 + 框内移动。
        """
        if corners is None:
            corners = self._transform_quad()
        view = [QPointF(self.mapFromScene(corners[key]))
                for key in CORNER_HANDLES]
        lengths = [QLineF(view[index], view[(index + 1) % 4]).length()
                   for index in range(4)]
        return min(lengths) >= EDGE_HANDLE_MIN_VIEW_PX

    def _transform_quad(self) -> dict[str, QPointF]:
        """变换后选区四角（图片坐标）：手柄几何与命中测试的几何来源。

        ⚠️ 用**视觉矩阵**（:meth:`_visual_xf`）而不是 ``_xf``：校正（向后）
        模式下框必须跟浮层内容同向（内容走 ``_preview_xf``），否则
        「图片和操作框方向相反」。
        """
        rect = self._transform_local_rect()
        assert rect is not None
        xf = self._visual_xf()
        return {
            "tl": xf.map(rect.topLeft()), "tr": xf.map(rect.topRight()),
            "br": xf.map(rect.bottomRight()), "bl": xf.map(rect.bottomLeft()),
        }

    # ------------------------------------------------------------ 节点高亮
    def _set_handle_focus(self, name: str | None) -> None:
        """把"当前节点"换成 ``name``（``None`` = 谁都不亮）。

        这是"点哪个节点、哪个节点亮"的唯一入口：悬停（``_update_hover_cursor``）
        与按下（``_begin_transform_drag``）都走它，所以**悬停与激活是同一套
        状态**，不会出现"按下了却高亮在别处"。变的时候才推一次覆盖层。
        """
        if name == self._focus_handle:
            return
        self._focus_handle = name
        if self._tool == "transform" and not self._xf_reshape:
            self._sync_overlay()
