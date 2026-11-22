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
4. 干完：源文件副本原子落地、首屏缩略图备齐（2026-10-21 起懒加载，
   不再整本预渲染）、右下角提示条自动收掉。
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
        # ⚠️ 2026-10-21 起不再整本预渲染：只备 PREFETCH_PAGES（首屏 + 余量），
        #    其余页滚到可见窗口时按需补（旧断言 ==80 是懒加载改造前的契约，
        #    一直红着没更新，把后面的模块全挡住了）。
        from desktop.workers.source_thumbnails_worker import PREFETCH_PAGES

        prerendered = min(pages, PREFETCH_PAGES)
        ok("导入后台只备首屏缩略图（懒加载，不再整本预渲染）",
           thumbs_of(task["id"]) == prerendered,
           f"实际 {thumbs_of(task['id'])} 张 / 预期 {prerendered}")
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
        ok("三本首屏缩略图都备齐（懒加载契约）",
           counts == [prerendered] * 3, str(counts))

        # ---- ⑤ 空壳任务（没选源文件）绝不排队后台活（任务 0017，2026-11-17）----
        # ``start_create`` 的空壳分支传的是 ``Path()`` —— 它就是 ``Path('.')``，
        # ``str()`` 是 "."（真值）。判"有没有源"必须把 "." 一起挡掉，否则：
        # ① 给 thumbnails/source 立假 `.producing` 标记（查看器白等回扫）；
        # ② 排队一个 ``pdf_path='.'`` 的 worker → 复制线程报
        #    「Permission denied: '.'」、fitz 报「'.' is no file」，
        #    用户回到列表页看到两块错误 toast。
        from pathlib import Path

        from desktop.utils.files import PRODUCING_MARKER

        ok("进入⑤前队列空闲",
           wait_until(app, lambda: not queue.busy(), timeout=60.0))
        # ⚠️ **替身 submit，同步断言**：放真队列会有竞态——坏 worker 毫秒级
        #    就失败收场（fitz 打不开 '.'），收尾 finally 还会把 `.producing`
        #    撤掉，事后查"队列空不空""标记在不在"都可能"恰好"绿（注入复验
        #    实测）。替身只记录不动真格，"排没排队""立没立标记"变成同步判据。
        submitted: list[str] = []
        real_submit = queue.submit
        queue.submit = lambda *a, **k: submitted.append(k.get("label", ""))
        try:
            page._create_imported_task(Path(), "")
            shell = repo.list_tasks()[0]
        finally:
            queue.submit = real_submit
        created.append(shell["id"])
        ok("空壳任务照常建出来（PDF 非必需）",
           len(repo.list_tasks()) == before + 5,
           f"tasks={len(repo.list_tasks())} expected={before + 5}")
        ok("空壳任务不排队任何后台活（不白报错、不堵串行队列）",
           submitted == [], f"submitted={submitted}")
        ok("空壳任务不立 .producing 假标记（否则查看器白等一轮回扫）",
           not (repo.source_thumbnails_dir(shell["id"]) / PRODUCING_MARKER)
           .exists())
        ok("空壳任务没有写过缩略图缓存（worker 根本没跑）",
           thumbs_of(shell["id"]) == 0,
           f"thumbs={thumbs_of(shell['id'])}")

        # ---- toast 挂主窗口（2026-11-17 用户报障"回列表页才弹出"）----
        # 建任务链路 open_detail 在 toast 之前：壳层已切到详情页，列表页隐藏。
        # InfoBar 挂在隐藏控件上要等父级重新显示才弹出来 ⇒ 必须挂主窗口。
        from desktop.pages.tasklist import page as tasklist_page_module

        captured: dict = {}
        real_info = tasklist_page_module.InfoBar.info
        tasklist_page_module.InfoBar.info = lambda **kw: captured.update(kw)
        try:
            page._toast("info", "任务已创建", "尚未选择源文件")
        finally:
            tasklist_page_module.InfoBar.info = real_info
        ok("列表页 toast 挂**主窗口**（挂在本页＝被切走后迟到弹出）",
           captured.get("parent") is page.window(),
           f"parent={captured.get('parent')} page={page}")
    finally:
        # 清场：本模块造的临时任务全部删掉，别影响后面的模块数任务数
        for tid in created:
            repo.delete_task(tid)
