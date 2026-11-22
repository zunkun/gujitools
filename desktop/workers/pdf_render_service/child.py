# -*- coding: utf-8 -*-
"""子进程侧入口：渲页 / 页数 / 单页提取（**纯函数，可 pickle**）。"""

from __future__ import annotations

import io as _io
from pathlib import Path

from .jpx import _child_jpx_thumb
from .thumbs import _thumb_from_page_image


def _is_djvu(path) -> bool:
    """源文件是不是 DjVu（预览/页数都走 djvu-rs 而不是 MuPDF）。"""
    return Path(str(path)).suffix.lower() in (".djvu", ".djv")


def _child_djvu_render_jpeg(djvu_path: str, page_index: int, edge: int,
                            quality: int, fmt: str) -> bytes:
    """子进程里用 djvu-rs 渲一页 DjVu（**纯函数，可 pickle**）。

    ``edge``：目标最长边；**0 = 原生分辨率**（与 PDF 分支同语义）。
    """
    import djvu_rs
    from PIL import Image

    document = djvu_rs.Document.open(str(djvu_path))
    try:
        page = document.page(int(page_index))
        if edge:
            longest = max(int(page.width), int(page.height)) or 1
            scale = float(edge) / float(longest)
            size = (
                max(1, int(round(page.width * scale))),
                max(1, int(round(page.height * scale))),
            )
            pixmap = page.render(size=size)
        else:
            pixmap = page.render()
        image = pixmap.to_pil()
        if image.mode == "RGBA":
            # DjVu 页可能有透明背景；预览/缩略图统一按白纸合成
            canvas = Image.new("RGBA", image.size, (255, 255, 255, 255))
            image = Image.alpha_composite(canvas, image)
        image = image.convert("RGB")
        buffer = _io.BytesIO()
        if fmt in ("jpg", "jpeg"):
            image.save(buffer, "JPEG", quality=int(quality))
        else:
            image.save(buffer, fmt.upper())
        return buffer.getvalue()
    finally:
        document = None  # djvu-rs 的 Document 没有 close()，释放引用即关文件


def _child_render_jpeg(pdf_path: str, page_index: int, edge: int,
                       quality: int, fmt: str,
                       pages_dir: str | None = None) -> bytes:
    """子进程里渲一页并编码成字节（**纯函数，可 pickle**）。

    ``edge``：目标最长边；**0 = 不缩放**（要原始分辨率，与 ``PreviewWorker``
    的 ``longest_edge=0`` 语义一致）。

    ``pages_dir``：**已提取的整页图目录**（``stages/extract``）。命中就用那张
    JPEG 缩（21ms），不再回 PDF 解 JPX（~850ms）——"提取之后还得等缩略图"
    就是缺了这一步。图读不出来时静默回落到源文件渲染。
    """
    if pages_dir:
        data = _thumb_from_page_image(pages_dir, page_index, edge, quality,fmt)
        if data:
            return data
    if _is_djvu(pdf_path):
        return _child_djvu_render_jpeg(pdf_path, page_index, edge, quality, fmt)
    # JPX 快速通道：按需降分辨率解码（161ms vs MuPDF 871ms，见模块说明）
    data = _child_jpx_thumb(pdf_path, page_index, edge, quality, fmt)
    if data:
        return data
    import pymupdf as fitz

    document = fitz.open(str(pdf_path))
    try:
        page = document.load_page(int(page_index))
        rect = page.rect
        longest = max(rect.width, rect.height) or 1.0
        scale = (float(edge) / longest) if edge else 1.0
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        if fmt in ("jpg", "jpeg"):
            return pixmap.tobytes("jpg", jpg_quality=int(quality))
        return pixmap.tobytes(fmt)
    finally:
        document.close()


def _child_page_count(pdf_path: str) -> int:
    """子进程里读页数（PDF / DjVu 都支持）。"""
    if _is_djvu(pdf_path):
        import djvu_rs

        document = djvu_rs.Document.open(str(pdf_path))
        try:
            return int(document.page_count())
        finally:
            document = None
    import pymupdf as fitz

    document = fitz.open(str(pdf_path))
    try:
        return int(document.page_count)
    finally:
        document.close()


def _child_render_safe(spec: tuple) -> bytes:
    """``render_jpegs`` 的单页入口：**单页失败只让那一页空着**（不炸整批）。

    整批渲染里一页坏掉（超页数 / 图片流损坏）不该让另外几十页全丢掉——
    调用方按"空字节 = 这页没渲出来"处理即可（与原实现"跳过该页"一致）。
    """
    try:
        return _child_render_jpeg(*spec)
    except Exception:  # noqa: BLE001 - 单页失败不影响同批其它页
        return b""


def _child_extract_page(pdf_path: str, page_index: int, out_dir: str,
                        zoom: float, ext: str, quick: bool,
                        dpi: float) -> dict:
    """子进程里做**单页提取**（与批量提取同一条实现，产物逐位一致）。"""
    from utils.pdf_extract import extract_single_page

    return extract_single_page(
        str(pdf_path), int(page_index), str(out_dir),
        zoom=zoom, ext=ext, quick=quick, dpi=dpi,
    )


def _child_warmup() -> bool:
    """子进程预热：把 pymupdf 的 import 提前做掉（首张缩略图不用等它）。"""
    import pymupdf  # noqa: F401 - 纯粹为了在子进程里完成导入

    return True
