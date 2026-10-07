# -*- coding: utf-8 -*-
"""画布 Mixin：**插入文字块**（就地编辑/整块拖动/样式目标）。

从 ``EditorCanvas`` 拆出（2026-10-07）。方法体逐字未改。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

from ..text_item import TextBlockItem
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import CanvasHost
else:
    CanvasHost = object


class TextMixin(CanvasHost):
    """文字工具：造块/移动/焦点/样式目标/清空。"""

    # ------------------------------------------------------------ 文字块
    def add_text_block(self, pos: QPointF, px: int, color: QColor,
                       family: str) -> TextBlockItem:
        """在落点放一个可就地编辑的文字块并给它焦点（光标闪烁）。

        ⚠️ 顺便把键盘焦点拿回视图：场景焦点项的输入要靠「视图持有键盘
        焦点 → keyPressEvent 转发」这条链，视图没焦点时打字全落空。
        """
        item = TextBlockItem(pos, px, color, family)
        item._canvas = self  # 拖动时让画布的边界虚线框跟随
        item.setZValue(20)
        self._scene.addItem(item)
        self._active_text_block = item
        self.setFocus()
        item.setFocus()
        return item


    def _move_text_outline(self, block: TextBlockItem) -> None:
        """文字块**边界虚线框**挪到块身（悬停/拖动中可见，松手即隐）。

        用户 2026-10-01：鼠标放在文字上要有"这一块的范围"线段，拖动时
        跟着走，释放就消失——拖的是整块，不是光标。
        """
        rect = block.mapRectToScene(block.boundingRect())
        self._text_outline.setRect(rect)
        self._text_outline.setVisible(True)


    def _hide_text_outline(self) -> None:
        self._text_outline.hide()


    def _text_block_at(self, pos: QPointF) -> TextBlockItem | None:
        """落点处的文字块（按块的边界矩形命中，与虚线框口径一致）。"""
        for block in self.text_blocks():
            if block.boundingRect().contains(block.mapFromScene(pos)):
                return block
        return None


    def text_blocks(self) -> list[TextBlockItem]:
        """画布上所有待插入文字块。"""
        return [i for i in self._scene.items()
                if isinstance(i, TextBlockItem)]


    def focused_text_block(self) -> TextBlockItem | None:
        """正在编辑的文字块（场景焦点项；键盘输入路由用）。"""
        item = self._scene.focusItem()
        return item if isinstance(item, TextBlockItem) else None


    def style_target_block(self) -> TextBlockItem | None:
        """选项行改样式时作用的那一块：优先正在编辑的，其次"当前样式块"。

        ⚠️ 与 :meth:`focused_text_block` 分开是刻意的：点选项行的滑杆/按钮
        会抢走键盘焦点，此时"正在编辑"已经没了，但用户**期望**改动仍落在他
        刚点的那个文字块上（用户 2026-10-01 报"字号不生效"就是这个原因）。
        """
        block = self.focused_text_block()
        if block is not None:
            return block
        block = self._active_text_block
        if block is None:
            return None
        try:
            alive = block.scene() is self._scene
        except RuntimeError:  # 空块失焦自删，C++ 对象已回收
            alive = False
        if not alive:
            self._active_text_block = None
            return None
        return block


    def focus_text_block(self, block: TextBlockItem | None = None) -> None:
        """把键盘焦点还给文字块（颜色面板关掉后接着打字用）。"""
        block = block if block is not None else self.style_target_block()
        if block is None or block.scene() is not self._scene:
            return
        self.setFocus()
        block.setFocus()


    def clear_text_blocks(self) -> None:
        """清掉所有文字块（插入/换图/关编辑时）。"""
        self._hide_text_outline()
        self._active_text_block = None
        for item in self.text_blocks():
            self._scene.removeItem(item)
            item.deleteLater()
