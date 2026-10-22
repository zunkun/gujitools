# -*- coding: utf-8 -*-
"""第三步「改参数实时预览当前页」自测。

覆盖四条边界（都是设计里刻意划的）：

1. 参数与「生成预览」不同时，才算当前页；一致时不白算。
2. **一次只算一页**，全量留给「生成预览」按钮。
3. **增量落盘**（用户 2026-10-18 起）：该页去底色结果写
   ``stages/rembgpreview``，白底转透明的成品图写 ``stages/rembg``（整图，不裁）；
   两个目录允许不完整（用户预览了哪一页，那一页才有产物）。
4. ``stages/rembg`` 里有零星应用图**不代表**本步已提交——写图前先落 ``.draft``
   哨兵，第四步只有哨兵不存在时才认这批图（用户 2026-10-18 原话：有零星图片
   ≠ 已提交，必须提交下一步才能用）。提交的整目录重建会顺带删掉哨兵。

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
    from tests.selftests._context import make_fake_page_image, ok, pump, show_detail

    app, d, repo = ctx.app, ctx.d, ctx.repo

    # ---- 专用任务：2 页，带 extract 产物与检测框（最小侵入，用完即删）----
    tid = repo.create_task(Path("D:/samples/实时预览样例.pdf"), "hash-live", "实时预览样例")
    # ⚠️ 实时预览暂存目录在 tests/tmp/guji_live_preview/<task_id>/，**跨运行共享**
    #    而每轮测试的任务号都从 0001 重排——批内前面的模块占掉了几个号之后，
    #    本模块的任务号可能撞上历史运行的残留目录（'001.png' 混进断言，
    #    2026-10-12 last_stage→rembg_live 连跑必红的根因）。开场先清自己的。
    from desktop.services import rembg_live as _live_mod

    _live_mod.reset(tid)
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
    ok("开场：正式预览目录里还没有任何产物（后面要看增量落盘补进来）",
       not preview_dir.exists() or not any(preview_dir.iterdir()))

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

    # ⚠️ 「显示优先、落盘异步」（用户 2026-10-18）：大图在去底色一算完就上屏，
    #    写正式产物目录是**之后**的事 ⇒ 断言文件前必须等落盘那一单收敛。
    _wait(app, lambda: d._live_persist_done.get("001") is not None, timeout=25)
    ok("落盘任务也已收敛（显示不被落盘阻塞）",
       d._live_persist_done.get("001") is not None)

    from desktop.services import rembg_live as live_mod

    live_dir = d.rembg_viewer.live_dir
    ok("实时目录就是系统临时目录（与正式产物物理分离）",
       live_dir is not None and Path(live_dir) == live_mod.live_dir(tid),
       f"{live_dir}")

    files = sorted(p.name for p in Path(live_dir).glob("*.png")) if live_dir else []
    ok("实时结果已落盘到暂存目录", len(files) == 1, f"{files}")

    # ---- 增量落盘（新契约，用户 2026-10-18）----
    preview_files = (
        sorted(p.name for p in preview_dir.glob("*")) if preview_dir.exists() else []
    )
    ok("该页去底色结果已增量写进 stages/rembgpreview",
       preview_files == ["001.png"], f"{preview_files}")
    ok("正式预览那份与实时结果逐字节一致（同一份去底色产物）",
       (preview_dir / "001.png").exists()
       and live_dir is not None
       and (preview_dir / "001.png").read_bytes()
       == (Path(live_dir) / "001.png").read_bytes())
    ok("未预览的页没有被写进正式预览目录",
       not (preview_dir / "002.png").exists())

    apply_dir = Path(repo.rembg_output_dir(tid))
    applied = (
        sorted(p.name for p in apply_dir.glob("*.png")) if apply_dir.exists() else []
    )
    # ⚠️ 2026-10-22：去底色不再按 area/border 合成——一条输入、一条成品，
    #    文件名原样沿用（裁剪已在第二步提交时做完）。
    ok("整图去底色的应用图已增量写进 stages/rembg（一进一出，同名）",
       applied == ["001.png"], f"{applied}")
    ok("增量落盘留下未定稿哨兵（有零星应用图 ≠ 本步已提交）",
       (apply_dir / repo.REMBG_DRAFT_NAME).exists())
    ok("因此第四步不许用这批零星应用图", not d.print_source_committed())

    # ---- 参数回到「生成预览」时的取值 → 丢弃实时结果，回到正式产物 ----
    d._live_done.clear()
    panel.offset.setValue(0)
    panel.apply_args({"offset": 0})
    d._live_timer.stop()
    d._maybe_run_live_preview()
    pump(app, times=4)
    ok("参数与正式预览一致时不再重算（live 目录已撤下）",
       d.rembg_viewer.live_dir is None, f"{d.rembg_viewer.live_dir}")

    # ---- 「提交本次任务」清掉哨兵后，第四步才恢复可用 ----
    # 这里直接模拟提交的整目录重建（clean=True 会删掉 .draft），不必真跑子进程。
    ok("提交前：第四步仍拒绝这批零星应用图", not d.print_source_committed())
    (apply_dir / repo.REMBG_DRAFT_NAME).unlink(missing_ok=True)
    ok("提交后（哨兵已清）：第四步取图来源恢复为可用", d.print_source_committed())
    entries, _doc = d._print_entries()
    ok("第四步待打印列表能看到这批提交后的应用图",
       {"001.png"} <= {Path(e["file"]).name for e in entries},
       f"{[Path(e['file']).name for e in entries]}")

    # 收尾：删掉专用任务，别给后续用例留下多余条目
    try:
        repo.delete_task(tid)
    except Exception:
        pass
