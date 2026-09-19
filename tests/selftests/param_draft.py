# -*- coding: utf-8 -*-
"""参数暂存自测：用户改过、但还没执行的阶段参数，切阶段/重开任务后还在。

背景：进入阶段时表单按**最近一次执行参数**回填。用户改完参数没执行就切走，
改动会全部丢失（再回来看到的是上一次执行的值）。本模块守住新契约：

1. 用户改动 → 防抖后写 ``tasks/<号>/drafts/<阶段>.json``；
2. 重新进入任务 → 回填**暂存**（优先于历史执行参数）；
3. 防抖未到期就切阶段/切任务 → 走之前先落盘，不丢最后几个字符；
4. 参数非法（颜色/边距填一半，``get_args()`` 抛错）→ 保留上一份有效暂存；
5. **程序化回填不算用户改动**（否则每次回填都会反过来写一份暂存）。

⚠️ 本模块自建任务、自建页面实例（不动 ``ctx.d``），结束后清掉自己建的任务，
避免把暂存文件留给后面的模块（历史回填类断言会被暂存抢先命中）。
"""

NAME = "param_draft"
DEPENDS: list[str] = ["tasklist"]
TITLE = "参数暂存（改过没执行也不丢）"


def run(ctx) -> None:
    from tests.selftests._context import ok, pump

    from desktop.pages.taskdetail.page import TaskDetailPage

    app, repo = ctx.app, ctx.repo
    tid = repo.create_task(ctx.pdf, "hash-param-draft", "暂存样本")
    page = TaskDetailPage(repo)
    try:
        page.set_task(tid)
        print_panel = page.control_stack.widget(3)
        page._select_stage(3)
        pump(app, times=6)

        # ---- 1. 干净任务：没有暂存 ----
        ok("新任务没有暂存文件", repo.load_draft(tid, "print") is None)
        ok("暂存文件路径在任务目录的 drafts/ 下",
           repo.draft_path(tid, "print").parent.name == "drafts"
           and repo.drafts_dir(tid).parent == repo.task_dir(tid),
           str(repo.draft_path(tid, "print")))

        # ---- 2. 改参数 → 防抖后落盘 ----
        print_panel.page_margins.setText("30,40")
        print_panel.title_text.setText("暂存书名")
        pump(app, times=20, interval=0.05)  # 跨过 400ms 防抖
        draft = repo.load_draft(tid, "print") or {}
        ok("改参数后写出暂存文件", bool(draft), str(draft)[:100])
        ok("暂存里是刚改的边距（已归一化为四值）",
           draft.get("page_margins") == [30.0, 40.0, 30.0, 40.0],
           str(draft.get("page_margins")))
        ok("暂存里带上了标题文本", draft.get("title_text") == "暂存书名",
           repr(draft.get("title_text")))
        ok("系统管理字段不进暂存",
           not ({"input", "output", "workers", "clean"} & set(draft)),
           str(sorted(draft)))

        # ---- 3. 重新进入任务：回填暂存（不是内置默认）----
        page.set_task(tid)
        page._select_stage(3)
        pump(app, times=6)
        ok("重开任务后边距来自暂存", print_panel.page_margins.text() == "30,40",
           print_panel.page_margins.text())
        ok("重开任务后标题来自暂存", print_panel.title_text.text() == "暂存书名",
           print_panel.title_text.text())

        # ---- 4. 暂存优先于历史执行参数 ----
        repo._save_runs(tid, {"print": [{
            "run_id": f"{tid}-print", "status": "success",
            "parameters": {"page_margins": [5, 5, 5, 5]},
            "done": 1, "total": 1, "started_at": 0, "finished_at": 0,
        }]})
        page.set_task(tid)
        page._select_stage(3)
        pump(app, times=6)
        ok("暂存比「最近一次执行参数」优先",
           print_panel.page_margins.text() == "30,40",
           print_panel.page_margins.text())

        # 清掉暂存 → 这次该轮到历史参数
        repo.clear_draft(tid, "print")
        page.set_task(tid)
        page._select_stage(3)
        pump(app, times=6)
        # 用 get_args() 比语义：文本框里是简写形式（四值相同会写成 "5"）
        ok("没有暂存时回填最近一次执行参数",
           print_panel.get_args()["page_margins"] == [5.0, 5.0, 5.0, 5.0],
           str(print_panel.get_args()["page_margins"]))

        # ---- 5. 防抖未到期就切阶段：先落盘再走 ----
        print_panel.page_margins.setText("10")
        page._select_stage(0)  # 不 pump，直接切：此刻防抖还没到期
        draft = repo.load_draft(tid, "print") or {}
        ok("切阶段前会把待写暂存落盘",
           draft.get("page_margins") == [10.0] * 4, str(draft.get("page_margins")))

        # ---- 6. 非法参数不覆盖上一份有效暂存 ----
        page._select_stage(3)
        pump(app, times=6)
        print_panel.page_margins.setText("30,40")
        page._flush_param_drafts()
        print_panel.title_color.setText("0,0")  # 非法颜色：get_args 会抛
        raised = False
        try:
            print_panel.get_args()
        except Exception:
            raised = True
        ok("非法参数时 get_args 确实抛错（本断言的前提）", raised)
        page._flush_param_drafts()
        draft = repo.load_draft(tid, "print") or {}
        ok("非法参数不覆盖上一份有效暂存",
           draft.get("page_margins") == [30.0, 40.0, 30.0, 40.0],
           str(draft.get("page_margins")))

        # ---- 7. 程序化回填不产生暂存 ----
        repo.clear_draft(tid, "print")
        page.set_task(tid)      # 复位 + 回填全流程都是程序化 setText/setValue
        page._select_stage(3)
        page._flush_param_drafts()
        ok("程序化回填不写暂存（不会把回填当成用户改动）",
           repo.load_draft(tid, "print") is None)

        # ---- 8. 面板都接上了"用户改动"通道 ----
        ok("四个阶段面板都带 param_edited 信号",
           all(hasattr(page.control_stack.widget(i), "param_edited")
               for i in range(page.control_stack.count())))
        seen: list[int] = []
        page.control_stack.widget(0).param_edited.connect(lambda: seen.append(1))
        extract_panel = page.control_stack.widget(0)
        extract_panel.zooms = getattr(extract_panel, "zoom", None)
        if extract_panel.zooms is not None:
            extract_panel.zoom.setValue(extract_panel.zoom.value() + 1)
        ok("改 extract 的参数也会上报（不只第四步）", bool(seen), str(seen))
    finally:
        try:
            page.shutdown_all_workers()
        except Exception:  # noqa: BLE001 — 收尾失败不该让整个模块报错
            pass
        page.deleteLater()
        repo.delete_task(tid)
        ok("模块自建任务已清理", repo.get_task(tid) is None)
