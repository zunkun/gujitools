# -*- coding: utf-8 -*-
"""任务详情页的视图构建：头部/步骤条/预览区/控制列/日志的 UI 组装。

只做控件创建与信号连接，业务动作全部委托给宿主页面的其他 Mixin。

视觉结构（自上而下）：
1. 页头卡片：返回 + 任务名 + 源文件标签 + 打开目录；
2. 步骤条卡片：四步流程与状态；
3. 主体：左侧预览卡片（自适应）+ 右侧参数卡片（固定宽度区间）；
4. 底部：执行日志状态条（常驻一行，点击唤出不挤压布局的日志浮层）。
"""

from __future__ import annotations

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    CaptionLabel, ComboBox, PrimaryPushButton, PushButton, ToolButton,
)
from qfluentwidgets import FluentIcon as FIF

from desktop.components import PANEL_CLASSES
from desktop.components.log_panel import LogPanel
from desktop.components.step_bar import StepBar
from desktop.components.viewers import (
    ImageViewerWidget, PdfViewerWidget, PrintPreviewWidget, RembgPreviewWidget,
)
from desktop.store import STAGES, STAGE_LABELS
from desktop.ui import theme as T
from desktop.ui.widgets import Card, Divider, ProgressLine, SectionTitle, apply_to


class DetailViewMixin:
    """依赖宿主页面提供的方法：_on_back、_select_stage、各预览联动槽、
    current_stage()、_update_run_buttons() 等。"""

    # ------------------------------------------------------------------ 组装
    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG)
        root.setSpacing(T.SPACE_MD)

        root.addWidget(self._build_header())
        root.addWidget(self._build_step_bar())
        body = QHBoxLayout()
        body.setSpacing(T.SPACE_MD)
        body.addWidget(self._build_preview_card(), 1)
        body.addWidget(self._build_control_card())
        root.addLayout(body, 1)

        self.log_panel = LogPanel()
        # 页面各处沿用的 self.log_view 直接指向面板内的文本域
        self.log_view = self.log_panel.log_view
        root.addWidget(self.log_panel)

        self._update_run_buttons({"status": "pending"})

    def _build_header(self) -> Card:
        card = Card(padding=0, spacing=0, radius=T.RADIUS_MD, layout="h")
        row = card.box
        row.setContentsMargins(T.SPACE_MD, T.SPACE_SM, T.SPACE_MD, T.SPACE_SM)
        row.setSpacing(T.SPACE_MD)

        back_btn = ToolButton(FIF.RETURN)
        back_btn.setToolTip("返回任务列表")
        back_btn.setFixedSize(34, 34)
        back_btn.clicked.connect(self._on_back)
        row.addWidget(back_btn)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(1)
        self.detail_title = QLabel("任务详情")
        apply_to(self.detail_title, T.SIZE_SUBTITLE, bold=True, color=T.INK)
        text_column.addWidget(self.detail_title)
        self.source_label = QLabel("")
        apply_to(self.source_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        text_column.addWidget(self.source_label)
        row.addLayout(text_column)
        row.addStretch()

        open_dir_btn = ToolButton(FIF.FOLDER)
        open_dir_btn.setToolTip("打开任务数据目录")
        open_dir_btn.setFixedSize(34, 34)
        open_dir_btn.clicked.connect(self._open_task_dir)
        row.addWidget(open_dir_btn)
        return card

    def _build_step_bar(self) -> StepBar:
        # 步骤条自带卡片底（paintEvent 绘制），不再套一层 Card，避免"卡片套卡片"
        self.step_bar = StepBar(STAGE_LABELS[s] for s in STAGES)
        self.step_bar.current_changed.connect(self._select_stage)
        return self.step_bar

    def _build_preview_card(self) -> Card:
        card = Card(padding=T.SPACE_SM, spacing=0, radius=T.RADIUS_MD)
        card.box.addWidget(self._build_preview_stack())
        return card

    def _build_preview_stack(self) -> QStackedWidget:
        self.preview_stack = QStackedWidget()
        # extract：双标签页
        self.extract_tabs = QTabWidget()
        self.source_pdf_viewer = PdfViewerWidget("尚未导入 PDF")
        self.source_pdf_viewer.page_count_changed.connect(self._pdf_page_count_ready)
        self.extract_tabs.addTab(self.source_pdf_viewer, "PDF 预览")
        self.extract_result_viewer = ImageViewerWidget(
            editable=True, empty_hint="尚未提取，点击右侧「执行本子任务」",
            thumb_provider=self._page_thumb_for,
        )
        self.extract_result_viewer.current_changed.connect(self._image_selected)
        self.extract_result_viewer.delete_requested.connect(self.delete_selected_page)
        self.extract_result_viewer.insert_requested.connect(self.insert_pages)
        self.extract_tabs.addTab(self.extract_result_viewer, "提取结果")
        self.preview_stack.addWidget(self.extract_tabs)

        # detect：图片 + 检测框
        self.detect_viewer = ImageViewerWidget(
            editable=True, show_boxes=True, empty_hint="暂无图片，请先完成提取",
            image_size_provider=self._original_image_size,
            thumb_provider=self._page_thumb_for,
        )
        self.detect_viewer.current_changed.connect(self._detect_image_selected)
        self.detect_viewer.delete_requested.connect(self.delete_selected_page)
        self.detect_viewer.insert_requested.connect(self.insert_pages)
        self.detect_viewer.boxes_edited.connect(self._save_manual_boxes)
        self.preview_stack.addWidget(self.detect_viewer)

        # rembg：原图/结果对比
        self.rembg_viewer = RembgPreviewWidget()
        self.preview_stack.addWidget(self.rembg_viewer)

        # print：图片瀑布流列表（可拖动排序/删除/插入）
        self.print_preview = PrintPreviewWidget(
            empty_hint="暂无图片，请先在第三步「生成预览」并「提交本次任务」"
        )
        self.print_preview.order_changed.connect(self._save_print_order)
        self.print_preview.insert_requested.connect(self._insert_print_images)
        self.print_preview.download_requested.connect(self._download_print_pdf)
        self.print_preview.hint.connect(
            lambda message: self._toast("info", "提示", message)
        )
        self.preview_stack.addWidget(self.print_preview)
        return self.preview_stack

    def _build_control_card(self) -> QWidget:
        card = Card(padding=T.SPACE_MD, spacing=T.SPACE_MD, radius=T.RADIUS_MD)
        column = card.box

        self.control_stack = QStackedWidget()
        for panel_class in PANEL_CLASSES:
            self.control_stack.addWidget(panel_class())
        column.addWidget(self.control_stack, 1)
        self._connect_stage_panels()

        column.addWidget(Divider())
        self._build_history_controls(column)
        column.addWidget(Divider())
        self._build_run_controls(column)

        # 控制面板限宽：参数表单需要舒适宽度，第四步 YAML 编辑器尤甚
        self.control_widget = card
        self._apply_control_width()
        return self.control_widget

    def _connect_stage_panels(self) -> None:
        """阶段面板信号 → 宿主动作的联动接线。"""
        # detect 面板「检测本页」：手动触发当前页的 YOLO 检测（不自动执行）
        detect_panel = self.control_stack.widget(1)
        detect_panel.detect_page_requested.connect(self._detect_current_page)

        # rembg 面板的参数变化决定检测框标注与去底色预览区域，联动刷新
        rembg_panel = self.control_stack.widget(2)

        def _on_rembg_panel_changed(*_):
            self._refresh_reference_boxes()
            self._update_submit_button(
                bool(self.process and self.process.state() != QProcess.NotRunning)
            )

        rembg_panel.area.currentTextChanged.connect(_on_rembg_panel_changed)
        rembg_panel.border.textChanged.connect(_on_rembg_panel_changed)
        # 去底参数变化会改变预览图 → 「提交」按钮的新版本提示需实时刷新
        rembg_panel.type.currentTextChanged.connect(_on_rembg_panel_changed)
        rembg_panel.offset.valueChanged.connect(_on_rembg_panel_changed)
        rembg_panel.seal.toggled.connect(_on_rembg_panel_changed)
        rembg_panel.sealcolor.toggled.connect(_on_rembg_panel_changed)
        rembg_panel.sealarea.valueChanged.connect(_on_rembg_panel_changed)
        rembg_panel.sealmin_sat.valueChanged.connect(_on_rembg_panel_changed)

    def _build_history_controls(self, control: QVBoxLayout) -> None:
        # ---- 历史执行配置选择 ----
        control.addWidget(SectionTitle("执行记录"))
        self.history_caption = CaptionLabel("历史执行配置（选择后回填到表单）")
        apply_to(self.history_caption, T.SIZE_CAPTION, color=T.INK_FAINT)
        control.addWidget(self.history_caption)
        self.history_combo = self._make_history_combo()
        control.addWidget(self.history_combo)

        self.stage_status = CaptionLabel("未执行")
        apply_to(self.stage_status, T.SIZE_CAPTION, color=T.INK_SOFT)
        control.addWidget(self.stage_status)
        # 细进度条：只表达"执行到多少页"，不抢视觉
        self.stage_progress = ProgressLine()
        control.addWidget(self.stage_progress)

    def _make_history_combo(self) -> ComboBox:
        combo = ComboBox()
        combo.currentIndexChanged.connect(self._on_history_selected)
        return combo

    def _build_run_controls(self, control: QVBoxLayout) -> None:
        self.run_button = PrimaryPushButton(FIF.PLAY, "执行本子任务")
        self.run_button.setFixedHeight(36)
        self.run_button.clicked.connect(lambda: self.run_stage(resume=False))
        # 步骤三（rembg）专用：把预览结果按 area/border 合成为最终图片
        self.submit_button = PrimaryPushButton(FIF.ACCEPT, "提交本次任务")
        self.submit_button.setFixedHeight(36)
        self.submit_button.setToolTip(
            "将「生成预览」的去底色图片按 area/border 等合成为真正想要的最终图片"
        )
        self.submit_button.clicked.connect(self.run_rembg_submit)
        self.submit_button.setVisible(False)
        # 新版本提示：生成预览参数/结果变化后、提交前常驻提醒（位于提交按钮下方）
        self.submit_hint = CaptionLabel("")
        self.submit_hint.setWordWrap(True)
        apply_to(self.submit_hint, T.SIZE_CAPTION)
        self.submit_hint.hide()
        self.resume_button = PushButton(FIF.UPDATE, "继续执行（跳过已完成）")
        self.resume_button.setFixedHeight(34)
        self.resume_button.clicked.connect(lambda: self.run_stage(resume=True))
        self.cancel_button = PushButton(FIF.CLOSE, "中断执行")
        self.cancel_button.setFixedHeight(34)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_stage)
        control.addWidget(self.run_button)
        control.addWidget(self.submit_button)
        control.addWidget(self.submit_hint)
        control.addWidget(self.resume_button)
        control.addWidget(self.cancel_button)

    # ------------------------------------------------------------------ 宽度
    def _apply_control_width(self) -> None:
        """按当前阶段调整右侧控制面板宽度：
        第四步 YAML 编辑器需要更宽的编辑区，其余步骤保持舒适表单宽度。"""
        stage = self.current_stage()
        if stage == "print":
            self.control_widget.setMinimumWidth(400)
            self.control_widget.setMaximumWidth(580)
        else:
            self.control_widget.setMinimumWidth(340)
            self.control_widget.setMaximumWidth(440)
