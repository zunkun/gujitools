# -*- coding: utf-8 -*-
"""待打印图片清单的收集与页序推导。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from utils.sort_utils import natural_sort_key


def _collect_image_files(input_dir: Path, files: Optional[List[str]] = None) -> List[str]:
    """收集待打印图片，返回**按最终页序排列**的路径列表。

    页序规则（二选一）：
    - ``files`` 非空：直接采用该清单顺序（GUI 第四步的列表顺序，即
      ``print.json`` 的 pages 数组序）。**不再解析文件名**——文件名只是
      标识，顺序完全由数据层决定，拖拽重排无需改动任何物理文件。
    - ``files`` 为空：退回 CLI 独立用法——扫描目录并按
      ``natural_sort_key``（cover/menu 优先、同编号 r→l、数字自然序）
      推导顺序。

    清单中不存在的路径会被跳过（让「数据表里有记录但物理文件已删」的条目失效
    而不是整次打印失败），但**会明确报出跳过了几张**——否则用户看到的只是
    PDF 页数变少，完全不知道是清单和磁盘对不上。

    ⚠️ 三处健壮性（2026-09-26 审计）：
      1. `files` 是字符串时（YAML 写错类型）以前会被**逐字符迭代**，得到一堆
         单字符路径、全部静默跳过 → 现在直接拒绝；
      2. 相对路径以前按**当前工作目录**解析——清单里的相对路径应当相对
         `input_dir`（数据表与图片目录是一起搬的），否则换台机器就全找不到；
      3. 输入是**单个图片文件**时 `os.listdir` 会抛 `NotADirectoryError`
         （未处理）→ 现在按单文件处理。
    """
    if files is not None and not isinstance(files, (list, tuple)):
        raise ValueError(
            f"files 应为图片路径清单（数组），当前是 {type(files).__name__}：{files!r}"
        )
    if files:
        out = []
        missing = 0
        for text in files:
            p = Path(str(text))
            if not p.is_absolute():
                # 相对路径按输入目录解析（清单与图片是一起搬的）
                p = (input_dir if input_dir.is_dir() else input_dir.parent) / p
            if p.is_file():
                out.append(str(p))
            else:
                missing += 1
        if missing:
            print(f"⚠️ 清单里有 {missing}/{len(files)} 张图片在磁盘上不存在，已跳过")
        return out
    if input_dir.is_file():
        # 单个图片文件当输入：直接就是这一页（以前会 NotADirectoryError 崩掉）
        return [str(input_dir)]
    if not input_dir.is_dir():
        return []
    image_files = []
    for name in os.listdir(input_dir):
        if name.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
            image_files.append(os.path.join(str(input_dir), name))
    image_files.sort(key=natural_sort_key)
    return image_files
