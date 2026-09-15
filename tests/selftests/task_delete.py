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
    from tests.selftests._context import ok

    repo, w = ctx.repo, ctx.w

    repo.delete_task(ctx.tid_dup)
    ok("删除任务", repo.get_task(ctx.tid_dup) is None)
    ok("任务目录已清理", not repo.task_dir(ctx.tid_dup).exists())
    w.list_page.refresh()
    ok("列表同步刷新", w.list_page.table.table.rowCount() == len(repo.list_tasks()))

    # 清场：删除剩余测试任务（tid 为 None 说明 tasklist 被跳过，无事可做）
    if ctx.tid:
        repo.delete_task(ctx.tid)
    if ctx.tid_big:
        repo.delete_task(ctx.tid_big)
    w.close()
