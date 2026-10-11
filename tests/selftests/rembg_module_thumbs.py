# -*- coding: utf-8 -*-
"""独立「去底色」模块页左栏缩略图自测（用户 2026-10-11 报「缩略图不显示」）。

故障机理：宿主 ``_warm_thumb_cache`` 此前**每张缓存就绪就调一次**
``viewer.set_cached_thumbs({单条})``，而查看器那边的实现内部走
``_load_thumbs_chunked``＝「重新装载」（代际令牌 +1、批次光标重置）——
初始批次的在飞回调被作废、单张刷新又被下一张的代际作废，左栏缩略图
几乎一张都落不了地。

修法：单张就绪**只记映射**，缓存 pass 结束后**整体替换一次**
（``set_cached_thumbs`` 本来就是整体替换语义，单条更新另有
``set_cached_thumb``）。本用例钉三件事：

1. 换源后走一条真实缓存 pass，``set_cached_thumbs`` **恰好被调一次**
   （旧实现按张数调 N 次，直接红）；
2. 缩略图条每一条都真的有了图标（最终要的是「显示」本身）；
3. 单张回调只记映射不碰查看器、旧批次的迟到完成回调被身份闸丢弃。
"""

from __future__ import annotations

from pathlib import Path

NAME = "rembg_module_thumbs"
DEPENDS: list[str] = ["modules_shell"]
TITLE = "独立去底色页·左栏缩略图（缓存 pass 整体替换）"


def _png(path: Path, gray: int = 200) -> Path:
    import numpy as np
    import utils

    utils.imwrite(path, np.full((64, 48, 3), gray, dtype="uint8"))
    return path


def run(ctx) -> None:
    from desktop.modules.rembg.page import RembgModulePage
    from tests.selftests._context import ok, wait_until

    tmp = Path(ctx.tmp) / "rembg_module_thumbs"
    tmp.mkdir(parents=True, exist_ok=True)
    page = RembgModulePage()
    try:
        # 缓存目录指到临时区：别把测试图写进真实的 ~/Documents/guji/singletask
        page._thumb_cache_dir = lambda: tmp / "thumbs"

        calls: list[dict] = []
        original_apply = page.viewer.set_cached_thumbs

        def spy(mapping: dict) -> None:
            calls.append(dict(mapping))
            original_apply(mapping)

        page.viewer.set_cached_thumbs = spy  # type: ignore[method-assign]

        # 三张小图当源（走真实的一条缓存 pass，worker 是 QThread、离屏可跑）
        images = tmp / "images"
        images.mkdir(exist_ok=True)
        paths = [_png(images / f"000{i}.png", 180 + i) for i in (1, 2, 3)]
        page.control.set_source(images)

        ok("给源后左栏条目建好", page.viewer.strip.count() == 3,
           str(page.viewer.strip.count()))
        ok("缓存 pass 结束前不整体替换（单张就绪只记映射）", calls == [],
           str(calls))

        # 等缓存 worker 跑完 + 完成回调把映射整体交给查看器
        applied = wait_until(ctx.app, lambda: len(calls) == 1, timeout=30)
        ok("缓存 pass 结束 → set_cached_thumbs 恰好一次（旧实现按张数 N 次）",
           applied and len(calls) == 1, str(len(calls)))
        ok("整体替换的映射覆盖全部源图",
           calls and set(calls[0]) == {str(p) for p in paths},
           str(sorted(calls[0]) if calls else None))

        # 最终要的是「显示」本身：三条都有非空图标
        shown = wait_until(ctx.app, lambda: all(
            not page.viewer.strip.item(r).icon().isNull()
            for r in range(page.viewer.strip.count())
        ), timeout=30)
        ok("缩略图条三条都落了图标", shown)

        # ---- 单元口径：单张回调 / 旧批次身份闸（不依赖线程时序）----
        calls.clear()
        mapping: dict[str, str] = {}
        page._thumb_cache_batch = mapping  # 让它成为"当前批"（身份相等）
        page._on_thumb_cached(0, "c.jpg", [paths[0]], mapping)
        page._on_thumb_cached(99, "d.jpg", [paths[0]], mapping)  # 越界下标
        page._on_thumb_cached(0, "", [paths[0]], mapping)        # 空缓存路径
        ok("单张就绪只记映射、不碰查看器",
           len(calls) == 0 and mapping == {str(paths[0]): "c.jpg"},
           f"calls={calls} mapping={mapping}")

        page._apply_cached_thumbs(mapping)
        ok("当前批的完成回调把映射整体交给查看器",
           len(calls) == 1 and calls[0] == {str(paths[0]): "c.jpg"},
           str(calls))

        calls.clear()
        page._thumb_cache_batch = {}  # 换源即换批：旧 mapping 身份已失效
        page._apply_cached_thumbs(mapping)
        ok("旧批的迟到完成回调被身份闸丢弃", calls == [], str(calls))
    finally:
        page.shutdown_workers()
        page.deleteLater()


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
