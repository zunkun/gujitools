# -*- coding: utf-8 -*-
"""与输入框同高的下拉框（自 ``desktop/ui/widgets.py`` 拆出）。

另有 :class:`GroupedComboBox`：下拉里带**分组标题**的版本（去底色算法用它按
分类摆放）。qfluent 的 ``ComboBox`` 是自绘的，分组标题不能只靠
``setItemEnabled(False)``——那样只是把字变灰，跟普通选项的差别只剩明度，用户
分不清（2026-11-24 用户报：「标题和选项只出了深浅颜色不同」）。所以这里给组标题
一个**独立的画法**：浅色底 + 加粗主色文字 + 上方分隔线。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPen
from qfluentwidgets import ComboBox
from qfluentwidgets.common.color import themeColor
from qfluentwidgets.common.style_sheet import isDarkTheme
from qfluentwidgets.components.widgets.combo_box import ComboBoxMenu
from qfluentwidgets.components.widgets.menu import IndicatorMenuItemDelegate

from .constants import CONTROL_HEIGHT


def _prepare(combo, width: int | None):
    """统一尺寸：与同列表单控件等高，且不把窄控制列撑开。"""
    combo.setFixedHeight(CONTROL_HEIGHT)
    # 它的 minimumSizeHint 偏大，而控制列最窄只有 340px：不放开会把表单
    # 撑出横向边界。表单字段列会自动拉伸，表格单元格内则按列宽收纳。
    combo.setMinimumWidth(0)
    if width is not None:
        combo.setFixedWidth(width)
    return combo


def combo_box(
    items: Iterable[str | Sequence[Any]] | None = None,
    width: int | None = None,
) -> ComboBox:
    """创建与输入框同高的下拉框（统一表单的行高节奏）。

    直接在表单里 ``ComboBox()`` 会比同列的 ``LineEdit``/``SafeSpinBox`` 矮
    6px（见 ``CONTROL_HEIGHT`` 的说明），所以下拉框一律用本函数建。

    ``items`` 传字符串序列时只填显示文案；传 ``(文案, 值)`` 二元组序列时
    值写进 ``itemData``，读出用 ``currentData()``。``width`` 非空则固定宽度
    （用于节点行这类需要横向对齐的窄列）。
    """

    combo = _prepare(ComboBox(), width)
    for item in items or ():
        if isinstance(item, str):
            combo.addItem(item)
        else:
            label, value = item
            combo.addItem(label, userData=value)
    return combo


def grouped_combo(width: int | None = None) -> "GroupedComboBox":
    """建一个空的分组下拉框（尺寸口径与 :func:`combo_box` 相同）。

    内容用 ``add_group`` / ``add_option`` 填，见 :class:`GroupedComboBox`。
    """
    return _prepare(GroupedComboBox(), width)


#: 标记「这一行是分组标题」的 action 属性名（delegate 据此换画法）。
_HEADER_PROPERTY = "comboGroupHeader"


class _GroupedMenuDelegate(IndicatorMenuItemDelegate):
    """下拉项绘制：分组标题画成浅底 + 加粗主色 + 上方分隔线，其余照旧。"""

    def paint(self, painter: QPainter, option, index) -> None:
        action = index.data(Qt.ItemDataRole.UserRole)
        if isinstance(action, QAction) and action.property(_HEADER_PROPERTY):
            self._paint_header(painter, option, index, action)
            return
        super().paint(painter, option, index)

    @staticmethod
    def _paint_header(painter: QPainter, option, index, action: QAction) -> None:
        """组标题：不再用"禁用项变灰"那套，改成能一眼认出的分类条。"""
        rect = option.rect
        accent = themeColor()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # 上方分隔线（第一组不画：下面是弹窗顶边，画了像双线）
        if index.row() > 0:
            line = QColor(255, 255, 255, 32) if isDarkTheme() else QColor(0, 0, 0, 28)
            pen = QPen(line, 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawLine(rect.x() + 10, rect.y() + 1, rect.right() - 10, rect.y() + 1)

        # 浅底：主色压到 ~7% 不透明度（深色主题略高），像一条分类带
        band = QRectF(rect.x() + 6, rect.y() + 3, rect.width() - 12, rect.height() - 6)
        tint = QColor(accent)
        tint.setAlpha(30 if isDarkTheme() else 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tint)
        painter.drawRoundedRect(band, 4, 4)

        # 文字：加粗 + 主色（对比度明显高于普通选项的纯黑/纯白）
        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(accent)
        painter.drawText(
            rect.adjusted(16, 0, -10, 0),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            action.text(),
        )
        painter.restore()


class _GroupedComboMenu(ComboBoxMenu):
    """带分组样式的下拉菜单：弹窗**之前**给标题行打标记，再换 delegate 画。

    ⚠️ 标记必须写在 ``exec()`` 之前：``ComboBox._showComboMenu`` 是「建菜单 →
    ``menu.exec()``（阻塞模态）→ 返回」，把标记写在 super() 之后等于菜单关掉才
    执行 —— 实际运行时样式永远不会生效（离屏截图也是靠手工建菜单才看得见）。
    """

    def _tag_headers(self) -> None:
        combo = self.parent()
        indexes = (
            combo.group_header_indexes()
            if isinstance(combo, GroupedComboBox)
            else ()
        )
        actions = self.actions()
        for index in indexes:
            if 0 <= index < len(actions):
                actions[index].setProperty(_HEADER_PROPERTY, True)

    def exec(self, *args, **kwargs):
        self._tag_headers()
        self.view.viewport().update()
        return super().exec(*args, **kwargs)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.view.setItemDelegate(_GroupedMenuDelegate(self.view))


class GroupedComboBox(ComboBox):
    """下拉里可以带**分组标题**的下拉框。

    用法与 ``ComboBox`` 一致，多两个方法：:meth:`add_group` 插一条不可选的组
    标题，:meth:`add_option` 插一个可选项（值写进 itemData）。

    ⚠️ 组标题仍然 ``setItemEnabled(False)``：qfluent 只会因此不响应点击/不参与
    键盘选择，而**外观由 delegate 接管**（不再显示成"灰掉的选项"）。取值路径上
    仍要当心「第 0 项是标题」——调用方回落时请用 :meth:`group_header_indexes`
    跳过它们。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._header_indexes: list[int] = []

    # ---------------------------------------------------------------- 构建
    def add_group(self, text: str) -> int:
        """插一条分组标题（不可选），返回它的下标。"""
        index = self.count()
        self.addItem(text)
        self.setItemEnabled(index, False)
        self._header_indexes.append(index)
        return index

    def add_option(self, label: str, value=None) -> int:
        """插一个可选项；``value`` 写进 itemData（读出用 ``currentData()``）。"""
        index = self.count()
        self.addItem(label, userData=value)
        return index

    def group_header_indexes(self) -> list[int]:
        """组标题的下标（升序副本）。"""
        return list(self._header_indexes)

    # ---------------------------------------------------------------- 绘制
    def _createComboMenu(self):
        return _GroupedComboMenu(self)
