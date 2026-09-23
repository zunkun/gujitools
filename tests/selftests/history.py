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

    # ⚠️ 与上面**相反**的一条：进阶段时的**自动**回填不许带 extract 的 pages。
    # pages 是「续跑」按缺失页派生的一次性参数（不是用户意图），自动回填它会让
    # 下一次点「执行本子任务」只跑那一小段页码 —— 用户看到"只提取了一半"。
    # 上面那条钉的是"用户主动从下拉框挑一条历史配置"的语义，两条都要成立。
    repo.clear_draft(tid, "extract")          # 暂存优先，先清掉才能测历史分支
    d._history_prefilled.discard("extract")
    d.control_stack.widget(0).pages_edit.setText("")
    d._restore_stage_params(0)
    ok("自动回填跳过派生 pages", d.control_stack.widget(0).pages_edit.text() == "",
       d.control_stack.widget(0).pages_edit.text())
    ok("自动回填其它字段照旧", d.control_stack.widget(0).zoom.value() == 1,
       str(d.control_stack.widget(0).zoom.value()))
