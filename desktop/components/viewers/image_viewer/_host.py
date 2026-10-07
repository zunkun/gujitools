# -*- coding: utf-8 -*-
"""ImageViewerWidget 的**宿主面**声明——仅供类型检查，运行期从不加载。

拆分后每个 Mixin 都是独立类，pyright 看不到兄弟 Mixin / 主类 / Qt 基类上的
成员（``self._image`` / ``self.mapFromScene`` …），会把它们整块报成
``reportAttributeAccessIssue``。这里把「主类 + 全部兄弟 Mixin」的成员面集中
声明一次，各 Mixin 在**类型检查期**以 ImageViewerHost 为基类继承进来：

    if TYPE_CHECKING:
        from ._host import ImageViewerHost
    else:
        ImageViewerHost = object        # 运行期退化成 object ⇒ MRO 与行为零改动

⚠️ 成员落点 / 签名改动后要同步本文件——守卫
``tests/selftests/viewer_split.py`` 会核对它覆盖了全部成员。
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QWidget
from desktop.components.viewers.image_view import ImageView
from desktop.components.viewers.image_zoom_dialog import ZoomPopupMixin, ZoomTarget
from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.components.viewers.thumbs_loader import ThumbsMixin
from pathlib import Path
from qfluentwidgets import CaptionLabel
from typing import Any


class ImageViewerHost(QWidget, ThumbsMixin, ZoomPopupMixin):
    """``ImageViewerWidget`` 的成员面：主类 + 3 个 Mixin。

    只有注解与 ``...`` 桩，没有任何实现——不要在这里写逻辑。
    """

    # ---- 状态 ----
    _empty_hint: Any
    _image_size_provider: Any
    _insert_buttons: tuple[Any, ...]
    _load_token: int
    _page_source: tuple[Any, ...] | tuple[Path, int] | None
    _page_source_cache: Any
    _paths: Any
    _pending_boxes: tuple | tuple[Any, ...] | None
    _thumb_cache_dir: Path | None
    _thumb_cache_edge: Any
    _thumb_cache_lookup: Any
    _thumb_cache_names: Any
    _thumb_cache_ready: dict[Any, Any] | dict[str, Path]
    _thumb_cache_worker: Any
    _thumb_provider: Any
    box_edit_rejected: Signal
    boxes_edited: Signal
    current_changed: Signal
    delete_requested: Signal
    image_saved: Signal
    info_label: CaptionLabel
    insert_folder_requested: Signal
    insert_requested: Signal
    selection_changed: Signal
    show_boxes: Any
    strip: ThumbStrip
    view: ImageView

    # ---- 方法（主类 + 各 Mixin）----
    def _boxes_edited(self, boxes: list) -> None:
        ...

    def _clear_page_source(self) -> None:
        ...

    def _image_ready(self, _page: int, image, _path: str) -> None:
        ...

    def _image_ready_if_current(self, token: int, page: int, image, path: str) -> None:
        ...

    def _load_failed_if_current(self, token: int, msg: str) -> None:
        ...

    def _load_thumbs(self, strip, paths: list[Path | str], start: int = 0) -> None:
        ...

    def _lookup_thumb_path(self, path_text: str) -> Path | None:
        ...

    def _on_thumb_cached(self, index: int, image, cached: str) -> None:
        ...

    def _on_zoom_image_saved(self, path_text: str, image=None) -> None:
        ...

    def _original_size(self, path_text: str):
        ...

    def _pdf_page_failed(self, token: int, message: str) -> None:
        ...

    def _pdf_page_ready(self, token: int, image) -> None:
        ...

    def _select_image(self, index: int, _path: str) -> None:
        ...

    def _select_pdf_page(self, index: int) -> None:
        ...

    def _start_thumb_cache(self, paths: list[Path | str]) -> None:
        ...

    def _thumb_cache_target(self, index: int, path: Path) -> Path:
        ...

    def _thumb_for(self, path_text: str) -> Path:
        # ⚠️ **缓存优先于 provider**：:meth:`set_thumb_source` 的缓存小图就绪后，
        #    没必要再让宿主那个 provider 去合成区域效果（去底色页那条 provider
        #    会现算一遍，几十页就是几十次全尺寸合成）。缓存没就绪的那张回落到
        #    provider，最后才回落原图。
        ...

    def _zoom_index(self) -> int:
        ...

    def _zoom_target(self, index: int) -> ZoomTarget | None:
        ...

    def apply_boxes(self, boxes: list[tuple], image_size: QSize, info_text: str = "",
                    full: bool = False, selected: int = -1) -> None:
        ...

    def apply_edited_image(self, path_text: str, image) -> None:
        ...

    def begin_pdf_pages(self, count: int, path: str = "") -> None:
        ...

    def box_full_mode(self) -> bool:
        ...

    def box_kinds(self) -> list:
        ...

    def current_path(self) -> Path | None:
        ...

    def navigate(self, forward: bool) -> None:
        ...

    @property
    def paths(self) -> list[Path | str]:
        ...

    def refresh_page(self, path_text: str) -> None:
        ...

    def reload_thumb(self, path_text: str) -> None:
        ...

    def select_box(self, index: int) -> None:
        ...

    def selected_index(self) -> int:
        ...

    def set_empty_hint(self, hint: str) -> None:
        ...

    def set_images(self, paths: list[Path | str], boxes_map: dict | None = None) -> None:
        ...

    def set_insert_visible(self, visible: bool) -> None:
        ...

    def set_pdf_source(
        self, pdf: Path | str, cache_dir: Path | None = None, gen: int = 0,
    ) -> None:
        ...

    def set_pdf_thumb(self, gen: int, index: int, image) -> None:
        ...

    def set_reference_boxes(self, boxes: list) -> None:
        ...

    def set_thumb_source(
        self, paths: list[Path | str], cache_dir: Path | str,
        edge: int | None = None,
        names: list[str | None] | None = None,
    ) -> None:
        ...
