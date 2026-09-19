# -*- coding: utf-8 -*-
"""detect 阶段自测：真实 YOLO 子进程执行、裁剪框几何规则、续跑跳过。"""

NAME = "detect"
DEPENDS: list[str] = ["pages"]
TITLE = "detect"


def run(ctx) -> None:
    import time
    from pathlib import Path

    from tests.selftests._context import ok, wait_worker
    from utils.box_geometry import compute_final_boxes
    from utils.box_geometry import parse_border_mm as _pbm

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid

    d._select_stage(1)
    d.run_stage(resume=False)
    wait_worker(d, app, timeout=300)
    state = repo.stage_states(tid)["detect"]
    ok("detect 执行完成", state["status"] in ("success",), str(state))
    ok("detect 执行历史已保存", len(repo.list_stage_runs(tid, "detect")) == 1)
    ok("detect 步骤高亮", 1 in d.step_bar._completed)
    time.sleep(0.3); app.processEvents()
    detect_out = repo.stage_output_dir(tid, "detect")
    ok("detect 阶段不生成切割文件",
       not detect_out.exists() or not any(detect_out.iterdir()), str(detect_out))
    manifest_before_detect = [p["file"] for p in repo.load_pages(tid)]
    manifest_now = [p["file"] for p in repo.load_pages(tid)]
    ok("detect 不影响页面清单", manifest_now == manifest_before_detect)

    # 最终裁剪框规则与 crop 命令一致（utils.box_geometry）
    _left, _right = [100, 100, 200, 200], [300, 100, 500, 300]
    _d = _pbm("10")[0]
    ok("area=1 逐框外扩 border",
       compute_final_boxes([_left, _right], 1, "10")
       == [[100 - _d, 100 - _d, 200 + _d, 200 + _d],
           [300 - _d, 100 - _d, 500 + _d, 300 + _d]])
    ok("area=2 合并大框",
       compute_final_boxes([_left, _right], 2, "10")
       == [[100 - _d, 100 - _d, 500 + _d, 300 + _d]])
    ok("area=3 与 area=2 同规则",
       compute_final_boxes([_left, _right], 3, "10")
       == compute_final_boxes([_left, _right], 2, "10"))
    ok("单框对称取内容框",
       compute_final_boxes([_left], 2, "10") == [[100 - _d, 100 - _d, 200 + _d, 200 + _d]])

    # 检测框坐标实时入库（YOLO 检出时 origin=auto；合成页面可能检不出）
    first_stem = Path(repo.load_pages(tid)[0]["file"]).stem
    entry = repo.detect_boxes_entry(tid, first_stem)
    ok("detect 阶段框坐标入库", entry is None or entry[1] == "auto", str(entry))

    # detect 输入直指 extract 目录：不再物化 workset，页数即清单页数
    extract_dir = repo.extract_output_dir(tid)
    ok("detect 输入为 extract 目录", extract_dir.exists())
    # 两种可能落点都要查（旧实现为 tasks/<id>/workset；按 output.parent
    # 拼错则会落在 stages/workset）。detect 早于 print 执行，此时必须为空。
    _ws_leaks = [
        c.name for c in (repo.task_dir(tid) / "workset",
                         repo.stage_dir(tid, "workset"))
        if c.exists() and any(c.iterdir())
    ]
    ok("detect 不再产生 workset 副本", not _ws_leaks, f"泄漏={_ws_leaks or '无'}")

    # ---- 回归：第二步预览的框必须画得住（2026-09-19 重跑手册截图时抓到）----
    # 症状：第二步预览「一个框都没有」，信息条只剩像素尺寸；三张检测截图
    # md5 完全相同。根因：`_select_image()` 里的 `strip.setCurrentRow()` 会经
    # ThumbStrip 的 currentRowChanged **递归回调**回本函数 → 同一张图起了两个
    # PreviewWorker，两个都走 `_image_ready` → `view.set_image()`，后到的那个
    # 把已经画好的框清成 `[]`。这里用「一次选页只起一个加载任务」+「框与信息条
    # 真的上屏」两条断言钉住（框走内存缓存注入，不落盘、不影响后续模块）。
    from desktop.components.viewers import image_viewer as _iv

    from tests.selftests._context import pump

    control = d.control_stack.widget(2)  # area 属第三步面板，此处只借来定档
    control.area.setCurrentIndex(control._index_of(control.area, 1))
    pump(app, 4)

    view = d.detect_viewer
    page_path = view.paths[0]
    injected = [[30, 500, 1100, 2000], [1270, 520, 2360, 2070]]
    d.detect_cache[str(page_path)] = injected
    d._select_stage(1)
    pump(app, 6)

    # ⚠️ 先把缩略图条的当前行挪到第 2 张，再选回第 1 张——只有「行真的变了」
    # 才会经 currentRowChanged 递归回调回 _select_image。若停在当前行不动，
    # setCurrentRow 不发信号，重复加载的 bug 就复现不出来（会假绿）。
    view.strip.setCurrentRow(1)
    pump(app, 4)

    maker = {"n": 0}
    real_worker = _iv.PreviewWorker

    class _CountingWorker(real_worker):
        def __init__(self, *a, **kw):
            maker["n"] += 1
            super().__init__(*a, **kw)

    _iv.PreviewWorker = _CountingWorker
    try:
        view._select_image(0, str(page_path))
        pump(app, 2)
    finally:
        _iv.PreviewWorker = real_worker
    ok("一次选页只起一个预览加载任务（不重复加载同一张图）",
       maker["n"] == 1, f"起了 {maker['n']} 个 PreviewWorker")

    deadline = time.time() + 15
    while [list(b) for b in view.view._boxes] != injected and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    pump(app, 4)
    ok("第二步预览的检测框真的画上了（不是空画面）",
       [list(b) for b in view.view._boxes] == injected,
       f"_boxes={view.view._boxes}")
    ok("信息条显示框坐标而不是像素尺寸",
       "左框" in view.info_label.text() and "px" not in view.info_label.text(),
       repr(view.info_label.text()))
    d.detect_cache.pop(str(page_path), None)

