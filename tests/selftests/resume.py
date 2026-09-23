# -*- coding: utf-8 -*-
"""中断与续跑自测：大部头任务跑 extract 中途中断，再续跑补齐缺失页。"""

NAME = "resume"
DEPENDS: list[str] = ["tasklist"]
TITLE = "中断与续跑"


def run(ctx) -> None:
    import time

    from tests.selftests._context import ok, wait_worker

    app, d, repo = ctx.app, ctx.d, ctx.repo

    tid_big = repo.create_task(ctx.big_pdf, "", "大部头")
    ctx.tid_big = tid_big
    d.set_task(tid_big)
    # 提高渲染分辨率拖慢速度，保证有可靠的中断窗口
    d.control_stack.widget(0).zoom.setValue(4)
    d.run_stage(resume=False)
    # 等到确实有页产出再中断。原来是固定 sleep 1.5s——GUI 提取改成多线程后
    # 80 页可能整轮都跑完了，中断窗口就没了（表现为状态是 success 而非 cancelled）。
    # 这里按"进度 > 0"判断，与提取快慢无关。
    deadline = time.time() + 15
    while time.time() < deadline:
        app.processEvents()
        _cur = repo.stage_states(tid_big)["extract"]
        if _cur.get("done", 0) >= 1 or _cur["status"] != "running":
            break
        time.sleep(0.01)
    app.processEvents()
    d.cancel_stage()
    # 持续补发 kill，防止偶发的终止延迟导致旧进程跑完
    deadline = time.time() + 30
    while d.process and d.process.state() != 0 and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
        if d.process and d.process.state() != 0:
            d.process.kill()
    app.processEvents()
    # 详情带上真实状态：否则失败时只有一个断言名，看不出是"跑完了"还是"报错了"
    _st = repo.stage_states(tid_big)["extract"]
    ok("中断后状态 cancelled", _st["status"] == "cancelled", str(_st))

    # 续跑：只补缺失页
    partial = repo.extract_output_dir(tid_big)
    have = len(list(partial.glob("*.jpg"))) if partial.exists() else 0
    d.run_stage(resume=True)
    wait_worker(d, app, timeout=300)
    state = repo.stage_states(tid_big)["extract"]
    ok("续跑后成功", state["status"] == "success", str(state))
    total_now = len(list(partial.glob("*.jpg")))
    ok(f"续跑补齐缺失页（中断前 {have} 页 → 续跑后 {total_now} 页）", total_now >= have)
    # ⚠️ 页码必须**正好**是缺失的那几页。GUI 侧曾经把 parse_pages 的结果又减了一次 1
    # （它本身就返回 0-based），整段页码前移一页：缺失页里的最后一页永远补不出来，
    # 前一页被反复重做（而这里的 `>= have` 断言发现不了）。用「页集合」钉死。
    for _ in range(40):
        app.processEvents()
        if len(list(partial.glob("*.jpg"))) >= _total_pages(ctx):
            break
        time.sleep(0.05)
    stems = sorted(int(p.stem) for p in partial.glob("*.jpg") if p.stem.isdigit())
    expected = list(range(1, _total_pages(ctx) + 1))
    ok(
        f"续跑后页集合完整（1..{_total_pages(ctx)}）",
        stems == expected,
        f"缺 {sorted(set(expected) - set(stems))}，多 {sorted(set(stems) - set(expected))}",
    )

    # 全量重跑：跑完就该是**满进度 + 日志有「处理完成」**。
    # 这是"提取像被中断 / 只提取了一半"的端到端守卫：大任务时 GUI 吃不下每页一条
    # 的进度事件，收尾若不等管道读干就清引用，末尾那批事件（含 6/6 那条进度和
    # 「处理完成」日志）会被整批丢掉，运行记录就会停在中间值。
    d.control_stack.widget(0).zoom.setValue(1)  # 上面为制造中断窗口调到了 4，改回来
    before_log = d.log_view.toPlainText()
    d.run_stage(resume=False)
    wait_worker(d, app, timeout=300)
    total_pages = _total_pages(ctx)
    deadline = time.time() + 30
    while time.time() < deadline:
        app.processEvents()
        _st = repo.stage_states(tid_big)["extract"]
        if (_st["done"], _st["total"]) == (total_pages, total_pages):
            break
        time.sleep(0.05)
    _st = repo.stage_states(tid_big)["extract"]
    ok(
        f"全量提取进度满格（{total_pages}/{total_pages}）",
        (_st["done"], _st["total"]) == (total_pages, total_pages),
        str(_st),
    )
    new_log = d.log_view.toPlainText()[len(before_log):]
    ok("全量提取日志含『处理完成』（尾巴没被丢）", "处理完成" in new_log, new_log[-200:])

    # ---- 收尾必须把管道读干（确定性地钉住，不靠"跑得快不快"这种运气）----
    # 上面那条是端到端的：能不能复现取决于 GUI 有没有落后于 worker，属于概率性
    # 断言。这里用一个假 proc 把事件**攒在管道里**，模拟"Qt 的 finished 先到了、
    # 管道里还剩一批事件"——那正是丢尾巴的现场。收尾流程必须把它们全读出来。
    guard_mark = "看门狗尾巴守卫标记"
    fake = _FakeProc(
        [
            b'{"type":"progress","done":1,"total":2}\n',
            b'{"type":"progress","done":2,"total":2}\n',
            # 末条故意不带换行：收尾那次读取要连残留半行一起吃掉
            ('{"type":"log","message":"%s"}' % guard_mark).encode("utf-8"),
        ]
    )
    d.task_id, d.running_stage, d.process = tid_big, "extract", fake
    d.run_id = repo.create_stage_run(tid_big, "extract", {}, False)
    d._last_progress = (0, 0)
    d._stdout_tail = ""
    d._worker_finished(0, None)
    _g = repo.stage_states(tid_big)["extract"]
    ok("收尾排空管道后进度满格（2/2）", (_g["done"], _g["total"]) == (2, 2), str(_g))
    ok("收尾排空管道后日志补齐（含无换行的末条）",
       guard_mark in d.log_view.toPlainText())


class _FakeProc:
    """假 worker 进程：事件先攒在"管道"里，读一次吐一批。

    只实现收尾流程用到的三个方法；``state()`` 报 NotRunning 模拟"进程已退出、
    Qt 却还没把管道读完"的现场。
    """

    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)

    def state(self):
        from PySide6.QtCore import QProcess

        return QProcess.NotRunning

    def readAllStandardOutput(self) -> bytes:
        data, self._chunks = b"".join(self._chunks), []
        return data

    def readAllStandardError(self) -> bytes:
        return b""


def _total_pages(ctx) -> int:
    """大部头样例 PDF 的真实页数（不依赖 GUI 侧缓存的 pdf_page_count）。"""
    import pymupdf

    doc = pymupdf.open(str(ctx.big_pdf))
    try:
        return doc.page_count
    finally:
        doc.close()
