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
from PySide6.QtWidgets import QDialog, QHBoxLayout, QWidget
from desktop.components.viewers.image_editor.canvas import EditorCanvas
from qfluentwidgets import CaptionLabel, PrimaryPushButton, PushButton, ToggleButton, ToolButton
from typing import Any


class DialogHost(QDialog):
    """``ImageEditorDialog`` 的成员面：主类 + 4 个 Mixin。

    只有注解与 ``...`` 桩，没有任何实现——不要在这里写逻辑。
    """

    # ---- 状态 ----
    _cage_busy: bool
    _deform_busy: bool
    _erase_size: Any
    _finishing: bool
    _image: Any
    _option_page: Any
    _option_row: QHBoxLayout
    _original: Any
    _rectify_busy: bool
    _redo: list[QImage]
    _save_back: bool
    _text_color: str
    _text_family: Any
    _text_size: int
    _tool_buttons: dict[str, ToggleButton]
    _undo: list[QImage]
    canvas: EditorCanvas
    done_btn: PrimaryPushButton
    fit_btn: PushButton
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

    def _build_status(self) -> QWidget:
        ...

    def _build_toolbar_row(self) -> QHBoxLayout:
        ...

    def _commit_cage(self) -> None:
        ...

    def _commit_deform(self) -> None:
        ...

    def _commit_rectify(self) -> None:
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
    def _hint(layout: QHBoxLayout, text: str) -> None:
        ...

    def _page_cage(self, layout: QHBoxLayout) -> None:
        ...

    def _page_crop(self, layout: QHBoxLayout) -> None:
        ...

    def _page_deform(self, layout: QHBoxLayout) -> None:
        ...

    def _page_erase(self, layout: QHBoxLayout) -> None:
        ...

    def _page_rectify(self, layout: QHBoxLayout) -> None:
        ...

    def _page_text(self, layout: QHBoxLayout) -> None:
        ...

    def _page_transform(self, layout: QHBoxLayout) -> None:
        ...

    def _push_undo(self) -> None:
        ...

    def _redo_now(self) -> None:
        ...

    def _report_bake_error(self, exc: Exception) -> None:
        ...

    def _reset_all(self) -> None:
        ...

    def _selection(self) -> QRectF | None:
        ...

    def _set_tool(self, tool: str) -> None:
        ...

    def _spawn_text_block(self, pos: QPointF) -> None:
        ...

    def _swap_option_page(self) -> QHBoxLayout:
        ...

    def _sync_undo_buttons(self) -> None:
        ...

    def _undo_now(self) -> None:
        ...

    def closeEvent(self, event) -> None:  # noqa: N802（Qt 回调）
        ...

    def result_image(self) -> QImage | None:
        ...
