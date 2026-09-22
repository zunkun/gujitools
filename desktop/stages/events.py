# -*- coding: utf-8 -*-
"""worker 子进程的事件输出层。

分两层职责，**顺序很重要**：

1. **结构化通道**（主）：`JsonLinesReporter` 实现 `core.reporter.Reporter` 协议，
   由阶段执行器注入给功能模块。进度、检测框、页尺寸等「给程序读的信号」直接
   以字典形式写成 JSON Lines，不经过任何字符串解析 —— 改文案不会再静默打断
   GUI 进度条。
2. **兜底通道**（辅）：`ProgressStream` 拦截功能模块（以及第三方库）的 print，
   把**人读日志**转发为 ``{"type": "log"}`` 事件。它不再做正则解析。

历史包袱说明：以前没有结构化通道，所有信号都靠 ProgressStream 跑正则从中文
提示里捞（`进度: d/t`、`图片总数: n`、`[boxes] …`、`[imgsize] …`）。那种
「文案即契约」的耦合已移除；`[boxes]`/`[imgsize]` 两行文本仍在 functions 侧
兼容保留一个版本，便于对照验证，但本文件不再解析它们。
"""

from __future__ import annotations

import io
import json
import sys
import threading
from typing import Any, Dict

from core.reporter import EVENT_PAGE_BOXES, EVENT_PAGE_SIZE, EVENT_PROGRESS

#: 保护"写一行 JSON 到 stdout"这个动作。
#: ⚠️ worker 里的功能模块是**线程池**并发跑的（crop/rembg/detect 都是），
#: 多线程同时 `write` + `flush` 会让两条事件的字节交错，GUI 那边 `json.loads`
#: 直接解析失败、整行被当成人读日志丢掉——表现为"进度/框偶尔丢一条"，
#: 极难复现。写一行是极短的操作，加锁的代价可以忽略。
_EMIT_LOCK = threading.Lock()


def _real_stdout():
    """窗口化打包运行时 sys.stdout 可能为 None，尝试 fd 1 兜底。"""
    for candidate in (sys.__stdout__, sys.stdout):
        if candidate is not None:
            return candidate
    import os

    return os.fdopen(1, "w", encoding="utf-8", closefd=False)


def emit(payload: dict, stream=None) -> None:
    """
    向 GUI 输出一条 JSON Lines 事件（线程安全）。

    stream 缺省写真实 stdout；窗口化打包运行时 sys.stdout 可能为 None，
    此时由 _real_stdout() 兜底到文件描述符 1。

    ⚠️ 序列化与写入必须在同一把锁里：先序列化再抢锁会让两个线程的
    payload 交替入队、输出的仍是交错行。
    """
    target = stream if stream is not None else _real_stdout()
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    with _EMIT_LOCK:
        target.write(line)
        target.flush()


class JsonLinesReporter:
    """把功能模块的结构化汇报写成 JSON Lines（worker → GUI 的正式协议）。

    context 提供 task_id/stage/run_id，附加到每条事件上供 GUI 归位到具体任务。
    """

    __slots__ = ("_context", "_stream")

    def __init__(self, context: dict, stream=None):
        self._context = dict(context)
        self._stream = stream

    def _send(self, payload: Dict[str, Any]) -> None:
        emit(payload, stream=self._stream)

    def progress(self, done: int, total: int) -> None:
        self._send(
            {
                "type": EVENT_PROGRESS,
                **self._context,
                "done": int(done),
                "total": int(total),
            }
        )

    def event(self, name: str, **payload: Any) -> None:
        """转发具名事件。

        `progress_total`（引擎先给出总数、尚无完成量）在协议上仍是一条
        progress 事件：GUI 只关心 total 用来设进度条 range，因此这里
        统一映射为 done=0 的 progress，避免新增一种 GUI 不认识的事件类型。
        """
        if name == "progress_total":
            self.progress(0, int(payload.get("total", 0)))
            return
        self._send({"type": name, **self._context, **payload})

    def log(self, message: str) -> None:
        self._send({"type": "log", **self._context, "message": message})


class ProgressStream(io.TextIOBase):
    """拦截功能模块的 print 输出，原样转发为人读日志事件。

    ⚠️ 这里**刻意不做任何解析**。以前它跑四条正则从中文提示里捞进度与结构化
    数据，属于「文案即契约」——改一句提示就静默断掉 GUI 进度条。现在信号走
    `JsonLinesReporter`，本类只负责让日志视图不漏行（含第三方库的 print）。
    """

    def __init__(self, real_stdout, context: dict):
        """
        real_stdout 为真实输出流；context 提供 task_id/stage/run_id，会附加到
        本流发出的每条事件上，供 GUI 归位到具体任务与阶段。
        """
        self.real = real_stdout
        self.context = context  # {"task_id", "stage", "run_id"}
        self.buffer = ""
        # 兼容旧调用方：阶段执行器以前从解析结果里取 done/total 组装 finished。
        # 现在由 JsonLinesReporter 负责进度，这里不再维护计数，恒为 0。
        self.done = 0
        self.total = 0

    def writable(self) -> bool:
        """恒为 True：本流始终接受写入。"""
        return True

    def write(self, text: str) -> int:
        """按换行或回车切分输出边界，逐行转发日志；返回写入字符数（满足 io.TextIOBase 约定）。"""
        if not isinstance(text, str):
            text = str(text)
        self.buffer += text
        # 以换行或回车作为一条输出边界（print.py 使用 end="" + \r 输出进度）
        while True:
            idx = min(
                (i for i in (self.buffer.find("\n"), self.buffer.find("\r")) if i >= 0),
                default=-1,
            )
            if idx < 0:
                break
            line = self.buffer[: idx + 1].strip()
            self.buffer = self.buffer[idx + 1 :]
            if line:
                self._consume(line)
        return len(text)

    def flush(self) -> None:
        """空实现（行缓冲已在 write 中处理，无需真正刷盘）。"""
        pass

    def _consume(self, line: str) -> None:
        """把一行人读输出转发为 log 事件。"""
        emit({"type": "log", **self.context, "message": line}, stream=self.real)


__all__ = [
    "EVENT_PAGE_BOXES",
    "EVENT_PAGE_SIZE",
    "EVENT_PROGRESS",
    "JsonLinesReporter",
    "ProgressStream",
    "emit",
]
