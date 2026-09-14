# -*- coding: utf-8 -*-
"""任务详情页：顶部步骤条 + 左侧多标签预览 + 右侧阶段控制面板。

预览区按阶段组织：
- extract：[PDF 预览 | 提取结果] 双标签页；
- detect：图片预览，叠加显示每张图的检测框位置；
- rembg：原图 / 去底结果对比；
- print：输出 PDF 预览。

阶段执行逻辑见 detail_runner.StageRunnerMixin，
detect 检测逻辑见 detail_detect.DetectMixin。
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from PySide6.QtCore import QProcess, Signal
from PySide6.QtCore import QUrl
from PySide6.QtCore import QSize
from PySide6.QtGui import QDesktopServices, QImageReader
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    CaptionLabel, ComboBox, FluentIcon as FIF, InfoBar, InfoBarPosition,
    PrimaryPushButton, ProgressBar, PushButton, TextEdit, TitleLabel, ToolButton,
)

from ..components import PANEL_CLASSES
from ..components.step_bar import StepBar
from ..components.viewers import (
    ImageViewerWidget, PdfViewerWidget, PrintPreviewWidget, RembgPreviewWidget,
)
from ..utils.files import list_stage_images
from ..store import STAGES, STAGE_LABELS
from utils.sort_utils import pdf_custom_sort_key
from ..workers import WorkerHost
from .detail_detect import DetectMixin
from .detail_runner import STATUS_LABELS, StageRunnerMixin


class TaskDetailPage(StageRunnerMixin, DetectMixin, QWidget, WorkerHost):
    back_requested = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._init_worker_host()
        self.task_id: str | None = None
        self.source_path: Path | None = None
        self.pages: list[dict] = []
        self.pdf_page_count = 0
        self.process: QProcess | None = None
        self.run_id: str | None = None
        self.running_stage: str | None = None
        self.cancel_requested = False
        self.detect_process: QProcess | None = None
        self.detect_cache: dict[str, list[tuple] | None] = {}
        self._last_error_line: str | None = None
        self._extract_seen = 0  # 提取过程中已展示的结果页数
        self._init_ui()

    # ------------------------------------------------------------------ UI
    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # ---- 头部：返回 / 标题 / 打开目录 ----
        header = QHBoxLayout()
        back_btn = ToolButton(FIF.RETURN)
        back_btn.setToolTip("返回任务列表")
        back_btn.clicked.connect(self._on_back)
        header.addWidget(back_btn)
        self.detail_title = TitleLabel("任务详情")
        header.addWidget(self.detail_title)
        self.source_label = CaptionLabel("")
        header.addWidget(self.source_label)
        header.addStretch()
        open_dir_btn = ToolButton(FIF.FOLDER)
        open_dir_btn.setToolTip("打开任务数据目录")
        open_dir_btn.clicked.connect(self._open_task_dir)
        header.addWidget(open_dir_btn)
        root.addLayout(header)

        # ---- 步骤条 ----
        self.step_bar = StepBar(STAGE_LABELS[s] for s in STAGES)
        self.step_bar.current_changed.connect(self._select_stage)
        root.addWidget(self.step_bar)

        # ---- 主体：预览区 | 控制面板 ----
        body = QHBoxLayout()
        body.setSpacing(12)

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
        self.preview_stack.addWidget(self.print_preview)

        # ---- 右侧控制列 ----
        control = QVBoxLayout()
        self.control_stack = QStackedWidget()
        for panel_class in PANEL_CLASSES:
            self.control_stack.addWidget(panel_class())
        control.addWidget(self.control_stack)

        # detect 面板 area/border 变化时，重算预览中的最终裁剪大框
        # detect 面板「检测本页」：手动触发当前页的 YOLO 检测（不自动执行）
        detect_panel = self.control_stack.widget(1)
        detect_panel.detect_page_requested.connect(self._detect_current_page)

        # rembg 面板的 area/border 决定检测框标注与去底色预览区域，变化时联动刷新
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

        # ---- 历史执行配置选择 ----
        self.history_caption = CaptionLabel("历史执行配置（选择后回填到表单）")
        control.addWidget(self.history_caption)
        self.history_combo = ComboBox()
        self.history_combo.currentIndexChanged.connect(self._on_history_selected)
        control.addWidget(self.history_combo)

        self.stage_status = CaptionLabel("未执行")
        control.addWidget(self.stage_status)
        self.stage_progress = ProgressBar()
        control.addWidget(self.stage_progress)

        self.run_button = PrimaryPushButton(FIF.PLAY, "执行本子任务")
        self.run_button.clicked.connect(lambda: self.run_stage(resume=False))
        # 步骤三（rembg）专用：把预览结果按 area/border 合成为最终图片
        self.submit_button = PrimaryPushButton(FIF.ACCEPT, "提交本次任务")
        self.submit_button.setToolTip(
            "将「生成预览」的去底色图片按 area/border 等合成为真正想要的最终图片"
        )
        self.submit_button.clicked.connect(self.run_rembg_submit)
        self.submit_button.setVisible(False)
        # 新版本提示：生成预览参数/结果变化后、提交前常驻提醒（位于提交按钮下方）
        self.submit_hint = CaptionLabel("")
        self.submit_hint.setWordWrap(True)
        self.submit_hint.hide()
        self.resume_button = PushButton(FIF.UPDATE, "继续执行（跳过已完成）")
        self.resume_button.clicked.connect(lambda: self.run_stage(resume=True))
        self.cancel_button = PushButton(FIF.CLOSE, "中断执行")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_stage)
        control.addWidget(self.run_button)
        control.addWidget(self.submit_button)
        control.addWidget(self.submit_hint)
        control.addWidget(self.resume_button)
        control.addWidget(self.cancel_button)
        control.addStretch()

        # 控制面板限宽：参数表单需要舒适宽度，第四步 YAML 编辑器尤甚
        self.control_widget = QWidget()
        self.control_widget.setLayout(control)
        self._apply_control_width()
        body.addWidget(self.preview_stack, 1)
        body.addWidget(self.control_widget)

        root.addLayout(body, 1)

        # ---- 底部日志 ----
        self.log_view = TextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(140)
        self.log_view.setPlaceholderText("执行日志")
        root.addWidget(self.log_view)

        self._update_run_buttons({"status": "pending"})

    # ------------------------------------------------------------------ 任务切换
    def set_task(self, task_id: str) -> None:
        task = self.store.get_task(task_id)
        if not task:
            return
        self.task_id = task_id
        self.source_path = Path(task["source_path"])
        self.detail_title.setText(task["name"])
        self.source_label.setText(self.source_path.name)
        # 第四步默认 PDF 名/古籍名随源 PDF 名派生（xxx[重制].pdf / xxx）；
        # 若该任务已有 print 历史，进入第四步时会再回填历史配置
        self.control_stack.widget(3).set_source_defaults(self.source_path.stem)
        self.log_view.clear()
        self.detect_cache.clear()
        self.pdf_page_count = 0
        self._history_prefilled: set[str] = set()
        self.source_pdf_viewer.set_pdf(
            self.source_path, cache_dir=self.store.source_thumbnails_dir(task_id)
        )
        self._refresh_manifest()
        self._refresh_stage_views()
        self._select_stage(0)

    def _on_back(self) -> None:
        if self.process and self.process.state() != QProcess.NotRunning:
            self._toast("warning", "任务进行中", "请先中断当前子任务再返回。")
            return
        self.task_id = None
        self.source_path = None
        self.back_requested.emit()

    def _open_task_dir(self) -> None:
        if self.task_id:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self.store.task_dir(self.task_id)))
            )

    # ------------------------------------------------------------------ 页面清单
    def _refresh_manifest(self) -> None:
        if not self.task_id:
            return
        self.pages = self.store.load_pages(self.task_id)

    def _manifest_paths(self) -> list[Path]:
        return [Path(p["file"]) for p in self.pages if Path(p["file"]).exists()]

    def _page_thumb_for(self, path_text: str, box=None, parea: int = 1, border_mm=None):
        """extract/rembg 数字页名 → 预生成页缩略图。

        box（原始像素坐标）非空时，返回在缩略图上按 area/border 规则
        合成的效果图参数（坐标/边距按缩略图比例缩放）。返回：
        - {"path": 缩略图路径, "effect": {boxes, area, border, dpi} | None}
        - None：无可用缩略图，调用方回退真图
        """
        p = Path(path_text)
        if not p.stem.isdigit() or not self.task_id:
            return None
        allowed = {
            self.store.extract_output_dir(self.task_id),
            self.store.rembg_preview_output_dir(self.task_id),
            self.store.rembg_output_dir(self.task_id),
        }
        if p.parent not in allowed:
            return None
        total = self.pdf_page_count or 0
        n = int(p.stem)
        if total and n > total:
            return None
        thumb = self.store.source_thumbnails_dir(self.task_id) / f"{n:04d}.jpg"
        if not thumb.exists():
            return None
        if box is None:
            return {"path": str(thumb), "effect": None}
        meta = self.store.image_size(self.task_id, p.stem)
        if not meta:
            return {"path": str(thumb), "effect": None}
        ts = QImageReader(str(thumb)).size()
        if not ts.isValid() or not meta[0] or not meta[1]:
            return {"path": str(thumb), "effect": None}
        sx, sy = ts.width() / meta[0], ts.height() / meta[1]
        scaled_box = [box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy]
        return {
            "path": str(thumb),
            "effect": {
                "boxes": [scaled_box],
                "area": parea,
                "border": border_mm,
                "dpi": 300 * sx,  # border 像素随缩略图比例缩放
            },
        }

    def _pdf_page_count_ready(self, count: int) -> None:
        self.pdf_page_count = count

    def _original_image_size(self, path_text: str) -> QSize | None:
        """页面图片的原始像素尺寸：优先 extract 阶段记录的 DB 值。"""
        if self.task_id:
            meta = self.store.image_size(self.task_id, Path(path_text).stem)
            if meta:
                return QSize(meta[0], meta[1])
        size = QImageReader(path_text).size()
        return size if size.isValid() else None

    # ------------------------------------------------------------------ 阶段切换/状态
    def current_stage(self) -> str:
        return STAGES[max(self.step_bar._current, 0)]

    def _select_stage(self, index: int) -> None:
        self.step_bar.set_current(index)
        self.control_stack.setCurrentIndex(index)
        self.preview_stack.setCurrentIndex(index)
        # 步骤三：主按钮为「生成预览」，下方另有「提交本次任务」；
        # 其他阶段保持「执行本子任务」，提交按钮隐藏。
        is_rembg = STAGES[index] == "rembg"
        self.run_button.setText("生成预览" if is_rembg else "执行本子任务")
        self.submit_button.setVisible(is_rembg)
        self._apply_control_width()
        self._refresh_stage_views()
        self._refresh_preview(index)
        self._restore_last_run_params(index)
        self._refresh_history_options()

    def _apply_control_width(self) -> None:
        """按当前阶段调整右侧控制面板宽度：
        第四步 YAML 编辑器需要更宽的编辑区，其余步骤保持舒适表单宽度。"""
        stage = self.current_stage()
        if stage == "print":
            self.control_widget.setMinimumWidth(380)
            self.control_widget.setMaximumWidth(560)
        else:
            self.control_widget.setMinimumWidth(320)
            self.control_widget.setMaximumWidth(420)

    # ------------------------------------------------------------------ 历史执行配置
    # 各阶段历史回填时要跳过的字段（临时/派生/运行时覆盖）
    _HISTORY_SKIP = frozenset(
        {"input", "output", "workers", "clean", "resume",
         "_effects", "_outpath", "_preview_run_id"}
    )
    # print 阶段：pdf_name / title_text 始终从源 PDF 名派生，
    # 历史里存的是旧值或用户曾经填的自定义名，不应覆盖当前任务的规则值
    _PRINT_FIXED_KEYS = frozenset({"pdf_name", "title_text"})

    def _restore_last_run_params(self, index: int) -> None:
        """进入页面/切换阶段时，回填该阶段最近一次执行的参数。"""
        if not self.task_id:
            return
        stage = STAGES[index]
        if stage in self._history_prefilled:
            return
        self._history_prefilled.add(stage)
        history = self.store.list_stage_runs(self.task_id, stage)
        if history:
            skip = set(self._HISTORY_SKIP)
            if stage == "print":
                skip |= self._PRINT_FIXED_KEYS
            params = {
                k: v for k, v in history[0].get("parameters", {}).items()
                if k not in skip
            }
            self.control_stack.widget(index).apply_args(params)

    def _refresh_history_options(self) -> None:
        """把当前阶段的历史执行记录填入下拉框（最新在前）。"""
        combo = self.history_combo
        combo.blockSignals(True)
        combo.clear()
        self._history_params: list[dict] = []
        if self.task_id:
            stage = STAGES[max(self.step_bar._current, 0)]
            for record in self.store.list_stage_runs(self.task_id, stage):
                started = time.strftime(
                    "%m-%d %H:%M", time.localtime(record.get("started_at", 0))
                )
                resume = "续跑" if record.get("parameters", {}).get("resume") else "全量"
                status = STATUS_LABELS.get(record.get("status", ""), record.get("status", ""))
                combo.addItem(f"{started} · {resume} · {status}")
                self._history_params.append(record.get("parameters", {}))
        if self._history_params:
            combo.setCurrentIndex(-1)
            combo.setPlaceholderText(f"共 {len(self._history_params)} 次，选择回填")
        else:
            combo.setPlaceholderText("暂无历史执行配置")
        combo.blockSignals(False)

    def _on_history_selected(self, index: int) -> None:
        if index < 0 or index >= len(getattr(self, "_history_params", [])):
            return
        stage = STAGES[max(self.step_bar._current, 0)]
        skip = set(self._HISTORY_SKIP)
        if stage == "print":
            skip |= self._PRINT_FIXED_KEYS
        params = {
            k: v for k, v in self._history_params[index].items()
            if k not in skip
        }
        self.control_stack.widget(self.step_bar._current).apply_args(params)
        self._toast("info", "已回填历史配置", STAGE_LABELS[stage])

    def _refresh_stage_views(self) -> None:
        if not self.task_id:
            return
        states = self.store.stage_states(self.task_id)
        texts = []
        for index, stage in enumerate(STAGES):
            state = states[stage]
            status = STATUS_LABELS.get(state["status"], state["status"])
            progress = f" {state['done']}/{state['total']}" if state["total"] else ""
            texts.append(f"{index + 1}. {STAGE_LABELS[stage]} · {status}{progress}")
            if state["status"] == "success":
                self.step_bar.mark_completed(index)  # 已完成步骤淡蓝标记
        self.step_bar.set_steps(texts)
        stage = self.current_stage()
        self._apply_stage_state(stage, states[stage])
        self._update_run_buttons(states[stage])

    def _apply_stage_state(self, stage: str, state: dict) -> None:
        total, done = state["total"], state["done"]
        if total:
            self.stage_progress.setRange(0, total)
            self.stage_progress.setValue(min(done, total))
        else:
            self.stage_progress.setRange(0, 1)
            self.stage_progress.setValue(0)
        self.stage_status.setText(
            f"{STAGE_LABELS[stage]}：{STATUS_LABELS.get(state['status'], state['status'])}"
        )

    def _update_run_buttons(self, state: dict) -> None:
        running = bool(self.process and self.process.state() != QProcess.NotRunning)
        self.run_button.setEnabled(not running)
        self.resume_button.setEnabled(
            not running and state["status"] in ("cancelled", "failed", "success")
        )
        self.cancel_button.setEnabled(running)
        self._update_submit_button(running)

    # 影响「生成预览」产物（去底预览图）的参数；变化后预览图即过期
    PREVIEW_PARAM_KEYS = (
        "type", "offset", "seal", "sealcolor", "sealarea", "sealmin_sat",
    )

    def _latest_success_run(self, stage: str) -> dict | None:
        if not self.task_id:
            return None
        for record in self.store.list_stage_runs(self.task_id, stage):
            if record.get("status") == "success":
                return record
        return None

    def _rembg_submit_version_state(self) -> str:
        """提交按钮版本状态：

        - no_preview   ：从未成功生成预览（或最近一次失败/中断）→ 禁止提交；
        - preview_stale：面板去底参数相对最近一次成功预览已修改，
                         磁盘上的预览图不是最新 → 建议重新生成预览；
        - new_version  ：预览有新版本（重新生成过、或 area/border 已改），
                         最终图片落后于预览 → 提示需要提交；
        - up_to_date   ：最终图片已是最新预览版本。
        """
        preview = self._latest_success_run("rembg")
        if preview is None:
            return "no_preview"
        panel_args = self.control_stack.widget(2).get_args()
        prev_params = preview.get("parameters", {})
        if any(prev_params.get(k) != panel_args.get(k)
               for k in self.PREVIEW_PARAM_KEYS):
            return "preview_stale"
        submit = self._latest_success_run("rembg_submit")
        if submit is None:
            return "new_version"
        sub_params = submit.get("parameters", {})
        if sub_params.get("_preview_run_id") != preview.get("run_id"):
            return "new_version"  # 预览已用新参数重新生成
        if (sub_params.get("area") != panel_args.get("area")
                or sub_params.get("border") != panel_args.get("border")):
            return "new_version"  # area/border 变了，最终图需要重新合成
        return "up_to_date"

    def _update_submit_button(self, running: bool) -> None:
        """步骤三「提交本次任务」：最近一次「生成预览」成功后才可用；
        预览产生新版本（重跑/参数变更）时按钮高亮提示需要重新提交。"""
        if not self.task_id or self.current_stage() != "rembg":
            self.submit_hint.hide()
            return
        preview_state = self.store.stage_states(self.task_id)["rembg"]["status"]
        has_preview = bool(
            list_stage_images(self.store.rembg_preview_output_dir(self.task_id))
        )
        if running:
            version = None
            tip = "当前有任务正在执行，请等待完成后再提交"
        elif preview_state != "success":
            version = "no_preview"
            if preview_state in ("failed", "cancelled"):
                tip = (
                    f"上次「生成预览」{STATUS_LABELS.get(preview_state, preview_state)}，"
                    "请重新执行并成功后再提交本次任务"
                )
            else:
                tip = "请先点击「生成预览」，执行成功后才能提交本次任务"
        elif not has_preview:
            version = "no_preview"
            tip = "预览结果缺失，请重新点击「生成预览」"
        else:
            version = self._rembg_submit_version_state()
            tip = {
                "new_version": "预览已产生新版本（重新生成或参数已变更），"
                               "请点击「提交本次任务」更新最终图片",
                "preview_stale": "面板去底参数已修改，当前预览图不是最新；"
                                 "建议先重新「生成预览」，再提交本次任务",
                "up_to_date": "最终图片已是最新预览版本；参数变更或重新生成预览后需再次提交",
                "no_preview": "请先点击「生成预览」，执行成功后才能提交本次任务",
            }[version]
        self.submit_button.setToolTip(tip)

        # 按钮文案/高亮
        self.submit_button.setEnabled(version not in (None, "no_preview"))
        if version == "new_version":
            self.submit_button.setText("提交本次任务（有新版本）")
            self.submit_button.setStyleSheet(
                "PrimaryPushButton{font-weight:bold;}"
            )
            self._show_submit_hint(
                "● 预览有新版本，请提交本次任务", "#c0392b"
            )
        elif version == "preview_stale":
            self.submit_button.setText("提交本次任务")
            self.submit_button.setStyleSheet("")
            self._show_submit_hint(
                "● 去底参数已修改，请重新「生成预览」后再提交", "#b8860b"
            )
        elif version == "up_to_date":
            self.submit_button.setText("提交本次任务")
            self.submit_button.setStyleSheet("")
            self._show_submit_hint("最终图片已是最新版本", "#3a8a3e")
        elif version == "no_preview":
            self.submit_button.setText("提交本次任务")
            self.submit_button.setStyleSheet("")
            self.submit_hint.hide()
        else:  # 执行中
            self.submit_button.setText("提交本次任务")
            self.submit_button.setStyleSheet("")
            self.submit_hint.hide()

    def _show_submit_hint(self, text: str, color: str) -> None:
        self.submit_hint.setText(text)
        self.submit_hint.setStyleSheet(f"color:{color}; font-weight:bold;")
        self.submit_hint.show()

    def _refresh_preview(self, index: int | None = None) -> None:
        if not self.task_id:
            return
        index = self.preview_stack.currentIndex() if index is None else index
        stage = STAGES[index]
        if stage == "extract":
            self.extract_result_viewer.set_images(self._manifest_paths())
        elif stage == "detect":
            self.detect_viewer.set_images(self._manifest_paths())
        elif stage == "rembg":
            self.rembg_viewer.set_images(
                self._manifest_paths(),
                self.store.rembg_preview_output_dir(self.task_id),
                boxes_provider=self._detect_boxes_for,
                region_params_provider=self._current_detect_params,
                thumb_provider=self._page_thumb_for,
            )
        elif stage == "print":
            entries, _doc = self._print_entries()
            self.print_preview.set_entries(entries)
            # 若此前已生成过 PDF，恢复下载按钮状态
            self.print_preview.set_pdf_path(self._latest_print_pdf_path())

    # ------------------------------------------------------------------ 图片选择（extract 结果大图）
    def _image_selected(self, index: int, path_text: str) -> None:
        pass  # 预览组件内部已渲染大图，此处留作扩展

    # ------------------------------------------------------------------ 生成 PDF 列表
    def _print_entries(self) -> tuple[list[dict], dict]:
        """第四步待打印图片：直接使用第三步「提交本次任务」产出的
        stages/rembg 最终图片（已按 area/border 合成），按古籍阅读
        顺序（cover/menu 优先、同编号 r→l、数字自然序）排列。

        列表不再使用源 PDF 缩略图，直接显示 rembg 最终图片本身；
        print.json 仅持久化用户的拖动/删除/插入顺序。
        """
        rembg_files = sorted(
            list_stage_images(self.store.rembg_output_dir(self.task_id)),
            key=lambda p: pdf_custom_sort_key(p.name),
        )
        current_rembg = [str(p) for p in rembg_files]
        current_set = set(current_rembg)
        doc = self.store.load_print_doc(self.task_id)
        snapshot = set(doc.get("rembg_snapshot") or []) if doc else set()
        entries: list[dict] = []

        def _existing(pages) -> list[dict]:
            out, seen = [], set()
            for p in pages or []:
                file_text = p.get("file")
                if not file_text or file_text in seen or not Path(file_text).exists():
                    continue
                out.append({"file": file_text,
                            "label": p.get("label") or Path(file_text).stem})
                seen.add(file_text)
            return out

        if doc and snapshot == current_set and current_set:
            # rembg 产物未变化：沿用用户保存的顺序（拖动/删除/插入结果）
            entries = _existing(doc.get("pages"))
        else:
            # 首次进入，或重新提交后 rembg 产物集合变化：
            # rembg 最终图按阅读顺序排列；旧列表中用户插入的外部图片
            # （不在 rembg 目录）按原顺序追加在末尾
            external = [
                e for e in _existing(doc.get("pages") if doc else None)
                if e["file"] not in current_set
            ]
            entries = [{"file": str(p), "label": p.stem} for p in rembg_files]
            entries.extend(external)
        new_doc = {"rembg_snapshot": current_rembg, "pages": entries}
        self._print_doc_snapshot = new_doc
        if not doc or snapshot != current_set:
            self.store.save_print_doc(self.task_id, new_doc)
        return list(entries), new_doc

    def _save_print_order(self) -> None:
        """列表拖动/删除后持久化顺序。"""
        if not self.task_id:
            return
        entries = self.print_preview.entries()
        doc = getattr(self, "_print_doc_snapshot", None) or {
            "rembg_snapshot": [], "pages": [],
        }
        doc["pages"] = [
            {k: e.get(k) for k in ("file", "label")}
            for e in entries
        ]
        self.store.save_print_doc(self.task_id, doc)
        self.log_view.append(f"待打印列表已更新（{self.print_preview.count()} 页）。")

    def _insert_print_images(self) -> None:
        """插入外部图片到待打印列表末尾。"""
        if not self.task_id:
            return
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "插入图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"
        )
        if not filenames:
            return
        entries = self.print_preview.entries()
        for filename in filenames:
            source = Path(filename)
            entries.append({"file": str(source), "label": source.stem})
        self.store.save_print_pages(self.task_id, entries)
        self.print_preview.set_entries(self._print_entries())
        self.log_view.append(f"已插入 {len(filenames)} 张图片到待打印列表。")

    def _download_print_pdf(self) -> None:
        """将已生成的 PDF 另存到用户选择的位置（默认下载目录、同名文件）。"""
        if not self.task_id:
            return
        # 优先用下载按钮当前绑定的 PDF；否则按最近一次 print 参数解析
        source = getattr(self.print_preview, "_pdf_path", None)
        if source is None or not Path(source).exists():
            source = self._latest_print_pdf_path()
        if source is None or not Path(source).exists():
            self._toast("warning", "无可下载 PDF", "请先执行「生成 PDF」。")
            return
        source = Path(source)
        # 默认保存到系统「下载」目录，文件名与生成的 PDF 一致
        downloads = Path.home() / "Downloads"
        default_dir = downloads if downloads.exists() else Path.home()
        target, _ = QFileDialog.getSaveFileName(
            self, "下载 PDF", str(default_dir / source.name), "PDF 文件 (*.pdf)",
        )
        if not target:
            return
        import shutil
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            self._toast("error", "下载失败", str(exc))
            return
        self._toast("success", "下载完成", f"已保存到：{target}")
        self.log_view.append(f"PDF 已下载到：{target}")

    # ------------------------------------------------------------------ 页面增删
    def delete_selected_page(self) -> None:
        if not self.task_id:
            return
        viewer = (
            self.detect_viewer if self.preview_stack.currentIndex() == 1
            else self.extract_result_viewer
        )
        row = viewer.strip.currentRow()
        if row < 0 or row >= len(self.pages):
            self._toast("warning", "提示", "请先选择要删除的页面。")
            return
        removed = self.pages.pop(row)
        self.store.save_pages(self.task_id, self.pages)
        self.log_view.append(f"已删除页面：{removed.get('label')}")
        self._refresh_preview()
        if self.preview_stack.currentIndex() == 0:
            self._refresh_preview(1)

    def insert_pages(self) -> None:
        if not self.task_id:
            return
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "插入图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"
        )
        if not filenames:
            return
        # 手动插入的图片直接放入 stages/extract，与提取结果同目录
        target_dir = self.store.extract_output_dir(self.task_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        viewer = (
            self.detect_viewer if self.preview_stack.currentIndex() == 1
            else self.extract_result_viewer
        )
        row = max(viewer.strip.currentRow(), -1)
        insert_at = row + 1 if row >= 0 else len(self.pages)
        for filename in filenames:
            source = Path(filename)
            target = target_dir / source.name
            counter = 1
            while target.exists():
                target = target_dir / f"{source.stem}-{counter}{source.suffix}"
                counter += 1
            shutil.copy2(source, target)
            self.pages.insert(insert_at, {"file": str(target), "label": target.stem})
            insert_at += 1
        self.store.save_pages(self.task_id, self.pages)
        self.log_view.append(f"已插入 {len(filenames)} 张图片。")
        self._refresh_preview()
        if self.preview_stack.currentIndex() == 0:
            self._refresh_preview(1)

    # ------------------------------------------------------------------ 工具
    def _toast(self, kind: str, title: str, content: str) -> None:
        factory = getattr(InfoBar, kind, InfoBar.info)
        factory(
            title=title,
            content=content,
            parent=self,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=2500,
        )

    def closeEvent(self, event) -> None:
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1500)
        if self.detect_process and self.detect_process.state() != QProcess.NotRunning:
            self.detect_process.kill()
        self.shutdown_workers()
        event.accept()
