# -*- coding: utf-8 -*-
"""执行按钮的防抖与「执行权」占用守卫自测。

覆盖的核心是**同一个洞**：原先只用 ``self.process.state()`` 判断"在不在跑"，
而 ``run_stage`` 收到点击后还要校验参数、组装 effects、写运行配置，做完才
``QProcess.start()``——那段同步重活里 ``self.process`` 还是 None，连点第二下
就能溜过去，起出第二个 worker（两个 torch 同时加载、同写一批输出目录）。

六条断言线：
1. 连击的第二下被**静默**吞掉（不弹提示，免得刷一串"任务进行中"）；
2. 子任务在跑时再点 → 拒绝并提示；
3. **受理窗口期**（只有受理标记、还没进程对象）→ 照样拦住（就是上面那个洞）；
4. 按钮状态跟随执行权，且「中断」只认子任务进程（检测在跑时不该亮）；
5. 「提交本次任务」与「执行本子任务」共用同一份执行权；
6. 单页检测换页重检**允许顶替**（旧进程先断信号再杀，始终只有一个在跑）；
7. **没跑起来的受理不占用防抖预算**（防抖量"距上次真正启动进程"，不是"距上次
   受理"——否则「提交被拒 → 马上点生成预览」会被静默吞掉）；
8. 进程收尾自动释放执行权。

⚠️ 全程不真起 worker 子进程（一次 torch 冷启动 5 秒以上），执行体被替换成
记录函数；用假进程对象模拟"正在运行"。
"""

from __future__ import annotations

from pathlib import Path

NAME = "run_guard"
DEPENDS: list[str] = ["tasklist"]
TITLE = "执行按钮防抖与占用守卫"


class _FakeProc:
    """只实现守卫真正用到的 ``state()``：模拟一个还在跑的 QProcess。"""

    def __init__(self, running: bool = True):
        self.running = running

    def state(self):
        from PySide6.QtCore import QProcess

        return (
            QProcess.ProcessState.Running
            if self.running
            else QProcess.ProcessState.NotRunning
        )


def run(ctx) -> None:
    import ast

    from PySide6.QtCore import QProcess

    from tests.selftests._context import ROOT, ok, pump

    app, d, repo = ctx.app, ctx.d, ctx.repo

    # ---- 0. 带图标的按钮不得用 setStyleSheet 上样式（会把 qss 整串抹掉）----
    # qfluent 按钮的 qss 里有 `PushButton[hasIcon=true]{padding-left:36px}`，
    # 图标是 paintEvent 手绘的，全靠这条让居中的文字让开；整串替换后图标就
    # 压到文字上（2026-09-23 用户报「执行本子任务按钮中的图片显示在了文字上面」）。
    # 加粗一律走 desktop.ui.widgets.bold_button（setFont）。
    bypass = []
    for path in sorted((ROOT / "desktop").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "setStyleSheet"):
                continue
            receiver = getattr(func.value, "attr", None) or getattr(
                func.value, "id", None
            )
            if not receiver or "button" not in receiver.lower():
                continue
            # 遍历整个调用子树：实参可能是条件表达式
            # （`setStyleSheet("…" if pending else "")`），只看 args 会漏掉
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str) \
                        and "font-weight" in sub.value:
                    bypass.append(f"{path.name}:{node.lineno}({receiver})")
                    break
    ok("没有按钮用 setStyleSheet 设 font-weight（qss 被整串替换后图标压字）",
       not bypass, str(bypass))
    qss = d.run_button.styleSheet()
    ok("执行按钮的 qss 完整（hasIcon 的 36px 左边距还在）",
       "hasIcon=true" in qss and "padding" in qss,
       f"样式表长度 {len(qss)}")
    ok("「继续执行」「中断」两颗带图标按钮的 qss 同样完整",
       all("hasIcon=true" in b.styleSheet() for b in (d.resume_button, d.cancel_button)),
       str([len(b.styleSheet()) for b in (d.resume_button, d.cancel_button)]))


    # 专用任务：守卫要读阶段状态刷按钮，需要一个真实 task_id（用完即删）
    tid = repo.create_task(Path("D:/samples/守卫样例.pdf"), "hash-guard", "守卫样例")
    d.set_task(tid)
    pump(app)

    # ---- 替换执行体与提示：只记录"是否被调用"，避免真起 5 秒的 worker ----
    calls: list = []
    toasts: list = []
    saved = (
        d._run_stage_unchecked,
        d._run_rembg_submit_unchecked,
        d._toast,
        d.process,
        d.detect_process,
        d._run_claim,
        d._run_launched_at,
    )
    def _fake_stage(resume=False):
        """替身执行体：记一笔，并模拟"进程真的起来了"（防抖从这里计时）。"""
        calls.append(("stage", resume))
        d._mark_run_launched()

    def _fake_submit():
        calls.append(("submit", None))
        d._mark_run_launched()

    d._run_stage_unchecked = _fake_stage
    d._run_rembg_submit_unchecked = _fake_submit
    d._toast = lambda level, title, content="", *_a, **_kw: toasts.append(
        (level, title, content)
    )
    try:
        def _reset(running_proc=None, detect_proc=None, claim=None):
            """把守卫状态调回已知点（并清掉防抖时钟，免得前一步的受理挡住断言）。"""
            d.process = running_proc
            d.detect_process = detect_proc
            d._run_claim = claim
            d._run_launched_at = 0.0
            d._refresh_run_buttons()

        # ---- 1. 空闲受理 + 连击的第二下被静默吞掉 ----
        _reset()
        d.run_stage()
        ok("空闲时受理执行", calls == [("stage", False)], str(calls))

        # 上一步受理后已随 finally 释放，这次会走到防抖判断
        toasts.clear()
        d.run_stage()
        ok("连点第二次不再执行（防抖吞掉）", calls == [("stage", False)], str(calls))
        ok("防抖是静默的（不弹'任务进行中'骚扰手快的用户）",
           toasts == [], str(toasts))

        # ---- 2. 子任务在跑 → 拒绝并提示 ----
        _reset(running_proc=_FakeProc())
        toasts.clear()
        d.run_stage()
        ok("子任务在跑时不二次执行", calls == [("stage", False)], str(calls))
        ok("拒绝时说清了「什么在跑」",
           len(toasts) == 1 and "子任务" in toasts[0][2], str(toasts))

        # ---- 3. 受理窗口期（关键：就是原先溜过去的那个洞）----
        _reset(claim="子任务")
        toasts.clear()
        d.run_stage()
        ok("只有受理标记、进程还没起时同样拦住",
           calls == [("stage", False)], str(calls))
        ok("窗口期也给了提示", len(toasts) == 1, str(toasts))

        # ---- 4. 按钮状态 ----
        _reset(claim="子任务")
        ok("持有执行权时主按钮置灰",
           not d.run_button.isEnabled() and not d.resume_button.isEnabled())
        ok("持有执行权时「中断」可用", d.cancel_button.isEnabled())

        _reset(detect_proc=_FakeProc())
        ok("单页检测在跑：主按钮置灰",
           not d.run_button.isEnabled())
        ok("单页检测在跑：「中断」不亮（它只杀子任务进程）",
           not d.cancel_button.isEnabled())

        # 释放只针对"受理标记"：假进程要撤掉，否则按钮本就该因它灰着
        _reset(claim="子任务")
        ok("只持有受理标记时主按钮也是灰的", not d.run_button.isEnabled())
        d._release_run()
        ok("释放执行权后主按钮恢复可用", d.run_button.isEnabled())

        # ---- 5. 提交按钮共用同一份执行权 ----
        _reset(running_proc=_FakeProc())
        toasts.clear()
        d.run_rembg_submit()
        ok("子任务在跑时「提交本次任务」也被拦住",
           ("submit", None) not in calls, str(calls))

        _reset()
        d._run_claim = None
        d._run_launched_at = 0.0
        d.run_rembg_submit()   # 交给被替换的实现体，只验证放行
        ok("空闲时「提交本次任务」正常受理",
           calls[-1] == ("submit", None), str(calls))

        # ---- 6. 替换语义：换页重检允许顶替，但子任务在跑时必须让路 ----
        _reset(detect_proc=_FakeProc())
        ok("旧检测在跑时允许换一页重检（replace）",
           d._acquire_run("单页检测", replace=("单页检测",)))
        d._release_run()

        # replace 只放行"同类顶替"：子任务在跑时必须让路
        _reset(running_proc=_FakeProc())
        ok("子任务在跑时不允许塞进单页检测",
           not d._acquire_run("单页检测", replace=("单页检测",)))

        # ---- 7. 没跑起来的受理不占用防抖预算 ----
        # 真实回归：rembg 用例里「提交被前置条件拒绝」紧接着调 run_stage，
        # 若防抖量的是"距上次受理"，那次点击会被静默吞掉、worker 根本不起。
        _reset()
        d._run_stage_unchecked = lambda resume=False: calls.append(("aborted", resume))
        d.run_stage()   # 受理后早退（没启动进程，因此不记 _run_launched_at）
        calls.clear()
        d._run_stage_unchecked = _fake_stage
        d.run_stage()
        ok("没跑起来的受理不再罚掉紧接着的下一次点击",
           calls == [("stage", False)], str(calls))

        # ---- 8. 进程收尾自动释放（含正常结束 / 被杀 / 看门狗兜底三条汇流）----
        _reset(claim="子任务")
        # task_id 置空做隔离：_worker_finished 会写 store 与刷视图，这里只想验释放
        saved_tid = d.task_id
        d.task_id = None
        try:
            d._worker_finished(0, QProcess.ExitStatus.NormalExit)
        finally:
            d.task_id = saved_tid
        ok("进程收尾后执行权自动释放",
           d._run_claim is None and d.run_button.isEnabled(),
           f"claim={d._run_claim!r}")

        # ---- 9. 失败原因必须落盘（"静默失败"唯一的事后可查线索）----
        # 这一类失败**一条输出都没有**：0 条事件、0.2 秒退出、记录里只剩
        # done=0/total=0。用户报的「提交失败，界面也没说为什么」就是它 ——
        # 界面上只有一条会自己消失的 toast，所以原因必须写进 runs.json。
        _reset()
        d.cancel_requested = False
        run_id = repo.create_stage_run(tid, "rembg_submit", {"area": 1})
        d.run_id = run_id
        d.running_stage = "rembg_submit"
        d._last_error_line = None
        toasts.clear()
        d._worker_finished(1, QProcess.ExitStatus.CrashExit)
        rec = next(r for r in repo.list_stage_runs(tid, "rembg_submit")
                   if r["run_id"] == run_id)
        ok("失败原因（退出码）落进运行记录，不再只有 done=0/total=0",
           rec["status"] == "failed" and rec.get("error") == "退出码 1",
           str({k: rec.get(k) for k in ("status", "done", "total", "error")}))
        ok("失败 toast 与记录里的原因一致",
           bool(toasts) and toasts[-1][0] == "error" and toasts[-1][2] == "退出码 1",
           str(toasts))
        ok("失败原因也留在日志里（toast 会消失，日志不会）",
           "失败原因：退出码 1" in d.log_view.toPlainText(),
           d.log_view.toPlainText()[-120:].replace("\n", " / "))

        # 有具体错误行（stderr / 子进程启动失败）时，记具体原因而不是退出码
        run_id2 = repo.create_stage_run(tid, "rembg_submit", {"area": 1})
        d.run_id = run_id2
        d.running_stage = "rembg_submit"
        d._last_error_line = "子进程启动失败：C:\\x\\python.exe"
        d._worker_finished(1, QProcess.ExitStatus.CrashExit)
        rec2 = next(r for r in repo.list_stage_runs(tid, "rembg_submit")
                    if r["run_id"] == run_id2)
        ok("有具体错误行时记具体原因（优先于退出码）",
           rec2.get("error") == "子进程启动失败：C:\\x\\python.exe",
           str(rec2.get("error")))
        d.run_id = None
        d.running_stage = None

        # 成功的那次不留 error（别把上一条失败的原因串过来）
        ok_run = repo.create_stage_run(tid, "rembg_submit", {"area": 1})
        repo.finish_stage(tid, ok_run, "success", progress=(6, 6))
        rec_ok = next(r for r in repo.list_stage_runs(tid, "rembg_submit")
                      if r["run_id"] == ok_run)
        ok("成功的记录不带失败原因",
           rec_ok["status"] == "success" and not rec_ok.get("error"),
           str(rec_ok.get("error")))
    finally:
        (
            d._run_stage_unchecked,
            d._run_rembg_submit_unchecked,
            d._toast,
            d.process,
            d.detect_process,
            d._run_claim,
            d._run_launched_at,
        ) = saved
        d._refresh_run_buttons()
        repo.delete_task(tid)
