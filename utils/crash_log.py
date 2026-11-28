# -*- coding: utf-8 -*-
"""崩溃取证：把「最后一刻」留在磁盘上。

为什么需要它（2026-11-21）：生产版偶发 ``Qt6Gui.dll`` 访问违例（异常码
``0xc0000005`` 紧接着 ``0xc000041d``）直接闪退，而 GUI 是 windowed 程序、
没有控制台，stderr 全丢；Windows 的 WER ``LocalDumps`` 在这台机器上实测
**根本不落盘**（配了 DumpFolder/DumpType=2，崩溃后目录一直是空的，用探针
程序验过），所以拿不到任何现场。这里自备三条证据链：

1. ``faulthandler`` —— 原生崩溃（访问违例/段错误）时把**所有 Python 线程**
   的栈写进日志。标准库实现，进 GUI 主进程不引入任何依赖。
2. ``sys.excepthook`` / ``threading.excepthook`` —— Python 层漏出来的异常
   也进同一份日志（崩溃之前常有被吞掉的异常，这条经常是破案关键）。
3. :func:`breadcrumb` —— 关键动作留痕（切步骤、切页、开弹窗、合成/缩略图
   批次…）。崩溃时日志末尾那几行就等于「最后做了什么」，比栈还好用。

本模块**不许 import Qt**（住在 ``utils`` 层，GUI 与 CLI 都能用）；Windows 专属
的 minidump 在 :mod:`utils.crash_dump` 里。

⚠️ 日志只记**动作与位置**，不记用户内容（页号、数量、文件名按需截断）。整份
日志超过 ``MAX_BYTES`` 时按时间戳归档旧日志，不覆盖、不删除。
程序重启追加到 ``crash.log``，不会清掉上一份现场。
"""

from __future__ import annotations

import faulthandler
import os
import signal
import sys
import threading
import time
import traceback
from pathlib import Path

#: 单份日志上限（超过就按时间戳归档，保留所有归档）
MAX_BYTES = 2 * 1024 * 1024

#: 想改落点（排障/自测）时设它：``GUJI_CRASH_LOG=<文件路径>``
LOG_ENV = "GUJI_CRASH_LOG"

_lock = threading.RLock()
_log_path: Path | None = None
_stream = None  # 打开的文件对象，faulthandler 与 log() 共用
_prev_excepthook = None
_prev_thread_hook = None


def _stamp() -> str:
    """``HH:MM:SS.mmm``：日志按「同一天」看就够了，不加日期省宽度。"""
    now = time.time()
    return time.strftime("%H:%M:%S", time.localtime(now)) + \
        f".{int(now * 1000) % 1000:03d}"


def _rotate(path: Path) -> None:
    """超过上限就归档旧日志，绝不覆盖或删除历史日志。"""
    try:
        if path.is_file() and path.stat().st_size > MAX_BYTES:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            millis = f"{int(time.time() * 1000) % 1000:03d}"
            stem = f"crash_log_{stamp}_{millis}_pid{os.getpid()}.log"
            backup = path.with_name(stem)
            number = 2
            while backup.exists():
                stem = f"crash_log_{stamp}_{millis}_pid{os.getpid()}_{number}.log"
                backup = path.with_name(stem)
                number += 1
            os.replace(path, backup)
    except OSError:
        pass  # 滚动失败不影响继续写


def install(directory: str | Path | None = None, name: str = "crash.log") -> Path | None:
    """装好三条证据链，返回日志路径（装不上返回 ``None``，**绝不抛**）。

    ``directory=None`` 时看环境变量 :data:`LOG_ENV`，再退到 ``%TEMP%``。
    ⚠️ 绝不能因为取证装不上而拦住启动——它是排障设施，不是功能。
    """
    global _log_path, _stream, _prev_excepthook, _prev_thread_hook

    with _lock:
        if _stream is not None and _log_path is not None:
            return _log_path  # 幂等：重复调用不算错

        target: Path | None
        override = (os.environ.get(LOG_ENV) or "").strip()
        if override:
            target = Path(override).expanduser()
        elif directory is not None:
            target = Path(directory).expanduser() / name
        else:
            target = Path(os.environ.get("TEMP") or ".") / name

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            _rotate(target)
            stream = open(target, "a", encoding="utf-8", errors="replace",
                          buffering=1)
        except OSError as exc:
            print(f"[guji] 崩溃日志装不上（{target}）：{exc}")
            return None

        _log_path = target
        _stream = stream

        # 1) 原生崩溃 → 所有线程的 Python 栈
        try:
            faulthandler.enable(stream, all_threads=True)
        except (OSError, ValueError, RuntimeError) as exc:
            stream.write(f"{_stamp()} [warn] faulthandler 启用失败：{exc}\n")

        # 1b) 手动抓栈：``kill -USR1 <pid>`` 立刻把所有线程的 Python 栈写进日志。
        #     为什么需要（2026-11-28 用户报"点一下突然卡住、窗口消失"）：
        #     排查时进程还活着、事件循环也还能应答 socket（10ms 内），但界面
        #     不动、图案不再重绘——**主线程并不忙**，看门狗自然一条 ``[stall]``
        #     都不会打。这种"界面死、进程活"只能当场抓栈才分得清是渲染线程、
        #     合成器还是某个嵌套事件循环在等；事后翻日志永远是零线索。
        #     faulthandler 的信号栈是**信号安全**的：主线程真卡在 C 里也能抓。
        if hasattr(signal, "SIGUSR1"):
            try:
                faulthandler.register(signal.SIGUSR1, file=stream,
                                      all_threads=True, chain=False)
            except (OSError, ValueError, RuntimeError) as exc:
                stream.write(f"{_stamp()} [warn] SIGUSR1 抓栈注册失败：{exc}\n")

        # 2) Python 异常（主线程 + 子线程）
        _prev_excepthook = sys.excepthook
        _prev_thread_hook = getattr(threading, "excepthook", None)

        def _hook(exc_type, exc, tb):  # noqa: ANN001 - 与标准库签名一致
            try:
                text = "".join(traceback.format_exception(exc_type, exc, tb))
                log("未捕获异常：\n" + text.rstrip())
            except Exception:  # noqa: BLE001 - 兜底钩子里不能再炸
                pass
            if _prev_excepthook is not None:
                _prev_excepthook(exc_type, exc, tb)

        def _thread_hook(args):  # noqa: ANN001
            try:
                text = "".join(traceback.format_exception(
                    args.exc_type, args.exc_value, args.exc_traceback))
                log(f"子线程未捕获异常（{getattr(args.thread, 'name', '?')}）：\n"
                    + text.rstrip())
            except Exception:  # noqa: BLE001
                pass
            if _prev_thread_hook is not None:
                _prev_thread_hook(args)

        sys.excepthook = _hook
        if _prev_thread_hook is not None:
            threading.excepthook = _thread_hook

        log(f"==== 崩溃日志开始（pid={os.getpid()}，py={sys.version.split()[0]}）")
        return target


def log(text: str) -> None:
    """写一行带时间戳与线程名的日志（没装就静默丢弃，绝不抛）。"""
    with _lock:
        stream = _stream
        if stream is None:
            return
        try:
            tid = threading.get_ident()
            name = threading.current_thread().name
            stream.write(f"{_stamp()} [{name}:{tid:x}] {text}\n")
            stream.flush()
        except (OSError, ValueError):
            pass


def breadcrumb(text: str) -> None:
    """记一条「做了什么」。保持短、可 grep：统一前缀 ``[crumb]``。"""
    log(f"[crumb] {text}")


# ------------------------------------------------------- 主线程卡顿看门狗 ----
# 为什么需要它（2026-11-21）：用户报「拼版卡死」——界面完全无响应、只能强杀，
# 而强杀既不留 Python 栈也不留转储，等于没有现场（崩溃日志末尾只有最后一条
# 面包屑）。闪退有 faulthandler 兜着，**卡死没有**：进程活着、什么也不写。
#
# 做法：主线程用 QTimer 定期 :meth:`StallWatchdog.beat`，另一个 Python 线程
# 盯着"心跳多久没更新"。超时就把**所有线程的栈**钉进日志——卡在哪一行、
# 谁在持锁、后台 worker 是不是僵在等主线程，一眼可见。
#
# ⚠️ 看门狗线程拿不到 GIL 时（主线程卡在不放 GIL 的 C 扩展里：PIL 编码、
#    cv2、Qt 的部分 C++ 调用）它会被饿死，等主线程放 GIL 才醒——那时栈已经
#    恢复。所以日志会同时记"这次饿死了多久"，用来区分这两种卡法。
# ⚠️ 心跳间隔必须 **小于** 阈值：主线程正常空转时 QTimer 照常触发，所以
#    "没有心跳"只可能是主线程真被占住了，不会因为用户没操作而误报。

#: 超过这么久没心跳就判「卡死」（毫秒）。``GUJI_STALL_THRESHOLD_MS`` 可覆盖。
STALL_THRESHOLD_MS = 3000

#: 看门狗自身的轮询间隔（毫秒）——同时也是 GUI 心跳的间隔。
STALL_POLL_MS = 500

#: 一个进程最多写几份卡顿栈（滚轮卡顿之类别把日志刷爆）。
STALL_MAX_REPORTS = 20

_watchdog: "StallWatchdog | None" = None


def _stall_threshold_ms() -> int:
    raw = (os.environ.get("GUJI_STALL_THRESHOLD_MS") or "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return STALL_THRESHOLD_MS


def dump_stacks(heading: str, limit: int = 30) -> None:
    """把**所有** Python 线程的栈写进日志（主线程排最前，看门狗自己截短）。

    纯 Python 实现（``sys._current_frames``），所以从别的线程也能读主线程栈；
    代价是需要 GIL——主线程不放 GIL 时调不到这里（见模块注释）。
    """
    main = threading.main_thread()
    names = {t.ident: t.name for t in threading.enumerate()}
    frames = sys._current_frames()
    me = threading.get_ident()
    order = sorted(frames, key=lambda tid: 0 if tid == main.ident else 1)
    parts = [heading]
    for tid in order:
        if tid == main.ident:
            label = "主线程"
        elif tid == me:
            label = "看门狗线程"
        else:
            label = names.get(tid, f"thread-{tid:x}")
        # 看门狗自己的栈只留几帧（它永远停在 _loop 里，写全了纯占地方）
        keep = 6 if tid == me else limit
        stack = "".join(traceback.format_stack(frames[tid], limit=keep)).rstrip()
        parts.append(f"--- {label} ---\n{stack}")
    log("\n".join(parts))


class StallWatchdog:
    """盯着主线程心跳：卡住就把线程栈钉进日志。

    用法（GUI 入口）::

        dog = install_stall_watchdog()        # 起监控线程
        timer = QTimer(app); timer.timeout.connect(dog.beat); timer.start(dog.poll_ms)

    ``beat()`` 可以被**任何**线程调（只更新时间戳），但语义是"主线程还活着"，
    所以只在主线程的事件循环里调。
    """

    def __init__(self, threshold_ms: int | None = None,
                 poll_ms: int = STALL_POLL_MS) -> None:
        self.threshold_ms = int(threshold_ms or _stall_threshold_ms())
        self.poll_ms = max(50, int(poll_ms))
        self._beat = time.monotonic()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        #: 这次卡顿的起点（monotonic）；None = 当前没卡
        self._since: float | None = None
        self._reports = 0

    # ------------------------------------------------------------------ 接口
    def beat(self) -> None:
        """主线程报一次活。"""
        with self._lock:
            self._beat = time.monotonic()

    def start(self) -> "StallWatchdog":
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop.clear()
        self.beat()
        self._thread = threading.Thread(
            target=self._loop, name="stall-watchdog", daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------ 内部
    def _loop(self) -> None:
        interval = self.poll_ms / 1000.0
        threshold = self.threshold_ms / 1000.0
        last_tick = time.monotonic()
        while not self._stop.wait(interval):
            now = time.monotonic()
            lag = now - last_tick - interval      # 自己被饿死了多久
            last_tick = now
            with self._lock:
                beat = self._beat
            idle = now - beat
            if idle >= threshold:
                if self._since is None:
                    self._since = beat
                    self._report(idle, lag, threshold)
                continue
            if self._since is not None:
                total = now - self._since
                self._since = None
                log(f"[stall] 主线程恢复：这次卡了 {total:.1f}s"
                    f"（判定阈值 {threshold:.1f}s）")

    def _report(self, idle: float, lag: float, threshold: float) -> None:
        if self._reports >= STALL_MAX_REPORTS:
            return
        self._reports += 1
        where = ""
        if lag > 1.0:
            # 看门狗自己都醒不过来 ⇒ 主线程攥着 GIL 不放（C 扩展里），
            # 下面这份栈多半是**恢复后**抓到的，只能当参考。
            where = (f"；看门狗自身也被饿死 {lag:.1f}s，栈可能已随主线程恢复而前移"
                     "（典型是不放 GIL 的 C 调用）")
        dump_stacks(
            f"[stall] 主线程卡顿：已 {idle:.1f}s 没有心跳"
            f"（阈值 {threshold:.1f}s，第 {self._reports} 次）{where}"
        )


def install_stall_watchdog(threshold_ms: int | None = None,
                           poll_ms: int = STALL_POLL_MS) -> StallWatchdog:
    """装好（或复用）卡顿看门狗并启动监控线程；心跳要调用方自己打。"""
    global _watchdog
    if _watchdog is None:
        _watchdog = StallWatchdog(threshold_ms, poll_ms)
    return _watchdog.start()


def stall_watchdog() -> "StallWatchdog | None":
    """当前进程的看门狗（没装为 ``None``）。"""
    return _watchdog


def tail(lines: int = 40) -> str:
    """取日志末尾若干行（崩溃转储里带上，省得回头再对时间）。"""
    path = _log_path
    if path is None:
        return ""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(raw.splitlines()[-max(1, lines):])


def path() -> Path | None:
    """当前日志文件（没装为 ``None``）。"""
    return _log_path


def installed() -> bool:
    return _stream is not None


def uninstall() -> None:
    """关掉取证（只有自测会用；正常进程跑到死为止）。"""
    global _stream, _log_path, _prev_excepthook, _prev_thread_hook

    # 看门狗先停：它还在跑的时候关流，_report 会往已关闭的文件写。
    if _watchdog is not None:
        try:
            _watchdog.stop()
        except Exception:  # noqa: BLE001
            pass

    with _lock:
        try:
            if hasattr(signal, "SIGUSR1"):
                faulthandler.unregister(signal.SIGUSR1)
        except (OSError, ValueError, RuntimeError):
            pass
        try:
            faulthandler.disable()
        except Exception:  # noqa: BLE001
            pass
        if _prev_excepthook is not None:
            sys.excepthook = _prev_excepthook
            _prev_excepthook = None
        if _prev_thread_hook is not None:
            threading.excepthook = _prev_thread_hook
            _prev_thread_hook = None
        if _stream is not None:
            try:
                _stream.close()
            except OSError:
                pass
        _stream = None
        _log_path = None
