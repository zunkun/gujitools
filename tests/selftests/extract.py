# -*- coding: utf-8 -*-
"""extract 阶段全量执行自测：真实子进程跑提取、进度/清单/尺寸/日志。"""

NAME = "extract"
DEPENDS: list[str] = ["tasklist"]
TITLE = "extract"


def run(ctx) -> None:
    import time
    from pathlib import Path

    from PySide6.QtGui import QImageReader

    from tests.selftests._context import ok, wait_worker

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid

    d._select_stage(0)
    d.run_stage(resume=False)
    wait_worker(d, app)
    # wait_worker 只看进程状态：进程退出时最后一条 finished 事件（才带
    # done=6）可能还排在事件队列里没被读完，直接读状态会偶发拿到 done=5。
    for _ in range(60):
        app.processEvents()
        if repo.stage_states(tid)["extract"]["done"] == 6:
            break
        time.sleep(0.05)
    state = repo.stage_states(tid)["extract"]
    ok("extract 成功", state["status"] == "success", str(state))
    ok("进度 6/6", (state["done"], state["total"]) == (6, 6), str(state))
    for _ in range(15):
        app.processEvents(); time.sleep(0.1)
    ok("提取结果 6 页入清单", len(repo.load_pages(tid)) == 6)
    # extract 阶段记录的原始尺寸与实际图片文件一致
    first_page = repo.load_pages(tid)[0]["file"]
    stem = Path(first_page).stem
    meta = repo.image_size(tid, stem)
    actual = QImageReader(first_page).size()
    ok("extract 记录图片原始尺寸", meta == (actual.width(), actual.height()),
       f"db={meta} actual={actual.width()}x{actual.height()}")
    log = d.log_view.toPlainText()
    ok("中文日志无乱码", "处理完成" in log and "\\ufffd" not in repr(log))

    # ---- 输出尾巴不许丢（"提取像被中断 / 只提取了一半"的回归守卫）----
    # 背景：worker 退出时管道里可能还压着一批 progress/log 事件没被 GUI 读完，
    # 收尾时若直接清 process/run_id，这批事件会被永久丢掉 —— 进度停在中间值、
    # 日志缺「处理完成」。这里直接喂字节验两条纪律：
    # ① 事件被管道劈成两半时要拼回来（不拼 = 这条进度被当成"人读日志"丢掉）
    d._stdout_tail = ""
    d._consume_worker_stdout(b'{"type":"progress","done":3,"to')
    d._consume_worker_stdout(b'tal":6}\n')
    ok("半行事件能拼回来（进度 3/6）", d._last_progress == (3, 6), str(d._last_progress))

    # ② 没收到换行的半条不许当成完整事件用（否则会把半截 JSON 当日志刷屏）
    d._consume_worker_stdout(b'{"type":"progress","done":9,"total":9}')
    ok("未收尾时不认半行", d._last_progress == (3, 6), str(d._last_progress))
    ok("半行留在缓冲区等下一批", d._stdout_tail.startswith('{"type"'), repr(d._stdout_tail))

    # ③ 协议外的裸 print（无换行）要立刻收成人读日志，不能留在缓冲区里 ——
    # 否则下一条真正的事件会被拼到它后面、一起解析失败（"丢半条"变"丢一条"）
    d._stdout_tail = ""
    d._consume_worker_stdout(b"warning: bare print without newline")
    ok("裸 print 余量立刻入日志", "bare print without newline" in d.log_view.toPlainText()
       and d._stdout_tail == "", repr(d._stdout_tail))
    d._consume_worker_stdout(b'{"type":"progress","done":5,"total":6}\n')
    ok("裸 print 余量不吃掉下一条事件", d._last_progress == (5, 6), str(d._last_progress))

    # ④ 收尾那次读取（final=True）必须把残留半行也吃掉，不许留在缓冲区里
    d._stdout_tail = ""
    d._consume_worker_stdout(
        b'{"type":"progress","done":6,"total":6}', final=True
    )
    ok("收尾读干管道余量（进度 6/6）", d._last_progress == (6, 6), str(d._last_progress))
    ok("收尾后缓冲区清空", d._stdout_tail == "", repr(d._stdout_tail))
    # 还原运行态：本节只借宿主页面的解析函数用，别把状态留给后面的模块
    d._stdout_tail = ""
    d._progress_dirty = False
    d._progress_ui_timer.stop()
