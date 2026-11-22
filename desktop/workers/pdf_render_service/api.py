# -*- coding: utf-8 -*-
"""对外 API：渲页 / 批量渲 / 页数 / 单页提取 / 预热（均为阻塞调用）。"""

from __future__ import annotations

import threading

from .child import (
    _child_extract_page,
    _child_page_count,
    _child_render_jpeg,
    _child_render_safe,
    _child_warmup,
)
from .inproc import _inproc_render_jpeg
from .pool import (
    _NoPool,
    _call,
    _drop_pool,
    _fallback_count,
    _mode,
    _note_success,
    _pool_or_none,
    _stats,
    _worker_count,
)


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
    pool = _pool_or_none("render")
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
        _note_success()
        return results
    except Exception as exc:  # noqa: BLE001 - 池崩了：整批退回进程内
        _drop_pool("render", exc)
        _fallback_count()
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
    pool = _pool_or_none("render")
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
        _note_success()
    except Exception as exc:  # noqa: BLE001 - 池崩了：剩下的退回进程内逐页渲
        _drop_pool("render", exc)
        _fallback_count()
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
    """单页「提取图片」落盘（阻塞调用）；返回 ``{ok, path, w, h, err}``。

    ⚠️ 走**独立的提取池**（``kind="extract"``）：它绝不排在缩略图/预览批次
    后面——否则用户点一页提取时会看到"一直转圈"（见 ``EXTRACT_WORKERS``）。
    """
    _stats["extracts"] += 1
    try:
        return dict(_call(_child_extract_page, str(pdf_path), int(page_index),
                          str(out_dir), float(zoom), str(ext), bool(quick),
                          float(dpi), kind="extract") or {})
    except _NoPool:
        _fallback_count()
        from utils.pdf_extract import extract_single_page

        return extract_single_page(
            str(pdf_path), int(page_index), str(out_dir),
            zoom=zoom, ext=ext, quick=quick, dpi=dpi,
        )


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
