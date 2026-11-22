# -*- coding: utf-8 -*-
"""独立拼图页的预览区/控制列搭建与编辑菜单（从原 ``page.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path

import PySide6.QtWidgets as QtWidgets
from qfluentwidgets import FluentIcon as FIF, PrimaryPushButton, PushButton

from desktop.components.imposition import (
    ImpositionPanel,
    ImpositionViewWidget,
)
from desktop.components.progress_row import ProgressRow
from desktop.steps import StepKernel, callable_job
from desktop.ui.widgets import Card

from .constants import _SPEC


class UiMixin:
    """左右两栏控件搭建与「编辑」菜单入口。"""

    # ------------------------------------------------------------------ 预览
    def _build_preview(self) -> ImpositionViewWidget:
        """左栏：拼版页清单 + 操作画布（复用现成装配控件）。"""
        self.view = ImpositionViewWidget()
        self.view.add_requested.connect(self._on_add_pages)
        self.view.page_remove_requested.connect(self._on_release_page)
        self.view.page_selected.connect(lambda _i: self._refresh_panel())
        self.view.slot_selected.connect(lambda _slot: self._refresh_panel())
        self.view.items_changed.connect(self._on_items_changed)
        self.view.page_reorder_requested.connect(self._on_reorder)
        # 左列右键：上移/下移、向前/向后插入拼版（2026-11-16，与任务流程同款）
        self.view.page_move_requested.connect(self._on_move)
        self.view.page_insert_requested.connect(self._on_insert)
        self.view.pages_batch_delete_requested.connect(self._on_batch_delete)
        # 双击图片 / 右键编辑：统一打开整页编辑；右键预览仍支持单图或整页。
        # 与任务流程的拼版步骤**同一组信号、同一套语义**——此前这四条没接线，
        # 画布右键菜单弹得出来、双击也有反应信号，但**点了什么都不会发生**
        # （用户 2026-10-03：「独立步骤，图片也可以编辑生效」）。
        self.view.item_preview_requested.connect(self._open_item_preview)
        self.view.spread_preview_requested.connect(self._open_spread_preview)
        self.view.item_edit_requested.connect(
            lambda _slot: self._open_spread_edit()
        )
        self.view.spread_edit_requested.connect(self._open_spread_edit)
        # 「定位图片资源」没定位成（源文件已不存在）：说清原因，别静默
        self.view.locate_failed.connect(
            lambda message: self.toast("warning", "定位图片资源", message)
        )
        # 左列滚到新的位置：按新窗口补生成缩略图（只生成看得见的那几页，
        # 与任务流程拼版步骤同一套口径，见 page_thumb.PageThumbManager）
        self.view.viewport_changed.connect(self._on_viewport_changed)
        return self.view

    # ------------------------------------------------------------------ 控制
    def _build_control(self) -> Card:
        """右栏：自动拼版 + 复用 ``ImpositionPanel`` + **底部动作区**。

        底部动作区与其它单任务页（``StepControl``）同一套排法（用户
        2026-11-17：「输出目录/执行/中断等功能，放在控制面板底部」）：
        输出目录 → 进度 → 导出成品 → 查看处理文件，恒在控制列最底下；
        「自动拼版」是版面参数区的一部分，随面板放在上面。
        """
        card = Card()

        # 导出走共用执行内核：拼版是纯函数，所以用 CallableJob
        self.kernel = StepKernel(callable_job(self._compose_job), self)
        self.kernel.log.connect(self.log)
        self.kernel.progress.connect(self._on_progress)
        self.kernel.finished.connect(self._on_exported)
        self.kernel.failed.connect(self._on_export_failed)

        self.auto_button = PushButton(FIF.MOVE, "自动拼版")
        self.auto_button.setFixedHeight(34)
        self.auto_button.setToolTip(
            "按文件名规则自动配对：前一页左半幅 + 当前页右半幅拼成对页"
        )
        self.auto_button.clicked.connect(self._auto_impose)
        card.box.addWidget(self.auto_button)

        # enable_switch=False：单文件模式没有「第四步取图来源」概念，
        # 构造时声明收掉启用开关（任务流程专属概念不进独立页）。
        # 其余信号与任务流程的拼版步骤**逐条对齐**（2026-10-13 用户：独立
        # 拼图页跟任务流程保持一致）：整版旋转、单图页「新增图片」、
        # 「删除选中图片」、复位、清空。
        self.panel = ImpositionPanel(enable_switch=False)
        self.panel.reset_requested.connect(self._on_reset_layout)
        self.panel.whole_rotate_delta.connect(self._on_whole_rotate)
        self.panel.item_rotation_edited.connect(self._on_item_rotate)
        self.panel.add_image_requested.connect(self._on_add_image)
        self.panel.item_delete_requested.connect(self._on_delete_item)
        self.panel.clear_requested.connect(self._on_clear)
        card.box.addWidget(self.panel)

        # ---- 底部动作区（与 StepControl 同一排法）----
        # ⚠️ 弹性空白把动作区压到控制列最底（用户 2026-11-17 截图反馈，
        #     与 ``StepControl`` 内部同一手法）。
        card.box.addStretch(1)

        # 执行进度：与四个步骤页**同一个**组件（``StepControl`` 内部那条也是
        # 它），所以拼图页的进度条长得跟别处一模一样。
        # ⚠️ 本页**不继承** ``StepModulePage``（源是一批图、执行是纯函数导出），
        # 所以这条得自己摆、自己接——别以为基类会捎带带上。
        self.out_button = PushButton(FIF.SAVE, "输出目录")
        self.out_button.setFixedHeight(34)
        self.out_button.setToolTip(
            "默认在源图旁边（拼图成品/）；点这里可以改到别处。\n"
            "「导出成品」直接写进这个目录，不再每次弹选择框。"
        )
        self.out_button.clicked.connect(self._pick_output)
        card.box.addWidget(self.out_button)

        self.progress_row = ProgressRow(noun=_SPEC.progress_unit())
        card.box.addWidget(self.progress_row)

        self.export_button = PrimaryPushButton(FIF.SAVE, "导出成品")
        self.export_button.setFixedHeight(36)
        self.export_button.clicked.connect(self._export)
        card.box.addWidget(self.export_button)

        # ---- 查看处理文件（2026-10-11 用户：执行成功后右侧下边的入口）----
        # 导出成功才出现，指向最近一次导出的目录；再次导出/清空输入即收起。
        self._last_output: Path | None = None
        self.view_output_button = PushButton(FIF.FOLDER, "查看处理文件")
        self.view_output_button.setFixedHeight(34)
        self.view_output_button.setToolTip("在资源管理器中打开本次导出结果")
        self.view_output_button.setVisible(False)
        self.view_output_button.clicked.connect(self._open_last_output)
        card.box.addWidget(self.view_output_button)
        return card

    def _pick_output(self) -> None:
        """改输出目录（与 ``StepControl`` 的输出目录按钮同语义：手动选择后
        记住，不再被自动重推覆盖）。"""
        current = self._out_dir
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "选择输出目录", str(current) if current else ""
        )
        if directory:
            self._out_dir = Path(directory)
            self.status(f"输出目录：{directory}", "info")

    # ---------------------------------------------------- 「编辑」菜单
    def can_edit_delete_selected(self) -> bool:
        """「编辑 → 删除选中」：左列**勾选**的拼版页可批量删除（与悬浮框同判据）。"""
        return bool(getattr(self.view, "checked_pages", lambda: [])())

    def edit_delete_selected(self) -> None:
        """走左列悬浮框「批量删除」同一条实现（含确认弹窗与落盘）。"""
        if self.can_edit_delete_selected():
            self._on_batch_delete()

    def can_edit_insert_images(self) -> bool:
        """「编辑 → 插入图片」：点「＋ 选择拼版」的同一入口（候选池含已删除图）。"""
        return bool(self._sources) and self.view is not None

    def edit_insert_images(self) -> None:
        self._on_add_pages()
