# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""画布鼠标交互：拖移 / 缩放 / 旋转 / 双击 / 右键。"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from utils.page_layout import normalize_page_rotation

from .constants import (
    MIN_RECT_MM,
    SNAP_DEGREES,
    _EDGE_BY_HANDLE,
    _HANDLE_CURSORS,
)

if TYPE_CHECKING:
    from ._host import PrintLayoutCanvasHost
else:
    PrintLayoutCanvasHost = object


class MouseMixin(PrintLayoutCanvasHost):
    """鼠标手势：框内移动、手柄缩放、旋转钮旋转。"""

    # ------------------------------------------------------------------ 鼠标
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._image is None or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        corner = self._hit_handle(event.position())
        if corner == 8:
            # 旋转钮：记下起点角度与起点内容尺寸，拖动时按增量算朝向
            self._mode = "rotate"
            center = self._rect_px().center()
            mx, my = event.position().x(), event.position().y()
            self._grab_angle = math.degrees(
                math.atan2(mx - center.x(), center.y() - my)
            )
            self._grab_rotation = self._rotation
            self._grab_content = self._content_size_mm(
                self._rect_mm, self._rotation
            )
            self._dirty = False
            self.update()
            return
        if corner is not None:
            self._mode = "resize"
            self._corner = corner
            # 保比例的角拖拽以**起点框**为基准（比例与对角锚点都取自它）；
            # 读拖动中的 _rect_mm 会逐帧累积偏差。
            self._grab_rect = list(self._rect_mm)
            self._dirty = False
            self.update()
            return
        if self._hit_rect(event.position()):
            self._mode = "move"
            self._dirty = False
            mx, my = self._to_mm(event.position())
            self._grab_x = mx - self._rect_mm[0]
            self._grab_y = my - self._rect_mm[1]
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
            return
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._mode == "rotate":
            center = self._rect_px().center()
            mx, my = event.position().x(), event.position().y()
            angle = math.degrees(
                math.atan2(mx - center.x(), center.y() - my)
            )
            value = self._grab_rotation + angle - self._grab_angle
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                value = round(value / SNAP_DEGREES) * SNAP_DEGREES
            self._rotation = normalize_page_rotation(value)
            self._rect_mm = self._bbox_for_content(
                self._grab_content, self._rotation
            )
            self._dirty = True
            self.update()
            return
        if self._mode == "move":
            mx, my = self._to_mm(event.position())
            # 允许拖出纸面：负页边距下图片本来就可能比纸大（纸外内容由
            # 画布/成品裁掉），把框夹回纸内会让用户无法挪动裁切位置。
            self._rect_mm[0] = mx - self._grab_x
            self._rect_mm[1] = my - self._grab_y
            self._dirty = True
            self.update()
            return
        if self._mode == "resize":
            mx, my = self._to_mm(event.position())
            self._rect_mm = self._resize_from_handle(mx, my)
            self._dirty = True
            self.update()
            return
        # 悬停光标提示
        if self._image is not None:
            corner = self._hit_handle(event.position())
            if corner == 8:
                self.setCursor(Qt.CursorShape.CrossCursor)
                return
            if corner is not None:
                self.setCursor(_HANDLE_CURSORS[corner])
                return
            if self._hit_rect(event.position()):
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                return
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        return super().mouseMoveEvent(event)

    def _resize_from_handle(self, mx: float, my: float) -> list[float]:
        """按当前手柄算出新框（页面 mm，始终夹在页面内）。

        - 四边手柄：只改受影响的那个维度，**自由拉伸**（这是「取消原比例」
          的核心手感：上下/左右单独拉，比例随之改变）；
        - 四角手柄：`keep_ratio=False` 时自由拉伸；`True` 时以**对角为锚点**
          等比缩放——比例取自拖拽起点框 `_grab_rect`，鼠标决定的宽高里取
          **更受限**的那个维度配对，这样往任何方向拖都不会跑形。
        """
        gx, gy, gw, gh = self._grab_rect
        pw, ph = self._page_w_mm, self._page_h_mm
        edge = _EDGE_BY_HANDLE.get(self._corner)
        if edge is not None:
            x, y, w, h = self._rect_mm
            if edge == "top":
                top = min(max(my, 0.0), y + h - MIN_RECT_MM)
                return [x, top, w, y + h - top]
            if edge == "bottom":
                bottom = min(max(my, y + MIN_RECT_MM), ph)
                return [x, y, w, bottom - y]
            if edge == "left":
                left = min(max(mx, 0.0), x + w - MIN_RECT_MM)
                return [left, y, x + w - left, h]
            right = min(max(mx, x + MIN_RECT_MM), pw)
            return [x, y, right - x, h]
        # ---- 四角 ----
        ax, ay = {
            0: (gx + gw, gy + gh), 1: (gx, gy + gh),
            2: (gx, gy), 3: (gx + gw, gy),
        }[self._corner]
        if not self._keep_ratio or gw <= 0 or gh <= 0:
            nx1, ny1 = min(ax, mx), min(ay, my)
            nx2, ny2 = max(ax, mx), max(ay, my)
            nx1 = min(max(nx1, 0.0), pw)
            ny1 = min(max(ny1, 0.0), ph)
            nx2 = min(max(nx2, 0.0), pw)
            ny2 = min(max(ny2, 0.0), ph)
            return [nx1, ny1, nx2 - nx1, ny2 - ny1]
        ratio = gh / gw
        scale = min(
            abs(mx - ax) / gw if gw else 0.0,
            abs(my - ay) / gh if gh else 0.0,
        )
        new_w = max(MIN_RECT_MM, gw * scale)
        new_h = max(MIN_RECT_MM, new_w * ratio)
        # 超出页面就等比缩回来（不破比例，也不做单维度夹取）
        if new_w > pw:
            new_w, new_h = pw, pw * ratio
        if new_h > ph:
            new_h, new_w = ph, ph / ratio if ratio else new_w
        nx = ax - new_w if self._corner in (0, 3) else ax
        ny = ay - new_h if self._corner in (0, 1) else ay
        nx = min(max(nx, 0.0), pw - new_w)
        ny = min(max(ny, 0.0), ph - new_h)
        return [nx, ny, new_w, new_h]

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """双击 → ``double_clicked``（宿主打开预览弹窗）。"""
        if event.button() == Qt.MouseButton.LeftButton and self._image is not None:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        """右键 → ``context_menu_requested``（宿主弹「预览图片 / 编辑图片」菜单）。

        左键的拖拽/缩放不受影响（右键不参与编辑手势）；空页不弹菜单。
        """
        if self._image is not None:
            self.context_menu_requested.emit()
            event.accept()
            return
        super().contextMenuEvent(event)

    def flush_pending(self) -> bool:
        """把"还没松手"的拖动结果补发出去（关窗口/切步骤/切页时调）。

        ⚠️ 为什么需要（2026-09-26 审计）：`rect_changed` 只在 `mouseReleaseEvent`
        里发（拖动过程中只 `update()` 重绘、不落盘）。于是「拖住图片框不放、
        直接关窗口 / 返回列表」这一下改动就**永久丢失**，而且用户以为已经生效了
        （画布上就是拖动后的样子）。这里主动补发一次，语义与正常松手完全一致。

        返回 True 表示确实补发了一次（即存在未提交的改动）。
        """
        if not self._dirty:
            return False
        self.rect_changed.emit([round(v, 2) for v in self._rect_mm])
        self._dirty = False
        return True

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._mode in ("move", "resize", "rotate"):
            self._mode = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if self._dirty:
                self.rect_changed.emit([round(v, 2) for v in self._rect_mm])
            self._dirty = False
            self.update()
            return
        return super().mouseReleaseEvent(event)
