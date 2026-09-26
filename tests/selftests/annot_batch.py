# -*- coding: utf-8 -*-
"""尺寸/检测框**攒批落盘**守卫：内容与逐条写等价、人工框优先、切任务先落盘。

背景（2026-09-25 实测）：extract 上报尺寸、detect 上报框，原先**每个事件**
都「读整个 JSON + 改写」——320 页实测累计主线程阻塞 **3.1 秒**
（sizes 1.3s + boxes 1.8s；2400 页的书记忆里是 47.5s，见
``.workbuddy/perf/2026-09-23-sqlite-vs-json.md``）。改成攒批（400ms）+ 阶段
收尾一次性写，只要 ~0.02s。

⚠️ 这一改直接落在 **GUI 主线程**上，而 extract/detect 的护栏在沙箱里跑不了
（QProcess 起不来）——所以本模块用「事件级调用 + 主动 flush」在进程内独立验证，
不依赖阶段子进程。
"""

NAME = "annot_batch"
DEPENDS: list[str] = ["tasklist"]
TITLE = "尺寸/框攒批落盘"


def run(ctx) -> None:
    from tests.selftests._context import ok

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid
    d.set_task(tid)
    app.processEvents()

    sizes_path = repo.sizes_path(tid)
    boxes_path = repo.boxes_path(tid)
    sizes_before = sizes_path.read_text(encoding="utf-8") if sizes_path.exists() else ""

    # ---- 1. 尺寸：事件只攒不写，flush 后一次写齐 ----
    for i in range(1, 6):
        d._store_page_size({"image": f"{i:04d}", "width": 5000 + i, "height": 4400})
    sizes_now = sizes_path.read_text(encoding="utf-8") if sizes_path.exists() else ""
    ok("攒批期间不逐条落盘（定时器未到期就不会写文件）",
       sizes_now == sizes_before, f"文件被改了：{len(sizes_now)} 字节")
    d._flush_annotations()
    got = [repo.image_size(tid, f"{i:04d}") for i in range(1, 6)]
    ok("flush 后 5 页尺寸一次写齐",
       got == [(5001, 4400), (5002, 4400), (5003, 4400), (5004, 4400), (5005, 4400)],
       str(got))

    # ---- 2. 检测框：人工框优先，自动框批量写 ----
    repo.save_detect_boxes(tid, "0001", [[1, 2, 3, 4], [5, 6, 7, 8]], origin="manual")
    d._store_stage_boxes({"image": "0001", "left": [0, 0, 10, 10], "right": None})
    d._store_stage_boxes({"image": "0002", "left": [0, 0, 20, 20], "right": [30, 0, 60, 60]})
    d._flush_annotations()
    manual = repo.detect_boxes_entry(tid, "0001")
    auto = repo.detect_boxes_entry(tid, "0002")
    ok("人工框（origin=manual）不被批量写覆盖",
       manual is not None and manual[1] == "manual" and manual[0][0] == [1, 2, 3, 4],
       str(manual))
    ok("自动框批量写入且保留左右身份",
       auto is not None and auto[1] == "auto"
       and auto[0] == [[0, 0, 20, 20], [30, 0, 60, 60]],
       str(auto))

    # ---- 3. 切任务前必须先落盘（否则上一任务的攒批会写进新任务）----
    other = repo.create_task(ctx.pdf, "hash-annot-batch", "另一本", True)
    d._store_page_size({"image": "0999", "width": 111, "height": 222})
    d.set_task(other)
    app.processEvents()
    ok("切任务时把攒批落进**原任务**",
       repo.image_size(tid, "0999") == (111, 222),
       str(repo.image_size(tid, "0999")))
    ok("新任务没有被串入上一个任务的攒批",
       repo.image_size(other, "0999") is None,
       str(repo.image_size(other, "0999")))

    # 收尾：把临时任务删掉，别影响后续模块的任务数
    d.set_task(tid)
    repo.delete_task(other)
