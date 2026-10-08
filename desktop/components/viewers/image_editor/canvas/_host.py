# -*- coding: utf-8 -*-
"""EditorCanvas 的**宿主面**声明——仅供类型检查，运行期从不加载。

拆分后每个 Mixin 都是独立类，pyright 看不到兄弟 Mixin / 主类 / Qt 基类上的
成员（``self._image`` / ``self.mapFromScene`` …），会把它们整块报成
``reportAttributeAccessIssue``。这里把「主类 + 全部兄弟 Mixin」的成员面集中
声明一次，各 Mixin 在**类型检查期**以 CanvasHost 为基类继承进来：

    if TYPE_CHECKING:
        from ._host import CanvasHost
    else:
        CanvasHost = object        # 运行期退化成 object ⇒ MRO 与行为零改动

⚠️ 成员落点 / 签名改动后要同步本文件——守卫
``tests/selftests/viewer_split.py`` 会核对它覆盖了全部成员。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QImage, QTransform
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPixmapItem, QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView
from desktop.components.viewers.image_editor.text_item import TextBlockItem
from typing import Any


class CanvasHost(QGraphicsView):
    """``EditorCanvas`` 的成员面：主类 + 3 个 Mixin。

    只有注解与 ``...`` 桩，没有任何实现——不要在这里写逻辑。
    """

    # ---- 状态 ----
    _active_text_block: Any
    _border: QGraphicsRectItem | None
    _edge_lines: dict[str, QGraphicsLineItem]
    _erase_size: Any
    _eraser_pos: QPointF
    _eraser_ring: list[QGraphicsEllipseItem]
    _fit_ratio: float
    _float_item: QGraphicsPixmapItem | None
    _handles: dict[str, QGraphicsRectItem]
    _hover_handle: Any
    _image: Any
    _item: Any
    _mask: list[QGraphicsRectItem]
    _mode: tuple | tuple[Any, ...] | None
    _paint_image: Any
    _pivot_item: QGraphicsEllipseItem
    _quad: QGraphicsPolygonItem
    _rect: Any
    _scene: QGraphicsScene
    _sel_border: QGraphicsRectItem
    _text_outline: QGraphicsRectItem
    _tool: Any
    _user_zoomed: bool
    _xf: Any
    _xf_about_pivot: bool
    _xf_pivot: Any
    _xf_rect: QRectF | None
    _xf_region: Any
    _xf_reshape: Any
    _xf_touched: bool
    _zoom: Any
    reshape_finished: Signal
    stroke_started: Signal
    text_requested: Signal

    # ---- 方法（主类 + 各 Mixin）----
    def _apply_hover_highlight(self) -> None:
        ...

    def _apply_shear(self, edge: str, k: float, x_start: QTransform) -> None:
        ...

    def _build_overlay(self) -> None:
        ...

    def _clear_transform_preview(self) -> None:
        ...

    def _ensure_transform_preview(self) -> None:
        ...

    def _erase_at(self, start: QPointF, end: QPointF) -> None:
        ...

    def _handle_boxes(self, rect: QRectF) -> dict[str, QRectF]:
        ...

    def _hide_eraser_ring(self) -> None:
        ...

    def _hide_text_outline(self) -> None:
        ...

    def _hit_handle(self, view_pos: QPointF) -> str | None:
        ...

    def _hit_transform(self, view_pos: QPointF) -> str:
        ...

    def _move_eraser_ring(self, pos: QPointF, show: bool = True) -> None:
        ...

    def _move_text_outline(self, block: TextBlockItem) -> None:
        ...

    def _resize_rect(self, handle: str, pos: QPointF) -> None:
        ...

    def _sync_cursor(self) -> None:
        ...

    def _sync_float(self) -> None:
        ...

    def _sync_overlay(self) -> None:
        ...

    def _sync_scene_rect(self) -> None:
        ...

    def _sync_transform_overlay(self) -> None:
        ...

    def _text_block_at(self, pos: QPointF) -> TextBlockItem | None:
        ...

    def _transform_quad(self) -> dict[str, QPointF]:
        ...

    def _update_hover_cursor(self, view_pos: QPointF) -> None:
        ...

    def add_text_block(self, pos: QPointF, px: int, color: QColor,
                       family: str) -> TextBlockItem:
        ...

    def clear_text_blocks(self) -> None:
        ...

    def fit(self, ratio: float | None = None) -> None:
        ...

    def fit_selection(self) -> None:
        ...

    def focus_text_block(self, block: TextBlockItem | None = None) -> None:
        ...

    def focused_text_block(self) -> TextBlockItem | None:
        ...

    @property
    def image(self) -> QImage | None:
        ...

    def image_rect(self) -> QRectF:
        ...

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # 就地编辑文字时按键（含 ←/→ 移光标）全部给文本编辑，不走翻页
        ...

    def leaveEvent(self, event) -> None:  # noqa: N802
        # 鼠标离开画布：高亮熄灭、橡皮擦圈/文字边界框隐藏、光标回默认
        ...

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        ...

    def mousePressEvent(self, event) -> None:  # noqa: N802
        ...

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        ...

    def refresh(self) -> None:
        ...

    def replace_image(self, image: QImage) -> None:
        ...

    def reset_transform(self) -> None:
        ...

    def resizeEvent(self, event) -> None:  # noqa: N802
        ...

    def selection(self) -> QRectF | None:
        ...

    def set_eraser(self, size: int) -> None:
        ...

    def set_fit_ratio(self, ratio: float) -> None:
        ...

    def set_image(self, image: QImage | None) -> None:
        ...

    def set_tool(self, tool: str) -> None:
        ...

    def set_transform_about_pivot(self, about: bool) -> None:
        ...

    def set_transform_reshape(self, on: bool) -> None:
        ...

    def set_zoom(self, zoom: float, anchor_view: QPointF | None = None) -> None:
        ...

    def style_target_block(self) -> TextBlockItem | None:
        ...

    def text_blocks(self) -> list[TextBlockItem]:
        ...

    def transform_move(self, dx: float, dy: float) -> None:
        ...

    def transform_pending(self) -> tuple[QRectF, QTransform, QImage] | None:
        ...

    def transform_rotate(self, degrees: float) -> None:
        ...

    def transform_scale(self, sx: float, sy: float,
                        anchor: QPointF | None = None) -> None:
        ...

    def transform_shear(self, edge: str, k: float) -> None:
        ...

    def wheelEvent(self, event) -> None:  # noqa: N802
        ...

    def zoom_in(self) -> None:
        ...

    def zoom_out(self) -> None:
        ...
