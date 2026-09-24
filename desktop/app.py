# -*- coding: utf-8 -*-
"""gujitools 桌面端主窗口：任务列表页 + 任务详情页切换。"""

from __future__ import annotations
import os
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QWidget
from PySide6.QtGui import QIcon
from qfluentwidgets import setTheme, Theme
from desktop.pages import TaskListPage
from desktop.store import TaskStore
from desktop.ui import theme as T
from desktop.utils.icon import rounded_window_icon
from desktop.ui.style import apply_app_style
from desktop.utils.files import package_dir

#: 主窗口标题（单例守卫按它找已有实例的窗口，见 desktop/single_instance.py）
WINDOW_TITLE = "古籍重製"


class MainWindow(QMainWindow):
    """主窗口：在任务列表页与任务详情页之间切换。
    创建时设定窗口最小尺寸并套用全局底色；通过 QStackedWidget 持有两页，
    并连接列表页「打开详情」与详情页「返回」信号完成页面跳转。
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1440, 920)
        self.setMinimumSize(1080, 720)

        # ========== 加载窗口图标 desktop/static/icon.png ==========
        # 打包后 desktop/ 是 PYZ 内字节码，磁盘上无此路径，改从
        # _internal/desktop/static 取（spec datas 已收集）——用 package_dir()
        #
        # 源图保持直角原图即可：形状由像素决定，圆角在这里统一裁
        # （ICON_RADIUS_RATIO，与打包脚本 tools/make_icon.py 同一套规则）。
        icon_path = package_dir() / "static" / "icon.png"
        if icon_path.exists():
            icon = rounded_window_icon(icon_path)
            self.setWindowIcon(icon if icon else QIcon(str(icon_path)))
        # ==========================================================

        self.store = TaskStore()
        self.pages = QStackedWidget()
        self.pages.setObjectName("pageRoot")
        self.list_page = TaskListPage(self.store)
        self.pages.addWidget(self.list_page)
        # 详情页**惰性创建**（见 _ensure_detail_page）：它带着第四步打印参数
        # 面板等一大批控件，构造实测约 400ms。启动时用户还停在列表页，先不付
        # 这笔钱——首次点开任务再建。
        self._detail_page: "QWidget | None" = None
        self.setCentralWidget(self.pages)
        self.setStyleSheet(f"QMainWindow {{ background: {T.CANVAS}; }}")
        self.list_page.open_detail.connect(self._open_detail)

    def _ensure_detail_page(self):
        """首次需要时创建详情页，挂进堆栈并接上「返回」信号。

        惰性化的收益只在启动那一刻：构造详情页要 ~400ms，而它内部的
        打印参数面板（print_form / print_panel）在启动时完全用不到。
        """
        if self._detail_page is None:
            from desktop.pages import TaskDetailPage

            page = TaskDetailPage(self.store)
            page.back_requested.connect(self._back_to_list)
            self.pages.addWidget(page)
            self._detail_page = page
        return self._detail_page

    @property
    def detail_page(self):
        """详情页实例（惰性构造）。

        保留这个公开属性名：``tests/selftests/_context.py`` 与
        ``tests/gui_shot.py`` 都按 ``window.detail_page`` 取页面来操作控件。
        读它本身就等于声明「现在就需要详情页」，因此访问即构造——与启动期
        惰性并不冲突。
        """
        return self._ensure_detail_page()

    def _open_detail(self, task_id: str) -> None:
        page = self._ensure_detail_page()
        page.set_task(task_id)
        self.pages.setCurrentWidget(page)

    def _back_to_list(self) -> None:
        self.list_page.refresh()
        self.pages.setCurrentWidget(self.list_page)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """←/→ 转发给详情页翻页。

        ⚠️ 点击预览大图（QLabel 默认不收焦点）后，焦点落在**主窗口本身**，
        按键只会到这里——不转发的话，用户点完图片按左右毫无反应
        （用户 18:29 实测）。两条边界：
        - 只在**详情页可见**时转发（任务列表页没有翻页语义）；
        - 焦点在参数输入区等输入类控件时，方向键被它们自己消费（移光标/
          改值），根本到不了这里——「焦点在输入区不切换」天然成立，
          且详情页的 navigate_by_arrow 里还有同一道守卫兜底。
        """
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right) \
                and self._detail_page is not None \
                and self.pages.currentWidget() is self._detail_page:
            if self._detail_page.navigate_by_arrow(key == Qt.Key.Key_Right):
                event.accept()
                return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        """关闭窗口时先让详情页收尾 worker 子进程。
        详情页持有 worker 子进程与后台线程的引用，直接退出会让进程被强杀；
        这里把事件转交给详情页的 closeEvent 完成 kill/等待/清理后再接受关闭。
        详情页是惰性的——没建过就说明没有 worker 需要收尾。

        列表页也要收尾：导入后的「复制源文件 + 生成缩略图」在后台队列里，
        整本可能几千页（实测 2400 页要 69s），退出时让它尽快收手。
        """
        self.list_page.shutdown_workers()
        if self._detail_page is not None:
            self._detail_page.closeEvent(event)
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
    """创建 QApplication、套用样式并显示主窗口，返回退出码。

    设环境变量 ``GUJI_GUI_SELFTEST=1`` 时，主窗口构造并短暂跑过事件循环后
    自动退出（退出码 0）。仅供打包后冒烟使用——GUI 是 windowed 程序，没有
    控制台，导入期崩溃会弹错误框并一直挂住，靠"进程还活着"根本判断不了
    成败；有了这个开关就能用**退出码**判定。
    """
    app = QApplication(sys.argv)
    setTheme(Theme.LIGHT)
    apply_app_style(app)  # 统一字体、主题色、底色与滚动条
    from desktop.ui.font_setup import ensure_cjk_fonts

    ensure_cjk_fonts()  # 没有中文字体时先弹安装引导，再进主界面

    # ---- 单例守卫：同一个构建只允许一个 GUI 实例 ----
    # 已有本构建实例在跑 → 把那个窗口恢复并带到前台，本进程直接退出。
    # 身份是 **desktop 包目录**：开发版与正式版的目录不同，因此两个程序可以
    # 同时存在、互不阻拦（用户原则）。冒烟模式（GUJI_GUI_SELFTEST）不检查：
    # 打包冒烟可能在 GUI 开着时运行，不该让它被单例挡住而"空过"。
    if not os.environ.get("GUJI_GUI_SELFTEST"):
        from desktop.single_instance import acquire, activate_existing_window

        if not acquire(str(package_dir())):
            activate_existing_window(WINDOW_TITLE)
            return 0

    window = MainWindow()
    window.show()
    # 列表数据推迟到窗口显示之后的**下一拍**：TaskListPage 首次渲染要建每行的
    # 控件、还要读各任务的 runs.json（实测 ~74 ms），放在 show() 之前等于推迟
    # 窗口出现。先给用户一个空壳窗口，再填内容。
    from PySide6.QtCore import QTimer

    QTimer.singleShot(0, window.list_page.refresh)
    _install_sigint_handler(app)
    if os.environ.get("GUJI_GUI_SELFTEST"):
        from PySide6.QtCore import QTimer

        # 延迟一拍再退出：让事件循环真正转起来，能抓到构造期之外的错误
        QTimer.singleShot(500, app.quit)
    try:
        code = app.exec()
    finally:
        # desktop 关闭 → 释放常驻 YOLO 服务（模型 + torch 运行时约 350MB）。
        # ⚠️ 只在 GUI 路径做：worker 子进程不拥有服务，不该替 GUI 去关它。
        # 用户原则：desktop 关闭，YOLO 就释放；关掉之后下次检测重新拉起服务
        # （约 5 秒）。`shutdown_service` 内部吞掉所有异常，finally 里安全。
        from functions.yolo_service import shutdown_service

        shutdown_service()
    return code
