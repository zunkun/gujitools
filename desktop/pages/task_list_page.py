# -*- coding: utf-8 -*-
"""任务管理页：表格列表 + 导入PDF（先算指纹查重，确认后建任务并落副本/缩略图）。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    CardWidget,
    Dialog,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    SubtitleLabel,
    TitleLabel,
)
from qfluentwidgets import CaptionLabel

from ..workers import HashWorker, SourceThumbnailsWorker
from ..store import STAGES, STAGE_LABELS, TaskStore
from ..components.task_table import TaskTable

STATUS_LABELS = {
    "pending": "未执行",
    "running": "执行中",
    "success": "成功",
    "failed": "失败",
    "cancelled": "已中断",
    "draft": "未开始",
    "completed": "已完成",
}


class TaskListPage(QWidget):
    open_detail = Signal(str)

    def __init__(self, store: TaskStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.hash_thread: QThread | None = None
        self.hash_worker: HashWorker | None = None
        self._import_button: PrimaryPushButton | None = None
        self._init_ui()
        self.refresh()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header_card = CardWidget()
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(16, 12, 16, 12)
        title = TitleLabel("任务管理")
        header_layout.addWidget(title)
        header_layout.addStretch()
        import_button = PrimaryPushButton(FIF.DOCUMENT, "导入PDF")
        import_button.clicked.connect(self.import_pdf)
        header_layout.addWidget(import_button)
        self._import_button = import_button
        layout.addWidget(header_card)

        self.table = TaskTable()
        self.table.open_detail.connect(self.open_detail)
        self.table.delete_request.connect(self.delete_task)
        layout.addWidget(self.table, 1)

        self.tip_label = CaptionLabel()
        layout.addWidget(self.tip_label)

    # ------------------------------------------------------------------ 数据
    def refresh(self) -> None:
        rows = []
        for task in self.store.list_tasks():
            states = self.store.stage_states(task["id"])
            summary = "  ".join(
                f"{STAGE_LABELS[s].split('(')[0]}:{STATUS_LABELS.get(states[s]['status'], states[s]['status'])}"
                for s in STAGES
            )
            rows.append(
                {
                    "id": task["id"],
                    "name": task["name"],
                    "source_path": task["source_path"],
                    "created_at": task["created_at"],
                    "summary": summary,
                }
            )
        self.table.set_data(rows)
        self.tip_label.setText(
            f"共 {len(rows)} 个任务    数据目录：{self.store.root}"
        )

    # ------------------------------------------------------------------ 导入
    def import_pdf(self) -> None:
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
