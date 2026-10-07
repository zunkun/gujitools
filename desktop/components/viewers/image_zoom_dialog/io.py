# -*- coding: utf-8 -*-
"""预览弹窗的**存盘原语**（下载另存 / 原子覆盖原图）。

从 ``image_zoom_dialog.py`` 拆出（2026-10-07）。方法体逐字未改。
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from PySide6.QtGui import QImage

from utils.file_utils import replace_with_retry

from .consts import JPEG_QUALITY, OVERWRITE_FORMATS, OVERWRITE_JPEG_QUALITY

def save_image(image: QImage, path: str | Path,
               quality: int = JPEG_QUALITY) -> bool:
    """把 QImage 写到磁盘：``.jpg``/``.jpeg`` 走有损（quality），其余交给 Qt。

    单独抽出来是为了可测——保存对话框在离屏环境里弹不出来。
    """
    target = Path(path)
    # ⚠️ type: ignore —— PySide6 的 save() 类型注解把 format 写成
    # ``bytes | bytearray | memoryview | None``，但**运行时接受 str**（官方
    # 示例也传字符串）。这里按运行时的写法保持不变。
    if target.suffix.lower() in (".jpg", ".jpeg"):
        return bool(image.save(str(target), "JPEG", quality))  # type: ignore[reportCallIssue]
    return bool(image.save(str(target)))  # type: ignore[reportCallIssue]


def overwrite_image_file(image: QImage, target: Path,
                         quality: int = OVERWRITE_JPEG_QUALITY) -> bool:
    """把 ``image`` **原子**覆盖到 ``target``（格式按目标后缀）。

    ⚠️ 必须走「临时文件 + os.replace」，不能就地写：任务目录里的页面图
    可能是硬链接（workset 时代的遗产），就地写会把链接另一头的源文件一起
    改掉；且覆盖途中被 200ms 一次的 extract 轮询/预览读到半截也是事故。
    ``os.replace`` 换的是目录项——读者要么看到完整旧图、要么看到完整新图，
    旧 inode 原样留在硬链接另一头。
    """
    fmt = OVERWRITE_FORMATS.get(target.suffix.lower(), "PNG")
    temp = target.with_name(
        f"{target.stem}.{os.getpid():x}{threading.get_ident():x}"
        f"{target.suffix}.part"
    )
    try:
        # ⚠️ type: ignore —— 同 _save_image：PySide6 的 save() 注解要求
        # format 是 bytes，但运行时接受 str（实测 str 正常编码）。
        if not image.save(str(temp), fmt, quality):  # type: ignore[reportCallIssue]
            return False
        replace_with_retry(temp, target)
        return True
    except OSError:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        return False
