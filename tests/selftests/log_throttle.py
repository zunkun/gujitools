# -*- coding: utf-8 -*-
"""日志攒批器（``desktop/ui/log_throttle.py``）自测。

背景（2026-10-20 用户报「检测文本框执行过程中页面卡顿」）
    detect/extract 逐页打日志，原先每来一行就 ``append`` 一次 —— 一次
    QTextDocument 布局 + 一次状态条刷新，几百上千行下来主线程被拖住。
    ``LogCoalescer`` 把它们攒成**低频的一次 append**。

钉住五条契约：
1. 攒批窗口内**不写**；
2. 到期**一次**写入全部行（不是逐行）；
3. 待写行数达到 ``max_pending`` 立刻冲刷；
4. ``append_now`` 先冲刷已攒的，再立刻写这一行（阶段起止那几行不许等）；
5. ``flush()`` 幂等、``pending()`` 归零。
"""

NAME = "log_throttle"
DEPENDS: list[str] = ["log_overlay"]
TITLE = "日志攒批（执行期主线程不再被逐行日志拖住）"


class _Recorder:
    """只实现 ``append(str)`` 的记录型 target（契约要求的唯一接口）。"""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def append(self, text: str) -> None:
        self.lines.append(text)


def run(ctx) -> None:
    from desktop.ui.log_throttle import LogCoalescer
    from tests.selftests._context import ok, pump

    app = ctx.app

    # ---- 1. 窗口内不写；到期一次写齐 ----
    rec = _Recorder()
    logs = LogCoalescer(rec, interval_ms=60)
    for i in range(20):
        logs.append(f"line {i}")
    ok("攒批窗口内一行都没写（不再逐行 append）", rec.lines == [], str(rec.lines[:3]))
    ok("待写行数正确", logs.pending() == 20, str(logs.pending()))
    pump(app, times=6, interval=0.03)
    ok("到期后**一次**写入全部 20 行", len(rec.lines) == 1
       and rec.lines[0].count("\n") == 19, f"写入 {len(rec.lines)} 次")
    ok("flush 后待写归零", logs.pending() == 0, str(logs.pending()))

    # ---- 2. flush() 幂等 ----
    logs.flush()
    ok("空 flush 不产生新写入（幂等）", len(rec.lines) == 1, str(len(rec.lines)))

    # ---- 3. 达到 max_pending 立刻冲刷 ----
    rec2 = _Recorder()
    logs2 = LogCoalescer(rec2, interval_ms=10_000, max_pending=5)
    for i in range(5):
        logs2.append(f"x{i}")
    ok("待写达到上限 → 立刻冲刷（不等窗口）",
       len(rec2.lines) == 1 and logs2.pending() == 0,
       f"写入={len(rec2.lines)} pending={logs2.pending()}")

    # ---- 4. append_now 先冲刷再写 ----
    rec3 = _Recorder()
    logs3 = LogCoalescer(rec3, interval_ms=10_000)
    logs3.append("a")
    logs3.append("b")
    logs3.append_now("=== 开始执行 ===")
    ok("append_now 先冲刷已攒的行、再单独写这一行",
       rec3.lines == ["a\nb", "=== 开始执行 ==="], str(rec3.lines))
    ok("append_now 之后待写归零", logs3.pending() == 0, str(logs3.pending()))

    # ---- 5. 空行忽略（不占攒批位）----
    rec4 = _Recorder()
    logs4 = LogCoalescer(rec4, interval_ms=10_000)
    logs4.append("")
    ok("空行不进入攒批", logs4.pending() == 0, str(logs4.pending()))

    # 收尾：把定时器停掉（否则窗口到期会在用例结束后回写记录器）
    for item in (logs, logs2, logs3, logs4):
        item.flush()
