# -*- coding: utf-8 -*-
"""按钮手型光标过滤器（自 ``desktop/ui/widgets.py`` 拆出）。"""

from __future__ import annotations

from ._qt import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QComboBox,
    QEvent,
    QObject,
    Qt,
)

class _ButtonCursorFilter(QObject):
    """全局按钮光标过滤器：按钮首次被布局（Polish 事件）时设手型光标。

    挂在 QApplication 上，覆盖现在和将来创建的所有按钮，不用每个按钮
    单独 setCursor。下拉框（qfluent 的 ``ComboBox`` 继承 ``QPushButton``）
    与复选框是"选择"不是"按压"，保持系统箭头光标。
    """

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.Type.Polish
            and isinstance(obj, QAbstractButton)
            and not isinstance(obj, (QCheckBox, QComboBox))
        ):
            obj.setCursor(Qt.CursorShape.PointingHandCursor)
        return False


def install_button_pointer_cursor(app: QApplication) -> None:
    """给整个应用的按钮启用 hover 手型光标（见 :class:`_ButtonCursorFilter`）。"""
    guard = getattr(app, "_button_cursor_filter", None)
    if guard is None:
        guard = _ButtonCursorFilter(app)
        # 过滤器必须保引用，否则被 GC 摘掉。⚠️ 属性是动态挂到 QApplication 上的，
        # 类型存根里没有，用 setattr（运行时与直接赋值一样）。
        setattr(app, "_button_cursor_filter", guard)
        app.installEventFilter(guard)
