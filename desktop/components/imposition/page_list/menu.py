# -*- coding: utf-8 -*-
"""页清单的**右键菜单**：上移 / 下移 / 删除当前拼版 / 向前 / 向后插入拼版
（``_MenuMixin``）。

Mixin 只在运行期与 ``ImpositionPageList`` 组合；宿主面见 :mod:`._host`，本模块
**不 import** 主类 ``list_widget``，避免循环导入。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from desktop.components.imposition.page_list._host import PageListHost as _Host
    from desktop.components.imposition.page_list.entries import _PageEntry
else:
    _Host = object


class _MenuMixin(_Host):
    """某页缩略图右键弹出的菜单及其动作分发。"""

    # ------------------------------------------------------------- 右键菜单
    def _on_entry_context_menu(self, entry: _PageEntry, pos) -> None:
        """某页缩略图右键：上移 / 下移 / 删除当前拼版 / 向前 / 向后插入拼版。

        用户 2026-11-16：与「PDF排版」左列缩略图**同一套菜单**（拖动能做的
        事，右键也能做，且不用对准 8px 的描边拖）。

        ⚠️ 先右键把命中的那一页设成当前页：菜单动作（上移/下移/删除/插入
        落点）必须作用在**刚点的那一页**上，不能沿用上一次的选中页。
        ⚠️ 菜单父对象必须是**顶层窗口**（``self.window()``）：qfluentwidgets
        的 ``exec`` 只是非阻塞 ``show()``，Qt 会沿父链找 popup 的原生父窗口，
        父对象是嵌套控件时控制台会刷 "must be a top level window"。
        """
        from qfluentwidgets import Action, FluentIcon as FIF, RoundMenu

        if entry not in self._entries:
            return
        index = self._entries.index(entry)
        self.set_current(index)
        self.page_selected.emit(index)
        previous = self._context_menu
        if previous is not None:
            previous.deleteLater()
        menu = RoundMenu(parent=self.window())
        self._context_menu = menu
        count = len(self._entries)
        # 首/末行置灰：点了"没反应"比置灰更让人困惑
        for text, icon, delta, enabled in (
            ("上移", FIF.CARE_UP_SOLID, -1, index > 0),
            ("下移", FIF.CARE_DOWN_SOLID, +1, index < count - 1),
        ):
            action = Action(icon, text, menu)
            action.setEnabled(enabled)
            # ⚠️ ``triggered`` 带一个 ``checked=False`` 实参，直接 partial
            # ``emit(index, delta)`` 会多塞一个参数进信号（TypeError）——
            # 用默认参数把它吃掉。
            action.triggered.connect(
                lambda _checked=False, i=index, d=delta:
                self.move_requested.emit(i, d)
            )
            menu.addAction(action)
        menu.addSeparator()
        for text, icon, key in (
            ("删除当前拼版", FIF.DELETE, "remove"),
            ("向前插入拼版", FIF.UP, "before"),
            ("向后插入拼版", FIF.DOWN, "after"),
        ):
            action = Action(icon, text, menu)
            action.triggered.connect(
                lambda _checked=False, k=key, i=index:
                self._run_menu_action(k, i)
            )
            menu.addAction(action)
        menu.exec(entry.mapToGlobal(pos))

    def _run_menu_action(self, key: str, index: int) -> None:
        """右键菜单项分发（``triggered`` 的 checked 实参已在调用处吃掉）。"""
        if not (0 <= index < len(self._entries)):
            return
        if key == "remove":
            self.remove_requested.emit(index)
        elif key == "before":
            self.insert_requested.emit(index, "before")
        elif key == "after":
            self.insert_requested.emit(index, "after")

    def menu_actions(self) -> list:
        """当前右键菜单里的动作（护栏/自检用；没弹过菜单返回空列表）。"""
        menu = self._context_menu
        return list(menu.actions()) if menu is not None else []
