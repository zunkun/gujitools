# -*- coding: utf-8 -*-
"""阶段运行历史（runs.json）：每个阶段保留最近多次执行的记录，最新在前。

结构：{stage: [record, ...]}
record: {run_id, status, parameters, done, total, started_at, finished_at,
         output_path, error}
历史记录既用于页面状态渲染（最新一条），也作为阶段面板的历史配置选项。
``error`` 只在失败时写：worker 起不来的那类失败（0 条事件、0.2 秒退出）
以前在记录里只有 ``done=0 total=0``，事后完全没法查。
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from desktop.store.json_io import read_json, write_json
from desktop.store.tasks import STAGES

MAX_RUN_HISTORY = 20  # 每阶段保留的执行历史条数

#: 入史前剥掉的大块**运行时派生**字段。它们由「面板参数 + 当页清单」在每次
#: 执行时重新推导（``_effects`` ← entries+area/border；``files`` ← print.json；
#: ``page_rects`` ← 版面编辑器），面板回填（``apply_args``）只认表单字段，
#: 永远用不到这三个。留着它们的话：2400 页的书单条记录 64KB~0.5MB，
#: ×20 条历史，运行期每 200ms 的 ``set_progress`` 全量重写一次 → 每秒几十 MB
#: 的磁盘写放大 + 主线程 json.dumps 卡顿（2026-09-26 第二轮审计 M5）。
#: ⚠️ ``pdf_name`` 等**表单字段必须保留**（``_latest_print_pdf_path`` 靠它解析产物名）。
_RUN_STRIP_KEYS = frozenset({"_effects", "files", "page_rects"})


class RunMixin:
    """runs.json 读写。"""

    if TYPE_CHECKING:
        # 宿主 TaskStore（或同级 Mixin）提供：只做类型声明，运行时零副作用。
        root: Path
        task_dir: Callable[[str], Path]
        task_slots: Callable[[str], Any]

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
        stored_parameters = {
            key: value
            for key, value in parameters.items()
            if key not in _RUN_STRIP_KEYS
        }
        history.insert(
            0,
            {
                "run_id": run_id,
                "status": "running",
                "parameters": {"resume": resume, **stored_parameters},
                "done": 0,
                "total": 0,
                "started_at": time.time(),
                "finished_at": None,
                "output_path": None,
                "error": None,
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
        error: str | None = None,
    ) -> None:
        """结束某次运行：写入 status/finished_at/output_path（可选 error）。

        status 取 success/failed/cancelled 等；output_path 为该次执行的
        主产物路径（如 print.pdf、rembg 输出目录），供历史面板回链。
        任务目录已删除时静默跳过。

        progress 为 (done, total)，用于补齐最终计数。worker 的 finished 事件
        不再携带 done/total（进度由结构化 progress 事件实时汇报），因此调用方
        传入「最近一次进度」即可让历史记录落到真实完成数，而不是停在中间值。

        error 为失败原因（退出码 / worker 的最后一行错误 / "子进程启动失败"）。
        ⚠️ 必须落盘：worker 起不来的那类失败**没有任何输出**，界面上只有一条
        转瞬即逝的 toast，记录里若也只有 ``done=0 total=0``，事后就彻底查不出
        原因（用户报「提交失败但没说为什么」，只能靠猜）。
        """
        runs = self._load_runs(task_id)
        for records in runs.values():
            for record in self._as_history(records):
                if record.get("run_id") == run_id:
                    record["status"] = status
                    record["finished_at"] = time.time()
                    record["output_path"] = output_path
                    if error is not None:
                        record["error"] = error
                    if progress is not None:
                        record["done"], record["total"] = progress
        self._save_runs(task_id, runs)

    def list_stage_runs(self, task_id: str, stage: str) -> list[dict]:
        """某阶段的历史执行记录，最新在前。"""
        return self._as_history(self._load_runs(task_id).get(stage))

    def all_stage_runs(self, task_id: str) -> dict[str, list[dict]]:
        """整份运行历史（**一次读盘**），键为阶段名、值为最新在前的记录列表。

        给"跨阶段比对时间戳"这类一次要看全的场景用：逐个 ``list_stage_runs()``
        会把整份 runs.json 读 N 遍（任务多跑过几次就有几十上百 KB）。
        """
        runs = self._load_runs(task_id)
        return {
            stage: self._as_history(records) for stage, records in runs.items()
        }

    def flow_stages(self, task_id: str) -> set[str]:
        """本任务流程里**真实存在**的运行阶段集合（按界面格摊开）。

        ⚠️ **按"界面格"判定，不按节点**：``rembg``（图片去底色）与
        ``rembg_submit``（提交去底色结果）在界面上折成**同一格**，用户画流程图
        时通常只画一个「图片去底色」节点。若按"图里有没有这个节点"判，会把
        提交那一动作判成"不在流程里"⇒ 进度条上"已提交"的绿点不亮。

        读盘失败（文件坏/无任务）一律**当作"一个阶段也不在流程里"**（空集）：
        调用方（列表胶囊、``stage_states`` 的 ``in_flow`` 标记）据此不显示、
        不断言，**而不是**伪造四个默认阶段——以前这里回 ``set(STAGES)``，
        读不到流程的任务在列表里会冒出四个默认胶囊，用户还以为"默认流程
        又出现了"（而 ``task_slots`` 读不到时列表 worker 那边是另一套伪造，
        两边伪造的还可能对不上）。

        ⚠️ 键集合不受影响：:meth:`stage_states` 照旧建四个静态键（调用方硬
        索引），只是 ``in_flow`` 全是 False。
        """
        from desktop.steps import ports

        try:
            steps = {slot.step for slot in self.task_slots(task_id)
                     if not slot.optional}
        except Exception:  # noqa: BLE001 - 读不到流程不该拖垮调用方
            return set()
        return {stage for stage, step in ports.STAGE_STEPS.items()
                if step in steps}

    def stage_states(self, task_id: str) -> dict[str, dict]:
        """每个阶段最近一次运行的状态与进度（页面步骤条渲染用）。

        ``status/done/total`` 取自最近一次运行；``completed`` 表示该阶段历史上
        是否成功执行过——重试失败不应把已经产出结果的步骤变回未完成。

        ⚠️ **键集合仍是静态的四个阶段**（调用方大量硬索引，例如
        ``stage_states(tid)["rembg"]["status"]``），另外给每个键加一个
        ``in_flow`` 标记表示"这一阶段在本任务的流程图里"。**别把不在流程里
        的阶段直接删掉**——那些硬索引会 KeyError，症状是"点了没反应"的崩溃
        而不是干净降级。要"只列流程里的阶段"请走 :meth:`flow_stages` 或
        ``task_slots``。
        """
        runs = self._load_runs(task_id)
        in_flow = self.flow_stages(task_id)
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
                    "in_flow": stage in in_flow,
                }
            else:
                states[stage] = {
                    "status": "pending", "done": 0, "total": 0, "completed": False,
                    "in_flow": stage in in_flow,
                }
        return states
