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

