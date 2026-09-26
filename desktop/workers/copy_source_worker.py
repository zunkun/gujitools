# -*- coding: utf-8 -*-
"""后台补一份源文件副本（**绝不在主线程复制**）。

背景：导入后台任务会顺手把源 PDF 复制进任务目录，之后一切都用副本
（源文件在用户磁盘上会被移动/改名/删除）。但两种情况副本会缺：

1. 导入时复制失败（磁盘满/权限）；
2. 早期版本导入的老任务，压根没做备份。

老实现是在详情页 `set_task()` 里**同步**调 `ensure_source_copy()` 补——
一本 800MB 的书就是主线程卡住几秒到几十秒（用户报「进详情页要等一会」）。
现在改成：先照常用源文件显示，**延时几秒**后如果副本还是没出现，再由这个
worker 在后台线程里补一份；补的期间界面照常可用。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from desktop.utils.files import copy_file_atomic


class CopySourceWorker(QObject):
    """把源 PDF 原子复制到任务目录（后台线程里跑）。"""

    finished = Signal(str)  # 副本路径
    failed = Signal(str)

    def __init__(self, source: Path, target: Path):
        """source 为源文件；target 为任务目录里的副本路径。"""
        super().__init__()
        self.source = source
        self.target = target

    @Slot()
    def run(self) -> None:
        """执行复制：失败只报 failed，不影响任务使用源文件继续干活。"""
        try:
            self.finished.emit(str(copy_file_atomic(self.source, self.target)))
        except Exception as exc:  # noqa: BLE001 - 复制失败不该让界面报错
            self.failed.emit(str(exc))


class CopyFilesWorker(QObject):
    """批量复制文件到目标目录（后台线程里跑；审计 D2）。

    「插入图片」「下载 PDF」原先在主线程 `shutil.copy2`——一本 463MB 的 PDF
    就把界面冻住整个复制时长。现在主线程只算好 (源, 目标) 对，这里逐对复制；
    单个失败不中断整批（跳过并在结果里注明）。
    """

    #: 全部完成：(成功列表 [(源, 目标)], 失败列表 [(源, 原因)])
    finished = Signal(list, list)
    failed = Signal(str)

    def __init__(self, jobs: list[tuple[Path, Path]]):
        super().__init__()
        self.jobs = list(jobs)

    @Slot()
    def run(self) -> None:
        import shutil

        done: list[tuple[str, str]] = []
        errors: list[tuple[str, str]] = []
        try:
            for source, target in self.jobs:
                try:
                    shutil.copy2(source, target)
                    done.append((str(source), str(target)))
                except OSError as exc:
                    errors.append((str(source), str(exc)))
            self.finished.emit(done, errors)
        except Exception as exc:  # noqa: BLE001 - 兜底：别让线程静默死掉
            self.failed.emit(str(exc))
