# -*- coding: utf-8 -*-
"""后台 worker 线程模型：WorkerHost 混入 + 各类 QObject worker。

⚠️ **具体 worker 一律惰性导出**（PEP 562 模块级 ``__getattr__``）。

为什么：启动路径只走到**任务列表页**，它用到的是 HashWorker（导入 PDF 算指纹）
与 SourceThumbnailsWorker（缩略图）。而本文件原先在模块顶层把每个 worker 都
import 了一遍，于是详情页的活——``preview_worker``（PDF 渲染 + 第四步效果预览
绘制，500+ 行）等——全被拖进启动。实测启动期会多加载 5 个与列表页无关的模块。

旧写法 ``from desktop.workers import PreviewWorker`` 依然可用，只是变懒了：
属性首次被访问时才真正 import，并把结果缓存进模块 globals。

``WorkerHost`` / ``connect_queued`` 仍走立即导入——它们只是 QThread 的薄封装，
没有重依赖，而且几乎每个页面都要用。
"""

from desktop.workers.worker_host import WorkerHost, connect_queued
from desktop.workers.serial_jobs import SerialJobQueue

__all__ = [
    "HashWorker",
    "ImageListWorker",
    "PreviewWorker",
    "RembgLiveWorker",
    "SerialJobQueue",
    "SourceThumbnailsWorker",
    "TaskRowsWorker",
    "WorkerHost",
    "connect_queued",
]

#: 惰性导出的名字 → (模块路径, 属性名)
_LAZY = {
    "HashWorker": ("desktop.workers.hash_worker", "HashWorker"),
    "ImageListWorker": ("desktop.workers.image_list_worker", "ImageListWorker"),
    "PreviewWorker": ("desktop.workers.preview_worker", "PreviewWorker"),
    "RembgLiveWorker": ("desktop.workers.rembg_live_worker", "RembgLiveWorker"),
    "SourceThumbnailsWorker": (
        "desktop.workers.source_thumbnails_worker",
        "SourceThumbnailsWorker",
    ),
    "TaskRowsWorker": ("desktop.workers.task_rows_worker", "TaskRowsWorker"),
}


def __getattr__(name: str):
    """按需导入具体 worker（PEP 562），并缓存以免重复走导入系统。"""
    entry = _LAZY.get(name)
    if entry is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module_path, attr_name = entry
    value = getattr(importlib.import_module(module_path), attr_name)
    globals()[name] = value  # 缓存：下次访问直接命中 globals，不再进 __getattr__
    return value
