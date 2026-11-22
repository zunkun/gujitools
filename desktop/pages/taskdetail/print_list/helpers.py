# -*- coding: utf-8 -*-
"""子模块共用的小工具（从原 ``print_list.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from desktop.pages.taskdetail.print_list._qt import QWidget
def _parent(page) -> "QWidget":
    """Mixin 里的 ``self`` 当文件对话框的 parent 用——宿主是 QWidget。

    ⚠️ 类型检查器看 Mixin 只看到「一个普通类」，故这里 cast 一下；运行时
    什么也没做（cast 是恒等函数）。
    """
    return cast(QWidget, page)


def _file_stamp(path: Path) -> tuple[int, int] | None:
    """文件的 ``(mtime_ns, 字节数)``：缩略图路径记忆的失效判据。读不到给 ``None``。

    与 ``thumb_cache_worker`` 的有效性判据同源（那套判"缓存不旧于源图"），
    这里只判"源图还是不是刚才那张"——源图被上游覆盖（拼版重合成、编辑器
    回写）后 mtime/大小必变 ⇒ 记忆自动作废，重新查一遍缓存。
    """
    try:
        info = path.stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size)
