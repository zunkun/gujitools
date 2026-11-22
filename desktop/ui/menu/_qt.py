# -*- coding: utf-8 -*-
"""PySide6 名字集中导入（拆包后各子模块从这里取，避免重复声明）。"""

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFontMetrics, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMenuBar,
    QVBoxLayout,
    QWidget,
)


