# -*- coding: utf-8 -*-
"""第四步「版面编辑器」交互画布：在 A4 纸上拖拽 / 缩放图片。

坐标体系与 ``utils.page_layout.plan_print_page`` 算出的 ``plan.image`` 完全一致
——**页面毫米，左上原点，x 向右、y 向下**。控件把页面等比缩放到可视区，
用 ``px_per_mm`` 在「页面 mm」与「控件像素」之间换算；用户拖拽/缩放得到的
``[x_mm, y_mm, w_mm, h_mm]`` 直接写回 ``print.json`` 的 ``pages[].rect``，
生成 PDF 时由 ``plan_print_page(image_rect=...)`` 原样采用——所见即所得。

交互（与 detect/rembg 的裁剪框编辑同款手感）：
- 框内拖动 → 整体移动；四角手柄拖动 → 缩放；松手 emit ``rect_changed``；
- 框始终被夹在页面内（夹到纸边即停），不会拖出页面；
- 悬停手柄/框时显示对应光标。

**标题与页码照画**：它们是「版面」的一部分，去掉就无从判断图片挪动后会不会
压到字（曾误判为「标题页码被去除」）。绘制复用 ``preview_worker`` 的
``_draw_print_text``——与成品 PDF 同源，只是多了画布自身的居中偏移。
标题/页码的落点只取决于 ``page_margins``，**不随图片框移动**，与 PDF 一致。

图片在框内按目标矩形**拉伸**绘制，与成品 ``pdf.image(img, x, y, w, h)`` 的
拉伸规则一致（PDF 用 w/h 直接定最终尺寸，不保比例）。
"""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from desktop.ui import theme as T
# 标题/页码的绘制必须与成品 PDF 同源：直接复用效果预览那套（mm → px 换算
# 与竖排分段完全一致），避免编辑器和 PDF 各画各的、看起来对不上。
from desktop.workers.preview_worker import (
    _draw_print_text, _pick_preview_font,
)

# 纸张恒为白底（PDF 纸张即白）；边框/控件用中性色，深浅主题下都清楚
PAGE_COLOR = QColor("#ffffff")
PAGE_BORDER = QColor("#cbd2dc")
# 命中 skip_pages 的页：成品里没有它，编辑时给灰底明确提示（与效果预览同色）
SKIP_COLOR = QColor("#eceff3")
SKIP_INK = QColor("#98a2b3")
IMAGE_STROKE = QColor("#2563eb")
HANDLE_STROKE = QColor("#2563eb")
HANDLE_FILL = QColor("#ffffff")
HANDLE_RADIUS = 6  # 手柄半径（控件像素）

# 四角手柄光标：0=左上 1=右上 2=右下 3=左下
_HANDLE_CURSORS = [
    Qt.SizeFDiagCursor, Qt.SizeBDiagCursor,
    Qt.SizeFDiagCursor, Qt.SizeBDiagCursor,
]


class PrintLayoutCanvas(QWidget):
    """A4 纸上的图片拖拽/缩放画布；rect_changed 发出页面 mm 坐标。"""

    rect_changed = Signal(list)  # [x_mm, y_mm, w_mm, h_mm]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 360)
        self._page_w_mm = 210.0
        self._page_h_mm = 297.0
        self._image: QImage | None = None
        self._plan = None          # PrintPagePlan：标题/页码/跳过态的来源
        self._rect_mm = [0.0, 0.0, 0.0, 0.0]
        self._pad = 18
        self._px_per_mm = 1.0
        self._off_x = float(self._pad)
        self._off_y = float(self._pad)
        self._mode: str | None = None  # move / resize
        self._corner = 0
        self._grab_x = 0.0
        self._grab_y = 0.0
        self._dirty = False
        self.setMouseTracking(True)
        self.setStyleSheet(
            f"background:{T.SURFACE_SOFT}; border:1px solid {T.BORDER};"
            f" border-radius:{T.RADIUS_MD}px;"
        )

    # ------------------------------------------------------------------ API
    def set_page(
        self,
        page_w_mm: float,
        page_h_mm: float,
        image: QImage | None,
        rect_mm: Sequence[float],
        plan=None,
    ) -> None:
        """设置页面尺寸、待绘制图片与初始图片框（页面 mm）。

        ``plan`` 为 ``utils.page_layout.PrintPagePlan``：本控件据它画标题/
        页码与「已跳过」提示——版面编辑不能只看图片，否则无从判断挪动后
        会不会压到字。传 None 表示纯图片编辑（无标题/页码）。
        """
        self._page_w_mm = float(page_w_mm)
        self._page_h_mm = float(page_h_mm)
        self._image = image
        self._plan = plan
        self._rect_mm = [float(v) for v in rect_mm]
        self._recompute()
        self.update()

    def current_rect(self) -> list[float]:
        """当前图片框（页面 mm），供宿主落盘前读取。"""
        return list(self._rect_mm)

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

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._recompute()
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802
        """显示时重算：首次进入第四步可能在布局完成前就 ``set_page`` 过，
        那时 ``width()/height()`` 还是 0，``_px_per_mm`` 会退化为 1.0。
        仅靠 resizeEvent 兜不住「已分配尺寸但从未显示」的情况。"""
        super().showEvent(event)
        self._recompute()
        self.update()

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
        r = self._rect_px()
        return [
            (r.x(), r.y()),
            (r.x() + r.width(), r.y()),
            (r.x() + r.width(), r.y() + r.height()),
            (r.x(), r.y() + r.height()),
        ]

    def _hit_handle(self, pos: QPointF) -> int | None:
        for i, (cx, cy) in enumerate(self._handle_positions()):
            if abs(pos.x() - cx) <= HANDLE_RADIUS + 2 and \
                    abs(pos.y() - cy) <= HANDLE_RADIUS + 2:
                return i
        return None

    def _hit_rect(self, pos: QPointF) -> bool:
        return self._rect_px().contains(pos)

    # ------------------------------------------------------------------ 鼠标
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._image is None or event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        corner = self._hit_handle(event.position())
        if corner is not None:
            self._mode = "resize"
            self._corner = corner
            self._dirty = False
            self.update()
            return
        if self._hit_rect(event.position()):
            self._mode = "move"
            self._dirty = False
            mx, my = self._to_mm(event.position())
            self._grab_x = mx - self._rect_mm[0]
            self._grab_y = my - self._rect_mm[1]
            self.setCursor(Qt.ClosedHandCursor)
            self.update()
            return
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._mode == "move":
            mx, my = self._to_mm(event.position())
            nx = min(max(mx - self._grab_x, 0.0),
                      self._page_w_mm - self._rect_mm[2])
            ny = min(max(my - self._grab_y, 0.0),
                      self._page_h_mm - self._rect_mm[3])
            self._rect_mm[0] = nx
            self._rect_mm[1] = ny
            self._dirty = True
            self.update()
            return
        if self._mode == "resize":
            mx, my = self._to_mm(event.position())
            x, y, w, h = self._rect_mm
            # 以与拖动角相对的「对角」为锚点
            ax, ay = {
                0: (x + w, y + h), 1: (x, y + h),
                2: (x, y), 3: (x + w, y),
            }[self._corner]
            nx1, ny1 = min(ax, mx), min(ay, my)
            nx2, ny2 = max(ax, mx), max(ay, my)
            # 夹在页面内
            nx1 = min(max(nx1, 0.0), self._page_w_mm)
            ny1 = min(max(ny1, 0.0), self._page_h_mm)
            nx2 = min(max(nx2, 0.0), self._page_w_mm)
            ny2 = min(max(ny2, 0.0), self._page_h_mm)
            self._rect_mm = [nx1, ny1, nx2 - nx1, ny2 - ny1]
            self._dirty = True
            self.update()
            return
        # 悬停光标提示
        if self._image is not None:
            corner = self._hit_handle(event.position())
            if corner is not None:
                self.setCursor(_HANDLE_CURSORS[corner])
                return
            if self._hit_rect(event.position()):
                self.setCursor(Qt.OpenHandCursor)
                return
            self.setCursor(Qt.ArrowCursor)
            return
        return super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._mode in ("move", "resize"):
            self._mode = None
            self.setCursor(Qt.ArrowCursor)
            if self._dirty:
                self.rect_changed.emit([round(v, 2) for v in self._rect_mm])
            self._dirty = False
            self.update()
            return
        return super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------ 渲染
    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        # 纸张
        page_rect = QRectF(
            self._off_x, self._off_y,
            self._page_w_mm * self._px_per_mm,
            self._page_h_mm * self._px_per_mm,
        )
        if self._plan is not None and self._plan.skipped:
            # 命中 skip_pages：成品不含此页，编辑时明确提示（与效果预览同款）
            painter.fillRect(page_rect, SKIP_COLOR)
            painter.setPen(SKIP_INK)
            painter.setFont(_pick_preview_font(14))
            painter.drawText(page_rect, Qt.AlignCenter, "该页已跳过，不会输出到 PDF")
            painter.end()
            return
        painter.fillRect(page_rect, PAGE_COLOR)
        painter.setPen(QPen(PAGE_BORDER, 1))
        painter.drawRect(page_rect)
        # 图片（按目标矩形拉伸，与成品 pdf.image 一致）
        if self._image is not None and not self._image.isNull():
            r = self._rect_px()
            if r.width() > 0 and r.height() > 0:
                painter.drawImage(r, self._image)
            painter.setPen(QPen(IMAGE_STROKE, 2))
            painter.drawRect(r)
        # 标题 / 页码：与成品 PDF 同一份 PrintTextSpec 与同一套绘制函数，
        # 只多一层画布居中偏移。落点只由 page_margins 决定，不随图片框移动。
        if self._plan is not None:
            painter.save()
            painter.translate(self._off_x, self._off_y)
            for spec in (self._plan.title, self._plan.page_number):
                if spec is not None:
                    _draw_print_text(painter, spec, self._px_per_mm)
            painter.restore()
        # 四角缩放手柄
        if self._image is not None:
            painter.setPen(QPen(HANDLE_STROKE, 1.5))
            painter.setBrush(HANDLE_FILL)
            for cx, cy in self._handle_positions():
                painter.drawRect(
                    QRectF(cx - HANDLE_RADIUS, cy - HANDLE_RADIUS,
                           2 * HANDLE_RADIUS, 2 * HANDLE_RADIUS)
                )
        painter.end()
