# -*- coding: utf-8 -*-
"""实体 PNG 紧凑编码自测：编辑回写不再让底片体积暴涨。

背景（2026-10-14 用户报障）：去底色实体图轻微编辑后「应用」，文件从 200K
涨到 5M。两个叠加的原因，本用例分别钉死：

1. ``overwrite_image_file`` 把 **JPEG 的 quality 传给了 PNG**，Qt 把它当
   "反过来的压缩级别" ⇒ 95 = 几乎不压缩（实测同一页 7.59 MB）；
2. 即使不传 quality，Qt 也只按 ``QImage.format()`` 写 8 位 RGBA，而这一页
   的天然形态是「1 位调色板 + tRNS」（同一页 70 KB）。

断言线：

1. 编码形态按**像素**挑：二值透明页 → ``P``/1 位/tRNS；白底灰阶 → ``P``/1 位
   且**不写 tRNS**；少色真彩 → ``P``；真彩噪声 → RGBA；灰阶+软 alpha 组合
   超 256 → LA；
2. **逐像素无损**：五条路径全部与输入 RGBA 逐像素相等；
3. **dpi 跟着原文件走**：覆盖前读原图 pHYs，覆盖后仍然是它；
4. **覆盖原图（PNG）体积回到紧凑量级**，且头里就是调色板 —— 这一条是本用例
   的主断言（改前同一张图是 600×480×4 ≈ 1.15 MB 的 RGBA 未压缩数据）；
5. **后台应用链（``_apply_job``）也走紧凑编码**：它就是用户点「完成」后真正
   写底片的那条路（工作线程里 compose + 原子覆盖），不能只有同步路被修好；
6. **颜色通道序不能错**：``_qimage_rgba_array`` 走 RGBA8888，红图不能读回蓝图；
7. 写盘失败不留 ``*.part``（沿用既有约定）。
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional

NAME = "png_compact"
DEPENDS: list[str] = []
TITLE = "实体 PNG 紧凑编码（编辑回写不再膨胀）"


def _png_header(path: Path) -> tuple[int, int, int, int, bool]:
    """``(宽, 高, 位深, 颜色类型, 有没有 tRNS)``。颜色类型 3 = 调色板。"""
    with open(path, "rb") as handle:
        data = handle.read(4096)
    width, height, depth, ctype = struct.unpack(">IIBB", data[16:26])
    return width, height, depth, ctype, b"tRNS" in data


def _dpi_is(got: Optional[tuple[float, float]], want: float = 300.0) -> bool:
    """pHYs 存的是"每米像素数"的整数，读回来必然有 0.001 级的舍入误差。"""
    return (got is not None and abs(got[0] - want) < 0.01
            and abs(got[1] - want) < 0.01)


def _binary_page():
    """造一张「去底色后的二值透明页」：黑字 + 透明白底。"""
    import numpy as np

    gray = np.full((600, 480), 255, np.uint8)
    gray[40:560:28, 30:450] = 0
    alpha = np.where(gray == 255, 0, 255).astype(np.uint8)
    return np.dstack([gray, gray, gray, alpha])


def run(ctx) -> None:
    import numpy as np
    from PIL import Image
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QTransform

    from desktop.components.viewers.image_zoom_dialog import (
        overwrite_image_file, save_image,
    )
    from tests.selftests._context import ok
    from tests.tmpdir import temp_dir
    from utils.compact_png import read_png_dpi, save_png_compact

    tmp = temp_dir("png_compact_")
    rng = np.random.default_rng(20261014)

    def write_and_reread(arr, name):
        path = tmp / name
        info = save_png_compact(arr, path)
        with Image.open(path) as img:
            back = np.array(img.convert("RGBA"))
        return path, info, back

    # ---------------------------------------------------------- 1. 形态选择
    page = _binary_page()
    path, info, back = write_and_reread(page, "binary.png")
    _, _, depth, ctype, has_trns = _png_header(path)
    ok("二值透明页 → 1 位调色板 + tRNS",
       (info["encoding"], info["bits"], ctype, depth, has_trns)
       == ("P", 1, 3, 1, True),
       f"info={info} ctype={ctype} depth={depth} tRNS={has_trns}")
    ok("二值透明页逐像素无损",
       back.shape == page.shape and bool((back == page).all()),
       f"{back.shape} vs {page.shape}")
    ok("二值透明页体积是个位数 KB（600×480 原始像素 1.15MB）",
       info["bytes"] < 20_000, f"{info['bytes']} 字节")

    gray_opaque = np.dstack([page[:, :, 2]] * 3)
    path, info, back = write_and_reread(gray_opaque, "gray_opaque.png")
    _, _, depth, ctype, has_trns = _png_header(path)
    ok("白底灰阶 → 调色板且不写 tRNS（不透明图不该带 alpha 信息）",
       (info["encoding"], ctype, depth, has_trns) == ("P", 3, 1, False),
       f"info={info} ctype={ctype} tRNS={has_trns}")
    ok("白底灰阶逐像素无损",
       bool((back == np.dstack(
           [gray_opaque, np.full((600, 480), 255, np.uint8)])).all()))

    few_colors = np.zeros((64, 64, 4), np.uint8)
    few_colors[...] = (200, 30, 30, 255)
    few_colors[::2, ::2] = (0, 0, 0, 255)
    few_colors[:8, :8] = (0, 0, 0, 0)
    path, info, back = write_and_reread(few_colors, "few_colors.png")
    _, _, _depth, ctype, has_trns = _png_header(path)
    ok("少色真彩（含透明）→ 调色板 + tRNS",
       (info["encoding"], ctype, has_trns) == ("P", 3, True), str(info))
    ok("少色真彩逐像素无损", bool((back == few_colors).all()))

    photo = np.dstack([rng.integers(0, 256, (64, 64, 3), dtype=np.uint8),
                       np.full((64, 64), 255, np.uint8)])
    path, info, back = write_and_reread(photo, "photo.png")
    ok("真彩噪声 → 老实走真彩（不硬塞调色板），且不透明时不带 alpha 通道",
       info["encoding"] == "RGB", str(info))
    ok("真彩噪声逐像素无损", bool((back == photo).all()))

    gray_soft = rng.integers(0, 256, (128, 128), dtype=np.uint8)
    soft = np.dstack([gray_soft] * 3 + [
        rng.choice(np.array([0, 128, 255], np.uint8), (128, 128))])
    path, info, back = write_and_reread(soft, "soft_alpha.png")
    ok("灰阶+软 alpha 组合超 256 → LA（16 位/像素，仍是 RGBA 的一半）",
       info["encoding"] == "LA", str(info))
    ok("软 alpha 逐像素无损", bool((back == soft).all()))

    # ---------------------------------------------------------- 2. dpi
    path = tmp / "dpi.png"
    save_png_compact(page, path, dpi=(300, 300))
    ok("写盘带 pHYs 时读得回（300 DPI 不丢）",
       _dpi_is(read_png_dpi(path)), str(read_png_dpi(path)))
    path2 = tmp / "nodpi.png"
    save_png_compact(page, path2)
    ok("不传 dpi 就不写 pHYs（与原文件本来就没有保持一致）",
       read_png_dpi(path2) is None, str(read_png_dpi(path2)))

    # --------------------------------------- 3. 覆盖原图：用户报障的那条路
    target = tmp / "0001-r.png"
    save_png_compact(page, target, dpi=(300, 300))
    before = target.stat().st_size
    arr = np.array(Image.open(target).convert("RGBA"))
    arr[:, :, :3] = np.where(arr[:, :, 3:4] > 0, 0, 255)     # 轻微编辑：全黑
    edited = QImage(arr.tobytes(), arr.shape[1], arr.shape[0],
                    arr.shape[1] * 4, QImage.Format.Format_RGBA8888).copy()
    ok("覆盖原图成功", overwrite_image_file(edited, target))
    after = target.stat().st_size
    _, _, depth, ctype, has_trns = _png_header(target)
    ok("覆盖后仍是调色板（没有被 Qt 改回 32 位 RGBA）",
       (ctype, depth, has_trns) == (3, 1, True),
       f"ctype={ctype} depth={depth} tRNS={has_trns}")
    ok("覆盖后体积回到紧凑量级（改前这一张是 600×480×4 ≈ 1.15 MB）",
       after < 200_000, f"{before} → {after} 字节")
    ok("覆盖后 dpi 沿用原文件（300，不是 72）",
       _dpi_is(read_png_dpi(target)), str(read_png_dpi(target)))
    with Image.open(target) as img:
        after_arr = np.array(img.convert("RGBA"))
    ok("覆盖后像素就是编辑结果（颜色通道序没反）",
       after_arr.shape == arr.shape and bool((after_arr == arr).all()))
    ok("覆盖后不剩 .part 半截文件", not list(tmp.glob("*.part")))

    red = np.zeros((8, 8, 4), np.uint8)
    red[:, :, 0] = 255
    red[:, :, 3] = 255
    red_target = tmp / "red.png"
    save_png_compact(red, red_target)
    red_img = QImage(red.tobytes(), 8, 8, 8 * 4,
                     QImage.Format.Format_RGBA8888).copy()
    ok("覆盖纯红图成功", overwrite_image_file(red_img, red_target))
    read_back = QImage(str(red_target)).pixelColor(2, 2)
    ok("红还是红（ARGB32 的 B,G,R,A 内存序没被当 RGBA 用）",
       (read_back.red(), read_back.green(), read_back.blue()) == (255, 0, 0),
       read_back.name())

    download = tmp / "download.png"
    ok("另存 PNG 成功", save_image(red_img, download))
    _, _, depth, ctype, _ = _png_header(download)
    ok("另存 PNG 也是紧凑形态（调色板，不是 32 位 RGBA）",
       (ctype, depth) == (3, 1), f"ctype={ctype} depth={depth}")

    # -------------------------- 4. 「完成」的后台应用链（真正写底片的那条）
    bg_target = tmp / "0002-r.png"
    save_png_compact(page, bg_target)
    from desktop.components.viewers.image_editor.dialog_commit import _apply_job

    full = QImage(str(bg_target)).convertToFormat(QImage.Format.Format_ARGB32)
    result, saved = _apply_job({
        "image": full,
        "rect": QRectF(0.0, 0.0, float(full.width()), float(full.height())),
        "xf": QTransform(),
        "region": QImage(full),
        "grow": False,
        "clipping": "clip",
        "interpolation": "smooth",
        "target": str(bg_target),
        "payload": [],
    })
    _, _, depth, ctype, has_trns = _png_header(bg_target)
    ok("后台应用（_apply_job）写出的底片是调色板（不是 32 位 RGBA）",
       saved and ctype == 3 and depth <= 4,
       f"saved={saved} ctype={ctype} depth={depth} tRNS={has_trns}")
    ok("后台应用写出的底片体积仍是紧凑量级（改前 ≈ 1.15 MB）",
       bg_target.stat().st_size < 200_000, f"{bg_target.stat().st_size} 字节")
    ok("后台应用返回的图不是空的", result is not None and not result.isNull())
