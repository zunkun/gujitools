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
    # ⚠️ **阶段专属的跳过键已搬进 ``StepSpec``**（2026-10-03）：
    #   print 的 pdf_name/title_text → ``spec.history_skip``；
    #   extract 的 pages → ``spec.auto_fill_skip``。
    #   理由同上：那是"这一步"的属性，不该由页面维护第二份（加一步要改两处）。

    def _history_fill_keys(self, stage: str) -> set:
        """历史回填（手动挑历史 + 自动回填都）要跳过的键。

        跳过集合 = 全局公共项 + **这一步声明的** ``StepSpec.history_skip``
        （第四步的 ``pdf_name`` / ``title_text`` 始终从源 PDF 名派生，历史里的
        旧值不应覆盖规则值）。⚠️ 查 spec 而非 ``if stage == "print"``：加一步
        要跳别的键，改它的 spec 即可。
        """
        from desktop.steps import ports

        spec = ports.spec_for_stage(stage)
        skip = set(self._HISTORY_SKIP)
        if spec:
            skip |= set(spec.history_skip)
        return skip

    def _auto_fill_keys(self, stage: str) -> set:
        """自动回填用的跳过集合 = 历史跳过 + **这一步声明的** ``auto_fill_skip``。

        extract 的 ``pages`` 是「续跑」时按缺失页**派生**出来的一次性参数
        （见 StageRunnerMixin._run_stage_unchecked），压根不是用户意图：自动
        回填它会让下一次点执行只跑那一小段页码——用户看到的就是"只提取了一半"，
        而且历史里存的还是这个残缺范围，越跑越窄。

        ⚠️ **只在自动回填时跳过**。用户在下拉框里主动挑一条历史配置时仍然原样
        回填（那是"照那次参数再跑一遍"的明确指令，tests/selftests/history.py 钉着）。
        """
        from desktop.steps import ports

        spec = ports.spec_for_stage(stage)
        return self._history_fill_keys(stage) | set(
            spec.auto_fill_skip if spec else ()
        )

    def _current_history_stage(self) -> str:
        """历史回填当前对应的阶段 key。

        ⚠️ 流程条第 5 位是「图片拼版」伪步骤（无历史/无参数可回填），
        下标越界时按第一步兜底——只走防御，正常路径不会到那里。
        """
        current = self.step_bar._current
        return STAGES[current] if 0 <= current < len(STAGES) else STAGES[0]

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
                if k not in self._auto_fill_keys(stage)
            }
            self.control_stack.widget(index).apply_args(params)

    def _refresh_history_options(self) -> None:
        """把当前阶段的历史执行记录填入下拉框（最新在前）。"""
        combo = self.history_combo
        combo.blockSignals(True)
        combo.clear()
        self._history_params: list[dict] = []
        if self.task_id:
            stage = self._current_history_stage()
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
        current = self.step_bar._current
        if not 0 <= current < len(STAGES):
            return  # 「图片拼版」占位详情没有历史回填（下拉框也处于隐藏态）
        stage = STAGES[current]
        params = {
            k: v for k, v in self._history_params[index].items()
            if k not in self._history_fill_keys(stage)
        }
        self.control_stack.widget(current).apply_args(params)
        self._toast("info", "已回填历史配置", STAGE_LABELS[stage])
