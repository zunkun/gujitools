# -*- coding: utf-8 -*-
"""后台把一批**白底图**转成透明底副本（singletask 缓存区，原图不动）。

给独立拼图页用：源清单来自带 ``singletask-rembg`` 标记的导出目录时，
拼版前先把这些白底图转成透明底副本（判据与编码见
``desktop.services.rembg_export``，复用 ``utils.transparent_png``）。
几百页的去底导出逐张解码+重编码在主线程做就是卡死，必须放线程。
"""

from __future__ import annotations

from pathlib import Path

# ⚠️ QImage 在 QtGui 不在 QtCore——放错的话模块一被 import 就 ImportError
#（与 imposition_worker 同一条护栏）。
from PySide6.QtCore import QObject, Signal, Slot


class RembgTransparentWorker(QObject):
    """逐张把白底图转成透明底副本；单张失败不拖垮整批。"""

    #: (done, total) —— 逐张进度
    progress = Signal(int, int)
    #: (映射 dict[源路径str, 副本路径str], 失败清单 list[str])
    #: ⚠️ 失败的图**不在映射里**，调用方按"没有副本"回落原图。
    finished = Signal(dict, list)
    failed = Signal(str)

    def __init__(self, sources: list[str]):
        """``sources``：需要转透明的源图路径（带标记目录里的那批）。"""
        super().__init__()
        self._sources = [str(p) for p in sources]

    @Slot()
    def run(self) -> None:
        from desktop.services.rembg_export import (
            make_transparent_copy, transparent_copy_path,
        )

        mapping: dict[str, str] = {}
        errors: list[str] = []
        total = len(self._sources)
        try:
            for index, text in enumerate(self._sources):
                source = Path(text)
                try:
                    target = transparent_copy_path(source)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    # 指纹路径天然幂等：同源同副本，命中即复用（零重编码）
                    if not target.is_file():
                        make_transparent_copy(source, target)
                    mapping[text] = str(target)
                except Exception as exc:  # noqa: BLE001 - 单张失败不拖垮整批
                    errors.append(f"{source.name}：{exc}")
                self.progress.emit(index + 1, total)
            self.finished.emit(mapping, errors)
        except Exception as exc:  # noqa: BLE001 - 兜底：别让线程静默死掉
            self.failed.emit(str(exc))
