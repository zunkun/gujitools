# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""工具提交：裁剪。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QTransform
from PySide6.QtWidgets import QApplication, QProgressDialog

from desktop.workers.worker_host import connect_queued
from ..bake import _BakeWorker, run_with_progress
from ..consts import (
    CLIPPING_DEFAULT, DIRECTION_DEFAULT, DISTORT_SYNC_RENDER_PIXELS,
    INTERPOLATION_DEFAULT, STEP_CROP, STEP_DISTORT, STEP_ERASE, STEP_FLIP,
    STEP_TEXT, STEP_TRANSFORM, TRANSFORM_SYNC_RENDER_PIXELS,
)
from ..content_quad import quad_frame, read_quad, sync_content_quad, upright_image
from ..geometry import (
    center_crop_aspect, clamp_rect, compose_transform, draw_text,
)
from .jobs import _same_rect

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._host import DialogHost
else:
    DialogHost = object



class CropCommitMixin(DialogHost):
    """工具提交：裁剪。"""


    # ------------------------------------------------------------ 应用
    def _selection(self) -> QRectF | None:
        rect = self.canvas.selection()
        if rect is None:
            return None
        return clamp_rect(rect, self.canvas.image_rect())


    # ------------------------------------------------------------ 裁剪（待定 → 落定）
    def _preview_crop(self) -> None:
        """裁剪框拖完松手：**只记下选区**，一个像素都不动。

        ⚠️⚠️ 非破坏性裁剪（用户 2026-10-10 报障：「裁剪线可以向内移动也可以
        向外移动，向外移动，原本被隐藏的区域要显示出来」）。旧版在这里直接
        ``self._image.copy(rect)`` 把图裁小、画布换图并把选区重置成新图的
        整幅——于是**第二次拖动时手柄已经压在边界上，向外无处可拖**，系统里
        根本没有"还没落定"这个中间态（想找回只能 Ctrl+Z 或点历史某一格）。

        现在裁剪是**待定**的：

        - 松手只写 ``_pending_crop`` + 刷右下角的尺寸提示；
        - 拖动框内会预览整张图片与选区一起平移；选区外那 4 块半透明遮罩每帧按选区重算
          （``overlay._sync_overlay``）⇒ 向外拖时被变暗的区域立刻重新显露；
        - 真正的 ``copy()`` 推迟到 :meth:`_commit_crop`（切走裁剪工具 / 点
          「完成」），一次落定 = 一个撤销点。

        选区就是整幅且图片没有位移时当成"没裁"，把待定清掉。图片有位移时，
        应用会扩展画布并保留透明边距，以便位移写入图片文件。
        """
        rect = self._selection()
        if rect is None:
            return  # 选区被拖成 <MIN_RECT_EDGE 的废框：不动任何东西
        offset = self.canvas.crop_offset()
        if _same_rect(rect, self.canvas.image_rect()) \
                and offset == QPointF():
            self._discard_crop()
            return
        self._pending_crop = QRectF(rect)
        self._pending_crop_offset = (offset.x(), offset.y())
        self._refresh_size_label()


    def _commit_crop(self) -> None:
        """把**待定**裁剪真正落到像素上（切走裁剪工具 / 点「完成」时各调一次）。

        GIMP 口径："带着未确认的裁剪切走工具 = 确认这次裁剪"。不定这条规则
        的话两头都不对——切到擦除/变换时画布上还是整幅原图，用户以为裁剪丢了；
        而留在裁剪工具里又永远落不了地。

        没有待定裁剪就**直接返回**（连选区都不动：切功能不该顺手清掉用户的框）。
        """
        rect = getattr(self, "_pending_crop", None)
        if rect is None or self._image is None or self._image.isNull():
            return
        offset_x, offset_y = getattr(self, "_pending_crop_offset", (0.0, 0.0))
        self._pending_crop = None
        self._pending_crop_offset = (0.0, 0.0)
        shift_x, shift_y = round(offset_x), round(offset_y)
        source_rect = QRectF(rect).translated(-shift_x, -shift_y)
        # 选区和图片一起移动；换回源图坐标后裁切，再用透明边距编码图片位移。
        # toRect() 向外取整，再与源图矩形求交以兜住取整后越界 1px。
        box = source_rect.toRect().intersected(self._image.rect())
        if box.isEmpty():
            self.canvas.reset_selection()
            return
        pad_x, pad_y = max(0, shift_x), max(0, shift_y)
        result_width = box.width() + abs(shift_x)
        result_height = box.height() + abs(shift_y)
        self._push_undo(STEP_CROP)
        if box != self._image.rect() or shift_x or shift_y:
            # ⚠️ 真裁了（尺寸变了）：内容四边形 (rect0, V) 对新尺寸的像素
            #    不再成立，整组作废——切回「统一变换」退回整幅矩形框架，
            #    宁可不恢复也不能错恢复（用户 2026-10-10 口径「边缘变了
            #    就不恢复」）。选区＝整幅的"裁剪"像素没变，节点保留。
            self._content_clear()
        cropped = self._image.copy(box)
        if shift_x or shift_y:
            shifted = QImage(
                result_width, result_height,
                QImage.Format.Format_ARGB32_Premultiplied,
            )
            shifted.fill(Qt.GlobalColor.transparent)
            painter = QPainter(shifted)
            painter.drawImage(QPoint(pad_x, pad_y), cropped)
            painter.end()
            self._image = shifted
        else:
            self._image = cropped
        # ⚠️⚠️ 原点累加的量必须让 **sheet 映射**（:meth:`_scene_to_sheet`：
        #    ``sheet = rect + (画布坐标 + origin) * scale``）在提交裁剪前后
        #    **完全一致**——活动层自己是绝对基准（不受切层换人影响），这是唯一
        #    无歧义的判据。提交后可见内容画在画布 ``pad`` 处、对应初始像素
        #    ``box``；提交前它位于 ``box + shift``。两式相等 ⇒
        #        **origin 增量 = box + shift - pad**
        #    正位移（``pad == shift``）⇒ 增量 == ``box``：位移已由透明留白烤进
        #    像素，origin 不能再动一次；纯裁剪（``shift == pad == 0``）⇒ ``box``，
        #    既有断言 ``origin==(20,10)`` 不受影响。
        # ⚠️ 2026-10-15 用户报障「裁剪功能里拖动图片，无论多远都弹回原样」：
        #    本行一度被改成 ``box - pad``，正位移时等于 ``box - shift``、比正确
        #    值少 ``2*shift``，位移被**整个抵消**（实测拖 70px 后提交，内容
        #    sheet_left 由 40.7 弹回 0.0）。旧式 ``box + shift`` 则是正位移
        #    过冲 ``2*shift``。两个都错在把 ``shift`` 项算错一次。
        #    判据＝活动层可见内容左边缘的 sheet x 提交前后相等（±取整残差）。
        self._multi_layer_shift(
            float(box.x() + shift_x - pad_x),
            float(box.y() + shift_y - pad_y),
        )
        # ⚠️ 双图模式换图**不**重新适应窗口（世界缩放保持，2026-10-13
        #    「不要放大缩小」）；单图维持"裁完 fit 一遍"的旧行为。
        self.canvas.set_image(self._image, refit=not self._multi_layers)
        if getattr(self, "_multi_layers", None):
            self._refresh_multi_canvas()
        self._refresh_size_label()


    def _discard_crop(self) -> None:
        """丢掉待定裁剪、选区弹回整幅；像素本来就没动过，**不产生撤销点**。

        Ctrl+Z / Ctrl+Y / 「还原」/ 参数页「重置选区」都走这里（见
        ``dialog_undo``：有待定裁剪时按键先退它，再按一次才动历史）。
        """
        had = getattr(self, "_pending_crop", None) is not None
        self._pending_crop = None
        self._pending_crop_offset = (0.0, 0.0)
        if had:
            self.canvas.reset_selection()
        self._refresh_size_label()


    # ------------------------------------------------------------ 一笔开始
    def _on_stroke_started(self) -> None:
        """画布上一笔开始（擦除 / 扭曲提交）：压撤销点，步骤名按当前工具取。

        橡皮擦在**按下时**就发 ``stroke_started``；扭曲在**松手提交前**发
        （见 ``DistortionMixin._finish_distortion_stroke``）。两条路都要求
        "先压点、后改像素"，所以统一在这里按工具分流取名。
        """
        label = STEP_DISTORT if self.canvas.tool == "distort" else STEP_ERASE
        self._push_undo(label)
        # ⚠️ 擦除/扭曲**真的改像素**（擦除原地画、扭曲整幅重采样）：upright
        #    缓存作废，下次进「统一变换」要从当前画布重算（2026-10-11 脏位）
        self._content_pixels_dirty = True
