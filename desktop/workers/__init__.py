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

from typing import TYPE_CHECKING

#: 惰性导出的**类型**侧声明（见模块 docstring）：类型检查器看不见 PEP 562 的
#: ``__getattr__``，缺这一段会把下面 ``_LAZY`` 里的名字全当成未定义。
#: **只影响类型检查**——运行时的惰性导入一点没变（启动期仍不会拉进
#: preview_worker 等重模块）。
if TYPE_CHECKING:
    from desktop.workers.copy_source_worker import CopyFilesWorker, CopySourceWorker
    from desktop.workers.hash_worker import HashWorker
    from desktop.workers.image_list_worker import ImageListWorker
    from desktop.workers.imposition_worker import (
        ImpositionComposeWorker, ImpositionPagePreviewWorker,
    )
    from desktop.workers.preview_worker import PreviewWorker, close_cached_documents
    from desktop.workers.rembg_live_worker import RembgLiveWorker
    from desktop.workers.source_thumbnails_worker import SourceThumbnailsWorker
    from desktop.workers.task_rows_worker import TaskRowsWorker
    from desktop.workers.thumb_cache_worker import ImageThumbCacheWorker

__all__ = [
    "CopyFilesWorker",
    "CopySourceWorker",
    "HashWorker",
    "ImageListWorker",
    "ImpositionComposeWorker",
    "ImpositionPagePreviewWorker",
    "PreviewWorker",
    "RembgLiveWorker",
    "SerialJobQueue",
    "SourceThumbnailsWorker",
    "TaskRowsWorker",
    "ImageThumbCacheWorker",
    "WorkerHost",
    "close_cached_documents",
    "connect_queued",
]

#: 惰性导出的名字 → (模块路径, 属性名)
_LAZY = {
    "CopyFilesWorker": (
        "desktop.workers.copy_source_worker",
        "CopyFilesWorker",
    ),
    "CopySourceWorker": (
        "desktop.workers.copy_source_worker",
        "CopySourceWorker",
    ),
    "HashWorker": ("desktop.workers.hash_worker", "HashWorker"),
    "ImageListWorker": ("desktop.workers.image_list_worker", "ImageListWorker"),
    "ImageThumbCacheWorker": (
        "desktop.workers.thumb_cache_worker", "ImageThumbCacheWorker",
    ),
    "ImpositionComposeWorker": (
        "desktop.workers.imposition_worker",
        "ImpositionComposeWorker",
    ),
    "ImpositionPagePreviewWorker": (
        "desktop.workers.imposition_worker",
        "ImpositionPagePreviewWorker",
    ),
    "PreviewWorker": ("desktop.workers.preview_worker", "PreviewWorker"),
    "RembgLiveWorker": ("desktop.workers.rembg_live_worker", "RembgLiveWorker"),
    "SourceThumbnailsWorker": (
        "desktop.workers.source_thumbnails_worker",
        "SourceThumbnailsWorker",
    ),
    "TaskRowsWorker": ("desktop.workers.task_rows_worker", "TaskRowsWorker"),
    "close_cached_documents": (
        "desktop.workers.preview_worker",
        "close_cached_documents",
    ),
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
