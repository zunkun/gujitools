# -*- coding: utf-8 -*-
"""
File: safecomponents.py
修复 QFluentWidgets SpinBox / LineEdit 悬浮滚轮直接修改数值、hover自动抢焦点问题
规则：只有控件获得焦点后，滚轮才响应；无焦点时滚轮透传给外层滚动区域
"""

from PySide6.QtCore import Qt, QEvent, QObject
from PySide6.QtWidgets import QLineEdit
from qfluentwidgets import SpinBox, DoubleSpinBox, CompactSpinBox, CompactDoubleSpinBox


class SafeLineEdit(QLineEdit):
    """普通文本输入框：悬浮不自动聚焦，无焦点时滚轮透传"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def enterEvent(self, event):
        super().enterEvent(event)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class SafeSpinBox(SpinBox):
    """QFluentWidgets 整数SpinBox，修复悬浮滚轮修改数值"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class SafeDoubleSpinBox(DoubleSpinBox):
    """QFluentWidgets 浮点数SpinBox（用于带 mm 单位边距控件）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class SafeCompactSpinBox(CompactSpinBox):
    """QFluentWidgets 紧凑版整数SpinBox"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class SafeCompactDoubleSpinBox(CompactDoubleSpinBox):
    """QFluentWidgets 紧凑版浮点数SpinBox"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class FluentSpinWheelFilter(QObject):
    """
    全局事件过滤器（存量界面不想替换控件类时使用）
    一次性拦截所有 fluent spinbox 无焦点滚轮事件
    使用：
    _filter = FluentSpinWheelFilter()
    widget.installEventFilter(_filter)
    """

    def eventFilter(self, obj, event):
        target_types = (SpinBox, DoubleSpinBox, CompactSpinBox, CompactDoubleSpinBox)
        if isinstance(obj, target_types):
            if event.type() == QEvent.Type.Wheel:
                if not obj.hasFocus():
                    event.ignore()
                    return True
        return super().eventFilter(obj, event)
