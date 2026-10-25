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

    # ---- 2b. 唯一写者：连续批量写不重读整份文件；extra 并入条目 ----
    cache = repo._doc(boxes_path)
    doc_obj = cache.doc()
    loads: list[int] = []
    real_load = cache._load

    def _counted_load() -> None:
        loads.append(1)
        real_load()

    cache._load = _counted_load            # type: ignore[method-assign]
    try:
        repo.save_detect_boxes_batch(tid, {"0003": [[0, 0, 5, 5]]})
        repo.save_detect_boxes_batch(
            tid, {"0003": []}, extra={"0003": {"src": [10, 20], "det": "abc"}}
        )
        ok("连续两次批量写不重新整份读盘（内存文档是唯一写者）",
           not loads and cache.doc() is doc_obj, f"重读 {len(loads)} 次")
    finally:
        cache._load = real_load            # type: ignore[method-assign]
    entry = repo.detect_boxes_entry(tid, "0003")
    ok("extra 字段被并入条目（空框页也能留下额外字段）",
       entry is not None and entry[0] == []
       and repo.boxes_raw_at(boxes_path)["0003"].get("src") == [10, 20]
       and repo.boxes_raw_at(boxes_path)["0003"].get("det") == "abc",
       str(entry))

    repo.save_detect_boxes(tid, "0004", [[1, 1, 9, 9]], origin="manual")
    repo.save_detect_boxes_batch(tid, {"0004": [[2, 2, 8, 8]]})
    entry = repo.detect_boxes_entry(tid, "0004")
    ok("单页写与批量写共用一份文档、互不覆盖（人工框仍优先）",
       entry is not None and entry[1] == "manual"
       and entry[0] == [[1, 1, 9, 9]], str(entry))

    # ---- 2c. 提交计划（产物角色）：随框落盘、拖框/重检测不抹掉 ----
    plans = {
        "0002": {
            "page_class": "harfcontent",
            "outputs": [
                {"label": "0002-r", "role": "half-right", "placeholder": False},
                {"label": "0002-l", "role": "half-left", "placeholder": False},
            ],
        },
        # 没有框记录的页不凭空造条目（否则会被统计当成"检测过的空页"）
        "不存在的页": {"page_class": "empty", "outputs": []},
    }
    repo.save_detect_plans(tid, plans)
    got_plans = repo.detect_plans_all_at(boxes_path)
    ok("提交计划按页读回（含产物角色与占位标记）",
       got_plans.get("0002", {}).get("outputs") == plans["0002"]["outputs"],
       str(got_plans.get("0002")))
    ok("没有框记录的页不会被计划凭空造出来",
       "不存在的页" not in repo.boxes_raw_at(boxes_path))

    repo.save_detect_boxes(tid, "0002", [[0, 0, 20, 20], [30, 0, 60, 60]])
    ok("拖框重写条目时保留提交计划（它描述的是已落盘的产物）",
       isinstance(repo.boxes_raw_at(boxes_path)["0002"].get("plan"), dict),
       str(repo.boxes_raw_at(boxes_path)["0002"]))
    repo.save_detect_boxes_batch(tid, {"0002": [[0, 0, 21, 21], [30, 0, 61, 61]]})
    ok("重跑检测批量写同样保留提交计划",
       isinstance(repo.boxes_raw_at(boxes_path)["0002"].get("plan"), dict),
       str(repo.boxes_raw_at(boxes_path)["0002"]))

    # 用户 2026-10-26：每次检测都重新执行 → 这次没检出框的页必须覆盖旧框，
    # 否则界面/下游仍拿着上一次的框。
    repo.save_detect_boxes(tid, "0007", [[0, 0, 10, 10]])
    repo.save_detect_boxes_batch(tid, {"0007": []})
    ok("重跑检测得到空框 → 覆盖旧框（不残留上次结果）",
       repo.boxes_entry_at(boxes_path, "0007")[0] == [],
       str(repo.boxes_entry_at(boxes_path, "0007")))

    # ---- 2d. 人工「整幅」遇同框的自动「半幅」→ 只刷新槽形 ----
    # 用户 2026-10-23（任务 0004）：旧模型把半幅页存成 1 槽人工记录，人工框
    # 优先让新检测结果永远写不进去。同框（IoU≥0.9）时只改形态、保留人工坐标。
    repo.save_detect_boxes(tid, "0005", [[100, 100, 900, 1300]], origin="manual")
    repo.save_detect_plans(tid, {"0005": {"page_class": "fullcontent", "outputs": []}})
    repo.save_detect_boxes_batch(tid, {"0005": [None, [102, 101, 898, 1302]]})
    raw5 = repo.boxes_raw_at(boxes_path)["0005"]
    ok("同框的自动半幅把人工整幅刷新成 2 槽（0004 的 37 页场景）",
       len(raw5["boxes"]) == 2 and raw5["boxes"][0] is None
       and raw5["boxes"][1] == [100, 100, 900, 1300], str(raw5))
    ok("刷新只改槽形：origin 仍是 manual、坐标仍取人工那份",
       raw5.get("origin") == "manual"
       and raw5["boxes"][1] == [100, 100, 900, 1300], str(raw5))
    ok("形态变了，旧提交计划作废（下次提交会重写）",
       "plan" not in raw5, str(raw5))

    repo.save_detect_boxes(tid, "0006", [[100, 100, 900, 1300]], origin="manual")
    repo.save_detect_boxes_batch(tid, {"0006": [None, [0, 0, 300, 400]]})
    raw6 = repo.boxes_raw_at(boxes_path)["0006"]
    ok("不同框（IoU 低）→ 人工记录原样保留，不被改写",
       raw6["boxes"] == [[100, 100, 900, 1300]]
       and raw6.get("origin") == "manual", str(raw6))

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
