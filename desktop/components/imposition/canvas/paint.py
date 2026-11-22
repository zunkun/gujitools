# -*- coding: utf-8 -*-
"""拼版画布的**渲染**：贴图、选中框、旋转钮、对齐线与截图范围框
（``_PaintMixin``）。

Mixin 只在运行期与 ``ImpositionCanvas`` 组合；宿主面见 :mod:`._host`，本模块
**不 import** 主类 ``widget``，避免循环导入。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from desktop.components.imposition.canvas._qt import (
    QColor,
    QImage,
    QPainter,
    QPen,
    QPointF,
    QRectF,
    Qt,
)
from desktop.components.imposition.canvas.constants import (
    CROP_COLOR,
    DISPLAY_EDGE_STEPS,
    FRAME_COLOR,
    FRAME_STYLE,
    HANDLE_FILL,
    HANDLE_RADIUS,
    HANDLE_STROKE,
    ROTATE_ARC_BARB,
    ROTATE_ARC_GAP,
    ROTATE_ARC_SPAN,
    ROTATE_ARC_START,
    ROTATE_KNOB_GAP,
    ROTATE_KNOB_RADIUS,
    SPINE_COLOR,
)
from desktop.components.imposition.canvas.images import _trim_transparent_border
from desktop.utils.image_scaling import smooth_downscale

if TYPE_CHECKING:
    from desktop.components.imposition.canvas._host import CanvasHost as _Host
else:
    _Host = object


class _PaintMixin(_Host):
    """``paintEvent`` 与各图层绘制，及贴图底图的分档缓存。"""

    def _spine_visible(self) -> bool:
        """红色对齐线要不要画：两图页恒显；**单图页只认横图（宽>高）**。

        单图页判据走**源图的宽高比**而不是文件名后缀（用户 2026-09-30 晚：
        「单独一张半页图片在某页，不需要显示中间红线」）——实际任务里
        **没有 ``-l``/``-r`` 后缀的竖图也可能是半页**（整幅误检、封面插页、
        单页扫描），文件名认不出来，而半页/单页图恒为竖图（高≥宽）、
        整幅对开页恒为横图（宽>高，见任务 0007 实测 1917×1410）。
        尺寸读不到（文件已丢）不画——宁可少画也不画误导线。
        """
        if len(self._items) >= 2:
            return True
        if len(self._items) == 1:
            size = self._image_size(self._items[0]["file"])
            return size is not None and size[0] > size[1]
        return False

    # ------------------------------------------------------------------ 渲染
    def _image(self, path: str) -> QImage | None:
        """按路径懒加载 QImage（同一路径只解码一次）。

        ⚠️ **裁掉四周纯透明的边**（2026-10-14 用户报障「编辑保存后拼版页
        图片与虚线框错位」）：图片编辑器的裁剪移动把位移编码成**透明边距**，
        像素图因此变大而可见内容缩在某个角上。版面 ``rect`` 按可见内容记
        （见 ``services.imposition.refresh_rects_for_edited_source``），
        ``_draw_item`` 又把整张图 ``drawImage`` 进 rect ⇒ 不裁的话屏幕上
        框贴着（含留白的）整张图、内容却偏在一角，看着就是"图与框错位"，
        导出侧 :func:`compose_page` 也会把内容压扁。两边必须同口径。
        整幅不透明时 alpha 不透明、裁剪区等于整张 ⇒ 直接返回原图，零行为变化。
        """
        if not path:
            return None
        cached = self._images.get(path)
        if cached is not None:
            return cached
        image = QImage(path)
        if image.isNull():
            return None
        image = _trim_transparent_border(image)
        self._images[path] = image
        return image

    def _image_size(self, path: str) -> tuple[int, int] | None:
        image = self._image(path)
        if image is None:
            return None
        return image.width(), image.height()

    def _display_image(self, path: str, need_edge: float) -> QImage | None:
        """贴图底图：按**屏幕实际需要的边长**从 ``DISPLAY_EDGE_STEPS`` 取档预缩。

        键含档位：拖动/旋转期间屏幕尺寸不变 ⇒ 只做一次廉价平滑贴图；滚轮
        缩放跨档（600/1200/2400）才重算一次。连发滚动期间**不重建**——大图
        重采样会把这一帧拖长，先用已有的最近档凑合（下一帧高质量重绘兜底）。
        """
        image = self._image(path)
        if image is None or image.isNull():
            return None
        longest = max(image.width(), image.height())
        step = next((s for s in DISPLAY_EDGE_STEPS if s >= need_edge), 0)
        if step == 0 or step >= longest:
            return image  # 需要的已超过最大档 / 原生都不够缩：直接用原生
        key = (path, step)
        cached = self._display_cache.get(key)
        if cached is not None:
            return cached
        if self._wheel_burst:
            fallback = [
                value for (cached_path, _s), value in self._display_cache.items()
                if cached_path == path
            ]
            if fallback:
                return fallback[-1]
        display = smooth_downscale(image, step)
        self._display_cache[key] = display
        return display

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        # 滚轮连发期间走快速档（不做平滑采样，大图缩放的重头开销在这）；
        # 停稳后由 _on_wheel_frame 关掉快速档并补一帧高质量重绘
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform, not self._wheel_burst
        )
        # 纯白底（用户口径：拼版不需要纸张，白底就行）——没有纸张矩形要画，
        # 控件自身的样式表已经是白的。
        # 选中的那张图**永远画在最上面**（用户 2026-10-10：类似 CSS 里
        # zIndex 更大）——两图重叠时，被压住的那张一旦选中就得浮上来，
        # 否则看不清在操作哪张。其余仍按清单顺序画（落盘/合成顺序不变，
        # 这是纯显示层的拾升）。
        selected = (
            self._selected if 0 <= self._selected < len(self._items) else None
        )
        for index, item in enumerate(self._items):
            if index != selected:
                self._draw_item(painter, index, item)
        if selected is not None:
            self._draw_item(painter, selected, self._items[selected])
        # 红色对齐线（用户 2026-09-30）：两图公共中心所在竖线，**恒显**——
        # 不管有没有选中、有没有在拖动，它都在；整版旋转时拿它当对比基准。
        # ⚠️ 单图页只认横图（源图宽>高；2026-09-30 晚用户定：单张半页图
        # ——包括无 -l/-r 后缀的竖图——不画红线；单张整幅对开仍要），
        # 见 _spine_visible。
        if self._items:
            if self._spine_visible():
                center_x, _ = self._spread_center_units()
                x = self._off_x + center_x * self._px_per_unit
                # 宽度 1.0（用户 2026-09-30：1.5 的红线渲染出来约 2px，嫌太宽）
                painter.setPen(QPen(SPINE_COLOR, 1.0, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(
                    QPointF(x, 0.0), QPointF(x, float(self.height()))
                )
            # 成品截图范围框（用户 2026-09-30）：两图外接框并集的灰虚线，
            # **恒显**——产出图就是这块范围的紧裁，旋转/挪动时它跟着变。
            self._draw_crop_frame(painter)
        # 框线分两态（用户 2026-09-30）：按住操作期间画**带手柄的完整框**；
        # 平时选中的那张图带**常显细虚线**（选中状态）。没选中的图永远干净。
        if self.frame_visible():
            self._draw_frame(painter, self._selected)
        elif 0 <= self._selected < len(self._items):
            self._draw_selected_border(painter, self._selected)
        painter.end()

    def _draw_crop_frame(self, painter: QPainter) -> None:
        """画**成品截图范围**虚线框：两图旋转后外接框的并集。

        「上下左右四个方向最外面点组成的框」（用户 2026-09-30 口径）——
        ``_item_box_units`` 与 ``services.imposition.page_bounds`` 是同一套
        几何：画布上这个框里有什么，产出图就是什么。
        """
        boxes = [self._item_box_units(item) for item in self._items]
        left = min(b[0] for b in boxes)
        top = min(b[1] for b in boxes)
        right = max(b[2] for b in boxes)
        bottom = max(b[3] for b in boxes)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(CROP_COLOR, 1.2, FRAME_STYLE, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        painter.drawRect(QRectF(
            self._off_x + left * self._px_per_unit,
            self._off_y + top * self._px_per_unit,
            (right - left) * self._px_per_unit,
            (bottom - top) * self._px_per_unit,
        ))

    def _draw_item(self, painter: QPainter, index: int, item: dict) -> None:
        """画一张图：**只画图像，不画任何框线**（框线归 _draw_frame）。

        ⚠️ **不做裁剪**（用户 2026-09-30：「图片拉伸、移动后可能超出原本界限，
        现在是不显示了，现在不要限制」）：图可以拖/拉到任何位置，越界的部分也
        必须画出来。真正落到控件可视区之外的部分由 Qt 自己丢弃，那与"我们主动
        裁掉"是两回事。
        """
        r = self._rect_px(index)
        if r.width() <= 0 or r.height() <= 0:
            return
        painter.save()
        center = r.center()
        painter.translate(center)
        painter.rotate(float(item.get("rotation") or 0.0))
        image = self._image(item["file"])
        box = QRectF(-r.width() / 2, -r.height() / 2, r.width(), r.height())
        # 贴图用**已按屏幕需要的档位预缩**的底图（见 _display_image）：原图
        # 几千像素一次缩到几百像素是跳采样，古籍细笔画会发虚。
        dpr = self.devicePixelRatioF() or 1.0
        display = self._display_image(
            item["file"], max(r.width(), r.height()) * dpr
        )
        if display is not None and not display.isNull():
            painter.drawImage(box, display)
        elif image is not None and not image.isNull():
            painter.drawImage(box, image)
        else:
            painter.fillRect(box, QColor("#f0f2f5"))
        painter.restore()

    def _draw_frame(self, painter: QPainter, index: int) -> None:
        """按住期间画的选中框：**虚线**矩形 + 四角四边手柄 + 旋转钮。

        ⚠️ 框与手柄**跟着图一起转**（用户 2026-09-30：选中高亮虚线不随旋转
        是 bug）：在"平移到 rect 中心 + 旋转 rotation"的坐标系里画，与
        ``_draw_item`` 的图像变换同一套。命中判定（``_hit_handle``）已在
        局部系里做，手柄画在哪就能在哪抓到。
        """
        r = self._rect_px(index)
        painter.save()
        painter.translate(r.center())
        painter.rotate(float(self._items[index].get("rotation") or 0.0))
        local = QRectF(
            -r.width() / 2.0, -r.height() / 2.0, r.width(), r.height()
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(FRAME_COLOR, 1.6, FRAME_STYLE, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        painter.drawRect(local)
        painter.setPen(QPen(HANDLE_STROKE, 1.5))
        painter.setBrush(HANDLE_FILL)
        for cx, cy in self._handle_positions_local(index):
            painter.drawRect(
                QRectF(cx - HANDLE_RADIUS, cy - HANDLE_RADIUS,
                       2 * HANDLE_RADIUS, 2 * HANDLE_RADIUS)
            )
        # 旋转钮：一条引线 + 一个圆钮（**画在框外、图片上方**）
        self._draw_rotate_knob(painter, r.height())
        painter.restore()

    def _draw_rotate_knob(self, painter: QPainter, height_px: float) -> None:
        """画框外上方的旋转钮（**选中后常显**，用户 2026-10-23）。

        用户口径：「可以在图片外面……哪个图片是选中的，就旋转哪个图片，
        鼠标左键旋转操作」——旋转抓手不能藏在图上，也不能只在按住时才出现：
        选中的那张图，框外上方一直挂着一个圆钮，左键拖它即绕图心旋转。

        ⚠️ 调用方的 painter 必须已**平移到 rect 中心并旋转该项角度**——钮与
        框同一套局部坐标（``_rotate_knob_local``），跟着图一起转。

        圆钮**外侧**环绕一段顺时针弧形箭头（用户 2026-11-02：画在圆里太小、
        看不清）；缺口留在下方，不压住引线。
        """
        knob = QPointF(0.0, -height_px / 2.0 - ROTATE_KNOB_GAP)
        painter.setPen(QPen(HANDLE_STROKE, 1.5))
        painter.drawLine(QPointF(0.0, -height_px / 2.0), knob)
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

    def _draw_selected_border(self, painter: QPainter, index: int) -> None:
        """选中态**常显**的细虚线框（用户 2026-09-30：点击某张图后它要有
        "选中状态"）：细边框 + **框外上方的旋转钮**；四角/四边手柄仍只在
        按住操作期间出现。

        ⚠️ 旋转钮必须**跟着常显**（用户 2026-10-23）：只在按住时画的钮等于
        没有——用户根本看不到抓手，也没法「在图片外面」按住左键拖它。
        ⚠️ 跟着图一起转（用户 2026-09-30：旋转后高亮框要贴着图像的边）。
        """
        r = self._rect_px(index)
        painter.save()
        painter.translate(r.center())
        painter.rotate(float(self._items[index].get("rotation") or 0.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(FRAME_COLOR, 1.2, FRAME_STYLE, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        painter.drawRect(QRectF(
            -r.width() / 2.0, -r.height() / 2.0, r.width(), r.height()
        ))
        self._draw_rotate_knob(painter, r.height())
        painter.restore()
