# -*- coding: utf-8 -*-
"""RembgPreviewWidget 的**宿主面**声明——仅供类型检查，运行期从不加载。

拆分后每个 Mixin 都是独立类，pyright 看不到兄弟 Mixin / 主类 / Qt 基类上的
成员（``self._image`` / ``self.mapFromScene`` …），会把它们整块报成
``reportAttributeAccessIssue``。这里把「主类 + 全部兄弟 Mixin」的成员面集中
声明一次，各 Mixin 在**类型检查期**以 RembgViewerHost 为基类继承进来：

    if TYPE_CHECKING:
        from ._host import RembgViewerHost
    else:
        RembgViewerHost = object        # 运行期退化成 object ⇒ MRO 与行为零改动

⚠️ 成员落点 / 签名改动后要同步本文件——守卫
``tests/selftests/viewer_split.py`` 会核对它覆盖了全部成员。
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QWidget
from desktop.components.viewers.image_view import ImageView
from desktop.components.viewers.image_zoom_dialog import ZoomPopupMixin, ZoomTarget
from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.components.viewers.thumbs_loader import ThumbsMixin
from desktop.ui.widgets import SegmentedToggle
from pathlib import Path
from qfluentwidgets import CaptionLabel
from typing import Any


class RembgViewerHost(QWidget, ThumbsMixin, ZoomPopupMixin):
    """``RembgPreviewWidget`` 的成员面：主类 + 2 个 Mixin。

    只有注解与 ``...`` 桩，没有任何实现——不要在这里写逻辑。
    """

    # ---- 状态 ----
    _border_mm: Any
    _boxes_provider: Any
    _cached_thumbs: Any
    _entries: Any
    _live_dir: Any
    _load_token: Any
    _mode: Any
    _paths: Any
    _region_params_provider: Any
    _rembg_dir: Any
    _thumb_provider: Any
    current_changed: Signal
    image_saved: Signal
    strip: ThumbStrip
    toggle: SegmentedToggle
    toggle_caption: CaptionLabel
    view: ImageView

    # ---- 方法（主类 + 各 Mixin）----
    def _build_entries(self) -> list[dict]:
        ...

    def _current_entry(self) -> dict | None:
        ...

    def _display(self, token, image) -> None:
        ...

    @staticmethod
    def _fill_icon(image: QImage) -> QImage:
        ...

    def _load_display(self) -> None:
        ...

    def _load_failed(self, token, msg: str) -> None:
        ...

    def _load_page_thumbs(self, entries: list[dict],
                          rows: list[int] | None = None) -> None:
        ...

    def _on_zoom_image_saved(self, path_text: str, image=None) -> None:
        ...

    def _rebuild_entries(self, force_strip: bool = False) -> None:
        ...

    def _resolve_source(self, entry: dict) -> tuple:
        ...

    def _result_full_image(self, entry: dict | None = None,
                           include_live: bool = True) -> Path | None:
        ...

    def _select_entry(self, index: int) -> None:
        ...

    def _select_image(self, index: int, _path: str) -> None:
        ...

    def _set_mode(self, mode: str) -> None:
        ...

    def _sync_toggle(self, has_result: bool) -> None:
        ...

    def _zoom_index(self) -> int:
        ...

    def _zoom_target(self, index: int) -> ZoomTarget | None:
        ...

    def current_entry_path(self) -> str | None:
        ...

    @property
    def live_dir(self) -> Path | None:
        ...

    def navigate(self, forward: bool) -> None:
        ...

    def refresh_display(self) -> None:
        ...

    def refresh_page(self, path_text: str) -> None:
        ...

    def reload_thumb(self, path_text: str) -> None:
        ...

    def set_cached_thumb(self, path_text: str, cache: str) -> None:
        ...

    def set_cached_thumbs(self, mapping: dict[str, str]) -> None:
        ...

    def set_images(
        self,
        paths: list[Path | str],
        rembg_dir: Path | None,
        boxes_provider=None,
        region_params_provider=None,
        thumb_provider=None,
    ) -> None:
        ...

    def set_live_dir(self, path: Path | None) -> None:
        ...

    def show_live_pending(self) -> None:
        ...
