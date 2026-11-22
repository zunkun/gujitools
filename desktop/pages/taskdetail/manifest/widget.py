# -*- coding: utf-8 -*-
"""任务详情页页面清单控制器的装配点（由 ``manifest.py`` 拆出，只搬不改）。

- sync：清单与输入目录对齐、聚合起点判定
- thumbs：页缩略图、尺寸、编辑回写后的刷新
- pages：页面增删 / 插入 / 打开目录
- aggregate：聚合任务输入汇集与刷新
- source_prompt：缺源提示层、入口动作高亮
- source_pick：选择/替换源文件、查重与产物复位
- reconcile：清单按 stem 对齐到目录实际文件
- thumbs 里定义 ``_ENTRY_THUMB_WARM_LIMIT``，``source_prompt`` 里定义
  ``_set_tool_highlight``。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, cast

from .aggregate import ManifestAggregateMixin
from .pages import ManifestPagesMixin
from .source_pick import ManifestSourcePickMixin
from .source_prompt import ManifestSourcePromptMixin
from .sync import ManifestSyncMixin
from .thumbs import ManifestThumbsMixin


class PageListMixin(ManifestSyncMixin, ManifestThumbsMixin, ManifestPagesMixin, ManifestAggregateMixin, ManifestSourcePromptMixin, ManifestSourcePickMixin):
    """页面清单控制器：清单维护、缩略图/尺寸提供、页面增删。"""
