# -*- coding: utf-8 -*-
"""JPX 快速通道：用 OpenJPEG 按需降分辨率解码（比 MuPDF 快 5 倍）。"""

from __future__ import annotations

import io as _io
import os
from pathlib import Path

from .constants import JPX_FAST_MAX_EDGE, JPX_FAST_MIN_REDUCE

#: 解析结果缓存（``None`` 也缓存：没装就是没装，别每页都去 which 一遍）
_OPJ_PATH: str | None | bool = False


def _resolve_opj() -> str | None:
    """找 ``opj_decompress``（OpenJPEG 的解码 CLI）；找不到返回 None。

    查找顺序（**任何一步失败都只是回落到 MuPDF**，绝不影响出图）：

    1. 环境变量 ``GUJI_OPJ_DECOMPRESS``（排障/自测指定）；
    2. ``PATH`` 上的 ``opj_decompress``（conda 用户天然有）；
    3. 程序目录（frozen：exe 同级 / ``_internal``；源码：仓库根的 ``tools/opj``）。
    """
    global _OPJ_PATH
    if _OPJ_PATH is not False:
        return _OPJ_PATH  # type: ignore[return-value]
    import shutil
    import sys

    candidates: list[str] = []
    env = (os.environ.get("GUJI_OPJ_DECOMPRESS") or "").strip()
    if env:
        candidates.append(env)
    found = shutil.which("opj_decompress")
    if found:
        candidates.append(found)
    base = Path(sys.executable).resolve().parent
    for extra in (
        base,
        base / "_internal",
        base / "Library" / "bin",
        base.parent / "Library" / "bin",
        # 本文件在 desktop/workers/pdf_render_service/jpx.py ⇒ parents[3] 是仓库根
        Path(__file__).resolve().parents[3] / "tools" / "opj",
    ):
        for name in ("opj_decompress.exe", "opj_decompress"):
            candidates.append(str(extra / name))
    _OPJ_PATH = next(
        (c for c in candidates if c and Path(c).is_file()), None
    )
    return _OPJ_PATH  # type: ignore[return-value]


def jpx_fast_available() -> bool:
    """本机有没有可用的 OpenJPEG 解码器（自测/排障用）。"""
    return _resolve_opj() is not None


def _child_jpx_thumb(pdf_path: str, page_index: int, edge: int,
                     quality: int, fmt: str) -> bytes:
    """**JPX 按需降分辨率**出缩略图；不适用时返回空字节（调用方回落 MuPDF）。

    ## 为什么这条路能快 5 倍

    MuPDF 的 ``page.get_pixmap()`` 对 JPX 是**整帧全分辨率解码**（实测要 64px
    还是 1024px 都是 ~990ms——目标尺寸完全不影响解码量）。而 JPEG2000 的码流
    自带**分辨率分级**（小波层），OpenJPEG 可以只解前几级：``-r 4`` 就是 1/16。

    实测（本仓样例书，内嵌 3705×7042 JPX，目标 256px）：

    ====  ====  =========  ======
    方式  降采样  输出        耗时
    ====  ====  =========  ======
    MuPDF  1/16  135×256    871 ms
    opj    1/4   926×1760   616 ms
    opj    1/8   463×880    284 ms
    opj    1/16  231×440    **161 ms**
    ====  ====  =========  ======

    ## 只在"确实是整页扫描图"时才用

    走这条路等于绕开 MuPDF 的整页合成（页面上的矢量/注释/旋转都不会被画出来），
    所以判据必须严：**唯一一张内嵌图 + 无 SMask + 铺满整页 + 页面无旋转 +
    无注释 + 格式是 jpx/jp2**。任一不满足就返回空、交回 MuPDF——宁慢勿错。
    """
    if not edge or edge > JPX_FAST_MAX_EDGE or fmt not in ("jpg", "jpeg"):
        return b""
    opj = _resolve_opj()
    if opj is None:
        return b""
    import pymupdf as fitz

    document = fitz.open(str(pdf_path))
    try:
        page = document.load_page(int(page_index))
        if int(page.rotation) % 360:
            return b""
        # ⚠️ ``page.annots()`` 返回**生成器**——直接 ``if page.annots()`` 恒为真
        #    （生成器对象本身 truthy），会把每一页都挡在快速通道外面。
        if next(page.annots(), None) is not None:
            return b""
        images = page.get_images(full=True)
        if len(images) != 1 or int(images[0][1] or 0):
            return b""
        xref = int(images[0][0])
        # ⚠️ 判"这张图铺满整页"必须用 ``get_image_info()``，**不能用
        #    ``get_image_rects()``**：后者要建整页显示列表（实测 **1090ms**，
        #    比它省下来的解码时间还多）。``get_image_info`` 只扫内容流，0ms。
        infos = page.get_image_info()
        page_rect = page.rect
        if len(infos) != 1:
            return b""  # 页面上画了不止一次图（拼贴/水印）：交给 MuPDF
        bbox = fitz.Rect(infos[0]["bbox"])
        if (
            abs(bbox.x0 - page_rect.x0) > 1.5
            or abs(bbox.y0 - page_rect.y0) > 1.5
            or abs(bbox.x1 - page_rect.x1) > 1.5
            or abs(bbox.y1 - page_rect.y1) > 1.5
        ):
            return b""  # 图没铺满整页：页面上还有别的内容，交给 MuPDF
        try:
            info = document.extract_image(xref)
        except Exception:  # noqa: BLE001 - 抽不出流就回落
            return b""
        ext = (info.get("ext") or "").lower()
        if ext not in ("jpx", "jp2", "j2k"):
            return b""
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        if not width or not height:
            return b""
        reduce = 0
        while (
            reduce < 6
            and (max(width, height) >> (reduce + 1)) >= int(edge * 1.05)
        ):
            reduce += 1
        if reduce < JPX_FAST_MIN_REDUCE:
            return b""  # 降不下来就没赚头（全分辨率 opj 慢得多）
        return _run_opj_thumb(opj, info["image"], ext, reduce, edge, quality)
    finally:
        document.close()


def opj_run_kwargs() -> dict:
    """``opj_decompress`` 的启动参数——**唯一决定"会不会闪黑窗"的地方**。

    ⚠️ ``CREATE_NO_WINDOW`` 不能省（2026-11-22 用户报「导入 PDF 时大量黑色命令行
    弹窗一闪而过」）：``opj_decompress`` 是控制台程序，而**每渲一页缩略图就要起
    一次**。父进程若有控制台（源码版从终端跑）子进程就继承、看不见；但打包版
    ``guji-desktop.exe`` 是 windowed、**没有控制台**，于是每次调用都由 Windows
    新开一个黑窗——导入一本书的首屏（24 页）就是二十多个窗口接连闪烁。

    加了标志只是不建窗口：stdout/stderr 仍是管道（``capture_output``），解码结果
    与"缺失即回落 MuPDF"的降级路径都不受影响。
    """
    import subprocess
    import sys

    kwargs: dict = {"capture_output": True, "timeout": 30}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(
            subprocess, "CREATE_NO_WINDOW", 0x08000000
        )
    return kwargs


def _run_opj_thumb(opj: str, stream: bytes, ext: str, reduce: int,
                   edge: int, quality: int) -> bytes:
    """把 JPX 码流交给 ``opj_decompress -r N``，再缩成目标尺寸。失败返回空字节。

    启动参数见 :func:`opj_run_kwargs`（**必须**带 ``CREATE_NO_WINDOW``，否则打包版
    每页一个黑窗）。
    """
    import subprocess
    import tempfile

    from PIL import Image

    # ⚠️ ``extract_image`` 给 "jpx" 时内容是**裸码流**（J2K），给 "jp2" 才是
    #    容器；opj_decompress 按**后缀**选解析器，写错后缀会直接解不出来。
    suffix = ".jp2" if ext == "jp2" else ".j2k"
    try:
        with tempfile.TemporaryDirectory(prefix="guji_jpx_") as tmp:
            source = Path(tmp) / f"page{suffix}"
            source.write_bytes(stream)
            out = Path(tmp) / "page.ppm"
            proc = subprocess.run(
                [opj, "-i", str(source), "-o", str(out), "-r", str(int(reduce))],
                **opj_run_kwargs(),
            )
            if proc.returncode != 0 or not out.is_file():
                return b""
            with Image.open(out) as image:
                image.draft("RGB", (edge, edge))
                rgb = image.convert("RGB")
                rgb.thumbnail((int(edge), int(edge)), Image.LANCZOS)
                buffer = _io.BytesIO()
                rgb.save(buffer, "JPEG", quality=int(quality))
                return buffer.getvalue()
    except Exception:  # noqa: BLE001 - 二进制缺失/超时/坏图：一律回落
        return b""
