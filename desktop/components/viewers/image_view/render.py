# -*- coding: utf-8 -*-
"""``ImageView`` Mixin：**绘制与坐标映射**。

重绘整张预览（框/参考框/整幅虚框）与图↔屏坐标映射。（从 ``image_view.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from .styles import BOX_COLORS, BOX_NAMES, REFERENCE_COLOR, box_styles
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import ImageViewHost
else:
    ImageViewHost = object


class RenderMixin(ImageViewHost):
    """重绘整张预览（框/参考框/整幅虚框）与图↔屏坐标映射。"""

    def _rerender(self) -> None:
        """按当前控件尺寸缩放显示（窗口缩放/布局变化后保持完整可见）。

        ⚠️ 必须按**物理**像素出图并把 dpr 写回 pixmap：早先按逻辑像素出图，
        高分屏下 Qt 再按 dpr 放大一次，等于把图「先降后升」重采样两轮。
        实测 150% 缩放下锐度 494 → 3755（**7.6 倍**）、200% 下 171 → 2831
        （**16 倍**），而 100% 缩放下几乎无差别——所以只在普通屏上是看不出
        这个问题的（数据见 .workbuddy/perf/2026-09-24-preview-sharpness.md）。

        叠加层（框/手柄/文字）用**逻辑**坐标绘制。

        ⚠️ **不要再手动 `painter.scale(dpr, dpr)`**：Qt 在带 devicePixelRatio 的
        pixmap 上作画时，painter 的坐标**已经是逻辑坐标**（实测 dpr=1.5 时
        `drawRect(0,0,10,10)` 覆盖物理 0~15px，而 `transform().m11()` 仍报 1.0
        ——dpr 是在设备层生效的，不体现在 painter 的变换里）。再乘一次 dpr
        等于放大两次：框会整体放大并偏移，而底图是对的，看上去就是"框和图片
        对不上/比例不对"。离屏自测（dpr 恒为 1）测不出这个，必须在 dpr≠1 下
        用像素级断言验（见 tests/selftests/preview_dpr.py）。
        """
        if self._pixmap is None:
            return
        dpr = self.devicePixelRatioF() or 1.0
        self._dpr = dpr
        if self.width() <= 0 or self.height() <= 0:
            # 还没布局（尺寸 0）：照 0 尺寸缩放只会得到一张 1x1，别覆盖上一张图
            return
        target = QSize(
            max(1, round(self.width() * 0.96 * dpr)),
            max(1, round(self.height() * 0.96 * dpr)),
        )
        # ---- 底图缓存（审计 D3）：SmoothTransformation 对 3000px 源图是
        # ~37MB/帧的重采样，而拖框时 mouseMoveEvent 逐帧调这里。键 = (源图版本,
        # 目标尺寸, dpr)，三者拖框期间都不变 → 直接复用，只做一次廉价 copy
        # 再画叠加层。窗口缩放/换图/换屏时键变 → 才真正重采样一次。
        key = (self._pixmap_version, target, dpr)
        if key != self._scaled_key or self._scaled_base is None:
            self._scaled_base = self._pixmap.scaled(
                target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self._scaled_base.setDevicePixelRatio(dpr)
            self._scaled_key = key
        # copy() 是纯内存拷贝（毫秒级）；直接在缓存底图上画会把叠加层烙进缓存
        scaled = self._scaled_base.copy()
        # 先刷新映射，再绘制：框/参考框/橡皮筋都使用本次渲染的缩放比
        self._update_mapping(scaled)
        painter = QPainter(scaled)
        if self._reference_boxes:
            self._draw_reference_boxes(painter)
        if self._boxes and self._image_size:
            self._draw_boxes(painter)
        ghost = getattr(self, "_ghost_box", None)
        if ghost:
            painter.setPen(QPen(QColor("#8b949e"), 1, Qt.PenStyle.DashLine))
            painter.drawRect(
                round(ghost[0] * self._scale_x), round(ghost[1] * self._scale_y),
                round((ghost[2] - ghost[0]) * self._scale_x),
                round((ghost[3] - ghost[1]) * self._scale_y),
            )
        painter.end()
        self.setPixmap(scaled)


    def _pen_width(self, logical: int | float) -> float:
        """叠加层线宽：取整到**设备像素**后再换算回逻辑宽度。

        ⚠️ Qt 用**逻辑**线宽 × dpr 得到设备线宽。不是整数设备像素时（125% 缩放
        下 2×1.25 = 2.5；150% 下选中态 3×1.5 = 4.5），光栅化对四条边的取整不一致
        ——实测同一个框会出现「上3 下3 左3 右2」这种**粗细不匀**。取整到设备像素
        后四条边一致（实测 dpr=1.0/1.25/1.5/2.0 全部均匀）。
        """
        dpr = self._dpr or 1.0
        return max(1.0 / dpr, round(float(logical) * dpr) / dpr)


    def _draw_reference_boxes(self, painter: QPainter) -> None:
        """参考框：按 area/border 规则推导的最终裁剪大框，橙色虚线。"""
        pen = QPen(REFERENCE_COLOR, self._pen_width(2), Qt.PenStyle.DashLine)
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
        # 名称/颜色**每帧现算**：整幅页恒为「整幅」；半幅页按中心位置定左右，
        # 因此拖动跨过中线的那一刻标签就换过来（不必等宿主回写）。
        size = (self._image_size.width(), self._image_size.height()) if self._image_size else None
        names, colors = box_styles(self._boxes, size, self._full_mode)
        for index, box in enumerate(self._boxes):
            x1, y1, x2, y2 = box
            color = colors[index] if index < len(colors) else BOX_COLORS[0]
            selected = index == self._selected
            # 选中的框加粗（3 逻辑像素），未选中 2；两者都取整到设备像素，
            # 否则高分屏下四边会粗细不均（见 _pen_width）
            pen = QPen(color, self._pen_width(3 if selected else 2))

            painter.setPen(pen)
            painter.drawRect(
                round(x1 * self._scale_x), round(y1 * self._scale_y),
                round((x2 - x1) * self._scale_x), round((y2 - y1) * self._scale_y),
            )
            name = names[index] if index < len(names) else BOX_NAMES[0]
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
                painter.drawRect(round(cx - r), round(cy - r), round(2 * r), round(2 * r))
            painter.setBrush(Qt.BrushStyle.NoBrush)


    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._rerender()


    def event(self, event) -> bool:  # noqa: N802
        """跨显示器拖动（dpr 变化）时按新 dpr 重画。

        Qt 在窗口 dpr 变化时发 ``DevicePixelRatioChange``，**不保证**同时发
        ``resizeEvent``。不接这个事件的话，把窗口从 100% 屏拖到 200% 屏，
        图会一直停在按旧 dpr 出的那版（明显发糊），要等下次换页才恢复。
        """
        if event.type() == QEvent.Type.DevicePixelRatioChange and self._pixmap:
            self._rerender()
        return super().event(event)
