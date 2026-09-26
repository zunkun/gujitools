# -*- coding: utf-8 -*-
"""资源与生命周期：退出/取消/中断时不许留垃圾、不许崩（2026-09-26 审计）。

覆盖五处：

1. **效果图暂存目录**：中断「生成 PDF」走 `QProcess.kill()`（Windows
   `TerminateProcess`）——`with TemporaryDirectory` 的清理**不会执行**，
   每次取消都在 %TEMP% 留下几百 MB~GB 的整页 PNG。改成固定根 + 属主 pid，
   下次生成 PDF 时扫掉「属主已死」的旧目录。
2. **PreviewWorker 无 cancel**：整本缩略图渲染（几千页 × ~160ms）在收尾时只能
   等它跑完，`shutdown_workers` 必然超时、线程被摘出去后还在啃 GIL。
3. **常驻 YOLO 服务的发现文件**：只在正常退出时清理，被 kill 会留下，
   而且是**按指纹**分文件的、从不回收 → 客户端扫到陈旧文件就去连不存在的端口。
4. **服务日志**：永久追加、从不轮转。
5. **拉起服务的 Popen**：不留引用（对象立刻被 GC、服务退出后没人 wait → POSIX 僵尸）。
"""

NAME = "resource_lifecycle"
DEPENDS: list[str] = []
TITLE = "资源与生命周期"


def run(ctx) -> None:
    import json
    import os
    import time
    from pathlib import Path

    from tests.selftests._context import ok

    # ---- 1. 暂存目录清扫：活属主保留、死属主删、陈旧无标记删 ----
    from desktop.stages.print_stage import staging_root, sweep_orphan_staging

    root = staging_root()
    root.mkdir(parents=True, exist_ok=True)
    live = root / "case-live"
    dead = root / "case-dead"
    stale = root / "case-stale"
    for d in (live, dead):
        d.mkdir(parents=True, exist_ok=True)
    stale.mkdir(parents=True, exist_ok=True)
    (live / "owner.pid").write_text(str(os.getpid()), encoding="utf-8")
    (dead / "owner.pid").write_text("999999", encoding="utf-8")
    old = time.time() - 7200
    os.utime(stale, (old, old))

    removed = sweep_orphan_staging(exclude=live)
    ok("暂存目录：属主进程还活着的**不删**", live.exists(), str(live))
    ok("暂存目录：属主已死的删掉", not dead.exists(), str(dead))
    ok("暂存目录：无属主标记且陈旧的删掉", not stale.exists(), str(stale))
    ok("暂存目录：返回删除个数", removed >= 2, str(removed))

    # ---- 2. PreviewWorker 真的能取消 ----
    import fitz
    from desktop.workers.preview_worker import PreviewWorker

    pdf = ctx.tmp / "resource_lifecycle.pdf"
    doc = fitz.open()
    for _ in range(5):
        doc.new_page()
    doc.save(str(pdf))
    doc.close()

    worker = PreviewWorker(pdf, thumbnails=True, cache_dir=None, render_missing=True)
    done = {"completed": False, "thumbs": 0}
    worker.completed.connect(lambda: done.__setitem__("completed", True))
    worker.thumbnail_ready.connect(lambda *_: done.__setitem__("thumbs", done["thumbs"] + 1))
    worker.cancel()  # 开跑前就取消 → 第一页开头就退出
    worker.run()
    ok("PreviewWorker：取消后立刻收手（不再逐页渲染）", done["thumbs"] == 0, str(done))
    ok("PreviewWorker：取消后仍发 completed（宿主状态能收尾）", done["completed"], str(done))

    # ---- 3. 队列按任务取消 ----
    from PySide6.QtCore import QObject

    from desktop.workers.serial_jobs import SerialJobQueue

    # ⚠️ owner 必须留住 Python 引用：QTimer 是它的子对象，owner 被 GC 掉定时器
    #    也随之销毁（第一次跑就踩到 `Internal C++ object already deleted`）。
    owner = QObject()
    queue = SerialJobQueue(owner)
    try:
        class _W(QObject):
            def run(self):  # pragma: no cover - 不会真跑（被 gate 扣住）
                pass

        queue.submit(_W(), label="a1", tag="task-a")
        queue.submit(_W(), label="b1", tag="task-b")
        ok("队列：两个不同 tag 的 job 都在排队", queue.pending_count() == 2, str(queue.pending_count()))
        stopped = queue.cancel_tag("task-a")
        ok("队列：取消 task-a 后它自己的活没了", queue.pending_count() == 1, str(queue.pending_count()))
        ok("队列：没有在跑的活时 cancel_tag 返回 True", stopped is True, str(stopped))
        ok("队列：cancel_tag(None) 不动任何活", queue.cancel_tag(None) is True)
    finally:
        queue.shutdown()

    # ---- 4. 常驻服务：发现文件清扫 + 日志轮转 + Popen 保留引用 ----
    from functions import yolo_service as ys

    dead_file = ys.service_file("case-dead")
    live_file = ys.service_file("case-live")
    bad_file = ys.service_file("case-bad")
    dead_file.write_text(json.dumps({"port": 1, "fp": "case-dead", "pid": 999999}), encoding="utf-8")
    live_file.write_text(json.dumps({"port": 2, "fp": "case-live", "pid": os.getpid()}), encoding="utf-8")
    bad_file.write_text("{not json", encoding="utf-8")
    ys.sweep_stale_service_files()
    ok("服务发现文件：属主已死的被清掉", not dead_file.exists(), str(dead_file))
    ok("服务发现文件：属主还活着的保留", live_file.exists(), str(live_file))
    ok("服务发现文件：损坏的也清掉（它已经没用了）", not bad_file.exists(), str(bad_file))
    ok("服务日志有体积上限（会轮转，不无界增长）",
       isinstance(ys.LOG_MAX_BYTES, int) and ys.LOG_MAX_BYTES > 0, str(ys.LOG_MAX_BYTES))
    ok("拉起的服务进程保留了引用（否则退出后没人 wait → 僵尸）",
       isinstance(ys._SERVICE_PROCS, list))

    live_file.unlink(missing_ok=True)

    # ---- 5. 回归形态：源码层面钉住这几个决定 ----
    repo = Path(__file__).resolve().parents[2]

    def code_of(rel: str) -> str:
        raw = (repo / rel).read_text(encoding="utf-8")
        return "\n".join(line.split("#", 1)[0] for line in raw.splitlines())

    stage = code_of("desktop/stages/print_stage.py")
    ok("print_stage 不再用 TemporaryDirectory（kill 时清不掉）",
       "TemporaryDirectory" not in stage and "sweep_orphan_staging" in stage)
    runner = code_of("desktop/pages/taskdetail/runner.py")
    ok("取消阶段时顺手回收暂存目录", "sweep_orphan_staging()" in runner)
    ok("看门狗有无进展预警（不是只能干等）",
       "_warn_if_stalled" in runner and "STALL_WARN_S" in runner)
    ok("worker 有输出会重置无进展计时", "_last_event_at = time.time()" in runner)
    preview = code_of("desktop/workers/preview_worker.py")
    ok("PreviewWorker 有 cancel() 且渲染循环会检查它",
       "def cancel(self)" in preview and "if self._cancelled:" in preview)
    host = code_of("desktop/workers/worker_host.py")
    ok("收尾时先给 worker 发 cancel() 再等", "cancel()" in host and "stop_thread(" in host)
    queue_code = code_of("desktop/workers/serial_jobs.py")
    ok("队列支持按 tag 取消", "def cancel_tag(" in queue_code)
    page = code_of("desktop/pages/tasklist/page.py")
    ok("删任务前先停该任务自己的后台导入", "cancel_tag(task_id" in page)
    ok("导入提交时带上归属 tag", "tag=task_id" in page)
    worker = code_of("desktop/workers/source_thumbnails_worker.py")
    ok("缩略图 worker 提供 wait_copy（删任务前等复制收手）",
       "def wait_copy(" in worker)
