# -*- coding: utf-8 -*-
"""任务详情页的「参数暂存」：用户改过、但还没执行的阶段参数，切走也还在。

问题：进入某阶段时表单按**最近一次执行参数**回填（``history.py``）。用户改完
参数却没执行就切阶段、切任务或关程序，改动全丢——再回来看到的还是上一次执行
的值，等于白调一遍（尤其第四步参数多）。

做法：
- 面板把"用户改了参数"通过 ``StagePanel.param_edited`` 报上来（程序化回填由
  面板自己的 ``_applying`` 挡住，不会误报）；
- 这里按 400ms 防抖写 ``tasks/<任务号>/drafts/<阶段>.json``（``store.DraftMixin``）；
- 进入阶段回填时的优先级是 **暂存 > 最近一次执行参数 > 内置默认**，
  实现在 ``HistoryMixin._restore_stage_params``。

为什么参数非法时不覆盖暂存：颜色/边距是逐字符输入的，"0,0" 这种半截状态
``get_args()`` 会抛 ValueError；此时保留上一份**有效**暂存，比写进去一份
用不了的值更合理（面板本来也会在说明行提示参数不合法）。
"""

from __future__ import annotations

from functools import partial

from PySide6.QtCore import QTimer

from desktop.store import STAGES


class ParamDraftMixin:
    """依赖宿主提供：store、task_id、control_stack。"""

    # 编辑防抖：边距/颜色/跳过页都是逐字符输入，每敲一下就写盘没必要
    _DRAFT_DEBOUNCE_MS = 400

    def _install_draft_hooks(self) -> None:
        """给每个阶段面板接上「用户改了参数」→ 防抖暂存。"""
        self._draft_dirty: set[int] = set()
        self._draft_timer = QTimer(self)
        self._draft_timer.setSingleShot(True)
        self._draft_timer.setInterval(self._DRAFT_DEBOUNCE_MS)
        self._draft_timer.timeout.connect(self._flush_param_drafts)
        for index in range(self.control_stack.count()):
            host = self.control_stack.widget(index)
            register = getattr(host, "add_created_hook", None)
            if callable(register):
                # 惰性宿主（第四步面板）：⚠️ 这里**不能**读面板的任何属性，
                # 属性转发会立刻把面板建出来、惰性就白做了。挂个回调等它建好。
                register(partial(self._connect_panel_draft, index))
            else:
                self._connect_panel_draft(index, host)

    def _connect_panel_draft(self, index: int, panel) -> None:
        """给某个阶段面板接上「用户改了参数」→ 防抖暂存。"""
        panel.param_edited.connect(partial(self._on_param_edited, index))

    def _on_param_edited(self, index: int) -> None:
        """某阶段有改动：记下待写并重启防抖计时。"""
        self._draft_dirty.add(index)
        self._draft_timer.start()

    def _flush_param_drafts(self) -> None:
        """把待写的暂存落盘（切阶段/切任务/退出前也要调，别丢最后 400ms 的输入）。"""
        dirty, self._draft_dirty = self._draft_dirty, set()
        for index in sorted(dirty):
            self.save_stage_draft(index)

    def save_stage_draft(self, index: int) -> bool:
        """暂存某阶段当前表单值；参数非法/没有任务时返回 False（不覆盖旧暂存）。"""
        if not self.task_id:
            return False
        panel = self.control_stack.widget(index)
        try:
            params = panel.get_args()
        except Exception:  # 颜色/边距填到一半：保留上一份有效暂存
            return False
        return self.store.save_draft(self.task_id, STAGES[index], params)
