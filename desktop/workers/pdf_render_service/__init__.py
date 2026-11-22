# -*- coding: utf-8 -*-
"""PDF 页渲染**出进程**（GUI 进程里只发请求，不碰 PyMuPDF 的像素）。

## 为什么必须搬到子进程

PyMuPDF 的 ``page.get_pixmap()`` 在**整段解码期间持有 GIL**，而且扫描古籍常见
的内嵌格式是 **JPX（JPEG2000）**：

=====  =========================  ===================  ============
内嵌格式  内嵌图尺寸                 渲一张 256px 缩略图     备注
=====  =========================  ===================  ============
JPX    4285×5736（本仓样例书）      **~850 ms**          解码按像素线性增长
JPX    1280×2688                  ~190 ms
Flate  702×1360                   ~11 ms
=====  =========================  ===================  ============

这 850ms 里 GUI 线程**拿不到一次时间片**（实测：另一线程 1ms 心跳被拖成
800~970ms 一整块）。于是"导入后生成整本缩略图"＝一本 28 页的书把界面冻成
28 个 0.85 秒的卡顿块，用户感知就是「创建任务卡、进详情卡、切缩略图卡」。

单飞锁（``render_lock``）只能把**并发**压平，压不掉**单次**的 850ms——线程
方案对 PyMuPDF 渲染没有任何加速（见 ``utils.pdf_extract.render_pages_parallel``
的实测：6 线程仅 1.15×）。唯一出路是**换进程**：GIL 不共享，GUI 一次都不冻，
而且多个子进程可以真并行（本模块默认按 CPU 数开 2~3 个）。

## 用法

调用方**必须是后台线程**（``PreviewWorker.run`` / ``SourceThumbnailsWorker.run``
之类），这些函数是**阻塞**的：

- :func:`render_jpeg`：渲一页，返回 JPEG 字节（缩略图 / 大图预览）；
- :func:`page_count`：页数；
- :func:`extract_page`：单页"提取图片"落盘（与批量提取逐位一致）；
- :func:`shutdown`：退出前收子进程。

## 降级

子进程起不来（打包漏模块 / 权限 / OOM）时**自动退回进程内渲染**（并持
``single_flight`` 单飞锁），行为与改动前一致——宁可慢一点，也不能让缩略图
整片不出来。降级只发生一次，之后一直走进程内（避免每个请求都白试一遍）。

``GUJI_PDF_RENDER=inproc`` 可强制关闭出进程（排障 / 单测用）。

⚠️ 2026-11-22 起拆成子包（constants / child / jpx / thumbs / pool / inproc /
api）。本 ``__init__`` 只做重导出：既有 ``from desktop.workers.pdf_render_service
import X`` 全部不变；子模块之间不要反过来导入本包（会形成循环）。
"""

from __future__ import annotations

from .api import (
    extract_page,
    page_count,
    prewarm,
    render_jpeg,
    render_jpegs,
    render_stream,
)
from .child import (
    _child_djvu_render_jpeg,
    _child_extract_page,
    _child_page_count,
    _child_render_jpeg,
    _child_render_safe,
    _child_warmup,
    _is_djvu,
)
from .constants import (
    CALL_TIMEOUT_S,
    ENV_MODE,
    EXTRACT_WORKERS,
    JPX_FAST_MAX_EDGE,
    JPX_FAST_MIN_REDUCE,
    MAX_WORKERS,
    POOL_FAILURE_LIMIT,
)
from .inproc import _inproc_render_jpeg
from .jpx import (
    _child_jpx_thumb,
    _resolve_opj,
    _run_opj_thumb,
    jpx_fast_available,
)
from .pool import (
    _NoPool,
    _call,
    _drop_pool,
    _fallback_count,
    _mode,
    _note_success,
    _pool_or_none,
    _silent_failure,
    _worker_count,
    offloaded,
    reset_stats,
    shutdown,
    stats,
    workers,
)
from .thumbs import _thumb_from_page_image

__all__ = [
    "ENV_MODE",
    "EXTRACT_WORKERS",
    "JPX_FAST_MAX_EDGE",
    "extract_page",
    "offloaded",
    "jpx_fast_available",
    "page_count",
    "prewarm",
    "render_jpeg",
    "render_jpegs",
    "render_stream",
    "reset_stats",
    "shutdown",
    "stats",
    "workers",
]
