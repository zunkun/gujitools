# -*- coding: utf-8 -*-
"""任务列表页的视图组装：页头 / 搜索条 / 表格与空状态 / 底栏 / toast。"""

from __future__ import annotations

from PySide6.QtCore import QSize, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
)
from qfluentwidgets import (
    CaptionLabel,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
)

from desktop import ui
from desktop.ui import theme as T
from desktop.ui.help_dialog import open_manual
from desktop.ui.icons import HELP_CIRCLE, PDF_FILE
from desktop.components.pagination import Pagination
from desktop.components.task_table import TaskTable
from desktop.pages.tasklist.page.constants import HEADER_SUBTITLE


class TaskListViewMixin:
    """页头、搜索条、内容区、底栏与 toast 的构建。"""

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG)
        layout.setSpacing(T.SPACE_LG)

        # ---- 页头：标题 + 任务数 + 操作 ----
        header = ui.PageHeader("任务管理", HEADER_SUBTITLE)
        self._header = header
        # 内置的裸问号图标被裁到边框上，这里用自绘的「带圆圈的问号」
        manual_button = PushButton(HELP_CIRCLE, "用户手册")
        manual_button.setFixedHeight(34)
        manual_button.setIconSize(QSize(18, 18))
        manual_button.clicked.connect(self._open_manual)
        header.actions.addWidget(manual_button)
        import_button = PrimaryPushButton(PDF_FILE, "创建任务")
        import_button.setFixedHeight(34)
        import_button.clicked.connect(self.import_pdf)
        header.actions.addWidget(import_button)
        self._import_button = import_button
        layout.addWidget(header)

        # ---- 搜索条：关键词过滤（只影响展示，不改数据）----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(T.SPACE_SM)
        self.search_edit = SearchLineEdit()
        self.search_edit.setPlaceholderText("搜索任务名或源文件名")
        self.search_edit.setFixedWidth(280)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_keyword_changed)
        toolbar.addWidget(self.search_edit)
        self.hint_label = QLabel()
        ui.apply_to(self.hint_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        toolbar.addWidget(self.hint_label)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ---- 内容区：表格 / 空状态 二选一 ----
        self.content_stack = QStackedWidget()
        table_card = ui.Card(padding=T.SPACE_SM, spacing=0)
        self.table = TaskTable()
        self.table.open_detail.connect(self.open_detail)
        self.table.delete_request.connect(self.delete_task)
        table_card.box.addWidget(self.table)
        # 分页条跟着表格一起在卡片里，空状态时随整块一起隐藏
        self.pagination = Pagination(self._page_size)
        self.pagination.changed.connect(self._on_page_changed)
        self.pagination.page_size_changed.connect(self._on_page_size_changed)
        pager_row = QHBoxLayout()
        pager_row.setContentsMargins(T.SPACE_MD, 0, T.SPACE_MD, T.SPACE_SM)
        pager_row.addWidget(self.pagination)
        table_card.box.addLayout(pager_row)
        self.content_stack.addWidget(table_card)

        empty_card = ui.Card(padding=0, spacing=0)
        self.empty_state = ui.EmptyState(
            "还没有任务",
            "点击右上角「创建任务」选择一本书与任务流程，系统会自动建立任务目录并生成逐页缩略图",
            # ⚠️ 空状态文案讲的就是"创建任务"，配``FIF.DOCUMENT``（空文档）
            #    会被读成"文档"——用带 PDF 字样的自绘图，语义才闭环。
            icon=PDF_FILE,
        )
        empty_card.box.addWidget(self.empty_state)
        self.content_stack.addWidget(empty_card)
        layout.addWidget(self.content_stack, 1)

        # ---- 底部：数据目录 + 打开按钮 ----
        footer = QHBoxLayout()
        footer.setSpacing(T.SPACE_SM)
        self.tip_label = CaptionLabel()
        ui.apply_to(self.tip_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        footer.addWidget(self.tip_label)
        footer.addStretch()
        open_dir_btn = PushButton(FIF.FOLDER, "打开数据目录")
        open_dir_btn.setFixedHeight(30)
        open_dir_btn.clicked.connect(self._open_data_dir)
        footer.addWidget(open_dir_btn)
        layout.addLayout(footer)

    def _open_data_dir(self) -> None:
        self.store.root.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root)))

    def _open_manual(self) -> None:
        """在系统默认浏览器里打开用户手册。

        手册是运行时由 Markdown 渲染出来的完整 HTML（见
        ``desktop.ui.help_dialog``）：交给真实浏览器渲染，表格/代码块/截图
        的排版才能到位，Qt 富文本引擎渲染长文档的效果太勉强。

        HTML 落在临时目录的固定文件名上，浏览器会复用同一个标签页，
        重复点按钮不会叠出一堆窗口。
        """
        open_manual()

    def _toast(self, kind: str, title: str, content: str) -> None:
        factory = getattr(InfoBar, kind, InfoBar.info)
        factory(
            title=title,
            content=content,
            # ⚠️ 挂**主窗口**，不挂本页（2026-11-17 用户报障）：建空壳任务的
            #    链路里 `open_detail.emit` 在 toast **之前**——壳层已同步切到
            #    详情页，本页此刻是隐藏的。InfoBar 挂在隐藏控件上要等父级
            #    重新显示（用户点回任务管理）才弹出来，用户看到的就是"回到
            #    列表页才弹出"的迟到提示。主窗口恒可见，任何页面下都立刻弹。
            parent=self.window(),
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=2500,
        )
