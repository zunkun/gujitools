# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""工具提交：文字块。"""
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
from .jobs import _render_text_payload

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._host import DialogHost
else:
    DialogHost = object



class TextCommitMixin(DialogHost):
    """工具提交：文字块。"""


    # ------------------------------------------------------------ 文字
    def _spawn_text_block(self, pos: QPointF) -> None:
        """文字工具点击落点 → 画布上生成文字块就地编辑（光标可见）。"""
        if self._image is None or self._image.isNull():
            return
        self.canvas.add_text_block(
            pos, self._text_size, QColor(self._text_color),
            self._text_family,
        )


    def _text_payload(self) -> list:
        """摘走画布上的非空文字块，返回可重放的 ``(pos,text,px,color,family)``。

        「完成」的**后台应用**要用两段式：关窗前先把块摘下来（画布立即干净、
        ``_commit_crop`` 拿到的是干净图），烘焙完成后在回调里重放到最终图上
        （普通路径由 :meth:`_commit_text_blocks` 一次做完，语义不变）。
        """
        if not hasattr(self, "canvas"):
            return []
        blocks = self.canvas.text_blocks()
        payload = [
            (b.pos(), b.toPlainText(), b.font().pixelSize(),
             QColor(b.defaultTextColor()), b.font().family())
            for b in blocks if b.toPlainText().strip()
        ]
        self.canvas.clear_text_blocks()
        return payload

    def _commit_text_blocks(self) -> None:
        """把画布上非空文字块写进图片（一个批次一个撤销点），然后清块。"""
        payload = self._text_payload()
        if not payload or self._image is None or self._image.isNull():
            return
        self._push_undo(STEP_TEXT)
        for pos, text, px, color, family in payload:
            self._image = draw_text(
                self._image, pos, text, px, color, family)
        self._content_pixels_dirty = True   # 文字改了像素：upright 缓存作废
        self.canvas.replace_image(self._image)

    def _apply_text_payload(self, payload: list, image: QImage) -> QImage:
        """把 :meth:`_text_payload` 摘走的文字块重放到 ``image`` 上。

        ⚠️ 只碰像素（``draw_text`` 纯 QPainter），不碰撤销栈与画布——调用
        方是「完成」的完成回调（弹窗已关、栈已无用），**普通路径不走这里**
        （那边走 :meth:`_commit_text_blocks`，带撤销点）。
        """
        if image is None or image.isNull():
            return image
        return _render_text_payload(image, payload)
