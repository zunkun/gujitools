# -*- coding: utf-8 -*-
"""任务详情页：顶部步骤条 + 左侧多标签预览 + 右侧阶段控制面板。

预览区按阶段组织：
- extract：[PDF 预览 | 提取结果] 双标签页；
- detect：图片预览，叠加显示每张图的检测框位置；
- rembg：原图 / 去底结果对比；
- print：输出 PDF 预览。

本文件只保留页面骨架（任务切换、阶段切换、状态刷新），
其余职责按功能分文件（均位于 desktop/pages/taskdetail/）：
- view.DetailViewMixin       UI 组装（头部/步骤条/预览区/控制列/日志）
- manifest.PageListMixin     页面清单、缩略图、页面增删
- history.HistoryMixin       历史执行配置回填（暂存优先）
- params_draft.ParamDraftMixin 参数暂存（改过没执行也不丢）
- submit.SubmitMixin         rembg 提交控制器与按钮状态
- print_list.PrintListMixin  第四步待打印列表
- runner.StageRunnerMixin    阶段执行（worker 子进程编排）
- detect.DetectMixin         detect 检测控制
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QProcess, Signal
from PySide6.QtWidgets import QWidget

from desktop.store import STAGES, STAGE_LABELS
from desktop.workers import WorkerHost
from desktop.pages.taskdetail.detect import DetectMixin
from desktop.pages.taskdetail.history import HistoryMixin
from desktop.pages.taskdetail.manifest import PageListMixin
from desktop.pages.taskdetail.params_draft import ParamDraftMixin
from desktop.pages.taskdetail.print_list import PrintListMixin
from desktop.pages.taskdetail.runner import STATUS_LABELS, StageRunnerMixin
from desktop.pages.taskdetail.submit import SubmitMixin
from desktop.pages.taskdetail.view import DetailViewMixin


class TaskDetailPage(
    StageRunnerMixin,
    SubmitMixin,
    PrintListMixin,
    ParamDraftMixin,
    HistoryMixin,
    DetectMixin,
    PageListMixin,
    DetailViewMixin,
    QWidget,
    WorkerHost,
):
    """任务详情页：由多个 Mixin 组合，固定四阶段流程。

    编排 extract→detect→rembg→print 四阶段；各职责（预览、清单、历史、
    提交、执行、检测）分散到同级 Mixin，本类只持有任务切换与阶段切换骨架。
    """

    back_requested = Signal()

    def __init__(self, store, parent=None):
        """初始化详情页：建 worker 宿主、清运行态并组装 UI。

        创建 store 引用与 _init_worker_host 后台线程宿主；初始化全部运行态
        字段（task_id/process/run_id/detect_cache 等）为空，再构建界面骨架。
        """
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
        # 参数暂存：面板报到"用户改了参数"就防抖写 drafts/<阶段>.json
        self._install_draft_hooks()

    # ------------------------------------------------------------------ 任务切换
    def set_task(self, task_id: str) -> None:
        """切换当前任务：复位所有阶段面板与运行态，避免跨任务泄漏。

        加载任务后先调用各面板 reset_to_default 清掉上一任务手改参数，再清
        detect 缓存/运行态引用并刷新清单与预览；防止参数或 run_id 串到新任务。
        """
        task = self.store.get_task(task_id)
        if not task:
            return
        # ⚠️ 必须在覆盖 task_id 之前落盘：暂存要写进"上一个任务"的目录
        self._flush_param_drafts()
        self.task_id = task_id
        # ⚠️ 一律用任务目录里的**备份** PDF，不用索引里的 source_path：
        # 源文件在用户磁盘上会被移动/改名/删除，一走就「渲染失败」；
        # 备份随任务走，删除任务时一起清掉，任务才是自包含的。
        # 备份缺失但源还在（老任务/复制失败）时 ensure_source_copy 顺手补一份。
        self.source_path = self.store.ensure_source_copy(task_id) or Path(
            task["source_path"]
        )
        if not self.source_path.exists():
            self._toast(
                "error",
                "PDF 缺失",
                f"任务备份与源文件都不存在：{task['source_path']}\n"
                "请重新导入该 PDF（或把原文件放回原处后重开任务）。",
            )
        self.detail_title.setText(task["name"])
        self.source_label.setText(self.source_path.name)
        # 切任务时先把各阶段面板复位到默认：这些面板是长生命周期控件，
        # 上个任务手改过的参数（area/border/type/zoom…）否则会带到新任务上，
        # 而新任务往往没有历史记录可覆盖回来
        for index in range(self.control_stack.count()):
            self.control_stack.widget(index).reset_to_default()
        # 第四步默认 PDF 名/古籍名随源 PDF 名派生（xxx[重制].pdf / xxx）；
        # 若该任务已有 print 历史，进入第四步时会再回填历史配置
        self.control_stack.widget(3).set_source_defaults(self.source_path.stem)
        self.log_view.clear()
        self.detect_cache.clear()
        self.pdf_page_count = 0
        self._history_prefilled: set[str] = set()
        self._history_params: list[dict] = []
        # 运行态引用清零：避免上一个任务的 run_id/running_stage 影响新任务
        self.run_id = None
        self.running_stage = None
        self.cancel_requested = False
        self._last_error_line = None
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
        # 离开前把待写暂存落盘：task_id 马上被清掉，之后再写就找不到任务了
        self._flush_param_drafts()
        self.task_id = None
        self.source_path = None
        # 释放 PDF：不释放的话回到列表删除该任务时，rmtree 可能撞上文件占用
        self.source_pdf_viewer.set_pdf(None)
        self.back_requested.emit()

    # ------------------------------------------------------------------ 阶段切换/状态
    def current_stage(self) -> str:
        """返回当前所处阶段的 key（extract/detect/rembg/print）。

        以步骤条高亮下标映射到 STAGES 序列；下标为负时按 0 兜底处理。
        """
        return STAGES[max(self.step_bar._current, 0)]

    def _select_stage(self, index: int) -> None:
        # 离开当前阶段前把待写暂存落盘（防抖未到期就走人不该丢改动）
        self._flush_param_drafts()
        self.step_bar.set_current(index)
        self.control_stack.setCurrentIndex(index)
        self.preview_stack.setCurrentIndex(index)
        # 步骤三：主按钮为「生成预览」，下方另有「提交本次任务」；
        # 步骤四：主按钮为「生成 PDF」（按版面编辑器里的逐图坐标生成）；
        # 其余阶段保持「执行本子任务」，提交按钮隐藏。
        stage = STAGES[index]
        if stage == "rembg":
            self.run_button.setText("生成预览")
        elif stage == "print":
            self.run_button.setText("生成PDF")
        else:
            self.run_button.setText("执行本子任务")
        self.submit_button.setVisible(stage == "rembg")
        self._apply_control_width()
        self._refresh_stage_views()
        self._refresh_preview(index)
        self._restore_stage_params(index)
        self._refresh_history_options()
        if STAGES[index] == "detect":
            # 整页开关是 area=4 的入口，切回第二步时按当前 area 回填
            self._sync_whole_page_checkbox()

    def _refresh_stage_views(self) -> None:
        if not self.task_id:
            return
        states = self.store.stage_states(self.task_id)
        self.step_bar.reset_statuses()
        for index, stage in enumerate(STAGES):
            state = states[stage]
            progress = (state["done"], state["total"]) if state["total"] else None
            # 步骤条只表达"第几步 / 执行到哪"：completed 决定徽标是否打勾，
            # status 决定副标题文案与颜色（重试失败不会让已完成步骤退回未完成）
            self.step_bar.set_step_status(
                index, state["status"], progress, completed=state["completed"]
            )
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

    # ------------------------------------------------------------------ 预览刷新
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

    # ------------------------------------------------------------------ 工具
    def _toast(self, kind: str, title: str, content: str) -> None:
        from qfluentwidgets import InfoBar, InfoBarPosition

        factory = getattr(InfoBar, kind, InfoBar.info)
        factory(
            title=title,
            content=content,
            parent=self,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=2500,
        )

    def closeEvent(self, event) -> None:
        """关闭页面时杀掉并等待 worker/detect 子进程，并关停所有后台线程。

        详情页持有 QProcess 与多个 WorkerHost 线程；先 kill 正在跑的执行/
        检测子进程并等待（最多 1.5s），再 shutdown_all_workers 收尾其余线程，
        最后接受关闭事件，避免解释器退出时被强杀崩溃。
        """
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1500)
        if self.detect_process and self.detect_process.state() != QProcess.NotRunning:
            self.detect_process.kill()
        self._flush_param_drafts()
        self.shutdown_all_workers()
        event.accept()

    def shutdown_all_workers(self) -> None:
        """连同各预览控件自己的缩略图线程一起收尾。

        页面自身、PDF 预览、打印预览、缩略图条分别持有 WorkerHost 的线程，
        只停页面的会让其余线程在解释器退出时被强杀（偶发崩溃/卡顿）。
        """
        self.shutdown_workers()
        for widget in self.findChildren(QWidget):
            shutdown = getattr(widget, "shutdown_workers", None)
            if callable(shutdown):
                try:
                    shutdown()
                except RuntimeError:
                    pass  # 控件已析构
