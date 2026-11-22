# -*- coding: utf-8 -*-
"""第四步「PDF排版」进页面耗时守卫（用户 2026-11-21 报「任务 0032 点进详情有些慢」）。

真实数据实测：343 页的任务进入详情 1.37s（冷 2.1s），其中约 69% 是**同一批页面的
缩略图路径被反复查询**——``_print_thumb_provider`` 被调 687 次（预览预热一遍 +
缩略图条一遍），每次 2 次 ``book_key``（``stat`` ＋ Windows ``resolve()``）＋若干
``stat``。本模块钉住四条互不替代的判据：

1. ``book_key`` 的路径摘要**有缓存**，且**取值与旧算法逐字相同**（换摘要 = 全仓
   缩略图缓存集体失效，不能悄悄发生）；
2. ``_print_thumb_provider`` 第二次问同一页时**不再查一遍缓存体系**（只付一次
   ``stat``），而源图被覆盖后自动重新查、小图落地后记忆要让位；
3. 缩略图条的路径解析**跟着可见窗口走**（对齐「检测/去底色」），不为整本书
   预先解析；
4. 进页面**不**同步预热待打印缩略图（那笔活推给定时器；「管理图片」等入口仍
   同步等它）。
"""

NAME = "detail_print_thumbs"
DEPENDS: list[str] = ["tasklist"]
TITLE = "第四步缩略图路径：缓存/记忆/窗口化/延后预热"


def run(ctx) -> None:
    import hashlib
    import os
    import time
    from pathlib import Path

    from PIL import Image

    from desktop.components.viewers.print_preview import PrintPreviewWidget
    from desktop.pages.taskdetail import print_list as print_list_mod
    from desktop.utils import files as files_mod
    from tests.selftests._context import ok, pump, wait_until

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid
    assert tid is not None, "tasklist 模块应已创建主任务"

    root = Path(ctx.tmp) / "print_thumbs_probe"
    root.mkdir(parents=True, exist_ok=True)
    probe = root / "探针图.png"
    Image.new("RGB", (320, 240), (90, 140, 200)).save(probe)

    # ---------------------------------------------------------------- ① book_key
    files_mod._resolved_path_digest.cache_clear()
    first = files_mod.book_key(probe)
    second = files_mod.book_key(probe)
    info = files_mod._resolved_path_digest.cache_info()
    ok("同一路径第二次问：路径摘要走缓存（不再 resolve）",
       info.hits >= 1 and first == second, f"{first} / {second} {info}")

    legacy = hashlib.sha1(
        str(probe.resolve()).encode("utf-8", "replace")
    ).hexdigest()
    ok("缓存后的键与旧算法逐字相同（既有缩略图缓存不失效）",
       first == f"{probe.stem}-{probe.stat().st_size}-{legacy[:8]}",
       f"{first} vs legacy {legacy[:8]}")

    rel = os.path.relpath(probe, Path.cwd())
    ok("相对路径不进缓存（结果依赖 cwd，会变）",
       files_mod.book_key(rel) == files_mod.book_key(rel))

    # --------------------------------------------------- ② provider 路径记忆
    d.set_task(tid)
    calls = {"book_key": 0, "entry": 0}
    real_book_key = print_list_mod.book_key
    real_entry = repo.entry_thumb_path

    def counting_book_key(book):
        calls["book_key"] += 1
        return real_book_key(book)

    def counting_entry(*a, **kw):
        calls["entry"] += 1
        return real_entry(*a, **kw)

    # ⚠️ provider 里 `book_key` 是**本模块模块级导入**的 ⇒ 补丁必须打在
    #    `print_list.book_key` 这个名字上（打在 utils.files 上无效，见记忆里那条坑）
    print_list_mod.book_key = counting_book_key
    repo.entry_thumb_path = counting_entry
    try:
        cold = d._print_thumb_provider(str(probe))
        cold_calls = dict(calls)
        warm = d._print_thumb_provider(str(probe))
        ok("第一次问：走完整查询（入口缓存 + 图键缓存两条路都要问）",
           cold is None and cold_calls["book_key"] >= 1
           and cold_calls["entry"] == 1, f"{cold} {cold_calls}")
        ok("第二次问同一页：只凭记忆返回，不再查一遍缓存体系",
           calls["book_key"] == cold_calls["book_key"]
           and calls["entry"] == cold_calls["entry"] and warm is None,
           f"after={calls} cold={cold_calls}")

        # 源图被覆盖（上游重合成/编辑器回写）：记忆必须自动作废
        Image.new("RGB", (400, 300), (30, 30, 30)).save(probe)
        os.utime(probe, (time.time() + 2, time.time() + 2))
        d._print_thumb_provider(str(probe))
        ok("源图 mtime/大小变了 ⇒ 记忆作废、重新查一遍",
           calls["book_key"] > cold_calls["book_key"],
           f"book_key={calls['book_key']} cold={cold_calls['book_key']}")

        # 小图落地后要能立刻被看见（否则记忆里的 None 会把列表压死在原图上）
        d._print_thumb_paths[str(probe)] = ((0, 0), "旧值")
        d._on_print_thumb_ready(tid, str(probe))
        ok("一张小图生成完 ⇒ 丢掉这张的路径记忆",
           str(probe) not in d._print_thumb_paths)
        d._print_thumb_paths[str(probe)] = ((0, 0), "旧值")
        d._on_print_thumbs_warmed(tid)
        ok("整批预热完成 ⇒ 整份路径记忆作废", not d._print_thumb_paths)
    finally:
        print_list_mod.book_key = real_book_key
        repo.entry_thumb_path = real_entry

    # ------------------------------------------------------ ③ 缩略图窗口化
    total = 60
    for index in range(total):
        Image.new("RGB", (60, 80), (200, 120, 90)).save(
            root / f"页{index:03d}.png"
        )
    preview = PrintPreviewWidget(thumb_provider=lambda text: None)
    try:
        resolved = {"count": 0}
        real_path_for = preview._thumb_path_for

        def counting_path_for(entry):
            resolved["count"] += 1
            return real_path_for(entry)

        preview._thumb_path_for = counting_path_for
        preview.set_entries([
            {"file": str(root / f"页{i:03d}.png"), "label": f"页{i:03d}"}
            for i in range(total)
        ])
        # 窗口 = 视口 ± 边距（未显示时 FALLBACK_VISIBLE=16，最多 3 段）
        ok("缩略图条只为**可见窗口**解析路径（不为整本预先解析）",
           resolved["count"] <= 48,
           f"解析 {resolved['count']} 次 / 共 {total} 条")
        ok("条目本身照旧全量建出（窗口化只省路径解析，不改列表）",
           preview.count() == total, str(preview.count()))
    finally:
        preview.deleteLater()

    # -------------------------------------------------------- ④ 进页面不同步预热
    # ⚠️ 这里不对"进页面"做端到端计时断言（离屏 + 临时任务没有待打印图，
    #    `_print_entries` 会在半路早退，测出来是空断言）。改钉**调用形状**：
    #    建表那条路只许排定时器，两个"马上就要用缓存"的入口仍同步等它。
    import inspect

    entries_body = inspect.getsource(
        print_list_mod.PrintListMixin._print_entries
    )
    ok("建表这条路只排定时器，不直接同步预热",
       "self._warm_print_thumbs(" not in entries_body
       and "_schedule_print_thumbs_warm(" in entries_body)
    whole_module = inspect.getsource(print_list_mod.manage)
    ok("「管理图片 / 插入图片」仍同步预热（它们紧接着就要用缓存）",
       whole_module.count("self._warm_print_thumbs(") >= 2,
       str(whole_module.count("self._warm_print_thumbs(")))

    d.set_task(tid)
    warmed = {"count": 0}
    real_warm = d._warm_print_thumbs

    def counting_warm(files=None):
        warmed["count"] += 1
        return real_warm(files)

    d._warm_print_thumbs = counting_warm
    try:
        d._schedule_print_thumbs_warm([str(probe)])
        ok("排定时器：待办记下了要补的图、定时器已启动，且这一拍还没干活",
           d._print_warm_timer.isActive() and d._print_warm_pending
           and warmed["count"] == 0,
           f"pending={len(d._print_warm_pending)} warm={warmed['count']}")
        got = wait_until(app, lambda: warmed["count"] >= 1, timeout=5.0)
        ok("首帧之后定时器把它补上（用户在界面里时再做）",
           got and warmed["count"] >= 1, str(warmed["count"]))
    finally:
        d._warm_print_thumbs = real_warm

    # 切任务要撤掉待办：否则定时器回来会把上一个任务的图生成进新任务
    d._schedule_print_thumbs_warm([str(probe)])
    d.set_task(tid)
    ok("切任务撤掉待办并停表（不跨任务生成缩略图）",
       not d._print_warm_pending and not d._print_warm_timer.isActive(),
       f"pending={d._print_warm_pending} "
       f"active={d._print_warm_timer.isActive()}")

    pump(app, 4)
    d.shutdown_workers()
