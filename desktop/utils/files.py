# -*- coding: utf-8 -*-
"""文件与目录相关的通用工具：哈希、自然排序、阶段输出清单、预览缓存键。"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

# 页缩略图（thumbnails/source 等）的最长边；256px 保证 area=1 半幅裁剪后仍清晰
THUMBNAIL_EDGE = 256


def guji_data_dir() -> Path:
    return Path.home() / "Documents" / "guji"


def file_hash(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def natural_key(name: str):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]


def list_stage_images(directory: Path) -> list[Path]:
    """某阶段输出目录中的图片（自然排序）。"""
    if not directory.exists():
        return []
    return sorted(
        (f for f in directory.iterdir() if f.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda f: natural_key(f.name),
    )
