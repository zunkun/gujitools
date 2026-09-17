# -*- coding: utf-8 -*-
"""源文件备份自测：源 PDF 被移动/删除后，后续操作仍走任务目录里的备份。

背景：导入时任务目录下会留一份 PDF 副本，但详情页与 extract 入参一直读
索引里的 ``source_path``（用户磁盘上的原文件）——源文件一挪走，详情页就
「渲染失败」、extract 直接拒绝执行。备份才是任务自包含的那份。
"""

from pathlib import Path

NAME = "source_copy"
DEPENDS: list[str] = ["tasklist"]
TITLE = "源文件备份"

ROOT = Path(__file__).resolve().parents[2]


def run(ctx) -> None:
    import os

    from tests.selftests._context import make_pdf, ok

    app, w, d, repo = ctx.app, ctx.w, ctx.d, ctx.repo

    # ---- 正常导入：备份落在任务目录 ----
    src = make_pdf(ctx.tmp / "会被移走的古籍.pdf", 3)
    tid = repo.create_task(src, "hash-movable", "会被移走的古籍")
    backup = repo.copy_source_to_task(tid, src)
    ok("导入后任务目录有 PDF 备份", backup.is_file(), str(backup))
    ok("备份在任务目录内", str(backup).startswith(str(repo.task_dir(tid))), str(backup))
    ok("source_copy_path 命中备份", repo.source_copy_path(tid) == backup)

    # ---- 源文件没了（被移动/删除）：一切照旧 ----
    os.remove(src)
    ok("源已删除", not src.exists())
    ok("源删除后仍能取到备份", repo.source_copy_path(tid) == backup)
    ok("ensure_source_copy 复用已有备份", repo.ensure_source_copy(tid) == backup)

    w._open_detail(tid)
    ok("详情页用备份 PDF（不是源路径）", d.source_path == backup, str(d.source_path))
    ok("详情页 PDF 真实存在", d.source_path.exists())
    ok("详情页显示的文件名不变", d.source_label.text() == backup.name)

    # extract 实际拿到的入参：拦在「起子进程」之前，不真跑，
    # 确认交给 CLI 的是备份而不是源路径（源此刻已经被删了）
    captured: dict = {}
    original_launch = d._launch_stage_process
    d._launch_stage_process = lambda stage, args, resume=False: captured.update(
        {"stage": stage, "args": args}
    )
    try:
        d._select_stage(0)  # 第一步：提取图片
        d.run_stage()
    finally:
        d._launch_stage_process = original_launch
    ok(
        "extract 入参是备份 PDF",
        captured.get("args", {}).get("input") == str(backup),
        str(captured.get("args", {}).get("input")),
    )
    ok("extract 阶段未被「源文件缺失」拦下", captured.get("stage") == "extract")

    # 让缩略图后台线程跑完再动磁盘：PreviewWorker 正读着这份 PDF，
    # 抢着删会撞上 WinError 32（另一个程序正在使用此文件）
    from tests.selftests._context import pump

    d.source_pdf_viewer.set_pdf(None)
    pump(app, times=15)

    # ---- 备份被误删、源还在：自愈补一份 ----
    os.remove(backup)
    make_pdf(ctx.tmp / "会被移走的古籍.pdf", 3)
    healed = repo.ensure_source_copy(tid)
    ok("备份丢失后按源补回", healed is not None and healed.is_file(), str(healed))

    # ---- 备份与源都没了：明确报错而不是静默渲染失败 ----
    os.remove(healed)
    os.remove(ctx.tmp / "会被移走的古籍.pdf")
    ok("源与备份都缺失时返回 None", repo.ensure_source_copy(tid) is None)

    original_toast = d._toast
    toasts: list[tuple] = []
    d._toast = lambda *a: toasts.append(a)
    try:
        w._open_detail(tid)
    finally:
        d._toast = original_toast
    ok(
        "PDF 全缺时给出提示",
        any(a and a[0] == "error" for a in toasts),
        str(toasts),
    )

    # ---- 防回归：extract 入参不许再回到索引里的 source_path ----
    runner_src = (ROOT / "desktop" / "pages" / "taskdetail" / "runner.py").read_text(
        encoding="utf-8"
    )
    ok("runner 不再读 task['source_path']", 'task["source_path"]' not in runner_src)
    page_src = (ROOT / "desktop" / "pages" / "taskdetail" / "page.py").read_text(
        encoding="utf-8"
    )
    ok(
        "详情页改用 store.ensure_source_copy",
        "ensure_source_copy(task_id)" in page_src,
    )

    repo.delete_task(tid)
    w._open_detail(ctx.tid)  # 还原后续模块依赖的详情页
