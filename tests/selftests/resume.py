# -*- coding: utf-8 -*-
"""中断与续跑自测：大部头任务跑 extract 中途中断，再续跑补齐缺失页。"""

NAME = "resume"
DEPENDS: list[str] = ["tasklist"]
TITLE = "中断与续跑"


def run(ctx) -> None:
    import time

    from tests.selftests._context import ok, wait_worker

    app, d, repo = ctx.app, ctx.d, ctx.repo

    tid_big = repo.create_task(ctx.big_pdf, "", "大部头")
    ctx.tid_big = tid_big
    d.set_task(tid_big)
    # 提高渲染分辨率拖慢速度，保证有可靠的中断窗口
    d.control_stack.widget(0).zoom.setValue(4)
    d.run_stage(resume=False)
    time.sleep(1.5)
    app.processEvents()
    d.cancel_stage()
    # 持续补发 kill，防止偶发的终止延迟导致旧进程跑完
    deadline = time.time() + 30
    while d.process and d.process.state() != 0 and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
        if d.process and d.process.state() != 0:
            d.process.kill()
    app.processEvents()
    ok("中断后状态 cancelled",
       repo.stage_states(tid_big)["extract"]["status"] == "cancelled")

    # 续跑：只补缺失页
    partial = repo.extract_output_dir(tid_big)
    have = len(list(partial.glob("*.jpg"))) if partial.exists() else 0
    d.run_stage(resume=True)
    wait_worker(d, app, timeout=300)
    state = repo.stage_states(tid_big)["extract"]
    ok("续跑后成功", state["status"] == "success", str(state))
    total_now = len(list(partial.glob("*.jpg")))
    ok(f"续跑补齐缺失页（中断前 {have} 页 → 续跑后 {total_now} 页）", total_now >= have)
