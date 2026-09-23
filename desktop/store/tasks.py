# -*- coding: utf-8 -*-
"""任务索引（tasks.json）与任务目录布局。"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from desktop.store.json_io import read_json, write_json
from desktop.utils.files import copy_file_atomic

STAGES = ("extract", "detect", "rembg", "print")
# ⚠️ 这些是**界面文案**（步骤条/面板标题/toast/日志共用一份）：有中文就不再附
# 英文键名 —— 用户口径「四个步骤有中文，英文就不要出现」。
STAGE_LABELS = {
    "extract": "提取图片",
    "detect": "检测文本框",
    "rembg": "图片去底色",
    # rembg 的「提交本次任务」动作：预览图按 area/border 合成最终图片
    "rembg_submit": "提交去底色结果",
    "print": "生成 PDF",
}

# 列表里的阶段短名（步骤条/表格空间有限，用 2~3 字表达）
STAGE_SHORT = {
    "extract": "提取",
    "detect": "检测",
    "rembg": "去底",
    "print": "PDF",
}

#: 运行阶段 → 它归属的**界面步骤**（值取 STAGES 里的一项）。
#:
#: ⚠️ 「提交本次任务」（rembg_submit）不是独立步骤，而是第三步 rembg 面板上的
#: 动作：它的进度必须显示在第三步。有了这张表，界面才谈得上"只有当前这一步的
#: 进度才上屏"（详见 desktop/pages/taskdetail/runner.py::_progress_belongs_here）。
STAGE_STEP = {
    "extract": "extract",
    "detect": "detect",
    "rembg": "rembg",
    "rembg_submit": "rembg",
    "print": "print",
}


class TaskMixin:
    """任务索引读写与任务目录/阶段输出目录的路径推导。"""

    root: Path

    # ---------- tasks.json ----------
    def _tasks_path(self) -> Path:
        return self.root / "tasks.json"

    def _load_tasks_index(self) -> list[dict]:
        data = read_json(self._tasks_path(), [])
        return data if isinstance(data, list) else []

    def _save_tasks_index(self, tasks: list[dict]) -> None:
        self._tasks_path().parent.mkdir(parents=True, exist_ok=True)
        write_json(self._tasks_path(), tasks)

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
        """按源文件指纹查重，返回全部命中的任务记录（可能多条）。"""
        return [
            t for t in self._load_tasks_index() if t.get("source_hash") == source_hash
        ]

    def list_tasks(self) -> list[dict]:
        """全部任务，按 updated_at 倒序（最近改动的排在前面）。"""
        return sorted(
            self._load_tasks_index(), key=lambda t: t.get("updated_at", 0), reverse=True
        )

    def get_task(self, task_id: str) -> dict | None:
        """按任务号取任务记录；不存在返回 None。"""
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
        """
        新建任务并返回任务号（四位零填充）。

        任务号取当前最大号 +1，同时参考索引与磁盘目录；若两者不一致导致号被
        占用则继续顺延。创建时会预建 stages/runs/thumbnails/source
        子目录，但不复制源文件（由 copy_source_to_task 负责）。
        """
        task_id = self._next_task_no()  # 顺序任务号，目录即 0001、0002…
        now = time.time()
        tasks = self._load_tasks_index()
        # 兜底：极端情况下（并发/索引与磁盘不一致）拿到已占用的号，继续往后取
        taken = {t.get("id") for t in tasks}
        while task_id in taken or (self.task_dir(task_id)).exists():
            task_id = f"{int(task_id) + 1:04d}"
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
        for sub in ("stages", "runs", "thumbnails/source"):
            (task_dir / sub).mkdir(parents=True, exist_ok=True)
        return task_id

    def update_task(self, task_id: str, status: str) -> None:
        """更新任务状态与 updated_at；任务号不存在时静默忽略。"""
        tasks = self._load_tasks_index()
        for task in tasks:
            if task.get("id") == task_id:
                task["status"] = status
                task["updated_at"] = time.time()
                break
        self._save_tasks_index(tasks)

    def delete_task(self, task_id: str) -> bool:
        """删除任务及其中间产物，返回是否真的删掉。

        ⚠️ 顺序是「**先删目录、成功才删索引**」：反过来的话目录一旦被占用
        没删掉、索引却先没了，任务目录就变成没人认领的孤儿，用户还看不见。

        ⚠️ Windows 上 PDF 被后台渲染线程打开时 ``rmtree`` 抛 PermissionError，
        原先 ``ignore_errors=True`` 会让它**静默残留**——列表里显示已删除，
        磁盘上目录还在。这里重试若干次再判定失败，失败时保留任务让用户重试。
        """
        task_dir = self.task_dir(task_id)
        if task_dir.exists() and not self._rmtree_with_retry(task_dir):
            return False
        tasks = [t for t in self._load_tasks_index() if t.get("id") != task_id]
        self._save_tasks_index(tasks)
        return True

    @staticmethod
    def _rmtree_with_retry(path: Path, tries: int = 8, delay: float = 0.06) -> bool:
        """反复尝试删除目录；文件被短暂占用（后台渲染）时等一会儿再试。"""
        for attempt in range(tries):
            try:
                shutil.rmtree(path)
                return True
            except OSError:
                if attempt == tries - 1:
                    return False
                time.sleep(delay)
        return False

    # ---------- 任务目录布局 ----------
    def task_dir(self, task_id: str) -> Path:
        """任务根目录：tasks/<任务号>。"""
        return self.root / "tasks" / task_id

    def stage_dir(self, task_id: str, stage: str) -> Path:
        """某阶段的输出目录：tasks/<任务号>/stages/<阶段>。"""
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
        """print 阶段产物 print.pdf 的完整路径。"""
        return self.stage_dir(task_id, "print") / "print.pdf"

    def stage_output_dir(self, task_id: str, stage: str) -> Path:
        """返回某阶段（GUI）应写入的输出目录。

        注意 rembg 阶段返回 rembgpreview 预览目录，rembg_submit 才指向
        rembg 最终目录；print 返回 print.pdf 所在目录。
        """
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
        """已废弃：检测/去底直接读 extract 输出目录，不再物化输入副本。

        仅为清理历史遗留目录保留（老版本任务目录下可能仍有 workset/）。
        """
        return self.task_dir(task_id) / "workset"

    def runs_config_dir(self, task_id: str) -> Path:
        """子进程执行配置（run-*.json / detect-config.json）。"""
        return self.task_dir(task_id) / "runs"

    def source_thumbnails_dir(self, task_id: str) -> Path:
        """源 PDF 页缩略图：导入即生成，PDF 预览直接复用，永不清理。"""
        return self.task_dir(task_id) / "thumbnails" / "source"

    def copy_source_to_task(self, task_id: str, source_path: Path) -> Path:
        """导入时在任务目录下保留一份源文件副本（原子落地）。

        ⚠️ 复制本身可能是在**后台线程**里做的（见
        ``desktop/workers/serial_jobs.py``），而详情页/预览随时会来读这份
        副本，所以走 ``copy_file_atomic``：写 ``.part`` 再 ``os.replace``，
        别人不会读到半截 PDF。
        """
        target = self.task_dir(task_id) / source_path.name
        return copy_file_atomic(source_path, target)

    def source_copy_path(self, task_id: str) -> Path | None:
        """任务目录里的 PDF 备份路径；没有备份返回 None。

        ⚠️ 后续所有操作（详情页预览、extract 入参…）**都必须用它**，不能用
        ``task['source_path']``：源文件在用户磁盘上，会被移动/改名/删除，
        一走就「渲染失败」。备份随任务走，任务才是自包含的。
        """
        task_dir = self.task_dir(task_id)
        task = self.get_task(task_id)
        if task:
            candidate = task_dir / Path(str(task.get("source_path") or "")).name
            if candidate.is_file():
                return candidate
        # 兜底：源被改名过（文件名对不上）时，任务目录下唯一的 PDF 就是备份
        pdfs = sorted(task_dir.glob("*.pdf")) if task_dir.exists() else []
        return pdfs[0] if pdfs else None

    def ensure_source_copy(self, task_id: str) -> Path | None:
        """保证任务目录里有 PDF 备份；缺了就按索引里的 source_path 补一份。

        老任务（导入时复制失败）或备份被误删时靠它自愈；源也一起没了就
        返回 None，调用方负责提示。
        """
        existing = self.source_copy_path(task_id)
        if existing:
            return existing
        task = self.get_task(task_id)
        if not task:
            return None
        source = Path(str(task.get("source_path") or ""))
        if not source.is_file():
            return None
        try:
            return self.copy_source_to_task(task_id, source)
        except OSError:
            return None
