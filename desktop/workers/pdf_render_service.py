# -*- coding: utf-8 -*-
"""PDF 页渲染**出进程**（GUI 进程里只发请求，不碰 PyMuPDF 的像素）。

## 为什么必须搬到子进程

PyMuPDF 的 ``page.get_pixmap()`` 在**整段解码期间持有 GIL**，而且扫描古籍常见
的内嵌格式是 **JPX（JPEG2000）**：

=====  =========================  ===================  ============
内嵌格式  内嵌图尺寸                 渲一张 256px 缩略图     备注
=====  =========================  ===================  ============
JPX    4285×5736（本仓样例书）      **~850 ms**          解码按像素线性增长
JPX    1280×2688                  ~190 ms
Flate  702×1360                   ~11 ms
=====  =========================  ===================  ============

这 850ms 里 GUI 线程**拿不到一次时间片**（实测：另一线程 1ms 心跳被拖成
800~970ms 一整块）。于是"导入后生成整本缩略图"＝一本 28 页的书把界面冻成
28 个 0.85 秒的卡顿块，用户感知就是「创建任务卡、进详情卡、切缩略图卡」。

单飞锁（``render_lock``）只能把**并发**压平，压不掉**单次**的 850ms——线程
方案对 PyMuPDF 渲染没有任何加速（见 ``utils.pdf_extract.render_pages_parallel``
的实测：6 线程仅 1.15×）。唯一出路是**换进程**：GIL 不共享，GUI 一次都不冻，
而且多个子进程可以真并行（本模块默认按 CPU 数开 2~3 个）。

## 用法

调用方**必须是后台线程**（``PreviewWorker.run`` / ``SourceThumbnailsWorker.run``
之类），这些函数是**阻塞**的：

- :func:`render_jpeg`：渲一页，返回 JPEG 字节（缩略图 / 大图预览）；
- :func:`page_count`：页数；
- :func:`extract_page`：单页"提取图片"落盘（与批量提取逐位一致）；
- :func:`shutdown`：退出前收子进程。

## 降级

子进程起不来（打包漏模块 / 权限 / OOM）时**自动退回进程内渲染**（并持
``single_flight`` 单飞锁），行为与改动前一致——宁可慢一点，也不能让缩略图
整片不出来。降级只发生一次，之后一直走进程内（避免每个请求都白试一遍）。

``GUJI_PDF_RENDER=inproc`` 可强制关闭出进程（排障 / 单测用）。
"""

from __future__ import annotations

import io as _io
import os
import threading
from pathlib import Path
from typing import Any

#: 环境变量：``inproc`` = 强制进程内渲染（排障与自测用）
ENV_MODE = "GUJI_PDF_RENDER"

#: 子进程数上限。**不要贪多**：每个进程都在抢物理核，占满之后 GUI 的事件
#: 循环自己就没 CPU 了（用户同样会觉得"卡"，只是卡法不同）。
MAX_WORKERS = 3

#: 单次渲染的超时（秒）。超时说明子进程卡死/被杀，按失败处理并降级。
#: 一页 JPX 最慢见过 ~1.2s，给 60s 是给超大矢量页留余量。
CALL_TIMEOUT_S = 60.0

_LOCK = threading.Lock()
_pool: Any = None
_disabled = False
#: 正在收尾（``shutdown()`` 之后）：不再建池、也不再刷"降级"日志
_closing = False
_stats = {"renders": 0, "extracts": 0, "page_counts": 0, "fallbacks": 0}


# --------------------------------------------------------------------- 子进程侧
def _child_render_jpeg(pdf_path: str, page_index: int, edge: int,
                       quality: int, fmt: str,
                       pages_dir: str | None = None) -> bytes:
    """子进程里渲一页并编码成字节（**纯函数，可 pickle**）。

    ``edge``：目标最长边；**0 = 不缩放**（要原始分辨率，与 ``PreviewWorker``
    的 ``longest_edge=0`` 语义一致）。

    ``pages_dir``：**已提取的整页图目录**（``stages/extract``）。命中就用那张
    JPEG 缩（21ms），不再回 PDF 解 JPX（~850ms）——"提取之后还得等缩略图"
    就是缺了这一步。图读不出来时静默回落到 PDF 渲染。
    """
    if pages_dir:
        data = _thumb_from_page_image(pages_dir, page_index, edge, quality,fmt)
        if data:
            return data
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


# --------------------------------------------------------------------- JPX 快速通道
#: 走快速通道的**目标边长上限**：只有"要小图"时才值得。要整页原图（提取）时
#: 反而不划算——OpenJPEG 全分辨率解码比 MuPDF 慢一个数量级（实测 27s vs 1s）。
JPX_FAST_MAX_EDGE = 512

#: 至少要降到这个倍率才开子进程（1/4 以下才有赚头；1/2 反而比 MuPDF 慢）
JPX_FAST_MIN_REDUCE = 2

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
        Path(__file__).resolve().parents[2] / "tools" / "opj",
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


def _run_opj_thumb(opj: str, stream: bytes, ext: str, reduce: int,
                   edge: int, quality: int) -> bytes:
    """把 JPX 码流交给 ``opj_decompress -r N``，再缩成目标尺寸。失败返回空字节。"""
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
                capture_output=True,
                timeout=30,
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


def _child_page_count(pdf_path: str) -> int:
    """子进程里读页数。"""
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


# --------------------------------------------------------------------- 进程内兜底
def _inproc_render_jpeg(pdf_path: str, page_index: int, edge: int,
                        quality: int, fmt: str) -> bytes:
    """进程内渲染（降级路径）：与子进程那份**逐字一致**，只是持单飞锁。

    锁是必须的：PyMuPDF 不是线程安全的，而这条路上仍可能有别的线程在渲。
    """
    from desktop.workers.render_lock import single_flight

    with single_flight():
        return _child_render_jpeg(pdf_path, page_index, edge, quality, fmt)


# --------------------------------------------------------------------- 池管理
def _worker_count() -> int:
    """池大小：按 CPU 数给 2~3 个（见 ``MAX_WORKERS`` 的说明）。"""
    cpu = os.cpu_count() or 2
    return max(1, min(MAX_WORKERS, cpu - 2 if cpu > 4 else 2))


def _mode() -> str:
    """当前模式：``proc`` / ``inproc``。"""
    if _disabled:
        return "inproc"
    if (os.environ.get(ENV_MODE) or "").strip().lower() in ("inproc", "0", "off"):
        return "inproc"
    return "proc"


def offloaded() -> bool:
    """渲染是否**真的**在子进程里做（宿主据此决定要不要"让出 GIL"的 sleep）。"""
    return _mode() == "proc" and _pool is not None


def workers() -> int:
    """池大小（批量路径按它决定一批渲几页）。"""
    return _worker_count()


def _pool_or_none():
    """惰性建池；失败返回 None（此后永久走进程内）。"""
    global _pool, _disabled
    if _closing or _mode() != "proc":
        return None
    with _LOCK:
        if _pool is not None:
            return _pool
        if _disabled:
            return None
        try:
            from concurrent.futures import ProcessPoolExecutor

            _pool = ProcessPoolExecutor(max_workers=_worker_count())
            return _pool
        except Exception as exc:  # noqa: BLE001 - 起不来就降级，绝不抛给界面
            _disabled = True
            print(f"[渲染服务] 子进程池启动失败，退回进程内渲染：{exc}")
            return None


def _call(fn, *args):
    """把一次渲染交给子进程；任何异常都降级为进程内（并只记一次）。"""
    global _disabled
    pool = _pool_or_none()
    if pool is None:
        raise _NoPool()
    try:
        return pool.submit(fn, *args).result(timeout=CALL_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 - 池崩了（OOM/被杀/超时）
        with _LOCK:
            _disabled = True
        if not _closing and not _silent_failure(exc):
            print(
                "[渲染服务] 子进程渲染失败，本次起退回进程内渲染："
                f"{type(exc).__name__}: {exc}"
            )
        raise _NoPool() from exc


class _NoPool(Exception):
    """内部信号：没有可用的子进程池 → 走进程内。"""


def _silent_failure(exc: BaseException) -> bool:
    """这次失败要不要**不吭声**（只回落）。

    情形：解释器正在退出——``concurrent.futures`` 的 atexit 已经把池关掉，
    还在跑的后台线程再 submit 就会拿到 ``RuntimeError: cannot schedule new
    futures after shutdown``。那不是 bug，是收尾顺序；刷一行红字只会吓人。
    """
    return "after shutdown" in str(exc).lower()


def _fallback_count() -> None:
    _stats["fallbacks"] += 1


# --------------------------------------------------------------------- 对外 API
def render_jpeg(pdf_path, page_index: int, edge: int, quality: int = 70,
                fmt: str = "jpg") -> bytes:
    """渲一页并返回编码后的字节（**阻塞调用，只许在后台线程里用**）。

    缩略图用 ``edge=256, quality=70``；大图预览用 ``edge=视口边长, quality=80``。
    """
    _stats["renders"] += 1
    try:
        return _call(_child_render_jpeg, str(pdf_path), int(page_index),
                     int(edge), int(quality), str(fmt))
    except _NoPool:
        _fallback_count()
        return _inproc_render_jpeg(str(pdf_path), int(page_index),
                                   int(edge), int(quality), str(fmt))


def render_jpegs(pdf_path, pages, edge: int, quality: int = 70,
                 fmt: str = "jpg", pages_dir=None) -> list[bytes]:
    """**并行**渲多页，按入参顺序返回（每页一条；失败的那页是空字节）。

    为什么要"并行"这层：``render_jpeg`` 一次一页，池里的另外两个进程闲着，
    整本缩略图就还是串行的 0.7s/页。批量路径（导入缩略图、查看器补页）走
    这里，池内真正并发——3 个进程约 2.5~3 倍吞吐，且 GUI 依然一次都不冻。

    ⚠️ 只在**批量**时用：交互式单页（用户点一下要一页）用 ``render_jpeg``，
    否则多出来的调度与 pickle 纯属浪费。

    ``pages_dir``：**已提取的整页图目录**（见 :func:`_child_render_jpeg`）。
    给了它，已提取的页就从那张 JPEG 缩（21ms），不再解 JPX（850ms）。
    """
    pages = [int(p) for p in pages]
    if not pages:
        return []
    _stats["renders"] += len(pages)
    pages_text = str(pages_dir) if pages_dir else None
    specs = [
        (str(pdf_path), p, int(edge), int(quality), str(fmt), pages_text)
        for p in pages
    ]
    pool = _pool_or_none()
    if pool is None:
        _fallback_count()
        return [_inproc_render_jpeg(*spec) for spec in specs]
    try:
        results = [bytes(chunk) for chunk in pool.map(_child_render_safe, specs)]
        if results and not any(results):
            # ⚠️ **整批全空**是"子进程环境坏了"（缺 DLL / pymupdf 导不进来），
            #    不是"这几页恰好都坏"。必须抛出去走进程内兜底，否则调用方
            #    会把一本正经的书当"渲染成功但一张都没有"——静默丢图。
            raise RuntimeError("子进程整批渲染为空（子进程环境异常）")
        return results
    except Exception as exc:  # noqa: BLE001 - 池崩了：整批退回进程内
        with _LOCK:
            _disabled = True
        _fallback_count()
        if not _closing and not _silent_failure(exc):
            print(
                "[渲染服务] 批量渲染失败，本批退回进程内渲染："
                f"{type(exc).__name__}: {exc}"
            )
        return [_inproc_render_jpeg(*spec) for spec in specs]


def render_stream(pdf_path, pages, edge: int, quality: int = 70,
                  fmt: str = "jpg", on_page=None, pages_dir=None) -> None:
    """**并行渲多页，每渲好一页就回调**（``on_page(page, bytes)``）。

    ⚠️ 与 :func:`render_jpegs` 的分工（2026-10-21 实测教训）：

    - ``render_jpegs`` 是"整批一起交"，调用方只能**等整批回来**才写盘；
      一批 16 页 × ~1s ÷ 3 进程 = **5 秒多一张缩略图都不出现**——用户看到的
      就是"缩略图半天不出来"（比改之前还差，改之前的旧实现是逐页写的）。
    - 本函数用 ``as_completed`` 把结果**积压即交付**：第一批 3 张 ~1s 就落地，
      之后滚动交付；总量与并行度完全不变。

    回调在**调用线程**里执行（不是子进程），可以安全地写盘、emit Qt 信号。
    """
    pages = [int(p) for p in pages]
    if not pages or on_page is None:
        return
    _stats["renders"] += len(pages)
    pages_text = str(pages_dir) if pages_dir else None
    specs = [
        (str(pdf_path), p, int(edge), int(quality), str(fmt), pages_text)
        for p in pages
    ]
    pool = _pool_or_none()
    if pool is None:
        _fallback_count()
        for spec in specs:
            on_page(spec[1], _inproc_render_jpeg(*spec))
        return
    delivered: set[int] = set()
    try:
        from concurrent.futures import as_completed

        futures = {pool.submit(_child_render_safe, spec): spec[1] for spec in specs}
        for future in as_completed(futures):
            page = futures[future]
            on_page(page, future.result())
            delivered.add(page)
    except Exception as exc:  # noqa: BLE001 - 池崩了：剩下的退回进程内逐页渲
        with _LOCK:
            _disabled = True
        _fallback_count()
        if not _closing and not _silent_failure(exc):
            print(
                "[渲染服务] 流式渲染中断，剩余页退回进程内渲染："
                f"{type(exc).__name__}: {exc}"
            )
        for spec in specs:
            if spec[1] in delivered:
                continue  # 已经交付过的页不重渲
            on_page(spec[1], _inproc_render_jpeg(*spec))


def page_count(pdf_path) -> int:
    """PDF 页数（阻塞调用）。"""
    _stats["page_counts"] += 1
    try:
        return int(_call(_child_page_count, str(pdf_path)))
    except _NoPool:
        _fallback_count()
        import pymupdf as fitz

        document = fitz.open(str(pdf_path))
        try:
            return int(document.page_count)
        finally:
            document.close()


def extract_page(pdf_path, page_index: int, out_dir, zoom: float = 1,
                 ext: str = "jpg", quick: bool = True,
                 dpi: float = 300) -> dict:
    """单页「提取图片」落盘（阻塞调用）；返回 ``{ok, path, w, h, err}``。"""
    _stats["extracts"] += 1
    try:
        return dict(_call(_child_extract_page, str(pdf_path), int(page_index),
                          str(out_dir), float(zoom), str(ext), bool(quick),
                          float(dpi)) or {})
    except _NoPool:
        _fallback_count()
        from utils.pdf_extract import extract_single_page

        return extract_single_page(
            str(pdf_path), int(page_index), str(out_dir),
            zoom=zoom, ext=ext, quick=quick, dpi=dpi,
        )


def stats() -> dict:
    """运行计数（自测断言用）：``renders`` / ``extracts`` / ``page_counts`` /
    ``fallbacks`` / ``mode`` / ``workers``。"""
    return {
        **_stats,
        "mode": _mode(),
        "workers": _worker_count(),
        "offloaded": offloaded(),
    }


def reset_stats() -> None:
    """清零计数（自测用；不动池）。"""
    for key in _stats:
        _stats[key] = 0


def _child_warmup() -> bool:
    """子进程预热：把 pymupdf 的 import 提前做掉（首张缩略图不用等它）。"""
    import pymupdf  # noqa: F401 - 纯粹为了在子进程里完成导入

    return True


def prewarm() -> None:
    """**后台**把子进程池拉起来并预热（进任务详情页时调一次，幂等）。

    为什么需要：首次建池 + 每个子进程 import pymupdf 约 1.5s。不预热的话，
    这笔钱会落在"用户看到的第一张缩略图"上（进详情页先愣 1.5 秒）；预热之后
    它和页面构建并行，用户感知不到。

    ⚠️ 绝不阻塞调用线程（它在 GUI 线程被调用），也绝不因为起不来而报错。
    """
    if _mode() != "proc":
        return

    def _run() -> None:
        pool = _pool_or_none()
        if pool is None:
            return
        try:
            for _ in range(_worker_count()):
                pool.submit(_child_warmup)
        except Exception:  # noqa: BLE001 - 预热是加速，失败无所谓
            pass

    threading.Thread(target=_run, name="guji-render-prewarm", daemon=True).start()


def shutdown() -> None:
    """收掉子进程池（关程序/单测收尾）。

    ⚠️ 置 ``_closing`` 之后**不再建池**：关程序时还可能有后台线程在渲，
    它会安静地退回进程内（≤1s 一页）而不是刷一条"子进程渲染失败"的日志。
    """
    global _pool, _closing
    _closing = True
    with _LOCK:
        pool, _pool = _pool, None
    if pool is None:
        return
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception:  # noqa: BLE001 - 收尾尽力而为
        pass


__all__ = [
    "ENV_MODE",
    "JPX_FAST_MAX_EDGE",
    "extract_page",
    "offloaded",
    "jpx_fast_available",
    "page_count",
    "prewarm",
    "render_jpeg",
    "render_jpegs",
    "render_stream",
    "reset_stats",
    "shutdown",
    "stats",
    "workers",
]
