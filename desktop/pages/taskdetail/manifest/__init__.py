# -*- coding: utf-8 -*-
"""任务详情页的页面清单控制器：manifest 维护、缩略图/尺寸提供、页面增删。

2026-11-22 按职责拆成子包（只搬不改）：
- widget.py
- sync.py
- thumbs.py
- pages.py
- aggregate.py
- source_prompt.py
- source_pick.py
- reconcile.py
"""

from desktop.pages.taskdetail.manifest.widget import (
    PageListMixin,
)
from desktop.pages.taskdetail.manifest.sync import (
    ManifestSyncMixin,
)
from desktop.pages.taskdetail.manifest.thumbs import (
    ManifestThumbsMixin,
    _ENTRY_THUMB_WARM_LIMIT,
)
from desktop.pages.taskdetail.manifest.pages import (
    ManifestPagesMixin,
)
from desktop.pages.taskdetail.manifest.aggregate import (
    ManifestAggregateMixin,
)
from desktop.pages.taskdetail.manifest.source_prompt import (
    ManifestSourcePromptMixin,
    _MISSING_INPUT_TEXT,
    _set_tool_highlight,
)
from desktop.pages.taskdetail.manifest.source_pick import (
    ManifestSourcePickMixin,
)
from desktop.pages.taskdetail.manifest.reconcile import (
    reconcile_page_files,
)

__all__ = ["PageListMixin", "ManifestSyncMixin", "ManifestThumbsMixin", "ManifestPagesMixin", "ManifestAggregateMixin", "ManifestSourcePromptMixin", "ManifestSourcePickMixin", "reconcile_page_files"]
