# -*- coding: utf-8 -*-
"""「拼图」独立模块页（= 图片拼版）。

**复用共用组件**：

- 输入：:class:`~desktop.steps.source_zone.SourceZone`——页头下方横跨整幅的
  **大输入区**（拖一批图片、拖一个图片文件夹、或点选），与"图片提取 / 去底色"
  是同一块控件；
- 执行：:class:`~desktop.steps.kernel.StepKernel` + ``CallableJob``——
  拼版不是 CLI 命令，所以走"纯函数 job"这条路（内核同样只认"输出目录"）；
- 界面：``ImpositionViewWidget``（左页清单 + 右拖拽画布）、
  ``ImpositionPanel``（右侧控制面板）、``ImpositionPickerDialog``（选图弹窗）；
- 规则：``desktop.services.imposition`` 是**纯函数模块**（无 Qt），版面默认
  摆放、自动拼版、合成紧裁全部直接用；
- 元数据：``desktop/steps/spec.py`` 的 imposition 条目（标题/副标题/过滤串/
  后缀/输出名）。

**独立**：不依赖任务目录、不依赖 ``TaskDetailPage`` 的拼版控制器。用户选了
一批图片作为「源清单」，模块自己维护一份 ``doc``（内存 + 可导出），
点「导出成品」把每页合成为**白底** PNG（2026-10-13 用户：singletask 导出的
就是交付物，不要透明底；任务流程的 ``stages/imposition`` 仍默认透明底）。

**与去底色独立页的衔接**（2026-10-13 用户）：源图来自带
``guji_singletask_rembg`` 标记的导出目录时（``services.rembg_export``），
先把白底图转成**透明底副本**（singletask 缓存区，原图不动）再拼版；
没有标记的目录/散图原样直用。

⚠️ 与任务流程的差别（有意为之）：任务流程里拼版的产物供第四步 PDF排版使用，
且「启用开关」决定取图来源；单文件模式下没有下游，所以这里把面板里的
「启用开关」隐掉，只留版面操作与导出。

**面板能力与任务流程对齐**（2026-10-13 用户）：单图页「新增图片」
（append 弹窗挑 1 张并进当前页，``append_item_to_page`` 摆放）、
「删除选中图片」（选中才出现；本页最后一张删除前先确认）、整体旋转/
选中图旋转（停手 250ms 统一提交）——语义逐条与任务流程的拼版步骤一致。

2026-11-22 起按职责拆成子包：常量/落点在 ``constants`` / ``paths``，
页面能力按「选源 / 页面操作 / 版面 / 预览 / 缩略图 / 界面 / 导出」分到
各 ``mixin_*`` 子模块；本 ``__init`` 只负责组装页面类并重导出既有名字
（``from desktop.modules.imposition.page import X`` 保持不变）。

⚠️ 子模块之间只互相 import，不要反过来导入本包（会形成循环）。
"""

from __future__ import annotations

from pathlib import Path

import PySide6.QtCore as QtCore

from desktop.components.imposition import ImpositionPickerDialog
from desktop.modules.base import ModulePage
from desktop.services.imposition import normalize_doc

from .constants import (
    EDITED_DIRNAME,
    EDIT_COMMIT_DEBOUNCE_MS,
    THUMB_REFRESH_DEBOUNCE_MS,
    UPLOAD_DIRNAME,
    _SPEC,
)
from .mixin_export import ExportMixin
from .mixin_layout import LayoutMixin
from .mixin_pages import PagesMixin
from .mixin_preview import PreviewMixin
from .mixin_sources import SourcesMixin
from .mixin_thumbs import ThumbsMixin
from .mixin_ui import UiMixin
from .paths import _chosen_items, _page_overrides, edited_page_dir, uploaded_page_dir

__all__ = ["ImpositionModulePage"]


class ImpositionModulePage(
    SourcesMixin,
    PagesMixin,
    LayoutMixin,
    PreviewMixin,
    ThumbsMixin,
    UiMixin,
    ExportMixin,
    ModulePage,
):
    """拼图模块页：选图 → 自动/手动拼版 → 调整版面 → 导出成品。"""

    TITLE = _SPEC.title
    SUBTITLE = _SPEC.subtitle

    #: 拼版视图 + 控制面板需要更宽的控制列（沿用详情页拼版档位）
    CONTROL_MIN_WIDTH = 340
    CONTROL_MAX_WIDTH = 460

    def __init__(self, parent=None):
        """先建骨架，再补「选图 / 自动拼版 / 导出」这条操作链。"""
        self._sources: list[str] = []
        self._doc: dict = normalize_doc({})
        self._out_dir: Path | None = None
        #: 去底色导出目录衔接的**代际闸**（见 _prepare_sources）：换源/清空
        #: 即换新对象，迟到的副本转换回调整批丢弃。
        self._rembg_prep_batch: object | None = None
        #: 最近一次导出的页数（job 在 worker 线程里写、主线程读，只搬一个整数）
        self._export_result: dict = {}
        #: 左列每页的缩略图（QPixmap 列表，页序；未就绪处是 None）
        self._page_thumbs: list = []
        #: 预览弹窗（懒建，与任务流程的拼版步骤同一个控件）
        self._zoom_dialog = None
        super().__init__(parent)
        # 版面改动 → 防抖后单页重合成左列缩略图（见 _on_items_changed）
        self._thumb_dirty_pages: set[int] = set()
        self._thumb_timer = QtCore.QTimer(self)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.setInterval(THUMB_REFRESH_DEBOUNCE_MS)
        self._thumb_timer.timeout.connect(self._refresh_dirty_page_thumbs)
        # 旋转组件（整体/选中图）停手提交的防抖（见 EDIT_COMMIT_DEBOUNCE_MS）
        self._rotate_commit_timer = QtCore.QTimer(self)
        self._rotate_commit_timer.setSingleShot(True)
        self._rotate_commit_timer.setInterval(EDIT_COMMIT_DEBOUNCE_MS)
        self._rotate_commit_timer.timeout.connect(self._commit_rotation_edit)
        self.status("尚未选择图片")

    def _picker_dialog(self, *args, **kwargs):
        """按名取 ``ImpositionPickerDialog``（自测把替身打在 page 模块命名上）。"""
        return ImpositionPickerDialog(*args, **kwargs)
