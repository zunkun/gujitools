# -*- coding: utf-8 -*-
"""任务列表表格组件：每行带 详情/删除 操作按钮。"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QTableWidgetItem, QVBoxLayout, QWidget,
)
from qfluentwidgets import PrimaryPushButton, PushButton, TableWidget


class TaskTable(QWidget):
    open_detail = Signal(str)
    delete_request = Signal(str)

    COLUMNS = ["序号", "任务名称", "源文件", "创建时间", "子任务状态", "操作"]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table = TableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.resizeSection(0, 56)
        header.resizeSection(1, 180)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.resizeSection(3, 160)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.resizeSection(5, 170)
        self.table.setMinimumHeight(420)
        layout.addWidget(self.table)

    def set_data(self, rows: list[dict]) -> None:
        """rows: [{id, name, source_path, created_at, summary}]"""
        self.table.setRowCount(len(rows))
        for row, task in enumerate(rows):
            values = [
                str(row + 1),
                task["name"],
                task["source_path"],
                datetime.fromtimestamp(task["created_at"]).strftime("%Y-%m-%d %H:%M"),
                task["summary"],
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col in (0, 3):
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
            item = self.table.item(row, 1)
            item.setData(Qt.UserRole, task["id"])
            item.setToolTip(task["source_path"])
            self.table.setCellWidget(row, 5, self._action_widget(task["id"]))
        for row in range(len(rows)):
            self.table.setRowHeight(row, 46)

    def select_task(self, task_id: str) -> bool:
        """选中并滚动到指定任务所在行，返回是否找到。"""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item and item.data(Qt.UserRole) == task_id:
                self.table.selectRow(row)
                self.table.scrollToItem(item)
                return True
        return False

    def _action_widget(self, task_id: str) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        detail_btn = PrimaryPushButton("详情")
        detail_btn.setFixedHeight(28)
        detail_btn.clicked.connect(lambda: self.open_detail.emit(task_id))
        layout.addWidget(detail_btn)
        delete_btn = PushButton("删除")
        delete_btn.setFixedHeight(28)
        delete_btn.clicked.connect(lambda: self.delete_request.emit(task_id))
        layout.addWidget(delete_btn)
        return w
