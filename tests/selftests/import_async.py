# -*- coding: utf-8 -*-
"""导入异步守卫：**列表先行**，副本与缩略图后台串行补。

为什么需要它（实测数据见 `.workbuddy/perf/`）：导入后的「复制源文件 + 整本
缩略图」原先每次导入各起一个线程、且不设上限。多个 PyMuPDF 渲染线程并行会
争抢 GIL，主线程的每一次文件操作都排到 GIL 队列后面——主线程读 3KB 从
0.08ms 涨到 111ms，`create_task` 中位从 5ms 涨到 929ms，「导入 → 看见新行」
从 0.2s 变成 0.5~2.5s（大部头 2.5s）。对照实验里后台**纯写盘**对主线程 0
影响，所以不是磁盘而是 GIL。

现在的契约（本模块逐条钉住）：

1. `_hash_ready`（用户点完文件之后主线程只剩这一步）**不做任何复制/渲染**，
   重活只是进队列排队；
2. 列表行画完（`_on_rows_ready`）才 `release()` 放行后台；
3. 后台**串行**：同一时刻最多一个 job，连续导入多少本都一样；
4. 干完：源文件副本原子落地、逐页缩略图齐全、右下角提示条自动收掉。
"""

NAME = "import_async"
DEPENDS: list[str] = ["tasklist"]  # 借它建好的窗口与列表页
TITLE = "导入异步（列表先行）"


def run(ctx) -> None:
    from desktop.pages.tasklist.page import HEADER_SUBTITLE

    from tests.selftests._context import ok, wait_until

    app, w, repo = ctx.app, ctx.w, ctx.repo
    page = w.list_page
    queue = page._thumb_queue
    src = ctx.big_pdf  # 80 页
    pages = 80

    def subtitle() -> str:
        """页头副标题（导入期间应显示「正在导入 · …」）。"""
        return page._header.subtitle_label.text()

    def thumbs_of(task_id) -> int:
        d = repo.source_thumbnails_dir(task_id)
        return len(list(d.glob("*.jpg"))) if d.exists() else 0

    created: list[str] = []

    try:
        # ---- 起点：先等前一个模块（tasklist）的后台活干完 ----
        # ⚠️ 不能直接断言"空闲"：tasklist 也导入过，它的副本/缩略图可能还在跑，
        #    慢机器上会偶发失败（本模块只关心自己的那一次导入）。
        ok("进入本模块前队列能回到空闲",
           wait_until(app, lambda: not queue.busy(), timeout=60.0),
           f"running={queue.running_count()} pending={queue.pending_count()}")
        ok("初始页头是默认说明（没有导入提示）", subtitle() == HEADER_SUBTITLE,
           subtitle())

        # ---- ① 主线程只建任务，重活只排队 ----
        before = len(repo.list_tasks())
        page._confirm_duplicate = lambda path, dups: True  # 重复导入不弹模态框
        page._hash_ready(str(src), "hash-import-async")
        task = repo.list_tasks()[0]
        created.append(task["id"])

        ok("建任务后立刻进了索引", len(repo.list_tasks()) == before + 1)
        ok(
            "重活只是排队、一步没跑（主线程没在复制源文件）",
            queue.pending_count() == 1 and queue.running_count() == 0,
            f"pending={queue.pending_count()} running={queue.running_count()}",
        )
        ok(
            "此刻源文件副本尚未落地",
            not (repo.task_dir(task["id"]) / src.name).exists(),
        )

        # ---- ② 列表画完才放行开工 ----
        ok("列表出现新行",
           wait_until(app, lambda: page.table.table.rowCount() == before + 1))
        ok("列表画完后后台才开始跑",
           wait_until(app, lambda: queue.running_count() == 1))
        ok("导入期间页头显示「正在导入」", "正在导入" in subtitle(), subtitle())

        # ---- ③ 干完：副本 + 缩略图 + 提示条收尾 ----
        ok("后台活全部结束", wait_until(app, lambda: not queue.busy(), timeout=60.0))
        ok(
            "源文件副本原子落地（.part 替换完才会出现）",
            (repo.task_dir(task["id"]) / src.name).exists(),
        )
        ok("逐页缩略图齐全", thumbs_of(task["id"]) == pages,
           f"实际 {thumbs_of(task['id'])} 张 / 预期 {pages}")
        ok("干完后页头恢复默认说明", "正在导入" not in subtitle(), subtitle())

        # ---- ④ 串行不变式：连导 3 本，并发恒不超过 1 ----
        import time

        ids = []
        for i in range(3):
            page._hash_ready(str(src), f"hash-import-async-{i}")
            ids.append(repo.list_tasks()[0]["id"])
        created.extend(ids)

        peak = 0
        end = time.time() + 3
        while time.time() < end:
            app.processEvents()
            peak = max(peak, queue.running_count())
            time.sleep(0.005)
        ok("后台并发数恒为 1（多个渲染线程会抢 GIL）", peak <= 1, f"峰值 {peak}")

        ok("三本都能跑完", wait_until(app, lambda: not queue.busy(), timeout=120.0))
        counts = [thumbs_of(tid) for tid in ids]
        ok("三本缩略图都齐全", counts == [pages] * 3, str(counts))
    finally:
        # 清场：本模块造的临时任务全部删掉，别影响后面的模块数任务数
        for tid in created:
            repo.delete_task(tid)
