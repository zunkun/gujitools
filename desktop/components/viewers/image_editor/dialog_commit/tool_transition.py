# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""大图切走统一变换的后台过渡。"""
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
from .jobs import _transform_job, _transform_target_pixels

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._host import DialogHost
else:
    DialogHost = object



class ToolTransitionMixin(DialogHost):
    """大图切走统一变换的后台过渡。"""


    def _start_async_tool_transition(self, tool: str) -> bool:
        """对大图先后台烘焙；完成后再切工具，避免主线程同步等待。"""
        pending = self.canvas.transform_pending()
        if pending is None:
            return False
        rect, xf, region = pending
        if getattr(self.canvas, "_xf_direction", DIRECTION_DEFAULT) == "backward":
            inverse, ok = xf.inverted()
            if ok:
                xf = inverse
        clipping = getattr(self.canvas, "_xf_clipping", CLIPPING_DEFAULT)
        grow = clipping != "clip"
        upright = getattr(self, "_content_upright", None)
        original = (
            upright if getattr(self, "_content_restored", False)
            and upright is not None else self._image
        )
        target = _transform_target_pixels(original, rect, xf, grow)
        if target <= TRANSFORM_SYNC_RENDER_PIXELS:
            return False

        params = {
            "image": original,
            "rect": QRectF(rect),
            "xf": QTransform(xf),
            "region": QImage(region),
            "grow": grow,
            "clipping": clipping,
            "interpolation": getattr(
                self.canvas, "_xf_interpolation", INTERPOLATION_DEFAULT),
        }
        worker = _BakeWorker(_transform_job, params, self)
        progress = QProgressDialog(
            "正在应用变换；完成后将切换功能…", "取消", 0, 100, self)
        progress.setWindowTitle("变换处理中")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        progress.canceled.connect(worker.cancel)
        connect_queued(self, worker.ticked,
                       self._on_async_tool_transition_progress, worker)
        connect_queued(self, worker.finished,
                       self._on_async_tool_transition_finished, worker)

        self._tool_transition_worker = worker
        self._tool_transition_progress = progress
        self._tool_transition_target = tool
        self._tool_transition_data = (QRectF(rect), QTransform(xf),
                                      clipping, original)
        # grow（画布跟内容长）与否：完成回调里决定要不要平移双图内容原点
        self._tool_transition_grow = grow
        self._set_async_tool_transition_busy(True)
        worker.start()
        return True

    def _set_async_tool_transition_busy(self, busy: bool) -> None:
        """冻结会改动当前图像/变换的控件，进度框仍保持响应。"""
        widgets = [
            self.canvas, self.undo_btn, self.redo_btn, self.reset_btn,
            self.zoom_out_btn, self.zoom_in_btn, self.fit_btn, self.done_btn,
            self._option_page,
            *getattr(self, "_tool_buttons", {}).values(),
        ]
        for widget in widgets:
            if widget is not None:
                widget.setEnabled(not busy)

    def _on_async_tool_transition_progress(self, done: int, total: int) -> None:
        progress = getattr(self, "_tool_transition_progress", None)
        if progress is not None and total > 0:
            progress.setValue(min(100, int(done * 100 / total)))

    def _on_async_tool_transition_finished(self) -> None:
        worker = getattr(self, "_tool_transition_worker", None)
        if worker is None:
            return
        progress = getattr(self, "_tool_transition_progress", None)
        tool = getattr(self, "_tool_transition_target", "erase")
        data = getattr(self, "_tool_transition_data", None)
        assert data is not None
        rect, xf, clipping, original = data
        self._tool_transition_worker = None
        self._tool_transition_progress = None
        self._tool_transition_target = None
        self._tool_transition_data = None
        grow = getattr(self, "_tool_transition_grow", False)
        self._tool_transition_grow = False
        if progress is not None:
            progress.canceled.disconnect(worker.cancel)
            progress.close()
            progress.deleteLater()

        try:
            result = worker.result
            image = None if result is None else result[0]
            bake_origin = (0.0, 0.0) if result is None else (
                float(result[1][0]), float(result[1][1]))
            if worker.error is not None:
                from desktop.ui.toast import show_toast

                show_toast(
                    self, "error", "变换没能应用",
                    f"变换预览仍保留，可重试或重置："
                    f"{type(worker.error).__name__}: {worker.error}",
                )
            elif image is not None and not image.isNull():
                self._push_undo(STEP_TRANSFORM)
                self._image = image
                # 双图编辑：新画布原点平移要在压撤销点**之后**记账
                if grow:
                    self._multi_layer_shift(bake_origin[0], bake_origin[1])
                self.canvas.set_image(image, refit=False)
                if getattr(self, "_multi_layers", None):
                    self._refresh_multi_canvas()
                self._content_after_bake(rect, xf, clipping, original)
                self._refresh_size_label()
                self._activate_tool(tool)
                self._sync_undo_buttons()
                self._sync_history()
            elif not worker.cancelled:
                from desktop.ui.toast import show_toast

                show_toast(
                    self, "error", "变换没能应用",
                    "后台变换未返回结果；变换预览仍保留，可重试或重置。",
                )
            # 用户取消时保留未烘焙的变换预览，允许重试或重置。
        finally:
            self._set_async_tool_transition_busy(False)
            self._sync_undo_buttons()
            worker.deleteLater()
