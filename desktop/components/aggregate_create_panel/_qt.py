# -*- coding: utf-8 -*-
"""PySide6 导入的**唯一落点**（各子模块从这里取，别各自再 import 一遍）。

拆包后同一个 Qt 名字会在多个子模块里用到；每处各写一行 ``from PySide6...``
会让 pylint 的 ``no-name-in-module``（PySide6 是 C 扩展，pylint 认不出名字）
按「用到次数」翻倍。集中到这里后，每个名字只报一次——与拆包前一致。
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
