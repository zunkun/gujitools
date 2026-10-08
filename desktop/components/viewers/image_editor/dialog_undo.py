# -*- coding: utf-8 -*-
"""``ImageEditorDialog`` Mixin：**撤销栈 + 步骤历史**。

快照入栈/撤销/重做/全部复位，以及右侧「编辑历史」面板的同步与点选跳转。
（从 ``image_editor/dialog.py`` 拆出，2026-10-07；2026-10-08 加**步骤名**与
历史面板——用户要"记录步骤数据、Ctrl+Z 撤销上一步、可点选回退"。）

数据模型（三个列表，靠索引对齐）
--------------------------------

``_undo`` 存的是**变更前**的整图快照，``_redo`` 存撤销时吐出来的状态，
``_image`` 永远是"当前"。于是**时间轴**是：

```text
节点 0 .. U            U+1 .. N
_undo[0..U-1] + _image + reversed(_redo)
```

``_labels[i]`` 是**把 ``_undo[i]`` 这一步的状态改掉的那一步的名字**（也就是
"节点 i → 节点 i+1"这一步）。因此：

- ``len(_labels) == len(_undo) + len(_redo)`` —— 不变量，撤销/重做只挪光标；
- 节点 ``t``（``t>=1``）的名字 = ``_labels[t-1]``；
- 节点 ``0`` 的名字 = ``_origin_label``：正常是"打开"，而**栈被截断**（超过
  ``UNDO_LIMIT`` 丢掉了最老的状态）之后，它变成被丢掉那一步的名字——那一格
  已经不是原始图了，还写"打开"就是骗人。

⚠️ 只改 ``_undo``/``_redo`` 而不动 ``_labels``（或反过来）会让历史面板与
真实状态错位：点某一格跳过去的图不是那一格标的步骤。所有改动都收敛在
:meth:`_push_undo` / :meth:`_undo_now` / :meth:`_redo_now` / :meth:`_reset_all`。
"""
from __future__ import annotations

from .consts import STEP_RESET, UNDO_LIMIT
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import DialogHost
else:
    DialogHost = object


class UndoMixin(DialogHost):
    """快照入栈/撤销/重做/全部复位 + 步骤历史。"""

    def _push_undo(self, label: str = "") -> None:
        """把当前状态压入撤销栈（必须在任何破坏性操作**之前**调用）。

        ``label`` 是**紧接着要做的这一步**的名字（"裁剪"/"擦除"/"变换"…），
        进历史面板显示。缺省给"编辑"，别留空格子。

        ⚠️ 名字挂在"将要被改掉的那个状态"上：本函数压入的是**变更前**的
        快照，而这条快照到下一个状态之间的那一步，正是 ``label``。
        """
        if self._image is None or self._image.isNull():
            return
        self._undo.append(self._image.copy())
        # 重做分支作废：先砍掉比新槽位更靠后的名字，再补上本步的名字
        del self._labels[len(self._undo) - 1:]
        self._labels.append(label or "编辑")
        self._redo.clear()
        if len(self._undo) > UNDO_LIMIT:
            self._undo.pop(0)
            # 最老的状态没了 ⇒ 第 0 节点换人：它现在是被丢掉那一步的结果
            self._origin_label = self._labels.pop(0)
        self._sync_undo_buttons()
        self._sync_history()


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
        self._sync_history()


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
        self._sync_history()


    def _reset_all(self) -> None:
        """还原到打开时的图（还原本身可撤销）。"""
        if self._original.isNull():
            return
        self.canvas.clear_text_blocks()
        if self._undo and self._image is not None:
            self._push_undo(STEP_RESET)
        self._image = self._original.copy()
        self._redo.clear()
        self.canvas.set_image(self._image)
        self._sync_undo_buttons()
        self._sync_history()


    def _sync_undo_buttons(self) -> None:
        self.undo_btn.setEnabled(bool(self._undo))
        self.redo_btn.setEnabled(bool(self._redo))


    # ------------------------------------------------------------ 历史面板
    def _history_nodes(self) -> list[str]:
        """时间轴上每一格的文案（第 0 格 = 打开时的状态，之后每步一个）。"""
        return [self._origin_label, *self._labels]


    def _history_cursor(self) -> int:
        """当前停在哪一格（= 已应用的步数）。"""
        return len(self._undo)


    def _sync_history(self) -> None:
        """把时间轴重画到右侧列表并把光标停在当前格。

        ``_history_syncing`` 是给 ``currentRowChanged`` 用的闸门：本函数自己
        ``clear()`` + ``setCurrentRow()`` 也会发那个信号，不挡住就会拿程序化
        的行号去当"用户点了某一格"，一路撤销到底。
        """
        widget = getattr(self, "history_list", None)
        if widget is None:
            return  # 面板还没建（构造期）或已被销毁
        self._history_syncing = True
        try:
            nodes = self._history_nodes()
            widget.clear()
            if nodes:
                widget.addItems(nodes)
            row = self._history_cursor()
            if 0 <= row < len(nodes):
                widget.setCurrentRow(row)
        finally:
            self._history_syncing = False
        # 尺寸提示跟着图走（裁剪/变换会换画布尺寸）——撤销/重做/还原都从
        # 这里过一遍，所以挂在这儿而不是散在各处
        self._refresh_size_label()


    def _on_history_row(self, row: int) -> None:
        """点某一格：把图退/进到那一步（等价连按若干次 Ctrl+Z / Ctrl+Y）。"""
        if getattr(self, "_history_syncing", False) or row < 0:
            return
        target = int(row)
        # ⚠️ 必须有"推不动就停"的兜底：就地编辑文字时 _undo_now/_redo_now 会
        #    主动让位（见它们的注释），while 写死就会在这儿空转卡住界面。
        for _ in range(len(self._labels) + 2):
            if len(self._undo) > target and self._undo:
                before = len(self._undo)
                self._undo_now()
            elif len(self._undo) < target and self._redo:
                before = len(self._undo)
                self._redo_now()
            else:
                return
            if len(self._undo) == before:
                return
