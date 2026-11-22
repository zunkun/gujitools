# -*- coding: utf-8 -*-
"""PySide6 导入集中点：全包只在这里导入一次，避免每个子模块各报一遍 no-name-in-module（pylint 对
PySide6 的既有误报）。子模块按需 ``from ._qt import X``。"""

from __future__ import annotations

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer
