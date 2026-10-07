# -*- coding: utf-8 -*-
"""PrintPreviewWidget 的**宿主面**声明——仅供类型检查，运行期从不加载。

拆分后每个 Mixin 都是独立类，pyright 看不到兄弟 Mixin / 主类 / Qt 基类上的
成员（``self._image`` / ``self.mapFromScene`` …），会把它们整块报成
``reportAttributeAccessIssue``。这里把「主类 + 全部兄弟 Mixin」的成员面集中
声明一次，各 Mixin 在**类型检查期**以 PrintPreviewHost 为基类继承进来：

    if TYPE_CHECKING:
        from ._host import PrintPreviewHost
    else:
        PrintPreviewHost = object        # 运行期退化成 object ⇒ MRO 与行为零改动

⚠️ 成员落点 / 签名改动后要同步本文件——守卫
``tests/selftests/viewer_split.py`` 会核对它覆盖了全部成员。
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
from desktop.components.viewers.image_view import ImageView
from desktop.components.viewers.image_zoom_dialog import ZoomPopupMixin, ZoomTarget
from desktop.components.viewers.print_layout_canvas import PrintLayoutCanvas
from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.components.viewers.thumbs_loader import ThumbsMixin
from desktop.ui.widgets import SegmentedToggle
from pathlib import Path
from qfluentwidgets import CaptionLabel, PrimaryPushButton, PushButton
from typing import Any


class PrintPreviewHost(QWidget, ThumbsMixin, ZoomPopupMixin):
    """``PrintPreviewWidget`` 的成员面：主类 + 3 个 Mixin。

    只有注解与 ``...`` 桩，没有任何实现——不要在这里写逻辑。
    """

    # ---- 状态 ----
    EXPORT_IMAGE_DPI: int
    THUMB_EDGE: Any
    _PAPER_TO_QPAGE: dict[Any, Any]
    _canvas_index: Any
    _empty_hint: Any
    _entries_cache: Any
    _entry_keys: Any
    _export_token: Any
    _load_token: Any
    _mode: Any
    _params_provider: Any
    _pdf_path: Any
    _print_capture: Any
    _thumb_provider: Any
    canvas: PrintLayoutCanvas
    caption: CaptionLabel
    delete_button: PushButton
    download_button: PrimaryPushButton
    download_requested: Signal
    empty_label: QLabel
    export_failed: Signal
    export_finished: Signal
    export_image_button: PushButton
    export_image_requested: Signal
    hint: Signal
    hint_label: CaptionLabel
    image_saved: Signal
    insert_button: PrimaryPushButton
    insert_requested: Signal
    layout_changed: Signal
    list: Any
    order_changed: Signal
    print_button: PushButton
    print_failed: Signal
    print_finished: Signal
    strip: ThumbStrip
    toggle: SegmentedToggle
    view: ImageView

    # ---- 方法（主类 + 各 Mixin）----
    def _apply_page_thumb(self, key, image) -> None:
        ...

    def _build_toolbar(self) -> QHBoxLayout:
        ...

    def _capture_print_image(self, _page, image, _path: str) -> None:
        ...

    def _current_index(self) -> int:
        ...

    def _display(self, token, image) -> None:
        ...

    def _emit_order_changed(self) -> None:
        ...

    def _export_edge(self) -> int:
        ...

    def _export_failed(self, token, message: str) -> None:
        ...

    def _load_display(self) -> None:
        ...

    def _load_failed(self, token, msg: str) -> None:
        ...

    def _load_page_thumbs(self) -> None:
        ...

    def _on_canvas_rect(self, rect: list) -> None:
        ...

    def _on_strip_order_changed(self) -> None:
        ...

    def _on_zoom_image_saved(self, path_text: str, image=None) -> None:
        ...

    def _page_size_mm(self) -> tuple[float, float]:
        ...

    def _plan_for(self, index: int, path: Path, rect=None):
        ...

    def _print_current(self) -> None:
        ...

    def _print_spec(self, index: int, path: Path) -> tuple[dict | None, str]:
        ...

    def _refresh_zoom_popup_if_open(self) -> None:
        ...

    def _render_current_effect_sync(self):
        ...

    def _resolved_nodes(self, args: dict) -> list:
        ...

    def _select_entry(self, index: int) -> None:
        ...

    def _select_image(self, index: int, _path: str) -> None:
        ...

    def _set_mode(self, mode: str) -> None:
        ...

    def _show_layout(self, index: int) -> None:
        ...

    def _stop_worker(self) -> None:
        ...

    def _sync_cache_order(self) -> None:
        ...

    def _sync_export_button(self) -> None:
        ...

    def _thumb_path_for(self, entry: dict) -> Path:
        ...

    def _write_export(self, token, image, target: Path) -> None:
        ...

    def _zoom_index(self) -> int:
        ...

    def _zoom_target(self, index: int) -> ZoomTarget | None:
        ...

    def count(self) -> int:
        ...

    def entries(self) -> list[dict]:
        ...

    def export_current_effect(self, target: str | Path) -> None:
        ...

    def export_default_name(self) -> str | None:
        ...

    def navigate(self, forward: bool) -> None:
        ...

    def refresh_display(self) -> None:
        ...

    def refresh_layout(self) -> None:
        ...

    def remove_selected(self) -> None:
        ...

    def set_entries(self, entries: list[dict]) -> None:
        ...

    def set_pdf_path(self, path: str | Path | None) -> None:
        ...
