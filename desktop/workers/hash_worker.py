# -*- coding: utf-8 -*-
"""文件指纹（SHA-256）后台计算。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from desktop.utils.files import file_hash


class HashWorker(QObject):
    """后台计算单个文件 SHA-256 的 worker（QObject，运行于子线程）。

    完成时发 finished(path, hash)，异常发 failed(message)；用于导入时
    异步计算源文件指纹以做任务查重。
    """
    finished = Signal(str, str)
    failed = Signal(str)

    def __init__(self, path: Path):
        """待计算指纹的文件路径。"""
        super().__init__()
        self.path = path

    @Slot()
    def run(self) -> None:
        """执行哈希计算并通过 finished 信号回报结果（异常走 failed）。"""
        try:
            self.finished.emit(str(self.path), file_hash(self.path))
        except Exception as exc:
            self.failed.emit(str(exc))
