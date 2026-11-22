# -*- coding: utf-8 -*-
"""页清单的**勾选批量**与批量悬浮框摆位（``_SelectionMixin``）。

Mixin 只在运行期与 ``ImpositionPageList`` 组合；宿主面见 :mod:`._host`，本模块
**不 import** 主类 ``list_widget``，避免循环导入。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from desktop.ui import theme as T

if TYPE_CHECKING:
    from desktop.components.imposition.page_list._host import PageListHost as _Host
else:
    _Host = object


class _SelectionMixin(_Host):
    """勾选集合、批量删除悬浮框的显隐与摆位。"""

    # ------------------------------------------------------------- 勾选批量
    def checked_indexes(self) -> list[int]:
        """勾选了的页下标（升序）。"""
        return sorted(e.index for e in self._entries if e.is_checked())

    def _on_entry_check_toggled(self, _index: int, _checked: bool) -> None:
        self.check_changed.emit()
        self._update_select_bar()

    def _clear_selection(self) -> None:
        """悬浮框「取消选择」：清空全部勾选——勾选数归零，悬浮框随之消失。"""
        for entry in self._entries:
            entry.set_checked(False)
        self.check_changed.emit()
        self._update_select_bar()

    def _update_select_bar(self) -> None:
        """悬浮框跟着勾选数走：勾了页才浮出，取消选择/删页归零即收起。"""
        count = len(self.checked_indexes())
        self.select_bar.set_count(count)
        self.select_bar.setVisible(count > 0)
        if count > 0:
            self._place_select_bar()
            self.select_bar.raise_()

    def _place_select_bar(self) -> None:
        """摆悬浮框：默认悬在**页码栏右缘、垂直居中**（浮在右侧画布上，
        不压底部的「＋ 选择拼版」）；用户拖过就不再自动摆位。"""
        bar = self.select_bar
        if bar._user_moved:
            return
        hint = bar.sizeHint()
        host = bar.parentWidget()
        if host is None or host is self:
            # 兜底（没有外部宿主，比如单独实例化）：清单内右缘、垂直居中
            scroll = self.list_scroll.geometry()
            x = max(0, self.width() - hint.width() - T.SPACE_XS)
            y = scroll.top() + max(0, (scroll.height() - hint.height()) // 2)
            bar.setGeometry(x, y, hint.width(), hint.height())
            return
        g = self.geometry()  # 本列在宿主坐标系里的位置
        x = max(0, min(g.right() - 8, host.width() - hint.width()))
        y = max(0, g.top() + (g.height() - hint.height()) // 2)
        bar.setGeometry(x, y, hint.width(), hint.height())
