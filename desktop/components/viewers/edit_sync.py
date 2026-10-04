# -*- coding: utf-8 -*-
"""「编辑生效链」的**查看器级原语**——编辑器覆盖文件后如何让界面跟上。

编辑链的完整口径（2026-10-03/04 定）：``ImageEditorDialog``「完成」→ 覆盖真实
文件 → 宿主收到 ``image_saved`` 信号 → 分两步走：

1. **立即上屏**（本调用内）：把编辑结果直接画到大图与条目图标，不等任何
   后台重解码——否则"改完屏幕还是旧图"，看着就是「编辑不生效」；
2. **后台重渲缩略图**：按新文件重生成缓存缩略图，渲好只刷那一条。

本模块把第 1 步与第 2 步的**收尾动作**收成函数（任务流程
``pages/taskdetail/manifest.py`` 与独立任务页 ``modules/thumb_source.py``
共用同一份，不再各写一份 getattr 探测）。缓存目录与重渲 worker 由各宿主
自管——那是两套**有意不同**的缓存布局（``tasks/<id>/thumbnails/`` 与
``singletask/<key>/`` 禁止借道），本模块不掺和。
"""

from __future__ import annotations

from typing import Any


def show_edited_image(viewer: Any, path_text: str, image=None) -> None:
    """编辑结果**立刻**上屏，不等缩略图重渲、不等重新解码文件。

    ``apply_edited_image``（``ImageViewerWidget`` 有）能直接把编辑结果画到
    大图与条目图标上；没有它的控件（``RembgPreviewWidget``）退到
    ``refresh_page`` 按新文件重载——那一趟是异步的，但不会显示旧图。
    """
    apply = getattr(viewer, "apply_edited_image", None)
    if image is not None and callable(apply):
        apply(path_text, image)
        return
    refresh = getattr(viewer, "refresh_page", None)
    if callable(refresh):
        refresh(path_text)


def apply_single_thumb(viewer: Any, path_text: str, cached: str) -> None:
    """重渲好的单条缩略图到位：只换这一条，其余条目不动。

    ``set_cached_thumb``（``RembgPreviewWidget``）：合并一条 + 刷该条；
    ``reload_thumb``（``ImageViewerWidget``）：忘掉旧记忆后重取。两者都没有
    的控件安静返回（调用方通常随后有大图兜底）。
    """
    single = getattr(viewer, "set_cached_thumb", None)
    if cached and callable(single):
        single(path_text, cached)
        return
    reload_thumb = getattr(viewer, "reload_thumb", None)
    if callable(reload_thumb):
        reload_thumb(path_text)
