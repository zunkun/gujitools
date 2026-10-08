# -*- coding: utf-8 -*-
"""画布 Mixin：GIMP 风格的笔刷扭曲笔划。

拖动时**只累加位移场**（纯加减法，实测 0.08 ms/落点），显示用的预览按
16 ms 节流、每帧只重渲染鼠标这一帧扫过的那一小块；松手时渲染一次
**笔划包围盒**。因此：

- 拖动过程中没有"算不动"的帧；
- 松手提交的成本只跟笔划覆盖了多大面积有关，**与拖动时长无关**（旧实现
  是每个落点都把整个圆盘重采样一遍，一笔 30 秒要 66 秒才算完）。

预览与提交共用同一张场，所以预览看到的就是最终结果（只是分辨率低一档）。
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPointF, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QImage, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QGraphicsPixmapItem

from ..bake import run_with_progress
from ..consts import (
    DISTORT_PREVIEW_PIXELS, DISTORT_PREVIEW_RENDER_PIXELS,
    DISTORT_PREVIEW_TILE, DISTORT_PREVIEW_TILES_PER_TICK,
    DISTORT_SYNC_RENDER_PIXELS,
)
from ..distortion import (
    StrokeField, StrokeSampler, render_rect_into, render_stroke_field,
)


if TYPE_CHECKING:
    from ._host import CanvasHost
else:
    CanvasHost = object


class DistortionMixin(CanvasHost):
    """局部笔刷形变：拖动走位移场预览，松手只渲染笔划包围盒，每笔一个撤销点。"""

    def set_distortion_options(self, **options: Any) -> None:
        """更新扭曲参数，并将各值限制在界面允许范围内。"""
        if "size" in options:
            self._distort_size = max(4, min(600, int(options["size"])))
            if self._tool == "distort" and any(
                    item.isVisible() for item in self._eraser_ring):
                self._move_eraser_ring(self._eraser_pos)
        if "hardness" in options:
            self._distort_hardness = max(0, min(100, int(options["hardness"])))
        if "strength" in options:
            self._distort_strength = max(0, min(100, int(options["strength"])))
        if "spacing" in options:
            self._distort_spacing = max(1, min(100, int(options["spacing"])))
        if "mode" in options:
            new_mode = str(options["mode"])
            if new_mode != self._distort_mode and self._distort_field is not None:
                # 场的"类型"（几何/混合）在开笔时就定下了，中途换模式会把
                # 两种语义混进同一张场 ⇒ 先把当前这一笔收干净。
                self._finish_distortion_stroke()
            self._distort_mode = new_mode
        if "interpolation" in options:
            self._distort_interpolation = str(options["interpolation"])
        if "high_quality_preview" in options:
            self._distort_high_quality_preview = bool(
                options["high_quality_preview"])
        if "realtime" in options:
            self._distort_realtime = bool(options["realtime"])

    # ------------------------------------------------------------ 起笔
    def _begin_distortion_stroke(self, pos: QPointF) -> None:
        """备份笔划起点图像，开一张位移场，并按需建低分辨率预览层。"""
        if self._distort_busy:
            return  # 上一笔还在提交，别叠进来
        if self._image is None or self._image.isNull():
            return
        if not self.image_rect().contains(pos):
            return
        self._distort_stroke_origin = self._image.copy()
        self._distort_sampler = StrokeSampler(self._distort_size,
                                              self._distort_spacing)
        self._distort_field = None
        self._distort_preview_dirty_rect = None
        self._distort_preview_pending_end = None
        if self._distort_realtime:
            self._create_distortion_preview()
        # 落笔这一刻就要吃掉第一个落点：径向/旋涡类模式在这里就生效
        # （move 因位移为零自然没有影响）。
        assert self._distort_sampler is not None
        self._accumulate(self._distort_sampler.start((pos.x(), pos.y())))

    def _start_distortion_field(self) -> None:
        """按图像尺寸建位移场（延迟到第一次真正落点时才建）。"""
        if self._distort_field is not None or self._image is None:
            return
        self._distort_field = StrokeField(
            self._image.width(), self._image.height(), self._distort_mode)

    def _create_distortion_preview(self) -> None:
        """创建低分辨率浮层；大图的逐帧计算量限制在固定像素预算内。"""
        if self._image is None or self._image.isNull():
            return
        width, height = self._image.width(), self._image.height()
        scale = min(1.0, math.sqrt(
            DISTORT_PREVIEW_PIXELS / max(1, width * height)))
        preview_width = max(1, round(width * scale))
        preview_height = max(1, round(height * scale))
        if preview_width * preview_height > DISTORT_PREVIEW_PIXELS:
            correction = math.sqrt(
                DISTORT_PREVIEW_PIXELS
                / (preview_width * preview_height))
            preview_width = max(1, int(preview_width * correction))
            preview_height = max(1, int(preview_height * correction))
        if preview_width == width and preview_height == height:
            preview_origin = self._image.copy()
        else:
            preview_origin = self._image.scaled(
                QSize(preview_width, preview_height),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._distort_preview_origin = preview_origin
        self._distort_preview_image = preview_origin.copy()
        self._distort_preview_scale_x = preview_width / width
        self._distort_preview_scale_y = preview_height / height
        if self._distort_preview_timer is None:
            timer = QTimer(self)
            timer.setInterval(16)
            timer.timeout.connect(self._on_distortion_preview_tick)
            self._distort_preview_timer = timer

    # ------------------------------------------------------------ 落点
    def _accumulate(self, stamps: Any) -> None:
        """把新落点累加进场，并记下这一帧要重渲染的预览区域。"""
        if not stamps:
            return
        self._start_distortion_field()
        field = self._distort_field
        if field is None:
            return
        for cx, cy, dx, dy in stamps:
            field.add_stamp(cx, cy, dx, dy, self._distort_size,
                            self._distort_hardness, self._distort_strength)
        if self._distort_preview_image is None:
            return
        # ⚠️ 场是**双线性**取样的：落点改了场里 1 格，会波及离它 1 格的取样点
        #    （图像单位 = 1/预览尺度）。脏区必须把这圈外扩算进去，否则预览在
        #    笔划边缘留下一圈"没跟上"的旧像素。
        halo = 2.0 / max(1e-6, self._distort_preview_scale_x)
        radius = max(1.0, self._distort_size / 2.0) + halo
        for cx, cy, _dx, _dy in stamps:
            self._queue_distortion_preview(cx, cy, radius)

    def _apply_distortion_segment(self, start: QPointF, end: QPointF) -> None:
        """吃掉一段鼠标位移：重采样成落点、累加进场、标记预览脏区。"""
        sampler = self._distort_sampler
        if sampler is None:
            return
        self._accumulate(sampler.extend((end.x(), end.y())))

    def _distort_segment(self, start: QPointF, end: QPointF) -> None:
        """记录鼠标轨迹：累加落点，预览重渲染交给 16 ms 节流器。"""
        if self._distort_stroke_origin is None:
            self._begin_distortion_stroke(start)
        if self._distort_stroke_origin is None:
            return
        self._apply_distortion_segment(start, end)
        if not self._distort_realtime:
            return
        self._distort_preview_pending_end = QPointF(end)
        if (self._distort_preview_timer is not None
                and not self._distort_preview_timer.isActive()):
            self._distort_preview_timer.start()

    # ------------------------------------------------------------ 预览
    def _queue_distortion_preview(
        self, center_x: float, center_y: float, radius: float,
    ) -> None:
        """把一个落点足迹（图像坐标）并进"本帧要重渲染"的矩形。"""
        scale_x = self._distort_preview_scale_x
        scale_y = self._distort_preview_scale_y
        left = (center_x - radius) * scale_x
        top = (center_y - radius) * scale_y
        right = (center_x + radius) * scale_x
        bottom = (center_y + radius) * scale_y
        rect = self._distort_preview_dirty_rect
        if rect is None:
            self._distort_preview_dirty_rect = [left, top, right, bottom]
            return
        rect[0] = min(rect[0], left)
        rect[1] = min(rect[1], top)
        rect[2] = max(rect[2], right)
        rect[3] = max(rect[3], bottom)

    def _flush_distortion_preview(self) -> None:
        """每帧只重渲染"刚被落点扫过"的那块矩形，再上传受影响的瓦片。

        ⚠️ 两处上限，缺一个都会卡：
        - **渲染**：脏区可以一下子很大（鼠标猛地一跳，或系统把一串 move 并成
          一个事件），一次渲染完就是一帧可感知的卡顿。超预算的部分**整段留给
          下一次 tick**，所以每帧成本恒定；优先渲染"离鼠标近"的那一段，光标
          下方永远是最新的。
        - **上传**：脏区横跨的瓦片可能很多，交给
          :meth:`_upload_distortion_tiles` 按 :data:`DISTORT_PREVIEW_TILES_PER_TICK`
          限量。
        """
        image = self._distort_preview_image
        origin = self._distort_preview_origin
        field = self._distort_field
        dirty = self._distort_preview_dirty_rect
        self._distort_preview_dirty_rect = None
        if image is None or origin is None or field is None or dirty is None:
            return
        tile = DISTORT_PREVIEW_TILE
        left = max(0, int(math.floor(dirty[0])))
        top = max(0, int(math.floor(dirty[1])))
        right = min(image.width(), int(math.ceil(dirty[2])) + 1)
        bottom = min(image.height(), int(math.ceil(dirty[3])) + 1)
        if right <= left or bottom <= top:
            return
        # ---- 渲染预算：本帧最多渲染这么多行，剩下的挂回脏矩形
        max_rows = max(1, DISTORT_PREVIEW_RENDER_PIXELS // (right - left))
        if bottom - top > max_rows:
            end = self._distort_preview_pending_end
            cursor_y = (end.y() * self._distort_preview_scale_y
                        if end is not None else (top + bottom) / 2.0)
            if cursor_y > (top + bottom) / 2.0:      # 光标在下半段：先渲染下面
                cut = bottom - max_rows
                self._distort_preview_dirty_rect = [left, top, right, cut]
                top = cut
            else:                                     # 光标在上半段：先渲染上面
                cut = top + max_rows
                self._distort_preview_dirty_rect = [left, cut, right, bottom]
                bottom = cut
            if bottom <= top:
                return
        render_rect_into(image, origin, field, self._distort_preview_scale_x,
                         (left, top, right, bottom),
                         self._distort_preview_filter())
        for ty in range(top // tile, (bottom - 1) // tile + 1):
            for tx in range(left // tile, (right - 1) // tile + 1):
                self._distort_preview_dirty_tiles.add((tx, ty))
        self._upload_distortion_tiles()

    def _upload_distortion_tiles(self) -> None:
        """把待上传瓦片贴进场景，每次最多 :data:`DISTORT_PREVIEW_TILES_PER_TICK` 块。"""
        image = self._distort_preview_image
        if image is None:
            self._distort_preview_dirty_tiles.clear()
            return
        tile = DISTORT_PREVIEW_TILE
        scale_x = self._distort_preview_scale_x
        scale_y = self._distort_preview_scale_y
        budget = DISTORT_PREVIEW_TILES_PER_TICK
        while self._distort_preview_dirty_tiles and budget > 0:
            tx, ty = self._distort_preview_dirty_tiles.pop()
            budget -= 1
            core_left, core_top = tx * tile, ty * tile
            left, top = max(0, core_left - 1), max(0, core_top - 1)
            right = min(image.width(), core_left + tile + 1)
            bottom = min(image.height(), core_top + tile + 1)
            if right <= left or bottom <= top:
                continue
            piece = image.copy(QRect(left, top, right - left, bottom - top))
            item = self._distort_preview_items.get((tx, ty))
            if item is None:
                item = QGraphicsPixmapItem()
                item.setTransformationMode(
                    Qt.TransformationMode.SmoothTransformation)
                item.setZValue(6)
                self._scene.addItem(item)
                item.setTransform(QTransform().scale(1.0 / scale_x,
                                                     1.0 / scale_y))
                item.setPos(left / scale_x, top / scale_y)
                self._distort_preview_items[(tx, ty)] = item
            item.setPixmap(QPixmap.fromImage(piece))
        if self._distort_preview_dirty_tiles \
                and self._distort_preview_timer is not None:
            self._distort_preview_timer.start()  # 还有没传完的，下一帧接着传

    def _clear_distortion_preview(self) -> None:
        """移除扭曲预览瓦片并释放缩小图缓存。"""
        if self._distort_preview_timer is not None:
            self._distort_preview_timer.stop()
        self._distort_preview_dirty_tiles.clear()
        self._distort_preview_dirty_rect = None
        self._distort_preview_pending_end = None
        for item in self._distort_preview_items.values():
            self._scene.removeItem(item)
        self._distort_preview_items.clear()
        self._distort_preview_origin = None
        self._distort_preview_image = None
        self._distort_preview_scale_x = 1.0
        self._distort_preview_scale_y = 1.0

    def _distort_preview_filter(self) -> str:
        if not self._distort_high_quality_preview:
            return "nearest"
        # 实时预览用线性采样，最终提交仍严格使用所选插值；三次插值留给
        # 全分辨率结果，避免高质量预览在每个拖动帧上做 16 次邻域采样。
        return ("linear" if self._distort_interpolation == "cubic"
                else self._distort_interpolation)

    def _on_distortion_preview_tick(self) -> None:
        """节流：最多每帧一次把积累的脏区重渲染并上传。"""
        if self._distort_stroke_origin is None or not self._distort_realtime:
            if self._distort_preview_timer is not None:
                self._distort_preview_timer.stop()
            self._flush_distortion_preview()
            return
        self._flush_distortion_preview()
        if (self._distort_preview_dirty_rect is None
                and not self._distort_preview_dirty_tiles
                and self._distort_preview_timer is not None):
            self._distort_preview_timer.stop()

    # ------------------------------------------------------------ 收笔
    def _render_distortion_field(self) -> QImage | None:
        """把场渲染成全分辨率结果；区域大时移入可取消的后台计算。"""
        if self._image is None or self._distort_field is None:
            return None
        field = self._distort_field
        rect = field.active_rect(self._image.width(), self._image.height())
        if rect is None:
            return None
        interpolation = self._distort_interpolation
        origin = self._distort_stroke_origin
        area = (rect[2] - rect[0]) * (rect[3] - rect[1])
        if area <= DISTORT_SYNC_RENDER_PIXELS:
            return render_stroke_field(self._image, field, interpolation, origin)

        def work(values: dict, progress):
            return render_stroke_field(values["image"], values["field"],
                                       values["interpolation"],
                                       values["origin"], progress=progress)

        return run_with_progress(
            self, "扭曲处理中", "正在生成全分辨率笔划…", work,
            {"image": self._image, "field": field,
             "interpolation": interpolation, "origin": origin})

    def _finish_distortion_stroke(self) -> None:
        """全分辨率提交笔划、移除预览层，并清理临时状态。

        ⚠️ 提交失败（爆内存 / 后台线程抛错）**绝不能把异常放出去**：异常逃出
        ``mouseReleaseEvent`` 只会打一行 stderr 就继续跑，而这时 ``_mode``、
        ``_distort_stroke_origin``、预览瓦片全停在半路，用户看到的是"拖一次
        就废了"。这里一律把这一笔退回起点图、再复位状态。
        """
        if self._distort_stroke_origin is None:
            return
        self._distort_busy = True
        origin = self._distort_stroke_origin
        try:
            if self._distort_sampler is not None:
                self._accumulate(self._distort_sampler.flush())
            if self._distort_realtime:
                self._flush_distortion_preview()
            result = self._render_distortion_field()
            if result is not None and self._image is not None:
                self.stroke_started.emit()  # 完成计算后再压撤销点，取消不留空撤销步
                painter = QPainter(self._image)
                painter.setCompositionMode(
                    QPainter.CompositionMode.CompositionMode_Source)
                painter.drawImage(0, 0, result)
                painter.end()
                self.refresh()
        except BaseException as exc:  # noqa: BLE001（兜底：不许逃出事件处理器）
            if self._image is not None:
                self._image = origin.copy()
                self.refresh()
            self._report_distortion_failure(exc)
        finally:
            self._clear_distortion_preview()
            self._distort_stroke_origin = None
            self._distort_field = None
            self._distort_sampler = None
            self._distort_busy = False
            self._move_eraser_ring(self._eraser_pos, show=self._tool == "distort")

    def _report_distortion_failure(self, exc: BaseException) -> None:
        """把提交失败说出来（否则用户只看到"点了没反应"）。"""
        from desktop.ui.toast import show_toast

        show_toast(self, "error", "扭曲没能应用",
                   f"本笔已退回起点：{type(exc).__name__}: {exc}")
