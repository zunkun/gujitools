# -*- coding: utf-8 -*-
"""「白底 → 透明底」的 PNG 编码：**唯一实现**。

只作用于第三步「提交本次任务」写出的最终图片（``stages/rembg/*.png``），
不碰去底产物本身、也不碰 PDF。

为什么值得单独一个模块
----------------------
这个规则同时决定两件容易漂移的事：**哪些像素算白底**、**用哪种编码最省空间**。
散在调用方（``desktop/stages/rembg_stage.py``）里，下一处再要透明 PNG 就会
各抄一份、判据各写一套。

编码形态与实测（5000×4400 仿古籍页，见
``.workbuddy/perf/bench_transparent_submit_2026-09-30.py``）：

===========================  ==============  =========  ==================
页内容                        编码形态         体积        对比旧写法
                          （PNG 头）                   （Qt 直存 RGB24）
===========================  ==============  =========  ==================
纯黑白（type=1/2，主流）      位深 1 调色板    0.011MB     6.7× 小、3.2× 快
灰度（type=3）               位深 2~8 调色板  0.015MB     5× 小、3.3× 快
彩色（sealcolor 印章原色）    RGBA8          0.095MB     体积略增（必须无损）
===========================  ==============  =========  ==================

三条硬约定（改动前先读）
------------------------
1. **判据只看像素，不看 ``type`` 参数**。提交阶段的图是「去底预览图经
   ``compose_region_output`` 合成」出来的 Qt ``Format_RGB32``，而面板的
   ``type`` 与预览可能不同步（改了参数没重新生成预览也能提交）——按像素
   判定才不会写错。
2. **透明像素的 RGB 保持 255，不清零**。第四步缩略图是 JPEG，Qt 丢 α 时直接
   取 RGB；清零就会把缩略图显示成黑底（``tools/make_icon.py`` 里那套
   「清零防预乘淡边」的做法在这里**不适用**）。
3. ⚠️ PIL 的 ``save(mode="P", transparency=N)`` 里 N 是**首个透明项的调色板
   下标**（实现为写 ``b"\\xff"*N + b"\\x00"`` 再按调色板项数截断），不是灰度
   值：传 255 而调色板只有 2 项 → tRNS 变成 ``[255, 255]``，**一个透明项都
   没写进去**，而且不报错。位深不用手写：不传 ``bits`` 时 PIL 按调色板项数
   自动取 1/2/4/8。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

#: 「白底」判据：三通道都等于它才算白（去底输出与合成画布的白恒为 255，
#: 不是"接近白"——见 utils.image_utils.apply_otsu_whole 的 np.full(..., 255)
#: 打底与 desktop.workers.preview_worker.compose_region_output 的 fill(白)）。
WHITE_LEVEL = 255

#: 产物 PNG 的压缩级别。与去底产物（functions.rembg.PNG_SAVE_KWARGS）同取 6：
#: 编码占单页耗时大头，level=9+optimize 换来的体积收益不值那个时间。
PNG_COMPRESS_LEVEL = 6

#: 灰度值的可能取值数（0~255），调色板路径用不到这么多项时会建紧凑调色板。
_GRAY_LEVELS = 256

#: 灰度值种类 ≤ 这个数才建「紧凑调色板」（索引连续 → PIL 自动选 1/2/4 位深）。
#: 超过就退回恒等调色板（索引 == 灰度值，恒 8 位深、256 项），省去一次重映射。
_COMPACT_PALETTE_MAX = 16


def save_white_as_transparent(
    rgb: np.ndarray,
    path: str | Path,
    *,
    compress_level: int = PNG_COMPRESS_LEVEL,
) -> dict:
    """把「白底图」写成白底透明的 PNG，自动选最省的编码形态。

    参数:
        rgb: (H, W, 3) 的 RGB 数组（``uint8``）；多于 3 通道时只用前 3 个。
        path: 输出 PNG 路径（调用方负责目录已存在）。
        compress_level: PNG 压缩级别（0~9）。

    返回:
        ``{"encoding": "P"|"RGBA", "colors": int|None, "bits": int, "bytes": int}``，
        供调用方打日志/统计；失败会直接抛异常（不静默降级成白底）。
    """
    arr = np.asarray(rgb)
    if arr.ndim != 3 or arr.shape[2] < 3:
        raise ValueError(f"save_white_as_transparent 需要 (H, W, 3) 的 RGB 数组，收到 {arr.shape}")
    arr = arr[:, :, :3]

    # 判据（唯一处）：灰阶页走调色板（体积最小），彩色页（印章原色）必须 RGBA
    route, levels = _classify(arr)
    if route == "P":
        assert levels is not None
        return _save_gray_palette(arr[:, :, 2], levels, Path(path), compress_level)
    return _save_rgba(arr, Path(path), compress_level)


def _classify(arr: np.ndarray) -> tuple[str, Optional[np.ndarray]]:
    """像素判据（唯一定义处）→ ``("P", 出现的灰度值升序)`` 或 ``("RGBA", None)``。

    ⚠️ 只看像素、不看 ``type`` 参数：提交阶段的图是「去底预览图经
    ``compose_region_output`` 合成」出来的，而面板 ``type`` 与预览可能不同步
    （改了参数不重新生成预览也能提交）。按像素判定才不会写错。
    """
    if (
        np.array_equal(arr[:, :, 0], arr[:, :, 1])
        and np.array_equal(arr[:, :, 1], arr[:, :, 2])
    ):
        counts = np.bincount(arr[:, :, 2].reshape(-1), minlength=_GRAY_LEVELS)
        return "P", np.nonzero(counts)[0]
    return "RGBA", None


def _save_gray_palette(
    gray: np.ndarray, levels: np.ndarray, path: Path, compress_level: int
) -> dict:
    """灰阶图 → 调色板 PNG（白项透明，PIL 按调色板项数自动选位深）。"""
    n = int(levels.size)

    if n <= _COMPACT_PALETTE_MAX:
        # 紧凑调色板：索引从 0 连续编号（PIL 据此自动选 1/2/4 位深）
        lut = np.zeros(_GRAY_LEVELS, np.uint8)
        lut[levels] = np.arange(n, dtype=np.uint8)
        index = lut[gray]
        palette_levels = levels
        white_index = int(np.searchsorted(levels, WHITE_LEVEL))
        has_white = white_index < n and int(levels[white_index]) == WHITE_LEVEL
    else:
        # 恒等调色板：索引 == 灰度值本身（省一次重映射，恒 8 位深）。
        # ⚠️ 显式连续化：调用方传进来的是 ``[:, :, 2::-1]`` 负步长视图，直接交给
        # PIL 也能对（它会 tobytes），但那样就依赖 PIL 内部的隐式复制了。
        index = np.ascontiguousarray(gray)
        palette_levels = np.arange(_GRAY_LEVELS, dtype=np.uint8)
        white_index = WHITE_LEVEL
        has_white = True  # 恒等调色板必然有 255 号项（白底页一定用到）

    image = Image.fromarray(index, "P")
    image.putpalette([int(v) for level in palette_levels for v in (level, level, level)])
    image.save(
        path,
        format="PNG",
        compress_level=compress_level,
        **({"transparency": white_index} if has_white else {}),
    )
    return {
        "encoding": "P",
        "colors": n,
        "bits": _palette_bits(n),
        "bytes": path.stat().st_size,
    }


def _save_rgba(rgb: np.ndarray, path: Path, compress_level: int) -> dict:
    """彩色图 → RGBA8 PNG（白底 α=0；透明区 RGB 保留 255）。"""
    white = (
        (rgb[:, :, 0] == WHITE_LEVEL)
        & (rgb[:, :, 1] == WHITE_LEVEL)
        & (rgb[:, :, 2] == WHITE_LEVEL)
    )
    # np.where 而不是就地清零：透明像素的 RGB 必须是 255（见模块 docstring 约定 2）
    alpha = np.where(white, 0, 255).astype(np.uint8)
    Image.fromarray(np.dstack([rgb, alpha]), "RGBA").save(
        path, format="PNG", compress_level=compress_level
    )
    return {
        "encoding": "RGBA",
        "colors": None,
        "bits": 32,
        "bytes": path.stat().st_size,
    }


def _palette_bits(colors: int) -> int:
    """调色板项数 → 实际位深（与 PIL 的自动选择算法一致）。"""
    if colors <= 2:
        return 1
    if colors <= 4:
        return 2
    if colors <= 16:
        return 4
    return 8


def describe_encoding(rgb: np.ndarray) -> Optional[dict]:
    """只算编码形态、不落盘（日志/护栏用，判据与 ``save_white_as_transparent`` 同源）。"""
    arr = np.asarray(rgb)
    if arr.ndim != 3 or arr.shape[2] < 3:
        return None
    route, levels = _classify(arr[:, :, :3])
    if route == "P":
        assert levels is not None
        return {"encoding": "P", "colors": int(levels.size),
                "bits": _palette_bits(int(levels.size))}
    return {"encoding": "RGBA", "colors": None, "bits": 32}
