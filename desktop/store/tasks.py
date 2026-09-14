# -*- coding: utf-8 -*-
"""任务索引（tasks.json）与任务目录布局。"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

STAGES = ("extract", "detect", "rembg", "print")
STAGE_LABELS = {
    "extract": "提取图片",
    "detect": "检测文本框(detect)",
    "rembg": "图片去底色",
    # rembg 的「提交本次任务」动作：预览图按 area/border 合成最终图片
    "rembg_submit": "提交去底色结果",
    "print": "生成PDF(print)",
}


class TaskMixin:
    """任务索引读写与任务目录/阶段输出目录的路径推导。"""

    root: Path

    # ---------- tasks.json ----------
    def _tasks_path(self) -> Path:
        return self.root / "tasks.json"

    def _load_tasks_index(self) -> list[dict]:
        path = self._tasks_path()
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save_tasks_index(self, tasks: list[dict]) -> None:
        self._tasks_path().write_text(
            json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    # ---------- 任务 CRUD ----------
    def _next_task_no(self) -> str:
        """下一个任务号：当前最大任务号 + 1（同时参考索引与磁盘目录）。"""
        numbers = []
        for task in self._load_tasks_index():
            tid = str(task.get("id", ""))
            if tid.isdigit():
                numbers.append(int(tid))
        tasks_root = self.root / "tasks"
        if tasks_root.exists():
            for entry in tasks_root.iterdir():
                if entry.is_dir() and entry.name.isdigit():
                    numbers.append(int(entry.name))
        return f"{max(numbers, default=0) + 1:04d}"

    def find_tasks(self, source_hash: str) -> list[dict]:
        return [
            t for t in self._load_tasks_index() if t.get("source_hash") == source_hash
        ]

    def list_tasks(self) -> list[dict]:
        return sorted(
            self._load_tasks_index(), key=lambda t: t.get("updated_at", 0), reverse=True
        )

    def get_task(self, task_id: str) -> dict | None:
        for task in self._load_tasks_index():
            if task.get("id") == task_id:
                return task
        return None

    def create_task(
        self,
        source_path: Path,
        source_hash: str,
        name: str,
        duplicate_confirmed: bool = False,
    ) -> str:
        task_id = self._next_task_no()  # 顺序任务号，目录即 0001、0002…
        now = time.time()
        tasks = self._load_tasks_index()
        tasks.append(
            {
                "id": task_id,
                "name": name,
                "source_path": str(source_path),
                "source_hash": source_hash,
                "status": "draft",
                "created_at": now,
                "updated_at": now,
                "duplicate_confirmed": int(bool(duplicate_confirmed)),
            }
        )
        self._save_tasks_index(tasks)
        task_dir = self.task_dir(task_id)
        for sub in ("stages", "workset", "runs", "thumbnails/source"):
            (task_dir / sub).mkdir(parents=True, exist_ok=True)
        return task_id

    def update_task(self, task_id: str, status: str) -> None:
        tasks = self._load_tasks_index()
        for task in tasks:
            if task.get("id") == task_id:
                task["status"] = status
                task["updated_at"] = time.time()
                break
        self._save_tasks_index(tasks)

    def delete_task(self, task_id: str) -> None:
        tasks = [t for t in self._load_tasks_index() if t.get("id") != task_id]
        self._save_tasks_index(tasks)
        task_dir = self.task_dir(task_id)
        if task_dir.exists():
            shutil.rmtree(task_dir, ignore_errors=True)

    # ---------- 任务目录布局 ----------
    def task_dir(self, task_id: str) -> Path:
        return self.root / "tasks" / task_id

    def stage_dir(self, task_id: str, stage: str) -> Path:
        return self.task_dir(task_id) / "stages" / stage

    def extract_output_dir(self, task_id: str) -> Path:
        """提取图片直接位于 stages/extract（无 PDF 名/嵌套子目录）。"""
        return self.stage_dir(task_id, "extract")

    def rembg_output_dir(self, task_id: str) -> Path:
        """步骤三最终图片目录（「提交本次任务」产出，print 阶段从此取图）。"""
        return self.stage_dir(task_id, "rembg")

    def rembg_preview_output_dir(self, task_id: str) -> Path:
        """「生成预览」产出的整页去底预览图目录（中间产物，不参与 print）。"""
        return self.stage_dir(task_id, "rembgpreview")

    def print_output_pdf(self, task_id: str) -> Path:
        return self.stage_dir(task_id, "print") / "print.pdf"

    def stage_output_dir(self, task_id: str, stage: str) -> Path:
        return {
            "extract": self.extract_output_dir(task_id),
            # detect 只检测不落盘；若有参考缩略图放 thumbnails/detect
            "detect": self.task_dir(task_id) / "thumbnails" / "detect",
            # rembg 阶段的执行产物是整页去底预览图（rembgpreview）；
            # 「提交本次任务」(rembg_submit) 才把最终图片写入 rembg。
            "rembg": self.rembg_preview_output_dir(task_id),
            "rembg_submit": self.rembg_output_dir(task_id),
            "print": self.print_output_pdf(task_id).parent,
        }[stage]

    def workset_dir(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "workset"

    def runs_config_dir(self, task_id: str) -> Path:
        """子进程执行配置（run-*.json / detect-config.json）。"""
        return self.task_dir(task_id) / "runs"

    def source_thumbnails_dir(self, task_id: str) -> Path:
        """源 PDF 页缩略图：导入即生成，PDF 预览直接复用，永不清理。"""
        return self.task_dir(task_id) / "thumbnails" / "source"

    def copy_source_to_task(self, task_id: str, source_path: Path) -> Path:
        """导入时在任务目录下保留一份源文件副本。"""
        target = self.task_dir(task_id) / source_path.name
        shutil.copy2(source_path, target)
        return target
