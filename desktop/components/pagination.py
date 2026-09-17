# -*- coding: utf-8 -*-
"""分页控件：纯计算 Pager + Qt 控件 Pagination。

拆成两层的理由和项目里其它地方一样：**几何/数值计算不要和渲染混在一起**。
``Pager`` 不 import Qt，能直接在自测里当普通对象断言（切片区间、页码钳制、
末页删空后的回退）；``Pagination`` 只负责把 Pager 的状态画出来、把点击翻译
成 ``set_page`` 调用。

页码一律 **1-based**——直接显示在界面上的东西就跟人看到的保持一致，
0-based 只在内部切片时用一次（``_offset``）。
"""

from __future__ import annotations

from dataclasses import dataclass
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
from qfluentwidgets import ComboBox, FluentIcon as FIF, ToolButton

from desktop.ui import theme as T
from desktop.ui.widgets import apply_to

# 每页条数候选。首项是默认值，也是任务列表的规格（用户要求 10 条/页）。
PAGE_SIZE_OPTIONS: tuple[int, ...] = (10, 20, 50, 100)
DEFAULT_PAGE_SIZE = PAGE_SIZE_OPTIONS[0]


# --------------------------------------------------------------------- 纯计算
@dataclass(frozen=True)
class Pager:
    """分页状态与派生量（不可变，改页码/每页条数就换一个新实例）。

    total      总条数（**过滤后**的条数，不是全量）
    page_size  每页条数
    page       当前页码，1-based；越界会在读取时被钳制
    """

    total: int = 0
    page_size: int = DEFAULT_PAGE_SIZE
    page: int = 1

    def __post_init__(self) -> None:
        # dataclass(frozen=True) 里要规范化字段只能走 object.__setattr__。
        # 每页条数 <=0 会让除模直接炸，兜底成默认；页码越界在 clamped_page 处理。
        if self.page_size <= 0:
            object.__setattr__(self, "page_size", DEFAULT_PAGE_SIZE)
        if self.total < 0:
            object.__setattr__(self, "total", 0)

    @property
    def total_pages(self) -> int:
        """总页数；0 条时也是 1 页（界面上显示「第 1 / 1 页」比「第 1 / 0 页」自然）。"""
        if self.total == 0:
            return 1
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def clamped_page(self) -> int:
        """钳制到 [1, total_pages] 的页码。

        ⚠️ 必须每次读都用这个值：删掉末页最后一条、或搜索后结果变少，
        当前页码就会越界，读原始 page 会切出空列表、界面变成空白页。
        """
        return min(max(self.page, 1), self.total_pages)

    @property
    def _offset(self) -> int:
        return (self.clamped_page - 1) * self.page_size

    def slice_bounds(self) -> tuple[int, int]:
        """当前页在整表里的 [start, end) 下标区间（左闭右开，直接喂 list 切片）。"""
        start = self._offset
        return start, min(start + self.page_size, self.total)

    def page_slice(self, items: list) -> list:
        """取当前页的切片；越界页码已钳制，不会返回空页。"""
        start, end = self.slice_bounds()
        return list(items[start:end])

    def first_index(self) -> int:
        """当前页第一条在整表中的序号（1-based，给表格「序号」列用）。"""
        return self._offset + 1

    def with_page(self, page: int) -> "Pager":
        return Pager(self.total, self.page_size, page)

    def with_page_size(self, page_size: int) -> "Pager":
        """换每页条数：页码按比例换算，尽量停在原来看到的那一条附近。

        不这么换算的话，从第 3 页（每页 10 条）切到每页 50 条会直接跳到第 3 页
        的第 101~150 条，用户感觉列表「乱跳」。换算后落在第 1 页第 21~50 条。
        """
        first = self._offset + 1  # 当前页第一条的全局序号
        new_page = (first + page_size - 1) // page_size if first > 0 else 1
        return Pager(self.total, page_size, max(new_page, 1))

    def with_total(self, total: int) -> "Pager":
        return Pager(total, self.page_size, self.page)


# ----------------------------------------------------------------------- 控件
class Pagination(QWidget):
    """分页条：总数 + 每页条数 + 上/下一页 + 页码。

    只做展示与事件转发，**不持有数据**：宿主页面把算好的 Pager 传进来，
    用户操作时由本控件算出新页码并通过 ``changed`` 抛回去，宿主再重算并
    ``set_pager`` 刷新。这样「过滤 → 分页 → 渲染」只有一条数据流向。
    """

    # 新页码（1-based，已钳制）
    changed = Signal(int)
    # 新的每页条数
    page_size_changed = Signal(int)

    def __init__(self, page_size: int = DEFAULT_PAGE_SIZE, parent=None):
        super().__init__(parent)
        self._pager = Pager(0, page_size, 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_SM)

        self.total_label = QLabel()
        apply_to(self.total_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        layout.addWidget(self.total_label)
        layout.addStretch()

        layout.addWidget(QLabel("每页"))
        self.size_combo = ComboBox()
        self.size_combo.setFixedWidth(84)
        for size in PAGE_SIZE_OPTIONS:
            self.size_combo.addItem(str(size), userData=size)
        index = self.size_combo.findData(page_size)
        self.size_combo.setCurrentIndex(index if index >= 0 else 0)
        self.size_combo.currentIndexChanged.connect(self._on_page_size_changed)
        layout.addWidget(self.size_combo)
        layout.addWidget(QLabel("条"))

        self.prev_btn = ToolButton(FIF.PAGE_LEFT)
        self.prev_btn.setFixedSize(32, 30)
        self.prev_btn.setToolTip("上一页")
        self.prev_btn.clicked.connect(lambda: self.changed.emit(self._pager.clamped_page - 1))
        layout.addWidget(self.prev_btn)

        self.page_label = QLabel()
        apply_to(self.page_label, T.SIZE_CAPTION, color=T.INK_SOFT)
        self.page_label.setMinimumWidth(72)
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.page_label)

        self.next_btn = ToolButton(FIF.PAGE_RIGHT)
        self.next_btn.setFixedSize(32, 30)
        self.next_btn.setToolTip("下一页")
        self.next_btn.clicked.connect(lambda: self.changed.emit(self._pager.clamped_page + 1))
        layout.addWidget(self.next_btn)

        self.set_pager(self._pager)

    # ------------------------------------------------------------------ 状态
    def pager(self) -> Pager:
        return self._pager

    def set_pager(self, pager: Pager) -> None:
        """用新的分页状态刷新显示（宿主算完过滤/切片后调它）。"""
        self._pager = pager
        page = pager.clamped_page
        pages = pager.total_pages
        self.total_label.setText(f"共 {pager.total} 条")
        self.page_label.setText(f"第 {page} / {pages} 页")
        self.prev_btn.setEnabled(page > 1)
        self.next_btn.setEnabled(page < pages)
        # 每页条数可能被外部改过（目前只有下拉会改），同步一下避免显示漂移
        index = self.size_combo.findData(pager.page_size)
        if index >= 0 and index != self.size_combo.currentIndex():
            self.size_combo.blockSignals(True)
            self.size_combo.setCurrentIndex(index)
            self.size_combo.blockSignals(False)
        # 只有一页时整条也没什么可操作的，但保留显示总数，不隐藏控件

    def set_visible_for(self, total: int) -> None:
        """总数为 0 时隐藏（配合空状态卡片，避免「共 0 条 第 1/1 页」的噪音）。"""
        self.setVisible(total > 0)

    # ------------------------------------------------------------------ 事件
    def _on_page_size_changed(self, _index: int) -> None:
        size = self.size_combo.currentData()
        if isinstance(size, int) and size > 0:
            self.page_size_changed.emit(size)
