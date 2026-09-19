# -*- coding: utf-8 -*-
"""缩略图异步装载混入：为 ThumbStrip 批量加载图片缩略图。"""

from __future__ import annotations

from pathlib import Path

from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.workers import ImageListWorker, WorkerHost, connect_queued


class ThumbsMixin(WorkerHost):
    """为持有 ThumbStrip 的查看器提供批量缩略图加载。"""

    def _init_thumbs(self) -> None:
        self._init_worker_host()

    def _load_thumbs(self, strip: ThumbStrip, paths: list[Path]) -> None:
        self.run_worker(
            lambda: ImageListWorker(paths),
            lambda worker, thread: (
                # ⚠️ 必须排队：worker 线程里直接 set_item_icon 会让 Qt 在子
                # 线程启动定时器（刷屏 QBasicTimer 警告），见 connect_queued
                connect_queued(
                    self,
                    worker.thumbnail_ready,
                    lambda i, img, p: strip.set_item_icon(
                        i, img, p, Path(p).name
                    ),
                    thread,
                ),
                worker.completed.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )
