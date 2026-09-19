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
        """退出并等待所有后台线程（最多 800ms/线程），随后清空引用。"""
        for thread in self._threads:
            thread.quit()
            thread.wait(800)
        self._threads.clear()
        self._workers.clear()
