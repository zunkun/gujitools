# -*- coding: utf-8 -*-
"""第三步「改参数 / 翻页实时预览当前页」自测。

单步化之后正式产物只由「执行去底色」写 ``stages/rembg``；实时预览只算当前页、
只写系统临时目录，**绝不碰正式产物**。本模块钉住：

1. 改参数会触发防抖（不是每拖一格就全量重跑）；
2. 防抖到期只算**当前页**，结果落在临时目录；
3. 查看器优先显示临时结果；
4. 正式产物文件不被实时预览改写；
5. 参数回到最近一次成功执行的取值时，收起临时结果、回到正式成品。
"""

NAME = "rembg_live"
DEPENDS: list[str] = ["rembg"]
TITLE = "去底色实时预览"

import time
from pathlib import Path


def _wait(app, cond, timeout: float = 25.0) -> bool:
    """驱动事件循环直到 cond 成立或超时。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def run(ctx) -> None:
    from desktop.services import rembg_live as live_mod
    from tests.selftests._context import ok, pump

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid

    d.set_task(tid)
    d._select_stage(2)
    pump(app, times=6)

    panel = d.control_stack.widget(2)
    entry_path = d.rembg_viewer.current_entry_path()
    ok("（前置）第三步有可预览的当前页", entry_path is not None, str(entry_path))
    if not entry_path:
        return
    stem = Path(entry_path).stem
    formal = Path(repo.rembg_output_dir(tid)) / f"{stem}.png"
    ok("（前置）正式成品存在", formal.is_file(), str(formal))
    if not formal.is_file():
        return
    before = formal.read_bytes()

    # ---- 1. 改参数 → 防抖 ----
    d._live_timer.stop()
    d._live_done.clear()
    old_offset = panel.offset.value()
    panel.offset.setValue(old_offset + 17)
    pump(app, times=1, interval=0.0)
    ok("改 offset 触发防抖计时（不是每拖一格都重算）",
       d._live_timer.isActive())

    # ---- 2/3. 防抖到期只算当前页、写临时目录 ----
    d._live_timer.stop()
    d._maybe_run_live_preview()
    _wait(app, lambda: bool(d._live_done), timeout=25)
    ok("实时预览只算当前页", len(d._live_done) == 1, str(d._live_done))
    live = d.rembg_viewer.live_dir
    ok("预览结果落在系统临时目录",
       live is not None and Path(live) == live_mod.live_dir(tid), str(live))
    ok("临时结果文件存在",
       live is not None and (Path(live) / f"{stem}.png").is_file(),
       str(sorted(p.name for p in Path(live).glob("*.png"))) if live else "None")
    ok("查看器优先显示临时结果",
       live is not None
       and d.rembg_viewer._result_full_image() == Path(live) / f"{stem}.png",
       str(d.rembg_viewer._result_full_image()))

    # ---- 4. 正式产物不被实时预览改写 ----
    ok("实时预览不改写正式成品",
       formal.read_bytes() == before, str(formal))

    # ---- 5. 参数回到成功执行的取值 → 收起临时结果 ----
    snapshot = d._preview_run_snapshot()
    ok("（前置）能取到上次成功执行的参数快照", snapshot is not None, str(snapshot))
    if snapshot is not None:
        panel.apply_args(snapshot)
        d._live_timer.stop()
        d._maybe_run_live_preview()
        pump(app, times=4)
        ok("参数与正式执行一致时收起实时结果",
           d.rembg_viewer.live_dir is None, str(d.rembg_viewer.live_dir))
        ok("收起后显示的是正式成品",
           d.rembg_viewer._result_full_image() == formal,
           str(d.rembg_viewer._result_full_image()))

    # 收尾：别把临时目录留给后续模块
    d._reset_rembg_live()
