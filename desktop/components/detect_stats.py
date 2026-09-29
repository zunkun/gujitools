# -*- coding: utf-8 -*-
"""检测结果统计组件（第二步右侧）：按页形态分类统计，总览 / 明细两级。

数据由宿主（`DetectMixin._refresh_detect_stats`）计算后经 `set_results`
灌入：分类规则唯一实现在 `utils.box_geometry.classify_page_slots`（槽位
形态 → fullcontent / harfcontent / 单独页 / 无文本框），本组件只管展示。

交互：默认显示**总览**（四类的页数，点击某一类）；明细页列出该类每页的
页码，点页码发 `page_clicked(row)` 由宿主跳转预览，另有「返回总览」。
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QListView,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import CaptionLabel, PushButton, ToolButton
from qfluentwidgets import FluentIcon as FIF

from desktop.ui import theme as T
from desktop.ui.widgets import SectionTitle, apply_to
from utils.box_geometry import (
    PAGE_CLASS_EMPTY,
    PAGE_CLASS_FULLCONTENT,
    PAGE_CLASS_HARFCONTENT,
    PAGE_CLASS_SINGLE,
)

#: 分类键 → 展示文案（顺序即总览里的排列顺序；键见 PAGE_CLASS_* 常量）
CLASS_LABELS: tuple[tuple[str, str], ...] = (
    (PAGE_CLASS_FULLCONTENT, "整幅一栏"),
    (PAGE_CLASS_HARFCONTENT, "左右双栏"),
    (PAGE_CLASS_SINGLE, "左右单栏"),
    (PAGE_CLASS_EMPTY, "无文本框"),
)

#: 明细页码列表的最大高度（px）：再多的页码靠内部滚动，不挤压右侧面板
LIST_MAX_HEIGHT = 168


class DetectStatsWidget(QWidget):
    """「检测结果统计」：总览四级分类页数，点进某类查看页码明细。"""

    #: 用户点了明细里的某个页码（row = 预览缩略图条里的行号）
    page_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(T.SPACE_SM)

        header = QHBoxLayout()
        header.setSpacing(T.SPACE_XS)
        self.title = SectionTitle("检测结果统计")
        header.addWidget(self.title)
        header.addStretch(1)
        # 明细页才显示的「返回总览」
        self.back_button = ToolButton(FIF.RETURN)
        self.back_button.setToolTip("返回分类总览")
        self.back_button.setFixedSize(28, 28)
        self.back_button.clicked.connect(self.show_overview)
        self.back_button.hide()
        header.addWidget(self.back_button)
        root.addLayout(header)

        self.stack = QStackedWidget()
        root.addWidget(self.stack)
        self.stack.addWidget(self._build_overview())
        self.stack.addWidget(self._build_detail())
        self._classes: dict[str, list[tuple[int, str]]] = {}
        self._current_class: str | None = None

    # ------------------------------------------------------------------ 总览
    def _build_overview(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_XS)
        self.summary_caption = CaptionLabel("尚未检测")
        apply_to(self.summary_caption, T.SIZE_CAPTION, color=T.INK_FAINT)
        layout.addWidget(self.summary_caption)
        self.class_buttons: dict[str, PushButton] = {}
        for key, label in CLASS_LABELS:
            button = PushButton(label)
            button.setFixedHeight(30)
            button.setToolTip(f"查看「{label}」包含的页码明细")
            button.clicked.connect(lambda _=False, k=key: self.show_detail(k))
            layout.addWidget(button)
            self.class_buttons[key] = button
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------ 明细
    def _build_detail(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_XS)
        self.detail_caption = CaptionLabel("")
        apply_to(self.detail_caption, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.detail_caption.setWordWrap(True)
        layout.addWidget(self.detail_caption)
        # 页码用 IconMode + 自动换行的列表：页多时自带滚动，不撑破面板
        self.page_list = QListWidget()
        self.page_list.setViewMode(QListView.IconMode)
        self.page_list.setFlow(QListView.LeftToRight)
        self.page_list.setWrapping(True)
        self.page_list.setResizeMode(QListView.Adjust)
        self.page_list.setMovement(QListView.Static)
        self.page_list.setSelectionMode(QListView.NoSelection)
        self.page_list.setGridSize(QSize(46, 26))
        self.page_list.setUniformItemSizes(True)
        self.page_list.setMaximumHeight(LIST_MAX_HEIGHT)
        self.page_list.setFrameShape(QListWidget.NoFrame)
        self.page_list.setStyleSheet(
            "QListWidget::item {"
            f" background: {T.SURFACE_SOFT}; border-radius: {T.RADIUS_SM}px;"
            f" color: {T.INK_SOFT}; font-size: {T.SIZE_CAPTION}px; }}"
            "QListWidget::item:hover {"
            f" background: {T.SURFACE_HOVER}; color: {T.INK}; }}"
        )
        self.page_list.itemClicked.connect(self._on_page_clicked)
        layout.addWidget(self.page_list)
        return page

    # ------------------------------------------------------------------ 数据
    def set_results(
        self, total: int, classes: dict[str, list[tuple[int, str]]]
    ) -> None:
        """灌入统计结果：``total`` 总页数；``classes`` 分类键 → [(行号, 页码)]。"""
        self._classes = {key: list(values) for key, values in (classes or {}).items()}
        detected = sum(
            len(values)
            for key, values in self._classes.items()
            if key != PAGE_CLASS_EMPTY
        )
        self.summary_caption.setText(
            f"共 {total} 页，已检出 {detected} 页，点击分类查看页码明细"
            if total
            else "尚未提取页面，或尚未执行检测"
        )
        for key, label in CLASS_LABELS:
            count = len(self._classes.get(key, []))
            button = self.class_buttons[key]
            button.setText(f"{label} · {count} 页")
            # 页数为 0 的分类不显示（用户 2026-09-29：左右双栏/左右单栏为
            # 0 时不占位），总览里只留真正有内容的分类
            button.setVisible(count > 0)
        # 明细若是当前打开的分类，同步刷新它的页码列表；
        # 该分类刚好清零（页被删/框被清）则明细已无内容，退回总览
        if self._current_class is not None:
            if self._classes.get(self._current_class):
                self.show_detail(self._current_class)
            else:
                self.show_overview()

    # ------------------------------------------------------------------ 切换
    def show_overview(self) -> None:
        """回到总览（返回按钮与数据刷新后的兜底都走这里）。"""
        self._current_class = None
        self.back_button.hide()
        self.stack.setCurrentIndex(0)

    def show_detail(self, class_key: str) -> None:
        """打开某分类的页码明细。"""
        label = dict(CLASS_LABELS).get(class_key, class_key)
        rows = self._classes.get(class_key, [])
        self.detail_caption.setText(
            f"{label} · 共 {len(rows)} 页"
            + ("，点击页码跳转预览" if rows else "（暂无页面）")
        )
        self.page_list.clear()
        for row, page_label in rows:
            item = QListWidgetItem(page_label)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setData(Qt.ItemDataRole.UserRole, row)
            self.page_list.addItem(item)
        self._current_class = class_key
        self.back_button.show()
        self.stack.setCurrentIndex(1)

    def _on_page_clicked(self, item: QListWidgetItem) -> None:
        row = item.data(Qt.ItemDataRole.UserRole)
        if row is not None and row >= 0:
            self.page_clicked.emit(int(row))
