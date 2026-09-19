# -*- coding: utf-8 -*-
"""参数暂存（``drafts/<阶段>.json``）：用户改过、但**还没执行**的阶段参数。

为什么需要它：进入某个阶段时表单按「最近一次执行参数」回填（见
``desktop/pages/taskdetail/history.py``），用户改完参数却没执行就切阶段 /
切任务 / 关程序，改动全部丢失——再回来看到的还是上一次执行的值，等于白调。

存什么：``get_args()`` 的结果（已归一化：边距是列表、颜色是 "r,g,b"、
跳过页是列表…）。读取方是同一个面板的 ``apply_args()``，所以"存—取"天然
按同一套键名对称，不需要第二份字段表。

- 与 ``pages.json``/``print.json`` 一样是任务目录下的 JSON，删除任务即清掉；
- 系统管理字段（input/output/workers/clean…）不入暂存，与历史回填的跳过
  清单一致；
- 参数非法时调用方**不写**（见 ``save_draft`` 的返回值），保留上一份有效暂存。
"""

from __future__ import annotations

from pathlib import Path

from desktop.store.json_io import read_json, write_json

# 不入暂存的键：系统管理 / 运行时覆盖，与 HistoryMixin._HISTORY_SKIP 同源
DRAFT_SKIP = frozenset(
    {"input", "output", "workers", "clean", "resume",
     "_effects", "_outpath", "_preview_run_id"}
)


class DraftMixin:
    """``drafts/<阶段>.json`` 的读写。"""

    root: Path

    def drafts_dir(self, task_id: str) -> Path:
        """暂存目录：``tasks/<任务号>/drafts``。"""
        return self.task_dir(task_id) / "drafts"

    def draft_path(self, task_id: str, stage: str) -> Path:
        """某阶段的暂存文件：``drafts/<阶段>.json``。"""
        return self.drafts_dir(task_id) / f"{stage}.json"

    def load_draft(self, task_id: str, stage: str) -> dict | None:
        """读取暂存参数；没有/格式不对返回 None。"""
        data = read_json(self.draft_path(task_id, stage), None)
        return data if isinstance(data, dict) and data else None

    def save_draft(self, task_id: str, stage: str, params: dict) -> bool:
        """写入暂存参数，返回是否真的写了。

        任务目录已删除时跳过（与 ``save_pages`` 同规矩：不把已删任务重新
        创建出来）；``params`` 为空则视为"没有可暂存的内容"，返回 False。
        """
        if not task_id or not params:
            return False
        if not self.task_dir(task_id).exists():
            return False
        cleaned = {k: v for k, v in params.items() if k not in DRAFT_SKIP}
        if not cleaned:
            return False
        self.drafts_dir(task_id).mkdir(parents=True, exist_ok=True)
        write_json(self.draft_path(task_id, stage), cleaned)
        return True

    def clear_draft(self, task_id: str, stage: str) -> None:
        """删除某阶段的暂存（用户点「恢复默认配置」并执行后想彻底归零时用）。"""
        try:
            self.draft_path(task_id, stage).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
