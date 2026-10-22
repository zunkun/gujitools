# -*- coding: utf-8 -*-
"""实体图片 PNG 的**无损紧凑编码**：唯一实现。

为什么需要它（2026-10-14 用户报障）
-----------------------------------
「去底色 / 提交产物」本来就是最省空间的编码形态，而编辑器的「完成」把结果
写回底片时走 ``QImage.save(..., "PNG")``：画布上的图是 **ARGB32**（32 位/
像素），Qt 于是整幅按 8 位 RGBA（PNG color type 6）重编码——**逐像素无损，
但"最省形态"没了**。同一页在用户机器上的实测：

=========================================  =========  =======================
文件（2400×2374 左右的书页）                体积       PNG 头
=========================================  =========  =======================
``rembg/10.png``（白底灰阶，去底色中间态）   201 KB     bits=8 type=0(gray)
``rembg/10-l.png``（透明底二值，**没编辑**）   70 KB      bits=1 type=3(P)+tRNS
``rembg/10-r.png``（**同一页，编辑过**）       7.6 MB     bits=8 type=6(RGBA)
=========================================  =========  =======================

105 倍。与"质量"无关（PNG 无损），纯粹是**编码形态**：二值透明页只要
1 位/像素 + 一个 tRNS 表，而 RGBA 是 32 位/像素。

修法
----
不降质量、不顺色，而是**按像素重新挑最省的形态**（每条都逐像素无损）：

=================================  ====================  ==========
像素实况                            输出                   每像素
=================================  ====================  ==========
灰阶、不透明                          P（灰阶调色板）        1/2/4/8 位
灰阶 + 透明，(灰,α) 组合 ≤ 256        P（+tRNS 表）          1/2/4/8 位
彩色，唯一 (RGB[, A]) ≤ 256           P（+tRNS 表）          1/2/4/8 位
灰阶 + 透明，但 (灰,α) > 256          LA（灰 + α）           16 位
其余                                RGBA / RGB             32 / 24 位
=================================  ====================  ==========

五条硬约定（改动前先读）
------------------------
1. **判据只看像素**，不看 ``QImage.format()`` / ``PIL.mode``：画布上的图
   恒为 ARGB32，格式名说明不了"这一页到底是不是二值稿"。
2. **逐像素无损**是本模块能被任何调用方拿来替换现存写法的唯一前提。索引形态
   把每个不同的像素四元组整组映射到一个调色板项，``tRNS`` 表逐项带 α；**透明
   项自己的灰度也进调色板**，所以透明像素的 RGB（去底色产物按约定是 255、
   编辑器里可能是 0）**原样保留**，不像"白底转透明"那样带约定。
3. **不透明图绝不写 tRNS**：α 恒 255 时丢掉整条 alpha 才最省，也让
   ``imposition.image_content_bounds`` 的"无 alpha ⇒ 内容＝整张图"判据继续
   成立（写一条全 255 的 tRNS 会让它白算一遍包围盒）。
4. **采样只用于早退**：真彩分支先均匀抽样，**采样就超 256 色** ⇒ 整体必然
   超，直接写真彩，省掉一次 22MP 排序；采样没超**不算数**，还要整体精确统计
   （否则会把"底色均匀但有上千暗部色"的图错当成调色板图）。灰阶分支走
   ``np.bincount``（256 / 65536 个桶，O(pixels)），既不用抽样也不用排序。
5. **dpi 由调用方给**，本模块不猜。覆盖原文件时必须沿用原文件的 pHYs：
   去底色产物是 300 DPI，丢了会让下游 PDF 的物理尺寸判据拿到 72 DPI 默认值。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from PIL import Image

#: 与去底产物（``functions.rembg.PNG_SAVE_KWARGS``）同取 6：编码耗时是大头
#: （22MP 页 level=9+optimize ≈ 2000ms / level=6 ≈ 326ms），只换来 17% 体积。
#: PNG 无损，压缩级别只影响体积/耗时，解码后的像素逐位不变。
PNG_COMPRESS_LEVEL = 6

#: 调色板形态的色彩上限（PNG 索引色硬上限 256）。
MAX_PALETTE_COLORS = 256

#: 真彩早退的采样目标点数（见硬约定 4）。
_SAMPLE_TARGET = 100_000

#: 真彩分支映射下标时的分块大小：``searchsorted`` 的结果是 int64，22MP 一次
#: 算完要多占 176MB，分块后峰值只剩几十 MB。
_MAP_CHUNK = 4_000_000


def save_png_compact(
    rgba,
    path: str | Path,
    *,
    dpi: Optional[Sequence[float]] = None,
    compress_level: int = PNG_COMPRESS_LEVEL,
) -> dict:
    """把 ``(H, W, 4)`` RGBA（或 ``(H, W, 3)`` RGB / ``(H, W)`` 灰度）数组写成
    **尽量省空间**的 PNG，逐像素无损。

    参数:
        rgba: ``uint8`` 数组。四通道按 **RGBA** 顺序（不是 Qt ARGB32 的内存序）。
        path: 输出路径（调用方负责目录已存在，也负责原子写）。
        dpi: ``(x, y)``；``None`` = 不写 pHYs（与"原文件本来就没有"一致）。
        compress_level: PNG 压缩级别（0~9）。

    返回:
        ``{"encoding": "P"|"LA"|"RGBA"|"RGB", "colors": int|None,
        "bits": int, "bytes": int}``，供调用方打日志/统计。
    """
    arr = _as_rgba(rgba)
    plan = _plan(arr)
    target = Path(path)
    extra = {"dpi": (float(dpi[0]), float(dpi[1]))} if dpi else {}

    if plan[0] == "P":
        _, index, palette, trns, bits = plan
        image = Image.fromarray(np.ascontiguousarray(index), "P")
        image.putpalette(palette)
        kwargs = {"format": "PNG", "compress_level": compress_level, **extra}
        if trns is not None:
            kwargs["transparency"] = trns
        image.save(target, **kwargs)
        return {"encoding": "P", "colors": len(palette) // 3, "bits": bits,
                "bytes": target.stat().st_size}

    if plan[0] == "LA":
        stack = np.dstack([arr[:, :, 2], arr[:, :, 3]])
        Image.fromarray(np.ascontiguousarray(stack), "LA").save(
            target, format="PNG", compress_level=compress_level, **extra)
        return {"encoding": "LA", "colors": None, "bits": 16,
                "bytes": target.stat().st_size}

    mode = plan[0]
    data = arr if mode == "RGBA" else arr[:, :, :3]
    Image.fromarray(np.ascontiguousarray(data), mode).save(
        target, format="PNG", compress_level=compress_level, **extra)
    return {"encoding": mode, "colors": None,
            "bits": 32 if mode == "RGBA" else 24,
            "bytes": target.stat().st_size}


def read_png_dpi(path: str | Path) -> Optional[tuple[float, float]]:
    """读回一个已有图片文件的 pHYs（覆盖原文件时沿用，见硬约定 5）。

    读不到（没有 pHYs / 不是图片 / 文件被占）返回 ``None``——调用方按"不写
    pHYs"处理，与"原本就没有"一致（实测提交产物 ``rembg/*-l.png`` 就没有
    pHYs，而 ``rembg/*.png`` 有）。
    """
    try:
        with Image.open(str(path)) as img:
            dpi = img.info.get("dpi")
    except Exception:      # noqa: BLE001 - 读不到就当没有，绝不打断写盘
        return None
    if not dpi:
        return None
    try:
        x, y = float(dpi[0]), float(dpi[1])
    except (TypeError, ValueError, IndexError):
        return None
    if x <= 0 or y <= 0:
        return None
    return x, y


# --------------------------------------------------------------------- 内部

def _plan(arr: np.ndarray):
    """挑编码形态：``("P", index, palette, trns, bits)`` / ``("LA",)`` /
    ``("RGBA",)`` / ``("RGB",)``。"""
    gray = arr[:, :, 2]
    alpha = arr[:, :, 3]
    opaque = bool((alpha == 255).all())

    if _is_gray(arr):
        if opaque:
            # 不透明灰阶：唯一键 = 灰度值本身（8 位桶，恒 ≤256，装得下）
            used = _used(np.bincount(gray.reshape(-1), minlength=256))
            return ("P", _lut(used, 256)[gray], _gray_palette(used),
                    None, _bit_depth(used.size))
        # 灰阶 + 透明：唯一键 = (灰度, α) 两个字节。bincount 只有 65536 个桶，
        # O(pixels) 且不用排序——二值透明页（本模块的主要场景）几乎零开销。
        pair = (gray.astype(np.uint16) << 8) | alpha
        used = _used(np.bincount(pair.reshape(-1), minlength=1 << 16))
        if used.size <= MAX_PALETTE_COLORS:
            palette = _gray_palette((used >> 8).astype(np.uint8))
            trns = bytes(int(v) & 0xFF for v in used.tolist())
            return ("P", _lut(used, 1 << 16)[pair], palette, trns,
                    _bit_depth(used.size))
        return ("LA",)                     # 16 位/像素，仍是 RGBA 的一半

    flat = np.ascontiguousarray(arr).reshape(-1, 4)
    if _sample_too_many(flat):
        return ("RGBA",) if not opaque else ("RGB",)
    keys = _pack_keys(flat)
    uniq = np.unique(keys)
    if uniq.size > MAX_PALETTE_COLORS:
        return ("RGBA",) if not opaque else ("RGB",)
    palette = bytearray()
    trns = bytearray()
    for key in uniq.tolist():
        palette += bytes((key & 0xFF, (key >> 8) & 0xFF, (key >> 16) & 0xFF))
        trns.append((key >> 24) & 0xFF)
    index = _map_chunked(uniq, keys).reshape(arr.shape[:2])
    return ("P", index, bytes(palette), None if opaque else bytes(trns),
            _bit_depth(uniq.size))


def _as_rgba(arr) -> np.ndarray:
    """灰度 / RGB / RGBA 的 ``uint8`` 数组 → ``(H, W, 4)`` RGBA。"""
    a = np.asarray(arr)
    if a.dtype != np.uint8:
        raise ValueError(f"save_png_compact 需要 uint8 数组，收到 {a.dtype}")
    if a.ndim == 2:
        out = np.empty(a.shape + (4,), np.uint8)
        out[:, :, 0] = out[:, :, 1] = out[:, :, 2] = a
        out[:, :, 3] = 255
        return out
    if a.ndim != 3 or a.shape[2] not in (3, 4):
        raise ValueError(
            f"save_png_compact 需要 (H,W)/(H,W,3)/(H,W,4)，收到 {a.shape}")
    if a.shape[2] == 4:
        return np.ascontiguousarray(a)
    out = np.empty(a.shape[:2] + (4,), np.uint8)
    out[:, :, :3] = a
    out[:, :, 3] = 255
    return out


def _is_gray(arr: np.ndarray) -> bool:
    """三通道逐像素相等（透明白与不透明黑都算灰阶）。"""
    return bool(np.array_equal(arr[:, :, 0], arr[:, :, 2])
                and np.array_equal(arr[:, :, 1], arr[:, :, 2]))


def _used(counts: np.ndarray) -> np.ndarray:
    """直方图 → **出现过**的键（升序，即调色板索引 0..n-1）。"""
    return np.nonzero(counts)[0]


def _lut(keys: np.ndarray, size: int) -> np.ndarray:
    """取值 → 索引 的查找表（``size`` = 取值空间大小，256 或 65536）。"""
    table = np.zeros(size, np.uint8)
    table[keys] = np.arange(keys.size, dtype=np.uint8)
    return table


def _pack_keys(flat: np.ndarray) -> np.ndarray:
    """``(N, 4)`` 的 RGBA 字节视图 → ``(N,)`` ``uint32``（r 在最低字节）。

    ⚠️ 刻意**显式移位**而不是 ``flat.view(np.uint32)``：后者把字节序写死进了
    调色板取色的方式（大端机器上 r/a 会互换），显式打包则与端序无关。
    几个 ``astype`` 都在 O(pixels) 上，真彩分支本来就是少数派。
    """
    key = flat[:, 3].astype(np.uint32)
    key <<= 8
    key |= flat[:, 2]
    key <<= 8
    key |= flat[:, 1]
    key <<= 8
    key |= flat[:, 0]
    return key


def _sample_too_many(flat: np.ndarray) -> bool:
    """均匀抽样看唯一值是否**已经**超过上限（只用于早退，见硬约定 4）。"""
    total = flat.shape[0]
    if total <= _SAMPLE_TARGET:
        return False
    step = int(np.ceil(total / float(_SAMPLE_TARGET)))
    return np.unique(_pack_keys(flat[::step])).size > MAX_PALETTE_COLORS


def _map_chunked(keys: np.ndarray, values: np.ndarray) -> np.ndarray:
    """把取值映射成 ``keys``（升序）里的下标；分块做，压住 int64 的峰值。"""
    index = np.empty(values.shape[0], np.uint8)
    for start in range(0, values.shape[0], _MAP_CHUNK):
        stop = min(start + _MAP_CHUNK, values.shape[0])
        index[start:stop] = np.searchsorted(keys, values[start:stop])
    return index


def _gray_palette(levels: np.ndarray) -> bytes:
    """灰阶调色板（R=G=B=灰度值）。"""
    return bytes(b for level in levels.tolist() for b in (level, level, level))


def _bit_depth(colors: int) -> int:
    """调色板项数 → 实际位深（与 PIL ``_save`` 的自动选择一致：``colors <= 16``
    时按 ≤2→1 位、≤4→2 位、≤16→4 位，其余 8 位）。"""
    if colors <= 2:
        return 1
    if colors <= 4:
        return 2
    if colors <= 16:
        return 4
    return 8
