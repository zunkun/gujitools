# -*- coding: utf-8 -*-
"""ImageView 的**宿主面**声明——仅供类型检查，运行期从不加载。

拆分后每个 Mixin 都是独立类，pyright 看不到兄弟 Mixin / 主类 / Qt 基类上的
成员（``self._image`` / ``self.mapFromScene`` …），会把它们整块报成
``reportAttributeAccessIssue``。这里把「主类 + 全部兄弟 Mixin」的成员面集中
声明一次，各 Mixin 在**类型检查期**以 ImageViewHost 为基类继承进来：

    if TYPE_CHECKING:
        from ._host import ImageViewHost
    else:
        ImageViewHost = object        # 运行期退化成 object ⇒ MRO 与行为零改动

⚠️ 成员落点 / 签名改动后要同步本文件——守卫
``tests/selftests/viewer_split.py`` 会核对它覆盖了全部成员。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QSize, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QLabel
from typing import Any


class ImageViewHost(QLabel):
    """``ImageView`` 的成员面：主类 + 2 个 Mixin。

    只有注解与 ``...`` 桩，没有任何实现——不要在这里写逻辑。
    """

    # ---- 状态 ----
    MAX_PREVIEW_EDGE: int
    MIN_PREVIEW_EDGE: int
    _boxes: Any
    _boxes_editable: Any
    _dirty: bool
    _dpr: Any
    _drag_index: Any
    _full_mode: bool
    _ghost_box: Any
    _grab_dx: Any
    _grab_dy: Any
    _image_size: Any
    _mode: str | None
    _new_start: tuple[Any, ...] | tuple[float, float] | None
    _offset_x: float | int
    _offset_y: float | int
    _pixmap: Any
    _pixmap_version: int
    _reference_boxes: Any
    _resize_corner: Any
    _scale_x: Any
    _scale_y: Any
    _scaled_base: Any
    _scaled_key: Any
    _selected: Any
    boxes_edited: Signal
    context_menu_requested: Signal
    double_clicked: Signal
    edit_rejected: Signal
    selection_changed: Signal

    # ---- 方法（主类 + 各 Mixin）----
    def _commit_edit(self) -> None:
        ...

    def _draw_boxes(self, painter: QPainter) -> None:
        ...

    def _draw_reference_boxes(self, painter: QPainter) -> None:
        ...

    def _handle_rects(self, box) -> list[tuple[int, int, float, float]]:
        ...

    def _hit_box(self, ix: float, iy: float) -> int | None:
        ...

    def _hit_handle(self, pos: QPointF) -> int | None:
        ...

    def _limit_message(self) -> str:
        ...

    @staticmethod
    def _normalize(box) -> list[int]:
        ...

    def _pen_width(self, logical: int | float) -> float:
        ...

    def _rerender(self) -> None:
        ...

    def _select(self, index: int | None) -> None:
        ...

    def _to_image_coords(self, pos: QPointF) -> tuple[float, float]:
        ...

    def _update_mapping(self, scaled: QPixmap) -> None:
        ...

    def box_kinds(self) -> list:
        ...

    def clear_image(self, text: str = "无预览") -> None:
        ...

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        ...

    def event(self, event) -> bool:  # noqa: N802
        ...

    @property
    def full_mode(self) -> bool:
        ...

    @property
    def has_image(self) -> bool:
        ...

    def keyPressEvent(self, event) -> None:  # noqa: N802
        ...

    @property
    def max_boxes(self) -> int:
        ...

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        ...

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        ...

    def mousePressEvent(self, event) -> None:  # noqa: N802
        ...

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        ...

    def preview_edge(self) -> int:
        ...

    def resizeEvent(self, event) -> None:  # noqa: N802
        ...

    def select_box(self, index: int) -> None:
        ...

    def selected_index(self) -> int:
        ...

    def set_boxes(self, boxes: list, image_size: QSize, full: bool = False,
                  selected: int | None = None) -> None:
        ...

    def set_boxes_editable(self, editable: bool) -> None:
        ...

    def set_image(self, image, boxes=None, image_size: QSize | None = None) -> None:
        ...

    def set_reference_boxes(self, boxes: list) -> None:
        ...
