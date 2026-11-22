# -*- coding: utf-8 -*-
"""DjVu 后端：djvu-rs 逐页解码（页面自带原生分辨率，不套 PDF 的 DPI 下限）。"""

import os
import time
from typing import List

from utils.pdf_extract.constants import MAX_OUTPUT_WIDTH_PX
from utils.pdf_extract.render import _fail_all_pages, _page_fail, _page_ok, _save_pil


def djvu_page_count(djvu_path) -> int:
    """DjVu 总页数（打开一次即关，别把句柄留在调用方）。"""
    import djvu_rs

    document = djvu_rs.Document.open(str(djvu_path))
    try:
        return int(document.page_count())
    finally:
        document = None  # djvu-rs 的 Document 没有 close()，靠释放引用关文件


def _djvu_target_size(width: int, height: int, zoom: float) -> tuple[int, int]:
    """DjVu 的目标渲染尺寸 = 原生像素 × zoom，再受 6000px 宽度封顶。

    ⚠️ **不套 PDF 那条 DPI 下限**：PDF 的 72 DPI 陷阱是"1pt 渲成 1px"，
    而 DjVu 页面本身就以原生像素记录扫描分辨率，再补 DPI 只是无端放大插值
    （细节不会变多，文件反而更大）。需要更高分辨率时用户可以给 ``--zoom``。
    """
    width = max(1, int(width))
    height = max(1, int(height))
    scale = float(zoom or 1)
    if width * scale > MAX_OUTPUT_WIDTH_PX:
        scale = MAX_OUTPUT_WIDTH_PX / float(width)
    return max(1, int(round(width * scale))), max(1, int(round(height * scale)))


def _flatten_on_white(image):
    """把带 alpha 的 DjVu 渲染结果叠到白底上，返回 RGB。

    DjVu 页通常有背景层（不透明）；少数只有前景层的文件解码出来是透明的，
    直接存 JPEG 会变黑，所以统一按白纸合成——与扫描件的阅读观感一致。
    """
    from PIL import Image

    if image.mode == "RGB":
        return image
    if image.mode != "RGBA":
        return image.convert("RGB")
    canvas = Image.new("RGBA", image.size, (255, 255, 255, 255))
    return Image.alpha_composite(canvas, image).convert("RGB")


def _render_djvu_batch_in_worker(payload: tuple) -> dict:
    """子进程执行体：解码一批 DjVu 页并落盘（返回结构与 PDF 批次一致）。

    payload = (djvu_path, page_indices, out_dir, zoom, ext, quick, dpi)

    ``quick`` / ``dpi`` 对 DjVu 不生效（DjVu 没有"内嵌原图直拷"这条捷径，
    也没有 72 DPI 陷阱），收下参数只是为了与 PDF 批次共用同一套并发调度。
    """
    djvu_path, page_indices, out_dir, zoom, ext, _quick, _dpi = payload

    def _fail_all(msg: str) -> dict:
        return _fail_all_pages(page_indices, msg)

    try:
        import djvu_rs
    except ImportError as e:
        return _fail_all(
            f"依赖缺失: djvu-rs 未安装。请运行: pip install djvu-rs（{e}）"
        )
    try:
        from PIL import Image  # noqa: F401 - 落盘依赖 PIL
    except ImportError as e:
        return _fail_all(f"依赖缺失: Pillow 未安装。请运行: pip install Pillow（{e}）")

    try:
        document = djvu_rs.Document.open(str(djvu_path))
    except Exception as e:  # noqa: BLE001 - 打不开就是整批失败
        return _fail_all(f"打开 DjVu 失败: {e}")

    pages: List[dict] = []
    try:
        for page_idx in page_indices:
            page_start = time.time()
            try:
                page = document.page(int(page_idx))
                target_wh = _djvu_target_size(page.width, page.height, zoom)
                pixmap = page.render(size=target_wh)
                image = _flatten_on_white(pixmap.to_pil())
                if image.size != target_wh:
                    image = image.resize(target_wh)
                img_path = os.path.join(out_dir, f"{page_idx + 1}.{ext}")
                _save_pil(image, img_path, ext)
                pages.append(_page_ok(page_idx, img_path, image.width,
                                      image.height, page_start))
            except Exception as e:  # noqa: BLE001 - 单页失败不拖垮整批
                pages.append(_page_fail(page_idx, e, page_start))
    finally:
        document = None  # 释放即可关文件（djvu-rs 无 close()）
    return {
        "pages": pages,
        "reasons": {},
        "fallback": 0,
        "jpx_fast": 0,
        "quick_direct": 0,
    }
