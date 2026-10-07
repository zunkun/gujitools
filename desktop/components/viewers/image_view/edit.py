# -*- coding: utf-8 -*-
"""``ImageView`` Mixin：**鼠标/键盘编辑**。

框的选中/拖拽/四角缩放/双击/右键/键盘删除。（从 ``image_view.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from .styles import HANDLE_RADIUS, _HANDLE_CURSORS
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import ImageViewHost
else:
    ImageViewHost = object


class EditMixin(ImageViewHost):
    """框的选中/拖拽/四角缩放/双击/右键/键盘删除。"""

    # ------------------------------------------------------------------ 坐标
    def _to_image_coords(self, pos: QPointF) -> tuple[float, float]:
        """控件坐标 → 图片原始像素坐标。"""
        return (
            (pos.x() - self._offset_x) / self._scale_x,
            (pos.y() - self._offset_y) / self._scale_y,
        )


    def _handle_rects(self, box) -> list[tuple[int, int, float, float]]:
        """选中框四角手柄的显示位图坐标区域 [(corner, cx, cy, r)]。

        与 _draw_boxes 的绘制坐标系一致（display 位图原点，不含居中偏移）；
        命中判断时由 _hit_handle 先减去偏移换算回该坐标系。
        """
        x1, y1, x2, y2 = box
        corners = [
            (x1 * self._scale_x, y1 * self._scale_y),
            (x2 * self._scale_x, y1 * self._scale_y),
            (x2 * self._scale_x, y2 * self._scale_y),
            (x1 * self._scale_x, y2 * self._scale_y),
        ]
        return [
            (i, cx, cy, HANDLE_RADIUS)
            for i, (cx, cy) in enumerate(corners)
        ]


    def _hit_handle(self, pos: QPointF) -> int | None:
        if self._selected is None or self._selected >= len(self._boxes):
            return None
        # 鼠标在控件坐标，display 位图以 (offset_x, offset_y) 为原点居中
        px = pos.x() - self._offset_x
        py = pos.y() - self._offset_y
        for corner, cx, cy, r in self._handle_rects(self._boxes[self._selected]):
            if abs(px - cx) <= r + 2 and abs(py - cy) <= r + 2:
                return corner
        return None


    def _hit_box(self, ix: float, iy: float) -> int | None:
        """命中检测：返回被点中的框下标（后画的优先），未命中返回 None。"""
        for index in range(len(self._boxes) - 1, -1, -1):
            x1, y1, x2, y2 = self._boxes[index]
            if x1 <= ix <= x2 and y1 <= iy <= y2:
                return index
        return None


    @staticmethod
    def _normalize(box) -> list[int]:
        x1, x2 = sorted((box[0], box[2]))
        y1, y2 = sorted((box[1], box[3]))
        return [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))]


    def _commit_edit(self) -> None:
        self.boxes_edited.emit([list(box) for box in self._boxes])


    # ------------------------------------------------------------------ 鼠标
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._boxes_editable and event.button() == Qt.MouseButton.LeftButton and self._pixmap is not None:
            ix, iy = self._to_image_coords(event.position())
            # 1) 选中框的缩放手柄
            corner = self._hit_handle(event.position())
            if corner is not None:
                self._mode = "resize"
                self._drag_index = self._selected
                self._resize_corner = corner
                self._dirty = False
                return
            # 2) 点中某个框 → 选中并进入拖动
            index = self._hit_box(ix, iy)
            if index is not None:
                self._select(index)
                self._drag_index = index
                self._mode = "move"
                self._dirty = False
                x1, y1, _, _ = self._boxes[index]
                self._grab_dx = ix - x1
                self._grab_dy = iy - y1
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self._rerender()
                return
            # 3) 空白处 → 手绘新框（已达上限则拒绝，宿主弹提示）
            if len(self._boxes) >= self.max_boxes:
                self._select(None)
                self._rerender()
                self.edit_rejected.emit(self._limit_message())
                return
            self._select(None)
            self._mode = "new"
            self._new_start = (ix, iy)
            self._rerender()
            return
        super().mousePressEvent(event)


    def _limit_message(self) -> str:
        """框数已达上限时的提示文案（按形态给出下一步该做什么）。"""
        if self._full_mode:
            return (
                "「整幅」页只能有一个文本框。要画左右文本框，请先在"
                "「选中框类型」里把整幅框改为左框或右框。"
            )
        return (
            "半幅页最多左右两个文本框。要画整页的整幅框，请先删除其他文本框，"
            "再把框类型改为「整幅」。"
        )


    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        ix, iy = self._to_image_coords(event.position())
        if self._mode == "move" and self._drag_index is not None and self._image_size is not None:
            x1, y1, x2, y2 = self._boxes[self._drag_index]
            width, height = x2 - x1, y2 - y1
            nx1 = min(max(ix - self._grab_dx, 0), self._image_size.width() - width)
            ny1 = min(max(iy - self._grab_dy, 0), self._image_size.height() - height)
            self._boxes[self._drag_index] = [
                round(nx1), round(ny1), round(nx1 + width), round(ny1 + height)
            ]
            self._dirty = True
            self._rerender()
            return
        if self._mode == "resize" and self._drag_index is not None:
            box = list(self._boxes[self._drag_index])
            anchor_x, anchor_y = {
                0: (box[2], box[3]), 1: (box[0], box[3]),
                2: (box[0], box[1]), 3: (box[2], box[1]),
            }[self._resize_corner]
            # ⚠️ 拖角必须夹在图幅内（与 move 分支、new 松手时的夹取同口径）：
            #    不夹的话 boxes.json 里会存进负坐标/超界框，下游 rembg 预览、
            #    提交合成、打印按越界框算出错误区域（2026-09-26 第二轮审计）。
            assert self._image_size is not None  # resize 模式下必有图幅尺寸
            ix = min(max(ix, 0), self._image_size.width())
            iy = min(max(iy, 0), self._image_size.height())
            self._boxes[self._drag_index] = self._normalize(
                [anchor_x, anchor_y, ix, iy]
            )
            self._dirty = True
            self._rerender()
            return
        if self._mode == "new" and self._new_start is not None:
            sx, sy = self._new_start
            self._ghost_box = self._normalize([sx, sy, ix, iy])
            self._rerender()
            return
        # 悬停光标
        if self._boxes_editable and self._pixmap is not None and self._boxes:
            corner = self._hit_handle(event.position())
            if corner is not None:
                self.setCursor(_HANDLE_CURSORS[corner])
                return
            if self._hit_box(ix, iy) is not None:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                return
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        super().mouseMoveEvent(event)


    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._mode == "move" and self._drag_index is not None:
            self._drag_index = None
            self._mode = None
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            if self._dirty:
                self._commit_edit()
            self._dirty = False
            return
        if self._mode == "resize" and self._drag_index is not None:
            self._drag_index = None
            self._mode = None
            if self._dirty:
                self._commit_edit()
            self._dirty = False
            return
        if self._mode == "new" and self._new_start is not None:
            ix, iy = self._to_image_coords(event.position())
            box = self._normalize([self._new_start[0], self._new_start[1], ix, iy])
            self._new_start = None
            self._mode = None
            self._ghost_box = None
            # 过滤误触产生的极小框
            if box[2] - box[0] > 8 and box[3] - box[1] > 8 and self._image_size is not None:
                if len(self._boxes) >= self.max_boxes:
                    self.edit_rejected.emit(self._limit_message())
                    self._rerender()
                    return
                box = [
                    min(max(box[0], 0), self._image_size.width()),
                    min(max(box[1], 0), self._image_size.height()),
                    min(max(box[2], 0), self._image_size.width()),
                    min(max(box[3], 0), self._image_size.height()),
                ]
                self._boxes.append(box)
                self._select(len(self._boxes) - 1)
                self._commit_edit()
            self._rerender()
            return
        super().mouseReleaseEvent(event)


    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """双击 → ``double_clicked``（宿主打开图片预览弹窗）。

        ⚠️ 必须把本次按下可能已经开始的"手绘新框"清干净：双击的第一下会先落到
        ``mousePressEvent`` 的"空白处 → 手绘"分支，不清就会在图上留一个跟着
        鼠标跑的橡皮筋残影，而且第二下松开还会真的落一个框。
        """
        if event.button() == Qt.MouseButton.LeftButton and self._pixmap is not None:
            self._mode = None
            self._new_start = None
            self._drag_index = None
            self._ghost_box = None
            self._rerender()
            self.double_clicked.emit()
            return
        super().mouseDoubleClickEvent(event)


    def contextMenuEvent(self, event) -> None:  # noqa: N802
        """右键大图 → ``context_menu_requested``（宿主弹「查看 / 编辑」菜单）。

        没有图时不弹（没有可查看/可编辑的东西），交给默认处理。框编辑用的是
        左键（见 mousePressEvent），右键不参与，两者不打架。
        """
        if self._pixmap is not None:
            self.context_menu_requested.emit()
            event.accept()
            return
        super().contextMenuEvent(event)


    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._boxes_editable and self._selected is not None and event.key() in (
            Qt.Key.Key_Delete, Qt.Key.Key_Backspace,
        ):
            del self._boxes[self._selected]
            # ⚠️ 先清选中再提交：只剩一个框时它的**类型不会被删除影响**
            #    （半幅仍是半幅、整幅仍是整幅），类型与"剩几个框"无关。
            self._select(None)
            self._commit_edit()
            self._rerender()
            return
        super().keyPressEvent(event)
