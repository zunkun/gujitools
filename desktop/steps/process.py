# -*- coding: utf-8 -*-
"""子进程传输层：把 worker 子进程的启动、看门狗与收尾收成一个可复用零件。

**为什么在"共用步骤组件层"里**：任务详情页原先自己攥着这坨代码
（``StageRunnerMixin`` 里一百多行 QProcess/看门狗/兜底收尾），它和页面耦合在
一起，谁都复用不了。抽到本模块后，它只依赖 Qt，不知道"第几步""任务是什么"，
于是和 :mod:`desktop.steps.kernel`（进程内执行内核）并列成为这一层的两种
"把一步跑起来"的方式：

- :class:`~desktop.steps.kernel.StepKernel`：**进程内**线程，轻，模块页用；
- :class:`StageProcess`：**子进程**隔离，重，任务管理用（torch 崩溃不带走
  GUI、能真正 kill 掉）。

职责边界（有意划在这里）：

- 本类**只做传输**：起进程、把管道里的**原始字节**转出来、Windows 偶发丢
  ``finished`` 时用看门狗兜底、保证"完成"只报一次；
- **不解析** stdout 的 JSON Lines、不认 stderr 里哪行像错误、不碰 runs.json
  ——那些是宿主的业务（写运行记录、刷进度条、落 boxes.json），放这里会让
  本类重新长出"任务流程"的触手，也就失去了复用价值。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal


def worker_arguments(config_path: Path) -> list[str]:
    """按运行环境给出启动 worker 子进程的参数表。

    - 打包（``sys.frozen``）：主程序即入口，``--worker --config`` 路由到子任务执行；
    - 源码：按模块启动（``-m desktop.worker``），不依赖入口文件名（``desktop.py``
      改名无影响），工作目录必须是项目根（能解析出 ``desktop`` 包的那一级）。
    """
    if getattr(sys, "frozen", False):
        return ["--worker", "--config", str(config_path)]
    return ["-m", "desktop.worker", "--config", str(config_path)]


def worker_env() -> QProcessEnvironment:
    """子进程强制 UTF-8：GUI 按 UTF-8 解析 JSON Lines，CLI 输出含 emoji。"""
    env = QProcessEnvironment.systemEnvironment()
    env.insert("PYTHONIOENCODING", "utf-8")
    env.insert("PYTHONUTF8", "1")
    return env


def _process_alive(pid: int) -> bool:
    """用 Win32 API 探测进程是否还活着（非 Windows 一律当"活着"）。

    ⚠️ 只在**看门狗**里用：Windows 偶发丢失 ``finished`` 信号，Qt 状态滞留
    Running 而 OS 进程其实已退出——这时必须能自己看出来。
    """
    if pid <= 0 or sys.platform != "win32":
        return True
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False  # 无法打开 = 已退出
    try:
        code = ctypes.c_ulong()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return code.value == STILL_ACTIVE
        return True
    finally:
        kernel32.CloseHandle(handle)


class StageProcess(QObject):
    """一个阶段子进程：起进程、转字节流、兜底收尾。

    信号（全部在**主线程**发出）：

    - ``stdout(bytes)``：标准输出的**原始字节**（宿主自己做半行重组与 JSON 解析）；
    - ``stderr(bytes)``：标准错误的原始字节（宿主决定哪行算错误）；
    - ``started()``：进程真的起来了；
    - ``finished(int, object)``：``(退出码, exit_status)``，**保证只发一次**；
    - ``process_error(object)``：QProcess 报的错（含启动失败）；
    - ``stalled(float)``：已 N 分钟没有任何输出（只提醒，不自动杀）；
    - ``unclean_exit()``：OS 进程已退出、Qt 却没能正常收尾（看门狗兜底）；
      宿主据此把"未正常收尾"记成失败原因——本类只报"发生了"，不管怎么记。
    """

    stdout = Signal(bytes)
    stderr = Signal(bytes)
    started = Signal()
    finished = Signal(int, object)
    process_error = Signal(object)
    stalled = Signal(float)
    unclean_exit = Signal()

    #: 「多少秒没有任何输出」就提醒用户可能卡住（只提醒，不自动杀）。
    #: 合法的慢阶段里 worker 一直在发 progress/log，所以静默 = 可疑；
    #: 但阈值给得宽松（3 分钟），宁可晚提醒也不误报。
    STALL_WARN_S = 180
    #: 看门狗轮询间隔（ms）
    WATCHDOG_MS = 300

    def __init__(self, parent=None, stall_warn_s: float | None = None):
        super().__init__(parent)
        self._process: QProcess | None = None
        self._watchdog: QTimer | None = None
        self._finish_delivered = False
        self._proc_started = False
        self._last_event_at = 0.0
        self._stall_warned = False
        self._stall_warn_s = (
            self.STALL_WARN_S if stall_warn_s is None else float(stall_warn_s)
        )

    # ------------------------------------------------------------------ 属性
    @property
    def process(self) -> QProcess | None:
        """底层 ``QProcess``（宿主用它查状态/杀进程；测试也按它等待）。"""
        return self._process

    def running(self) -> bool:
        """进程是否还在跑。"""
        return (
            self._process is not None
            and self._process.state() != QProcess.NotRunning
        )

    # ------------------------------------------------------------------ 启动
    def start(
        self,
        program: str,
        arguments: list[str],
        workdir: Path | str | None = None,
        env: QProcessEnvironment | None = None,
    ) -> QProcess:
        """起子进程并接好输出/看门狗；返回底层 ``QProcess``。

        调用方通常紧接着把返回值存到自己的属性上（既有测试按
        ``page.process`` 取进程）。
        """
        process = QProcess(self)
        process.setProgram(program)
        process.setProcessEnvironment(env if env is not None else worker_env())
        if workdir is not None:
            process.setWorkingDirectory(str(workdir))
        process.setArguments(arguments)
        process.readyReadStandardOutput.connect(self._on_stdout)
        process.readyReadStandardError.connect(self._on_stderr)
        process.errorOccurred.connect(self.process_error.emit)
        self._process = process
        self._finish_delivered = False
        self._proc_started = False
        self._last_event_at = time.time()
        self._stall_warned = False

        # Windows 偶发丢失 finished 信号（尤其从 worker 回调链启动时）：
        # 看门狗轮询兜底——Qt 状态滞留 Running 但 OS 进程已退出时，
        # 直接用 Win32 探测并手动驱动完成流程。
        watchdog = QTimer(self)
        watchdog.timeout.connect(self._tick)
        watchdog.start(self.WATCHDOG_MS)
        self._watchdog = watchdog

        process.started.connect(self._on_started)
        process.finished.connect(self._on_finished)
        process.start()
        return process

    def kill(self) -> None:
        """杀掉子进程（不等待；等待由宿主决定）。"""
        if self.running():
            self._process.kill()

    # ------------------------------------------------------------------ 读取
    def _on_stdout(self) -> None:
        """stdout 有数据到达：算"有进展"，原始字节转给宿主。"""
        if self._process is None:
            return
        self._last_event_at = time.time()
        self._stall_warned = False
        try:
            self.stdout.emit(bytes(self._process.readAllStandardOutput()))
        except RuntimeError:
            pass  # 底层对象已析构

    def _on_stderr(self) -> None:
        """stderr 有数据到达：原始字节转给宿主。"""
        if self._process is None:
            return
        try:
            self.stderr.emit(bytes(self._process.readAllStandardError()))
        except RuntimeError:
            pass

    # ------------------------------------------------------------------ 收尾
    def _on_started(self) -> None:
        self._proc_started = True
        self.started.emit()

    def _on_finished(self, code: int, status) -> None:
        self._deliver(code, status)

    def _tick(self) -> None:
        """看门狗：进程没了就补一次收尾；还活着但很久没输出就提醒。"""
        process = self._process
        if process is None:
            self._stop_watchdog()
            return
        if process.state() == QProcess.NotRunning:
            code = process.exitCode()
            # 从未成功启动时 exitCode() 仍是 0，直接当成功会误报"执行成功"
            if not self._proc_started and code == 0:
                code = 1
            self._deliver(code, process.exitStatus())
        elif not _process_alive(process.processId()):
            # OS 进程已退出，Qt 却没报 finished（Windows 偶发）。
            # ⚠️ 这里**不能**直接按成功收尾：
            # ① 硬编码 0 会把崩溃/失败（退出码非 0）报成"执行成功"；
            # ② 立刻收尾会丢掉管道里还没读的 progress/log 事件。
            # 所以先让 Qt 收尾——它会排空管道并把**真实退出码**带回来；
            # 实在收不了尾才按失败兜底（宁可误报失败，不可误报成功）。
            if process.waitForFinished(1500):
                code = process.exitCode()
                if not self._proc_started and code == 0:
                    code = 1
                self._deliver(code, process.exitStatus())
            else:
                # 宿主据此把"未正常收尾"记成失败原因（本类不碰它的状态）
                self.unclean_exit.emit()
                self._deliver(1, QProcess.CrashExit)
        else:
            self._warn_if_stalled()

    def _warn_if_stalled(self) -> None:
        """进程还活着、但很久没有任何事件 → 提醒用户可中断。

        ⚠️ 为什么只提醒不自动杀：worker 卡死（死锁、等常驻 YOLO 服务、torch
        卡住、管道反压）与**合法的慢阶段**（2400 页的去底色/生成 PDF）在外部看
        是一样的——都只是"没输出"。自动杀掉会把用户跑了几分钟的正常任务误杀，
        代价远大于收益。所以只把"已经 N 分钟没有任何进展"摆到用户面前，让**他**
        决定要不要点中断。
        """
        last = self._last_event_at
        if not last:
            return
        idle = time.time() - last
        if idle < self._stall_warn_s or self._stall_warned:
            return
        self._stall_warned = True
        self.stalled.emit(idle / 60)

    def _deliver(self, code: int, status) -> None:
        """把完成事件交给宿主（**只发一次**）。"""
        if self._finish_delivered:
            return
        self._finish_delivered = True
        self._stop_watchdog()
        self.finished.emit(code, status)

    def _stop_watchdog(self) -> None:
        if self._watchdog is not None:
            self._watchdog.stop()
            self._watchdog = None


__all__ = ["StageProcess", "worker_arguments", "worker_env"]
