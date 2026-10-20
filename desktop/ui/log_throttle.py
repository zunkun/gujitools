# -*- coding: utf-8 -*-
"""日志合并器：把高频日志攒成**低频的一次 append**。

## 为什么需要它

执行阶段（detect/extract 逐页打印）会把几百上千行日志送到 ``log_view``。
每来一行就 ``append`` 一次 = 一次 QTextDocument 布局 + 一次
``LogPanel._refresh_bar``，而这些行往往在**同一轮事件循环**里到达 —— 主线程
就在这两件事上被拖住，界面看着就是"卡"（用户报的「检测文本框执行过程中页面
卡顿」）。

把 N 行合并成**一次** ``append("\\n".join(lines))`` 后，这 N 行只付一次文档
布局与一次状态条刷新；行数越多收益越大。

## 与进度合并的关系

⚠️ **不复用** ``runner._progress_ui_timer``：进度合并与日志合并是两条独立的
节流线，语义不同（进度要的是"最新值"，日志要的是"每一行都不丢"）。两条各
管各的，互不干扰。

## 契约

``target`` 只需满足"有 ``append(str)``"这一条 —— 本类**不认识** ``LogPanel``，
也不 import 任何页面层对象（守住 ``desktop/ui`` 的底座定位）。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

#: 攒批窗口：这么久没有新日志就冲刷一批。
DEFAULT_INTERVAL_MS = 200
#: 待写行数达到这个上限就**立刻**冲刷（防止刷屏日志把内存堆起来）。
DEFAULT_MAX_PENDING = 500


class LogCoalescer(QObject):
    """把高频日志攒成低频的一次 append。

    用法::

        logs = LogCoalescer(self.log_view)
        logs.append(line)       # 攒批（高频路径）
        logs.append_now(line)   # 先冲刷已有再立刻写（阶段起止那几行）
        logs.flush()            # 收尾强制落笔

    ⚠️ ``flush()`` 必须**收尾时调**（阶段结束 / 页面关闭）：攒批窗口里可能还压
    着最后几行，不冲刷就会"日志少了一截"。
    """

    def __init__(
        self,
        target,
        interval_ms: int = DEFAULT_INTERVAL_MS,
        max_pending: int = DEFAULT_MAX_PENDING,
        parent: QObject | None = None,
    ) -> None:
        """绑定一个"有 ``append(str)``"的目标控件（通常是 ``QTextEdit``）。"""
        super().__init__(parent)
        self._target = target
        self._interval_ms = interval_ms
        self._max_pending = max_pending
        self._pending: list[str] = []
        #: 单发定时器：``append`` 时若没在计时就起一次；到期冲刷。
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)

    # ------------------------------------------------------------------ 写入
    def append(self, line: str) -> None:
        """攒批一行（高频路径：以攒批窗口为粒度落笔）。"""
        if line == "":
            return
        self._pending.append(line)
        if len(self._pending) >= self._max_pending:
            self.flush()
            return
        if not self._timer.isActive():
            self._timer.start(self._interval_ms)

    def append_now(self, line: str) -> None:
        """立刻写一行：先把压着的攒批冲刷掉，再写这一行。

        用于"用户此刻最想立刻看到"的几行（阶段起止、"=== 开始执行 … ==="）。
        ⚠️ 冲刷与这一行**分两次 append**：``append_now`` 的语义就是"这一行不许
        等窗口"，与攒批行挤在一起反而会让它跟着一起等。
        """
        self.flush()
        if line != "":
            self._target.append(line)

    def flush(self) -> None:
        """把压着的行**一次**写完（幂等：没有待写行就什么也不做）。"""
        if self._timer.isActive():
            self._timer.stop()
        if not self._pending:
            return
        lines = self._pending
        self._pending = []
        self._target.append("\n".join(lines))

    def pending(self) -> int:
        """待写行数（自测用）。"""
        return len(self._pending)
