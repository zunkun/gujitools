# -*- coding: utf-8 -*-
"""拼版画布的**坐标换算 + 适配 + 命中测试**（``_GeometryMixin``）。

Mixin 只在运行期与 ``ImpositionCanvas`` 组合；宿主面见 :mod:`._host`，本模块
**不 import** 主类 ``widget``，避免循环导入。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from desktop.components.imposition.canvas._qt import QPointF, QRectF
from desktop.components.imposition.canvas.constants import (
    EDGE_HIT_PX,
    HANDLE_RADIUS,
    ROTATE_KNOB_GAP,
    ROTATE_KNOB_HIT,
)

if TYPE_CHECKING:
    from desktop.components.imposition.canvas._host import CanvasHost as _Host
else:
    _Host = object


class _GeometryMixin(_Host):
    """坐标体系、可视区适配与手柄/旋转钮的命中判定。"""

    # ------------------------------------------------------------------ 坐标
    def _scene_rect(self) -> QRectF:
        """需要显示的范围（图坐标）：**所有图外接框的并集**。

        拼版没有纸张（用户 2026-09-30），可视范围就按图算——这样挪多远、拉多大
        都还看得见（超出控件可视区的部分由 Qt 丢弃，与"我们主动裁掉"不同）。
        旋转过的图按**外接框**算（用 w/h 与角度推），与画出来的样子一致。
        没有图时给一个占位方块，避免除零（此时画面就是纯白底）。
        """
        boxes = [self._item_box_units(item) for item in self._items]
        if not boxes:
            return QRectF(0.0, 0.0, 1.0, 1.0)
        return QRectF(
            min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(max(b[2] for b in boxes) - min(b[0] for b in boxes), 1.0),
            max(max(b[3] for b in boxes) - min(b[1] for b in boxes), 1.0),
        )

    @staticmethod
    def _item_box_units(item: dict) -> tuple[float, float, float, float]:
        """一项的**外接框**（旋转后），单位与图坐标一致。"""
        x, y, w, h = item["rect"]
        center_x, center_y = x + w / 2.0, y + h / 2.0
        angle = math.radians(float(item.get("rotation") or 0.0))
        box_w = abs(w * math.cos(angle)) + abs(h * math.sin(angle))
        box_h = abs(w * math.sin(angle)) + abs(h * math.cos(angle))
        return (center_x - box_w / 2.0, center_y - box_h / 2.0,
                center_x + box_w / 2.0, center_y + box_h / 2.0)

    def _spread_center_units(self) -> tuple[float, float]:
        """两图 rect 中心的**中点**（图坐标）——红色对齐线的落点。

        ⚠️ 用**未旋转的 rect 中心**（不是外接框中心）：单图自转不挪中心，
        整版旋转又绕这个中点公转——所以无论怎么转，对齐线都稳稳钉在同一处。
        只有一张图时就是它自己的中心。
        """
        if not self._items:
            return 0.0, 0.0
        centers = [
            (item["rect"][0] + item["rect"][2] / 2.0,
             item["rect"][1] + item["rect"][3] / 2.0)
            for item in self._items
        ]
        return (
            sum(c[0] for c in centers) / len(centers),
            sum(c[1] for c in centers) / len(centers),
        )

    def _recompute(self) -> None:
        """按「所有图的外接框」等比适配控件，再套上滚轮缩放倍率。

        ⚠️ 只在 ``set_page`` / 尺寸变化时算，**拖动过程中不重算**——否则一边拖
        一边缩放视图，手感会飘。所以拖动把图挪出可视区是可能的：松手后切页再
        回来（或窗口尺寸一变）就会重新适配、把整页显示全。
        ⚠️ 尺寸变化**保留**滚轮缩放倍率：只重算适配基准（``_fit_*``），倍率以
        控件中心为锚套回去——拖一下窗口大小不该把视图打回原形。归一只有
        ``set_page`` / ``refit`` 两处。
        """
        avail_w = self.width() - 2 * self._pad
        # 上边用 ``_pad_top``：把选中图框外的旋转钮也留在可视区（见 __init__）
        avail_h = self.height() - self._pad - self._pad_top
        scene = self._scene_rect()
        if avail_w <= 0 or avail_h <= 0 or scene.width() <= 0 or scene.height() <= 0:
            self._fit_ppu = 1.0
            self._fit_off_x = float(self._pad)
            self._fit_off_y = float(self._pad_top)
        else:
            self._fit_ppu = min(
                avail_w / scene.width(), avail_h / scene.height()
            )
            self._fit_off_x = (
                (self.width() - scene.width() * self._fit_ppu) / 2.0
                - scene.x() * self._fit_ppu
            )
            self._fit_off_y = (
                self._pad_top + (avail_h - scene.height() * self._fit_ppu) / 2.0
                - scene.y() * self._fit_ppu
            )
        self._px_per_unit = self._fit_ppu * self._zoom
        # 以控件中心为锚套倍率：场景中心（适配时在控件中心）不动
        cx, cy = self.width() / 2.0, self.height() / 2.0
        self._off_x = cx - (cx - self._fit_off_x) * self._zoom
        self._off_y = cy - (cy - self._fit_off_y) * self._zoom

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._recompute()
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._recompute()
        self.update()

    def _to_units(self, pos: QPointF) -> tuple[float, float]:
        """控件坐标 → 合成像素坐标。"""
        return (
            (pos.x() - self._off_x) / self._px_per_unit,
            (pos.y() - self._off_y) / self._px_per_unit,
        )

    def _rect_px(self, index: int) -> QRectF:
        x, y, w, h = self._items[index]["rect"]
        return QRectF(
            self._off_x + x * self._px_per_unit,
            self._off_y + y * self._px_per_unit,
            w * self._px_per_unit,
            h * self._px_per_unit,
        )

    def _to_local_px(self, index: int, pos: QPointF) -> QPointF:
        """控件像素 → 该项**局部**坐标：原点 = rect 中心，已反转旋转角。

        框与手柄是**跟着图一起转**的（用户 2026-09-30），命中判定、缩放取
        鼠标都得先反转旋转角——不反转就等于拿"转过的鼠标"去比"没转的框"。
        返回值与 ``_handle_positions_local`` / ``_rotate_knob_local`` 同一
        坐标系，可以直接比。
        """
        c = self._rect_px(index).center()
        angle = math.radians(float(self._items[index].get("rotation") or 0.0))
        cos_v, sin_v = math.cos(-angle), math.sin(-angle)
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        return QPointF(dx * cos_v - dy * sin_v, dx * sin_v + dy * cos_v)

    def _item_contains_px(self, index: int, pos: QPointF) -> bool:
        """点（控件像素）是否落在该项**旋转后**的图里。"""
        r = self._rect_px(index)
        local = self._to_local_px(index, pos)
        return (
            abs(local.x()) <= r.width() / 2.0
            and abs(local.y()) <= r.height() / 2.0
        )

    def _handle_positions_local(self, index: int) -> list[tuple[float, float]]:
        """手柄位置（**局部**坐标，rect 中心为原点）：四角 + 四边，恒 8 个。

        画框是在"平移到 rect 中心 + 旋转 rotation"的坐标系里画的，直接用它。
        """
        r = self._rect_px(index)
        hw, hh = r.width() / 2.0, r.height() / 2.0
        return [
            (-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh),
            (0.0, -hh), (hw, 0.0), (0.0, hh), (-hw, 0.0),
        ]

    def _handle_positions(self, index: int) -> list[tuple[float, float]]:
        """手柄位置（**控件**坐标，已按该项 rotation 转过）：命中判定与自测用。"""
        c = self._rect_px(index).center()
        angle = math.radians(float(self._items[index].get("rotation") or 0.0))
        cos_v, sin_v = math.cos(angle), math.sin(angle)
        return [
            (c.x() + lx * cos_v - ly * sin_v, c.y() + lx * sin_v + ly * cos_v)
            for lx, ly in self._handle_positions_local(index)
        ]

    def _rotate_knob_local(self, index: int) -> QPointF:
        """旋转钮位置（局部坐标）：框上边中点再向上 ``ROTATE_KNOB_GAP``。"""
        return QPointF(
            0.0, -self._rect_px(index).height() / 2.0 - ROTATE_KNOB_GAP
        )

    def _rotate_knob(self, index: int) -> QPointF:
        """旋转钮位置（**控件**坐标，已按该项 rotation 转过）。"""
        local = self._rotate_knob_local(index)
        c = self._rect_px(index).center()
        angle = math.radians(float(self._items[index].get("rotation") or 0.0))
        cos_v, sin_v = math.cos(angle), math.sin(angle)
        return QPointF(
            c.x() + local.x() * cos_v - local.y() * sin_v,
            c.y() + local.x() * sin_v + local.y() * cos_v,
        )

    def _hit_handle(self, index: int, pos: QPointF) -> int | None:
        """命中手柄：旋转钮 → 四角（圆点邻域）→ 四边（整条边的命中带）。

        ``pos`` 是控件坐标，先 ``_to_local_px`` 反转旋转角再与**局部**手柄
        位置比——框转了，命中带也跟着转（用户 2026-09-30）。
        ⚠️ 旋转钮**在图片外面**（框上方），选中后常显；命中区比画出来的圆
        大一圈（``ROTATE_KNOB_HIT``），左键拖它即可旋转选中的那张图。
        """
        local = self._to_local_px(index, pos)
        knob = self._rotate_knob_local(index)
        if (abs(local.x() - knob.x()) <= ROTATE_KNOB_HIT
                and abs(local.y() - knob.y()) <= ROTATE_KNOB_HIT):
            return 8  # 旋转
        for i, (cx, cy) in enumerate(self._handle_positions_local(index)[:4]):
            if abs(local.x() - cx) <= HANDLE_RADIUS + 2 and \
                    abs(local.y() - cy) <= HANDLE_RADIUS + 2:
                return i
        r = self._rect_px(index)
        hit = EDGE_HIT_PX
        hw, hh = r.width() / 2.0, r.height() / 2.0
        near_top = abs(local.y() + hh) <= hit
        near_bottom = abs(local.y() - hh) <= hit
        near_left = abs(local.x() + hw) <= hit
        near_right = abs(local.x() - hw) <= hit
        x_in = -hw - hit <= local.x() <= hw + hit
        y_in = -hh - hit <= local.y() <= hh + hit
        if near_top and x_in:
            return 4
        if near_right and y_in:
            return 5
        if near_bottom and x_in:
            return 6
        if near_left and y_in:
            return 7
        return None

    def _item_at(self, pos: QPointF) -> int:
        """最上面一张命中的图（后画的在上 → 倒序找）。

        ⚠️ 命中按**旋转后**的图算：每个项各自反转自己的旋转角再判包含。
        ⚠️ **选中的图优先**（用户 2026-10-10）：它在画面上永远垫在最上面
        （zIndex 语义，见 ``paintEvent``），重叠区点下去就该点到它——否则
        "看着在最上面、点下去选中的却是底下那张"。
        """
        if (0 <= self._selected < len(self._items)
                and self._item_contains_px(self._selected, pos)):
            return self._selected
        for index in range(len(self._items) - 1, -1, -1):
            if index == self._selected:
                continue
            if self._item_contains_px(index, pos):
                return index
        return -1
