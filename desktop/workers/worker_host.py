# -*- coding: utf-8 -*-
"""WorkerHost：在拥有者 widget 内启动一次性后台 worker 线程并自动回收。"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread


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
        thread.finished.connect(lambda *_: self._forget_worker(worker, thread))
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
