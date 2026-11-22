# -*- coding: utf-8 -*-
"""面板标题与页头（自 ``desktop/ui/widgets.py`` 拆出）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from desktop.ui import theme as T
from desktop.ui.fonts import ui_font

from ._qt import (
    QColor,
    QHBoxLayout,
    QLabel,
    QPainter,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    Qt,
)
from .help import HelpButton
from .text import apply_to

class PanelTitle(QWidget):
    """控制面板的**大标题行**：加粗标题 + 圆圈问号说明按钮（步骤面板统一款）。

    所有步骤面板的「大标题」统一走这一个组件（用户 2026-11-16：以
    「检测文本框」面板为基准——加粗大字 + 标题末尾挂问号；「图片拼版」
    用 ``SectionTitle`` 当大标题属于风格跑偏）。说明文字（description）
    不平铺占高度，全部收进问号按钮：hover 弹 ToolTip、点击弹 Flyout；
    没有说明就不放问号。

    ``title_label`` / ``help_button``（无说明时为 ``None``）挂在实例上，
    供宿主与自测按旧属性名访问。
    """

    def __init__(self, title: str, description: str = "", parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(T.SPACE_XS)
        self.title_label = QLabel(title, self)
        apply_to(self.title_label, T.SIZE_SUBTITLE, bold=True, color=T.INK)
        self.title_label.setWordWrap(True)
        row.addWidget(self.title_label)
        self.help_button: HelpButton | None = None
        if description:
            self.help_button = HelpButton(title, description, self)
            # 问号按钮要紧贴标题文字末尾，多余空间留在行尾
            row.addWidget(self.help_button, 0, Qt.AlignmentFlag.AlignTop)
        row.addStretch(1)



class PageHeader(QWidget):
    """页面头部：左侧标题 + 副标题，右侧操作区。

    带一条底部分隔线，把页头和内容区分开——原来只有一行孤立的标题，
    和下面的内容混在一起，层次不清。
    """

    if TYPE_CHECKING:
        # ⚠️ ``actions`` 这个名字**遮住了基类 QWidget.actions() 方法**（Qt 的
        # 动作列表 API）。运行上没问题（__init__ 里赋的是布局），但类型检查器
        # 会按基类方法解析、于是判成「布局没有 addWidget」。这里补一条类型侧
        # 声明把它钉回布局——只影响类型检查，运行时零副作用。
        # ⚠️ 对外名字不能改：页头操作区的用法 ``header.actions.addWidget(...)``
        # 被 tests/selftests/ui/manual_dialog.py 按源码文本钉住。
        actions: QHBoxLayout

    def __init__(self, title: str, subtitle: str = "", parent=None):
        """固定高 64px；右侧操作区通过 ``self.actions`` 布局添加按钮。"""
        super().__init__(parent)
        self.setFixedHeight(64)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(T.SPACE_XS, 0, T.SPACE_XS, 0)
        layout.setSpacing(T.SPACE_MD)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(2)
        self.title_label = QLabel(title, self)
        apply_to(self.title_label, T.SIZE_TITLE, bold=True, color=T.INK)
        text_column.addWidget(self.title_label)
        self.subtitle_label = QLabel(subtitle, self)
        apply_to(self.subtitle_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.subtitle_label.setVisible(bool(subtitle))
        text_column.addWidget(self.subtitle_label)
        layout.addLayout(text_column)
        layout.addStretch()

        self.actions = QHBoxLayout()
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(T.SPACE_SM)
        layout.addLayout(self.actions)

    def set_subtitle(self, text: str) -> None:
        """设置副标题文案，空串则隐藏副标题行。"""
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(0, self.height() - 1, self.width(), 1, QColor(T.BORDER))
