# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""PrintLayoutCanvas 的**宿主面**声明——仅供类型检查，运行期从不加载。

拆分后每个 Mixin 都是独立类，pyright 看不到兄弟 Mixin / 主类 / Qt 基类上的
成员（``self._rect_mm`` / ``self._recompute`` …），会把它们整块报成
``reportAttributeAccessIssue``。这里把「主类 + 全部兄弟 Mixin」的成员面集中
声明一次，各 Mixin 在**类型检查期**以 PrintLayoutCanvasHost 为基类继承：

    if TYPE_CHECKING:
        from ._host import PrintLayoutCanvasHost
    else:
        PrintLayoutCanvasHost = object    # 运行期退化成 object ⇒ MRO 与行为零改动

⚠️ 成员落点 / 签名改动后要同步本文件。
"""
from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCore import QPointF, QRectF, Signal
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QWidget


class PrintLayoutCanvasHost(QWidget):
    """``PrintLayoutCanvas`` 的成员面：主类 + 3 个 Mixin。

    只有注解与 ``...`` 桩，没有任何实现——不要在这里写逻辑。
    """

    # ---- 信号 ----
    rect_changed: Signal
    double_clicked: Signal
    context_menu_requested: Signal

    # ---- 状态 ----
    _page_w_mm: float
    _page_h_mm: float
    _image: QImage | None
    _display_source: QImage | None
    _display_image: QImage | None
    _rotation: float
    _plan: Any
    _rect_mm: list[float]
    _pad: int
    _px_per_mm: float
    _off_x: float
    _off_y: float
    _mode: str | None
    _corner: int
    _grab_x: float
    _grab_y: float
    _grab_angle: float
    _grab_rotation: float
    _grab_content: tuple[float, float]
    _keep_ratio: bool
    _grab_rect: list[float]
    _dirty: bool

    # ---- 主类 ----
    def __init__(self, parent=None) -> None:
        ...

    def set_page(
        self,
        page_w_mm: float,
        page_h_mm: float,
        image: QImage | None,
        rect_mm: Sequence[float],
        plan=None,
        keep_ratio: bool = True,
        rotate: float = 0.0,
    ) -> None:
        ...

    def current_rect(self) -> list[float]:
        ...

    def rotation(self) -> float:
        ...

    def set_rotation(self, degrees) -> None:
        ...

    def resizeEvent(self, event) -> None:
        ...

    def showEvent(self, event) -> None:
        ...

    # ---- geometry.py -> GeometryMixin ----
    def _content_size_mm(self, rect, angle) -> tuple[float, float]:
        ...

    def _bbox_for_content(self, content, angle) -> list[float]:
        ...

    def _rect_center_mm(self) -> tuple[float, float]:
        ...

    def _display_image_for(self) -> QImage | None:
        ...

    def _recompute(self) -> None:
        ...

    def _to_mm(self, pos: QPointF) -> tuple[float, float]:
        ...

    def _rect_px(self) -> QRectF:
        ...

    def _handle_positions(self) -> list[tuple[float, float]]:
        ...

    def _rotate_knob_pos(self) -> QPointF:
        ...

    def _hit_handle(self, pos: QPointF) -> int | None:
        ...

    def _hit_rect(self, pos: QPointF) -> bool:
        ...

    # ---- mouse.py -> MouseMixin ----
    def flush_pending(self) -> bool:
        ...

    def mousePressEvent(self, event) -> None:
        ...

    def mouseMoveEvent(self, event) -> None:
        ...

    def mouseDoubleClickEvent(self, event) -> None:
        ...

    def contextMenuEvent(self, event) -> None:
        ...

    def mouseReleaseEvent(self, event) -> None:
        ...

    def _resize_from_handle(self, mx: float, my: float) -> list[float]:
        ...

    # ---- paint.py -> PaintMixin ----
    def paintEvent(self, event) -> None:
        ...

    def _draw_image(self, painter: QPainter, image: QImage,
                    rect_px: QRectF) -> None:
        ...

    def _draw_rotate_knob(self, painter: QPainter) -> None:
        ...
