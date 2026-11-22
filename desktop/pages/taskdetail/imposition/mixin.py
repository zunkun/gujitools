# -*- coding: utf-8 -*-
"""拼版共享基元与 Mixin 装配。"""

from __future__ import annotations

from desktop.pages.taskdetail.imposition.detail import DetailMixin
from desktop.pages.taskdetail.imposition.document import DocumentMixin
from desktop.pages.taskdetail.imposition.node_visibility import NodeVisibilityMixin
from desktop.pages.taskdetail.imposition.print_source import PrintSourceMixin
from desktop.pages.taskdetail.imposition.sources import SourcesMixin
from desktop.pages.taskdetail.imposition_layout import ImpositionLayoutMixin
from desktop.pages.taskdetail.imposition_pages import ImpositionPagesMixin


class ImpositionBaseMixin(
    NodeVisibilityMixin,
    DocumentMixin,
    SourcesMixin,
    DetailMixin,
    PrintSourceMixin,
):
    """拼版共享基元：节点可见性、文档读写、取图切换、详情进出。

    依赖宿主页面提供：store/task_id、control_stack、step_bar、
    _select_stage()、_set_stage_status()、_toast()、log_view。
    """


class ImpositionMixin(ImpositionPagesMixin, ImpositionLayoutMixin, ImpositionBaseMixin):
    """「图片拼版」节点控制器 = 模块一（页管理） + 模块二（版面/合成） + 基元。

    方法查找顺序：模块一 → 模块二 → 共享基元；三个文件互不 import，
    只经 ``self`` 在组合后的宿主页面上协作。
    """


__all__ = ["ImpositionMixin", "ImpositionBaseMixin"]
