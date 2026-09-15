# -*- coding: utf-8 -*-
"""标题切换节点列表：不用表格，高度完全由内容撑开。

原来的做法是 QTableWidget：表格必须有表头 + 固定高度，行数超过上限就只能
靠内部滚动条兜住，于是「高度自适应」永远是人工算出来的常量组合，控件高度
随主题/DPI 一变就被压扁或裁掉。

这里换成 QVBoxLayout 逐行堆叠的普通控件：
- 行数增加 → 容器 sizeHint 自然变大，不需要任何高度计算；
- 行数再多也不会出现内部滚动条（外层面板的 ScrollArea 统一滚动）；
- 每行自带删除按钮，不再依赖「选中行」这种表格语义；
- 行内控件的真实高度就是行高，不存在被行高挤压的可能。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, ComboBox, LineEdit, SpinBox, ToolButton
from qfluentwidgets import FluentIcon as FIF

from desktop.components.panels.print_params import SIDES
from desktop.ui.widgets import combo_box

PAGE_MIN = 1
PAGE_MAX = 100000

_SPIN_W = 120  # 触发页码控件宽度：qfluent SpinBox 的上下按钮覆盖右侧约 71px，
               # 低于 120 时数字会被按钮压住看不清
_SIDE_W = 76   # 侧别下拉宽度
_DEL_W = 30    # 行内删除按钮宽度
_GAP = 6       # 行内/行间间距


def _make_side_combo(side: str) -> ComboBox:
    """侧别下拉：中文显示、英文值（存于 itemData）。"""
    combo = combo_box(SIDES, width=_SIDE_W)
    idx = combo.findData(side)
    if idx < 0:
        idx = combo.findData("left")
    combo.setCurrentIndex(max(idx, 0))
    combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    return combo


class NodeRow(QWidget):
    """一个标题切换节点：触发页码 + 标题 + 侧别 + 删除按钮。"""

    removeRequested = Signal(object)

    def __init__(self, page: int = 1, title: str = "", side: str = "left", parent=None):
        """构造一个标题切换节点行：页码 + 标题 + 侧别 + 删除按钮。

        用 QHBoxLayout 横向排布，各行自带删除按钮；removeRequested 在点击
        删除时带上本行自身，标题空行在收集时被忽略。
        """
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(_GAP)

        self.page_spin = SpinBox()
        self.page_spin.setRange(PAGE_MIN, PAGE_MAX)
        self.page_spin.setValue(int(page))
        self.page_spin.setFixedWidth(_SPIN_W)
        self.page_spin.setToolTip("触发页码：实际页码 ≥ 该值时改用本行标题")
        self.page_spin.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        self.title_edit = LineEdit()
        self.title_edit.setPlaceholderText("标题文本")
        self.title_edit.setText(str(title))
        self.title_edit.setMinimumWidth(0)
        self.title_edit.setToolTip("标题为空的行不会写入配置")
        self.title_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.side_combo = _make_side_combo(side)

        self.del_btn = ToolButton(FIF.DELETE)
        self.del_btn.setFixedWidth(_DEL_W)
        self.del_btn.setToolTip("删除该节点")
        self.del_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.del_btn.clicked.connect(lambda: self.removeRequested.emit(self))

        lay.addWidget(self.page_spin)
        lay.addWidget(self.title_edit, 1)
        lay.addWidget(self.side_combo)
        lay.addWidget(self.del_btn)

    def value(self) -> list | None:
        """收集本行配置；标题为空返回 None（该行忽略）。"""
        title = self.title_edit.text().strip()
        if not title:
            return None
        node: list = [self.page_spin.value(), title]
        side = self.side_combo.currentData()
        # 双面（both）为缺省值，省略第三项；左页/右页显式携带
        if side and side != "both":
            node.append(side)
        return node


class NodeListWidget(QWidget):
    """节点行容器：行数决定高度，无表头、无内部滚动条。"""

    changed = Signal()

    def __init__(self, parent=None):
        """构造节点容器：QVBoxLayout 逐行堆叠，默认显示空态提示。"""
        super().__init__(parent)
        self._rows: list[NodeRow] = []
        self._box = QVBoxLayout(self)
        self._box.setContentsMargins(0, 0, 0, 0)
        self._box.setSpacing(_GAP)

        self._empty_hint = CaptionLabel("未配置标题切换：整本使用上方标题")
        self._empty_hint.setWordWrap(True)
        self._box.addWidget(self._empty_hint)

    # ------------------------------------------------------------------ 查询
    def count(self) -> int:
        """返回当前节点行数量。"""
        return len(self._rows)

    def rows(self) -> list[NodeRow]:
        """返回节点行副本（防止外部直接改内部列表）。"""
        return list(self._rows)

    def collect(self) -> list:
        """按行序收集节点配置，空标题行忽略。"""
        return [node for node in (row.value() for row in self._rows) if node]

    # ------------------------------------------------------------------ 变更
    def add_row(self, page: int = 1, title: str = "", side: str = "left") -> NodeRow:
        """新增一行节点并刷新空态与高度；插入后发出 changed。

        行写入 QVBoxLayout 使容器高度随行数自适应；新行显式 show 并通知父级
        重算几何（已显示时布局会跳过隐藏项），空态提示在首行出现时隐藏。
        """
        row = NodeRow(page, title, side, self)
        row.removeRequested.connect(self.remove_row)
        row.title_edit.textChanged.connect(lambda _t: self.changed.emit())
        row.page_spin.valueChanged.connect(lambda _v: self.changed.emit())
        row.side_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
        self._rows.append(row)
        self._box.addWidget(row)
        # 新加入的控件默认处于隐藏状态，而布局会跳过隐藏项（此时 sizeHint 甚至为 0）。
        # 面板已经显示的情况下必须显式 show + 通知父级重算，否则行会被压扁。
        row.show()
        self._sync_empty_hint()
        self.updateGeometry()
        self.changed.emit()
        return row

    def remove_row(self, row: NodeRow) -> None:
        """移除指定行：解绑布局、删除对象并刷新空态与高度。

        行不在列表中则忽略；移除后重新显示空态提示（无行时）并通知父级重算
        几何，最后发出 changed 让面板同步配置。
        """
        if row not in self._rows:
            return
        self._rows.remove(row)
        self._box.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._sync_empty_hint()
        self.updateGeometry()
        self.changed.emit()

    def clear(self) -> None:
        """清空所有节点行。"""
        for row in self._rows:
            self._box.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        self._sync_empty_hint()
        self.updateGeometry()
        self.changed.emit()

    def _sync_empty_hint(self) -> None:
        self._empty_hint.setVisible(not self._rows)
