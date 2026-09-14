# -*- coding: utf-8 -*-
"""缩略图异步装载混入：为 ThumbStrip 批量加载图片缩略图。"""

from __future__ import annotations

from pathlib import Path

from ..viewers.thumb_strip import ThumbStrip
from ...workers import ImageListWorker, WorkerHost


class ThumbsMixin(WorkerHost):
    """为持有 ThumbStrip 的查看器提供批量缩略图加载。"""

    def _init_thumbs(self) -> None:
        self._init_worker_host()

    def _load_thumbs(self, strip: ThumbStrip, paths: list[Path]) -> None:
        self.run_worker(
            lambda: ImageListWorker(paths),
            lambda worker, thread: (
                worker.thumbnail_ready.connect(
                    lambda i, img, p: strip.set_item_icon(
                        i, img, p, Path(p).name
                    )
                ),
                worker.completed.connect(thread.quit),
                worker.failed.connect(lambda *_: thread.quit()),
            ),
        )
