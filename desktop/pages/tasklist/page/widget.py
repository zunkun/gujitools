# -*- coding: utf-8 -*-
"""任务管理页：表格列表 + **创建任务**（弹窗选流程与PDF → 算指纹查重 → 建任务）。

本文件只保留页面骨架（信号、构造、收尾），其余职责按功能分文件
（均位于 desktop/pages/tasklist/page/）：
- view.TaskListViewMixin   页头 / 搜索条 / 表格与空状态 / 底栏 / toast
- rows.TaskListRowsMixin   数据刷新、过滤与分页渲染
- importing.TaskListImportMixin 创建任务（指纹/查重/建任务/后台导入）、
  聚合任务汇集与删除
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget
from qfluentwidgets import PrimaryPushButton

from desktop.workers import HashWorker, SerialJobQueue, WorkerHost
from desktop.store import TaskStore
from desktop.components.pagination import DEFAULT_PAGE_SIZE
from desktop.pages.tasklist.page.importing import TaskListImportMixin
from desktop.pages.tasklist.page.rows import TaskListRowsMixin
from desktop.pages.tasklist.page.view import TaskListViewMixin


class TaskListPage(
    TaskListViewMixin,
    TaskListRowsMixin,
    TaskListImportMixin,
    QWidget,
    WorkerHost,
):
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
    #: 「创建任务」按钮被点了——宿主（壳层）切到**创建任务二级页**
    #: （2026-10-06 起不再是模态弹窗）。
    create_requested = Signal()
    #: 刚建好一条导入任务（源文件还没复制完、缩略图刚要开始渲）。
    #: 宿主据此**预热详情页**：用户下一步就是点进这一行，而详情页里惰性
    #: 构造的第四步面板要 ~150ms（机器空闲时）；等他在导入后台攥着 GIL 的
    #: 窗口里点进去再建，会被拖成 ~2 秒（实测 1987ms）——那正是「从列表点进
    #: 详情要等几秒」。挪到"刚点完导入、本来就在等"的时机付掉这笔开销。
    import_queued = Signal()
    #: 聚合任务的成员产物**汇集完成**（后台复制完毕、起点已置为已完成）。
    #: 宿主据此刷新详情页——否则用户看到的是"创建了但什么都没有"的空任务。
    aggregate_ready = Signal(str)

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
        #: 正在汇集成员产物的聚合任务：``{任务号: (QThread, worker)}``。
        #: 保留强引用防 GC（线程在跑而 Python 侧对象被回收＝Qt abort）；
        #: 线程结束时摘掉（见 :meth:`_start_aggregate_ingest` 的接线）。
        self._aggregate_jobs: dict[str, tuple[QThread, object]] = {}
        self._import_button: PrimaryPushButton | None = None
        #: 当前挂着的「创建任务」弹窗（防GC；弹窗期间用户点不了列表）
        self._create_dialog = None
        #: **本次**建任务要用的自定义流程（BPM 驱动，M3）。None = 默认流程。
        #⚠️ 建完任务立刻清空——留着会让下一个任务莫名其妙用上一份流程。
        self._pending_diagram = None
        #: 创建页填的任务名（空 = 回落源文件名）
        self._pending_name = ""
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

    def shutdown_workers(self) -> None:
        """关程序前的收尾：先停导入后台队列（复制/缩略图），再走基类线程。"""
        self._thumb_queue.shutdown()
        self._shutdown_hash_thread()
        # 聚合汇集是"一次性的重复制"，不可中断；等不到就摘父对象保命
        # （与指纹线程同一处理）。
        if self._aggregate_jobs:
            from desktop.workers.worker_host import stop_thread

            for thread, _worker in list(self._aggregate_jobs.values()):
                stop_thread(thread, self.DELETE_STOP_WAIT_MS, "聚合汇集线程")
            self._aggregate_jobs.clear()
        super().shutdown_workers()

    def _shutdown_hash_thread(self) -> None:
        """收尾指纹线程。

        ⚠️ `hash_thread = QThread(self)` 挂在**页对象**下，而基类
        `shutdown_workers` 只认它自己登记的 `_threads`，从不碰这个属性
        （2026-09-26 审计发现）。于是「导入 PDF 后、指纹还没算完就关程序」
        （800MB 的书要 1~2s）会让 QThread 对象在运行中被销毁 → Qt abort。
        哈希不可中断，只能等；等不到由 `stop_thread` 摘出父对象保命。
        """
        from desktop.workers.worker_host import stop_thread

        # stop_thread 自己会处理 None，这里显式跳过省一次调用（语义等价）
        if self.hash_thread is not None:
            stop_thread(self.hash_thread, self.HASH_SHUTDOWN_WAIT_MS, "指纹线程")

    #: 指纹线程的收尾等待上限（毫秒）：整本 PDF 的 SHA-256，留够余量
    HASH_SHUTDOWN_WAIT_MS = 5000

    #: 删任务前等该任务后台导入收手的上限（毫秒）。
    #: 缩略图渲染在下一页开头退出（单页约一两百毫秒），复制线程可能要更久；
    #: 等不到就不删、让用户稍后重试——比留半个目录或弹"文件正被占用"好。
    DELETE_STOP_WAIT_MS = 5000
