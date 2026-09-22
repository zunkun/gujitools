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

from PySide6.QtCore import QProcess, QTimer
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
from desktop.ui.widgets import (
    Card, Divider, ProgressLine, SectionTitle, apply_to, combo_box,
)


class LazyPanelHost(QWidget):
    """阶段面板的**惰性宿主**：真正被取用时才构造内部面板。

    为什么需要：详情页一进来停在第一步，而第四步的 ``PrintPanel`` 构造要
    ~128 ms（占整个详情页构造的**一半**——它那张参数表单 ``build_form`` 单项
    就 106 ms）。用户可能从头到尾都不点第四步，却每次进详情页都在为它买单。

    属性访问一律转发给内部面板，所以 ``control_stack.widget(3).get_args()``
    这类既有写法照常工作。Qt 自己的 ``sizeHint`` / ``paintEvent`` 等由 C++
    层调用，**不走 Python 的 __getattr__**，不会误触发构造。
    """

    def __init__(self, factory, hooks=(), parent=None):
        """factory() 造真面板；hooks 是"内部面板构造完成"后的回调（接线用）。"""
        super().__init__(parent)
        self._factory = factory
        self._hooks = list(hooks)
        self._inner: QWidget | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._host_layout = layout

    def add_created_hook(self, fn) -> None:
        """注册"内部面板构造完成"回调；**若已构造则立刻执行**。

        ⚠️ 必须支持挂多个回调：视图层要接预览刷新、暂存层要接 param_edited，
        它们分属不同 Mixin，各自只知道自己的接线，不能互相覆盖。
        """
        if self._inner is not None:
            fn(self._inner)
        else:
            self._hooks.append(fn)

    def peek(self) -> QWidget | None:
        """**不触发构造**地看内部面板；尚未构造时返回 None。"""
        return self._inner

    @property
    def panel(self) -> QWidget:
        """内部真面板，首次访问时构造（并把挂着的回调全部执行一遍）。"""
        if self._inner is None:
            self._inner = self._factory()
            self._host_layout.addWidget(self._inner)
            hooks, self._hooks = self._hooks, []
            for hook in hooks:
                hook(self._inner)
        return self._inner

    def __getattr__(self, name: str):
        # 只有在类上找不到该属性时才会走到这里；_factory/_inner 都在 __dict__
        factory = self.__dict__.get("_factory")
        if factory is None:
            raise AttributeError(name)
        return getattr(self.panel, name)


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

        # print：左缩略图条 + 右「打印效果」预览（可拖动排序/删除/插入）
        # ⚠️ params_provider 必须传：缺了它预览永远显示"未接入打印参数，已显示原图"，
        # 标题/页码/纸张效果一概看不到（组件自测传了参数，测不出宿主漏接线）。
        self._print_dirty = False  # 版面编辑器改过坐标、尚未重新生成 PDF
        self.print_preview = PrintPreviewWidget(
            empty_hint="暂无图片，请先在第三步「生成预览」并「提交本次任务」",
            params_provider=self._print_params,
        )
        self.print_preview.order_changed.connect(self._save_print_order)
        self.print_preview.insert_requested.connect(self._insert_print_images)
        self.print_preview.download_requested.connect(self._download_print_pdf)
        # 版面编辑：某一页图片坐标被拖拽/缩放后落盘 print.json 并标脏
        self.print_preview.layout_changed.connect(self._on_print_layout_changed)
        self.print_preview.hint.connect(
            lambda message: self._toast("info", "提示", message)
        )
        self.preview_stack.addWidget(self.print_preview)
        return self.preview_stack

    def _build_control_card(self) -> QWidget:
        card = Card(padding=T.SPACE_MD, spacing=T.SPACE_MD, radius=T.RADIUS_MD)
        column = card.box

        self.control_stack = QStackedWidget()
        for index, panel_class in enumerate(PANEL_CLASSES):
            if index == 3:
                # 第四步 PrintPanel 最重（构造 ~128 ms，占详情页构造的一半），
                # 而用户进来只看第一步 → 等真切到第四步再建（见 LazyPanelHost）。
                self.control_stack.addWidget(
                    LazyPanelHost(panel_class, hooks=[self._wire_print_panel])
                )
            else:
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
        # 整页模式：等价于把第三步 area 切到 4（跳过 YOLO，整页作为一个框）
        detect_panel.whole_page_toggled.connect(self._set_whole_page_mode)

        # rembg 面板的参数变化决定检测框标注与去底色预览区域，联动刷新
        rembg_panel = self.control_stack.widget(2)

        def _on_rembg_panel_changed(*_):
            # area 可能被第二步的整页开关改动，勾选状态需回填
            self._sync_whole_page_checkbox()
            self._refresh_reference_boxes()
            self._update_submit_button(
                bool(self.process and self.process.state() != QProcess.NotRunning)
            )
            # 第三步 border 级联第四步默认边距：border 变化时把上游 border
            # 同步给 print 面板（用户未手动改边距时，默认值随级联变 0/20）
            self._sync_print_margin_default()

        rembg_panel.area.currentTextChanged.connect(_on_rembg_panel_changed)
        rembg_panel.border.textChanged.connect(_on_rembg_panel_changed)
        # 去底参数变化会改变预览图 → 「提交」按钮的新版本提示需实时刷新
        rembg_panel.type.currentTextChanged.connect(_on_rembg_panel_changed)
        rembg_panel.offset.valueChanged.connect(_on_rembg_panel_changed)
        rembg_panel.seal.toggled.connect(_on_rembg_panel_changed)
        rembg_panel.sealcolor.toggled.connect(_on_rembg_panel_changed)
        rembg_panel.sealarea.valueChanged.connect(_on_rembg_panel_changed)
        rembg_panel.sealmin_sat.valueChanged.connect(_on_rembg_panel_changed)

        # print 面板的接线**推迟**到它真正被构造时（见 _wire_print_panel）：
        # 第四步面板是惰性的，这里一碰它就等于立刻把它建出来，白惰性了。
        # 边距级联只记下当前值，等面板建好时再补一次。
        self._pending_print_border = None
        self._sync_print_margin_default()

    def _wire_print_panel(self, panel) -> None:
        """第四步面板**首次构造后**的接线（LazyPanelHost 的 on_created 回调）。"""
        # 参数变化 → 效果预览按新参数重画（只是重画内存位图，不执行、不提交、
        # 不生成 PDF）。防抖 250ms：边距/颜色是逐字符输入，每次都重载一遍大图
        # 会明显卡顿。
        self._print_preview_timer = QTimer(self)
        self._print_preview_timer.setSingleShot(True)
        self._print_preview_timer.setInterval(250)
        self._print_preview_timer.timeout.connect(self.print_preview.refresh_display)
        panel.params_changed.connect(self._print_preview_timer.start)
        # 补一次"面板还没建时"挂起的边距级联
        try:
            panel.set_upstream_border(getattr(self, "_pending_print_border", None))
        except Exception:
            pass

    def _print_params(self) -> dict:
        """第四步打印参数（供「打印效果」预览）：直接读面板表单。

        颜色/边距填到一半时 ``get_args()`` 会抛 ValueError，这里**不吞**——
        由 ``PrintPreviewWidget`` 捕获后退回「原图」并在说明行给出原因，
        避免用户每敲一个字符就弹窗。
        """
        return self.control_stack.widget(3).get_args()

    def _sync_print_margin_default(self) -> None:
        """把第三步 rembg 面板的当前 border 同步给第四步面板做默认级联。

        读取 rembg 面板的 border 原始文本（不触发其 get_args 校验，避免
        填写中途的非法值抛错），交给 print 面板自行决定是否覆盖默认边距。
        """
        try:
            rembg_panel = self.control_stack.widget(2)
            border = (rembg_panel.border.text() or "").strip() or None
        except Exception:
            border = None
        host = self.control_stack.widget(3)
        peek = getattr(host, "peek", None)
        panel = peek() if callable(peek) else host
        if panel is None:
            # 第四步面板还没构造：先记住，等它建好时由 _wire_print_panel 补同步。
            # ⚠️ 这里绝不能走属性转发——rembg 参数一变就会把它建出来，
            #    惰性就白做了。
            self._pending_print_border = border
            return
        try:
            panel.set_upstream_border(border)
        except Exception:
            pass

    def _on_print_layout_changed(self, index: int, rect: list) -> None:
        """版面编辑器改了某页坐标：落盘 print.json 并标脏，提示可重新生成 PDF。

        落盘走 ``_save_print_order``（直接序列化当前条目，rect 已随条目携带），
        下次点「生成 PDF」时 runner 会从 print.json 收集 page_rects 注入生成。
        """
        if not self.task_id:
            return
        self._save_print_order(silent=True)  # 拖拽频繁落盘，不打列表日志
        self._print_dirty = True
        self.stage_status.setText("● 版面已修改，点击「生成 PDF」生效")
        apply_to(self.stage_status, T.SIZE_CAPTION, color=T.INK_SOFT)
        rx, ry, rw, rh = (list(rect) + [0, 0, 0, 0])[:4]
        self.log_view.append(
            f"第 {index + 1} 页版面已更新（x={rx:.0f}, y={ry:.0f}, "
            f"w={rw:.0f}, h={rh:.0f} mm），点击「生成 PDF」生效"
        )

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
        combo = combo_box()
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
