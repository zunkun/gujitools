# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""画布绘制：纸张、图片（含旋转）、标题/页码、手柄与旋转钮。"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import QImage, QPainter, QPen

# 标题/页码的绘制必须与成品 PDF 同源：直接复用效果预览那套（mm → px 换算
# 与竖排分段完全一致），避免编辑器和 PDF 各画各的、看起来对不上。
from desktop.workers.preview_worker import (
    _draw_print_text, _pick_preview_font,
)

from .constants import (
    HANDLE_FILL,
    HANDLE_RADIUS,
    HANDLE_STROKE,
    IMAGE_STROKE,
    PAGE_BORDER,
    PAGE_COLOR,
    ROTATE_ARC_BARB,
    ROTATE_ARC_GAP,
    ROTATE_ARC_SPAN,
    ROTATE_ARC_START,
    ROTATE_KNOB_GAP,
    ROTATE_KNOB_RADIUS,
    SKIP_COLOR,
    SKIP_INK,
)

if TYPE_CHECKING:
    from ._host import PrintLayoutCanvasHost
else:
    PrintLayoutCanvasHost = object


class PaintMixin(PrintLayoutCanvasHost):
    """``paintEvent`` 与图片 / 旋转钮的绘制细节。"""

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
            painter.drawText(page_rect, Qt.AlignmentFlag.AlignCenter, "该页已跳过，不会输出到 PDF")
            painter.end()
            return
        painter.fillRect(page_rect, PAGE_COLOR)
        painter.setPen(QPen(PAGE_BORDER, 1))
        painter.drawRect(page_rect)
        # 图片（未旋转时按目标矩形拉伸，与成品 pdf.image 一致；旋转时绕框心
        # 转、按旋转后的外接框等比放进框里，与预览/PDF 同一份几何）
        image = self._display_image_for()
        if image is not None and not image.isNull():
            r = self._rect_px()
            if r.width() > 0 and r.height() > 0:
                # 图片本体与画框都裁到纸内：纸面以外的内容成品里不存在，
                # 画布也不该显示。
                painter.save()
                painter.setClipRect(page_rect)
                # ⚠️ 必须开平滑：Qt 默认关闭 SmoothPixmapTransform 时走最近邻，
                # 一次大比例缩小会把细笔画/淡墨直接跳采样（版面页看着发虚的
                # 原因）。底图已先降到 ≤2000px（见 DISPLAY_IMAGE_EDGE），这里
                # 再平滑缩一档，代价只有毫秒级，拖框不掉帧。
                painter.setRenderHint(
                    QPainter.RenderHint.SmoothPixmapTransform, True
                )
                self._draw_image(painter, image, r)
                painter.setPen(QPen(IMAGE_STROKE, 2))
                painter.drawRect(r)
                painter.restore()
            else:
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
        # 四角缩放手柄 + 框外上方的旋转钮。手柄同样只画纸面以内的部分：
        # 图片顶出纸边时，纸外不该再留定位方块（旋转钮是换角度唯一抓手，保留）。
        if self._image is not None:
            painter.setPen(QPen(HANDLE_STROKE, 1.5))
            painter.setBrush(HANDLE_FILL)
            painter.save()
            painter.setClipRect(page_rect)
            for cx, cy in self._handle_positions():
                painter.drawRect(
                    QRectF(cx - HANDLE_RADIUS, cy - HANDLE_RADIUS,
                           2 * HANDLE_RADIUS, 2 * HANDLE_RADIUS)
                )
            painter.restore()
            self._draw_rotate_knob(painter)
        painter.end()

    def _draw_image(self, painter: QPainter, image: QImage,
                    rect_px: QRectF) -> None:
        """把图片画进当前框：未旋转直接拉伸；旋转时绕框心变换。

        旋转后的内容尺寸由 :meth:`_content_size_mm` 反推（按源图宽高比），
        因此画出来正好落在旋转后的**外接框**里——与 PDF / 效果预览用
        ``fit_rotated_rect`` 算出的落点同一份几何，不会出现"预览转过去、
        成品转回来"。
        """
        if not self._rotation:
            painter.drawImage(rect_px, image)
            return
        content_w, content_h = self._content_size_mm(
            self._rect_mm, self._rotation
        )
        cw = content_w * self._px_per_mm
        ch = content_h * self._px_per_mm
        painter.save()
        painter.translate(rect_px.center())
        painter.rotate(self._rotation)
        painter.drawImage(QRectF(-cw / 2, -ch / 2, cw, ch), image)
        painter.restore()

    def _draw_rotate_knob(self, painter: QPainter) -> None:
        """画框外上方的旋转钮（**常显**，与「图片拼版」同款）。

        一条引线 + 一个白底圆钮，**圆外**环绕一段顺时针弧形箭头——一眼看出
        这是"旋转"抓手而不是缩放手柄（用户 2026-11-02：画在圆里太小、看不清）。
        左键拖它即可绕框心旋转当前页图片。
        """
        knob = self._rotate_knob_pos()
        anchor = QPointF(knob.x(), knob.y() + ROTATE_KNOB_GAP)
        painter.setPen(QPen(HANDLE_STROKE, 1.5))
        painter.drawLine(anchor, knob)
        painter.setBrush(HANDLE_FILL)
        painter.drawEllipse(knob, ROTATE_KNOB_RADIUS, ROTATE_KNOB_RADIUS)
        # 弧形箭头在圆钮外侧（顺时针；缺口在下方，不压住引线）
        arc_r = ROTATE_KNOB_RADIUS + ROTATE_ARC_GAP
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(
            QRectF(knob.x() - arc_r, knob.y() - arc_r, arc_r * 2, arc_r * 2),
            ROTATE_ARC_START * 16, ROTATE_ARC_SPAN * 16,
        )
        # 箭头：弧末端沿**顺时针**切线方向收两道短线
        end = math.radians(ROTATE_ARC_START + ROTATE_ARC_SPAN)
        tip = QPointF(
            knob.x() + arc_r * math.cos(end),
            knob.y() - arc_r * math.sin(end),
        )
        dx, dy = math.sin(end), math.cos(end)
        for turn in (-0.8, 0.8):
            barb_x = dx * math.cos(turn) - dy * math.sin(turn)
            barb_y = dx * math.sin(turn) + dy * math.cos(turn)
            painter.drawLine(
                tip, QPointF(tip.x() - ROTATE_ARC_BARB * barb_x,
                             tip.y() - ROTATE_ARC_BARB * barb_y)
            )
