# -*- coding: utf-8 -*-
"""JPX（JPEG2000）页面的降档解码快通道。"""

import io
import os

from utils.pdf_extract.constants import (
    JPX_REDUCE_MIN_COVERAGE,
    JPX_SOURCE_EXTS,
)
from utils.pdf_extract.quick import _page_scan_block_reason
from utils.pdf_extract.render import _save_pil


def _jpx_page_source(doc, page):
    """本页能否「绕过 MuPDF 整页渲染、直接解内嵌 JPX 码流」。

    返回 ``(info, None)`` 可取；``(None, 原因)`` 需回落整页渲染。

    判据（与 jpg/png 直拷共用同一套"纯扫描页"检查）：
    唯一内嵌图、无 SMask、铺满整页、无旋转/裁切/注释/可见文字/矢量绘制、
    格式是 jpx/jp2/j2k。任一不满足就回退——宁慢勿错。

    ⚠️ "铺满整页"必须用 ``get_image_info()``（只扫内容流，~0ms）；``get_image_rects()``
    要建整页显示列表（实测 ~1090ms），比省下来的解码还贵。
    """
    import pymupdf as fitz

    images = page.get_images(full=True)
    if len(images) != 1:
        return None, f"内嵌 {len(images)} 张图（多图不取，避免破坏一页一图）"
    xref = int(images[0][0])
    if int(images[0][1] or 0):  # SMask
        return None, "内嵌图带透明遮罩（SMask）"
    why = _page_scan_block_reason(page)
    if why is not None:
        return None, why
    infos = page.get_image_info()
    if len(infos) != 1:
        return None, "同一张图画了多次（拼贴/水印）"
    bbox = fitz.Rect(infos[0]["bbox"])
    rect = page.rect
    if (
        abs(bbox.x0 - rect.x0) > 1.5
        or abs(bbox.y0 - rect.y0) > 1.5
        or abs(bbox.x1 - rect.x1) > 1.5
        or abs(bbox.y1 - rect.y1) > 1.5
    ):
        return None, "内嵌图未铺满整页（页面上还有别的内容）"
    try:
        info = doc.extract_image(xref)
    except Exception:  # noqa: BLE001 - 抽不出码流就回落
        return None, "抽取内嵌码流失败"
    if (info.get("ext") or "").lower() not in JPX_SOURCE_EXTS:
        return None, f"内嵌格式 .{(info.get('ext') or '').lower()}（非 jpx/jp2/j2k）"
    if not info.get("width") or not info.get("height"):
        return None, "取不到内嵌图尺寸"
    return info, None


def _decode_jpx_stream(stream: bytes, target_wh: tuple[int, int]):
    """把 JPX 码流解成 PIL 图；能降档就先降档。失败返回 None。

    JPEG2000 的码流自带分辨率分级：``_reduce=1`` 只解一半边长（实测
    0.23s vs 全解 0.82s）。不同码流支持的层数不一样，超出就报
    "broken data stream"——所以降档失败必须能无痛回落到全解。
    """
    from PIL import Image

    # 1) 能降档才走 PIL（只解目标需要的层数）
    try:
        with Image.open(io.BytesIO(stream)) as src:
            w, h = src.size
            reduce = 0
            while (
                reduce < 6
                and (max(w, h) >> (reduce + 1))
                >= max(target_wh) * JPX_REDUCE_MIN_COVERAGE
            ):
                reduce += 1
            if reduce:
                src._reduce = reduce  # type: ignore[attr-defined]
                src.load()
                return src.convert("RGB")
    except Exception:  # noqa: BLE001 - 该层数不支持/码流坏 → 回落全解
        pass

    # 2) 全分辨率解码：cv2(OpenJPEG) 通常比 PIL 快约 40%
    try:
        import cv2
        import numpy as np

        arr = cv2.imdecode(np.frombuffer(stream, dtype=np.uint8), cv2.IMREAD_COLOR)
        if arr is not None:
            return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))
    except Exception:  # noqa: BLE001 - 没装 cv2 / 解不出来 → 用 PIL
        pass
    try:
        with Image.open(io.BytesIO(stream)) as src:
            src.load()
            return src.convert("RGB")
    except Exception:  # noqa: BLE001
        return None


def _jpx_reduce_level(native_wh: tuple[int, int], target_wh: tuple[int, int],
                      max_level: int = 6) -> int:
    """这个码流最多能降几档还不低于目标分辨率（0 = 不建议降档）。

    只有 ``>= 1`` 才值得走 JPX 快通道：降不下档时 cv2/PIL 的全解既不比
    MuPDF 快多少，还要多一份解码缓冲（实测多进程下反而更慢、更吃内存）。
    """
    native_edge = max(native_wh)
    target_edge = max(target_wh)
    level = 0
    while (
        level < max_level
        and (native_edge >> (level + 1)) >= target_edge * JPX_REDUCE_MIN_COVERAGE
    ):
        level += 1
    return level


def _render_jpx_page(info, out_dir: str, page_idx: int, ext: str,
                     target_wh: tuple[int, int]):
    """JPX 快通道：直接解内嵌码流，落到**与整页渲染完全相同的目标尺寸**。

    返回 ``(路径, 宽, 高)``；不能降档或解码失败返回 None（调用方回落整页渲染）。

    ⚠️ ``target_wh`` 必须由 ``render_zoom``（含 DPI 下限与 6000px 封顶）算出来，
    **不能用内嵌图原生尺寸**——否则用户设的 ``zoom`` / ``dpi`` 在这一页上会被
    悄悄忽略，同一本书里还会出现"有的页按 zoom、有的页按原生"的尺寸不一致。

    ⚠️ 只有**能降档**（``_jpx_reduce_level >= 1``）才走快通道：不能降档时
    整帧解码的耗时与 MuPDF 相当，但内存更高、多进程吞吐反而更差（实测
    168 页 43.7s → 48.2s），交给 MuPDF 更划算。
    """
    native_wh = (int(info["width"]), int(info["height"]))
    if _jpx_reduce_level(native_wh, target_wh) < 1:
        return None
    img = _decode_jpx_stream(info["image"], target_wh)
    if img is None:
        return None
    from PIL import Image

    if img.size != target_wh:
        # 缩小/放大都做：整页渲染在这两种情况下也是同一个目标尺寸
        img = img.resize(target_wh, Image.LANCZOS)  # type: ignore[attr-defined]
    img_path = os.path.join(out_dir, f"{page_idx + 1}.{ext}")
    _save_pil(img, img_path, ext)
    return img_path, img.width, img.height
