# -*- coding: utf-8 -*-
"""从**已提取的整页图**缩出缩略图（子进程侧，纯函数可 pickle）。"""

from __future__ import annotations

from pathlib import Path


def _thumb_from_page_image(pages_dir: str, page_index: int, edge: int,
                           quality: int, fmt: str) -> bytes:
    """从**已提取的整页图**缩出缩略图；不可用时返回空字节。

    ⚠️ 只在要缩略图（``edge > 0``）时用：要原始分辨率（``edge=0``）时应当渲
    PDF 或直接读产物，不该在这里重编码。
    """
    if not edge or fmt not in ("jpg", "jpeg"):
        return b""
    base = Path(pages_dir)
    source = None
    for suffix in (".jpg", ".jpeg", ".png"):
        candidate = base / f"{int(page_index) + 1}{suffix}"
        if candidate.is_file():
            source = candidate
            break
    if source is None:
        return b""
    try:
        import io as _io

        from PIL import Image

        with Image.open(source) as image:
            # JPEG 的 DCT 域降采样：先把解码尺寸降到 1/2、1/4、1/8 再解，
            # 实测 2067×2767 → 256px 只要 ~21ms（整张解码再缩是 58ms+）
            image.draft("RGB", (edge, edge))
            rgb = image.convert("RGB")
            rgb.thumbnail((int(edge), int(edge)), Image.LANCZOS)
            buffer = _io.BytesIO()
            rgb.save(buffer, "JPEG", quality=int(quality))
            return buffer.getvalue()
    except Exception:  # noqa: BLE001 - 产物坏了/被占：回落到 PDF 渲染
        return b""
