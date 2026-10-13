# -*- coding: utf-8 -*-
"""singletask「去底色」导出目录的**标记**与白底→透明**副本**（纯函数，无 Qt）。

背景（用户 2026-10-13）：独立去底色页导出的成品是**白底** PNG（singletask
交付物口径），但独立拼图页拼版时白底图会互相遮挡、也没法自由挪动——任务
流程里拼版吃的是透明底的提交产物，独立页之间没这层衔接。所以：

1. 去底色独立页（``desktop/modules/rembg``）导出成功后，在输出目录写一个
   **标记文件**（:func:`write_marker`，出处唯一在本模块）；
2. 拼图页选源时，凡**父目录带标记**的图，先在 singletask 缓存区生成
   **透明底副本**（:func:`make_transparent_copy`，**原图绝不改动**），拼版
   用副本；
3. 没标记的目录（或散图）原样直用，不复制、不转换。

白底→透明的判据与编码形态**复用** ``utils.transparent_png``（第三步提交
产物同一套规则），不在这里另写一份。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from utils.file_utils import write_bytes_atomic

#: 标记文件名。⚠️ 故意用非图片后缀：``StepSpec.collect_files`` 按图片扩展名
#: 收集源清单，标记文件永远不会被当成图收进去。
MARKER_NAME = "guji_singletask_rembg.json"

#: 透明底副本在 singletask 缓存区里的子目录（挂在独立拼图页名下：副本是
#: 拼版的输入缓存，不是去底色的产物）。
_COPIES_SUBDIR = "rembg_transparent"

#: 副本缓存挂在哪个 singletask 子任务下。⚠️ 与独立拼图页的
#: ``spec.disk_key()``（= "imposition"）一致——那里 editable/缩略图缓存同根；
#: 服务层不 import spec，写字面量并钉住（改 disk_key 必须同步这里）。
_IMPOSITION_DISK_KEY = "imposition"


def marker_path(out_dir) -> Path:
    """导出目录里的标记文件路径。"""
    return Path(out_dir) / MARKER_NAME


def write_marker(out_dir) -> None:
    """在去底色导出目录落标记（原子写；重复导出直接覆盖，内容幂等）。"""
    payload = json.dumps(
        {
            "kind": "singletask-rembg",
            "note": "独立任务「图片去底色」的导出目录（白底 PNG）",
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        ensure_ascii=False,
        indent=1,
    )
    write_bytes_atomic(marker_path(out_dir), payload.encode("utf-8"))


def is_marked(directory) -> bool:
    """目录是否带去底色导出标记。"""
    return marker_path(directory).is_file()


def split_marked(images: list[Path]) -> tuple[list[Path], list[Path]]:
    """把源图清单按**父目录有无标记**分成两堆（各自保持原顺序）。

    返回 ``(普通原图, 需转透明的图)``。散图（不在任何导出目录里）永远落
    在普通堆——没有标记就不复制副本（2026-10-13 用户口径）。
    """
    plain: list[Path] = []
    marked: list[Path] = []
    for image in images:
        (marked if is_marked(Path(image).parent) else plain).append(Path(image))
    return plain, marked


def copies_dir() -> Path:
    """透明底副本的缓存根：``singletask/imposition/rembg_transparent/``。"""
    from desktop.utils.files import singletask_dir

    return singletask_dir(_IMPOSITION_DISK_KEY) / _COPIES_SUBDIR


def transparent_copy_path(source) -> Path:
    """一张白底图对应的**透明底副本**缓存路径（只算路径，不落盘）。

    文件名带**源指纹**（名字 + 大小 + mtime）：源图被编辑覆盖过 ⇒ 指纹变
    ⇒ 得到新副本路径，旧副本自然弃用（与页面缩略图实体同一套失效思路）。
    """
    path = Path(source)
    stat = path.stat()
    fingerprint = f"{path.name}|{stat.st_size}|{stat.st_mtime_ns}"
    digest = hashlib.md5(fingerprint.encode("utf-8")).hexdigest()[:8]
    return copies_dir() / f"{path.stem}-{digest}.png"


def make_transparent_copy(source, target) -> None:
    """把一张白底图转成**透明底 PNG** 写到 ``target``（原图绝不动）。

    判据与编码复用 ``utils.save_white_as_transparent``：像素全白的点 α=0
    （RGB 保持 255），其余逐位不变。输入若是带 alpha 的 RGBA，先按白底
    压平再判——去底导出恒为白底图，这里只是兜底。
    """
    import numpy as np
    from PIL import Image

    import utils

    with Image.open(source) as im:
        im.load()
        rgb = im.convert("RGB")
    utils.save_white_as_transparent(np.asarray(rgb), Path(target))


__all__ = [
    "MARKER_NAME",
    "copies_dir",
    "is_marked",
    "make_transparent_copy",
    "marker_path",
    "split_marked",
    "transparent_copy_path",
    "write_marker",
]
