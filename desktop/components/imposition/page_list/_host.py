# -*- coding: utf-8 -*-
"""``ImpositionPageList`` 的**宿主面**声明——仅供类型检查，运行期从不加载。

拆包后每个 Mixin 都是独立类，pyright 看不到兄弟 Mixin / 主类 / Qt 基类上的
成员。这里把「主类 + 全部兄弟 Mixin」的成员面集中声明一次，各 Mixin 在
**类型检查期**以 :class:`PageListHost` 为基类继承进来：

    if TYPE_CHECKING:
        from desktop.components.imposition.page_list._host import PageListHost as _Host
    else:
        _Host = object            # 运行期退化成 object ⇒ MRO 与行为零改动

⚠️ 成员落点 / 签名改动后要同步本文件——只写注解与 ``...`` 桩，不写逻辑。
"""

from __future__ import annotations

from qfluentwidgets import RoundMenu

from desktop.components.imposition.page_list._qt import (
    QScrollArea,
    QTimer,
    QVBoxLayout,
    QWidget,
    Signal,
)
from desktop.components.imposition.page_list.entries import _PageEntry
from desktop.components.imposition.page_list.select_bar import _SelectBar


class PageListHost(QWidget):
    """``ImpositionPageList`` 的成员面：主类 + 3 个 Mixin（菜单 / 勾选 / 拖动）。"""

    # ---- 信号 ----
    page_selected: Signal
    add_requested: Signal
    reorder_requested: Signal
    move_requested: Signal
    insert_requested: Signal
    remove_requested: Signal
    check_changed: Signal
    batch_delete_requested: Signal
    viewport_changed: Signal

    # ---- 类常量 ----
    _POLL_MS: int
    _ANIM_MS: int
    _INDICATOR_H: int
    _EDGE_PX: int
    _EDGE_STEP: int
    _VIEWPORT_DEBOUNCE_MS: int
    _VISIBLE_RETRIES: int

    # ---- 状态 ----
    _entries: list
    _current: int
    _drag_from: int
    _drag_drop: int
    _drag_entry: _PageEntry | None
    _ghost: _PageEntry | None
    _flow: list
    _anims: list
    _grab_dy: int
    _drag_x: int
    _committing: bool
    _visible_pending: int
    _visible_retries: int
    list_scroll: QScrollArea
    list_box: QVBoxLayout
    _indicator: QWidget
    _drag_timer: QTimer
    _viewport_timer: QTimer
    _context_menu: RoundMenu | None
    add_entry: object
    select_bar: _SelectBar

    # ---- 主类（list_widget）----
    def entries(self) -> list: ...

    def set_current(self, index: int) -> None: ...

    def checked_indexes(self) -> list[int]: ...

    def _update_select_bar(self) -> None: ...

    def _place_select_bar(self) -> None: ...

    def _on_entry_check_toggled(self, _index: int, _checked: bool) -> None: ...

    def _on_entry_context_menu(self, entry: object, pos) -> None: ...

    def _run_menu_action(self, key: str, index: int) -> None: ...

    def menu_actions(self) -> list: ...

    # ---- 拖动 Mixin ----
    def _on_drag_started(self, index: int) -> None: ...

    def _poll_drag(self) -> None: ...

    def _place_indicator(self) -> None: ...

    def _register_anim(self, anim) -> None: ...

    def _forget_anim(self, anim) -> None: ...

    def _auto_scroll(self) -> None: ...

    def _slot_y(self, drop: int) -> int: ...

    def _finish_drag(self) -> None: ...

    def _emit_reorder(self, source: int, target: int, ghost) -> None: ...

    def _cancel_drag(self) -> None: ...
