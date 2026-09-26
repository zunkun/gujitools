"""文件系统辅助函数：图片文件收集与尺寸校验。

提供以下功能：
- `collect_image_files`: 从文件或目录收集图片，按自然排序返回；
- `is_valid_image_size`: 校验文件大小，过滤异常小文件；
- `IMAGE_EXTS`: 支持的图片扩展名集合。
"""

from pathlib import Path
from typing import List
from utils.sort_utils import natural_sort_key

# 支持的图片扩展名（小写比较，不含 . 号）
# 用于 collect_image_files 中的扩展名过滤
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}


def collect_image_files(input_path: Path, is_file: bool) -> List[Path]:
    """收集输入路径下的所有图片文件，按自然排序返回。

    参数:
        input_path: 输入路径（文件或目录）。
        is_file: True 表示输入为单文件，False 表示输入为目录。

    返回:
        图片 Path 列表，按自然排序（cover → page1 → page2 → page10）。

    异常:
        ValueError: 输入为文件但扩展名不在 IMAGE_EXTS 中。
    """
    if is_file:
        if input_path.suffix.lower() in IMAGE_EXTS:
            return [input_path]
        raise ValueError(f"输入文件不是图片: {input_path}")
    # 遍历目录，筛选支持的图片扩展名
    files = [p for p in input_path.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    # 自然排序：封面优先，数字按数值排序
    files.sort(key=lambda p: natural_sort_key(p.name))
    return files


def is_valid_image_size(path: Path, min_size: int = 100) -> bool:
    """校验文件大小是否大于最小阈值。

    用于快速过滤异常小文件（下载不完整、占位符等），避免进入图像处理流水线。

    参数:
        path: 文件路径。
        min_size: 最小文件大小（字节），默认 100。

    返回:
        True = 文件大小合格，False = 文件过小。
    """
    return path.stat().st_size >= min_size


def replace_with_retry(source, target, attempts: int = 6, delay: float = 0.05) -> None:
    """`os.replace`，但在 Windows 上**短暂重试**。

    为什么必须重试（2026-09-26 审计实测）
        Windows 的 `os.replace` 走 `MoveFileEx(REPLACE_EXISTING)`，**目标文件只要
        还被别的句柄打开就会失败**（哪怕对方只是在读）：
        `PermissionError: [WinError 5] 拒绝访问`。
        实测场景：一边并发写 `tasks.json`、一边读它 —— 8 个写线程里就有 2 个当场
        撞上。这不是代码写错，是 Windows 的共享语义（POSIX 上 rename 不受读者影响），
        所以只能重试。争用窗口只有毫秒级，几次重试足够；真占用（PDF 被阅读器打开）
        重试完仍会抛，由调用方给用户看得懂的话。

    参数:
        source: 已写好的临时文件（同目录，保证同一卷）。
        target: 目标路径。
        attempts: 最多尝试次数（含第一次）。
        delay: 每次重试之间的等待秒数。

    抛出:
        最后一次的 OSError（重试仍失败时）。
    """
    import os
    import time

    for attempt in range(1, max(1, attempts) + 1):
        try:
            os.replace(source, target)
            return
        except OSError:
            if attempt >= attempts:
                raise
            time.sleep(delay)


def write_bytes_atomic(path, data: bytes) -> None:
    """原子写字节：先写同目录临时文件，再替换到目标名。

    ⚠️ 缩略图缓存**必须**这么写（2026-09-26 审计）：缓存是否可用的判据是
    ``缓存文件.mtime >= 源 PDF.mtime``（`source_thumbnails_worker._render_page`）。
    直接 `write_bytes` 的话，写到一半被 kill/断电留下的**截断 JPEG**，
    它的 mtime 必然比源文件新 → 会被**永久**当成有效缓存，预览区长期显示半截/
    损坏图，而且**没有任何自愈路径**（因为判断"要不要重渲"时看的就是 mtime）。
    原子写则保证目标名下要么不存在、要么是完整内容；被 kill 时只留一个
    `.part`（不匹配 `*.jpg`，也不会被当成缓存命中）。
    """
    from pathlib import Path as _Path

    import os as _os

    target = _Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.part")
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        _os.fsync(handle.fileno())
    replace_with_retry(tmp, target)
