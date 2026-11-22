# -*- coding: utf-8 -*-
"""任务索引相关的常量：运行阶段清单与界面文案。

从 ``desktop/store/tasks.py`` 拆出（2026-11-22）：本文件只放常量，不做任何
读写。真源仍是 ``desktop.steps.spec`` / ``desktop.steps.ports``。
"""

from __future__ import annotations

from typing import cast

from desktop.steps import ports
from desktop.steps.spec import FLOW_STAGES, OPTIONAL_STEPS, StepSpec, spec_by_key

#: 默认流程的四个步骤（顺序即执行顺序）。
#:
#: ⚠️ **这里不再是独立的一份清单**：它是 ``desktop.steps.spec.SPECS`` 里
#: ``role == "stage"`` 的派生结果。加/删一步只需改 spec，本文件自动跟着变。
#: （以前这里是第二份硬编码清单，加一步要改两处，还容易漏。）
STAGES = FLOW_STAGES

# ⚠️ 这些是**界面文案**（步骤条/面板标题/toast/日志共用一份）：有中文就不再附
# 英文键名 —— 用户口径「四个步骤有中文，英文就不要出现」。
#: ⚠️ **真源是 :func:`desktop.steps.ports.stage_label`**，本表只是它的派生
#: （多带 ``detect_submit``：它不是独立步骤，却是真实的运行阶段，worker 会跑
#: 它、进度与日志都要有名字）。别在这里另写一句中文
#: ——BPMN 流程图上的节点名走的是同一个函数，两边不一致就会出现"图上两个
#: 『检测文本框』"。
STAGE_LABELS = {key: ports.stage_label(key) for key in STAGES}
STAGE_LABELS["detect_submit"] = ports.stage_label("detect_submit")

# 列表里的阶段短名（步骤条/表格空间有限，用 2~3 字表达）
STAGE_SHORT = {key: cast(StepSpec, spec_by_key(key)).short_name() for key in STAGES}

# ------------------------------------------------------------ 流程条的可选节点
#: 「图片拼版」**伪步骤**：流程条上的虚线可选节点，位于第三步（图片去底色）
#: 与第四步（PDF排版）之间，图上画了就会出现。
#: 用户可以选择它（启用）也可以不选择；节点详情当前为占位（不参与任何执行
#: 链路，STAGES/runs.json/阶段面板等机制一律不感知它）。
#:
#: ⚠️ 它**有自己的独立模块页**（``desktop/modules/imposition``）——"进不进流程"
#: 和"有没有独立功能"是两件事，这也是 ``StepSpec.role`` 要分
#: ``stage`` / ``optional`` 的原因。
IMPOSITION_STAGE = OPTIONAL_STEPS[0]
IMPOSITION_LABEL = cast(StepSpec, spec_by_key(IMPOSITION_STAGE)).stage_name()
#: 🗑 **已删**：``IMPOSITION_INDEX``（= ``len(STAGES)``，即"拼版占第 5 位"）。
#:
#: 它是 BPM 改造**之前**的固定顺序口径：BPM 化后拼版插在哪一格由流程图决定
#: （``FlowDiagram.optional_after`` / 槽位表的 ``bar_index``），这个常量既没人
#: 用（``page.py`` 只 import 它、没有任何实际引用）又和真源矛盾——留在那儿
#: 就是给下一个人留一个"看起来能用"的默认流程假设。查格序一律走
#: ``TaskDetailPage.bar_index_of_step(IMPOSITION_STAGE)``。

# 「图片拼版」**不是 STAGES 里的一步**（它是可选节点），但任务列表的「节点
# 状态」胶囊会按任务详情里的启用情况把它插进去，所以上面两张文案表都得有它。
# ⚠️ 取值仍走 ``stage_name()`` / ``short_name()``，不另写一份中文。
STAGE_LABELS[IMPOSITION_STAGE] = IMPOSITION_LABEL
STAGE_SHORT[IMPOSITION_STAGE] = cast(StepSpec, spec_by_key(IMPOSITION_STAGE)).short_name()

#: 运行阶段 → 它归属的**界面步骤**（值取 STAGES 里的一项）。
#:
#: ⚠️ 「分割图片」（detect_submit）不是独立步骤，而是第二步 detect 面板上的
#: 动作：它的进度必须显示在第二步。有了这张表，界面才谈得上"只有当前这一步的
#: 进度才上屏"（详见 desktop/pages/taskdetail/runner.py::_progress_belongs_here）。
STAGE_STEP = ports.STAGE_STEPS
"""运行阶段 → 界面步骤（**别名** ``ports.STAGE_STEPS``，不是第二份）。

⚠️ 此前这里是一份手写字典，与 :data:`desktop.steps.ports.STAGE_STEPS` 同源却
不同步：漏了 ``imposition``、少了一个键就静默靠 ``.get(s, s)`` 兜底。今天两份
逐值相同只是巧合——`ports` 那份是真源（``bpmn_diagram`` / ``flow`` / ``tasks``
都用它），store 属于下层却反向持有一份，属于层次倒挂。现在直接别名，加/改一步
只改 :data:`desktop.steps.spec.SPECS` 一处。
"""
