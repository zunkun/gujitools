# -*- coding: utf-8 -*-
"""阶段运行历史（runs.json）：每个阶段保留最近多次执行的记录，最新在前。

结构：{stage: [record, ...]}
record: {run_id, status, parameters, done, total, started_at, finished_at, output_path}
历史记录既用于页面状态渲染（最新一条），也作为阶段面板的历史配置选项。
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from .tasks import STAGES

MAX_RUN_HISTORY = 20  # 每阶段保留的执行历史条数


class RunMixin:
    """runs.json 读写。"""

    def runs_path(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "runs.json"

    def _load_runs(self, task_id: str) -> dict:
        path = self.runs_path(task_id)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_runs(self, task_id: str, runs: dict) -> None:
        self.runs_path(task_id).write_text(
            json.dumps(runs, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    @staticmethod
    def _as_history(value) -> list[dict]:
        """兼容旧格式：单条记录（dict）→ 历史列表。"""
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return value
        return []

    def create_stage_run(
        self, task_id: str, stage: str, parameters: dict, resume: bool = False
    ) -> str:
        run_id = uuid.uuid4().hex
        runs = self._load_runs(task_id)
        history = self._as_history(runs.get(stage))
        history.insert(
            0,
            {
                "run_id": run_id,
                "status": "running",
                "parameters": {"resume": resume, **parameters},
                "done": 0,
                "total": 0,
                "started_at": time.time(),
                "finished_at": None,
                "output_path": None,
            },
        )
        runs[stage] = history[:MAX_RUN_HISTORY]
        self._save_runs(task_id, runs)
        return run_id

    def set_progress(self, task_id: str, run_id: str, done: int, total: int) -> None:
        runs = self._load_runs(task_id)
        for records in runs.values():
            for record in self._as_history(records):
                if record.get("run_id") == run_id:
                    record["done"] = done
                    record["total"] = total
        self._save_runs(task_id, runs)

    def finish_stage(
        self, task_id: str, run_id: str, status: str, output_path: str | None = None
    ) -> None:
        runs = self._load_runs(task_id)
        for records in runs.values():
            for record in self._as_history(records):
                if record.get("run_id") == run_id:
                    record["status"] = status
                    record["finished_at"] = time.time()
                    record["output_path"] = output_path
        self._save_runs(task_id, runs)

    def list_stage_runs(self, task_id: str, stage: str) -> list[dict]:
        """某阶段的历史执行记录，最新在前。"""
        return self._as_history(self._load_runs(task_id).get(stage))

    def stage_states(self, task_id: str) -> dict[str, dict]:
        """每个阶段最近一次运行的状态与进度（页面步骤条渲染用）。"""
        runs = self._load_runs(task_id)
        states = {}
        for stage in STAGES:
            history = self._as_history(runs.get(stage))
            record = history[0] if history else None
            if record:
                states[stage] = {
                    "status": record.get("status", "pending"),
                    "done": record.get("done", 0),
                    "total": record.get("total", 0),
                }
            else:
                states[stage] = {"status": "pending", "done": 0, "total": 0}
        return states
