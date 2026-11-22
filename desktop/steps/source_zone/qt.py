# -*- coding: utf-8 -*-
"""本包用到的 PySide6 符号：集中一处导入，子模块从这里取。

⚠️ 只是转发、不加工。PySide6 的类型信息在 pylint 下不完整（既有误报），
集中导入可避免同一批告警随拆分的子模块数量增长。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QSizePolicy,
    QWidget,
)

__all__ = [
    "QColor",
    "QFileDialog",
    "QFont",
    "QFontMetrics",
    "QHBoxLayout",
    "QPainter",
    "QPen",
    "QRectF",
    "QSizePolicy",
    "QTimer",
    "QWidget",
    "Qt",
    "Signal",
]
