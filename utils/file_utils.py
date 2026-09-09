"""文件系统辅助函数：图片文件收集与尺寸校验。

提供以下功能：
- `collect_image_files`: 从文件或目录收集图片，按自然排序返回；
- `is_valid_image_size`: 校验文件大小，过滤异常小文件；
- `IMAGE_EXTS`: 支持的图片扩展名集合。
"""

from pathlib import Path
from typing import List
from .sort_utils import natural_sort_key

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
