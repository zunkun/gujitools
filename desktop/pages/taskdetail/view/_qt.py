# -*- coding: utf-8 -*-
"""Qt 基础控件的一次性导入：拆包后各子模块共用，避免同一名字重复导入。"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import (
    QBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

__all__ = [
    "QObject",
    "QTimer",
    "QBoxLayout",
    "QHBoxLayout",
    "QLabel",
    "QLineEdit",
    "QStackedWidget",
    "QVBoxLayout",
    "QWidget",
]
