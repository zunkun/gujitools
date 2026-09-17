# -*- coding: utf-8 -*-
"""任务管理页：表格列表 + 导入PDF（先算指纹查重，确认后建任务并落副本/缩略图）。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    Dialog,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    PushButton,
)

from desktop import ui
from desktop.ui import theme as T
from desktop.ui.help_dialog import ManualDialog
from desktop.workers import HashWorker, SourceThumbnailsWorker
from desktop.store import STAGES, STAGE_LABELS, STAGE_SHORT, TaskStore
from desktop.components.task_table import TaskTable

# 状态文案统一取自 ui.theme，避免各处各自维护一份
STATUS_LABELS = T.STATUS_LABELS


class TaskListPage(QWidget):
    """任务管理页：列表展示任务并支持导入 PDF 与删除。

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
        self._manual_dialog: ManualDialog | None = None
        self._init_ui()
        self.refresh()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG)
        layout.setSpacing(T.SPACE_LG)

        # ---- 页头：标题 + 任务数 + 操作 ----
        header = ui.PageHeader("任务管理", "导入 PDF 后按四个子任务依次处理")
        manual_button = PushButton(FIF.QUESTION, "用户手册")
        manual_button.setFixedHeight(34)
        manual_button.clicked.connect(self._open_manual)
        header.actions.addWidget(manual_button)
        import_button = PrimaryPushButton(FIF.DOWNLOAD, "导入 PDF")
        import_button.setFixedHeight(34)
        import_button.clicked.connect(self.import_pdf)
        header.actions.addWidget(import_button)
        self._import_button = import_button
        layout.addWidget(header)

        # ---- 内容区：表格 / 空状态 二选一 ----
        self.content_stack = QStackedWidget()
        table_card = ui.Card(padding=T.SPACE_SM, spacing=0)
        self.table = TaskTable()
        self.table.open_detail.connect(self.open_detail)
        self.table.delete_request.connect(self.delete_task)
        table_card.box.addWidget(self.table)
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
        """打开用户手册（非模态，方便边看边操作）。

        复用同一个实例：重复点按钮只是把它提到前台，不会叠出多个窗口。
        """
        if self._manual_dialog is None:
            self._manual_dialog = ManualDialog(self)
        self._manual_dialog.show()
        self._manual_dialog.raise_()
        self._manual_dialog.activateWindow()

    # ------------------------------------------------------------------ 数据
    def refresh(self) -> None:
        """重建任务表格与状态摘要，并切换空状态。

        遍历各任务取四个阶段的 status/done/total 生成摘要行，列表为空时
        切到空状态卡片，并更新底部数据目录提示文案。
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
        self.table.set_data(rows)
        self.content_stack.setCurrentIndex(0 if rows else 1)
        self.tip_label.setText(
            f"共 {len(rows)} 个任务 · 数据目录 {self.store.root}" if rows
            else f"数据目录 {self.store.root}"
        )

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
                if self.table.select_task(first["id"]):
                    self._toast(
                        "info", "已定位到已有任务",
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

    def _create_imported_task(self, path: Path, source_hash: str, duplicate_confirmed: bool = False) -> None:
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
        worker = SourceThumbnailsWorker(path, thumbnails_dir)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.failed.connect(
            lambda msg: self._toast("warning", "缩略图生成失败", msg)
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
        self.store.delete_task(task_id)
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
