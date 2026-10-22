# -*- coding: utf-8 -*-
"""PDF 页渲染的**单飞锁**：全进程同一时刻只允许一个 PyMuPDF 页渲染。

⚠️ 现状（2026-10-21 起）：渲染已经**搬到子进程**（``pdf_render_service``），
这把锁现在只保护"**进程内兜底**"那条路——子进程池起不来、或
``GUJI_PDF_RENDER=inproc`` 时，渲染仍在 GUI 进程里做，就必须持这把锁
（见 ``pdf_render_service._inproc_render_jpeg``）。出进程时锁是空转的。

⚠️ 为什么当时单独成模块（不放在 ``preview_worker`` 里）
    导入后台任务（``source_thumbnails_worker``）也要用这把锁，而
    ``preview_worker`` 是 500+ 行的重模块（还带着第四步效果合成的整套依赖）。
    从它 import 会把这些依赖拖进**启动路径**——`desktop/workers/__init__.py`
    的惰性导出正是为了避免这件事。所以锁放在这个零依赖的小模块里，谁都能引。

⚠️ 历史：它当初存在的理由是"渲染全程攥 GIL 105~180ms，两个渲染并行就互相抢"。
    那把锁只能压**并发**、压不掉**单次**——一页 JPX 扫描件（4000×6000）实测
    ~850ms，GUI 在这 850ms 里一次都拿不到时间片。真正的解法是换进程，见
    ``desktop/workers/pdf_render_service.py`` 的模块说明。
"""

from __future__ import annotations

import threading

#: 全局唯一的渲染锁。用 ``single_flight()`` 取，不要直接引用这个私有名。
_PDF_RENDER_LOCK = threading.Lock()


def single_flight() -> threading.Lock:
    """取单飞锁。用法：``with single_flight(): ...渲染一页...``。

    ⚠️ 只把**渲染本身**（load_page + get_pixmap + tobytes）包进锁：写盘、
    ``QImage.fromData``、让出 GIL 的 sleep 都放锁外——否则别的渲染请求要陪着
    等 I/O，锁的粒度就过粗了。
    """
    return _PDF_RENDER_LOCK
