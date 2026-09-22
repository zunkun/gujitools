# -*- coding: utf-8 -*-
"""任务管理页：表格列表 + 导入PDF（先算指纹查重，确认后建任务并落副本/缩略图）。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal, Slot, QSize
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
from desktop.workers import (
    HashWorker,
    SerialJobQueue,
    SourceThumbnailsWorker,
    TaskRowsWorker,
    WorkerHost,
    connect_queued,
)
from desktop.store import TaskStore
from desktop.components.pagination import DEFAULT_PAGE_SIZE, Pager, Pagination
from desktop.components.task_table import TaskTable

# 状态文案统一取自 ui.theme，避免各处各自维护一份
STATUS_LABELS = T.STATUS_LABELS

#: 页头副标题的默认文案；导入期间会被「正在导入 · …」临时顶掉（见 _show_import_status）
HEADER_SUBTITLE = "导入 PDF 后按四个子任务依次处理"


class TaskListPage(QWidget, WorkerHost):
    """任务管理页：搜索 + 分页的任务列表，支持导入 PDF 与删除。

    数据流是单向的：``refresh()`` 从 store 读出**全量**行并缓存，
    ``_render()`` 负责「按关键词过滤 → 分页切片 → 填表」。搜索框只触发
    ``_render()``（不再读盘），所以打字时不会每次都去扫一遍任务目录。

    含表格/空状态二选一的内容区。导入刻意分两段：**主线程**只做「算指纹 →
    查重 → 确认 → 建任务 → 刷新列表」（毫秒级，用户立刻看到新行）；**后台**
    串行做「复制源文件 + 生成整本缩略图」，且等列表画完才开工，期间挂一条
    「正在导入」提示条。
    """

    open_detail = Signal(str)

    def __init__(self, store: TaskStore, parent=None):
        """初始化页面：构建 UI、绑定信号并刷新首次列表。

        parent 一般为 MainWindow；会创建 store 引用与导入按钮状态占位，
        随后调用 refresh 重建表格与空状态。
        """
        super().__init__(parent)
        self._init_worker_host()
        self.store = store
        self.hash_thread: QThread | None = None
        self.hash_worker: HashWorker | None = None
        self._import_button: PrimaryPushButton | None = None
        # ---- 导入后的后台活（复制源文件 + 整本缩略图）：串行队列 ----
        self._thumb_queue = SerialJobQueue(self)
        self._thumb_queue.job_started.connect(self._on_import_job_started)
        self._thumb_queue.progress.connect(self._on_import_progress)
        self._thumb_queue.job_finished.connect(self._on_import_job_finished)
        #: 导入进度（缩略图 done/total）；没有后台活在跑时是 None
        self._import_progress: tuple[int, int] | None = None
        # ---- 列表状态：全量行 / 关键词 / 页码 / 每页条数 ----
        self._all_rows: list[dict] = []
        self._filtered: list[dict] = []
        self._keyword = ""
        self._page = 1
        self._page_size = DEFAULT_PAGE_SIZE
        self._init_ui()
        # ⚠️ 这里**刻意不刷新**。首次列表渲染实测约 74 ms（每行要建名称标签 +
        # 操作按钮，还会读每个任务的 runs.json），它由 `desktop/app.py::main()`
        # 在窗口 `show()` **之后**的下一拍触发——先让空壳窗口出现在屏幕上，再
        # 填内容，用户感知的「启动到窗口出现」就少了这一段。
        # 空表与空状态的初始形态由 _init_ui 建好，refresh 只负责填数据。

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
        """刷新任务行：**读盘放后台线程**，读完回主线程渲染。

        ⚠️ 读盘不能占着 UI 线程：这里要遍历全部任务、逐个读它的 runs.json
        （任务一多就是几十次文件 IO），同步做会把已经画出来的窗口卡住。行的
        组装挪进了 ``TaskRowsWorker``，结果走 ``_on_rows_ready`` 回来渲染。

        ⚠️ 每次刷新带一个**代际令牌**：连续调用（导入任务后紧跟着又刷新）会让
        多个 worker 并发跑，先发的可能后回来，把新数据盖成旧的——只认最后
        一次发出的那个令牌，其余结果直接丢弃。
        """
        token = object()
        self._refresh_token = token
        self.run_worker(
            lambda: TaskRowsWorker(self.store),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.completed,
                    lambda rows, t=token: self._on_rows_ready(t, rows),
                    thread,
                ),
                connect_queued(
                    self,
                    worker.failed,
                    lambda message, t=token: self._on_rows_failed(t, message),
                    thread,
                ),
                worker.completed.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_rows_ready(self, token, rows: list) -> None:
        """后台读完 → 主线程：更新缓存，再走过滤/分页/填表（过期结果丢弃）。"""
        if token is not self.__dict__.get("_refresh_token"):
            return
        self._all_rows = rows
        self._render()
        # 列表行已经画出来了，这时候才放后台的复制/缩略图开工——否则它们
        # 会和上面这几个读盘动作抢 GIL，新行要等 0.5~2.5s 才出现
        self._thumb_queue.release()

    def _on_rows_failed(self, token, message: str) -> None:
        """读失败（任务目录被删/权限不足等）：保留原列表，别把界面清空。"""
        if token is not self.__dict__.get("_refresh_token"):
            return
        print(f"任务列表刷新失败：{message}")
        self._thumb_queue.release()  # 列表虽然没画成，后台活也不能一直扣着

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
        """建任务 → 立刻出列表行 → 源文件副本与缩略图交给后台队列。

        ⚠️ **主线程只做「写一个 tasks.json」这一件事**（实测 ~5ms）。复制源
        文件（一本书几十 MB）和渲染整本缩略图（2400 页要 69s）都进后台：
        它们由 ``_thumb_queue`` 串行跑，**并且等列表行画完再放行**。

        为什么顺序这么讲究（实测见 ``.workbuddy/perf/``）：
        - 列表回程要读 N 个任务的 runs.json，无争抢时 7.5ms；一旦和渲染线程
          撞上，每次文件操作都要排 GIL 队列，「导入 → 看见新行」从 0.2s
          变成 0.5~2.5s；
        - 多个渲染线程并行时主线程 ``create_task`` 中位从 5ms 涨到 929ms。
        所以：**先出行，再放后台干活**，且一次只跑一个。
        """
        task_id = self.store.create_task(
            path, source_hash, path.stem, duplicate_confirmed=duplicate_confirmed
        )
        self.refresh()
        # 逐页缩略图 + 源文件副本：后台生成，落到任务目录 thumbnails/ 与根目录，
        # 之后不再清理。渲染的是**副本**，源文件随后被移动/删除都不影响本任务。
        worker = SourceThumbnailsWorker(
            path,
            self.store.source_thumbnails_dir(task_id),
            copy_to=self.store.task_dir(task_id) / path.name,
        )
        self._thumb_queue.submit(
            worker,
            label=path.name,
            on_warning=lambda msg: self._toast("warning", "副本保存失败", msg),
            on_failed=lambda msg: self._toast("warning", "缩略图生成失败", msg),
        )

    # ------------------------------------------------------ 导入进度提示
    def _on_import_job_started(self, label: str) -> None:
        """后台活开工：把「正在导入」写进页头副标题。"""
        self._import_progress = None
        self._show_import_status(self._import_status_text(0))

    def _on_import_progress(self, done: int, total: int) -> None:
        """缩略图渲染进度：把「12/123」写进页头。"""
        self._import_progress = (done, total)
        self._show_import_status(self._import_status_text(done))

    def _on_import_job_finished(self, label: str) -> None:
        """一个后台活结束：还有排队的就继续显示，全干完才恢复页头。"""
        if self._thumb_queue.busy():
            self._show_import_status(self._import_status_text(0))
            return
        self._import_progress = None
        self._show_import_status("")
        self._toast("success", "导入完成", f"{label} 已可处理")

    #: 提示文案里文件名的最大展示长度（页头是一行，长名会顶到右侧按钮）
    _IMPORT_NAME_LIMIT = 12

    def _import_status_text(self, done: int) -> str:
        """拼「正在导入」文案：干到哪、哪一本、后面还排了几个。"""
        name = self._thumb_queue.current_label() or "文件"
        if len(name) > self._IMPORT_NAME_LIMIT:
            name = name[: self._IMPORT_NAME_LIMIT] + "…"
        waiting = self._thumb_queue.pending_count()
        total = self._import_progress[1] if self._import_progress else 0
        if done and total:
            body = f"正在导入 · 缩略图 {done}/{total}"
        elif total:
            body = f"正在导入 · 已复制，共 {total} 页"
        else:
            body = "正在导入 · 复制源文件"
        body += f" · {name}"
        if waiting:
            body += f" +{waiting} 排队"
        return body

    def _show_import_status(self, text: str) -> None:
        """把「正在导入」写进**页头副标题**；空串则恢复默认说明。

        为什么不用 InfoBar 常驻条：qfluentwidgets 的 InfoBarManager 在
        ``showEvent`` 里登记，控件被隐藏再显示时会重复登记，列表里留下悬垂
        条目——之后任何一条 toast 自动关闭都会在 ``_updateDropAni`` 里对
        已销毁对象取属性，控制台刷 ``Internal C++ object already deleted``。
        页头是固定高度的，改副标题不会顶动右侧按钮，长驻状态放这里最稳。
        """
        if text:
            ui.apply_to(self._header.subtitle_label, T.SIZE_CAPTION, color=T.ACCENT)
            self._header.set_subtitle(text)
        else:
            ui.apply_to(self._header.subtitle_label, T.SIZE_CAPTION, color=T.INK_FAINT)
            self._header.set_subtitle(HEADER_SUBTITLE)

    def shutdown_workers(self) -> None:
        """关程序前的收尾：先停导入后台队列（复制/缩略图），再走基类线程。"""
        self._thumb_queue.shutdown()
        super().shutdown_workers()

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
