# -*- coding: utf-8 -*-
"""任务详情页的「图片拼版」共享基元与 Mixin 装配。

流程条上的「图片拼版」是**虚线可选节点**（``desktop.components.step_bar``）。
它牵涉**两个判据，各管一件事、互不替代**（2026-10-05 逐层查证业务流程后定，
2026-10-22 移除 area 后简化为两条）：

1. **在不在流程里** ← **本任务的流程图**。图上画了「图片拼版」就有这一格
   （:meth:`ImpositionBaseMixin._imposition_node_visible`）。
2. **要不要真跑** ← **拼版面板底部的开关**（:meth:`imposition_active`
   只看勾没勾，那是"用户意图"）。开关在 ① 不满足时**置灰并写明原因**。

⚠️ 2026-10-22 起 **area 概念彻底移除**：检测文本框后永远逐框裁图，
半幅页天然产出成对的 ``-l`` / ``-r``，拼版不再需要"区域模式 = 左右分开"
这个业务前提；没有检测步骤时拼整图照样能拼。

按操作逻辑拆成三个文件（后续可由不同 agent 分头维护，互不影响）：

- **本包** ``ImpositionBaseMixin``：两个模块都要用的**共享基元**——
  节点可见性（查流程图）、
  拼版文档读写（``drafts/imposition.json``）、
  源图清单与「拼版生效」判定、第四步取图切换（``print_source_dir``）、
  视图灌装、详情进出与切任务复位；
- **``imposition_pages.ImpositionPagesMixin``**（模块一「选择拼版」）：
  启用开关、弹窗加页、删页/页序/清空；
- **``imposition_layout.ImpositionLayoutMixin``**（模块二「拼版操作」）：
  旋转/复位、版面落盘、防抖后台合成、状态行。

⚠️ 拼版本身**不是** STAGES 里的一步：runs.json / 阶段面板机制一概不感知它，
执行按钮组在拼版详情里整组隐藏。

2026-11-22 起本文件再按职责拆成子包（对外 ``from desktop.pages.taskdetail.
imposition import X`` 完全不变）：``node_visibility``（节点三态）、
``document``（文档读写/作用域）、``sources``（源图与取图来源）、
``detail``（视图与详情）、``print_source``（第四步刷新）、``helpers``（小工具）、
``mixin``（装配）。
"""

from desktop.pages.taskdetail.imposition.helpers import _rect_of
from desktop.pages.taskdetail.imposition.mixin import (
    ImpositionBaseMixin, ImpositionMixin,
)

__all__ = ["ImpositionMixin", "ImpositionBaseMixin"]
