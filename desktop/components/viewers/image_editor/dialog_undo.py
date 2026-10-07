# -*- coding: utf-8 -*-
"""``ImageEditorDialog`` Mixin：**撤销栈**。

快照入栈/撤销/重做/全部复位。（从 ``image_editor/dialog.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from .consts import UNDO_LIMIT
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import DialogHost
else:
    DialogHost = object


class UndoMixin(DialogHost):
    """快照入栈/撤销/重做/全部复位。"""

    def _push_undo(self) -> None:
        """把当前状态压入撤销栈（必须在任何破坏性操作**之前**调用）。"""
        if self._image is None or self._image.isNull():
            return
        self._undo.append(self._image.copy())
        if len(self._undo) > UNDO_LIMIT:
            self._undo.pop(0)
        self._redo.clear()
        self._sync_undo_buttons()


    def _undo_now(self) -> None:
        if not self._undo:
            return
        # 正在就地编辑文字时不撤图：Ctrl+Z 被弹窗快捷键截走，这里必须
        # 让位——不然想撤一个字却把整张图连同文字块一起退掉了
        if self.canvas.focused_text_block() is not None:
            return
        # 撤销换图会作废画布上的文字块（它们不在撤销历史里）
        self.canvas.clear_text_blocks()
        self._redo.append(self._image.copy())
        self._image = self._undo.pop()
        self.canvas.set_image(self._image)
        self._sync_undo_buttons()


    def _redo_now(self) -> None:
        if not self._redo:
            return
        if self.canvas.focused_text_block() is not None:
            return  # 同 _undo_now：文字编辑中不让 Ctrl+Y 动图
        self.canvas.clear_text_blocks()
        self._undo.append(self._image.copy())
        self._image = self._redo.pop()
        self.canvas.set_image(self._image)
        self._sync_undo_buttons()


    def _reset_all(self) -> None:
        """还原到打开时的图（还原本身可撤销）。"""
        if self._original.isNull():
            return
        self.canvas.clear_text_blocks()
        if self._undo and self._image is not None:
            self._undo.append(self._image.copy())
            if len(self._undo) > UNDO_LIMIT:
                self._undo.pop(0)
        self._image = self._original.copy()
        self._redo.clear()
        self.canvas.set_image(self._image)
        self._sync_undo_buttons()


    def _sync_undo_buttons(self) -> None:
        self.undo_btn.setEnabled(bool(self._undo))
        self.redo_btn.setEnabled(bool(self._redo))
