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

from PySide6.QtCore import QProcess, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractSlider, QAbstractSpinBox, QApplication,
    QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QWidget,
)

from desktop.services.font_catalog import start_background_scan
from desktop.services.stale_chain import stale_upstream
from desktop.store import STAGES, STAGE_LABELS
from desktop.ui import theme as T
from desktop.ui.widgets import apply_to, bold_button
from desktop.workers import CopySourceWorker, WorkerHost, connect_queued
from desktop.pages.taskdetail.detect import DetectMixin
from desktop.pages.taskdetail.history import HistoryMixin
from desktop.pages.taskdetail.manifest import PageListMixin
from desktop.pages.taskdetail.params_draft import ParamDraftMixin
from desktop.pages.taskdetail.print_list import PrintListMixin
from desktop.pages.taskdetail.rembg_live import RembgLiveMixin
from desktop.pages.taskdetail.runner import STATUS_LABELS, StageRunnerMixin
from desktop.pages.taskdetail.submit import SubmitMixin
from desktop.pages.taskdetail.view import DetailViewMixin


#: 方向键**不抢**的控件：它们的 ←/→ 有本职工作（移光标/改值/翻选择）。
#: 焦点落在这些控件上时方向键归它们；落在按钮/预览/页面本身时才翻页。
_ARROW_OCCUPIED = (
    QLineEdit, QTextEdit, QPlainTextEdit,          # 文本光标移动
    QComboBox, QAbstractSpinBox,                   # 改值
    QAbstractItemView,                             # 移动条目选择
    QAbstractSlider,                               # 滚动
)


def _arrow_free_to_navigate() -> bool:
    """当前焦点控件是否可以把 ←/→ 让给「切换页面」。"""
    focus = QApplication.focusWidget()
    if focus is None:
        return True
    return not isinstance(focus, _ARROW_OCCUPIED)


#: 阶段 key → 主预览控件属性名（←/→ 方向键翻页的目标；
#: 四个步骤的主预览都支持「焦点在哪里，哪里就切换」）
_STAGE_PREVIEW_ATTRS = {
    "extract": "extract_result_viewer",
    "detect": "detect_viewer",
    "rembg": "rembg_viewer",
    "print": "print_preview",
}


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

    #: 源文件副本缺失时，进详情页后延时多久再后台补副本（毫秒）。
    #: 这段时间足够导入流程先落地副本；这里只为「导入时复制失败 / 老任务
    #: 没有备份」兜底。绝不能在主线程里同步复制——800MB 的书会把进页面
    #: 卡住几秒到几十秒（用户报的就是它）。
    SOURCE_BACKUP_DELAY_MS = 4000

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
        #: 源文件副本缺失时的「延时后台补一份」定时器（见 _schedule_source_backup）
        self._backup_timer = QTimer(self)
        self._backup_timer.setSingleShot(True)
        self._backup_timer.timeout.connect(self._run_source_backup)
        self._backup_task_id: str | None = None
        #: 「按源 PDF 名派生第四步默认 PDF 名/古籍名」的挂起值：第四步面板是
        #: 惰性的，set_task 只记下源名，等面板真被建出来再应用（见 view.py
        #: 的 _apply_pending_source_defaults）
        self._pending_source_stem: str | None = None
        #: 最近一次的阶段状态：执行权变化时要重刷按钮，但不值得为此再读一次盘
        self._last_stage_state: dict = {"status": "pending"}
        self.detect_cache: dict[str, list[tuple] | None] = {}
        self._last_error_line: str | None = None
        self._extract_seen = 0  # 提取过程中已展示的结果页数
        #: 最近一次 progress 事件 (done, total)。⚠️ 这里必须给**实例级默认值**：
        #: 它平时在"开始执行"路径里赋值（runner.py），但进程收尾
        #: （``_worker_finished``，含看门狗兜底）会读它——若收尾先于任何一次
        #: 正常启动（护栏就是这么直接调的），没有默认值就是 AttributeError。
        self._last_progress: tuple[int, int] = (0, 0)
        #: 「上游重跑 → 本步产物已过期」的判定缓存（键为下游阶段名）。
        #: ⚠️ **只在运行收尾/切任务时**重算：判定要读整份 runs.json，而
        #: _refresh_stage_views 在运行期每 ≤200ms 就跑一次，绝不能放那儿。
        self._stale_notices: dict[str, dict] = {}
        #: worker stdout 的半行缓冲（管道读取会在任意字节处截断，见
        #: StageRunnerMixin._consume_worker_stdout）
        self._stdout_tail = ""
        self._init_ui()
        # 进度事件的界面刷新节流器（见 StageRunnerMixin._PROGRESS_UI_MS）
        self._init_progress_ui()
        # 页面尺寸/检测框的攒批落盘（见 StageRunnerMixin._ANNOT_FLUSH_MS）
        self._init_annotation_batch()
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
        # ⚠️ 复位**跨任务会串味**的两个第四步状态（2026-09-26 审计）：
        #    ① `_print_dirty`：在任务 A 拖过版面，打开任务 B 时 B 的第四步会误显示
        #       「● 版面已修改，点击「生成 PDF」生效」并把主按钮加粗；
        #    ② print 面板的 `_last_applied`（供「放弃本次修改」回填）：不重置的话
        #       在 B 点「放弃本次修改」会把 A 的参数（含 A 派生的 pdf_name/title_text）
        #       回填进来 —— 后续可能用 A 的名字生成 B 的 PDF。
        #    ⚠️ 面板是惰性的：**只能挂"待复位"标记**，等它真被建出来时再应用，
        #    绝不能在这里 `self.control_stack.widget(3)` 把它拽出来。
        self._print_dirty = False
        self._pending_print_reset = True
        self._apply_pending_print_reset()
        # ⚠️ 必须在覆盖 task_id 之前落盘：暂存要写进"上一个任务"的目录
        self._flush_param_drafts()
        # 标注攒批同理：攒着的尺寸/框属于**上一个任务**，切换后写就串任务了
        self._flush_annotations()
        self.task_id = task_id
        # ⚠️ 一律用任务目录里的**备份** PDF，不用索引里的 source_path：
        # 源文件在用户磁盘上会被移动/改名/删除，一走就「渲染失败」；
        # 备份随任务走，删除任务时一起清掉，任务才是自包含的。
        #
        # ⚠️⚠️ **这里绝不做同步复制**：老实现是 `ensure_source_copy()`，副本
        # 缺失时**在主线程里**把整个 PDF 复制一遍——一本 800MB 的书就是进页面
        # 卡住几秒到几十秒（用户报「进详情页要等一会」的真凶）。副本由导入
        # 后台任务负责落盘；这里只用**已落地**的副本，没有就先用源文件（两者
        # 二进制相同，渲染结果一致），后台补备份见 _schedule_source_backup()。
        self.source_path = self.store.source_copy_path(task_id) or Path(
            task["source_path"]
        )
        self._schedule_source_backup(task_id)
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
        # 而新任务往往没有历史记录可覆盖回来。
        # ⚠️ 四个面板都是**惰性**的，这里必须走 `peek()`（不触发构造）：直接
        #    `widget(i).reset_to_default()` 会经属性转发把面板全部现造出来，
        #    进详情页的时间就又回到"要为没进去的步骤买单"（用户明确要求
        #    第 2/3/4 步谁进去谁才建）。没建的面板本来就没动过，无需复位。
        for index in range(self.control_stack.count()):
            host = self.control_stack.widget(index)
            peek = getattr(host, "peek", None)
            panel = peek() if callable(peek) else host
            if panel is not None:
                panel.reset_to_default()
        # 第四步默认 PDF 名/古籍名随源 PDF 名派生（xxx[重制].pdf / xxx）；
        # ⚠️ 同样不能在这里碰面板本体：记下源名，面板真被建出来时再应用
        #    （见 _init_ui 里挂的 add_created_hook）。已有 print 历史时它会在
        #    进入第四步时再回填历史配置。
        self._pending_source_stem = self.source_path.stem
        self._apply_pending_source_defaults()
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
        # 换任务就得重算"上游比下游新"的判定缓存（读的是新任务的 runs.json）
        self._refresh_stale_notices()
        self._refresh_stage_views()
        self._select_stage(0)

    def _schedule_source_backup(self, task_id: str) -> None:
        """副本缺失且源还在时，**延时在后台**补一份（绝不在主线程里复制）。

        延时 `SOURCE_BACKUP_DELAY_MS`：导入流程本身就在复制，这里只为
        「导入时复制失败 / 早期版本没有备份的老任务」兜底，不该和正在跑的
        导入任务重复劳动（`copy_file_atomic` 各自的临时文件不同名，重复复制
        不会写坏文件，但白读白写一遍 800MB）。
        """
        if self.store.source_copy_path(task_id) is not None:
            return
        if not self._source_exists(task_id):
            return  # 源也没了：set_task 已经弹过「PDF 缺失」
        self._backup_task_id = task_id
        self._backup_timer.start(self.SOURCE_BACKUP_DELAY_MS)

    def _source_exists(self, task_id: str) -> bool:
        task = self.store.get_task(task_id)
        if not task:
            return False
        return Path(str(task.get("source_path") or "")).is_file()

    def _run_source_backup(self) -> None:
        """定时器到期：真正去后台复制（用户此时早就在用界面了）。"""
        task_id = self._backup_task_id
        self._backup_task_id = None
        if not task_id or self.task_id != task_id:
            return
        if self.store.source_copy_path(task_id) is not None:
            return  # 导入任务已经补上了
        task = self.store.get_task(task_id)
        if not task:
            return
        source = Path(str(task.get("source_path") or ""))
        if not source.is_file():
            return
        target = self.store.task_dir(task_id) / source.name
        self.run_worker(
            lambda: CopySourceWorker(source, target),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.finished,
                    lambda _path: self._on_source_backup_ready(),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_source_backup_ready(self) -> None:
        """副本补好了：若用户还在本任务上，把当前 PDF 换成副本。

        ⚠️ 只有在**还在看同一个任务**时才能换（定时器/线程回来时用户可能
        已经切走或返回列表了）。
        """
        if not self.task_id:
            return
        copy = self.store.source_copy_path(self.task_id)
        if copy is None or self.source_path == copy:
            return
        self.source_path = copy
        self.source_label.setText(copy.name)
        self.source_pdf_viewer.set_pdf(
            copy, cache_dir=self.store.source_thumbnails_dir(self.task_id)
        )

    def _on_back(self) -> None:
        if self.process and self.process.state() != QProcess.NotRunning:
            self._toast("warning", "任务进行中", "请先中断当前子任务再返回。")
            return
        # 离开前把待写暂存落盘：task_id 马上被清掉，之后再写就找不到任务了
        self._flush_param_drafts()
        self._flush_annotations()
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

    def navigate_by_arrow(self, forward: bool) -> bool:
        """方向键切换当前步骤的页面（主窗口 ←/→ 转发入口）。

        返回是否消费（主窗口据此决定要不要继续处理）。
        「焦点在哪里，哪里就切换」：
        - 焦点在**输入类控件**上时不抢（`_ARROW_OCCUPIED` 表——参数输入区
          的方向键移光标/改值，用户 18:30 明确那里不需要切换）；
        - 焦点在预览弹窗里则由弹窗自己的窗口级 QShortcut 接管；
        - 四个步骤的主预览都支持（移动缩略图条当前行，联动预览刷新）。
        """
        if not _arrow_free_to_navigate():
            return False
        preview = getattr(
            self, _STAGE_PREVIEW_ATTRS.get(self.current_stage(), ""), None
        )
        if preview is None:
            return False
        preview.navigate(forward)
        return True

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """←/→ 切换当前步骤的页面（焦点链不消费时兜底到达这里）。"""
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) \
                and self.navigate_by_arrow(event.key() == Qt.Key.Key_Right):
            event.accept()
            return
        super().keyPressEvent(event)

    def _select_stage(self, index: int) -> None:
        # 离开当前阶段前把待写暂存落盘、把未提交的版面拖动补发
        # （防抖未到期/拖住未松手就走人不该丢改动）
        self.flush_layout_pending()
        self._flush_param_drafts()
        self.step_bar.set_current(index)
        # ⚠️ 面板是**惰性**的：用户切到这一步，就现在把它建出来（不建的话
        #    左侧控制区是空白）。反过来，没切过来的步骤一直不建——这正是
        #    用户 2026-09-25 要求的"谁进去谁才建"。
        target = self.control_stack.widget(index)
        if hasattr(target, "peek") and target.peek() is None:
            target.panel  # noqa: B018 - 触发构造
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
        self._show_running_submit_on_steps(states)
        stage = self.current_stage()
        self._apply_stage_state(stage, states[stage])
        self._update_run_buttons(states[stage])

    def _show_running_submit_on_steps(self, states: dict) -> None:
        """「提交本次任务」（rembg_submit）在跑时，把**第三步**的步骤条显示成
        「执行中 · 42/91」。

        ⚠️ 提交不是独立步骤（STAGES 里没有它），但它归属第三步（见
        ``desktop.store.tasks.STAGE_STEP``）。进度条与状态文案只服务当前显示的
        步骤（见 ``StageRunnerMixin._progress_belongs_here``），所以用户一旦切到
        别的步骤，就只剩步骤条这一处还能看出"还有活儿在跑"——不补这一句，
        切走之后界面上就完全看不出提交还在执行了。
        """
        if self.running_stage != "rembg_submit":
            return
        done, total = self._last_progress
        self.step_bar.set_step_status(
            2, "running", (done, total) if total else None,
            completed=states["rembg"]["completed"],
        )

    def _apply_stage_state(self, stage: str, state: dict) -> None:
        if self._own_step_running():
            # 本步自己的活儿正在跑：进度条与文案此刻归 _on_worker_progress 所有。
            # 这里若照旧刷成"上一次运行"的 done/total，就会和进度文案每 200ms
            # 互相覆盖一次（状态文字来回跳，看着像卡住）。跑完 running_stage
            # 清空，下一次刷新自然回到真实状态。
            return
        total, done = state["total"], state["done"]
        if total:
            self.stage_progress.setRange(0, total)
            self.stage_progress.setValue(min(done, total))
        else:
            self.stage_progress.setRange(0, 1)
            self.stage_progress.setValue(0)
        # 「产物需要重新生成」优先于"最近一次的结果"：改了版面、或上游又跑过
        # 一次之后，再显示「成功」会误导（用户看着"成功"就把旧产物发出去了）
        notice = self._regenerate_notice(stage)
        if notice:
            self._set_stage_status(notice, alert=True)
        else:
            self._set_stage_status(
                f"{STAGE_LABELS[stage]}："
                f"{STATUS_LABELS.get(state['status'], state['status'])}"
            )

    def _set_stage_status(self, text: str, alert: bool = False) -> None:
        """写状态行文案，并选颜色：``alert=True`` 用警示色（红），否则常规柔和色。

        ⚠️ 颜色必须在这里**一起**写：状态行是同一个 QLabel，被三处抢着用
        （常规状态 / 版面已修改 / 上游已重跑）。只改文字不重置颜色，就会出现
        "过期提示的红字留在下一次的常规状态上"。
        """
        self.stage_status.setText(text)
        apply_to(
            self.stage_status, T.SIZE_CAPTION,
            color=T.DANGER if alert else T.INK_SOFT,
        )

    # ---------------------------------------------------- 上游重跑 → 产物过期
    def _refresh_stale_notices(self) -> None:
        """重算"上游比本步新"的判定缓存。

        ⚠️ 只在**运行收尾**与**切任务**时调，别放进 ``_refresh_stage_views`` 的
        热路径：判定要读整份 runs.json，而那里运行期每 ≤200ms 就跑一次。
        """
        if not self.task_id:
            self._stale_notices = {}
            return
        # 一次读全（五个阶段逐个 list_stage_runs 会把 runs.json 读五遍）
        self._stale_notices = stale_upstream(
            self.store.all_stage_runs(self.task_id)
        )

    def _regenerate_notice(self, stage: str) -> str | None:
        """本步产物"需要重新生成"的提示文案（没有则 None）。

        两种来源，顺序即优先级：

        1. 第四步的逐图坐标刚被版面编辑器改过（``_print_dirty``）——用户的直接
           改动，最该被看见；
        2. **上游重新执行过**（``services/stale_chain``）——本步产物是那之前生成的，
           可能已经不是最新参数下的结果。
        """
        if stage == "print" and getattr(self, "_print_dirty", False):
            return "● 版面已修改，点击「生成 PDF」生效"
        info = (self._stale_notices or {}).get(stage)
        if not info:
            return None
        label = STAGE_LABELS.get(info["stage"], info["stage"])
        when = time.strftime("%H:%M", time.localtime(info["upstream_at"]))
        return (
            f"● 上游已重新执行（{label} · {when}），"
            "本步产物可能已过期，请重新生成"
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
        self._apply_regenerate_highlight()
        self._update_submit_button(running)

    def _apply_regenerate_highlight(self) -> None:
        """本步产物过期（改了版面 / 上游又跑过）时把主按钮加粗高亮。

        与第三步「提交本次任务（有新版本）」同一套视觉语言：文案里点明该动作，
        但**不阻止**用户先干别的——只提示，不自动重跑。
        """
        pending = self._regenerate_notice(self.current_stage()) is not None
        # ⚠️ 加粗走 setFont，别用 setStyleSheet("…{font-weight:bold}") —— 那会把
        # qfluent 按钮的整套 qss（含 hasIcon=true 的 36px 左边距）整串抹掉，
        # 图标就画到文字上了（见 desktop.ui.widgets.bold_button）
        bold_button(self.run_button, pending)

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
        # ⚠️ 先把「拖住图片框不松手」的版面改动补发出去，再走落盘与线程收尾：
        #    rect_changed 只在 mouseRelease 发，不补发就会**丢掉这次拖动**
        #    （2026-09-26 审计）。
        self.flush_layout_pending()
        self._flush_param_drafts()
        self.shutdown_all_workers()
        event.accept()

    def flush_layout_pending(self) -> None:
        """把各处"未提交的界面改动"补发/落盘（关窗口、切步骤、切页前都要调）。

        目前是第四步的版面画布：拖动中不落盘，只在松手/补发时提交。

        ⚠️ **只按具体的类 `findChildren`，绝不用 `getattr(widget, ...)` 探测能力**：
        四个阶段面板是 `LazyPanelHost`，属性转发（`__getattr__`）会**立刻把面板
        构造出来**——那就把用户要求的「不进去就不建」破坏掉了。（2026-09-26 自己
        踩到：写成 `getattr(w, "flush_pending", None)` 之后，`detail_prewarm`
        护栏直接红成"四个面板全建"。）
        """
        from desktop.components.viewers.print_layout_canvas import PrintLayoutCanvas

        for canvas in self.findChildren(PrintLayoutCanvas):
            try:
                canvas.flush_pending()
            except RuntimeError:
                pass  # 控件已析构

    def shutdown_all_workers(self) -> None:
        """连同各预览控件自己的缩略图线程一起收尾。

        页面自身、PDF 预览、打印预览、缩略图条分别持有 WorkerHost 的线程，
        只停页面的会让其余线程在解释器退出时被强杀（偶发崩溃/卡顿）。
        """
        self.shutdown_workers()
        for widget in self.findChildren(QWidget):
            # ⚠️ 没建过的惰性面板直接跳过：`getattr` 探测会被 `LazyPanelHost` 的
            #    属性转发接住，顺手把面板构造出来——关页面时白建四个面板
            #    （2026-09-26 审计：同一类坑见 flush_layout_pending）。
            if hasattr(widget, "peek") and widget.peek() is None:
                continue
            shutdown = getattr(widget, "shutdown_workers", None)
            if callable(shutdown):
                try:
                    shutdown()
                except RuntimeError:
                    pass  # 控件已析构
