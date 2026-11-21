# -*- coding: utf-8 -*-
"""
File: safecomponents.py
修复 QFluentWidgets SpinBox / LineEdit 悬浮滚轮直接修改数值、hover自动抢焦点问题
规则：只有控件获得焦点后，滚轮才响应；无焦点时滚轮透传给外层滚动区域
"""

from PySide6.QtCore import Qt, QEvent, QObject
from PySide6.QtWidgets import QLineEdit
from qfluentwidgets import SpinBox, DoubleSpinBox, CompactSpinBox, CompactDoubleSpinBox


#: 量宽度用的"最长文本"样本（4 位整数 + 1 位小数 + 单位）。
#: 见 :func:`keep_spin_text_visible`。
_SPIN_TEXT_SAMPLE = "0000.0 mm"


def keep_spin_text_visible(spin) -> None:
    """兜底：别让 fluent spin 内部的 QLineEdit 被压成 1px（值就看不见了）。

    ⚠️⚠️ **2026-11-21 打包版实测事故**：qfluentwidgets 的 SpinBox 把「上/下」
    两个按钮放进**自己的 QHBoxLayout**（`InlineSpinBoxBase.__init__`）。PySide6
    6.11 起 `QAbstractSpinBox` 按"控件已有布局"的方式排内部 QLineEdit，把它压到
    **1px 宽**——值其实在（`text()` 是对的），但一个像素都不显示；界面上只剩
    两个箭头，看起来像"整个界面的输入框都不显示值了"。开发环境装的是 6.9.2，
    同一个 qfluentwidgets 1.11.3 正常 ⇒ 只有构建环境（yolobuild 里 6.11.3）
    出的包有病，极难在开发机上复现（用户 2026-11-21 报的就是这个）。

    修法是给内部 QLineEdit 一个**足以放下最长文本的最小宽度**：6.9/6.10 上它
    远小于可用宽度，布局照旧拉伸，视觉零变化；6.11+ 上它正好托住被压扁的
    编辑框。Qt 只认"最小宽度"，不会因此变成固定宽。

    ⚠️ 只在我们自己的控件上调用；直接用 qfluentwidgets 的 spin 的地方
    （如拼版角度框）必须显式调一次，否则仍会被压扁。
    """
    try:
        edit = spin.lineEdit()
    except (AttributeError, RuntimeError):  # 不是 QAbstractSpinBox（或已析构）
        return
    if edit is None:
        return
    need = edit.fontMetrics().horizontalAdvance(_SPIN_TEXT_SAMPLE) + 12
    if edit.minimumWidth() < need:
        edit.setMinimumWidth(need)


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
        keep_spin_text_visible(self)

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
        keep_spin_text_visible(self)

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
        keep_spin_text_visible(self)

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
        keep_spin_text_visible(self)

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
