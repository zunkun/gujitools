# -*- coding: utf-8 -*-
"""第三步「改参数实时预览当前页」自测。

覆盖三条边界（都是设计里刻意划的）：

1. 参数与「生成预览」不同时，才算当前页；一致时不白算。
2. **一次只算一页**，全量留给「生成预览」按钮。
3. 实时结果只落系统临时目录，**绝不写** stages/rembgpreview
   （否则各页参数不一致，「提交本次任务」会把新旧混在一起）。

另含 offset 滑块化本身的断言（范围/默认值/回填同步）。

异步：单页去底色跑在 QThread 里，断言前先驱动事件循环等它回来。
"""

import time
from pathlib import Path

NAME = "rembg_live"
DEPENDS: list[str] = ["tasklist"]
TITLE = "第三步实时预览"


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
    from tests.gui_shot import make_fake_page_image
    from tests.selftests._context import ok, pump, show_detail

    app, d, repo = ctx.app, ctx.d, ctx.repo

    # ---- 专用任务：2 页，带 extract 产物与检测框（最小侵入，用完即删）----
    tid = repo.create_task(Path("D:/samples/实时预览样例.pdf"), "hash-live", "实时预览样例")
    extract_dir = repo.extract_output_dir(tid)
    extract_dir.mkdir(parents=True, exist_ok=True)
    for page in (1, 2):
        make_fake_page_image(extract_dir / f"{page:03d}.jpg", f"第 {page} 页\n\n测试正文内容")
    repo.save_pages(
        tid,
        [{"file": str(extract_dir / f"{p:03d}.jpg"), "label": f"{p:03d}"} for p in (1, 2)],
    )
    for page in (1, 2):
        key = f"{page:03d}"
        repo.save_image_size(tid, key, 560, 800)
        repo.save_detect_boxes(
            tid, key, [[40, 40, 270, 760], [290, 40, 520, 760]], origin="auto"
        )

    # 造一条「生成预览」成功记录：它是"原本去底色参数"的比对基准。
    # parameters 必须与面板默认值一致，否则末段"参数没变就不重算"验不出来。
    repo._save_runs(tid, {"rembg": [{
        "run_id": f"{tid}-rembg", "status": "success",
        "parameters": {"area": 1, "type": 1, "offset": 0, "seal": False,
                       "sealcolor": False, "sealarea": 80, "sealmin_sat": 50},
        "done": 2, "total": 2,
        "started_at": time.time() - 60, "finished_at": time.time() - 30,
        "output_path": None,
    }]})

    d.set_task(tid)
    pump(app)
    panel = show_detail(ctx, stage=2)
    pump(app)

    preview_dir = Path(repo.rembg_preview_output_dir(tid))
    before = sorted(p.name for p in preview_dir.glob("*")) if preview_dir.exists() else []

    # ---- offset 滑块 ----
    ok("offset 是滑块而非数字框", panel.offset.inherits("QSlider"))
    ok("offset 范围 -100 ~ 100",
       (panel.offset.minimum(), panel.offset.maximum()) == (-100, 100))
    ok("offset 默认 0", panel.offset.value() == 0)
    ok("滑块右侧是可直接输入的文本框", panel.offset_input.text() == "0")
    _validator = panel.offset_input.validator()
    ok("文本框限定 -100 ~ 100",
       _validator is not None
       and (_validator.bottom(), _validator.top()) == (-100, 100),
       f"{getattr(_validator, 'bottom', lambda: None)()} ~ "
       f"{getattr(_validator, 'top', lambda: None)()}")

    # ---- 右侧不能被浮动的垂直滚动条压住 ----
    from PySide6.QtCore import QPoint
    from qfluentwidgets import ScrollArea

    from desktop.ui import theme as T

    scroll = panel.findChild(ScrollArea)
    if scroll is not None:
        vp = scroll.viewport()
        box = panel.offset_input
        limit = vp.width() - T.SCROLLBAR_WIDTH
        left_edge = box.mapTo(vp, QPoint(0, 0)).x()
        right_edge = box.mapTo(vp, QPoint(box.width(), 0)).x()
        ok("数字框右缘未被垂直滚动条压住",
           right_edge <= limit + 1,
           f"右缘 {right_edge} vs 可用 {limit}")
        # 更直接的一条：整框必须完整落在可视区内（宽度没被压掉/裁掉）
        visible = min(right_edge, limit) - left_edge
        ok("数字框完整可见（数值能看到）",
           visible >= box.width() - 2,
           f"可见 {visible} / 实际宽 {box.width()}（左缘 {left_edge}，右缘 {right_edge}，可用 {limit}）")

    # ---- 参数改动 → 防抖 ----
    d._live_timer.stop()
    panel.offset.setValue(23)
    pump(app, times=1, interval=0.0)
    ok("改 offset 触发防抖计时（不是每次拖动都立刻算）", d._live_timer.isActive())
    ok("拖动滑块时文本框同步", panel.offset_input.text() == "23")

    # 反向：直接在文本框里敲 → 滑块要跟着走，且同样触发防抖
    d._live_timer.stop()
    panel.offset_input.setText("-40")
    pump(app, times=1, interval=0.0)
    ok("在文本框输入时滑块同步", panel.offset.value() == -40)
    ok("文本框改动同样触发防抖计时", d._live_timer.isActive())

    # ---- 节流/防抖：连续拖动期间一次都不算，只认停下来之后的那一次 ----
    d._live_done.clear()
    d._live_timer.stop()
    for value in (5, 9, 13, 17, 21):
        panel.offset.setValue(value)
        pump(app, times=1, interval=0.0)
    ok("连续拖动期间不触发重算（防抖生效，不是每动一格算一次）",
       not d._live_done, f"已算 {len(d._live_done)} 页")
    ok("拖动期间计时器被反复重置（保持待发）", d._live_timer.isActive())

    # 拖动同步信号不应重复上报：一次 setValue 只发一次 param_edited
    fired = []
    _probe = lambda: fired.append(1)  # noqa: E731 — 需要具名引用才能精确断开
    panel.param_edited.connect(_probe)
    panel.offset.setValue(33)
    pump(app, times=1, interval=0.0)
    ok("滑块一次改动只上报一次 param_edited（不因同步文本框而重复）",
       len(fired) == 1, f"实际 {len(fired)} 次")
    panel.param_edited.disconnect(_probe)
    d._live_timer.stop()
    # 复原成上一步的取值，后面的断言依赖它
    panel.offset.setValue(-40)
    pump(app, times=1, interval=0.0)
    d._live_timer.stop()

    # 输入中途（只敲了负号）不能把滑块打回去，否则没法正常输负数
    d._live_timer.stop()
    panel.offset_input.setText("-")
    pump(app, times=1, interval=0.0)
    ok("只输入负号时不改变滑块", panel.offset.value() == -40)
    panel.offset_input.setText("-40")
    pump(app, times=1, interval=0.0)

    # ---- 手动走一次（跳过防抖等待）----
    d._live_timer.stop()
    d._live_done.clear()
    d._maybe_run_live_preview()
    _wait(app, lambda: bool(d._live_done), timeout=25)

    ok("按新参数算出了当前页", bool(d._live_done))
    ok("一次只算一页（不是全量）", len(d._live_done) == 1, f"{len(d._live_done)} 页")
    ok("预览区已切到实时暂存目录", d.rembg_viewer.live_dir is not None)

    from desktop.services import rembg_live as live_mod

    live_dir = d.rembg_viewer.live_dir
    ok("实时目录就是系统临时目录（与正式产物物理分离）",
       live_dir is not None and Path(live_dir) == live_mod.live_dir(tid),
       f"{live_dir}")

    files = sorted(p.name for p in Path(live_dir).glob("*.png")) if live_dir else []
    ok("实时结果已落盘到暂存目录", len(files) == 1, f"{files}")

    after = sorted(p.name for p in preview_dir.glob("*")) if preview_dir.exists() else []
    ok("stages/rembgpreview 未被实时预览改动", before == after,
       f"前 {before} / 后 {after}")

    # ---- 参数回到「生成预览」时的取值 → 丢弃实时结果，回到正式产物 ----
    d._live_done.clear()
    panel.offset.setValue(0)
    panel.apply_args({"offset": 0})
    d._live_timer.stop()
    d._maybe_run_live_preview()
    pump(app, times=4)
    ok("参数与正式预览一致时不再重算（live 目录已撤下）",
       d.rembg_viewer.live_dir is None, f"{d.rembg_viewer.live_dir}")

    # 收尾：删掉专用任务，别给后续用例留下多余条目
    try:
        repo.delete_task(tid)
    except Exception:
        pass
