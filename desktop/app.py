# -*- coding: utf-8 -*-
"""gujitools 桌面端主窗口：任务列表页 + 任务详情页切换。"""

from __future__ import annotations
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget
from PySide6.QtGui import QIcon
from qfluentwidgets import setTheme, Theme
from desktop.pages import TaskDetailPage, TaskListPage
from desktop.store import TaskStore
from desktop.ui import theme as T
from desktop.ui.style import apply_app_style


class MainWindow(QMainWindow):
    """主窗口：在任务列表页与任务详情页之间切换。
    创建时设定窗口最小尺寸并套用全局底色；通过 QStackedWidget 持有两页，
    并连接列表页「打开详情」与详情页「返回」信号完成页面跳转。
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("古籍重製")
        self.resize(1440, 920)
        self.setMinimumSize(1080, 720)

        # ========== 加载窗口图标 desktop/static/icon.png ==========
        base_dir = Path(__file__).resolve().parent  # desktop文件夹
        icon_path = base_dir / "static" / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        # ==========================================================

        self.store = TaskStore()
        self.pages = QStackedWidget()
        self.pages.setObjectName("pageRoot")
        self.list_page = TaskListPage(self.store)
        self.detail_page = TaskDetailPage(self.store)
        self.pages.addWidget(self.list_page)
        self.pages.addWidget(self.detail_page)
        self.setCentralWidget(self.pages)
        self.setStyleSheet(f"QMainWindow {{ background: {T.CANVAS}; }}")
        self.list_page.open_detail.connect(self._open_detail)
        self.detail_page.back_requested.connect(self._back_to_list)

    def _open_detail(self, task_id: str) -> None:
        self.detail_page.set_task(task_id)
        self.pages.setCurrentWidget(self.detail_page)

    def _back_to_list(self) -> None:
        self.list_page.refresh()
        self.pages.setCurrentWidget(self.list_page)

    def closeEvent(self, event) -> None:
        """关闭窗口时先让详情页收尾 worker 子进程。
        详情页持有 worker 子进程与后台线程的引用，直接退出会让进程被强杀；
        这里把事件转交给详情页的 closeEvent 完成 kill/等待/清理后再接受关闭。
        """
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
    """创建 QApplication、套用样式并显示主窗口，返回退出码。"""
    app = QApplication(sys.argv)
    setTheme(Theme.LIGHT)
    apply_app_style(app)  # 统一字体、主题色、底色与滚动条
    window = MainWindow()
    window.show()
    _install_sigint_handler(app)
    return app.exec()
