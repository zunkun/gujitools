# -*- coding: utf-8 -*-
"""WorkerHost：在拥有者 widget 内启动一次性后台 worker 线程并自动回收。"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread


class _SlotRelay(QObject):
    """主线程里的中继对象：把 worker 线程 emit 的参数转交闭包执行。

    PySide6 的两条坑决定了必须绕一道：

    - ``signal.connect(lambda)`` 是**直接连接**：lambda 没有接收者 QObject，
      Qt 判断不出它属于哪个线程，槽就跑在 emit 的（worker）线程里；
    - 给 lambda 加 ``Qt.QueuedConnection`` **也没用**：functor 连接的接收者
      被记成 sender 自己，事件照样排回 worker 线程。

    唯一可靠做法：让接收者成为**主线程里的 QObject**——``forward`` 是它的
    绑定方法，Qt 按接收者线程自动排队，于是闭包一定在主线程执行。
    """

    def __init__(self, parent, callback):
        """parent 须为主线程内的 QObject（通常就是宿主 widget）。"""
        super().__init__(parent)
        self._callback = callback

    def forward(self, *args):
        """接收 worker 发来的任意参数，转交构造时给的闭包（已在主线程）。"""
        self._callback(*args)


def connect_queued(owner, signal, slot, thread=None) -> QObject:
    """worker 信号 → 主线程闭包的**唯一正确写法**，返回中继对象。

    ⚠️ 直接 ``signal.connect(lambda ...)`` 会让闭包在 **worker 线程**执行。
    里面一旦碰 widget（``strip.set_item_icon``、``view.clear_image``、
    ``set_image``…），Qt 内部就在子线程启动定时器，控制台刷屏
    ``QBasicTimer::start: Timers cannot be started from another thread``
    （每张缩略图一条——用户报告的就是这个）。连到**宿主 QObject 的绑定
    方法**（``worker.finished.connect(self._ready)``）本来就安全，无需本
    助手；闭包 / lambda 一律走这里。

    owner 为宿主 widget（主线程），thread 给了就在线程结束时回收中继，
    避免长会话反复加载累积出一批中继对象。
    """
    relay = _SlotRelay(owner, slot)
    signal.connect(relay.forward)
    if thread is not None:
        # deleteLater 是 relay 自己的绑定方法 → 同样排队回主线程，安全
        thread.finished.connect(relay.deleteLater)
    return relay


#: 收尾等了超时、但**仍在运行**的线程。必须留引用：QThread 对象一旦在
#: "还在跑"的状态下被销毁，Qt 会直接 abort 整个进程
#: （`QThread: Destroyed while thread is still running`）。
_DETACHED_THREADS: list[QThread] = []


def stop_thread(thread: QThread, timeout_ms: int, label: str) -> bool:
    """请线程收手并最多等 `timeout_ms`；等不到就**摘下来别让它被销毁**。

    返回 True 表示已结束。

    为什么不能只 `quit()+wait()+丢引用`（2026-09-26 审计）
        `quit()` 只结束线程的事件循环，打不断正在执行的槽。本项目里
        `PreviewWorker._render_all_thumbnails`（整本缩略图）与 `PreviewWorker`
        的单页渲染都是长阻塞循环，`HashWorker` 要算完整本 PDF 的 SHA-256
        （800MB 约 1~2s）。这些线程都 parent 在 widget 上，而项目的退出路径是
        「worker 线程仍在跑时先销毁 widget」→ QThread 对象被销毁 → Qt abort
        （用户看到的是"关程序时崩一下"）。等不到时的正确做法不是假装成功，
        而是把线程从父对象上摘下来、由模块级列表持有引用，让它自然跑完。
    """
    if thread is None or not thread.isRunning():
        return True
    thread.quit()
    if thread.wait(timeout_ms):
        return True
    # 等不到：保命优先 —— 换父、留住引用，绝不让它在跑着的时候被析构
    _DETACHED_THREADS.append(thread)
    try:
        thread.setParent(None)
    except (RuntimeError, TypeError):  # 对象已在 C++ 侧销毁
        pass
    print(f"[shutdown] {label} 未在 {timeout_ms}ms 内结束，已摘出父对象避免崩溃")
    return False


class WorkerHost:
    """Mixin：在拥有者 widget 内启动一次性后台 worker 线程。"""

    def _init_worker_host(self) -> None:
        self._threads: list[QThread] = []
        self._workers: list[QObject] = []

    def run_worker(self, factory, wire) -> None:
        """
        启动一次性 worker 线程并登记引用以便回收。

        factory() 负责造 worker，wire(worker, thread) 负责连信号；线程结束后
        worker 自动 deleteLater 并移出引用表，避免长会话下线程对象堆积。
        """
        thread = QThread(self)
        worker = factory()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        wire(worker, thread)
        thread.finished.connect(worker.deleteLater)
        # thread.finished 由 worker 线程发出 → 排队回主线程再改引用表
        connect_queued(self, thread.finished,
                       lambda *_: self._forget_worker(worker, thread))
        self._threads = [t for t in self._threads if t.isRunning()]
        self._threads.append(thread)
        # 持有引用，避免 worker 在线程启动前被垃圾回收
        self._workers.append(worker)
        thread.start()

    def _forget_worker(self, worker: QObject, thread: QThread) -> None:
        for container in (self._workers, self._threads):
            if worker in container:
                container.remove(worker)
            if thread in container:
                container.remove(thread)

    def shutdown_workers(self) -> None:
        """退出并等待所有后台线程，随后清空引用表。

        先给每个 worker 发一次 `cancel()`（有的话）——批量缩略图那种长循环
        只有收到中止信号才会在页边界退出（见 `PreviewWorker.cancel`），
        不然 `wait` 注定超时、线程被摘出去后还在后台啃 GIL。
        等不到的线程交给 `stop_thread` 摘出父对象（否则 QThread 在运行中被销毁
        会让 Qt abort —— 见 `stop_thread` 的说明）。
        """
        for worker in list(self._workers):
            cancel = getattr(worker, "cancel", None)
            if callable(cancel):
                try:
                    cancel()
                except Exception:  # noqa: BLE001 - 收尾尽力而为
                    pass
        for thread in list(self._threads):
            stop_thread(thread, self.SHUTDOWN_WAIT_MS, "后台线程")
        self._threads.clear()
        self._workers.clear()

    #: 单个后台线程的收尾等待上限（毫秒）。长阻塞的渲染循环等不到就会被摘出去，
    #: 不让它带着父对象一起被析构。
    SHUTDOWN_WAIT_MS = 800
