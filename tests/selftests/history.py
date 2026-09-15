# -*- coding: utf-8 -*-
"""失败可见性与执行历史自测：非法页码失败入日志、历史保存/回填/高亮。"""

NAME = "history"
DEPENDS: list[str] = ["extract"]
TITLE = "失败可见性"


def run(ctx) -> None:
    import time

    from tests.selftests._context import ok, wait_worker

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid

    d.set_task(tid)
    d._select_stage(0)
    d.control_stack.widget(0).pages_edit.setText("99-200")
    d.run_stage(resume=False)
    wait_worker(d, app)
    time.sleep(0.3); app.processEvents()
    log = d.log_view.toPlainText()
    ok("失败原因进入日志", "页面参数错误" in log or "❌" in log)

    # 执行历史保存 + 历史配置回填 + 步骤条高亮
    hist = repo.list_stage_runs(tid, "extract")
    ok("执行历史已保存（最新在前）",
       len(hist) == 2 and hist[0]["status"] == "failed" and hist[1]["status"] == "success",
       str([(h["status"], h.get("parameters", {}).get("pages")) for h in hist]))
    d._select_stage(0)
    ok("历史配置下拉条数", d.history_combo.count() == 2)
    d._on_history_selected(0)
    ok("历史配置回填表单", d.control_stack.widget(0).pages_edit.text() == "99-200")
    ok("步骤条已完成高亮", 0 in d.step_bar._completed and 1 not in d.step_bar._completed)
