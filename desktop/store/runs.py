# -*- coding: utf-8 -*-
"""阶段运行历史（runs.json）：每个阶段保留最近多次执行的记录，最新在前。

结构：{stage: [record, ...]}
record: {run_id, status, parameters, done, total, started_at, finished_at, output_path}
历史记录既用于页面状态渲染（最新一条），也作为阶段面板的历史配置选项。
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from desktop.store.json_io import read_json, write_json
from desktop.store.tasks import STAGES

MAX_RUN_HISTORY = 20  # 每阶段保留的执行历史条数


class RunMixin:
    """runs.json 读写。"""

    def runs_path(self, task_id: str) -> Path:
        """运行历史文件：任务目录下的 runs.json。"""
        return self.task_dir(task_id) / "runs.json"

    def _load_runs(self, task_id: str) -> dict:
        data = read_json(self.runs_path(task_id), {})
        return data if isinstance(data, dict) else {}

    def _save_runs(self, task_id: str, runs: dict) -> None:
        """写回 runs.json。

        任务可能已经被删除（子进程仍在跑、进度回调迟到），此时目录不存在，
        静默跳过而不是抛异常打断 UI 事件循环。
        """
        if not self.task_dir(task_id).exists():
            return
        write_json(self.runs_path(task_id), runs)

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
        """
        登记一次新的阶段执行并返回 run_id。

        新记录插在该阶段历史最前，初始状态 running、进度 0/0；每阶段只保留
        最近 MAX_RUN_HISTORY 条。resume 标记本次是否为续跑。
        """
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
        """按 run_id 更新 done/total；run_id 不在任何阶段时静默忽略。"""
        runs = self._load_runs(task_id)
        for records in runs.values():
            for record in self._as_history(records):
                if record.get("run_id") == run_id:
                    record["done"] = done
                    record["total"] = total
        self._save_runs(task_id, runs)

    def finish_stage(
        self,
        task_id: str,
        run_id: str,
        status: str,
        output_path: str | None = None,
        progress: tuple[int, int] | None = None,
    ) -> None:
        """结束某次运行：写入 status/finished_at/output_path。

        status 取 success/failed/cancelled 等；output_path 为该次执行的
        主产物路径（如 print.pdf、rembg 输出目录），供历史面板回链。
        任务目录已删除时静默跳过。

        progress 为 (done, total)，用于补齐最终计数。worker 的 finished 事件
        不再携带 done/total（进度由结构化 progress 事件实时汇报），因此调用方
        传入「最近一次进度」即可让历史记录落到真实完成数，而不是停在中间值。
        """
        runs = self._load_runs(task_id)
        for records in runs.values():
            for record in self._as_history(records):
                if record.get("run_id") == run_id:
                    record["status"] = status
                    record["finished_at"] = time.time()
                    record["output_path"] = output_path
                    if progress is not None:
                        record["done"], record["total"] = progress
        self._save_runs(task_id, runs)

    def list_stage_runs(self, task_id: str, stage: str) -> list[dict]:
        """某阶段的历史执行记录，最新在前。"""
        return self._as_history(self._load_runs(task_id).get(stage))

    def stage_states(self, task_id: str) -> dict[str, dict]:
        """每个阶段最近一次运行的状态与进度（页面步骤条渲染用）。

        ``status/done/total`` 取自最近一次运行；``completed`` 表示该阶段历史上
        是否成功执行过——重试失败不应把已经产出结果的步骤变回未完成。
        """
        runs = self._load_runs(task_id)
        states = {}
        for stage in STAGES:
            history = self._as_history(runs.get(stage))
            record = history[0] if history else None
            completed = any(r.get("status") == "success" for r in history)
            if record:
                states[stage] = {
                    "status": record.get("status", "pending"),
                    "done": record.get("done", 0),
                    "total": record.get("total", 0),
                    "completed": completed,
                }
            else:
                states[stage] = {
                    "status": "pending", "done": 0, "total": 0, "completed": False,
                }
        return states
