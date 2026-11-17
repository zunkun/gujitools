# -*- coding: utf-8 -*-
"""「独立功能」入口页（用户 2026-11-17）：左侧导航只剩这一个条目，点进来
看到的是**各个独立任务的方块入口**，点方块进入对应功能页。

为什么是这一页
--------------
此前左侧导航为每个模块各摆一个条目（图片提取 / 检测文本框 / 去底色 / 拼图 /
PDF排版），导航栏被五个功能占满。用户 2026-11-17：「左侧目录菜单单任务列表
不再需要，改成一个菜单『独立功能』，页面是各个单独任务的入口，页面 UI 是
各个方块排列，每个方块都是一个单任务入口。」

结构契约：

- **清单只有一份**：本页**不维护**模块清单——壳层把
  :data:`desktop.modules.MODULES`（由 ``steps/spec.py`` 的 ``nav=True`` 派生）
  传进来，方块按传入顺序摆。加一个模块 = 加一条 spec，本页零改动。
- **只做入口不做业务**：方块只发 :attr:`module_requested`，切页/惰性构造/
  路由全在壳层（``desktop/shell.py``）——本页因此可以住在 pages 里而不破坏
  「模块页不 import pages」的边界（pages → modules 只经壳层转手的元数据，
  本文件**不 import** ``desktop.modules``）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QScrollArea, QVBoxLayout, QWidget,
)
from qfluentwidgets import FlowLayout

from desktop.ui import theme as T
from desktop.ui.icons import resolve_nav_icon
from desktop.ui.widgets import Card, PageHeader, apply_to, icon_pixmap

if TYPE_CHECKING:
    from desktop.modules import Module

#: 单个方块入口的尺寸（px）。三列布局下的舒适宽度：标题一行放得下
#: 「图片提取 / 检测文本框 / PDF排版」，副标题还有两行折行的余地。
TILE_WIDTH = 240
TILE_HEIGHT = 120


class ModuleHubPage(QWidget):
    """「独立功能」入口页：方块网格，每个方块 = 一个独立任务的入口。

    对外壳层的契约只有一个信号：:attr:`module_requested`（模块 key）。
    模块元数据由壳层注入（``modules`` 参数），本页不认得 ``MODULES`` 的来源。
    """

    #: 用户点了一个方块：参数是模块 key（壳层拿去 ``show_module(key)``）
    module_requested = Signal(str)

    def __init__(self, modules: Sequence["Module"], parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG)
        root.setSpacing(T.SPACE_LG)

        root.addWidget(PageHeader("独立功能", "与任务流程无关的独立处理功能，点方块进入"))

        # ---- 方块区：可滚动 + FlowLayout（窗口变窄时自动换行）----
        # ⚠️ FlowLayout 装在**一个内容控件**里、外面套 ScrollArea：滚动区按
        #    内容控件的 sizeHint 出滚动条，方块换行时内容控件高度会跟着长。
        from PySide6.QtCore import QSize

        self._tiles: list[_ModuleTile] = []
        content = QWidget()
        flow = FlowLayout(content, needAni=True)
        flow.setContentsMargins(T.SPACE_LG, T.SPACE_LG, T.SPACE_LG, T.SPACE_LG)
        flow.setHorizontalSpacing(T.SPACE_LG)
        flow.setVerticalSpacing(T.SPACE_LG)
        for module in modules:
            tile = _ModuleTile(module)
            tile.module_requested.connect(self.module_requested)
            flow.addWidget(tile)
            self._tiles.append(tile)
        content.setMinimumSize(QSize(TILE_WIDTH * 2 + T.SPACE_LG * 4, 0))

        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(scroll, 1)

    #: 方块清单（自测/壳层要按 key 找方块时用）
    def tiles(self) -> list["_ModuleTile"]:
        return list(self._tiles)

    def tile_for(self, key: str) -> "_ModuleTile | None":
        """按模块 key 取方块；没有返回 ``None``。"""
        for tile in self._tiles:
            if tile.key == key:
                return tile
        return None


class _ModuleTile(Card):
    """一个独立任务的方块入口：图标 + 标题 + 副标题，整块可点。

    ⚠️ 整块可点走 ``mousePressEvent``（方块是"卡片式入口"，不是按钮；
    不引入 QPushButton，保持与预览区守卫一致的用件习惯）。点击即发
    :attr:`module_requested`，本方块不直接知道壳层的存在。
    """

    module_requested = Signal(str)

    def __init__(self, module: "Module", parent=None):
        super().__init__(
            padding=T.SPACE_MD, spacing=T.SPACE_XS, radius=T.RADIUS_MD,
            parent=parent,
        )
        self.key = module.key
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(module.subtitle)
        self.setMinimumSize(TILE_WIDTH, TILE_HEIGHT)
        self.setMaximumSize(TILE_WIDTH, TILE_HEIGHT)

        # ---- 第一行：图标 + 标题 ----
        row = self.box  # Card 自带 QVBoxLayout（见 widgets.Card）
        from PySide6.QtWidgets import QHBoxLayout, QLabel

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(T.SPACE_SM)
        icon_label = QLabel()
        icon_label.setPixmap(icon_pixmap(
            resolve_nav_icon(module.icon), 28, T.ACCENT,
        ))
        icon_label.setFixedSize(28, 28)
        head.addWidget(icon_label)

        title = QLabel(module.title)
        apply_to(title, T.SIZE_SUBTITLE, bold=True, color=T.INK)
        head.addWidget(title, 1)
        row.addLayout(head)
        #: 标题标签（自测按它断言"方块文案来自注册表"）
        self.title_label = title

        # ---- 第二行：副标题（两行封顶折行，超长裁尾）----
        subtitle = QLabel(module.subtitle)
        subtitle.setWordWrap(True)
        apply_to(subtitle, T.SIZE_CAPTION, color=T.INK_FAINT)
        row.addWidget(subtitle, 1)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """整块可点：左键按下即发信号（与预览区点击区同口径，按下即生效）。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.module_requested.emit(self.key)
            event.accept()
            return
        super().mousePressEvent(event)


__all__ = ["ModuleHubPage", "TILE_HEIGHT", "TILE_WIDTH"]
