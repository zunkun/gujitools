# -*- coding: utf-8 -*-
"""图片加载与颜色模式收敛（alpha 压平、灰度/二值判定、降采样）。"""

from __future__ import annotations

from PIL import Image, ImageChops, ImageOps

from functions.print.constants import (
    PRINT_IMAGE_DPI,
    PRINT_KEEP_BINARY,
    _BINARY_LUT,
)


def _flatten_alpha(img: Image.Image) -> Image.Image:
    """把带 alpha 的图收敛成可嵌入 PDF 的 ``RGB``（透明区铺白底）。

    ⚠️ 只动**带 alpha** 的图：CMYK / 调色板 / 1 位等其余模式维持原样交给
    fpdf（它有自己的色彩空间处理，擅自转 RGB 会改变颜色）。

    ⚠️ 全不透明时走 ``convert("RGB")`` 快路径：``paste(..., mask=alpha)``
    是逐像素合成，5.5MP 的页要多花约 200ms/页（2026-10-24 实测）；而 alpha
    全为 255 时两者结果**逐像素相同**，没有理由付这份钱。
    """
    if img.mode not in ("RGBA", "LA"):
        return img
    alpha = img.getchannel("A")
    if alpha.getextrema() == (255, 255):
        return img.convert("RGB")
    rgba = img if img.mode == "RGBA" else img.convert("RGBA")
    bg = Image.new("RGB", rgba.size, (255, 255, 255))
    bg.paste(rgba, mask=rgba.getchannel("A"))
    return bg


def _is_binary_l(img: Image.Image) -> bool:
    """``L`` 图是否只有纯黑 / 纯白两级（二值稿的判据）。

    与拼版侧 ``services.imposition._looks_binary`` **同一语义**（那边看 alpha
    的 0/255，这边看压平后的 0/255），但分开实现：一边是 RGBA 的 alpha 通道、
    一边是压平白底后的灰阶，硬合并只会让两边都难读。
    """
    if img.mode != "L":
        return False
    colors = img.getcolors(maxcolors=2)
    if not colors or len(colors) != 2:
        return False
    return sorted(color for _count, color in colors) == [0, 255]


def _is_grayscale(img: Image.Image) -> bool:
    """``RGB`` 图是否逐像素满足 R=G=B（纯灰）。

    纯灰图转 ``L`` 与留 ``RGB`` 在画面上完全等价，但嵌入数据只有 1/3。
    用 ``ImageChops.difference`` 的 ``getbbox()`` 判断（C 实现，5.5MP 约
    20ms），不引 numpy。
    """
    r, g, b = img.split()
    return (
        ImageChops.difference(r, g).getbbox() is None
        and ImageChops.difference(g, b).getbbox() is None
    )


def _load_image(idx, path, max_w_px=0, max_h_px=0):
    try:
        img = Image.open(path)
        # ⚠️ EXIF 方向必须转正（2026-09-26 第二轮审计）：cv2 链
        #    （detect/crop，utils.image_io.imdecode）默认按 EXIF 方向
        #    自动转正，唯独 PIL 不转——不处理的话，带 EXIF 方向的 JPEG 会被
        #    **横躺 90°** 嵌进 PDF，与检测框方向不一致。
        #    先查方向标签：无标签时 exif_transpose 也会整图复制一份。
        # ⚠️（2026-11-20 更正）别再写"Qt 预览也转正"：``QImage`` /
        #    ``QImageReader`` 的 ``autoTransform`` 默认 **False**，全仓也没有
        #    任何 ``setAutoTransform(True)``。所以本程序落盘的页面图一律先
        #    剥掉方向标签（``utils.exif_clean``），这里对它们只是空操作；
        #    真正的转正对象是"用户直接放进来的素材"。
        if img.getexif().get(274, 1) != 1:
            img = ImageOps.exif_transpose(img)
        # ⚠️ 带 tRNS 的**调色板 PNG 必须先展成 RGBA**（2026-11-15）：拼版成品
        #    走紧凑编码后就是 ``P + tRNS``，而它"透明"那一项自己的 RGB 是
        #    **(0,0,0)**（合成画布是透明黑）。``_flatten_alpha`` 只认 RGBA/LA，
        #    P 会被原样放过、最后落到 fpdf 的 ``convert("RGB")``——透明白区
        #    会整片印成黑底。去底色产物（``rembg``）同理：它的透明项是白色，
        #    侥幸没炸，但不能靠运气。
        if img.mode in ("P", "PA") and "transparency" in img.info:
            img = img.convert("RGBA")
        img = _flatten_alpha(img)
        # ⚠️ 灰度转 L（2026-10-24，用户报「生成 PDF 慢」实测）：
        #    fpdf 对每页做 FlateDecode 时是**串行** zlib 压缩，耗时与像素
        #    字节数成正比。古籍扫描页绝大多数 R=G=B（纯灰），此时转 `L`
        #    在**逐像素等价**（无损、不影响观感）的前提下把数据量降到
        #    1/3，单页压缩耗时同步降到 1/3（任务 0017 实测 50 页
        #    27s → 14.5s，PDF 116MB → 70MB）。彩色页（R≠G≠B）照旧走
        #    RGB，不丢任何颜色。
        if img.mode == "RGB" and _is_grayscale(img):
            img = img.convert("L")
        # 二值稿标记：**必须在降采样前**判（降采样会把它毁掉），
        # 判完在降采样之后再把灰边阈值化回去，见 PRINT_KEEP_BINARY。
        binary = PRINT_KEEP_BINARY and _is_binary_l(img)
        # 超过打印所需像素时等比缩小（只缩不放），宽高比不变，
        # 后续排版几何完全一致，但压缩速度与 PDF 体积大幅改善。
        w, h = img.size
        if (
            max_w_px > 0
            and max_h_px > 0
            and (w > max_w_px or h > max_h_px)
        ):
            scale = min(max_w_px / w, max_h_px / h)
            target = (
                max(1, int(w * scale)),
                max(1, int(h * scale)),
            )
            img = img.resize(target, Image.Resampling.LANCZOS)
            if binary:
                # 只对二值稿：把 LANCZOS 插出来的灰边还原成 0/255。
                # 非二值稿（扫描灰度页、彩色插图）一律不碰。
                img = img.point(_BINARY_LUT)
        return {"idx": idx, "img": img, "path": path, "size": img.size}
    except Exception as e:
        print(f"加载图片失败 {path}: {e}")
        return None
