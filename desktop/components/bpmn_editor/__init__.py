# -*- coding: utf-8 -*-
"""BPMN 流程图**编辑控件**（原 ``desktop/components/bpmn_editor.py`` 的包化）。

⚠️ 2026-11-22 起按职责拆成子包：常量/几何 ``constants``、宿主类型面
``_host``、交互与绘制 ``interaction``、对话框 ``dialogs``、主体 ``editor``。
本 ``__init__`` 只做重导出——既有 ``from desktop.components.bpmn_editor
import X`` 全部不变；子模块之间不要反过来导入本包（会形成循环）。
"""

from desktop.components.bpmn_editor.constants import (
    DRAG_THRESHOLD,
    EDGE_HIT,
    NEW_NODE_GAP,
    PLACE_TRIES,
    PORT_HIT,
    PORT_RADIUS,
    _distance_to_segment,
)
from desktop.components.bpmn_editor.editor import BpmnEditor

__all__ = [
    "BpmnEditor",
    "EDGE_HIT",
    "PORT_HIT",
    "PORT_RADIUS",
    "DRAG_THRESHOLD",
    "NEW_NODE_GAP",
    "PLACE_TRIES",
    "_distance_to_segment",
]
