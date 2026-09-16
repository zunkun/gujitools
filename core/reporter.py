"""
File: core/reporter.py
功能模块（functions/）向宿主汇报的结构化事件通道。

**为什么需要这一层**

`functions/` 是 CLI 与 desktop 共用的核心层，但它同时要做两件事：
给人看的日志（「输入路径：…」「处理完成: x.jpg」）与给程序读的信号
（当前进度、每页检测框、图片尺寸）。历史上这两件事**都**走 `print()`，
于是 desktop 侧只能在 stdout 上跑正则去把信号捞回来：

    _PROGRESS_PAIR = re.compile(r"(?:进度|图片加载进度|写入进度)\\s*[:：]?\\s*(\\d+)\\s*/\\s*(\\d+)")

这种「文案即契约」的耦合有三个必然的坏结果：
1. 改一句中文提示就可能静默断掉 GUI 进度条 / 框入库，且没有任何测试会红；
2. 并发路径下 print 是**非原子**的（`\\r` 与 `\\n` 混用、线程池多线程同时写），
   正则偶尔会漏读一行，进度就少一格；
3. desktop 侧要复刻 `functions/` 的文案格式，两处必须同步维护。

**本模块的做法**

把「机器可读信号」从「人类文案」里剥离出来，走结构化回调：

    reporter.progress(done, total)          # 进度
    reporter.event("page_boxes", image=…, left=…, right=…)   # 结构化负载

`CoreReporter` 是**空实现**（Null Object）：不注入 reporter 时，所有方法都是
no-op，行为与「只 print 日志」完全一致 —— 因此 CLI 路径零改动、零风险。

各层的分工：
- `core/`：本模块（事件协议定义）。只依赖标准库，是依赖图上的叶子。
- `functions/`：在关键节点调用 `self.reporter.*`，**同时保留**人类可读的 print。
- `utils/pdf_utils.py`：同样接受可选 reporter（extract 的渲染在 utils 层）。
- `cli/`：不注入 → 空实现，输出与人读日志不变。
- `desktop/`：注入 `JsonLinesReporter`，把事件直接写成 JSON Lines。

⚠️ 渐进式迁移约定：本轮先把「有明确机器读者的信号」结构化（进度 / 检测框 /
图片尺寸），**人类日志仍走 print**，由 desktop 的 stdout 兜底层照收，
保证日志视图一行不少。后续可继续把高频日志也搬到 `reporter.log()`。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Protocol, runtime_checkable

# 已定义的事件名。写入 payload 的 "type" 字段之前请先在此登记，
# 免得两端各写各的字符串、拼错了也没人发现。
EVENT_PROGRESS = "progress"
EVENT_PAGE_BOXES = "page_boxes"
EVENT_PAGE_SIZE = "page_size"


@runtime_checkable
class Reporter(Protocol):
    """功能模块报告运行时信息的只读协议。

    只要求实现三个方法，因此任何对象（包括 `CoreReporter`、测试桩、
    desktop 的 JSON Lines 实现）都能直接充当 reporter，无需继承。
    """

    def progress(self, done: int, total: int) -> None:
        """报告已完成数量与总数。"""

    def event(self, name: str, **payload: Any) -> None:
        """报告一条具名结构化事件（name 取 EVENT_* 常量）。"""

    def log(self, message: str) -> None:
        """报告一条人类可读日志（可选实现，缺省等价于 print）。"""


class CoreReporter:
    """空实现（Null Object）：所有汇报都被吞掉。

    `functions/` 的默认 reporter 就是它 —— 不注入时功能模块的行为与
    「只有 print」的历史实现逐字节一致，CLI 因此完全不受影响。
    """

    __slots__ = ()

    def progress(self, done: int, total: int) -> None:  # noqa: D102 - 见协议
        pass

    def event(self, name: str, **payload: Any) -> None:  # noqa: D102 - 见协议
        pass

    def log(self, message: str) -> None:  # noqa: D102 - 见协议
        pass


class CallbackReporter:
    """把汇报转成回调的轻量适配器，便于测试与复用。

    参数 sink 收到 ``(name, payload_dict)``；``progress``/``log`` 也统一
    映射为同名事件，调用方不必实现三个方法。
    """

    __slots__ = ("_sink",)

    def __init__(self, sink: Callable[[str, Dict[str, Any]], None]):
        self._sink = sink

    def progress(self, done: int, total: int) -> None:
        self._sink(EVENT_PROGRESS, {"done": int(done), "total": int(total)})

    def event(self, name: str, **payload: Any) -> None:
        self._sink(name, payload)

    def log(self, message: str) -> None:
        self._sink("log", {"message": message})


# 全进程共用的空实现单例：默认参数直接引它，避免到处 CoreReporter()。
NULL_REPORTER = CoreReporter()


def normalize_reporter(reporter: Optional[Reporter]) -> Reporter:
    """None 一律视作 NULL_REPORTER，省掉调用点的判空。"""
    return reporter if reporter is not None else NULL_REPORTER


__all__ = [
    "EVENT_PAGE_BOXES",
    "EVENT_PAGE_SIZE",
    "EVENT_PROGRESS",
    "CallbackReporter",
    "CoreReporter",
    "NULL_REPORTER",
    "Reporter",
    "normalize_reporter",
]
