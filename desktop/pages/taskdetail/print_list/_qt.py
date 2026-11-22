# -*- coding: utf-8 -*-
"""Qt 基础类的一次性导入：拆包后各子模块共用，避免同一名字重复导入。"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QFileDialog, QWidget

__all__ = ["QTimer", "QDialog", "QFileDialog", "QWidget"]
