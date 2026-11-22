# -*- coding: utf-8 -*-
"""拼版版面控制器（模块二）的 Mixin 装配。"""

from __future__ import annotations

from desktop.pages.taskdetail.imposition_layout.compose import ComposeMixin
from desktop.pages.taskdetail.imposition_layout.layout_ops import LayoutOpsMixin
from desktop.pages.taskdetail.imposition_layout.persist import PersistMixin
from desktop.pages.taskdetail.imposition_layout.preview import PreviewMixin


class ImpositionLayoutMixin(
    LayoutOpsMixin, PreviewMixin, PersistMixin, ComposeMixin,
):
    """拼版版面操作（模块二）：旋转/复位、版面落盘、防抖后台合成。"""
