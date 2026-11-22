# -*- coding: utf-8 -*-
"""流程的节点与边：:class:`FlowEdge` / :class:`StageSlot`。"""

from __future__ import annotations

from dataclasses import dataclass

from desktop.steps import ports


@dataclass(frozen=True)
class FlowEdge:
    """一条连线：``supplier`` 阶段的 ``port`` 端口产物喂给 ``consumer`` 阶段。

    ``condition`` 为 ``None`` 表示**无条件边**（默认路径）；否则是条件名
    （如 ``"imposition"``），解析时按上下文标志位决定走不走它。
    """

    supplier: str
    consumer: str
    port: str
    condition: str | None = None


@dataclass(frozen=True)
class StageSlot:
    """**界面槽位**：BPMN 节点折叠到界面步骤条上的一格。

    ⚠️ 为什么要这层折叠——BPMN 的节点是**运行阶段**，界面步骤条上的格子是
    **界面步骤**，两者不是一一对应：

    - ``detect_submit`` 是第二步「检测文本框」面板上的第二个动作（提交裁图），
      进度也显示在第二步 ⇒ 折叠进 ``detect`` 那一格，不单独占格；
    - ``imposition`` 是**条件伪步骤**（``StepSpec.role == "optional"``），
      流程里有它，但界面上是否出现由运行态决定（第三步区域模式为 1 才出现）。

    两个下标各管一件事，别混：

    - ``bar_index``：在**步骤条上**的显示次序（自定义流程换顺序就变它）；
    - ``stack_index``：在 ``control_stack`` / ``preview_stack`` 里的页号。
      真实步骤按流程顺序排名，可选节点统一排在真实步骤之后（沿用既有的
      「伪步骤占最后一位」约定），这样两个栈的**建页顺序不用动**。
    """

    step: str
    stage: str
    optional: bool = False
    bar_index: int = 0
    stack_index: int = 0
    #: 这一格对应的**节点实例 id**（B 方案，2026-10-17）。
    #:
    #: 同类型步骤（图片拼版 / 检测文本框 / 图片去底色 / PDF排版…）可以有**多个
    #: 节点**，每个节点各占一格、各自独立（各自参数与产物落点）。这个字段把
    #: 界面格接回图上那个**具体节点**——界面据此寻址（``node_input`` /
    #: ``node_output`` / 按节点暂存参数）。
    #:
    #: 空串 = 这一格没有对应节点（旧模型 ``FlowDefinition`` 投影出来的槽位、
    #: 或"图上画了但没功能"的灰节点）——调用方一律先判空再按节点寻址，
    #: 退回阶段粒度的旧路径。
    node_id: str = ""
    #: 这一格**有没有接上真实功能**（2026-10-05）。
    #:
    #: ``False`` = 用户在流程图上画了一个本程序**还没有对应实现**的节点
    #: （例如 bpmn.io 里随手加的「OCR 识别」）。这类节点**不再被静默丢掉**：
    #: 它在步骤条上占一格、显示为**灰节点**、标着"未接入"，点它会告诉用户
    #: 怎么接上（改名成已有步骤名）或怎么删掉。
    #:
    #: ⚠️ 之前它们被 ``continue`` 直接跳过 ⇒ 图上画了、界面上却找不到
    #: （"流程节点不能完全映射"最明显的一条）。
    mapped: bool = True
    #: 该格在步骤条上的**显示名**（只有未接入的节点用它；已接入的仍走
    #: ``ports.stage_label``，不另写一份文案）。
    name: str = ""

    @property
    def label(self) -> str:
        """步骤条上显示的中文名（已接入的走 :func:`ports.stage_label`）。"""
        if not self.mapped:
            # 未接入的节点没有官方中文名，显示用户自己在图上写的那个
            return self.name or self.step
        return ports.stage_label(self.stage)
