# -*- coding: utf-8 -*-
"""``BpmnEditor`` 的**宿主面**声明——仅供类型检查，运行期从不加载。

拆分后每个 Mixin 都是独立类，pyright 看不到兄弟 Mixin / 主类 / Qt 基类上的
成员，会整块报 ``reportAttributeAccessIssue``。这里把「主类 + 全部兄弟 Mixin」
的成员面集中声明一次，各 Mixin 在**类型检查期**以 :class:`BpmnEditorHost`
为基类继承进来：

    if TYPE_CHECKING:
        from desktop.components.bpmn_editor._host import BpmnEditorHost as _Host
    else:
        _Host = object            # 运行期退化成 object ⇒ MRO 与行为零改动

⚠️ 成员落点 / 签名改动后要同步本文件——只写注解与 ``...`` 桩，不写逻辑。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from desktop.components.bpmn_editor._qt import QPointF, Signal

from desktop.components.bpmn_view import BpmnView


class BpmnEditorHost(BpmnView):
    """``BpmnEditor`` 的成员面：主类 + 2 个 Mixin（交互 / 对话框）。"""

    # ---- 信号 ----
    diagram_changed: Signal
    selection_changed: Signal
    flow_selection_changed: Signal
    link_mode_changed: Signal

    # ---- 状态 ----
    _floor: tuple[float, float]
    _name_source: Any
    _drag_id: str | None
    _drag_offset: QPointF
    _drag_note: str | None
    _drag_note_offset: QPointF
    _drag_sides: dict[str, tuple]
    _press_pos: QPointF | None
    _moved: bool
    _link_from: str | None
    _link_pos: QPointF | None
    _link_mode: bool

    # ---- 编辑动作（主类）----
    def add_node(self, kind: str = ..., name: str = ...,
                 stage: str | None = ..., at: tuple[float, float] | None = ...,
                 connect_from: str | None = ...) -> str: ...

    def add_step(self, token: str, at: tuple[float, float] | None = ...,
                 connect_from: str | None = ...) -> str | None: ...

    def connect(self, source: str, target: str, label: str = ...) -> str | None: ...

    def rename_node(self, node_id: str, name: str) -> None: ...

    def rename_flow(self, flow_id: str, label: str) -> None: ...

    def rename_selected(self, name: str) -> bool: ...

    def remove_node(self, node_id: str) -> None: ...

    def remove_flow(self, flow_id: str) -> None: ...

    def remove_selected(self) -> bool: ...

    def save_to(self, path: Path | str) -> Path: ...

    def auto_layout(self) -> None: ...

    def set_canvas_floor(self, width: float, height: float) -> None: ...

    def link_mode(self) -> bool: ...

    def set_link_mode(self, enabled: bool) -> None: ...

    # ---- 命中（交互 Mixin）----
    def _ports_of(self, node_id: str) -> list[tuple[str, QPointF]]: ...

    def _port_at(self, point: QPointF) -> tuple[str, str] | None: ...

    def _nearest_port(self, node_id: str, point: QPointF) -> QPointF: ...

    def flow_at(self, point: QPointF) -> str | None: ...

    # ---- 拖拽（交互 Mixin）----
    def _passes_threshold(self, point: QPointF) -> bool: ...

    def _move_node(self, point: QPointF) -> None: ...

    def _shift_notes(self, node_id: str, dx: float, dy: float) -> None: ...

    def _move_note(self, point: QPointF) -> None: ...

    def _finish_drag(self) -> None: ...

    # ---- 对话框（对话框 Mixin）----
    def ask_add_node(self) -> None: ...

    def _confirm_zh(self, title: str, text: str, *, yes_text: str = ...,
                    no_text: str = ...) -> bool: ...

    def _input_text_zh(self, title: str, label: str,
                       text: str = ...) -> tuple[str, bool]: ...

    def ask_rename_selected(self) -> None: ...

    def ask_delete_selected(self) -> None: ...
