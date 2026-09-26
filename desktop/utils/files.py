# -*- coding: utf-8 -*-
"""文件与目录相关的通用工具：哈希、自然排序、阶段输出清单、预览缓存键。"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import threading
from pathlib import Path

from utils.file_utils import replace_with_retry

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


def package_dir() -> Path:
    """`desktop` 包目录（源码与 PyInstaller 打包两种模式下都可用）。

    打包后 `desktop` 作为 PYZ 内的字节码存档存在，磁盘上没有真正的
    ``desktop/static/icon.png``；数据文件由 spec 的 ``datas`` 额外落到
    ``_internal/desktop/``，因此 frozen 下直接指向 ``sys._MEIPASS``。
    """
    import sys

    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "desktop"
    return Path(__file__).resolve().parents[1]


def file_hash(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """流式计算文件 SHA-256（分块读取，避免大 PDF 撑爆内存）。"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def copy_file_atomic(source: Path, target: Path) -> Path:
    """把 source 复制到 target，**要么没有、要么完整**。

    ⚠️ 不能用裸 ``shutil.copy2(source, target)``：导入后的复制是在**后台
    线程**里跑的，而详情页/PDF 预览随时会来看任务目录里的副本。直接往
    target 写，复制途中它就 ``is_file() == True`` 了，读到的却是半截
    PDF——渲染失败、甚至静默出一张残缺页。

    所以先写同目录的临时文件，落盘后再 ``os.replace`` 原子改名。临时名带
    .part 后缀，``glob("*.pdf")`` 之类的兜底查找也扫不到它。

    ⚠️ 临时名里要带 **pid + 线程号**：同一个副本可能被两个地方同时复制
    （后台队列复制中，用户已经点进详情页 → ``ensure_source_copy`` 又复制
    一遍）。共用一个临时名的话两边会交叉写同一个文件；各自写自己的临时
    文件则内容相同，谁最后 replace 都对。
    """
    # ⚠️ 临时名 = 原名截断 + pid/tid + .part：NTFS 单个文件名上限 255 字符，
    # 长书名（如《长短经.九卷.唐.赵蕤.撰.南宋时期杭州净戒院刊本…》这类古籍
    # 文件名本身就 100+ 字符）再加 pid/tid 后缀就会超限，copy2 直接报
    # 「系统找不到指定的路径」。把名字部分截到安全长度（pid/tid/part 约
    # 占 40 字符），截断后的前缀 + pid/tid 仍能保证两个并发复制不重名——
    # 同名前缀 + 不同 pid/tid 组合出的临时名彼此不同。
    _stem = target.stem[: 255 - 45 - len(target.suffix)]
    temp = target.with_name(
        f"{_stem}.{os.getpid():x}{threading.get_ident():x}{target.suffix}.part"
    )
    try:
        shutil.copy2(source, temp)
    except OSError:
        # 失败别留下半截临时文件，否则会被当成"下次可复用"
        try:
            temp.unlink()
        except OSError:
            pass
        raise
    replace_with_retry(temp, target)  # Windows 上读者会让 os.replace 抛 PermissionError
    return target


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
