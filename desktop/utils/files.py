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
    """GUI 数据根目录：用户文档目录下的 guji。"""
    return Path.home() / "Documents" / "guji"


def project_root() -> Path:
    """项目根目录（`desktop` 包的上一级）。

    源码模式下 worker 子进程用 `-m desktop.worker` 启动，工作目录必须是
    能解析出 `desktop` 包的那一级；用本函数取，避免依赖某个文件的层数
    （文件挪一层就会算错）。
    """
    return Path(__file__).resolve().parents[2]


def file_hash(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """流式计算文件 SHA-256（分块读取，避免大 PDF 撑爆内存）。"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def natural_key(name: str):
    """生成自然排序键：数字段按整数、其余转小写，使 2 排在 10 前。"""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]


def list_stage_images(directory: Path) -> list[Path]:
    """某阶段输出目录中的图片（自然排序）。"""
    if not directory.exists():
        return []
    return sorted(
        (f for f in directory.iterdir() if f.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda f: natural_key(f.name),
    )
