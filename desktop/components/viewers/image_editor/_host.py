# -*- coding: utf-8 -*-
"""ImageEditorDialog 的**宿主面**声明——仅供类型检查，运行期从不加载。

拆分后每个 Mixin 都是独立类，pyright 看不到兄弟 Mixin / 主类 / Qt 基类上的
成员（``self._image`` / ``self.mapFromScene`` …），会把它们整块报成
``reportAttributeAccessIssue``。这里把「主类 + 全部兄弟 Mixin」的成员面集中
声明一次，各 Mixin 在**类型检查期**以 DialogHost 为基类继承进来：

    if TYPE_CHECKING:
        from ._host import DialogHost
    else:
        DialogHost = object        # 运行期退化成 object ⇒ MRO 与行为零改动

⚠️ 成员落点 / 签名改动后要同步本文件——守卫
``tests/selftests/viewer_split.py`` 会核对它覆盖了全部成员。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget
from desktop.components.viewers.image_editor.canvas import EditorCanvas
from qfluentwidgets import (
    CaptionLabel, ListWidget, PrimaryPushButton, PushButton, StrongBodyLabel,
    ToggleButton, ToolButton,
)
from typing import Any


class DialogHost(QDialog):
    """``ImageEditorDialog`` 的成员面：主类 + 4 个 Mixin。

    只有注解与 ``...`` 桩，没有任何实现——不要在这里写逻辑。
    """

    # ---- 状态 ----
    _erase_size: Any
    _finishing: bool
    _history_syncing: bool
    _image: Any
    _labels: list[str]
    _option_host: QWidget
    _option_host_layout: QVBoxLayout
    _option_page: Any
    _origin_label: str
    _original: Any
    _redo: list[QImage]
    _reshape_uncheck: Any
    _save_back: bool
    _text_color: str
    _text_family: Any
    _text_size: int
    _tool_buttons: dict[str, ToggleButton]
    _undo: list[QImage]
    canvas: EditorCanvas
    done_btn: PrimaryPushButton
    fit_btn: PushButton
    history_list: ListWidget
    panel_title: StrongBodyLabel
    redo_btn: ToolButton
    reset_btn: PushButton
    size_label: CaptionLabel
    target_exists: bool
    target_name: str
    undo_btn: ToolButton
    zoom_in_btn: ToolButton
    zoom_out_btn: ToolButton

    # ---- 方法（主类 + 各 Mixin）----
    def _apply_crop(self) -> None:
        ...

    def _build_side_panel(self) -> QWidget:
        ...

    def _build_status(self) -> QWidget:
        ...

    def _build_toolbar_row(self) -> QVBoxLayout:
        ...

    def _commit_text_blocks(self) -> None:
        ...

    def _commit_transform(self) -> None:
        ...

    def _confirm_overwrite(self) -> bool:
        ...

    def _escape(self) -> None:
        ...

    def _finish(self) -> None:
        ...

    @staticmethod
    def _hint(layout: QVBoxLayout, text: str) -> None:
        ...

    def _history_cursor(self) -> int:
        ...

    def _history_nodes(self) -> list[str]:
        ...

    @staticmethod
    def _labeled(title: str, control: QWidget) -> QWidget:
        ...

    def _on_history_row(self, row: int) -> None:
        ...

    def _on_stroke_started(self) -> None:
        ...

    def _page_crop(self, layout: QVBoxLayout) -> None:
        ...

    def _page_distort(self, layout: QVBoxLayout) -> None:
        ...

    def _page_erase(self, layout: QVBoxLayout) -> None:
        ...

    def _page_text(self, layout: QVBoxLayout) -> None:
        ...

    def _page_transform(self, layout: QVBoxLayout) -> None:
        ...

    def _push_undo(self, label: str = "") -> None:
        ...

    def _redo_now(self) -> None:
        ...

    def _refresh_size_label(self) -> None:
        ...

    def _reset_all(self) -> None:
        ...

    def _selection(self) -> QRectF | None:
        ...

    def _set_tool(self, tool: str) -> None:
        ...

    def _slider_group(self, title: str, key: str, low: int, high: int,
                      suffix: str) -> QWidget:
        ...

    def _spawn_text_block(self, pos: QPointF) -> None:
        ...

    def _swap_option_page(self) -> QVBoxLayout:
        ...

    def _sync_history(self) -> None:
        ...

    def _sync_undo_buttons(self) -> None:
        ...

    def _undo_now(self) -> None:
        ...

    def closeEvent(self, event) -> None:  # noqa: N802（Qt 回调）
        ...

    def result_image(self) -> QImage | None:
        ...
