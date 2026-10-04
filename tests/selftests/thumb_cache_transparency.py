# -*- coding: utf-8 -*-
"""缩略图「透明被压黑」修复自测。

用户 2026-10-04 报「拼板左列缩略图全是黑的」：去底色（rembg）产物是
**调色板 PNG、白底被标记为透明**（tRNS），Qt 解码后透明像素 RGB=0；而
缩略图缓存是无 alpha 通道的 **JPEG**——直接编码把"透明 = 黑"固化成纯黑
图（实测一张 256px 坏缓存只有 1331 字节、全图 (0,0,0)）。

修复：:func:`flatten_on_white`（产出前一律白底合成）+ :func:`is_all_black`
（历史坏缓存体检、命中重渲自愈）。

断言线：

1. ``flatten_on_white``：带 alpha 的图合成到白底（透明→白、黑块保留）；
   无 alpha 的图**原样返回**（不复制、不换格式，普通照片零成本）；
2. ``is_all_black``：纯黑检出、白底/带内容不误检；
3. **worker 产出物非黑**：对"透明底 + 黑块"的 PNG 真渲染，写出的缓存与
   信号发出的图都不是全黑，且黑块位置仍是黑、空白处是白；
4. **历史坏缓存自愈**：预置全黑缓存（mtime 比源图新，会被 ``cache_usable``
   命中），跑一遍 worker 后缓存被重渲为非黑。

⚠️ 测试源图**现场用 Qt 编码**（不手写字节），源文件放临时目录、绝不碰
用户数据目录。
"""

from __future__ import annotations

import os
import time
from pathlib import Path

NAME = "thumb_cache_transparency"
DEPENDS: list[str] = []
TITLE = "缩略图透明压黑修复"


def run(ctx) -> None:
    import shutil
    import tempfile

    from PySide6.QtGui import QColor, QImage, QPainter

    from desktop.workers.thumb_cache_worker import (
        ImageThumbCacheWorker,
        flatten_on_white,
        is_all_black,
    )
    from tests.selftests._context import ok

    tmp = Path(tempfile.mkdtemp(prefix="guji_thumbflat_"))
    try:
        # ---- 1. flatten_on_white ----
        transparent = QImage(20, 10, QImage.Format.Format_ARGB32)
        transparent.fill(QColor(255, 255, 255, 0))
        flat = flatten_on_white(transparent)
        ok("全透明图合成后没有 alpha 通道", not flat.hasAlphaChannel())
        ok("全透明图合成后是白底",
           flat.pixelColor(5, 5).getRgb()[:3] == (255, 255, 255))

        painted = QImage(20, 10, QImage.Format.Format_ARGB32)
        painted.fill(QColor(255, 255, 255, 0))
        painter = QPainter(painted)
        painter.fillRect(2, 2, 4, 4, QColor(0, 0, 0, 255))
        painter.end()
        flat2 = flatten_on_white(painted)
        ok("透明底 + 黑块 → 白底黑块",
           flat2.pixelColor(3, 3).getRgb()[:3] == (0, 0, 0)
           and flat2.pixelColor(15, 8).getRgb()[:3] == (255, 255, 255))

        opaque = QImage(20, 10, QImage.Format.Format_RGB32)
        opaque.fill(QColor(30, 30, 30))
        ok("无 alpha 的图原样返回（同一对象，不复制）",
           flatten_on_white(opaque) is opaque)

        # ---- 2. is_all_black ----
        black = QImage(20, 10, QImage.Format.Format_RGB32)
        black.fill(QColor(0, 0, 0))
        ok("纯黑图被检出", is_all_black(black))
        ok("白底图不误检", not is_all_black(flat))
        ok("带内容的图不误检", not is_all_black(flat2))
        ok("空图不判黑", not is_all_black(QImage()))

        # ---- 3. worker 真渲染：透明底 PNG 的缓存不是全黑 ----
        # 源图语义与去底色产物一致：整张透明、中央一块黑（"字"）。
        src = tmp / "transparent.png"
        src_img = QImage(200, 120, QImage.Format.Format_ARGB32)
        src_img.fill(QColor(255, 255, 255, 0))
        painter = QPainter(src_img)
        painter.fillRect(60, 30, 80, 60, QColor(0, 0, 0, 255))
        painter.end()
        ok("测试源图（透明底 PNG）已生成", src_img.save(str(src), "PNG"))

        out_dir = tmp / "thumbs"
        first = ImageThumbCacheWorker([src], out_dir, edge=64)
        arrived: list = []
        first.thumbnail_ready.connect(
            lambda i, im, c: arrived.append((i, im, c))
        )
        first.run()
        target = first.cache_path(0)
        ok("缓存已写出", target.exists())
        cached = QImage(str(target))
        ok("缓存不是全黑（透明被压黑已修复）",
           not cached.isNull() and not is_all_black(cached),
           f"size={cached.size()}")
        # 64px 边长下黑块缩到中心 (32,19) 附近；JPG 有损，容忍 ±6
        center = cached.pixelColor(32, 19)
        corner = cached.pixelColor(3, 3)
        ok("缓存里黑块保留（中心仍是黑）", max(center.getRgb()[:3]) < 6,
           f"center={center.getRgb()}")
        ok("缓存里透明处变白（角落是白）", min(corner.getRgb()[:3]) > 250,
           f"corner={corner.getRgb()}")
        ok("信号发出的图同样不是全黑",
           bool(arrived) and not is_all_black(arrived[0][1]))

        # ---- 4. 历史坏缓存自愈 ----
        black_cache = QImage(64, 38, QImage.Format.Format_RGB32)
        black_cache.fill(QColor(0, 0, 0))
        ok("预置全黑缓存已写入", black_cache.save(str(target), "JPG", 80))
        ok("预置缓存确实是全黑", is_all_black(QImage(str(target))))
        # 源图 mtime 拨早 ⇒ 缓存 mtime 更新 ⇒ cache_usable 命中 ⇒ 走体检路径
        old = time.time() - 3600
        os.utime(src, (old, old))
        retry = ImageThumbCacheWorker([src], out_dir, edge=64)
        again: list = []
        retry.thumbnail_ready.connect(
            lambda i, im, c: again.append((i, im, c))
        )
        retry.run()
        healed = QImage(str(target))
        ok("全黑历史缓存被重渲自愈", not is_all_black(healed))
        ok("自愈后内容与首次渲染一致（角落是白）",
           min(healed.pixelColor(3, 3).getRgb()[:3]) > 250)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
