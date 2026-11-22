# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""多图编辑：右侧图层切换器与换层。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, QSizeF, Qt, Signal
from PySide6.QtGui import QImage, QKeySequence, QShortcut, QTransform
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget,
)

from desktop.ui import theme as T
from desktop.ui.window_size import apply_window_size
from ..canvas import EditorCanvas
from ..consts import (
    ERASER_DEFAULT, HISTORY_ORIGIN_LABEL, TEXT_COLOR_DEFAULT, TEXT_DEFAULT,
)
from ..geometry import _trim_transparent_edges, _transparent_content_bounds

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._host import DialogHost
else:
    DialogHost = object



class LayerSwitchMixin(DialogHost):
    """多图编辑：右侧图层切换器与换层。"""


    # ---- 激活图层：右侧面板显示 + 切换（2026-10-13 用户口径） ----
    def _build_layer_switcher(self) -> None:
        """按当前图层标签在右侧面板顶部铺一排切换按钮（双图才显示）。"""
        row = getattr(self, "_layer_row", None)
        if row is None:
            return
        layout = row.layout()
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._layer_buttons = []
        if len(self._multi_layers) < 2:
            row.setVisible(False)
            return
        from qfluentwidgets import ToggleButton

        for index, layer in enumerate(self._multi_layers):
            button = ToggleButton(layer["label"] or f"图层{index + 1}", row)
            button.clicked.connect(
                lambda _checked=False, i=index: self._activate_layer(i))
            layout.addWidget(button)
            self._layer_buttons.append(button)
        row.setVisible(True)
        self._sync_layer_switcher()

    def _sync_layer_switcher(self) -> None:
        """按钮选中态跟随活动层（程序化刷新，挡住回灌）。"""
        self._layer_buttons_syncing = True
        try:
            for index, button in enumerate(self._layer_buttons):
                button.setChecked(index == self._active_layer)
        finally:
            self._layer_buttons_syncing = False

    def _activate_layer(self, index: int) -> None:
        """右侧面板/外部请求把第 ``index`` 层设为激活层。"""
        if not self._multi_layers or index == self._active_layer:
            # 点的就是当前层：按钮弹回选中态即可，不空跑一次切层
            self._sync_layer_switcher()
            return
        if not 0 <= index < len(self._multi_layers):
            return
        self._switch_context_layer()
        self._sync_layer_switcher()

    def _switch_context_layer(self) -> None:
        """点击另一张图切换活动层：世界纹丝不动，两边互不影响。

        用户 2026-10-13 定的模型（对齐拼版页的手感）：两张图是两个**一直
        存在的独立图层**，摆在版面相对位置上；切换只换"哪张可编辑"——

        - **不烘焙**：挂起的变换预览不"应用"，当前显示效果拼成 ghost 留给
          非活动态展示（A 转了 15°，切到 B 时 A 还是转过的样子）；切回本层
          实时预览从快照原样恢复（亚毫秒，零重采样）。烘焙只发生在「完成」
          （:meth:`_bake_inactive_pending`）。
        - **视图不动**：切层不适配、不缩放、不重定位，只替换活动图片与
          非活动图片的显示图元。
        """
        if len(self._multi_layers) != 2 or self._active_layer < 0:
            return
        old_index = self._active_layer
        new_index = 1 - old_index
        self._commit_text_blocks()
        self._commit_crop()
        # 挂起变换预览：拼 ghost（要在 `_commit_crop` **之后**——裁剪若
        # 真落了像素，浮层已被 set_image 清掉，ghost 自然为 None）
        ghost = self._render_layer_ghost()
        self._multi_layers[old_index]["state"] = self._capture_layer_state()
        self._multi_layers[old_index]["canvas_state"] = (
            self.canvas.capture_transform_state()
        )
        self._multi_layers[old_index]["ghost"] = ghost[0] if ghost else None
        self._multi_layers[old_index]["ghost_origin"] = (
            ghost[1] if ghost else None)
        self._load_layer(new_index)
        self._multi_layers[new_index]["ghost"] = None
        self._multi_layers[new_index]["ghost_origin"] = None
        self.canvas.clear_text_blocks()
        # ``refit=False``：切层只换图片，不改视图缩放。
        self.canvas.set_image(self._image, refit=False)
        layer_canvas_state = self._multi_layers[new_index].get("canvas_state")
        if layer_canvas_state is None:
            self.canvas.rearm_content_restore()
            if self.canvas.tool == "transform":
                self.canvas.set_tool("transform")
        else:
            self.canvas.restore_transform_state(layer_canvas_state)
        self._refresh_multi_canvas()
        self._refresh_tool_page(self.canvas.tool)
        self._refresh_size_label()
        self._sync_undo_buttons()
        self._sync_history()
        self._sync_layer_switcher()
