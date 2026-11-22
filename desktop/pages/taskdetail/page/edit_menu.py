# -*- coding: utf-8 -*-
"""任务详情页「编辑」菜单按当前阶段分派（删除/插入/下载/打印）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any


class EditMenuMixin:
    """「编辑」菜单：按当前阶段分派 can_edit_* / edit_* 四对方法。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _delete_selected_box: Any
        _input_node_mode: Any
        _insert_print_images: Any
        _on_imposition_add_requested: Any
        _on_imposition_batch_delete: Any
        _toast: Any
        can_delete_selected_print: Any
        current_stage: Any
        delete_selected_print: Any
        detect_viewer: Any
        extract_input_viewer: Any
        extract_result_viewer: Any
        imposition_view: Any
        rembg_viewer: Any
        task_id: Any

    # ---------------------------------------------------------------- 「编辑」菜单
    #
    # 菜单只认 ``can_edit_* / edit_*`` 四对方法（见 ``desktop/ui/menu.py``）。
    # 详情页一个实例承载五个预览区，所以这里按**当前阶段**分派：PDF排版四项全开，
    # 拼版给删除/插入，其余步骤给下载/打印（检测的“删除选中”= 删选中框）。
    def _edit_image_path(self) -> Path | None:
        """当前阶段能下载/打印的**真实图片文件**；虚拟页（PDF 渲染页）返回 None。"""
        stage = self.current_stage()
        if stage == "detect":
            return self.detect_viewer.current_path()
        if stage == "rembg":
            text = self.rembg_viewer.current_display_path()
            return Path(text) if text else None
        if stage == "extract":
            if self._input_node_mode():
                # 聚合任务的提取起点：屏上是只读图片清单，当前页就是磁盘上那张图
                path = self.extract_input_viewer.current_path()
                return Path(path) if path else None
            return self.extract_result_viewer.current_display_path()
        return None

    def _edit_image_toast(self, kind: str, title: str, content: str) -> None:
        self._toast(kind, title, content)

    def can_edit_delete_selected(self) -> bool:
        stage = self.current_stage()
        if stage == "print":
            return self.can_delete_selected_print()
        if stage == "imposition":
            return bool(self.imposition_view.checked_pages())
        if stage == "detect":
            return self.detect_viewer.selected_index() >= 0
        return False

    def edit_delete_selected(self) -> None:
        stage = self.current_stage()
        if stage == "print":
            self.delete_selected_print()
        elif stage == "imposition":
            self._on_imposition_batch_delete()
        elif stage == "detect":
            self._delete_selected_box()

    def can_edit_insert_images(self) -> bool:
        stage = self.current_stage()
        if stage in ("print", "imposition"):
            return bool(self.task_id)
        return False

    def edit_insert_images(self) -> None:
        stage = self.current_stage()
        if stage == "print":
            self._insert_print_images()
        elif stage == "imposition":
            self._on_imposition_add_requested()
