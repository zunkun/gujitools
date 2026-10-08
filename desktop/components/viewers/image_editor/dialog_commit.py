# -*- coding: utf-8 -*-
"""``ImageEditorDialog`` Mixin：**工具提交**。

把画布上的临时状态烘焙进当前图像（含后台烘焙与失败提示）。（从 ``image_editor/dialog.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor
from .consts import (
    STEP_CROP, STEP_DISTORT, STEP_ERASE, STEP_TEXT, STEP_TRANSFORM,
)
from .geometry import bake_transform, clamp_rect, draw_text
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import DialogHost
else:
    DialogHost = object


class CommitMixin(DialogHost):
    """把画布上的临时状态烘焙进当前图像（含后台烘焙与失败提示）。"""

    # ------------------------------------------------------------ 应用
    def _selection(self) -> QRectF | None:
        rect = self.canvas.selection()
        if rect is None:
            return None
        return clamp_rect(rect, self.canvas.image_rect())


    def _apply_crop(self) -> None:
        """把图裁成当前选区（一步撤销点）。

        ⚠️ 裁剪**没有**「应用裁剪」按钮：画布拖完松手发 ``crop_committed``，
        弹窗直接调这里（松手即应用）。
        ⚠️ 选区就是整幅时**直接返回**：点一下不拖、或拖回原位，不该白压一个
        空撤销步、也不该换图（换图会把视图 fit 一遍，看起来像闪了一下）。
        """
        rect = self._selection()
        if rect is None or self._image is None:
            return
        full = self.canvas.image_rect()
        if (abs(rect.left() - full.left()) < 0.5
                and abs(rect.top() - full.top()) < 0.5
                and abs(rect.width() - full.width()) < 0.5
                and abs(rect.height() - full.height()) < 0.5):
            return
        self._push_undo(STEP_CROP)
        self._image = self._image.copy(rect.toRect())
        self.canvas.set_image(self._image)
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


    # ------------------------------------------------------------ 变换
    def _commit_transform(self) -> None:
        """把未应用的变换烘焙进图片（一个撤销点）；没有变换就只清预览。

        「应用变换」按钮、切走工具、「完成」都走这里——预览即所见，
        烘焙结果与浮层显示一致（原区域填白 + 变换后的选区内容）。
        """
        if not hasattr(self, "canvas"):
            return
        pending = self.canvas.transform_pending()
        if pending is None:
            self.canvas.reset_transform()
            return
        rect, xf, region = pending
        self._push_undo(STEP_TRANSFORM)
        # grow：旋转/倾斜把选区送出原边界时不截，画布放大到「原图 ∪ 变换后」
        image, _origin = bake_transform(self._image, rect, xf, region, grow=True)
        self._image = image
        self.canvas.set_image(self._image)
        self._refresh_size_label()


    # ------------------------------------------------------------ 文字
    def _spawn_text_block(self, pos: QPointF) -> None:
        """文字工具点击落点 → 画布上生成文字块就地编辑（光标可见）。"""
        if self._image is None or self._image.isNull():
            return
        self.canvas.add_text_block(
            pos, self._text_size, QColor(self._text_color),
            self._text_family,
        )


    def _commit_text_blocks(self) -> None:
        """把画布上非空文字块写进图片（一个批次一个撤销点），然后清块。"""
        if not hasattr(self, "canvas"):
            return
        blocks = self.canvas.text_blocks()
        payload = [
            (b.pos(), b.toPlainText(), b.font().pixelSize(),
             QColor(b.defaultTextColor()), b.font().family())
            for b in blocks if b.toPlainText().strip()
        ]
        self.canvas.clear_text_blocks()
        if not payload or self._image is None or self._image.isNull():
            return
        self._push_undo(STEP_TEXT)
        for pos, text, px, color, family in payload:
            self._image = draw_text(
                self._image, pos, text, px, color, family)
        self.canvas.replace_image(self._image)
