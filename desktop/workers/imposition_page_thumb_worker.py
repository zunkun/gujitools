# -*- coding: utf-8 -*-
"""拼版**页面效果缩略图实体**的后台生成器。

用户 2026-10-09（0002 任务）：页面缩略图不再在内存里临时拼——**实体落盘**
（``pageN.jpg`` + ``index.json`` 映射）。本 worker 收一批
``{"index", "name", "signature", "page"}`` 任务，逐页从全尺寸源图合成整页
缩略图、原子写盘、逐页上报；UI 拿到就贴，重进任务直接命中实体零生成。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImage

from desktop.workers.thumb_cache_worker import encode_jpeg
from utils.file_utils import write_bytes_atomic


class ImpositionPageThumbWorker(QObject):
    """逐页合成**整页**缩略图并落盘；每页就绪即发一次 :attr:`page_ready`。

    合成在 worker 线程做（QImage/QPainter 画非界面图，线程安全——与
    :class:`~desktop.workers.thumb_cache_worker.ImageThumbCacheWorker`
    同一套做法）；只写 ``pageN.jpg``，**不碰** ``index.json``（映射数据
    由主线程的 :class:`~desktop.components.imposition.page_thumb.\
PageThumbManager` 统一维护，同一文件永远只有一个写入者）。
    """

    page_ready = Signal(int, QImage, str, str)  # 页号, 图, 实体路径, 签名
    completed = Signal()
    failed = Signal(str)

    def __init__(self, jobs: list[dict], out_dir: Path | str, edge: int):
        super().__init__()
        self.jobs = list(jobs)
        self.out_dir = Path(out_dir)
        self.edge = int(edge)
        self._cancelled = False

    def cancel(self) -> None:
        """请求中止：在**下一页**之前退出（已写好的都在盘上，重进直接命中）。"""
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        """逐页：合成 → 原子写盘 → 上报；单页失败跳过，不让整批停摆。"""
        try:
            from desktop.components.imposition.page_thumb import (
                compose_page_thumb_from_files,
            )

            self.out_dir.mkdir(parents=True, exist_ok=True)
            for job in self.jobs:
                if self._cancelled:
                    break
                image = compose_page_thumb_from_files(job["page"], self.edge)
                import sys as _s
                print(f"[dbg-w] job={job['index']} name={job['name']} "
                      f"img={None if image is None else (image.width(), image.height())} "
                      f"cancelled={self._cancelled}", file=_s.stderr)
                if image is None or image.isNull():
                    continue  # 源图读不出来等：这页先占位，下次刷新再试
                target = self.out_dir / str(job["name"])
                data = encode_jpeg(image)
                if not data:
                    continue
                try:
                    write_bytes_atomic(target, data)
                except OSError:
                    continue  # 写不下去（权限/磁盘满）：界面下次再试
                self.page_ready.emit(
                    int(job["index"]), image, str(target),
                    str(job["signature"]),
                )
            import sys as _s; print('[dbg-w] completed', file=_s.stderr)
            import sys as _s; print('[dbg-w] completed', file=_s.stderr)
            self.completed.emit()
        except Exception as exc:  # noqa: BLE001 - 兜底：别让线程静默死掉
            self.failed.emit(str(exc))
