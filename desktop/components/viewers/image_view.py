# -*- coding: utf-8 -*-
"""大图查看控件：随控件尺寸缩放，支持叠加切割框。

坐标基准是图片原始像素坐标（_image_size），与预览显示缩放无关。

开启 boxes_editable 后：
- 点击框选中（四角出现缩放手柄），拖动框内移动整框，拖手柄缩放；
- 在空白处按下并拖动可手绘一个新框；
- Delete/Backspace 删除选中框；
- 每次修改结束通过 boxes_edited 发出全部框（仅内存与信号，不落盘）。

reference_boxes 为参考框（如按 area/border 规则推导的最终裁剪大框），
橙色虚线显示，不参与编辑。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel

BOX_COLORS = [QColor("#21c178"), QColor("#3b82f6"), QColor("#f59e0b")]
BOX_NAMES = ["左框", "右框", "合并框"]
REFERENCE_COLOR = QColor("#f97316")
HANDLE_RADIUS = 5  # 缩放手柄半径（控件像素）

# 选中框四角手柄：0=左上 1=右上 2=右下 3=左下
_HANDLE_CURSORS = [
    Qt.SizeFDiagCursor, Qt.SizeBDiagCursor,
    Qt.SizeFDiagCursor, Qt.SizeBDiagCursor,
]


class ImageView(QLabel):
    """大图查看：随控件尺寸实时缩放，支持在图片坐标系叠加切割框。"""

    boxes_edited = Signal(list)  # 移动/缩放/删除/新增后：全部框（图片像素坐标）

    def __init__(self, placeholder: str = "无预览", parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(320, 300)
        self.setText(placeholder)
        self.setStyleSheet("background:#1f242b;color:#8b949e;border-radius:8px;")
        self._pixmap: QPixmap | None = None
        self._boxes: list[list[int]] = []  # [(x1,y1,x2,y2)] 图片像素坐标
        self._reference_boxes: list = []  # 参考框（最终裁剪大框），虚线显示
        self._image_size: QSize | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self._boxes_editable = False
        self._selected: int | None = None
        self._mode: str | None = None  # move / resize / new
        self._ghost_box: list | None = None
        self._dirty = False  # 本次拖动/缩放是否实际改变了坐标
        self._drag_index: int | None = None
        self._grab_dx = 0
        self._grab_dy = 0
        self._resize_corner = 0
        self._new_start: tuple[float, float] | None = None
        self._scale_x = 1.0
        self._scale_y = 1.0
        self._offset_x = 0
        self._offset_y = 0

    @property
    def has_image(self) -> bool:
        return self._pixmap is not None

    # ------------------------------------------------------------------ API
    def set_boxes_editable(self, editable: bool) -> None:
        self._boxes_editable = editable
        self.setFocusPolicy(Qt.ClickFocus if editable else Qt.NoFocus)

    def set_reference_boxes(self, boxes: list) -> None:
        self._reference_boxes = [list(box) for box in (boxes or [])]
        self._rerender()

    def set_image(self, image, boxes=None, image_size: QSize | None = None) -> None:
        self._image_size = image_size or image.size()
        self._boxes = [list(box) for box in (boxes or [])]
        self._pixmap = QPixmap.fromImage(image)
        self._selected = None
        self._mode = None
        self._drag_index = None
        self._ghost_box = None
        self._rerender()

    def set_boxes(self, boxes: list, image_size: QSize) -> None:
        self._boxes = [list(box) for box in boxes]
        self._image_size = image_size
        self._selected = None
        self._mode = None
        self._rerender()

    def clear_image(self, text: str = "无预览") -> None:
        self._pixmap = None
        self._boxes = []
        self._reference_boxes = []
        self._selected = None
        self._mode = None
        self._drag_index = None
        self.setText(text)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._rerender()

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
        if self._boxes_editable and event.button() == Qt.LeftButton and self._pixmap is not None:
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
                self._selected = index
                self._drag_index = index
                self._mode = "move"
                self._dirty = False
                x1, y1, _, _ = self._boxes[index]
                self._grab_dx = ix - x1
                self._grab_dy = iy - y1
                self.setCursor(Qt.ClosedHandCursor)
                self._rerender()
                return
            # 3) 空白处 → 手绘新框
            self._selected = None
            self._mode = "new"
            self._new_start = (ix, iy)
            self._rerender()
            return
        super().mousePressEvent(event)

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
                self.setCursor(Qt.PointingHandCursor)
                return
            self.setCursor(Qt.ArrowCursor)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._mode == "move" and self._drag_index is not None:
            self._drag_index = None
            self._mode = None
            self.setCursor(Qt.PointingHandCursor)
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
                box = [
                    min(max(box[0], 0), self._image_size.width()),
                    min(max(box[1], 0), self._image_size.height()),
                    min(max(box[2], 0), self._image_size.width()),
                    min(max(box[3], 0), self._image_size.height()),
                ]
                self._boxes.append(box)
                self._selected = len(self._boxes) - 1
                self._commit_edit()
            self._rerender()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._boxes_editable and self._selected is not None and event.key() in (
            Qt.Key_Delete, Qt.Key_Backspace,
        ):
            del self._boxes[self._selected]
            self._selected = None
            self._commit_edit()
            self._rerender()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ 渲染
    def _update_mapping(self, scaled: QPixmap) -> None:
        """按当前显示尺寸刷新坐标映射（必须在绘制之前调用）。

        缩放比以 _image_size（图片原始尺寸）为基准：显示的 pixmap 可能是
        预览加载时降采样过的版本，框坐标始终是原始像素坐标。
        """
        ref_w = self._image_size.width() if self._image_size else self._pixmap.width()
        ref_h = self._image_size.height() if self._image_size else self._pixmap.height()
        self._scale_x = scaled.width() / ref_w if ref_w else 1.0
        self._scale_y = scaled.height() / ref_h if ref_h else 1.0
        # setPixmap 后 QLabel 按 AlignCenter 居中显示
        self._offset_x = max(0, (self.width() - scaled.width()) // 2)
        self._offset_y = max(0, (self.height() - scaled.height()) // 2)

    def _rerender(self) -> None:
        """按当前控件尺寸缩放显示（窗口缩放/布局变化后保持完整可见）。"""
        if self._pixmap is None:
            return
        target = self.size() * 0.96
        scaled = self._pixmap.scaled(
            target, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        # 先刷新映射，再绘制：框/参考框/橡皮筋都使用本次渲染的缩放比
        self._update_mapping(scaled)
        display = QPixmap(scaled.size())
        display.fill(Qt.transparent)
        painter = QPainter(display)
        painter.drawPixmap(0, 0, scaled)
        if self._reference_boxes:
            self._draw_reference_boxes(painter)
        if self._boxes and self._image_size:
            self._draw_boxes(painter)
        ghost = getattr(self, "_ghost_box", None)
        if ghost:
            painter.setPen(QPen(QColor("#8b949e"), 1, Qt.DashLine))
            painter.drawRect(
                round(ghost[0] * self._scale_x), round(ghost[1] * self._scale_y),
                round((ghost[2] - ghost[0]) * self._scale_x),
                round((ghost[3] - ghost[1]) * self._scale_y),
            )
        painter.end()
        self.setPixmap(display)

    def _draw_reference_boxes(self, painter: QPainter) -> None:
        """参考框：按 area/border 规则推导的最终裁剪大框，橙色虚线。"""
        pen = QPen(REFERENCE_COLOR, 2, Qt.DashLine)
        painter.setPen(pen)
        for box in self._reference_boxes:
            x1, y1, x2, y2 = box
            painter.drawRect(
                round(x1 * self._scale_x), round(y1 * self._scale_y),
                round((x2 - x1) * self._scale_x), round((y2 - y1) * self._scale_y),
            )
        if self._reference_boxes:
            painter.setPen(QPen(REFERENCE_COLOR))
            painter.drawText(
                round(self._reference_boxes[0][0] * self._scale_x) + 4,
                max(14, round(self._reference_boxes[0][3] * self._scale_y) - 4),
                "最终裁剪框",
            )

    def _draw_boxes(self, painter: QPainter) -> None:
        font = painter.font()
        font.setPixelSize(13)
        painter.setFont(font)
        for index, box in enumerate(self._boxes):
            x1, y1, x2, y2 = box
            color = BOX_COLORS[index % len(BOX_COLORS)]
            selected = index == self._selected
            pen = QPen(color, 3 if selected else 2)
            painter.setPen(pen)
            painter.drawRect(
                round(x1 * self._scale_x), round(y1 * self._scale_y),
                round((x2 - x1) * self._scale_x), round((y2 - y1) * self._scale_y),
            )
            name = BOX_NAMES[index % len(BOX_NAMES)]
            painter.drawText(
                round(x1 * self._scale_x) + 4,
                max(14, round(y1 * self._scale_y) - 4),
                f"{name} ({x1},{y1},{x2},{y2})" + (" ｜ 已选中，Delete 删除" if selected else ""),
            )
        # 选中框的四角缩放手柄
        if self._selected is not None and self._selected < len(self._boxes):
            painter.setPen(QPen(QColor("#ffffff")))
            painter.setBrush(QColor(0, 0, 0, 160))
            for _corner, cx, cy, r in self._handle_rects(self._boxes[self._selected]):
                painter.drawRect(round(cx - r), round(cy - r), 2 * r, 2 * r)
            painter.setBrush(Qt.NoBrush)
