# -*- coding: utf-8 -*-
"""worker 子进程的事件输出层。

- emit：向 GUI 输出一条 JSON Lines 事件；
- ProgressStream：拦截功能模块的 print 输出，解析进度并转发日志。

The worker emits JSON Lines on stdout so the GUI remains independent from heavy
libraries. While the stage function runs, sys.stdout is intercepted so that:
- progress messages produced by functions/* (处理完成 / 进度: d/t / 写入进度 等)
  are converted into {"type": "progress"} events;
- every other text line is forwarded as {"type": "log"} events for the GUI log view.
"""

from __future__ import annotations

import io
import json
import re
import sys

# 各功能模块的进度输出模式 → (done, total)
_PROGRESS_PAIR = re.compile(r"(?:进度|图片加载进度|写入进度)\s*[:：]?\s*(\d+)\s*/\s*(\d+)")
# base.py 引擎：先输出总数，再逐文件输出 完成/失败
_TOTAL_ONLY = re.compile(r"图片总数\s*[:：]\s*(\d+)")
_DONE_ONE = re.compile(r"处理(?:完成|失败)\s*[:：]")
# text_region 检测到的文本框坐标行：[boxes] 0001 left=10,20,300,400 right=none
_BOXES_LINE = re.compile(r"^\[boxes\]\s+(\S+)\s+left=(\S+)\s+right=(\S+)\s*$")
# extract 渲染的页面图片尺寸行：[imgsize] 1 2481,3508
_IMG_SIZE_LINE = re.compile(r"^\[imgsize\]\s+(\S+)\s+(\d+),(\d+)\s*$")


def _parse_box(text: str):
    if text == "none":
        return None
    try:
        return [int(v) for v in text.split(",")]
    except ValueError:
        return None


def _real_stdout():
    """窗口化打包运行时 sys.stdout 可能为 None，尝试 fd 1 兜底。"""
    for candidate in (sys.__stdout__, sys.stdout):
        if candidate is not None:
            return candidate
    import os

    return os.fdopen(1, "w", encoding="utf-8", closefd=False)


def emit(payload: dict, stream=None) -> None:
    """
    向 GUI 输出一条 JSON Lines 事件。

    stream 缺省写真实 stdout；窗口化打包运行时 sys.stdout 可能为 None，
    此时由 _real_stdout() 兜底到文件描述符 1。
    """
    target = stream if stream is not None else _real_stdout()
    target.write(json.dumps(payload, ensure_ascii=False) + "\n")
    target.flush()


class ProgressStream(io.TextIOBase):
    """拦截功能模块的 print 输出，解析进度并转发日志。"""

    def __init__(self, real_stdout, context: dict):
        """
        real_stdout 为真实输出流；context 提供 task_id/stage/run_id，会附加到
        本流发出的每条事件上，供 GUI 归位到具体任务与阶段。
        """
        self.real = real_stdout
        self.context = context  # {"task_id", "stage", "run_id"}
        self.buffer = ""
        self.done = 0
        self.total = 0

    def writable(self) -> bool:
        """恒为 True：本流始终接受写入。"""
        return True

    def write(self, text: str) -> int:
        """按换行或回车切分输出边界，逐行解析成事件；返回本次写入的字符数（满足 io.TextIOBase 约定）。"""
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
        match = _BOXES_LINE.match(line)
        if match:
            # 框坐标是结构化数据，转发为独立事件，不进日志视图
            emit(
                {
                    "type": "page_boxes",
                    **self.context,
                    "image": match.group(1),
                    "left": _parse_box(match.group(2)),
                    "right": _parse_box(match.group(3)),
                },
                stream=self.real,
            )
            return
        match = _IMG_SIZE_LINE.match(line)
        if match:
            emit(
                {
                    "type": "page_size",
                    **self.context,
                    "image": match.group(1),
                    "width": int(match.group(2)),
                    "height": int(match.group(3)),
                },
                stream=self.real,
            )
            return
        emit(
            {"type": "log", **self.context, "message": line},
            stream=self.real,
        )
        changed = False
        match = _PROGRESS_PAIR.search(line)
        if match:
            self.done, self.total = int(match.group(1)), int(match.group(2))
            changed = True
        else:
            match = _TOTAL_ONLY.search(line)
            if match and not self.total:
                self.total = int(match.group(1))
                changed = True
            elif _DONE_ONE.search(line):
                self.done += 1
                changed = True
        if changed:
            emit(
                {
                    "type": "progress",
                    **self.context,
                    "done": self.done,
                    "total": self.total,
                },
                stream=self.real,
            )
