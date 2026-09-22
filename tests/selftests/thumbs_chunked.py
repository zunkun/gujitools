# -*- coding: utf-8 -*-
"""缩略图**分批**装载自测。

起因是用户反馈：「刚点进详情页第一步，风扇突然转快」。根因是原先把全部页面
一次性丢给一个 ``ImageListWorker``，它在紧循环里连续做缩放解码 + 平滑缩放，
一个核直接打满；而首屏看得见的只有最上面几行。

断言线：

1. **首批立即、且只有首批那么多**：装载后经事件循环就能拿到前 ``FIRST_BATCH``
   张，而更靠后的下标一张未到——这就是"CPU 不再一次性打满"的机制本身；
2. **其余确实延后**：首批之后到 ``BATCH_DELAY_MS`` 之前不再有新图到达
   （用真实时间验证，不是只看代码）；
3. **最终不丢图**：全部页面最终都会加载到，且总耗时 ≥ 延迟窗口（真的分了批）；
4. **重新装载重置进度**：切阶段/切任务再调时，分批光标回到开头、代际 +1；
5. **旧批次作废**：上一代的「完成」回调不再续批（否则会串图）。

⚠️ 用真实 ``ImageViewerWidget`` + 真实 ``ImageListWorker``（图片很小，解码很快），
只把到达目标 ``ThumbStrip.set_item_icon`` 换成记录函数来观测时序。
"""

from __future__ import annotations

import time
from pathlib import Path

NAME = "thumbs_chunked"
DEPENDS: list[str] = []
TITLE = "缩略图分批装载"


def run(ctx) -> None:
    import shutil
    import tempfile

    from PySide6.QtGui import QImage

    from desktop.components import viewers as viewers_pkg
    from desktop.components.viewers import thumb_strip, thumbs_loader
    from tests.selftests._context import ok

    app = ctx.app
    mixin = thumbs_loader.ThumbsMixin
    saved_cfg = (
        mixin.FIRST_BATCH,
        mixin.SUCCESSIVE_BATCH,
        mixin.BATCH_DELAY_MS,
        mixin.BATCH_GAP_MS,
    )
    real_set_icon = thumb_strip.ThumbStrip.set_item_icon
    tmp = Path(tempfile.mkdtemp(prefix="guji_chunk_"))
    widget = None
    arrived: list[int] = []
    target_strip = None
    try:
        paths = []
        for index in range(30):
            img = QImage(40, 56, QImage.Format.Format_RGB32)
            img.fill(0xFF445566)
            path = tmp / f"p{index:02d}.png"
            img.save(str(path))
            paths.append(path)

        # 缩小批尺寸/缩短延迟让用例跑得快；**策略本身不变**
        mixin.FIRST_BATCH = 5
        mixin.SUCCESSIVE_BATCH = 8
        mixin.BATCH_DELAY_MS = 800
        mixin.BATCH_GAP_MS = 60

        # ⚠️ 先把图条造好再打补丁：补丁要按**本条图条**过滤。set_item_icon 打
        # 在类上，而前面的用例可能还留着详情页自己的图条在后台回填，不筛就会
        # 把别处的下标混进来（表现为同一批下标各出现两次）。
        widget = viewers_pkg.ImageViewerWidget()
        widget.strip.clear()
        for p in paths:
            widget.strip.add_page_item(p.stem)
        target_strip = widget.strip

        def _spy_set_icon(self, index, image, path, label):
            if self is target_strip:
                arrived.append(int(index))
            real_set_icon(self, index, image, path, label)

        thumb_strip.ThumbStrip.set_item_icon = _spy_set_icon

        t0 = time.time()
        widget._load_thumbs(widget.strip, paths)
        ok("装载后立即记了首批光标（首批不等任何延迟）",
           widget._thumb_next == mixin.FIRST_BATCH,
           f"cursor={widget._thumb_next}")

        # ---- 1. 首批立即到齐，且只有首批 ----
        deadline = time.time() + 0.4
        while time.time() < deadline and len(arrived) < mixin.FIRST_BATCH:
            app.processEvents()
            time.sleep(0.01)
        ok("首批经事件循环即可到达",
           len(arrived) == mixin.FIRST_BATCH, f"到达={sorted(arrived)}")
        ok("首批只含最前面几张，更靠后的下标一张未到",
           sorted(arrived) == list(range(mixin.FIRST_BATCH)),
           f"到达={sorted(arrived)}")

        # ---- 2. 延迟窗口内不再派发下一批 ----
        while time.time() - t0 < (mixin.BATCH_DELAY_MS / 1000) * 0.7:
            app.processEvents()
            time.sleep(0.02)
        ok("首批之后到延迟到期前，一张新图都没到（CPU 得以空闲）",
           len(arrived) == mixin.FIRST_BATCH,
           f"已到 {len(arrived)} 张（延迟 {mixin.BATCH_DELAY_MS}ms 未到）")

        # ---- 3. 最终全部加载，且确实是"分了几批" ----
        deadline = time.time() + 15
        while time.time() < deadline and len(arrived) < len(paths):
            app.processEvents()
            time.sleep(0.05)
        ok("最终每一张都加载到（分批不等于丢图）",
           sorted(arrived) == list(range(len(paths))),
           f"共到 {len(arrived)}/{len(paths)} 张")
        ok("总耗时 ≥ 延迟窗口（真的分了批，不是又退回一次性）",
           (time.time() - t0) * 1000 >= mixin.BATCH_DELAY_MS,
           f"耗时 {(time.time() - t0) * 1000:.0f}ms")

        # ---- 4. 重新装载：光标回到开头、代际 +1 ----
        gen_before = widget._thumb_generation
        widget._load_thumbs(widget.strip, paths)
        ok("重新装载会作废旧批次（代际 +1）",
           widget._thumb_generation == gen_before + 1,
           f"{gen_before} → {widget._thumb_generation}")
        ok("重新装载后分批光标从开头重走",
           widget._thumb_next == mixin.FIRST_BATCH,
           f"cursor={widget._thumb_next}")

        # ---- 5. 代际守卫：旧批次的「完成」回调不得再续批 ----
        widget._thumb_timer.stop()
        widget._thumb_next = mixin.FIRST_BATCH  # 假装这一轮还没加载完
        widget._on_thumb_batch_done(gen_before)  # 上一代的完成回调
        ok("旧代际的批次完成回调不再续批（作废真的生效）",
           not widget._thumb_timer.isActive())
        widget._on_thumb_batch_done(widget._thumb_generation)
        ok("当前代际的批次完成回调会安排下一批",
           widget._thumb_timer.isActive())
        widget._thumb_timer.stop()
    finally:
        thumb_strip.ThumbStrip.set_item_icon = real_set_icon
        (
            mixin.FIRST_BATCH,
            mixin.SUCCESSIVE_BATCH,
            mixin.BATCH_DELAY_MS,
            mixin.BATCH_GAP_MS,
        ) = saved_cfg
        if widget is not None:
            widget.shutdown_workers()
            widget.deleteLater()
        shutil.rmtree(tmp, ignore_errors=True)
