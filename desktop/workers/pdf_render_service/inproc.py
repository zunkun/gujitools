# -*- coding: utf-8 -*-
"""进程内兜底渲染：与子进程那份**逐字一致**，只是持单飞锁。"""

from __future__ import annotations

from .child import _child_render_jpeg


def _inproc_render_jpeg(pdf_path: str, page_index: int, edge: int,
                        quality: int, fmt: str,
                        pages_dir: str | None = None) -> bytes:
    """进程内渲染（降级路径）：与子进程那份**逐字一致**，只是持单飞锁。

    锁是必须的：PyMuPDF 不是线程安全的，而这条路上仍可能有别的线程在渲。

    ⚠️ ``pages_dir`` 必须收下并透传（2026-10-24）：``render_jpegs`` /
    ``render_stream`` 的 spec 是 6 元组，少了这个参数就是
    ``TypeError: takes 5 positional arguments but 6 were given``——**降级到
    进程内的那一刻，缩略图整批全炸**，用户看到的就是"缩略图不出来"。
    """
    from desktop.workers.render_lock import single_flight

    with single_flight():
        return _child_render_jpeg(pdf_path, page_index, edge, quality, fmt,
                                  pages_dir)
