# -*- coding: utf-8 -*-
"""``ImpositionPickerDialog`` 的**宿主面**声明——仅供类型检查，运行期从不加载。

拆包后每个 Mixin 都是独立类，pyright 看不到兄弟 Mixin / 主类 / Qt 基类上的
成员。这里把「主类 + 全部兄弟 Mixin」的成员面集中声明一次，各 Mixin 在
**类型检查期**以 :class:`PickerHost` 为基类继承进来：

    if TYPE_CHECKING:
        from desktop.components.imposition.picker._host import PickerHost as _Host
    else:
        _Host = object            # 运行期退化成 object ⇒ MRO 与行为零改动

⚠️ 成员落点 / 签名改动后要同步本文件——只写注解与 ``...`` 桩，不写逻辑。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from qfluentwidgets import CheckBox, PrimaryPushButton, PushButton, RadioButton
from qframelesswindow import FramelessDialog

from desktop.components.imposition.picker._qt import (
    QLabel,
    QPixmap,
    QScrollArea,
    QWidget,
)
from desktop.components.imposition.picker.cards import _CardGrid, _SourceCard


class PickerHost(FramelessDialog):
    """``ImpositionPickerDialog`` 的成员面：主类 + 2 个 Mixin（填充 / 状态）。"""

    # ---- 状态 ----
    _mode: str
    _thumb_provider: Callable[[str], Path | None] | None
    _files: list[Path]
    _uploads: list[tuple[str, Path]]
    _upload_seq: int
    _pixmaps: dict[str, QPixmap]
    _cand_cards: dict[str, _SourceCard]
    cards: list[_SourceCard]
    _total: int
    _current_row: int

    # ---- 控件 ----
    note: QLabel
    scroll: QScrollArea
    body: _CardGrid
    status: QLabel
    upload_row: QWidget
    upload_button: PushButton
    upload_hint: QLabel
    position_row: QWidget
    auto_checkbox: CheckBox
    ok_button: PrimaryPushButton
    before_radio: RadioButton | None
    after_radio: RadioButton | None

    # ---- 主类（dialog）----
    def count(self) -> int:
        return 0

    def position(self) -> str:
        return "after"

    def add_uploads(self, paths) -> None:
        return

    def _on_card_clicked(self, card: _SourceCard) -> None:
        return

    def _scroll_to_end(self) -> None:
        return

    # ---- 填充 Mixin ----
    def _source_candidate_paths(self) -> list[Path]:
        return []

    def _candidate_entries(self) -> list[tuple[str, Path, bool]]:
        return []

    def _sync_grid(self, grid, store: dict, entries: list) -> list:
        return []

    def _sync_grids(self) -> None:
        return

    def _populate(self) -> None:
        return

    def _thumb_pixmap_for(self, card: _SourceCard) -> QPixmap:
        return QPixmap()

    def _fill_thumbs(self) -> None:
        return

    # ---- 状态 Mixin ----
    def _build_position_row(self, default_position: str) -> QWidget:
        return QWidget()

    def _update_status(self) -> None:
        return
