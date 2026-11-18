# -*- coding: utf-8 -*-
"""「任务详情」预览窗：**非模态**、直接复用详情页（用户 2026-11-17）。

## 为什么要有它

聚合任务创建页的成员表格里点「详情」，原来会**跳走**到该子任务的详情页
（壳层切路由）——创建到一半的表单就看不见了，回来还得重进创建页。

用户原话：

    「详情按钮点击，不再跳转，而是弹窗显示任务详情信息，这个弹窗要宽一些，
     直接复用任务详情页，详情弹窗不阻塞页面操作其他内容，不会发出当当当声音」

所以这里就是一个**普通窗口** + 一个 ``TaskDetailPage`` 实例：

- **绝不 ``exec()`` / ``setModal(True)``**：模态窗会挡住创建页，且"点到被模态
  阻塞的父窗口"时 Windows 会「当当当」响（项目里踩过，见 ``confirm_dialog``
  那条纪律）。这里 ``setModal(False)`` + ``show()``，创建页照常能点。
- **宽**：按屏幕可用区的 92% 开窗（上限 1600×1000），详情页本来就是宽布局
  （左控制列 + 右预览），窄了四处挤。
- **复用而不是重画**：里面就是真的 :class:`TaskDetailPage`，步骤条/预览/
  历史/执行按钮全在；只是把「查看 / 编辑流程」收起来（那要靠壳层切二级页，
  预览窗没有壳层），把页头「←」的含义改成"关闭预览"。
- 关窗时按"返回"的同一套口径释放（停检测、落暂存、关共享 PDF 缓存）——直接
  销毁可能撞上正在跑的 worker，所以只在**没有步骤在跑**时走这条清理。
"""

from __future__ import annotations

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout

from desktop.pages.taskdetail.page import TaskDetailPage

#: 开窗占屏幕可用区的比例（用户 2026-11-17：「这个弹窗要宽一些」）
SCREEN_RATIO = 0.92
#: 下限/上限（px）：太小挤、太大（超宽屏）反而看不清
MIN_SIZE = (1000, 700)
MAX_SIZE = (1600, 1000)


class TaskPreviewDialog(QDialog):
    """非模态的任务详情预览窗（一个任务一个窗口）。"""

    def __init__(self, store, task_id: str, parent=None):
        super().__init__(parent)
        # ⚠️ **独立窗口 + 非模态**：既能和创建页并排看，也绝不会因为是"子对话框
        #    而挡住父窗口"引出系统提示音。
        self.setWindowFlag(Qt.WindowType.Window, True)
        # 标题栏给「最小化 / 最大化」按钮（用户 2026-11-18：「任务详情弹窗可以
        # 放大缩小」）：详情页信息密度高，宽窗也不够看时用户要能占满屏幕。
        # ⚠️ QDialog 默认 flags 里**没有**这两个 hint，不补就只有那个 ×；
        #    尺寸本身可自由拉伸（没设 maximumSize），补上 hint 就够了。
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint
        )
        # 预览窗是主窗口的"子窗口"（owned）：默认没有任务栏按钮（用户
        # 2026-11-18：要在任务栏看到多个窗口）。补 WS_EX_APPWINDOW。
        # ⚠️ 必须在 setWindowFlags 之后（那会重建原生窗口、丢样式位）。
        from desktop.ui.native_minimize import enable_taskbar_button

        enable_taskbar_button(self)
        self.setModal(False)
        self.setWindowTitle(f"任务详情 · {task_id}")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.task_id = task_id
        self._closing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.page = TaskDetailPage(store)
        # 预览窗里没有"任务列表"可回：← 就是关掉这个窗
        self.page.back_button.setToolTip("关闭预览")
        self.page.back_requested.connect(self.close)
        layout.addWidget(self.page)

        self._fit_to_screen()
        self.page.set_task(task_id)
        # ⚠️ set_task 之后才收：进任务会刷新页头按钮的显隐（聚合任务的「重新
        #    汇集」等），先收会被它再点亮。
        self.page.flow_button.setVisible(False)

    # ------------------------------------------------------------------ 几何
    def _fit_to_screen(self) -> None:
        """按屏幕可用区开一个**宽**窗，并居中（多屏时跟创建页同一块屏）。"""
        screen = None
        if self.parentWidget() is not None:
            screen = self.parentWidget().screen()
        screen = screen or QApplication.primaryScreen()
        if screen is None:                       # 极端情况（无屏幕信息）
            self.resize(*MIN_SIZE)
            return
        avail = screen.availableGeometry()
        width = int(min(MAX_SIZE[0], max(MIN_SIZE[0], avail.width() * SCREEN_RATIO)))
        height = int(min(MAX_SIZE[1], max(MIN_SIZE[1], avail.height() * SCREEN_RATIO)))
        self.resize(width, height)
        self.move(
            avail.center().x() - width // 2,
            avail.center().y() - height // 2,
        )

    # ------------------------------------------------------------------ 关闭
    def closeEvent(self, event) -> None:  # noqa: N802
        """关窗＝离开这个任务：没在跑步骤时按详情页「返回」的口径释放资源。"""
        self._release_page()
        super().closeEvent(event)

    def _release_page(self) -> None:
        if self._closing:
            return
        self._closing = True
        process = getattr(self.page, "process", None)
        running = (
            process is not None
            and process.state() != QProcess.ProcessState.NotRunning
        )
        if running:
            # 步骤正在跑：别在它跑的时候拆页面（"任务进行中不许返回"同理）。
            # 窗口销毁由 WA_DeleteOnClose 负责，worker 归它自己的宿主收尾。
            return
        try:
            self.page._on_back()
        except RuntimeError:
            # 底层 C++ 对象已提前释放（连点关闭等）：没什么可释放的了
            pass
