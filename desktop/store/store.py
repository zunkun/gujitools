# -*- coding: utf-8 -*-
"""TaskStore：任务、阶段、页面标注的统一文件存储入口。"""

from __future__ import annotations

from pathlib import Path

from ..utils.files import guji_data_dir
from .annotations import AnnotationMixin
from .migrate import migrate_legacy
from .pages import PageManifestMixin
from .runs import RunMixin
from .tasks import TaskMixin


class TaskStore(TaskMixin, RunMixin, PageManifestMixin, AnnotationMixin):
    def __init__(self, root: Path | None = None):
        self.root = root or guji_data_dir()
        (self.root / "tasks").mkdir(parents=True, exist_ok=True)
        migrate_legacy(self.root)
