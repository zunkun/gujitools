# -*- coding: utf-8 -*-
"""串行后台任务队列：同一时刻只跑一个 job，且**等界面画完再开工**。

## 为什么必须串行

导入 PDF 后要跑「复制源文件 + 渲染整本缩略图」，那是 PyMuPDF 的密集 C 调用。
原先每次导入都起一个线程、且不设上限，多个渲染线程同时跑就会争抢 GIL，
主线程的每一次文件操作都被排到 GIL 队列后面：

| 并发渲染线程 | 0 | 1 | 4 | 8 | 15 |
|---|---|---|---|---|---|
| 主线程 `create_task` 中位 | 5.5ms | 98ms | 216ms | 608ms | **1500ms** |

对照实验排除了磁盘因素：后台**纯写盘**（狂写 8KB 文件、期间落盘 1110 个文件）
对主线程 0 影响（stat 0.09ms、读 3KB 0.11ms、写 0.7ms）——是 GIL/线程调度，
不是 I/O、不是 fsync、也不是 tasks.json 的体积。串行 + 每页让出 GIL 后
主线程回到 16ms（脚本见 ``.workbuddy/perf/``）。

## 为什么还要「扣住不放行」

列表出现新行必须读 N 个任务的 runs.json。无争抢时 18 个任务只要 7.5ms；
一旦和渲染线程撞上，每个文件操作都要等 GIL，实测「导入 → 看见新行」从
0.2s 变成 0.5~2.5s。所以新 job 提交后先**扣住**，等页面把列表画完调
``release()`` 再开工；同时留一个超时兜底，信号丢了也不会永远不干活。
"""

from __future__ import annotations

from collections import deque
from typing import NamedTuple

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from desktop.workers.worker_host import connect_queued


class _Job(NamedTuple):
    """一个排队中的后台 job。

    `tag` 是归属标记（本项目传 task_id）：删任务时要能精确停掉「这个任务自己的」
    job，而不是把整个队列一刀切（见 `cancel_tag`）。
    """

    worker: QObject
    label: str
    callbacks: dict
    tag: str | None = None


class SerialJobQueue(QObject):
    """把一次性后台 job 串成一条队列，并支持「界面画完再放行」。

    用法：``submit(worker, label, on_warning=..., on_failed=...)`` 排队，
    ``release()`` 放行，``shutdown()`` 收尾。

    进度信号（job_started / progress / job_finished）供页面显示「正在导入」
    提示条：整本缩略图可能要跑几十秒，用户必须看得到它还在干活。
    """

    #: 某个 job 开始跑了（携带 label）
    job_started = Signal(str)
    #: 当前 job 的进度 (已完成, 总数)
    progress = Signal(int, int)
    #: 某个 job 结束（携带 label）；此时队列可能还有后续 job
    job_finished = Signal(str)

    #: 提交后最多等这么久就自动放行（页面回程信号丢失时的兜底）
    RELEASE_TIMEOUT_MS = 3000
    #: 两个 job 之间的间隔：让主线程把上一轮的收尾活干完
    GAP_MS = 150

    def __init__(self, owner: QObject):
        """owner 为宿主 widget（主线程）；线程与中继都挂在它下面。"""
        super().__init__(owner)
        #: 待跑的 job（见 _Job）
        self._pending: deque[_Job] = deque()
        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._label = ""
        #: 正在跑的 job 的 tag（用于按任务取消，见 cancel_tag）
        self._running_tag: str | None = None
        self._relays: list[QObject] = []
        #: True = 还没放行（正在等页面把列表画完）
        self._gated = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)

    # ------------------------------------------------------------ 对外接口
    def submit(
        self,
        worker: QObject,
        label: str = "",
        on_warning=None,
        on_failed=None,
        tag: str | None = None,
    ) -> None:
        """排队一个 job；等 ``release()``（或超时）后按提交顺序执行。

        `tag` 给这个 job 打归属标记（本项目传 task_id），供 `cancel_tag` 精确
        取消"某个任务的活"——删任务时必须先停掉它自己的后台导入，否则
        `rmtree` 会撞上正在写的文件（见 `cancel_tag`）。
        """
        self._pending.append(
            _Job(worker, label, {"warning": on_warning, "failed": on_failed}, tag)
        )
        # 先扣住：列表行还没画出来，现在开工只会抢 GIL 把回程拖慢
        self._gated = True
        self._timer.start(self.RELEASE_TIMEOUT_MS)
        self._maybe_start()

    def release(self) -> None:
        """界面画完了：放行排队中的 job（重复调用无副作用）。"""
        if not self._gated:
            return
        self._gated = False
        self._timer.stop()
        self._maybe_start()

    def running_count(self) -> int:
        """正在跑的 job 数（0 或 1）。"""
        return 1 if self._thread is not None else 0

    def pending_count(self) -> int:
        """排队中的 job 数。"""
        return len(self._pending)

    def current_label(self) -> str:
        """正在跑的 job 的名字（没在跑就是空串）。"""
        return self._label

    def busy(self) -> bool:
        """还有 job 在跑或排队。"""
        return self._thread is not None or bool(self._pending)

    def cancel_tag(self, tag: str | None, wait_ms: int = 3000) -> bool:
        """取消某个 tag（任务）名下的活：丢掉排队的、让在跑的收手并等它。

        ⚠️ 为什么需要它（2026-09-26 审计）：`delete_task` 只关预览缓存就删目录，
        不管该任务**自己的**后台导入（复制源文件 + 渲染整本缩略图，2400 页要
        69s）。`rmtree` 撞上正在写的文件 → 重试 8 次后失败，用户看到
        「文件正被占用」；更糟的是删完后台线程还按旧路径继续写。

        返回 True 表示该任务名下的活已经全部停下（可以安全删目录）；
        False 表示超时仍未收手（调用方应告知用户稍后重试，别硬删）。
        """
        if tag is None:
            return True
        self._pending = deque(job for job in self._pending if job.tag != tag)
        if self._running_tag != tag:
            return True
        worker, thread = self._worker, self._thread
        if worker is not None and hasattr(worker, "cancel"):
            # 缩略图渲染循环会在下一页开头退出（单页最长约一两百毫秒）
            worker.cancel()
        # 复制线程是 daemon，cancel() 打不断它；worker 自己会在收手时短暂 join
        # 一下（否则 .part 文件还开着，rmtree 照样失败）。
        waiter = getattr(worker, "wait_copy", None)
        if callable(waiter):
            try:
                waiter(wait_ms / 1000)
            except Exception:  # noqa: BLE001 - 收尾尽力而为
                pass
        if thread is None:
            return True
        return thread.wait(wait_ms)

    def shutdown(self, wait_ms: int = 800) -> None:
        """退出收尾：停表、丢弃排队的活、让当前 job 尽快退出。

        当前 job 的 ``cancel()`` 让它在下一次循环检查时收手（整本可能几千页，
        不能傻等）；随后 ``quit()`` 结束线程事件循环。
        """
        self._timer.stop()
        self._pending.clear()
        self._gated = False
        worker, thread = self._worker, self._thread
        if worker is not None and hasattr(worker, "cancel"):
            worker.cancel()
        if thread is not None:
            thread.quit()
            thread.wait(wait_ms)
        self._thread = None
        self._worker = None
        self._relays.clear()

    # ------------------------------------------------------------ 内部调度
    def _on_timer(self) -> None:
        """兜底放行 / 间隔结束 → 拉起下一个。"""
        self._gated = False
        self._maybe_start()

    def _maybe_start(self) -> None:
        """有空位、已放行且队列非空时，启动下一个 job。"""
        if self._thread is not None or self._gated or not self._pending:
            return
        job = self._pending.popleft()
        worker, label, callbacks = job.worker, job.label, job.callbacks
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        # 子线程 emit → 排队回主线程再弹 toast（闭包必须走 connect_queued）
        on_warning = callbacks.get("warning")
        if on_warning is not None and hasattr(worker, "warning"):
            self._relays.append(connect_queued(self, worker.warning, on_warning, thread))
        on_failed = callbacks.get("failed")
        if on_failed is not None:
            self._relays.append(connect_queued(self, worker.failed, on_failed, thread))
        if hasattr(worker, "progress"):
            # 进度也要回主线程再更新界面
            self._relays.append(
                connect_queued(
                    self,
                    worker.progress,
                    lambda done, total: self.progress.emit(done, total),
                    thread,
                )
            )
        # ⚠️ thread.finished 是在**子线程**里发出的，lambda 直接连会在子线程
        #    执行（那里改队列、起下一个 QThread 都是错的），必须走中继回主线程
        self._relays.append(
            connect_queued(
                self,
                thread.finished,
                lambda t=thread, name=label: self._on_job_done(t, name),
                thread,
            )
        )
        self._thread, self._worker, self._label = thread, worker, label
        self._running_tag = job.tag
        thread.start()
        self.job_started.emit(label)

    def _on_job_done(self, thread: QThread, label: str) -> None:
        """一个 job 结束（已在主线程）：释放引用，隔一小段再把下一个放出去。"""
        if self._thread is not thread:
            return
        self._thread = None
        self._worker = None
        self._label = ""
        self._running_tag = None
        self._relays.clear()  # 中继已随线程 deleteLater，这里只丢 Python 引用
        thread.deleteLater()
        self.job_finished.emit(label)
        if self._pending:
            self._timer.start(self.GAP_MS)
