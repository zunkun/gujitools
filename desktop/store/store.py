# -*- coding: utf-8 -*-
"""TaskStore：任务、阶段、页面标注的统一文件存储入口。"""

from __future__ import annotations

from pathlib import Path

from desktop.utils.files import guji_data_dir
from desktop.store.annotations import AnnotationMixin
from desktop.store.drafts import DraftMixin
from desktop.store.pages import PageManifestMixin
from desktop.store.runs import RunMixin
from desktop.store.tasks import TaskMixin


class TaskStore(TaskMixin, RunMixin, PageManifestMixin, AnnotationMixin, DraftMixin):
    """唯一数据入口：组合任务/运行/页面/标注/暂存五个 Mixin，统一读写文件存储。

    数据根目录下含 tasks/（每任务一子目录）及各 JSON 清单
    （tasks.json/runs.json/boxes.json/sizes.json/pages.json/print.json）；
    每任务目录下另有 drafts/<阶段>.json（用户改过但未执行的参数暂存）。
    """

    def __init__(self, root: Path | None = None):
        """初始化数据根。

        root 省略时默认用 guji_data_dir()（~/Documents/guji）；传入自定义
        root 主要用于测试隔离。构造时只确保 tasks/ 存在——存储一直是纯
        JSON 文件，没有旧数据（SQLite）需要迁移。
        """
        self.root = root or guji_data_dir()
        (self.root / "tasks").mkdir(parents=True, exist_ok=True)
