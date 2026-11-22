# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""画布几何：页面 mm ↔ 控件像素换算、旋转外接框、手柄/命中区。"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QImage

from desktop.utils.image_scaling import smooth_downscale
from utils.page_layout import normalize_page_rotation, rotated_bbox_size

from .constants import (
    DISPLAY_IMAGE_EDGE,
    EDGE_HIT_PX,
    HANDLE_RADIUS,
    ROTATE_KNOB_GAP,
    ROTATE_KNOB_HIT,
)

if TYPE_CHECKING:
    from ._host import PrintLayoutCanvasHost
else:
    PrintLayoutCanvasHost = object


class GeometryMixin(PrintLayoutCanvasHost):
    """坐标换算与旋转几何（页面 mm、左上原点）。"""

    # ---------------------------------------------------------------- 旋转几何
    def _content_size_mm(self, rect, angle) -> tuple[float, float]:
        """由「旋转后的外接框 + 朝向」反推**未旋转内容**的宽高（mm）。

        用源图宽高比约束（框通常就是按它摆的）：内容等比落在框内，
        旋转到任何角度都不会把图片拉伸变形。框被自由拉成别的比例时按
        "完整放进框"取较小的一档，预览与 PDF 同样少一点而不裁掉内容。
        """
        box_w, box_h = float(rect[2]), float(rect[3])
        image = self._image
        if image is None or image.isNull() or image.height() <= 0:
            return box_w, box_h
        aspect = image.width() / image.height()
        rad = math.radians(normalize_page_rotation(angle))
        cos_v, sin_v = abs(math.cos(rad)), abs(math.sin(rad))
        content_w = min(
            aspect * box_w / (aspect * cos_v + sin_v),
            aspect * box_h / (aspect * sin_v + cos_v),
        )
        return content_w, content_w / aspect

    def _bbox_for_content(self, content, angle) -> list[float]:
        """内容尺寸 + 朝向 → 居中的外接框（超出纸张时等比缩回页内）。"""
        content_w, content_h = content
        bbox_w, bbox_h = rotated_bbox_size(content_w, content_h, angle)
        scale = min(
            1.0,
            self._page_w_mm / bbox_w if bbox_w > 0 else 1.0,
            self._page_h_mm / bbox_h if bbox_h > 0 else 1.0,
        )
        bbox_w, bbox_h = bbox_w * scale, bbox_h * scale
        center = self._rect_center_mm()
        nx = min(max(center[0] - bbox_w / 2.0, 0.0),
                 max(0.0, self._page_w_mm - bbox_w))
        ny = min(max(center[1] - bbox_h / 2.0, 0.0),
                 max(0.0, self._page_h_mm - bbox_h))
        return [nx, ny, bbox_w, bbox_h]

    def _rect_center_mm(self) -> tuple[float, float]:
        x, y, w, h = self._rect_mm
        return x + w / 2.0, y + h / 2.0

    def _display_image_for(self) -> QImage | None:
        """贴图用的底图：源图平滑缩到 ``DISPLAY_IMAGE_EDGE`` 以内（换图才重算）。

        拖拽/缩放/旋转期间 ``_rect_mm`` 每帧在变，但**不参与**缓存键——底图按
        整页可能的最大显示尺寸准备（图片框被夹在页面内，不会比整页更大），
        所以拖框时零重采样；旋转是 QPainter 变换，同样不重采样位图。
        """
        source = self._image
        if source is None or source.isNull():
            return None
        if source is self._display_source:
            return self._display_image
        self._display_source = source
        self._display_image = smooth_downscale(source, DISPLAY_IMAGE_EDGE)
        return self._display_image

    # ------------------------------------------------------------------ 坐标
    def _recompute(self) -> None:
        avail_w = self.width() - 2 * self._pad
        avail_h = self.height() - 2 * self._pad
        if (avail_w <= 0 or avail_h <= 0
                or self._page_w_mm <= 0 or self._page_h_mm <= 0):
            self._px_per_mm = 1.0
            self._off_x = float(self._pad)
            self._off_y = float(self._pad)
            return
        # 等比缩放：整页（含留白）刚好放进可视区
        self._px_per_mm = min(
            avail_w / self._page_w_mm, avail_h / self._page_h_mm
        )
        page_px_w = self._page_w_mm * self._px_per_mm
        page_px_h = self._page_h_mm * self._px_per_mm
        self._off_x = (self.width() - page_px_w) / 2
        self._off_y = (self.height() - page_px_h) / 2

    def _to_mm(self, pos: QPointF) -> tuple[float, float]:
        """控件坐标 → 页面 mm 坐标。"""
        return (
            (pos.x() - self._off_x) / self._px_per_mm,
            (pos.y() - self._off_y) / self._px_per_mm,
        )

    def _rect_px(self) -> QRectF:
        x, y, w, h = self._rect_mm
        return QRectF(
            self._off_x + x * self._px_per_mm,
            self._off_y + y * self._px_per_mm,
            w * self._px_per_mm,
            h * self._px_per_mm,
        )

    def _handle_positions(self) -> list[tuple[float, float]]:
        """手柄位置：四角 + 四边，**恒 8 个**。

        四边手柄始终可用——用户明确去拖某条边，就是要单方向拉伸那条边
        （拖上/下边改高度、左/右边改宽度），与「原比例缩放」无关；
        该勾选只约束**四角**拖拽是否等比（True=等比，False=自由）。
        """
        r = self._rect_px()
        cx = r.x() + r.width() / 2
        cy = r.y() + r.height() / 2
        return [
            (r.x(), r.y()),                     # 0 左上
            (r.x() + r.width(), r.y()),         # 1 右上
            (r.x() + r.width(), r.y() + r.height()),  # 2 右下
            (r.x(), r.y() + r.height()),        # 3 左下
            (cx, r.y()),                        # 4 上
            (r.x() + r.width(), cy),            # 5 右
            (cx, r.y() + r.height()),           # 6 下
            (r.x(), cy),                        # 7 左
        ]

    def _rotate_knob_pos(self) -> QPointF:
        """旋转钮位置（控件坐标）：框上边中点再向上 ``ROTATE_KNOB_GAP``。"""
        r = self._rect_px()
        return QPointF(r.center().x(), r.y() - ROTATE_KNOB_GAP)

    def _hit_handle(self, pos: QPointF) -> int | None:
        """命中手柄：**旋转钮** → 四角（圆点邻域）→ 四边（**整条边的命中带**）。

        ⚠️ 旋转钮在图片**外面**（框上方），命中区比画出来的圆大一圈：它是
        唯一的旋转抓手，点太小抓不住（与「图片拼版」同一套手感，用户 2026-11-02）。
        ⚠️ 边命中**不限于边中点的小圆点**——整条边两侧 `EDGE_HIT_PX` 控件
        像素内都算拖那条边（窗口边缘的惯例：靠边即改宽/高，靠角即缩放）。
        角优先于边：角落同时邻近两条边，按角处理才符合直觉（圆点邻域
        判定在前，走到边判定时说明离角已经够远）。
        """
        if self._image is not None:
            knob = self._rotate_knob_pos()
            if abs(pos.x() - knob.x()) <= ROTATE_KNOB_HIT and \
                    abs(pos.y() - knob.y()) <= ROTATE_KNOB_HIT:
                return 8  # 旋转
        positions = self._handle_positions()
        for i in range(4):  # 四角：圆点邻域
            cx, cy = positions[i]
            if abs(pos.x() - cx) <= HANDLE_RADIUS + 2 and \
                    abs(pos.y() - cy) <= HANDLE_RADIUS + 2:
                return i
        r = self._rect_px()
        hit = EDGE_HIT_PX
        near_top = abs(pos.y() - r.y()) <= hit
        near_bottom = abs(pos.y() - (r.y() + r.height())) <= hit
        near_left = abs(pos.x() - r.x()) <= hit
        near_right = abs(pos.x() - (r.x() + r.width())) <= hit
        x_in = r.x() - hit <= pos.x() <= r.x() + r.width() + hit
        y_in = r.y() - hit <= pos.y() <= r.y() + r.height() + hit
        if near_top and x_in:
            return 4
        if near_right and y_in:
            return 5
        if near_bottom and x_in:
            return 6
        if near_left and y_in:
            return 7
        return None

    def _hit_rect(self, pos: QPointF) -> bool:
        return self._rect_px().contains(pos)
