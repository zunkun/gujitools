# -*- coding: utf-8 -*-
"""拼版页管理控制器（模块一）的 Mixin 装配。"""

from __future__ import annotations

from desktop.pages.taskdetail.imposition_pages.page_ops import PageOpsMixin
from desktop.pages.taskdetail.imposition_pages.picker import PickerMixin
from desktop.pages.taskdetail.imposition_pages.state import PagesStateMixin
from desktop.pages.taskdetail.imposition_pages.thumbnails import ThumbnailsMixin


class ImpositionPagesMixin(
    PagesStateMixin, PickerMixin, PageOpsMixin, ThumbnailsMixin,
):
    """拼版页管理（模块一）：启用开关、加页、删页、清空。"""
