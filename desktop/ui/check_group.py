# -*- coding: utf-8 -*-
"""一组「复选框外观、单选语义」的选项（创建任务页的**任务类型**用它）。

用户 2026-11-17：

    「任务类型，不要使用胶囊，而是 Checkbox 样式框，但是是单选，分别是
     常规任务/聚合任务，后续还可以加其他任务」

所以这里刻意**不是** :class:`~desktop.ui.segmented_toggle.SegmentedToggle`
（那个是胶囊滑块，给"同一视图换形态"用的），而是真的 ``CheckBox``：

- 外观＝qfluentwidgets 的 ``CheckBox``（方框 + 勾），选中项文字加粗，一眼看得出
  勾在哪一个；
- 语义＝**单选**：勾一个，别的自动灭；**点掉当前唯一勾选不生效**（恒有一个被
  选中，与「聚合任务起始节点」同一条纪律——界面不能出现"什么都没选"）；
- 只有用户点击才发 ``current_changed``；``set_current`` 是程序化切换、不发信号
  （否则"回流刷新选中项"会自我递归，同 ``SegmentedToggle``）；
- **加新类型**＝调用方在选项表里多给一项（:meth:`add_item` 也支持运行时追加），
  这里不含任何"任务"专属知识。
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget
from qfluentwidgets import CheckBox

from desktop.ui import theme as T
from desktop.ui.fonts import ui_font


class CheckBoxGroup(QWidget):
    """复选框外观、单选语义的一组选项。

    ``items`` 为 ``[(键, 文案), ...]``，默认选中第一项。
    """

    #: 用户点击换了选中项（键）。程序化 ``set_current`` **不发**这个信号。
    current_changed = Signal(str)

    #: 选项之间的横向间距（px）
    SPACING = T.SPACE_LG

    def __init__(self, items: Sequence[Sequence[str]], parent=None):
        super().__init__(parent)
        self._items = [(str(key), str(text)) for key, text in items]
        self._current = self._items[0][0] if self._items else ""
        #: 程序化勾选期间屏蔽 ``toggled`` 回流（否则 setChecked 会再触发一次）
        self._syncing = False
        self._boxes: dict[str, CheckBox] = {}

        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(self.SPACING)
        for key, text in self._items:
            self._add_box(key, text)

        # ⚠️ 只占内容宽度：默认的 Preferred 策略会被外层 QHBoxLayout 拉开
        #    （用户 2026-11-17 上一轮刚抱怨过"跟页面一样宽了，不好看"）。
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._sync()

    # ------------------------------------------------------------------ API
    def current(self) -> str:
        """当前选中的键。"""
        return self._current

    def keys(self) -> list[str]:
        """全部选项的键，顺序即摆放顺序。"""
        return [key for key, _ in self._items]

    def box(self, key: str) -> CheckBox | None:
        """取某一项的复选框（设置 tooltip / 判状态用）。"""
        return self._boxes.get(key)

    def set_current(self, key: str) -> None:
        """程序化切换选中项，**不发** ``current_changed``。"""
        if key == self._current or key not in self._boxes:
            return
        self._current = key
        self._sync()

    def add_item(self, key: str, text: str) -> CheckBox:
        """追加一个选项（运行时加新类型用），返回它的复选框。"""
        key, text = str(key), str(text)
        if key in self._boxes:
            return self._boxes[key]
        self._items.append((key, text))
        box = self._add_box(key, text)
        if not self._current:
            self._current = key
            self._sync()
        return box

    # ----------------------------------------------------------------- 内部
    def _add_box(self, key: str, text: str) -> CheckBox:
        box = CheckBox(text, self)
        box.setFont(ui_font(T.SIZE_BODY))
        # ⚠️ 必须用 lambda 兜住 checked 实参：QCheckBox.toggled 自带一个 bool，
        #    直接接 ``self._on_toggled`` 会把 bool 当成 key。
        box.toggled.connect(
            lambda checked, _key=key: self._on_toggled(_key, checked)
        )
        self._row.addWidget(box)
        self._boxes[key] = box
        return box

    def _sync(self) -> None:
        """把复选框的勾选状态对齐到 ``self._current``（单选）。"""
        self._syncing = True
        try:
            for key, box in self._boxes.items():
                box.setChecked(key == self._current)
        finally:
            self._syncing = False

    def _on_toggled(self, key: str, checked: bool) -> None:
        if self._syncing:
            return
        if not checked:
            # 用户点掉了**当前唯一**勾选 ⇒ 不生效，把勾补回去（恒有一个被选中）
            self._sync()
            return
        if key == self._current:
            return
        self._current = key
        self._sync()
        self.current_changed.emit(key)
