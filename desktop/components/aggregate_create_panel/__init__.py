# -*- coding: utf-8 -*-
"""**聚合任务**创建面板（创建任务页「任务类型：聚合任务」的内容）。

## 用户口径（2026-11-17）

> 同一部书有多个 PDF 子集，每个子集作为一个任务处理；拼版之后想把所有
> 拼版后的图片组合成一个 PDF——创建一个聚合任务，选择多个子任务、选择
> 图片拼版节点，同时可以对这几个子任务进行排序。

面板三件事：

1. **选子任务**：「选择子任务…」按钮弹「选择子任务」弹窗多选
   (:class:`AggregateMemberPicker`，**搜索 + 分页的勾选表格**，与任务管理
   列表同一套观感：节点状态胶囊/匹配判据/分页控件全部复用)；已选成员进
   下方成员表格，弹窗里勾掉已有的成员即移除，新勾的按任务号追加在后面
   ——**已排好的顺序不被弹窗冲掉**；
2. **成员表格**（用户 2026-11-17 晚：列表升级为表格，操作全在行内）：
   列 = 序号 / 任务名称 / **任务节点** / 操作——
   - **任务节点**：该子任务**已经完成**的节点（只读展示，不含「提取图片」）
     ——它是"起始节点能选什么"的依据，一眼看到每个子任务各自跑到了哪；
     列宽按**内容实测**放宽（最长那行的节点名全显示，不再裁字）；
   - **操作**：行内「详情 / 上移 / 下移 / 删除」（详情＝**非模态预览窗**，
     不再跳走创建页；顺序有意义，决定合并页序）；
   - 表格上方「选择子任务…」随时追加（同一个弹窗）。
3. **起始节点**（用户 2026-11-17 本轮：checkbox 列表 + **单选**）：
   候选 = 所选子任务里**任意一个已经完成**的任务节点（逐成员取
   :meth:`store.completed_aggregate_stages`，再用
   :func:`desktop.steps.aggregate.any_member_stages` 求**并集**；用户
   2026-11-18 口径，取代早先"每个成员都完成过"的交集）。全体子任务共用这
   一个节点，选它就等于选"流程从哪开始"。
   ⚠️ 并集的代价必须让用户看见：选中的节点有成员没跑过 ⇒ 汇集时缺它的
   页面，所以候选下方**点名**这些子任务（:func:`missing_members`）。
   ⚠️ 勾选是**单选**：勾一个别的自动灭；点掉当前唯一勾选不生效（不可能
   出现"没有起始节点"）。还没选成员、或并集为空时兜底列出全部候选
   （提交时 ``store`` 仍会校验）。
4. **流程**：起始节点变化 ⇒ 流程编辑器换到新派生图（开始节点自动变化）。

流程编辑器常驻（与普通创建页同一条纪律）：展示
:func:`desktop.steps.aggregate.derive_aggregate_diagram` 的派生图，用户可以
继续拖改；改过就随 ``submitted`` 一起交出去，没改过传 ``None``（store 落
派生图本身）。

⚠️ 起始节点变化会**整体重建编辑器**（派生图变了，旧图不能原地改）；
用户在旧根下做的流程编辑随之丢弃——起始节点是流程的根，根换了的
"自定义"没有意义。同理，成员集合变化导致候选集变化时，起始节点若不在
新候选里就自动落到新候选的第一个（见 :meth:`_sync_candidates`）。

⚠️ 2026-11-22 起按职责拆成子包：常量 ``constants``、选择弹窗 ``picker``、
起始节点 ``start_stage``、成员表格 ``members``、主体 ``panel``。本
``__init__`` 只做重导出——既有 ``from desktop.components.aggregate_create_panel
import X`` 全部不变，子模块之间不要反过来导入本包（会形成循环）。
"""

from desktop.components.aggregate_create_panel.constants import (
    DEFAULT_START_STAGE,
    MEMBER_HEADER_HEIGHT,
    MEMBER_PAGE_SIZE,
)
from desktop.components.aggregate_create_panel.panel import AggregateCreatePanel
from desktop.components.aggregate_create_panel.picker import AggregateMemberPicker

__all__ = [
    "AggregateCreatePanel",
    "AggregateMemberPicker",
    "DEFAULT_START_STAGE",
    "MEMBER_HEADER_HEIGHT",
    "MEMBER_PAGE_SIZE",
]
