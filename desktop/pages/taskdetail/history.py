# -*- coding: utf-8 -*-
"""任务详情页的历史执行配置控制器：回填最近参数、历史下拉框。"""

from __future__ import annotations

import time

from desktop.store import STAGES, STAGE_LABELS
from desktop.pages.taskdetail.runner import STATUS_LABELS


class HistoryMixin:
    """依赖宿主页面提供的属性：store/task_id、control_stack、step_bar、
    history_combo、_toast()。"""

    # 各阶段历史回填时要跳过的字段（临时/派生/运行时覆盖）
    _HISTORY_SKIP = frozenset(
        {"input", "output", "workers", "clean", "resume",
         "_effects", "_outpath", "_preview_run_id"}
    )
    # print 阶段：pdf_name / title_text 始终从源 PDF 名派生，
    # 历史里存的是旧值或用户曾经填的自定义名，不应覆盖当前任务的规则值
    _PRINT_FIXED_KEYS = frozenset({"pdf_name", "title_text"})

    def _history_fill_keys(self, stage: str) -> set:
        skip = set(self._HISTORY_SKIP)
        if stage == "print":
            skip |= self._PRINT_FIXED_KEYS
        return skip

    def _restore_stage_params(self, index: int) -> None:
        """进入页面/切换阶段时回填参数：**暂存优先**，其次最近一次执行。

        优先级 = 暂存 > 最近一次执行参数 > 内置默认：暂存是"用户最后的手动
        意图"（还没执行就切走了），比"上一次跑过的参数"更新；两者都没有时
        表单保持 `set_task` 复位后的内置默认（print 的 PDF 名/古籍名另由
        `set_source_defaults` 从源 PDF 名派生）。
        """
        if not self.task_id:
            return
        stage = STAGES[index]
        if stage in self._history_prefilled:
            return
        self._history_prefilled.add(stage)
        draft = self.store.load_draft(self.task_id, stage)
        if draft:
            self.control_stack.widget(index).apply_args(draft)
            return
        history = self.store.list_stage_runs(self.task_id, stage)
        if history:
            params = {
                k: v for k, v in history[0].get("parameters", {}).items()
                if k not in self._history_fill_keys(stage)
            }
            self.control_stack.widget(index).apply_args(params)

    def _refresh_history_options(self) -> None:
        """把当前阶段的历史执行记录填入下拉框（最新在前）。"""
        combo = self.history_combo
        combo.blockSignals(True)
        combo.clear()
        self._history_params: list[dict] = []
        if self.task_id:
            stage = STAGES[max(self.step_bar._current, 0)]
            for record in self.store.list_stage_runs(self.task_id, stage):
                started = time.strftime(
                    "%m-%d %H:%M", time.localtime(record.get("started_at", 0))
                )
                resume = "续跑" if record.get("parameters", {}).get("resume") else "全量"
                status = STATUS_LABELS.get(record.get("status", ""), record.get("status", ""))
                combo.addItem(f"{started} · {resume} · {status}")
                self._history_params.append(record.get("parameters", {}))
        if self._history_params:
            combo.setCurrentIndex(-1)
            combo.setPlaceholderText(f"共 {len(self._history_params)} 次，选择回填")
        else:
            combo.setPlaceholderText("暂无历史执行配置")
        combo.blockSignals(False)

    def _on_history_selected(self, index: int) -> None:
        if index < 0 or index >= len(getattr(self, "_history_params", [])):
            return
        stage = STAGES[max(self.step_bar._current, 0)]
        params = {
            k: v for k, v in self._history_params[index].items()
            if k not in self._history_fill_keys(stage)
        }
        self.control_stack.widget(self.step_bar._current).apply_args(params)
        self._toast("info", "已回填历史配置", STAGE_LABELS[stage])
