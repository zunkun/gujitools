# -*- coding: utf-8 -*-
"""崩溃取证自测（2026-11-21）。

背景：生产版反复在 ``Qt6Gui.dll+0xe0130``（``QScreen::geometry`` 首指令）崩，
WER ``LocalDumps`` 在这台机器上实测不落盘，等于没有现场。为此加了两层取证
（``utils/crash_log`` / ``utils/crash_dump``）并把 Qt 消息接进同一份日志。

断言线：

1. 日志能装、能写、能滚动、能取尾部；``[crumb]`` 前缀固定；
2. 两条 excepthook 都会落到日志里，且**原来的钩子仍被调用**（不能把别人的吃掉）；
3. Qt 消息能进日志（``[qt:warn]``）；
4. 原生崩溃真的能被逮住——另起子进程造一次真 AV，日志里必须有
   ``Fatal Python error`` 和线程栈（这是整套取证的核心价值）；
5. 转储模块的地址换算/模块枚举可用（``_where`` / ``_explain`` / ``_modules``）；
6. 接线（静态契约）：GUI 入口在 QApplication 之后立刻取证，且 **faulthandler
   在原生过滤器之前**装好（顺序反了就没有 Python 栈）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

NAME = "crash_forensics"
DEPENDS: list[str] = []
TITLE = "崩溃取证（日志 + Qt 消息 + 原生转储）"

_ENV = "GUJI_CRASH_LOG"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def run(ctx) -> None:
    # ⚠ 本用例会把 crash_log 的 excepthook 装进**本进程**。一旦断言失败，
    # 框架 re-raise 的 traceback 会被这个钩子写进日志文件、stderr 上什么都
    # 看不见（上面只印一句"执行异常"）。所以无论成败都得摘钩子。
    import utils.crash_log as crash_log

    try:
        _run(ctx)
    finally:
        try:
            crash_log.uninstall()
        except Exception:
            pass
        os.environ.pop(_ENV, None)


def _run(ctx) -> None:
    from tests.selftests._context import ok

    import utils.crash_log as crash_log

    root = Path(__file__).resolve().parents[3]
    work = Path(ctx.tmp) / "crash_forensics"
    work.mkdir(parents=True, exist_ok=True)
    log_file = work / "crash.log"

    # ---------------- 1. 装 + 写 + 不覆盖归档 ----------------
    log_file.write_bytes(b"x" * (crash_log.MAX_BYTES + 1))  # 先造一份超大旧日志
    os.environ[_ENV] = str(log_file)
    installed = crash_log.install(work)
    ok("日志装得上（返回落点）", installed == log_file, str(installed))
    ok("幂等：重复装不换文件", crash_log.install(work) == log_file)
    archives = sorted(work.glob("crash_log_*.log"))
    ok("超大旧日志按时间戳归档、不覆盖旧现场",
       len(archives) == 1 and archives[0].stat().st_size == crash_log.MAX_BYTES + 1,
       str([p.name for p in archives]))

    crash_log.breadcrumb("selftest 面包屑")
    crash_log.log("selftest 普通日志")
    text = _read(log_file)
    ok("面包屑带固定前缀写入", "[crumb] selftest 面包屑" in text)
    ok("行首带时间戳与线程名", "selftest 普通日志" in text and "MainThread" in text)

    # ---------------- 2. 两条 excepthook ----------------
    calls: list[str] = []
    crash_log.uninstall()
    os.environ[_ENV] = str(log_file)  # 上一轮写过的内容保留，便于断言"追加"

    def _prev_hook(exc_type, exc, tb):  # noqa: ANN001
        calls.append(getattr(exc_type, "__name__", "?"))

    sys.excepthook = _prev_hook
    crash_log.install(work)
    sys.excepthook(ValueError, ValueError("selftest 主线程炸了"), None)
    ok("主线程未捕获异常进日志", "selftest 主线程炸了" in _read(log_file))
    ok("原来的 excepthook 仍被调用（不吞别人的钩子）", calls == ["ValueError"],
       str(calls))

    sys.excepthook = sys.__excepthook__  # 复位，别影响后面的自测模块
    crash_log.uninstall()

    # ---------------- 3. Qt 消息 ----------------
    os.environ[_ENV] = str(log_file)
    crash_log.install(work)
    from desktop.ui.qt_log import install as install_qt_log

    install_qt_log()
    from PySide6.QtCore import qInstallMessageHandler, qWarning

    qWarning("selftest-crash-log 探针")
    ok("Qt 警告进日志（带级别）", "[qt:warn] selftest-crash-log 探针" in _read(log_file))
    qInstallMessageHandler(None)

    # ---------------- 4. 原生崩溃真能被逮住 ----------------
    crash_log.uninstall()
    if getattr(sys, "frozen", False):
        ok("打包环境：跳过原生崩溃实测（子进程用的是自带解释器）", True)
    else:
        probe = work / "native.log"
        src = (
            "import faulthandler, os, sys\n"
            f"sys.path.insert(0, r'{root}')\n"
            "os.environ['GUJI_CRASH_LOG'] = r'%s'\n"
            "import utils.crash_log as cl\n"
            "assert cl.install()\n"
            "cl.breadcrumb('崩前最后一条')\n"
            "faulthandler._sigsegv()\n" % str(probe)
        )
        proc = subprocess.run([sys.executable, "-c", src], timeout=120)
        body = _read(probe)
        ok("原生崩溃：子进程确实异常退出", proc.returncode != 0, str(proc.returncode))
        ok("原生崩溃：日志里有 Fatal Python error", "Fatal Python error" in body)
        ok("原生崩溃：日志里带线程栈（File 行）", 'File "' in body)
        ok("原生崩溃：崩前的面包屑还在（最后做了什么）",
           "[crumb] 崩前最后一条" in body)

        # ---- 4b. 全套取证：日志 + 原生栈 + minidump 一起落盘 ----
        # 这条才是生产上真正跑的路径：过滤器先写报告/dump，再把链交给
        # faulthandler —— 所以三种产物必须同时出现。
        dump_dir = work / "dump"
        dump_log = work / "dump.log"
        src2 = (
            "import os, sys\n"
            f"sys.path.insert(0, r'{root}')\n"
            "os.environ['GUJI_CRASH_LOG'] = r'%s'\n"
            "import utils.crash_log as cl\n"
            "assert cl.install()\n"
            "import utils.crash_dump as cd\n"
            "assert cd.install(r'%s')\n"
            "cl.breadcrumb('全套取证探针')\n"
            "import faulthandler\n"
            # ⚠ 必须用 _read_null()（真 AV）而不是 _sigsegv()：后者是个纯
            # raise()，不经过 SEH，SetUnhandledExceptionFilter 根本不会被调
            # 用 —— 用它测"全套"会得到"报告 0 份"的假失败。
            "faulthandler._read_null()\n" % (str(dump_log), str(dump_dir))
        )
        proc2 = subprocess.run([sys.executable, "-c", src2], timeout=180)
        reports = sorted(dump_dir.glob("crash_*.txt"))
        dumps = sorted(dump_dir.glob("crash_*.dmp"))
        ok("全套：子进程崩掉了", proc2.returncode != 0, str(proc2.returncode))
        ok("全套：写出了崩溃报告（crash_*.txt）", len(reports) == 1,
           f"{len(reports)} 份")
        report_text = _read(reports[0]) if reports else ""
        ok("全套：报告里识别出访问违例", "访问违例" in report_text)
        ok("全套：报告里带出错地址（模块+偏移）",
           "Qt6" in report_text or ".dll+" in report_text
           or ".exe+" in report_text)
        ok("全套：报告里带调用链候选段", "调用链候选" in report_text)
        ok("全套：报告里附了 crash.log 末尾（崩前动作）",
           "全套取证探针" in report_text)
        ok("全套：minidump 也落了盘", len(dumps) == 1
           and dumps[0].stat().st_size > 4096,
           f"{[d.name for d in dumps]}")
        # 过滤器只在末尾回调 faulthandler —— 这一条证明"链没被截断"，
        # 也就是报告和 Python 栈是同一份现场，而不是二选一。
        ok("全套：faulthandler 仍然拿到现场（链没被截断）",
           "Windows fatal exception" in _read(dump_log))

    # ---------------- 5. 转储模块的地址换算 ----------------
    if sys.platform != "win32":
        ok("非 Windows：无原生转储，跳过", True)
    else:
        import utils.crash_dump as crash_dump

        ok("转储钩子装得上", crash_dump.install(work) is True)
        ok("幂等：重复装不重复挂钩", crash_dump.install(work) is True)
        modules = crash_dump._modules()
        ok("模块枚举拿得到（含本进程主模块）", len(modules) > 3,
           f"{len(modules)} 个")
        ok("模块表按基址有序（二分查找的前提）",
           all(modules[i][0] < modules[i + 1][0] for i in range(len(modules) - 1)))
        base, _size, name = modules[0]
        ok("地址换算：基址落在自己模块的 +0x0",
           crash_dump._where(modules, base) == f"{name}+0x0",
           crash_dump._where(modules, base))
        ok("地址换算：0 直接给 0x0（不误判）",
           crash_dump._where(modules, 0) == "0x0")
        ok("异常码翻成人话：访问违例",
           "访问违例" in crash_dump._explain(0xC0000005))
        ok("异常码翻成人话：用户回调异常",
           "用户回调" in crash_dump._explain(0xC000041D))
        ok("栈扫描空指针不炸（返回列表即可）",
           isinstance(crash_dump._stack_frames(modules, 0), list))

    # ---------------- 6. 接线（静态契约）----------------
    app_src = (root / "desktop/app.py").read_text(encoding="utf-8")
    ok("GUI 入口在 QApplication 之后立刻取证",
       "_install_crash_forensics(app)" in app_src
       and app_src.index("_install_crash_forensics(app)")
       < app_src.index("kill_children_on_exit"))
    ok("顺序：faulthandler 先装、原生过滤器后装（否则丢 Python 栈）",
       app_src.index("install_crash_log(log_dir)")
       < app_src.index("install_crash_dump(log_dir)"))
    picker_src = (root / "desktop/components/imposition/picker.py").read_text(
        encoding="utf-8")
    ok("选图弹窗：记住「开过弹窗」与「开过系统选图框」",
       "拼版选图弹窗显示" in picker_src and "打开系统选图对话框" in picker_src)
    view_src = (root / "desktop/components/imposition/view.py").read_text(
        encoding="utf-8")
    ok("拼版切页留痕", "拼版切页" in view_src)
    page_src = (root / "desktop/pages/taskdetail/page.py").read_text(
        encoding="utf-8")
    ok("切步骤留痕", "切步骤" in page_src)

    # ---------------- 7. 卡顿看门狗（2026-11-21「拼版卡死」）----------------
    # 闪退有 faulthandler，**卡死没有**：进程活着、一个字都不写，用户只能强杀。
    # 这里真把主线程按 0.7s 不动（阈值 150ms），看门狗必须写下卡顿行 + 线程栈 +
    # 恢复行——这三样就是下次现场的全部依据。
    import time as _time

    # 第 4 节起为了跑子进程已经 uninstall 过（流关了，log() 会静默丢弃）
    os.environ[_ENV] = str(log_file)
    crash_log.install(work)

    dog = crash_log.StallWatchdog(threshold_ms=150, poll_ms=40).start()
    try:
        _time.sleep(0.7)      # 主线程真卡住（sleep 放 GIL，看门狗跑得动）
        dog.beat()            # 恢复心跳
        _time.sleep(0.25)     # 留一拍让看门狗写下"恢复"
    finally:
        dog.stop()
    body = _read(log_file)
    ok("卡顿看门狗：主线程卡住时写下 [stall] 卡顿行",
       "[stall] 主线程卡顿" in body)
    # 只从卡顿那行往后找栈：前面几节写过别的多行日志，别串味
    stall_text = body[body.index("[stall] 主线程卡顿"):] \
        if "[stall] 主线程卡顿" in body else ""
    ok("卡顿看门狗：栈里有主线程调用点（本用例文件）",
       "--- 主线程 ---" in stall_text and "crash_forensics" in stall_text)
    ok("卡顿看门狗：恢复后记下这次卡了多久",
       "[stall] 主线程恢复" in stall_text)

    # 有心跳时必须**不报**（用户翻页/滚动动辄几百毫秒，不该刷日志）
    before = _read(log_file).count("[stall]")
    dog2 = crash_log.StallWatchdog(threshold_ms=300, poll_ms=40).start()
    try:
        for _ in range(12):   # 0.6s 内一直打心跳
            _time.sleep(0.05)
            dog2.beat()
        _time.sleep(0.1)
    finally:
        dog2.stop()
    ok("卡顿看门狗：心跳正常时不写 [stall]（不误报）",
       _read(log_file).count("[stall]") == before)

    dog3 = crash_log.install_stall_watchdog(threshold_ms=150, poll_ms=40)
    try:
        ok("卡顿看门狗：install_ 能取回同一个实例（幂等）",
           dog3 is crash_log.stall_watchdog())
    finally:
        dog3.stop()
    ok("接线：GUI 入口装看门狗，心跳挂在主线程 QTimer 上",
       "install_stall_watchdog()" in app_src
       and "heartbeat.timeout.connect(dog.beat)" in app_src
       and "QTimer(app)" in app_src)

    os.environ.pop(_ENV, None)
