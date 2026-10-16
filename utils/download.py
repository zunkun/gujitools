# -*- coding: utf-8 -*-
"""流式下载：把 URL 内容写到文件，边下边回报进度、可取消（**纯规则**，无 Qt）。

被两处共用——「去底色数据包」（``desktop/workers/data_package_worker.py``）与
「程序更新」（``desktop/workers/update_worker.py``）——所以收在一处，别各写一份。

两条硬约定：

1. **先写 ``*.part``、成功才改名**：下载途中的半截文件绝不能以最终名出现，否则
   读者（YOLO 服务、检测进程、安装器）可能读到不完整的内容；
2. **进度与取消都由调用方给**（``on_progress`` / ``is_cancelled``），这里不碰
   Qt 信号，保持纯函数、好测。

⚠️ ``urllib`` 的 ``timeout`` 是**每次 socket 操作**的超时，不是"整包总时长"：
大安装包不会被某个总时限掐死，只有单次读写卡住过久才会抛。
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

#: 读块大小（字节）。约 96 次回调下完 6MB 权重，够顺滑也不刷屏。
CHUNK = 64 * 1024


class DownloadCancelled(Exception):
    """下载被调用方取消（``is_cancelled`` 返回真时抛出）。"""


def stream_to_file(url, target, *, on_progress=None, is_cancelled=None,
                   timeout: float = 120.0, chunk: int = CHUNK,
                   headers: dict | None = None) -> tuple[str, int]:
    """流式下载 ``url`` 到 ``target``，返回 ``(sha256 十六进制, 字节数)``。

    :param on_progress: ``fn(written, total)``；``total`` 为 0 表示总量未知。
    :param is_cancelled: 无参谓词，返回真即抛 :class:`DownloadCancelled`。
    :param headers: 额外请求头（GitHub 要求 ``User-Agent``）。

    ⚠️ 失败/取消**一定删掉 ``target``**（半截文件绝不能留下）。

    异常：:class:`DownloadCancelled`、``urllib`` 的错误、``OSError``。
    """
    digest = hashlib.sha256()
    written = 0
    target = Path(target)
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            try:
                total = int(resp.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                total = 0
            with open(target, "wb") as handle:
                while True:
                    if is_cancelled is not None and is_cancelled():
                        raise DownloadCancelled()
                    block = resp.read(chunk)
                    if not block:
                        break
                    handle.write(block)
                    digest.update(block)
                    written += len(block)
                    if on_progress is not None:
                        on_progress(written, total)
    except BaseException:
        _unlink_quiet(target)
        raise
    return digest.hexdigest(), written


def _unlink_quiet(path: Path) -> None:
    """删文件、没删掉也不抛（清理尽力而为）。"""
    try:
        Path(path).unlink()
    except OSError:
        pass


__all__ = ["CHUNK", "DownloadCancelled", "stream_to_file"]
