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
        self.print_preview = PrintPreviewWidget()
        self.print_preview.order_changed.connect(self._save_print_order)
        self.print_preview.insert_requested.connect(self._insert_print_images)
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
        rembg_panel.area.currentTextChanged.connect(
            lambda *_: self._refresh_reference_boxes()
        )
        rembg_panel.border.textChanged.connect(
            lambda *_: self._refresh_reference_boxes()
        )

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
        self.resume_button = PushButton(FIF.UPDATE, "继续执行（跳过已完成）")
        self.resume_button.clicked.connect(lambda: self.run_stage(resume=True))
        self.cancel_button = PushButton(FIF.CLOSE, "中断执行")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_stage)
        control.addWidget(self.run_button)
        control.addWidget(self.resume_button)
        control.addWidget(self.cancel_button)
        control.addStretch()

        # 控制面板限宽：参数表单不需要太宽，把空间留给预览区
        control_widget = QWidget()
        control_widget.setLayout(control)
        control_widget.setMaximumWidth(300)
        control_widget.setMinimumWidth(260)
        body.addWidget(self.preview_stack, 1)
        body.addWidget(control_widget)

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
        self._refresh_stage_views()
        self._refresh_preview(index)
        self._restore_last_run_params(index)
        self._refresh_history_options()

    # ------------------------------------------------------------------ 历史执行配置
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
            params = {
                k: v for k, v in history[0].get("parameters", {}).items()
                if k not in ("input", "output", "workers", "clean", "resume", "_effects")
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
        params = {
            k: v for k, v in self._history_params[index].items()
            if k not in ("input", "output", "workers", "clean", "resume", "_effects")
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
                self.store.rembg_output_dir(self.task_id),
                boxes_provider=self._detect_boxes_for,
                region_params_provider=self._current_detect_params,
                thumb_provider=self._page_thumb_for,
            )
        elif stage == "print":
            entries, _doc = self._print_entries()
            self.print_preview.set_entries(entries)

    # ------------------------------------------------------------------ 图片选择（extract 结果大图）
    def _image_selected(self, index: int, path_text: str) -> None:
        pass  # 预览组件内部已渲染大图，此处留作扩展

    # ------------------------------------------------------------------ 生成 PDF 列表
    def _print_entries(self) -> tuple[list[dict], dict]:
        """待打印条目（与 PDF 页一一对应）+ 布局快照文档。

        print.json 缺失或 area/border 快照与当前面板不一致时，
        从去底色结果 + 检测框重新派生（area=1 每框一条 -r/-l，
        area=2/3 双框取并集、单框对称）。"""
        area, border = self._current_detect_params()
        doc = self.store.load_print_doc(self.task_id)
        if not doc or doc.get("area") != area or doc.get("border") != border or not doc.get("pages"):
            entries = []
            for p in list_stage_images(self.store.rembg_output_dir(self.task_id)):
                boxes = self._valid_boxes(self._detect_boxes_for(str(p)))
                stem = p.stem
                if area == 1 and len(boxes) == 2:
                    # 右框在前（古籍阅读顺序 r → l）
                    entries.append({"file": str(p), "label": f"{stem}-r", "box": boxes[1], "parea": 1})
                    entries.append({"file": str(p), "label": f"{stem}-l", "box": boxes[0], "parea": 1})
                elif area in (2, 3) and len(boxes) == 2:
                    union = [min(b[0] for b in boxes), min(b[1] for b in boxes),
                             max(b[2] for b in boxes), max(b[3] for b in boxes)]
                    entries.append({"file": str(p), "label": stem, "box": union, "parea": 1})
                elif len(boxes) == 1:
                    entries.append({"file": str(p), "label": stem, "box": boxes[0],
                                    "parea": 2 if area in (2, 3) else 1})
                else:
                    entries.append({"file": str(p), "label": stem, "box": None, "parea": 1})
            doc = {"area": area, "border": border, "pages": entries}
            self._print_doc_snapshot = doc
            self.store.save_print_doc(self.task_id, doc)
        self._print_doc_snapshot = doc
        entries = []
        for p in doc["pages"]:
            entry = dict(p)
            if p.get("box"):
                entry["effect"] = {"boxes": [p["box"]], "area": p.get("parea", 1),
                                   "border": doc.get("border")}
                entry["thumb"] = self._page_thumb_for(
                    p["file"], p["box"], p.get("parea", 1), doc.get("border")
                )
            else:
                entry["effect"] = None
                entry["thumb"] = self._page_thumb_for(p["file"])
            entries.append(entry)
        return entries, doc

    def _save_print_order(self) -> None:
        """列表拖动/删除后持久化顺序（保留条目的框/parea 元数据）。"""
        if not self.task_id:
            return
        entries = self.print_preview.entries()
        doc = getattr(self, "_print_doc_snapshot", None) or {
            "area": 1, "border": None, "pages": [],
        }
        doc["pages"] = [
            {k: e.get(k) for k in ("file", "label", "box", "parea")}
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
