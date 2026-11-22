# -*- coding: utf-8 -*-
"""任务详情页的执行控制：执行权占用、防抖、按钮状态。"""

from __future__ import annotations

import time
from desktop.ui.widgets import bold_button
from ._qt import QProcess
from typing import TYPE_CHECKING, Any


class RunControlMixin:
    """执行权占用与执行按钮状态。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _is_aggregate_input_node: Any
        _regenerate_notice: Any
        _toast: Any
        _update_submit_button: Any
        current_stage: Any
        detect_process: Any
        process: Any
        run_button: Any

    #: 执行按钮的防抖窗口(ms)：连击/双击在窗口内的第二次直接**静默**吞掉
    #: （不弹提示——手快的人否则会看到一串"任务进行中"）。取 400ms：够盖住
    #: 鼠标双击间隔（通常 ≤250ms），又不至于让人感觉"点了没反应"。
    RUN_DEBOUNCE_MS = 400

    def _busy_label(self) -> str | None:
        """当前有执行在跑就返回它的名字，空闲返回 None（按钮状态的唯一判据）。

        ⚠️ 只看 ``self.process`` 会有两个盲区，所以这里分两步判断：

        1. **先看进程实况**（硬事实）：步骤子进程、单页检测进程任一在跑就是在忙。
        2. **再看受理标记**，且**只在还没有任何进程对象时**才算数：
           - 受理窗口期（点下去了，进程还没 start）→ 拦住，这正是漏点；
           - 进程刚结束、``finished`` 尚未派发完的瞬间 → 此时 ``self.process``
             已存在，直接放行——否则"中断后续跑"这类连招会像点了没反应。
        """
        for attr, label in (("process", "步骤"), ("detect_process", "单页检测")):
            proc = getattr(self, attr, None)
            if proc is not None and proc.state() != QProcess.ProcessState.NotRunning:
                return label
        if self._run_claim and self.process is None and self.detect_process is None:
            return self._run_claim
        return None

    def _acquire_run(self, what: str, *, replace: tuple = ()) -> bool:
        """领取执行权；拿不到返回 False，调用方直接 ``return``。

        三种拒绝情形：

        - 已有别的执行在跑 → 提示后拒绝（这是"不要二次执行"的正题）；
        - ``replace`` 里列出的执行在跑 → **允许顶替**。单页检测换一页重检就是
          这样：旧进程由 ``_start_detect`` 先断信号再杀，始终只有一个在跑；
        - 距上次受理不足 :data:`RUN_DEBOUNCE_MS` → 静默拒绝（连击的第二下）。
        """
        busy = self._busy_label()
        if busy and busy not in replace:
            self._toast(
                "warning", "任务进行中", f"{busy}正在执行，请等待完成后再试。"
            )
            return False
        now = time.monotonic()
        if (now - self._run_launched_at) * 1000 < self.RUN_DEBOUNCE_MS:
            return False
        self._run_claim = what
        # 立刻把按钮置灰：别等 proc.start() 之后那次 _refresh_stage_views
        self._refresh_run_buttons()
        return True

    def _mark_run_launched(self) -> None:
        """记下"进程真的起来了"——防抖窗口从这里开始计时（见 `_run_launched_at`）。

        在 ``QProcess.start()`` 之后调用。放在这里而不是受理处，是为了让
        "没能跑起来的受理"完全不占用防抖预算。
        """
        self._run_launched_at = time.monotonic()

    def _release_run(self) -> None:
        """释放执行权（进程结束 / 被中断 / 启动失败都要调）。"""
        self._run_claim = None
        self._refresh_run_buttons()

    def _refresh_run_buttons(self) -> None:
        """执行权变化后重刷按钮（不额外读盘）。"""
        self._update_run_buttons()

    def _update_run_buttons(self) -> None:
        running = self._busy_label() is not None
        # ⚠️ 聚合任务的**输入节点**（起点、产物由子任务汇集）没有可执行的东西：
        #    没有源 PDF 可提、也没有上游输入可处理。按钮留着可点只会让人以为
        #    "点了就能提取"，结果是一句找不到源文件（用户 2026-11-18 任务 0025）。
        input_node = self._input_node_mode()
        self.run_button.setEnabled(not running and not input_node)
        self.run_button.setToolTip(
            "这一步是聚合任务的输入节点：图片由子任务汇集而来，不需要执行"
            if input_node else ""
        )
        self._apply_regenerate_highlight()
        self._update_submit_button(running)

    def _input_node_mode(self) -> bool:
        """当前步骤是不是聚合任务的输入节点（判据见 manifest 同名方法）。

        ⚠️ 缓存一次（``_input_node_cached``）：``_update_run_buttons`` 在运行期
        是热路径（每 ≤200ms 一次），而判据要读任务索引 + 流程图。缓存由
        :meth:`_refresh_stage_views` 与 :meth:`set_task` 刷新。
        """
        cached = getattr(self, "_input_node_cached", None)
        if cached is not None:
            return cached
        try:
            value = bool(self._is_aggregate_input_node())
        except Exception:  # noqa: BLE001 - 判据读坏了按普通步骤处理
            value = False
        self._input_node_cached = value
        return value

    def _apply_regenerate_highlight(self) -> None:
        """本步产物过期（改了版面 / 上游又跑过）时把主按钮加粗高亮。

        与第三步「分割图片」待重新提交时的视觉语言一致：**用加粗**点明
        该动作，但**不阻止**用户先干别的——只提示，不自动重跑。
        """
        pending = self._regenerate_notice(self.current_stage()) is not None
        # ⚠️ 加粗走 setFont，别用 setStyleSheet("…{font-weight:bold}") —— 那会把
        # qfluent 按钮的整套 qss（含 hasIcon=true 的 36px 左边距）整串抹掉，
        # 图标就画到文字上了（见 desktop.ui.widgets.bold_button）
        bold_button(self.run_button, pending)
