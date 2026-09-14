# -*- coding: utf-8 -*-
"""gujitools 桌面端主窗口：任务列表页 + 任务详情页切换。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget
from qfluentwidgets import setTheme, Theme

from .pages.task_detail_page import TaskDetailPage
from .pages.task_list_page import TaskListPage
from .store import TaskStore


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("guji 古籍处理平台")
        self.resize(1400, 900)
        self.store = TaskStore()

        self.pages = QStackedWidget()
        self.list_page = TaskListPage(self.store)
        self.detail_page = TaskDetailPage(self.store)
        self.pages.addWidget(self.list_page)
        self.pages.addWidget(self.detail_page)
        self.setCentralWidget(self.pages)

        self.list_page.open_detail.connect(self._open_detail)
        self.detail_page.back_requested.connect(self._back_to_list)

    def _open_detail(self, task_id: str) -> None:
        self.detail_page.set_task(task_id)
        self.pages.setCurrentWidget(self.detail_page)

    def _back_to_list(self) -> None:
        self.list_page.refresh()
        self.pages.setCurrentWidget(self.list_page)

    def closeEvent(self, event) -> None:
        self.detail_page.closeEvent(event)
        event.accept()  # 文件存储无需关闭


def _install_sigint_handler(app: QApplication) -> None:
    """让 Ctrl+C 能退出 GUI。

    Qt 事件循环阻塞在 C 层，Python 的 SIGINT 处理器只有在上层循环被
    周期性唤醒时才有机会执行，因此配一个空转 QTimer。
    """
    import signal

    from PySide6.QtCore import QTimer

    def _handle_sigint(signum, frame) -> None:
        app.quit()

    try:
        signal.signal(signal.SIGINT, _handle_sigint)
    except (ValueError, OSError):
        return
    keepalive = QTimer()
    keepalive.timeout.connect(lambda: None)
    keepalive.start(200)
    app._sigint_keepalive = keepalive  # 持有引用，防止被 GC


def main() -> int:
    app = QApplication(sys.argv)
    setTheme(Theme.LIGHT)
    window = MainWindow()
    window.show()
    _install_sigint_handler(app)
    return app.exec()
