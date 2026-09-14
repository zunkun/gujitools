# -*- coding: utf-8 -*-
"""文件指纹（SHA-256）后台计算。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from ..utils.files import file_hash


class HashWorker(QObject):
    finished = Signal(str, str)
    failed = Signal(str)

    def __init__(self, path: Path):
        super().__init__()
        self.path = path

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(str(self.path), file_hash(self.path))
        except Exception as exc:
            self.failed.emit(str(exc))
