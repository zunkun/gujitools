# -*- coding: utf-8 -*-
"""任务详情页：顶部步骤条 + 左侧多标签预览 + 右侧阶段控制面板。

预览区按阶段组织：
- extract：**单缩略图**预览——左栏是 PDF 每页一份缩略图，切到某页时
  该页的提取产物已存在就显示产物，没有就后台单页提取落盘
  （``stages/extract``，与批量提取同一条实现）后显示（用户 2026-10-09：
  不再分「PDF 预览 | 提取结果」双标签）；
- detect：图片预览，叠加显示每张图的检测框位置；
- rembg：原图 / 去底结果对比；
- print：输出 PDF 预览。

本文件只保留页面骨架（任务切换、阶段切换、状态刷新），
其余职责按功能分文件（均位于 desktop/pages/taskdetail/）：
- view.DetailViewMixin       UI 组装（头部/步骤条/预览区/控制列/日志）
- manifest.PageListMixin     页面清单、缩略图、页面增删
- history.HistoryMixin       历史执行配置回填（暂存优先）
- params_draft.ParamDraftMixin 参数暂存（改过没执行也不丢）
- submit.SubmitMixin         检测提交控制器与按钮状态
- print_list.PrintListMixin  第四步待打印列表
- runner.StageRunnerMixin    阶段执行（worker 子进程编排）
- detect.DetectMixin         detect 检测控制
- rembg_live.RembgLiveMixin  第三步改参数/翻页时只重算当前页（只写预览草稿）
- imposition.ImpositionMixin 流程条「图片拼版」可选节点
  （共享基元 imposition.py + 模块一 imposition_pages.py「选择拼版」
  + 模块二 imposition_layout.py「拼版操作」）

2026-11-22 按职责拆成子包（只搬不改）：
- widget.py
- task_switch.py
- nodes.py
- edit_menu.py
- stage_switch.py
- stage_state.py
- run_control.py
- page_preview.py
- lifecycle.py
- constants.py
"""

from desktop.pages.taskdetail.page.widget import (
    TaskDetailPage,
    _ARROW_OCCUPIED,
    _arrow_free_to_navigate,
    _stage_preview_attr,
)
from desktop.pages.taskdetail.page.task_switch import (
    TaskSwitchMixin,
)
from desktop.pages.taskdetail.page.nodes import (
    NodeIndexMixin,
)
from desktop.pages.taskdetail.page.edit_menu import (
    EditMenuMixin,
)
from desktop.pages.taskdetail.page.stage_switch import (
    StageSwitchMixin,
)
from desktop.pages.taskdetail.page.stage_state import (
    StageStateMixin,
)
from desktop.pages.taskdetail.page.run_control import (
    RunControlMixin,
)
from desktop.pages.taskdetail.page.page_preview import (
    PagePreviewMixin,
)
from desktop.pages.taskdetail.page.lifecycle import (
    PageLifecycleMixin,
)
from desktop.pages.taskdetail.page.constants import (
    INPUT_NODE_POLL_MS,
)

__all__ = ["TaskDetailPage", "TaskSwitchMixin", "NodeIndexMixin", "EditMenuMixin", "StageSwitchMixin", "StageStateMixin", "RunControlMixin", "PagePreviewMixin", "PageLifecycleMixin", "INPUT_NODE_POLL_MS"]
