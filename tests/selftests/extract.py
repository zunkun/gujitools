# -*- coding: utf-8 -*-
"""extract 阶段全量执行自测：真实子进程跑提取、进度/清单/尺寸/日志。"""

NAME = "extract"
DEPENDS: list[str] = ["tasklist"]
TITLE = "extract"


def run(ctx) -> None:
    import time
    from pathlib import Path

    from PySide6.QtGui import QImageReader

    from tests.selftests._context import ok, wait_worker

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid

    d._select_stage(0)
    d.run_stage(resume=False)
    wait_worker(d, app)
    # wait_worker 只看进程状态：进程退出时最后一条 finished 事件（才带
    # done=6）可能还排在事件队列里没被读完，直接读状态会偶发拿到 done=5。
    for _ in range(60):
        app.processEvents()
        if repo.stage_states(tid)["extract"]["done"] == 6:
            break
        time.sleep(0.05)
    state = repo.stage_states(tid)["extract"]
    ok("extract 成功", state["status"] == "success", str(state))
    ok("进度 6/6", (state["done"], state["total"]) == (6, 6), str(state))
    for _ in range(15):
        app.processEvents(); time.sleep(0.1)
    ok("提取结果 6 页入清单", len(repo.load_pages(tid)) == 6)
    # extract 阶段记录的原始尺寸与实际图片文件一致
    first_page = repo.load_pages(tid)[0]["file"]
    stem = Path(first_page).stem
    meta = repo.image_size(tid, stem)
    actual = QImageReader(first_page).size()
    ok("extract 记录图片原始尺寸", meta == (actual.width(), actual.height()),
       f"db={meta} actual={actual.width()}x{actual.height()}")
    log = d.log_view.toPlainText()
    ok("中文日志无乱码", "处理完成" in log and "\\ufffd" not in repr(log))
