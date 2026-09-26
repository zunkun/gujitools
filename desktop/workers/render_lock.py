# -*- coding: utf-8 -*-
"""PDF 页渲染的**单飞锁**：全进程同一时刻只允许一个 PyMuPDF 页渲染。

⚠️ 为什么单独成模块（不放在 ``preview_worker`` 里）
    导入后台任务（``source_thumbnails_worker``）也要用这把锁，而
    ``preview_worker`` 是 500+ 行的重模块（还带着第四步效果合成的整套依赖）。
    从它 import 会把这些依赖拖进**启动路径**——`desktop/workers/__init__.py`
    的惰性导出正是为了避免这件事。所以锁放在这个零依赖的小模块里，谁都能引。

⚠️ 谁必须走它
    **任何**从 PDF 页渲位图的代码：单页预览（``PreviewWorker._render_pdf_page``）、
    批量缩略图（``PreviewWorker._render_all_thumbnails``）、导入后台任务
    （``SourceThumbnailsWorker._render_page``）。渲染全程攥 GIL ~105–180ms
    （实测），两个渲染并行 = GIL 互相抢，界面停顿叠加成 N×180ms——用户看到的
    就是「切缩略图卡、多点几下直接卡死」。串行化之后停顿上限收敛到**单次渲染**，
    且不随点击次数/页数增长。
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
