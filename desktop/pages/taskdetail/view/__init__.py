# -*- coding: utf-8 -*-
"""任务详情页的视图构建：头部/步骤条/预览区/控制列/日志的 UI 组装。

只做控件创建与信号连接，业务动作全部委托给宿主页面的其他 Mixin。

视觉结构（自上而下）：
1. 页头卡片：返回 + 任务名（含任务编号）+ 源文件标签 + 流程编辑 + 选 PDF +
   插入图片/文件夹；
2. 步骤条卡片：四步流程与状态；
3. 主体：左侧预览卡片（自适应）+ 右侧参数卡片（固定宽度区间）；
4. 底部：执行日志状态条（常驻一行，点击唤出不挤压布局的日志浮层），
   ���**最右端是「打开任务数据目录」**（用户 2026-10-06 从页头移来）。
"""

from __future__ import annotations

from desktop.pages.taskdetail.view.controls import DetailControlsMixin
from desktop.pages.taskdetail.view.header import DetailHeaderMixin
from desktop.pages.taskdetail.view.lazy_host import LazyPanelHost
from desktop.pages.taskdetail.view.panels import DetailPanelsMixin
from desktop.pages.taskdetail.view.previews import DetailPreviewMixin
from desktop.pages.taskdetail.view.step_bar import DetailStepBarMixin

__all__ = [
    "LazyPanelHost",
    "DetailViewMixin",
]


class DetailViewMixin(
    DetailHeaderMixin,
    DetailStepBarMixin,
    DetailPreviewMixin,
    DetailPanelsMixin,
    DetailControlsMixin,
):
    """依赖宿主页面提供的方法：_on_back、_select_stage、各预览联动槽、
    current_stage()、_update_run_buttons() 等。"""
