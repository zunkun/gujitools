# -*- coding: utf-8 -*-
"""编辑器烘焙的「二值稿不跑偏」护栏（体积 + 下游联锁）。

用户 2026-11-15：「图片编辑弹窗导致图片体积增大很多倍，会不会有这个问题」。
实测（``rembg`` 的 83KB 二值页，走真实的 ``compose_transform`` + ``overwrite_
image_file``）：

====================  =========  ==============
操作                   体积        像素组合
====================  =========  ==============
什么都不改              85 KB     2
旋转 0.5°（默认插值）   732 KB     260（8.8x）
旋转 0.5° **阈值化**    85 KB     2
====================  =========  ==============

两笔账：
1. **体积**：二值稿被插值成 260 色灰边，``compact_png`` 从「1 位调色板」掉到
   「8 位调色板」，一个数量级；
2. **联锁**（更要紧）：写回后不再是二值稿 ⇒ ``services.imposition.
   is_binary_source`` 判否 ⇒ 拼版合成与 PDF 排版那边的二值化**全部失效**
   （同页 194KB → 1.2MB）。等于编辑一张图，把整页的优化废掉。

修法：``_transform_job`` 里**判烘焙源、阈值化结果**（与 ``compose_page`` 同一
口径）。判据天然挡住两类不该动的图——照片（alpha 恒 255）、加过文字的页
（文字抗锯齿让 alpha 出中间值）。

本模块钉住：判据、端到端烘焙、写回体积、以及"写回后下游还认它是二值稿"。
要 QGuiApplication，但**不建窗口、不 show**。
"""

NAME = "image_editor_binary"
DEPENDS: list[str] = []
TITLE = "编辑器烘焙的二值稿（体积 / 下游联锁）"

import os
import shutil
import tempfile
from pathlib import Path


def _binary_pil(size=(600, 800)):
    """二值稿：墨 + 透明（等价于去底色产物的像素形态）。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    for step in range(8):                       # 几道"字"
        top = 60 + step * 90
        draw.rectangle((60, top, size[0] - 60, top + 26), fill=(0, 0, 0, 255))
    return canvas


def _text_like_pil(size=(600, 800)):
    """"加过文字"的样子：同一块墨，但边缘带半透明（alpha 96）。"""
    from PIL import ImageDraw

    canvas = _binary_pil(size)
    ImageDraw.Draw(canvas).rectangle((80, 700, 500, 760), fill=(0, 0, 0, 96))
    return canvas


def _photo_pil(size=(600, 800)):
    """照片样：全不透明 + 多灰阶（判据必须判否）。"""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", size, (120, 120, 120, 255))
    ImageDraw.Draw(canvas).ellipse((100, 150, 500, 700), fill=(200, 150, 90, 255))
    return canvas


def _qimage(pil_image):
    """PIL RGBA → QImage（``Format_RGBA8888``，内存序 R,G,B,A）。"""
    from PySide6.QtGui import QImage

    width, height = pil_image.size
    return QImage(pil_image.tobytes(), width, height, width * 4,
                  QImage.Format.Format_RGBA8888).copy()


def _rgba(qimage):
    from desktop.components.viewers.image_zoom_dialog.io import (
        _qimage_rgba_array,
    )

    return _qimage_rgba_array(qimage)


def _alpha_levels(qimage):
    import numpy as np

    return int(np.unique(_rgba(qimage)[:, :, 3]).size)


def _combos(qimage):
    """像素组合数（RGBA 四元组去重）——体积的真正判据。"""
    import numpy as np

    return int(np.unique(_rgba(qimage).reshape(-1, 4), axis=0).shape[0])


def _luma_levels(qimage):
    import numpy as np

    luma = _rgba(qimage)[:, :, :3].mean(axis=2).astype(np.uint8)
    return int(np.unique(luma).size)


def _rotate_job(image, degrees=0.5):
    """跑一次真实的 ``_transform_job``（绕图心转 ``degrees``）。"""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QTransform

    from desktop.components.viewers.image_editor.dialog_commit import (
        _transform_job,
    )

    width, height = image.width(), image.height()
    xf = QTransform()
    xf.translate(width / 2.0, height / 2.0)
    xf.rotate(degrees)
    xf.translate(-width / 2.0, -height / 2.0)
    return _transform_job({
        "image": image,
        "rect": QRectF(0, 0, width, height),
        "xf": xf,
        "region": QImage(image),
        "grow": False,
        "clipping": "",
        "interpolation": "nohalo",
    })


def run(ctx) -> None:
    from PIL import Image

    from desktop.components.viewers.image_zoom_dialog.io import (
        binary_ink, harden_alpha_image, is_binary_image, overwrite_image_file,
    )
    from tests.selftests._context import ok

    tmp = Path(tempfile.mkdtemp(prefix="editor_bin_"))
    try:
        # ---- 1. 判据 ---------------------------------------------------
        binary = _qimage(_binary_pil())
        ok("二值墨稿（alpha 只有 0/255、墨色唯一）判为二值",
           is_binary_image(binary) and binary_ink(binary) == (0, 0, 0),
           f"ink={binary_ink(binary)}")
        ok("全不透明图不判为二值（没有'无墨'这一态）",
           not is_binary_image(_qimage(Image.new("RGBA", (60, 90), (9, 9, 9, 255)))))
        ok("带半透明边（如加过文字）的图不判为二值",
           binary_ink(_qimage(_text_like_pil())) is None)

        two_color = _binary_pil()
        __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).Draw(
            two_color).rectangle((80, 700, 500, 760), fill=(200, 30, 30, 255))
        ok("alpha 二值但墨色有两种 ⇒ 不判为二值（不许把红并成黑）",
           binary_ink(_qimage(two_color)) is None)

        # ---- 2. 那一刀：连墨色一起归一，回到 2 种像素 -------------------
        text_like = _qimage(_text_like_pil())
        hardened = harden_alpha_image(text_like, (0, 0, 0))
        ok("阈值化后 alpha 只剩 0/255", _alpha_levels(hardened) == 2)
        ok("阈值化后像素组合是 2（墨色被归一，没有'灰色的墨'）",
           _combos(hardened) == 2, f"组合数={_combos(hardened)}")

        # ---- 3. 端到端：旋转 0.5° --------------------------------------
        rotated = _rotate_job(binary)[0]
        ok("二值稿旋转 0.5° 后仍是 2 种像素（没被插值成灰边/灰墨）",
           _combos(rotated) == 2, f"组合数={_combos(rotated)}")

        rotated_photo = _rotate_job(_qimage(_photo_pil()))[0]
        ok("照片旋转后保留灰阶（判据判否，没被误阈值化）",
           _alpha_levels(rotated_photo) == 1 and _luma_levels(rotated_photo) > 2,
           f"alpha 取值数={_alpha_levels(rotated_photo)}")

        rotated_text = _rotate_job(text_like)[0]
        ok("带半透明边的图旋转后仍保留中间 alpha（没被误伤）",
           _alpha_levels(rotated_text) > 2,
           f"alpha 取值数={_alpha_levels(rotated_text)}")

        # ---- 4. 写回体积 + 下游联锁 ------------------------------------
        target = tmp / "page.png"
        _binary_pil().save(target)                # 先落一张二值源
        base = os.path.getsize(target)

        overwrite_image_file(rotated, target)     # 走真实写回原语
        written_mode = Image.open(target).mode
        ok("旋转后的写回仍是调色板形态（紧凑编码生效）",
           written_mode == "P", f"mode={written_mode}")
        ok("写回体积没有跑偏（< 源图 2 倍）",
           os.path.getsize(target) < base * 2,
           f"{base // 1024}KB → {os.path.getsize(target) // 1024}KB")

        from desktop.services.imposition import is_binary_source

        with Image.open(target) as written:
            ok("写回后拼版侧仍认它是二值稿（联锁没断）",
               is_binary_source(written.convert("RGBA"), str(target)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
