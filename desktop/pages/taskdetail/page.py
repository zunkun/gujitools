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
- rembg_live.RembgLiveMixin  第三步改参数/翻页时只重算当前页的实时预览
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QProcess, Signal
from PySide6.QtWidgets import QWidget

from desktop.services.font_catalog import start_background_scan
from desktop.store import STAGES, STAGE_LABELS
from desktop.workers import WorkerHost
from desktop.pages.taskdetail.detect import DetectMixin
from desktop.pages.taskdetail.history import HistoryMixin
from desktop.pages.taskdetail.manifest import PageListMixin
from desktop.pages.taskdetail.params_draft import ParamDraftMixin
from desktop.pages.taskdetail.print_list import PrintListMixin
from desktop.pages.taskdetail.rembg_live import RembgLiveMixin
from desktop.pages.taskdetail.runner import STATUS_LABELS, StageRunnerMixin
from desktop.pages.taskdetail.submit import SubmitMixin
from desktop.pages.taskdetail.view import DetailViewMixin


class TaskDetailPage(
    StageRunnerMixin,
    SubmitMixin,
    RembgLiveMixin,
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
        #: 「执行权」占用标记。**必须**独立于 self.process：run_stage 收到点击后
        #: 还要校验参数、组装 effects、写运行配置，做完才 QProcess.start()，
        #: 这段同步重活里 self.process 仍是 None——没有这个标记，连点第二下
        #: 就能溜过守卫、起出第二个 worker 子进程（torch 各自加载一遍）。
        #: 存名字（"子任务"/"单页检测"）而非 bool，提示里能直接说清"什么在跑"。
        self._run_claim: str | None = None
        #: 上次**真正启动进程**的时刻（monotonic）。⚠️ 防抖量的是"距上次启动"，
        #: 而**不是**"距上次受理"：一次没跑起来的尝试（参数错、无输出、无需续跑、
        #: 提交被前置条件拒绝）不该罚掉用户紧接着的下一次点击——"提交被拒 →
        #: 马上点生成预览"就会踩到（rembg 自测真的红了）。
        self._run_launched_at = 0.0
        #: 最近一次的阶段状态：执行权变化时要重刷按钮，但不值得为此再读一次盘
        self._last_stage_state: dict = {"status": "pending"}
        self.detect_cache: dict[str, list[tuple] | None] = {}
        self._last_error_line: str | None = None
        self._extract_seen = 0  # 提取过程中已展示的结果页数
        self._init_ui()
        # 参数暂存：面板报到"用户改了参数"就防抖写 drafts/<阶段>.json
        self._install_draft_hooks()
        # 第三步实时预览：改参数/翻页时只重算当前页（见 rembg_live.RembgLiveMixin）
        self._init_rembg_live()
        # 字体列表后台预热：一进任务（还在第一/二/三步）就起后台线程扫系统
        # 字体，等用户翻到第四步时列表已就绪。扫描全局只跑一次、结果写磁盘
        # 缓存，且**不阻塞**任何界面操作（详见 desktop.services.font_catalog）。
        start_background_scan()

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
        # 实时预览状态跨任务必须清干净：临时目录里的旧图 + "哪些页算过"的记忆
        self._reset_rembg_live()
        self.pdf_page_count = 0
        self._history_prefilled: set[str] = set()
        self._history_params: list[dict] = []
        # 运行态引用清零：避免上一个任务的 run_id/running_stage 影响新任务
        self.run_id = None
        self.running_stage = None
        self.cancel_requested = False
        # 执行权也要清：切任务时上一个任务若卡在"已受理未启动"，标记不清会
        # 让新任务的执行按钮一直是灰的（且没有任何进程能来释放它）
        self._run_claim = None
        self._run_launched_at = 0.0
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

    #: 执行按钮的防抖窗口(ms)：连击/双击在窗口内的第二次直接**静默**吞掉
    #: （不弹提示——手快的人否则会看到一串"任务进行中"）。取 400ms：够盖住
    #: 鼠标双击间隔（通常 ≤250ms），又不至于让人感觉"点了没反应"。
    RUN_DEBOUNCE_MS = 400

    def _busy_label(self) -> str | None:
        """当前有执行在跑就返回它的名字，空闲返回 None（按钮状态的唯一判据）。

        ⚠️ 只看 ``self.process`` 会有两个盲区，所以这里分两步判断：

        1. **先看进程实况**（硬事实）：子任务进程、单页检测进程任一在跑就是在忙。
        2. **再看受理标记**，且**只在还没有任何进程对象时**才算数：
           - 受理窗口期（点下去了，进程还没 start）→ 拦住，这正是漏点；
           - 进程刚结束、``finished`` 尚未派发完的瞬间 → 此时 ``self.process``
             已存在，直接放行——否则"中断后续跑"这类连招会像点了没反应。
        """
        for attr, label in (("process", "子任务"), ("detect_process", "单页检测")):
            proc = getattr(self, attr, None)
            if proc is not None and proc.state() != QProcess.NotRunning:
                return label
        if self._run_claim and self.process is None and self.detect_process is None:
            return self._run_claim
        return None

    def _stage_running(self) -> bool:
        """阶段子任务（含"已受理、进程尚未 start"的窗口期）是否在跑。

        比 :meth:`_busy_label` 更窄：单页检测**不算**，因为「中断」按钮只杀
        子任务进程，检测在跑时给它点亮的会是个杀不掉东西的按钮。
        """
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            return True
        return bool(
            self._run_claim == "子任务"
            and self.process is None
            and self.detect_process is None
        )

    def _acquire_run(self, what: str, *, replace: tuple = ()) -> bool:
        """领取执行权；拿不到返回 False，调用方直接 ``return``。

        三种拒绝情形：

        - 已有别的执行在跑 → 提示后拒绝（这是"不要二次执行"的正题）；
        - ``replace`` 里列出的执行在跑 → **允许顶替**。单页检测换一页重检就是
          这样：旧进程由 ``_start_detect`` 先断信号再杀，始终只有一个在跑；
        - 距上次受理不足 :data:`RUN_DEBOUNCE_MS` → 静默拒绝（连击的第二下）。
        """
        busy = self._busy_label()
        if busy and busy not in replace:
            self._toast(
                "warning", "任务进行中", f"{busy}正在执行，请等待完成或先中断。"
            )
            return False
        now = time.monotonic()
        if (now - self._run_launched_at) * 1000 < self.RUN_DEBOUNCE_MS:
            return False
        self._run_claim = what
        # 立刻把按钮置灰：别等 proc.start() 之后那次 _refresh_stage_views
        self._refresh_run_buttons()
        return True

    def _mark_run_launched(self) -> None:
        """记下"进程真的起来了"——防抖窗口从这里开始计时（见 `_run_launched_at`）。

        在 ``QProcess.start()`` 之后调用。放在这里而不是受理处，是为了让
        "没能跑起来的受理"完全不占用防抖预算。
        """
        self._run_launched_at = time.monotonic()

    def _release_run(self) -> None:
        """释放执行权（进程结束 / 被中断 / 启动失败都要调）。"""
        self._run_claim = None
        self._refresh_run_buttons()

    def _refresh_run_buttons(self) -> None:
        """执行权变化后重刷按钮；复用最近一次的阶段状态，不额外读盘。"""
        self._update_run_buttons(self._last_stage_state)

    def _update_run_buttons(self, state: dict) -> None:
        self._last_stage_state = state
        running = self._busy_label() is not None
        self.run_button.setEnabled(not running)
        self.resume_button.setEnabled(
            not running and state["status"] in ("cancelled", "failed", "success")
        )
        self.cancel_button.setEnabled(self._stage_running())
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
