# -*- coding: utf-8 -*-
"""任务删除自测：删除任务清理目录、列表同步；最后清场删除全部测试任务。

TEARDOWN = True：本模块销毁共享夹具（删除 tid/tid_big 并关窗），必须排在
所有用例之后——否则后面依赖任务目录的模块（如 thumb_cache）会拿到空夹具。
"""

NAME = "task_delete"
DEPENDS: list[str] = ["detect_boxes"]
TITLE = "任务删除"
TEARDOWN = True


def run(ctx) -> None:
    from tests.selftests._context import ok, wait_until

    repo, w = ctx.repo, ctx.w

    repo.delete_task(ctx.tid_dup)
    ok("删除任务", repo.get_task(ctx.tid_dup) is None)
    ok("任务目录已清理", not repo.task_dir(ctx.tid_dup).exists())
    w.list_page.refresh()
    # refresh 是异步的（后台线程读盘）：等表格行数追上真实任务数再断言
    wait_until(
        ctx.app,
        lambda: w.list_page.table.table.rowCount() == len(repo.list_tasks()),
        timeout=5.0,
    )
    ok("列表同步刷新", w.list_page.table.table.rowCount() == len(repo.list_tasks()))

    # ⚠️ 文件被占用时不能「列表显示已删、磁盘却留着孤儿目录」：
    # 失败要保留任务记录，让用户看得见、能重试。
    tid_held = repo.create_task(ctx.pdf, "hash-held", "占用测试")
    held_pdf = repo.copy_source_to_task(tid_held, ctx.pdf)
    with held_pdf.open("rb"):  # 持句柄 = 模拟后台渲染线程正读这份 PDF
        ok("目录被占用时删除失败", repo.delete_task(tid_held) is False)
        ok("失败后任务仍在索引（不留孤儿）", repo.get_task(tid_held) is not None)
    ok("释放后可删除", repo.delete_task(tid_held) is True)
    ok("释放后目录清掉", not repo.task_dir(tid_held).exists())

    # ---- 删除**不回收任务号**（用户 2026-10-16：「任务序号保留占用」）----
    # 光靠"索引里的最大号 + 磁盘目录"做不到：删除正好把这两个来源同时抹掉，
    # 最大号会退回去、下一个新建又把那个号捡回来。所以另有一份只增不减的水位。
    tid_gone = repo.create_task(ctx.pdf, "hash-gone", "回收测试")
    ok("新建后就把水位抬到了该号（下一个号不回收它）",
       repo.next_task_no() == f"{int(tid_gone) + 1:04d}",
       f"新建={tid_gone} 下一个={repo.next_task_no()}")
    ok("水位文件落在数据根、与 tasks.json 并列",
       (repo.root / "task_no.json").is_file(), str(repo.root / "task_no.json"))
    ok("删除任务", repo.delete_task(tid_gone) is True)
    ok("删掉之后下一个号**不是**被删的那个（不回收）",
       repo.next_task_no() != tid_gone, repo.next_task_no())
    tid_after = repo.create_task(ctx.pdf, "hash-after", "删除后新建")
    ok("删掉 0020 之后新建拿到的是 0021（差 1）",
       int(tid_after) == int(tid_gone) + 1,
       f"被删={tid_gone} 新建={tid_after}")
    ok("删除后新建的任务目录也在", repo.task_dir(tid_after).is_dir())
    ok("水位 = 已分配过的最大号（只增不减）",
       int(repo._read_max_allocated()) == int(tid_after),
       f"水位={repo._read_max_allocated()} 最大号={tid_after}")
    repo.delete_task(tid_after)

    # 清场：删除剩余测试任务（tid 为 None 说明 tasklist 被跳过，无事可做）
    if ctx.tid:
        repo.delete_task(ctx.tid)
    if ctx.tid_big:
        repo.delete_task(ctx.tid_big)
    w.close()
