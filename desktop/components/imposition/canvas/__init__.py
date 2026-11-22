# -*- coding: utf-8 -*-
"""拼版画布（原 ``canvas.py`` 拆包）：对外名字在此**显式重导出**。

拆包前 ``from desktop.components.imposition.canvas import X`` 能取到的一切
（含私有常量与 ``_trim_transparent_border``），这里原样保留——外部 import
路径与名字不变。
"""

from __future__ import annotations

from desktop.components.imposition.canvas.constants import (
    CROP_COLOR,
    DISPLAY_EDGE_STEPS,
    EDGE_HIT_PX,
    FRAME_COLOR,
    FRAME_STYLE,
    HANDLE_FILL,
    HANDLE_RADIUS,
    HANDLE_STROKE,
    MIN_RECT,
    PAGE_COLOR,
    ROTATE_ARC_BARB,
    ROTATE_ARC_GAP,
    ROTATE_ARC_SPAN,
    ROTATE_ARC_START,
    ROTATE_KNOB_GAP,
    ROTATE_KNOB_HIT,
    ROTATE_KNOB_RADIUS,
    SNAP_DEGREES,
    SPINE_COLOR,
    WHEEL_REPAINT_MS,
    WHEEL_ZOOM_STEP,
    ZOOM_MAX,
    ZOOM_MIN,
    _CORNER_CURSORS,
    _EDGE_BY_HANDLE,
    _EDGE_CURSORS,
    _HANDLE_CURSORS,
)
from desktop.components.imposition.canvas.images import _trim_transparent_border
from desktop.components.imposition.canvas.widget import ImpositionCanvas

__all__ = [
    "ImpositionCanvas",
    "PAGE_COLOR",
    "FRAME_STYLE",
    "FRAME_COLOR",
    "HANDLE_STROKE",
    "HANDLE_FILL",
    "HANDLE_RADIUS",
    "ROTATE_KNOB_RADIUS",
    "ROTATE_KNOB_GAP",
    "ROTATE_KNOB_HIT",
    "ROTATE_ARC_GAP",
    "ROTATE_ARC_START",
    "ROTATE_ARC_SPAN",
    "ROTATE_ARC_BARB",
    "MIN_RECT",
    "EDGE_HIT_PX",
    "SNAP_DEGREES",
    "SPINE_COLOR",
    "CROP_COLOR",
    "WHEEL_ZOOM_STEP",
    "ZOOM_MIN",
    "ZOOM_MAX",
    "DISPLAY_EDGE_STEPS",
    "WHEEL_REPAINT_MS",
    "_CORNER_CURSORS",
    "_EDGE_CURSORS",
    "_HANDLE_CURSORS",
    "_EDGE_BY_HANDLE",
    "_trim_transparent_border",
]
