# -*- coding: utf-8 -*-
"""拼版成品的**体积形态**护栏（二值源 ⇒ 二值成品 + 紧凑编码）。

用户 2026-11-15：「拼版后的图片有些大……原本的图片很小，也就是 rembg 的图片很小」。
任务 0006 实测：去底图 184 张共 **15.9MB**（均 88KB），拼版成品 91 张共 **109.8MB**
（均 1236KB），第四步 PDF 123MB。

真因两处（**都不是"重合/拉伸"本身**）：

1. ``compose_page`` 对每张图无条件 ``resize(LANCZOS)`` + ``rotate(BICUBIC)``。
   二值稿（只有「墨 / 透明」两态）被插值出一圈半透明灰边——**哪怕只差 1 像素**
   也会从 2 色变 256 色（实测 1623 宽的二值图：+0px=2 色 154.8KB，**+1px=256 色
   418.9KB**），整页 1.7MB。整数像素的**平移/重合是无损的**（alpha_composite 是
   纯拷贝），所以只有"改尺寸"和"非 90° 旋转"才有代价。
2. ``_save_page_atomic`` 走 ``image.save(format="PNG")`` = 8bit RGBA（32 位/像素），
   把二值页 1 位/像素的最省形态丢掉了。

本模块钉住四件事（都是"改错就会静默变大"的地方）：

- 二值源的成品**必须仍是二值**（拉伸、旋转、重合三种操作各一条）；
- 带软边的源**必须不被误伤**（半透明边缘要原样留着）；
- 落盘走紧凑编码：P 模式、体积显著小于 RGBA；
- PDF 侧 ``_load_image``：① 带 tRNS 的调色板成品压平后是**白底不是黑底**
  （紧凑编码把透明项的 RGB 写成 0，`convert("RGB")` 会整片印黑）；
  ② 二值页降采样后仍只有两级灰；③ 非二值页不被阈值化。

纯 PIL + 纯函数，不需要 Qt 控件、不需要 YOLO。
"""

NAME = "imposition_binary"
DEPENDS: list[str] = []
TITLE = "拼版成品体积形态（二值源 / 紧凑编码 / PDF 降采样）"

import shutil
import tempfile
from pathlib import Path


def _make_binary(path: Path, size=(600, 800), boxes=None) -> Path:
    """造一张**二值稿**（墨 / 透明两态），形态与 rembg 产物一致（P + tRNS）。

    ⚠️ 必须用项目自己的紧凑编码落盘：只有这样才真的是"1 位调色板 + tRNS"，
    用 ``Image.save`` 手工造会写成 RGBA，就测不到真实形态了。
    """
    import numpy as np
    from PIL import Image, ImageDraw

    from utils.compact_png import save_png_compact

    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    for box in (boxes or [(60, 80, size[0] - 60, size[1] - 80)]):
        draw.rectangle(box, fill=(0, 0, 0, 255))
        # 内部挖几道"字"：避开纯色块，压缩率才像真页面
        for step in range(6):
            top = box[1] + 40 + step * 60
            draw.rectangle(
                (box[0] + 40, top, box[2] - 40, top + 8), fill=(0, 0, 0, 0))
    save_png_compact(np.array(canvas), path)
    return path


def _make_soft(path: Path, size=(600, 800)) -> Path:
    """造一张**带软边**的稿（alpha 是一条 0→255 的渐变）——它**不是**二值稿。"""
    import numpy as np
    from PIL import Image

    rgba = np.zeros((size[1], size[0], 4), np.uint8)
    ramp = np.linspace(0, 255, size[0]).astype(np.uint8)
    rgba[:, :, 3] = ramp[None, :]
    Image.fromarray(rgba, "RGBA").save(path, format="PNG")
    return path


def _colors(image) -> int:
    """成品图的**像素形态数**（RGBA 四元组去重）。"""
    import numpy as np

    return int(np.unique(np.array(image.convert("RGBA")).reshape(-1, 4),
                         axis=0).shape[0])


def _page(left, right, size=(600, 800), stretch=1.03, rotation=0.6,
          overlap=0.0) -> dict:
    """造一页版面：``left`` 贴 x=0，``right`` 摆到它右边（可拉伸/旋转/重叠）。"""
    lw, lh = size
    right_x = lw - overlap
    return {"items": [
        {"file": str(right), "rect": [right_x, 0.0, lw * stretch, lh * 0.995],
         "rotation": rotation},
        {"file": str(left), "rect": [0.0, 0.0, float(lw), float(lh)],
         "rotation": 0.0},
    ]}


def run(ctx) -> None:
    from PIL import Image

    from desktop.services.imposition import (
        _looks_binary, _save_page_atomic, compose_page,
    )
    from functions.print import PrintFunction
    from tests.selftests._context import ok
    from utils.compact_png import encode_png_compact, save_png_compact

    tmp = Path(tempfile.mkdtemp(prefix="impos_bin_"))
    try:
        left = _make_binary(tmp / "1-l.png")
        right = _make_binary(tmp / "2-r.png")
        soft = _make_soft(tmp / "3-l.png")

        # ---- 1. 二值稿判据 ---------------------------------------------
        ok("二值稿（墨/透明两态）判为二值",
           _looks_binary(Image.open(left).convert("RGBA")))
        ok("带软边的稿不判为二值",
           not _looks_binary(Image.open(soft).convert("RGBA")))
        opaque = Image.new("RGBA", (64, 64), (0, 0, 0, 255))
        ok("全不透明的稿不判为二值（没有'无墨'这一态）",
           not _looks_binary(opaque))

        # ---- 2. 拉伸 + 微旋转的页：成品必须仍是二值 ----------------------
        page = _page(left, right)
        composed = compose_page(page)
        ok("二值源 + 拉伸3% + 旋转0.6° ⇒ 成品仍是二值（2 种像素）",
           _colors(composed) == 2, f"实际 {_colors(composed)} 种")

        # ---- 3. 重合也是二值 --------------------------------------------
        page_overlap = _page(left, right, stretch=1.0, rotation=0.0,
                             overlap=40.0)
        ok("二值源 + 两图重合 40px ⇒ 成品仍是二值",
           _colors(compose_page(page_overlap)) == 2)

        # ---- 4. 带软边的源不被误伤 --------------------------------------
        soft_page = _page(soft, right, stretch=1.0, rotation=0.0)
        soft_out = compose_page(soft_page)
        import numpy as np

        alpha = np.array(soft_out.convert("RGBA"))[:, :, 3]
        ok("软边源的半透明边缘原样保留（没被误阈值化）",
           int(((alpha > 0) & (alpha < 255)).sum()) > 0,
           "阈值化会把渐变压成硬边")
        ok("软边页的成品不是二值（说明判据真的按图走，不是按页）",
           _colors(soft_out) > 2)

        # ---- 5. 落盘走紧凑编码 ------------------------------------------
        target = tmp / "0001.png"
        _save_page_atomic(composed, target)
        written = Image.open(target)
        ok("成品落盘是调色板模式（P），带透明度",
           written.mode == "P" and "transparency" in written.info,
           f"mode={written.mode}")

        import io

        buf = io.BytesIO()
        composed.save(buf, format="PNG")           # 旧口径（8bit RGBA）
        old_size, new_size = len(buf.getvalue()), target.stat().st_size
        ok("紧凑编码后的体积 < 旧 RGBA PNG 的 1/3",
           new_size * 3 < old_size,
           f"{old_size // 1024}KB → {new_size // 1024}KB")

        # ---- 6. 两个公开入口同一套编码 ----------------------------------
        path_copy = tmp / "0001_again.png"
        save_png_compact(np.array(composed), path_copy)
        data, info = encode_png_compact(np.array(composed))
        ok("encode_png_compact 的字节与 save_png_compact 落盘逐字节相同",
           data == path_copy.read_bytes(), "同一个'唯一实现'，不许分叉")
        ok("encode 返回的体积字段 == 实际字节数",
           info["bytes"] == len(data))

        # ---- 7. PDF 侧：调色板成品压平后是**白底** ----------------------
        load = PrintFunction._load_image
        loaded = load(0, str(target), 0, 0)
        corner = loaded["img"].getpixel((0, 0))
        ok("PDF 载入 P+tRNS 成品：透明处压平成白（不是黑）",
           corner == (255, 255, 255) if loaded["img"].mode == "RGB"
           else corner == 255,
           f"左上像素={corner}，mode={loaded['img'].mode}")

        # ---- 8. 二值页降采样后仍只有两级灰 ------------------------------
        w, h = composed.size
        shrunk = load(0, str(target), w // 2, h // 2)
        img = shrunk["img"]
        levels = sum(1 for count in img.histogram() if count)
        ok("二值页降采样后仍只有 2 级灰（LANCZOS 的灰边被还原）",
           img.mode == "L" and levels == 2,
           f"mode={img.mode} 灰度级={levels}")

        # ---- 9. 非二值页不被阈值化 --------------------------------------
        soft_target = tmp / "0002.png"
        _save_page_atomic(soft_out, soft_target)
        soft_loaded = load(0, str(soft_target), w // 2, h // 2)["img"]
        soft_levels = sum(1 for count in soft_loaded.histogram() if count)
        ok("非二值页降采样后保留灰阶（没被误阈值化）",
           soft_levels > 2, f"灰度级={soft_levels}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
