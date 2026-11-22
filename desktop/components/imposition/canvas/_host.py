# -*- coding: utf-8 -*-
"""``ImpositionCanvas`` 的**宿主面**声明——仅供类型检查，运行期从不加载。

拆包后每个 Mixin 都是独立类，pyright 看不到兄弟 Mixin / 主类 / Qt 基类上的
成员，会整块报 ``reportAttributeAccessIssue``。这里把「主类 + 全部兄弟 Mixin」
的成员面集中声明一次，各 Mixin 在**类型检查期**以 :class:`CanvasHost`
为基类继承进来：

    if TYPE_CHECKING:
        from desktop.components.imposition.canvas._host import CanvasHost as _Host
    else:
        _Host = object            # 运行期退化成 object ⇒ MRO 与行为零改动

⚠️ 成员落点 / 签名改动后要同步本文件——只写注解与 ``...`` 桩，不写逻辑。
"""

from __future__ import annotations

from typing import Callable

from desktop.components.imposition.canvas._qt import (
    QImage,
    QPointF,
    QRectF,
    QTimer,
    QWidget,
    Signal,
)


class CanvasHost(QWidget):
    """``ImpositionCanvas`` 的成员面：主类 + 3 个 Mixin（几何 / 绘制 / 交互）。"""

    # ---- 信号 ----
    items_changed: Signal
    selection_changed: Signal
    item_preview_requested: Signal
    spread_double_clicked: Signal
    item_edit_requested: Signal
    spread_edit_requested: Signal
    locate_failed: Signal

    # ---- 状态 ----
    _items: list[dict]
    _images: dict[str, QImage]
    _display_cache: dict[tuple[str, int], QImage]
    _selected: int
    _locate_resolver: Callable[[int], list] | None
    _pad: int
    _pad_top: int
    _px_per_unit: float
    _off_x: float
    _off_y: float
    _mode: str | None
    _handle: int
    _grab_x: float
    _grab_y: float
    _grab_rect: list[float]
    _grab_rotation: float
    _grab_angle: float
    _grab_center: QPointF
    _dirty: bool
    _pressed: bool
    _zoom: float
    _fit_ppu: float
    _fit_off_x: float
    _fit_off_y: float
    _wheel_burst: bool
    _wheel_paint_pending: bool
    _wheel_timer: QTimer

    # ---- 主类（widget）----
    def items(self) -> list[dict]:
        return []

    def _emit_changed(self) -> None:
        return

    def frame_visible(self) -> bool:
        return False

    # ---- 几何 Mixin ----
    def _scene_rect(self) -> QRectF:
        return QRectF()

    def _item_box_units(self, item: dict) -> tuple[float, float, float, float]:
        return (0.0, 0.0, 0.0, 0.0)

    def _spread_center_units(self) -> tuple[float, float]:
        return (0.0, 0.0)

    def _to_units(self, pos: QPointF) -> tuple[float, float]:
        return (0.0, 0.0)

    def _rect_px(self, index: int) -> QRectF:
        return QRectF()

    def _to_local_px(self, index: int, pos: QPointF) -> QPointF:
        return QPointF()

    def _item_contains_px(self, index: int, pos: QPointF) -> bool:
        return False

    def _handle_positions_local(self, index: int) -> list[tuple[float, float]]:
        return []

    def _handle_positions(self, index: int) -> list[tuple[float, float]]:
        return []

    def _rotate_knob_local(self, index: int) -> QPointF:
        return QPointF()

    def _rotate_knob(self, index: int) -> QPointF:
        return QPointF()

    def _hit_handle(self, index: int, pos: QPointF) -> int | None:
        return -1

    def _item_at(self, pos: QPointF) -> int:
        return -1

    # ---- 绘制 Mixin ----
    def _spine_visible(self) -> bool:
        return False

    def _image(self, path: str) -> QImage | None:
        return None

    def _image_size(self, path: str) -> tuple[int, int] | None:
        return None

    def _display_image(self, path: str, need_edge: float) -> QImage | None:
        return None

    def _draw_crop_frame(self, painter) -> None:
        return

    def _draw_item(self, painter, index: int, item: dict) -> None:
        return

    def _draw_frame(self, painter, index: int) -> None:
        return

    def _draw_rotate_knob(self, painter, height_px: float) -> None:
        return

    def _draw_selected_border(self, painter, index: int) -> None:
        return
