# -*- coding: utf-8 -*-
"""缩略图**按可见窗口懒加载**自测。

起因是用户 2026-10-21 的口径：

> 所有步骤缩略图不用全部一次加载

早先的折中是「分批补齐」（首批 10、之后每批 12、间隙 150ms）：单批小了，
但**仍然会把 1000+ 页全部解完**——一本千页书要持续解码十几秒，用户实际
只看得见首屏那几行。现在只在**可见窗口**（视口首末行 ± 预取边距）内解码，
滚到哪里才补哪里。

断言线：

1. **只装窗口内的行**：初始窗口 (0,5) 时，到达的恰好是 0..15（下方 10 行
   预取），更靠后的一张未到；
2. **滚动后补对应段**：窗口移到 (20,25) 后，到达 16..35，36 之后仍不加载；
3. **不滚永不加载尾部**：尾部行在整个用例里一次都没被解码；
4. **子集刷新不动主装载状态**：``_load_thumbs_subset`` 只补可见的指定行，
   不改变 ``_thumb_loaded``/主代际（否则用户后续滚动会永远不加载）；
5. **重新装载作废旧批次**：代际 +1、已装载集合清空。

⚠️ 用真实 ``ImageViewerWidget`` + 真实 ``ImageListWorker``（图片很小，解码很快）。
可见窗口直接在**图条实例**上打桩（``visible_row_range``）——本用例测的是
``ThumbsMixin`` 的窗口调度，不该被离屏环境下不可靠的视口几何牵着走。
"""

from __future__ import annotations

import time
from pathlib import Path

NAME = "thumbs_chunked"
DEPENDS: list[str] = []
TITLE = "缩略图按可见窗口懒加载"


def run(ctx) -> None:
    import shutil
    import tempfile

    from PySide6.QtGui import QImage

    from desktop.components import viewers as viewers_pkg
    from desktop.components.viewers import thumb_strip, thumbs_loader
    from desktop.workers import ImageListWorker
    from tests.selftests._context import ok

    app = ctx.app
    mixin = thumbs_loader.ThumbsMixin
    saved_cfg = (
        mixin.RECHECK_MS,
        mixin.VISIBLE_MARGIN_UP,
        mixin.VISIBLE_MARGIN_DOWN,
        mixin.FALLBACK_VISIBLE,
        mixin.BATCH_MAX,
    )
    real_set_icon = thumb_strip.ThumbStrip.set_item_icon
    tmp = Path(tempfile.mkdtemp(prefix="guji_chunk_"))
    widget = None
    arrived: list[int] = []
    target_strip = None
    window = [0, 5]
    total = 60
    try:
        paths = []
        for index in range(total):
            img = QImage(40, 56, QImage.Format.Format_RGB32)
            img.fill(0xFF445566)
            path = tmp / f"p{index:02d}.png"
            img.save(str(path))
            paths.append(path)

        # 窗口检查的延迟调短（策略不变，只让用例跑得快）
        setattr(mixin, "RECHECK_MS", 30)

        # ⚠️ 先把图条造好再打补丁：补丁要按**本条图条**过滤。set_item_icon 打
        # 在类上，而前面的用例可能还留着别的图条在后台回填，不筛就会把别处的
        # 下标混进来（表现为同一下标各出现两次）。
        widget = viewers_pkg.ImageViewerWidget()
        widget.strip.clear()
        for p in paths:
            widget.strip.add_page_item(p.stem)
        target_strip = widget.strip
        # 可见窗口打桩：本用例只测窗口调度，不要依赖离屏视口几何
        target_strip.visible_row_range = lambda: (window[0], window[1])  # type: ignore[method-assign]

        def _spy_set_icon(self, index, image, path, label):
            if self is target_strip:
                arrived.append(int(index))
            real_set_icon(self, index, image, path, label)

        thumb_strip.ThumbStrip.set_item_icon = _spy_set_icon

        def _wait(predicate, timeout: float = 10.0) -> bool:
            deadline = time.time() + timeout
            while time.time() < deadline:
                app.processEvents()
                if predicate():
                    return True
                time.sleep(0.01)
            return False

        # ---- 1. 初始窗口 (0,5)：只装 0..15（下方预取 10 行）----
        widget._load_thumbs(widget.strip, paths)
        window_hi = window[1] + mixin.VISIBLE_MARGIN_DOWN
        first_expected = list(range(0, window_hi + 1))
        got = _wait(lambda: len(set(arrived)) >= len(first_expected))
        ok("首屏窗口内（含预取边距）的行都装上了",
           got and sorted(set(arrived)) == first_expected,
           f"到达={sorted(set(arrived))[:20]}…共 {len(set(arrived))}")
        ok("窗口之外的行一张都没加载（不滚不为看不见的页付 CPU）",
           max(arrived, default=-1) == window_hi,
           f"最大下标={max(arrived, default=-1)}，窗口上界={window_hi}")
        ok("首屏装载后已装载集合恰是窗口内的行",
           set(widget._thumb_loaded) == set(first_expected),
           f"{sorted(widget._thumb_loaded)[:20]}…")
        ok("装载即接管滚动信号（用户滚动时才会补新的段）",
           widget._thumb_strip is target_strip)

        # ---- 2. 窗口移到 (20,25)：补 16..35 ----
        window[0], window[1] = 20, 25
        widget._on_thumb_scroll()
        second_expected = list(range(window[0] - mixin.VISIBLE_MARGIN_UP,
                                     window[1] + mixin.VISIBLE_MARGIN_DOWN + 1))
        got = _wait(lambda: set(second_expected) <= set(arrived))
        ok("滚动到新窗口后，新露出的那几行被补上",
           got, f"缺={sorted(set(second_expected) - set(arrived))}")
        ok("补的是新窗口段，不是把整本书重解一遍",
           sorted(set(arrived)) == first_expected + second_expected,
           f"共 {len(set(arrived))} 张（总 {total}）")
        ok("尾部仍未加载（不滚到底就永远不付这份 CPU）",
           max(arrived, default=-1) < total - 1,
           f"最大下标={max(arrived, default=-1)}，共 {total} 张")

        # ---- 3. 子集刷新：只补可见的指定行、不动主装载状态 ----
        gen_before = widget._thumb_generation
        loaded_before = set(widget._thumb_loaded)
        subset_rows = [0, 22, 50]        # 22 在当前窗口 (16..35) 内
        subset_arrived: list[int] = []

        def _subset_worker(start, end):
            return ImageListWorker(
                [paths[row] for row in subset_rows[start:end]],
                edge=ThumbStrip_edge(),
            )

        widget._load_thumbs_subset(
            len(subset_rows),
            make_worker=_subset_worker,
            sink=lambda index, image, _path: (
                subset_arrived.append(subset_rows[index])
                if 0 <= index < len(subset_rows) else None
            ),
            strip=widget.strip,
            row_map=subset_rows,
        )
        _wait(lambda: bool(subset_arrived))
        ok("子集刷新只补**可见**的那一行（22），窗口外的 0/50 不刷",
           subset_arrived == [22], str(subset_arrived))
        ok("子集刷新不改变主装载器的代际与已装载集合",
           widget._thumb_generation == gen_before
           and set(widget._thumb_loaded) == loaded_before,
           f"代际 {gen_before}→{widget._thumb_generation}")

        # ---- 4. 重新装载：代际 +1、已装载集合清空 ----
        gen_before = widget._thumb_generation
        window[0], window[1] = 0, 5   # 回到首屏窗口，"只装当前窗口"才是可判的
        widget._load_thumbs(widget.strip, paths)
        ok("重新装载会作废旧批次（代际 +1）",
           widget._thumb_generation == gen_before + 1,
           f"{gen_before} → {widget._thumb_generation}")
        ok("重新装载后只装当前窗口，不沿用上一轮的已装载集合",
           set(widget._thumb_loaded) == set(first_expected)
           or set(widget._thumb_loaded) <= set(first_expected),
           f"{sorted(widget._thumb_loaded)[:20]}…")
    finally:
        thumb_strip.ThumbStrip.set_item_icon = real_set_icon
        (
            mixin.RECHECK_MS,
            mixin.VISIBLE_MARGIN_UP,
            mixin.VISIBLE_MARGIN_DOWN,
            mixin.FALLBACK_VISIBLE,
            mixin.BATCH_MAX,
        ) = saved_cfg
        if widget is not None:
            widget.shutdown_workers()
            widget.deleteLater()
        shutil.rmtree(tmp, ignore_errors=True)


def ThumbStrip_edge() -> int:
    """子集刷新用的解码边长（真实 ``ThumbStrip.decode_edge`` 要 QWidget，这里给常量）。"""
    return 128
