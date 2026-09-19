# -*- coding: utf-8 -*-
"""任务管理页：表格列表 + 导入PDF（先算指纹查重，确认后建任务并落副本/缩略图）。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal, Slot, QSize
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    Dialog,
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
from desktop.ui.icons import HELP_CIRCLE
from desktop.workers import HashWorker, SourceThumbnailsWorker, connect_queued
from desktop.store import STAGES, STAGE_LABELS, STAGE_SHORT, TaskStore
from desktop.components.pagination import DEFAULT_PAGE_SIZE, Pager, Pagination
from desktop.components.task_table import TaskTable

# 状态文案统一取自 ui.theme，避免各处各自维护一份
STATUS_LABELS = T.STATUS_LABELS


class TaskListPage(QWidget):
    """任务管理页：搜索 + 分页的任务列表，支持导入 PDF 与删除。

    数据流是单向的：``refresh()`` 从 store 读出**全量**行并缓存，
    ``_render()`` 负责「按关键词过滤 → 分页切片 → 填表」。搜索框只触发
    ``_render()``（不再读盘），所以打字时不会每次都去扫一遍任务目录。

    含表格/空状态二选一的内容区；导入走「后台算指纹→查重→确认建任务」
    流程，缩略图另行后台生成，全程不阻塞界面。
    """

    open_detail = Signal(str)

    def __init__(self, store: TaskStore, parent=None):
        """初始化页面：构建 UI、绑定信号并刷新首次列表。

        parent 一般为 MainWindow；会创建 store 引用与导入按钮状态占位，
        随后调用 refresh 重建表格与空状态。
        """
        super().__init__(parent)
        self.store = store
        self.hash_thread: QThread | None = None
        self.hash_worker: HashWorker | None = None
        self._import_button: PrimaryPushButton | None = None
        # ---- 列表状态：全量行 / 关键词 / 页码 / 每页条数 ----
        self._all_rows: list[dict] = []
        self._filtered: list[dict] = []
        self._keyword = ""
        self._page = 1
        self._page_size = DEFAULT_PAGE_SIZE
        self._init_ui()
        self.refresh()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG)
        layout.setSpacing(T.SPACE_LG)

        # ---- 页头：标题 + 任务数 + 操作 ----
        header = ui.PageHeader("任务管理", "导入 PDF 后按四个子任务依次处理")
        # 内置的裸问号图标被裁到边框上，这里用自绘的「带圆圈的问号」
        manual_button = PushButton(HELP_CIRCLE, "用户手册")
        manual_button.setFixedHeight(34)
        manual_button.setIconSize(QSize(18, 18))
        manual_button.clicked.connect(self._open_manual)
        header.actions.addWidget(manual_button)
        import_button = PrimaryPushButton(FIF.DOWNLOAD, "导入 PDF")
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
            "点击右上角「导入 PDF」选择一本书，系统会自动建立任务目录并生成逐页缩略图",
            icon=FIF.DOCUMENT,
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

    # ------------------------------------------------------------------ 数据
    def refresh(self) -> None:
        """从 store 重新读出全量任务行并渲染（会读盘，不要在打字时调）。

        遍历各任务取四个阶段的 status/done/total 生成摘要行，结果缓存在
        ``_all_rows``；随后走 ``_render()`` 做过滤与分页。
        """
        tasks = self.store.list_tasks()
        rows = []
        for task in tasks:
            states = self.store.stage_states(task["id"])
            stages = []
            for stage in STAGES:
                state = states[stage]
                status = state["status"]
                progress = (
                    f" {state['done']}/{state['total']}" if state["total"] else ""
                )
                stages.append(
                    {
                        "short": STAGE_SHORT[stage],
                        "status": status,
                        "tip": f"{STAGE_LABELS[stage]}：{STATUS_LABELS.get(status, status)}{progress}",
                    }
                )
            rows.append(
                {
                    "id": task["id"],
                    "name": task["name"],
                    "source_path": task["source_path"],
                    "created_at": task["created_at"],
                    "stages": stages,
                }
            )
        self._all_rows = rows
        self._render()

    # ------------------------------------------------------- 过滤 / 分页渲染
    @staticmethod
    def _matches(row: dict, keyword: str) -> bool:
        """模糊匹配：任务名或源文件名（不含目录）包含关键词，大小写不敏感。

        只做**子串**匹配就够了——任务名是用户自己起或 PDF 文件名，长度短、
        没有拼写容错的需求；上 difflib 之类的模糊算法反而会让「搜 A 出来 B」
        变得不可预期。
        """
        if not keyword:
            return True
        haystack = " ".join(
            [
                str(row.get("name") or ""),
                # 只取文件名，避免用户磁盘上带关键词的父目录导致误命中
                Path(str(row.get("source_path") or "")).name,
            ]
        ).lower()
        return keyword.lower() in haystack

    def _render(self) -> None:
        """过滤 → 分页 → 填表，并同步空状态、分页条与提示文案。

        只依赖缓存的 ``_all_rows``，不读盘，所以搜索时可以逐字符调用。
        """
        keyword = self._keyword.strip()
        self._filtered = [r for r in self._all_rows if self._matches(r, keyword)]

        pager = Pager(len(self._filtered), self._page_size, self._page)
        # ⚠️ 页码可能越界（删了末页最后一条 / 搜索后结果变少），
        #    一律用钳制后的页码算切片，否则会渲染出空白页。
        self._page = pager.clamped_page
        page_rows = pager.page_slice(self._filtered)

        # 「序号」列由任务自己的编号填充（表格从 rows 里的 id 取），与分页无关
        self.table.set_data(page_rows)
        self.pagination.set_pager(pager)
        has_rows = bool(page_rows)
        self.content_stack.setCurrentIndex(0 if has_rows else 1)

        total = len(self._all_rows)
        if keyword and total != len(self._filtered):
            self.hint_label.setText(f"匹配 {len(self._filtered)} / {total} 个任务")
        elif keyword:
            self.hint_label.setText(f"匹配 {len(self._filtered)} 个任务")
        else:
            self.hint_label.setText("")

        self.tip_label.setText(
            f"共 {total} 个任务 · 数据目录 {self.store.root}"
            if total
            else f"数据目录 {self.store.root}"
        )

    def focus_task(self, task_id: str) -> bool:
        """翻到任务所在页并选中它；不在当前过滤结果里则返回 False。

        ⚠️ 分页后不能直接用 ``table.select_task``：任务可能不在当前页，
        表格里根本没有那一行。要先按**过滤后**的下标算出页码、切过去，
        再在表格里选中。
        """
        index = next(
            (i for i, r in enumerate(self._filtered) if r["id"] == task_id), None
        )
        if index is None:
            return False
        self._page = index // self._page_size + 1
        self._render()
        return self.table.select_task(task_id)

    # ------------------------------------------------------------ 搜索 / 分页
    def _on_keyword_changed(self, text: str) -> None:
        """搜索框变化：重置到第 1 页再渲染（否则会停在越界的旧页码上）。"""
        self._keyword = text or ""
        self._page = 1
        self._render()

    def _on_page_changed(self, page: int) -> None:
        self._page = page
        self._render()

    def _on_page_size_changed(self, page_size: int) -> None:
        """换每页条数时按当前页第一条换算页码，别让用户看着列表乱跳。"""
        pager = Pager(len(self._filtered), self._page_size, self._page)
        self._page = pager.with_page_size(page_size).page
        self._page_size = page_size
        self._render()

    # ------------------------------------------------------------------ 导入
    def import_pdf(self) -> None:
        """导入 PDF：选文件后后台算指纹并查重确认建任务。

        弹出文件框后若已有导入在跑则拒绝；否则起后台线程算内容指纹，
        完成后回调按查重结果弹「创建新任务/定位已有任务」，命中也可建副本。
        """
        filename, _ = QFileDialog.getOpenFileName(self, "导入 PDF", "", "PDF (*.pdf)")
        if not filename:
            return
        if self.hash_thread and self.hash_thread.isRunning():
            self._toast("warning", "正在导入", "上一个文件指纹尚未计算完成，请稍候。")
            return
        path = Path(filename)
        self._import_button.setEnabled(False)
        # 指纹后台计算，完成后决定是否建任务（查重 → 确认）
        self.hash_thread = QThread(self)
        self.hash_worker = HashWorker(path)
        self.hash_worker.moveToThread(self.hash_thread)
        self.hash_thread.started.connect(self.hash_worker.run)
        self.hash_worker.finished.connect(self._hash_ready)
        self.hash_worker.failed.connect(self._hash_failed)
        self.hash_worker.finished.connect(self.hash_thread.quit)
        self.hash_worker.failed.connect(self.hash_thread.quit)
        self.hash_thread.finished.connect(self.hash_worker.deleteLater)
        self.hash_thread.finished.connect(self._hash_thread_done)
        self.hash_thread.start()

    def _hash_thread_done(self) -> None:
        self._import_button.setEnabled(True)

    @Slot(str, str)
    def _hash_ready(self, path_text: str, source_hash: str) -> None:
        path = Path(path_text)
        duplicates = self.store.find_tasks(source_hash)
        if duplicates:
            if self._confirm_duplicate(path, duplicates):
                self._create_imported_task(path, source_hash, duplicate_confirmed=True)
            else:
                first = duplicates[0]
                # 走 focus_task 而不是 table.select_task：命中项可能在别的页上
                if self.focus_task(first["id"]):
                    self._toast(
                        "info",
                        "已定位到已有任务",
                        f"「{first['name']}」已在列表中选中",
                    )
                self.refresh()
            return
        self._create_imported_task(path, source_hash)

    def _confirm_duplicate(self, path: Path, duplicates: list) -> bool:
        """发现相同内容文件时弹窗确认；返回 True 表示仍创建新任务。"""
        names = "、".join(f"「{t['name']}」" for t in duplicates[:3])
        more = f" 等 {len(duplicates)} 个任务" if len(duplicates) > 3 else ""
        dialog = Dialog(
            "发现相同文件",
            f"任务列表中已存在内容相同的任务：{names}{more}。\n是否仍然创建一条新任务？",
            self,
        )
        dialog.yesButton.setText("创建新任务")
        dialog.cancelButton.setText("定位已有任务")
        return bool(dialog.exec())

    @Slot(str)
    def _hash_failed(self, message: str) -> None:
        self._toast("warning", "指纹计算失败", f"{message}（未创建任务）")

    def _create_imported_task(
        self, path: Path, source_hash: str, duplicate_confirmed: bool = False
    ) -> None:
        task_id = self.store.create_task(
            path, source_hash, path.stem, duplicate_confirmed=duplicate_confirmed
        )
        # 源文件副本留在任务目录下，任务自包含
        try:
            self.store.copy_source_to_task(task_id, path)
        except OSError as exc:
            self._toast("warning", "副本保存失败", str(exc))
        self.refresh()
        self._toast("success", "导入成功", f"{path.name} 已加入任务列表")
        # 逐页缩略图后台生成，落到任务目录 thumbnails/ 子文件夹，之后不再清理
        thumbnails_dir = self.store.source_thumbnails_dir(task_id)
        thread = QThread(self)
        # 缩略图也从**备份**渲染：源文件随后被移动/删除不影响已导入的任务
        worker = SourceThumbnailsWorker(
            self.store.ensure_source_copy(task_id) or path, thumbnails_dir
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # worker 在子线程 emit → 排队回主线程再弹 toast（connect_queued）
        connect_queued(
            self,
            worker.failed,
            lambda msg: self._toast("warning", "缩略图生成失败", msg),
            thread,
        )
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        # 持有 (thread, worker) 引用，防止线程启动前被垃圾回收
        self._thumbnail_jobs = [
            (t, w) for t, w in getattr(self, "_thumbnail_jobs", []) if t.isRunning()
        ]
        self._thumbnail_jobs.append((thread, worker))
        thread.start()

    # ------------------------------------------------------------------ 删除
    def delete_task(self, task_id: str) -> None:
        """删除指定任务及其全部中间产物（带确认弹窗）。

        任务不存在时直接返回；否则弹确认框，确认后删库并刷新列表与提示。
        """
        task = self.store.get_task(task_id)
        if not task:
            return
        dialog = Dialog(
            "删除任务", f"确定删除任务「{task['name']}」及其全部中间产物？", self
        )
        if not dialog.exec():
            return
        if not self.store.delete_task(task_id):
            # 目录被占用时 store 会保留任务记录，不留孤儿目录
            self._toast("error", "删除未完成", "文件正被占用，请稍后重试。")
            return
        self.refresh()
        self._toast("success", "删除成功", task["name"])

    # ------------------------------------------------------------------ 提示
    def _toast(self, kind: str, title: str, content: str) -> None:
        factory = getattr(InfoBar, kind, InfoBar.info)
        factory(
            title=title,
            content=content,
            parent=self,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=2500,
        )
