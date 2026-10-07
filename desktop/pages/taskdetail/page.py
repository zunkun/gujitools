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
- imposition.ImpositionMixin 流程条「图片拼版」可选节点
  （共享基元 imposition.py + 模块一 imposition_pages.py「选择拼版」
  + 模块二 imposition_layout.py「拼版操作」）
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
from desktop.steps import ports
from desktop.steps.flow import FlowDefinition
from desktop.steps.spec import FLOW_STAGES
from desktop.store import (
    IMPOSITION_LABEL, IMPOSITION_STAGE, STAGE_LABELS,
)
from desktop.ui import theme as T
from desktop.ui.toast import show_toast
from desktop.ui.widgets import apply_to, bold_button
from desktop.workers import CopySourceWorker, WorkerHost, connect_queued
from desktop.pages.taskdetail.detect import DetectMixin
from desktop.pages.taskdetail.flow_mixin import FlowMixin
from desktop.pages.taskdetail.history import HistoryMixin
from desktop.pages.taskdetail.imposition import ImpositionMixin
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
#: 四个步骤的主预览都支持「焦点在哪里，哪里就切换」）。
#:
#: ⚠️ **这份映射已搬进 ``StepSpec.preview_attr``**（2026-10-03）：它是"这一步
#: 的主预览控件是谁"，属于步骤自己的属性，不该由页面维护第二份。
#: 现由 :func:`desktop.steps.ports.spec_for_stage` 查 spec 得到。
def _stage_preview_attr(stage: str) -> str:
    """当前阶段的主预览控件属性名；没有（伪步骤）返回空串。"""
    spec = ports.spec_for_stage(stage)
    return spec.preview_attr if spec else ""


class TaskDetailPage(
    StageRunnerMixin,
    SubmitMixin,
    RembgLiveMixin,
    PrintListMixin,
    ParamDraftMixin,
    HistoryMixin,
    DetectMixin,
    ImpositionMixin,
    PageListMixin,
    DetailViewMixin,
    FlowMixin,
    QWidget,
    WorkerHost,
):
    """任务详情页：由多个 Mixin 组合，固定四阶段流程。

    编排 extract→detect→rembg→print 四阶段；各职责（预览、清单、历史、
    提交、执行、检测）分散到同级 Mixin，本类只持有任务切换与阶段切换骨架。
    """

    back_requested = Signal()
    #: 页头「查看 / 编辑流程」被点了（携带任务号）——宿主（壳层）切到
    #: **流程编辑二级页**（2026-10-06 起不再弹模态窗）。
    #:
    #: ⚠️ 必须声明在**这个 QWidget 子类**里：Mixin 是普通类，在里面写
    #: ``Signal(...)`` 不会注册进 Qt 元数据（发不出去）。
    flow_edit_requested = Signal(str)

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
        #: 本任务的源 PDF 路径。**None = 还没选**（空壳任务，用户 2026-10-06
        #: 「PDF 输入不是必须的」）；路径存在但文件不在 = "文件丢了"，两者在
        #: 界面与执行上处理不同，别混成一个 `exists()` 判断。
        self.source_path: Path | None = None
        #: ``source_path is not None`` 的缓存位（多处要判，别重复表达式）
        self.has_source = False
        #: 补选 PDF 的中间态：正在后台算指纹（按钮置灰）、等算完的文件路径
        self._picking_source = False
        self._pending_source: Path | None = None
        #: 「缺源 PDF」页内提示层（懒建；见 manifest.py 与
        #: components/missing_source_prompt.py）
        self._source_prompt = None
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
        #: 当前阶段的**子进程传输层**（起进程/读字节流/看门狗，见
        #: ``desktop.steps.process.StageProcess``）。由 runner 在启动阶段时建，
        #: 收尾/中断按它取进程；未启动时为 None。
        self._stage_transport = None
        self._init_ui()
        # 进度事件的界面刷新节流器（见 StageRunnerMixin._PROGRESS_UI_MS）
        self._init_progress_ui()
        # 页面尺寸/检测框的攒批落盘（见 StageRunnerMixin._ANNOT_FLUSH_MS）
        self._init_annotation_batch()
        # 参数暂存：面板报到"用户改了参数"就防抖写 drafts/<阶段>.json
        self._install_draft_hooks()
        # 图片拼版的合成防抖定时器（后台落 stages/imposition）
        self._init_imposition_compose()
        # 第三步实时预览：改参数/翻页时只重算当前页（见 rembg_live.RembgLiveMixin）
        self._init_rembg_live()
        # 字体列表后台预热：一进任务（还在第一/二/三步）就起后台线程扫系统
        # 字体，等用户翻到第四步时列表已就绪。扫描全局只跑一次、结果写磁盘
        # 缓存，且**不阻塞**任何界面操作（详见 desktop.services.font_catalog）。
        start_background_scan()

    # ------------------------------------------------------------------ 任务切换
    def _warn_if_flow_degraded(self, task_id: str) -> None:
        """本任务的流程图**读不出来时已回落默认模板** ⇒ 明确告诉用户一次。

        ⚠️ 这是"自定义流程里总是冒出默认流程"这类报障**唯一**能自证的线索。
        ``store.task_diagram`` 在三种失败形态下都会回落默认模板（文件缺失 /
        XML 坏 / **一个步骤名都认不出**），而回落是**静默**的——用户看到的
        现象与"我没改过它"完全一样，最隐蔽的一种是他在 bpmn.io 里改了节点名，
        阶段按名接不回，整张自定义图被判成坏图。

        ⚠️ 同一次 :meth:`set_task` 只弹一次（``set_task`` 一条链上会被
        ``flow_slots`` 读很多次流程图，别弹成刷屏）。
        """
        reason = self.store.flow_degraded_reason(task_id)
        if not reason:
            self._flow_warned_for = None
            return
        if getattr(self, "_flow_warned_for", None) == task_id:
            return
        self._flow_warned_for = task_id
        self._toast(
            "warning", "流程已临时按默认显示",
            f"{reason}。\n\n"
            "本任务的界面暂时按**默认流程**显示（步骤条、执行顺序、取图目录"
            "都按默认那套算）。请到「查看 / 编辑流程」里把流程修好——在修好之前，"
            "改动这份流程不会有任何效果。",
        )

    def set_task(self, task_id: str) -> bool:
        """切换当前任务：复位所有阶段面板与运行态，避免跨任务泄漏。

        加载任务后先调用各面板 reset_to_default 清掉上一任务手改参数，再清
        detect 缓存/运行态引用并刷新清单与预览；防止参数或 run_id 串到新任务。
        返回 False = 拒绝切换（任务不存在 / 子任务执行中），调用方应留在原地。
        """
        task = self.store.get_task(task_id)
        if not task:
            return False
        # ⚠️ 子任务执行中禁止切换（2026-09-26 第二轮审计）：runner 的收尾
        #    全部按 self.task_id 落盘，切走后事件到达就会写进**新任务**的
        #    runs.json / 输出目录。单页检测是几秒的辅助操作，直接停掉即可。
        if self.process and self.process.state() != QProcess.NotRunning:
            self._toast(
                "warning", "任务进行中", "请先中断当前子任务再切换其他任务。"
            )
            return False
        self._stop_detect_process()
        # ⚠️ 复位**跨任务会串味**的两个第四步状态（2026-09-26 审计）：
        #    ① `_print_dirty`：在任务 A 拖过版面，打开任务 B 时 B 的第四步会误显示
        #       「● 版面已修改，点击「生成PDF」生效」并把主按钮加粗；
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
        # 实时预览临时目录同理：reset(self.task_id) 清的是"上一个任务"的
        # %TEMP%/guji_live_preview/<id>/ ——放在覆盖之后清的就是新任务的
        # 空目录，旧任务那份（每张几 MB 的整页 PNG）永远没人清（审计 M4）
        self._reset_rembg_live()
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
        #
        # ⚠️ **空壳任务**（创建时没选 PDF，用户 2026-10-06「PDF 输入不是必须
        # 的」）：索引里 source_path 是**空串**。`Path("")` 是"."（当前目录），
        # 直接 `or Path(task["source_path"])` 会得到一个**存在的目录**——
        # 于是 exists() 通过、`set_pdf` 去渲染一个目录、后面 extract 拿着
        # 它当输入，静默走到崩为止。所以这里显式判空，置成 None（"还没有
        # 源文件"这个状态有别于"文件丢了"，UI 与执行各自处理，见下）。
        source_text = str(task.get("source_path") or "").strip()
        copy = self.store.source_copy_path(task_id)
        if copy is not None:
            self.source_path = copy
        elif source_text and source_text != ".":
            self.source_path = Path(source_text)
        else:
            self.source_path = None
        self.has_source = self.source_path is not None
        self._schedule_source_backup(task_id)
        # ⚠️ 空壳任务（没选源文件）在这里**什么都不弹**：「还没选」不是错误，
        #    而且**并非所有流程都需要 PDF**——要不要催、催什么（补 PDF 还是
        #    补入口图片）由 ``_missing_input_kind()`` 按流程入口判，提示统一
        #    走 set_task 末尾的 ``_prompt_missing_source()``（页内提示层）
        #    与页头红字/按钮高亮，这里再来一条 toast 就是重复+误导（用户
        #    2026-10-07：右下角「尚未选择 PDF」不再需要）。「文件丢了」才是
        #    错误，仍在下面单独说。
        if self.source_path is not None and not self.source_path.exists():
            self._toast(
                "error",
                "PDF 缺失",
                f"任务备份与源文件都不存在：{task['source_path']}\n"
                "请重新导入该 PDF（或把原文件放回原处后重开任务）。",
            )
        self.detail_title.setText(task["name"])
        self.source_label.setText(
            self.source_path.name if self.source_path else "尚未选择 PDF")
        self._warn_if_flow_degraded(task_id)
        self._refresh_source_actions()
        # 切任务时先把各阶段面板复位到默认：这些面板是长生命周期控件，
        # 上个任务手改过的参数（area/border/type/zoom…）否则会带到新任务上，
        # 而新任务往往没有历史记录可覆盖回来。
        # ⚠️ 四个面板都是**惰性**的，这里必须走 `peek()`（不触发构造）：直接
        #    `widget(i).reset_to_default()` 会经属性转发把面板全部现造出来，
        #    进详情页的时间就又回到"要为没进去的步骤买单"（用户明确要求
        #    第 2/3/4 步谁进去谁才建）。没建的面板本来就没动过，无需复位。
        #    ⚠️ 只遍历真实阶段（len(FLOW_STAGES)）：控制栈末尾是「图片拼版」占位面板，
        #    没有参数也没有 reset_to_default，混进来就是 AttributeError。
        for index in range(len(FLOW_STAGES)):
            host = self.control_stack.widget(index)
            peek = getattr(host, "peek", None)
            panel = peek() if callable(peek) else host
            if panel is not None:
                panel.reset_to_default()
        # 第四步默认 PDF 名/古籍名随源 PDF 名派生（xxx[重制].pdf / xxx）；
        # ⚠️ 同样不能在这里碰面板本体：记下源名，面板真被建出来时再应用
        #    （见 _init_ui 里挂的 add_created_hook）。已有 print 历史时它会在
        #    进入第四步时再回填历史配置。
        # ⚠️ 空壳任务（没有源文件）没有 stem 可派生：给**任务名**当源名，
        #    这样补选 PDF 之前第四步的参数也不是空的（补选后会被覆盖，
        #    见 _on_pick_source）。
        self._pending_source_stem = (
            self.source_path.stem if self.source_path
            else str(task.get("name") or task_id)
        )
        self._apply_pending_source_defaults()
        self.log_view.clear()
        self.detect_cache.clear()
        # 图头尺寸缓存按 (路径, mtime) 键控、只增不减：换任务清掉，别攒一整场会话
        self._thumb_size_cache = None
        # （实时预览临时目录已在覆盖 task_id 之前按旧任务清过，见上方）
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
        # ⚠️ 空壳任务：source_path 是 None（见上面），而``set_pdf`` 本身就
        #    接受 None（内部摆个占位就return，见 pdf_viewer.set_pdf），所以
        #    直接传；占位文案要说清是"还没选"而不是"加载失败"。
        self.source_pdf_viewer.set_pdf(
            self.source_path,
            placeholder=None if self.source_path else "尚未选择 PDF",
            cache_dir=self.store.source_thumbnails_dir(task_id),
        )
        self._refresh_manifest()
        # 换任务就得重算"上游比下游新"的判定缓存（读的是新任务的 runs.json）
        self._refresh_stale_notices()
        # 拼版视图/状态复位（取消在飞合成、灌新任务的拼版文档）
        self._reset_imposition_state()
        # ⚠️ 按**本任务流程**重建步骤条（BPM 驱动）：构造期还没有任务，
        #    ``_build_step_bar`` 只能先按默认流程建。自定义流程换了步骤
        #    顺序/ 可选节点位置后，必须在这里按新流程重排，否则步骤条显示的
        #    仍是默认顺序、点节点也会切错步骤。默认流程下这是**同参数重建**，
        #    外观零变化（自测 detail_structure 钉死）。
        self._rebuild_step_bar()
        self._refresh_stage_views()
        # 落到「上次停留的步骤」（没有记录 / 记录匹配不上时回第一步）
        # ——这就是「点任务详情直接进上次那一步」的全部实现（用户 2026-10-06
        #   明确保留的口径），与启动行为无关。
        self._select_stage(self._initial_stage_index())
        # 记下「上次停留的任务」：启动不再自动跳回（用户 2026-10-06 改口径），
        # 这条全局记录只留给将来的显式"回到上次任务"入口，步骤仍由该任务自己的
        # ui.json 另记（见 _remember_stage）
        self.store.save_last_task(task_id)
        # ⚠️ 弹窗提示放在**最后**：前面已经把页头、红字、按钮高亮、预览都摆好
        #    了，用户点"现在选择"时看到的界面已经是就绪的。
        #    判据是"流程要 PDF 而这个任务还没有"（``_missing_source``）——
        #    有源文件的任务、流程里不需要 PDF 的任务（自定义流程删掉了
        #    「提取图片」）都不弹。
        self._prompt_missing_source()
        # ⚠️ 必须 True：_open_detail 靠返回值决定切不切页——漏了这句
        #    "返回 None 被当拒绝"，详情页就永远进不去（2026-09-27 事故）
        return True

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
        # ⚠️ 检测是几秒到十几秒的慢活：返回后旧进程的 boxes 事件才到达，
        #    task_id 已清空/换成别的任务 → 跨任务写 boxes.json（审计 H3）。
        self._stop_detect_process()
        # 离开前把待写暂存落盘：task_id 马上被清掉，之后再写就找不到任务了
        self._flush_param_drafts()
        self._flush_annotations()
        # 实时预览暂存同样要按"当前任务"清（覆盖 task_id 之前，见 set_task）
        self._reset_rembg_live()
        # ⚠️ 「缺源 PDF」提示层也要收：它是这一页的子控件，不收的话回到列表
        #    之后它还浮在那儿（页面只是被切走、并没有销毁），下次进来会看到
        #    一个"上个任务"的提示层。
        self._dismiss_source_prompt()
        self.task_id = None
        self.source_path = None
        # 释放 PDF：不释放的话回到列表删除该任务时，rmtree 可能撞上文件占用
        self.source_pdf_viewer.set_pdf(None)
        self.back_requested.emit()

    # ------------------------------------------------------------------ 流程槽位（BPM）
    def flow_slots(self) -> tuple:
        """本任务流程投影出的**界面槽位**（BPM 驱动界面的唯一入口）。

        没有任务（构造期/已离开）时给**默认流程**的槽位表，让步骤条在
        还没有任务时也能正常建出来——它此时只是个静态展示。

        ⚠️ 步骤条上那一格的 ``bar_index`` 就是 :attr:`StepBar._current` 的
        语义；``stack_index`` 才是 ``control_stack`` / ``preview_stack`` 的页号。
        两者在默认流程下与旧的 ``STAGES[index]`` 逐值相等（自测 ``detail_structure``
        钉死），所以换流程不用改栈的建页。
        """
        if not getattr(self, "task_id", None):
            # 没任务时给**默认模板**的槽位（静态展示）。⚠️ 与任务态同源：
            # 任务态走 store.task_slots（也是读 bpmn 文件），口径不会漂。
            from desktop.steps.scheduler import load_default_diagram

            return load_default_diagram().stage_slots()
        return self.store.task_slots(self.task_id)

    def step_at_index(self, index: int) -> str | None:
        """步骤条格序 → **界面步骤 key**；这一格不在本流程里返回 ``None``。

        取代旧代码里的 ``STAGES[index]``（自定义流程下那个下标可能根本不存在）。
        """
        for slot in self.flow_slots():
            if slot.bar_index == index:
                return slot.step
        return None

    def stage_at_index(self, index: int) -> str | None:
        """步骤条格序 → **运行阶段**（``control_stack`` 页号语义那一层）。

        取代 ``ports.spec_for_stage(STAGES[index])`` 里的 ``STAGES[index]``。
        """
        for slot in self.flow_slots():
            if slot.bar_index == index:
                return slot.stage
        return None

    def stack_index_of(self, index: int) -> int:
        """步骤条格序 → ``control_stack`` / ``preview_stack`` 的页号。

        这一格不在本流程里时**兜回 0**（回第一步）并由调用方按"没找到"
        处理——绝不能拿一个越界页号去 ``setCurrentIndex``。
        """
        for slot in self.flow_slots():
            if slot.bar_index == index:
                return slot.stack_index
        return 0

    def bar_index_of_step(self, step: str) -> int | None:
        """界面步骤 key → 步骤条格序；这一步不在本流程里返回 ``None``。"""
        for slot in self.flow_slots():
            if slot.step == step:
                return slot.bar_index
        return None

    def flow_entry_step(self) -> str | None:
        """本流程**第一个真实步骤**的 step key（跳过可选节点）。

        ⚠️ "第一步"在自定义流程里不是"静态步骤表的第一格"——预热面板、
        缺输入提示等都得问图（``bar_index == 0`` 的那一格）。

        ⚠️ 刻意**跳过可选节点**：拼版永远是占位详情页（``mapped`` 语义上
        不算真正的入口步骤），否则"第一步是拼版"会让预热去建一个占位面板。
        """
        for slot in sorted(self.flow_slots(), key=lambda s: s.bar_index):
            if not slot.optional and slot.mapped:
                return slot.step
        return None

    def stage_at_stack_index(self, page: int) -> str | None:
        """``control_stack`` / ``preview_stack`` **页号** → 运行阶段。

        与 :meth:`stage_at_index` 是一对（那边是步骤条格序→ 阶段）。
        默认流程下两种下标逐值相等，自定义流程下必须分开查。
        """
        for slot in self.flow_slots():
            if slot.stack_index == page:
                return slot.stage
        return None

    def _rembg_step_index(self) -> int:
        """"图片去底色"这一步的**格序**（拼版节点消失时退回的那一步）。

        ⚠️ 旧代码写死 ``2``（第三步）。自定义流程里第三步未必在下标 2，
        写死会把用户送到别的步骤去。本流程里没有这一步时兜回 0。
        """
        index = self.bar_index_of_step("rembg")
        return 0 if index is None else index

    def panel_host_of_step(self, step: str):
        """界面步骤 key → ``control_stack`` 里那一页的宿主控件。

        ⚠️ **取别的步骤的面板只有这一个入口**（MEMORY「三套下标」）：两个栈是
        按 ``FLOW_STAGES + OPTIONAL_STEPS`` 一次建好**固定页数**的，所以
        ``control_stack.widget(2)`` 恰好是「图片去底色」——那是"静态步骤表
        顺序"的性质，**不是**流程图的性质。自定义流程一旦换序、``SPECS``
        一旦增删一步，它就读错面板；流程里压根没有那一步时还会**把不在流程
        里的面板构造出来**（破坏"谁进去谁才建"，还会读到用户没填过的参数）。

        本流程没有这一步 ⇒ 返回 ``None``，调用方必须自己降级（别再兜一个
        "随便哪一步"——那正是界面说 A、执行做 B 的来源）。

        ``step`` 是**界面步骤 key**（``extract``/``detect``/``rembg``/``print``），
        不是运行阶段 key（``rembg_submit`` 请传 ``"rembg"``）。
        """
        index = self.stack_index_of_step(step)
        if index is None or index < 0:   # NO_PAGE = -1
            return None
        stack = getattr(self, "control_stack", None)
        if stack is None or index >= stack.count():
            return None
        return stack.widget(index)

    def stack_index_of_step(self, step: str) -> int | None:
        """界面步骤 key → 两个栈的页号；这一步不在本流程里返回 ``None``。"""
        for slot in self.flow_slots():
            if slot.step == step:
                return slot.stack_index
        return None

    # ------------------------------------------------------------------ 阶段切换/状态
    def current_stage(self) -> str:
        """返回当前所处阶段的key（extract/detect/rembg/print/imposition）。

        以步骤条高亮下标反查**本任务流程**的槽位表（BPM 驱动：自定义流程
        换了顺序/删了节点，这里如实反映）；下标为负时按 0 兜底处理。
        「图片拼版」是**可选节点**（``StepSpec.role == "optional"``），
        返回它的专用 key：调用方凡是拿这个 key 去 STAGES/STAGE_LABELS/runs
        里查的，都必须先挡掉（见 _refresh_stage_views / _apply_control_width
        等处的守卫）。
        """
        current = self.step_bar._current
        stage = self.stage_at_index(max(current, 0))
        if stage is not None:
            return stage
        # ⚠️ 兜底走**本流程**第一格，不是 ``STAGES[0]``（那是静态步骤表的
        #    第一格 = 恒为 extract）。自定义流程里压根没有 extract 时，回退到
        #    一个不在流程里的阶段会让进度/参数回填全都打到别的步骤上。
        for slot in sorted(self.flow_slots(), key=lambda s: s.bar_index):
            if not slot.optional and slot.mapped:
                return slot.stage
        return None

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
            self, _stage_preview_attr(self.current_stage()), None
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

    # --------------------------------------------------- 上次停留的步骤（记忆）
    # 「上次停留的步骤」按 **key** 记（不是下标）：步骤会增减（「图片拼版」就是
    # 条件出现的可选节点），下标一旦错位就会把用户送到**另一个**步骤去。key 是
    # 按语义匹配的，匹配不上就回落第一步——这正是用户要的口径。
    def _stage_index_of(self, stage: str | None) -> int | None:
        """把记录的步骤 key 映射成**当前流程**里的格序；匹配不上返回 None。

        ⚠️ 查**本任务流程**的槽位表而不是 ``STAGES.index``：自定义流程
        里这一步可能被删掉（``bar_index_of_step`` 返回 ``None``）→ 视为
        "找不到匹配"，回第一步，而不是把用户送到流程条上不存在的那一格。
        「图片拼版」另有一道条件可见性检查，见
        :meth:`_imposition_node_visible_index`。
        """
        if not stage:
            return None
        if stage == IMPOSITION_STAGE:
            return self._imposition_node_visible_index()
        return self.bar_index_of_step(stage)

    def _imposition_node_visible_index(self) -> int | None:
        """拼版节点在步骤条上的格序；本流程里没有它时 ``None``。

        「图片拼版」是**条件节点**：**流程图里没画它**时它根本不在流程条上，
        即便 key 认得出来也算"找不到匹配"——否则会切进一个流程条上不存在的
        步骤，紧接着又被 ``_refresh_imposition_node`` 踢回第三步（落到哪一步
        全看谁后跑，比"回第一步"更难解释）。
        """
        if not self._imposition_node_visible():
            return None
        return self.bar_index_of_step(IMPOSITION_STAGE)

    def _initial_stage_index(self) -> int:
        """进详情页默认落到第几步：**上次停留的步骤**，匹配不上则第一步。

        这是「打开任务详情默认打开记录的那一步，找不到匹配就从第一步开始」
        的唯一实现处（``set_task`` 末尾调它）。
        """
        if not self.task_id:
            return 0
        index = self._stage_index_of(self.store.load_last_stage(self.task_id))
        return 0 if index is None else index

    def _remember_stage(self, index: int) -> None:
        """记下"用户最后停留的步骤"，下次打开这个任务直接回到这里。

        写在 ``_select_stage`` 里（切步骤的唯一入口）而不是"返回列表/关窗口"
        时：进程被强杀、断电都不会把记录丢掉。⚠️ 记的是 key 不是下标，理由
        见 :meth:`_stage_index_of`；任务目录已删时 ``save_last_stage`` 自己
        跳过（不重建目录）。
        """
        if not self.task_id:
            return
        # ⚠️ 记key 不记下标（理由见 :meth:`_stage_index_of`）。下标要**反查**
        #    槽位表，不能用 ``STAGES[index]``——自定义流程里那一格可能是
        #    拼版（可选节点）或换个顺序的别的步骤。
        stage = self.step_at_index(index)
        if stage is None:
            return
        self.store.save_last_stage(self.task_id, stage)

    def _select_stage(self, index: int) -> None:
        """切到步骤条的**第``index`` 格**（格序，含可选节点占位）。

        ⚠️ **参数是格序、不是栈页号**：默认流程 ``extract=0/detect=1/rembg=2/
        imposition=3/print=4``，而两个栈的页号是 ``extract=0/detect=1/rembg=2/
        print=3/imposition=4``（伪步骤占末位）。混用两者 = 切错步骤或切到越界页。
        调用方一律先 ``bar_index_of_step(step)`` / ``stack_index_of_step(step)``
        查表，**不要写死数字**（``IMPOSITION_INDEX=len(STAGES)=4`` 是改造前的
        遗留口径，现在落在 print 那一格）。
        """
        # 离开当前阶段前把待写暂存落盘、把未提交的版面拖动补发
        # （防抖未到期/拖住未松手就走人不该丢改动）
        self.flush_layout_pending()
        self._flush_param_drafts()
        # ⚠️ **在 set_current 之前**拦下"图上有、但还没有功能"的灰节点：
        #    放行的话步骤条会高亮在这一格、还会被记成"上次停留"，而右侧显示
        #    的仍是上一步的内容——看着就像"点了没反应"。
        slot = self._slot_at_index(index)
        if slot is not None and not slot.mapped:
            self._explain_unmapped_step(slot)
            return
        self.step_bar.set_current(index)
        # 记住这一步：下次打开任务默认回到这里
        self._remember_stage(index)
        step = self.step_at_index(index)
        if step == IMPOSITION_STAGE:
            # ⚠️ 节点本身的显示/选择状态要在这里先补一次：真实步骤是在本方法
            #    **末尾**刷的（那边得等 area 回填完），而这条分支提前 return 了。
            #    漏掉它的后果（用户 2026-09-30 报的 bug）：上次停在「图片拼版」，
            #    重进任务直接恢复到这一步时，流程条上**没有那个虚线节点**——
            #    节点显示状态还停在上一个任务/构造时的隐藏态，只能等用户点了
            #    别处再切回来才会出现。
            #    ⚠️ 这一步内部可能发现 area≠1 而把当前步踢回第三步
            #    （见 ImpositionMixin._refresh_imposition_node）：那就跟随它，
            #    别再进拼版详情，否则步骤条说"第三步"、页面却是拼版。
            self._refresh_imposition_node()
            #⚠️ 用**当前格序反查**判断有没有被踢走：`_refresh_imposition_node`
            #    在 area≠1 时会把当前步踢回第三步，那时 ``_current`` 已不是
            #    拼版那一格（旧代码写死 ``!= IMPOSITION_INDEX``，自定义流程
            #    下拼版的格序会变，写死就判错了）。
            if self.step_at_index(self.step_bar._current) != IMPOSITION_STAGE:
                return
            # 「图片拼版」可选节点：右侧/预览区都是占位详情，不碰阶段面板
            self._select_imposition_detail()
            return
        # ⚠️ 这一格不在本流程里（自定义流程删掉了对应节点，而调用方拿着
        #    旧下标）：回第一步，别拿越界页号去 setCurrentIndex。
        if step is None:
            self._select_stage(0)
            return
        # ⚠️ 面板是**惰性**的：用户切到这一步，就现在把它建出来（不建的话
        #    左侧控制区是空白）。反过来，没切过来的步骤一直不建——这正是
        #    用户 2026-09-25 要求的"谁进去谁才建"。
        # ⚠️ 栈的页号是``stack_index`` 而非步骤条格序：可选节点在步骤条上
        #    插在它该在的位置（bar_index），但两个栈仍按"真实步骤 + 伪步骤
        #    占最后一位"建页（stack_index）。默认流程下两者逐值相等。
        page = self.stack_index_of(index)
        target = self.control_stack.widget(page)
        if hasattr(target, "peek") and target.peek() is None:
            target.panel  # noqa: B018 - 触发构造
        self.control_stack.setCurrentIndex(page)
        self.preview_stack.setCurrentIndex(page)
        # 真实步骤：执行按钮组恢复可见（拼版详情页整组藏掉，见
        # _select_imposition_detail；两种状态互斥、切换时都要还原）
        # ⚠️ 恢复的是**整行** action_row（「生成预览 + 提交本次任务」并排），
        #    只恢复 run_button 的话行本身仍带着上一步的隐藏标记。
        self.action_row.setVisible(True)
        self.followup_row.setVisible(True)
        # 按钮文案与区块显隐**全查 spec**（不再 `if stage == ...`）：
        # 第三步是「生成预览」+「提交本次任务」两个动作，第四步是「生成PDF」，
        # 其余是「执行本子任务」——文案与"跑完会发生什么"绑定，所以放 spec 而
        # 不是散在页面里（加一步 / BPM 换顺序都不必改这里）。
        # ⚠️ 走 ``ports.spec_for_stage``：伪步骤（拼版）取不到 spec 时用默认值。
        spec = ports.spec_for_stage(step)
        self.run_button.setText(
            spec.run_button_text if spec else "执行本子任务"
        )
        self.submit_button.setVisible(bool(spec and spec.has_submit))
        # 右侧面板的步骤专属区块：``spec.panel_extra`` 非空 → 显示该专属区块
        # （detect 显示「检测结果统计」），否则显示「执行记录」
        # （detect 无表单参数，历史回填没用武之地）。
        self.detect_stats.setVisible(
            bool(spec) and spec.panel_extra == "detect_stats"
        )
        self.history_block.setVisible(not spec or not spec.panel_extra)
        self._apply_control_width()
        self._refresh_stage_views()
        # ⚠️ 传的是**栈页号**（``_refresh_preview`` 按 ``preview_stack`` 这一层
        #    理解入参），不是格序——自定义流程里两者不等。
        self._refresh_preview(self.stack_index_of(index))
        self._restore_stage_params(index)
        self._refresh_history_options()
        if step == "detect":
            # 整页开关是 area=4 的入口，切回第二步时按当前 area 回填
            self._sync_whole_page_checkbox()
        # 流程条上的「图片拼版」节点跟随当前 area（回填可能改了 area，
        # 走 blockSignals 时不会触发面板信号，这里统一补一次）
        self._refresh_imposition_node()

    def _slot_at_index(self, index: int):
        """步骤条**格序** → 槽位对象；没有这一格返回 ``None``。

        与 :meth:`step_at_index` 的区别：那个只给 step key，这个给整个槽位
        （要拿 ``optional`` / ``mapped`` 这类只有槽位才有的信息）。
        """
        for slot in self.flow_slots():
            if slot.bar_index == index:
                return slot
        return None

    def _explain_unmapped_step(self, slot) -> None:
        """图上画了、但还没有对应功能的节点：说清怎么接上，别静默跳走。

        两种出路都写进提示里，用户不用猜：改**名字**接上已有步骤，或直接
        **删掉**不需要的那一格（编辑器工具栏有「删除」与「恢复默认」）。
        """
        self._toast(
            "warning", "这一步还没有功能",
            f"流程图里的「{slot.label}」目前没有对应的处理功能，还不能执行。"
            "要用它：点页头「查看 / 编辑流程」把它的名字改成已有步骤"
            "（如「图片去底色」）；不需要就把它删掉。",
        )

    def _refresh_stage_views(self) -> None:
        if not self.task_id:
            return
        states = self.store.stage_states(self.task_id)
        self.step_bar.reset_statuses()
        # ⚠️ 按**槽位表**刷而不是 ``enumerate(STAGES)``：步骤条上的格序来自
        #    本任务流程（BPM 驱动），自定义流程换了顺序，状态要刷到对应那一格；
        #    可选节点（拼版）没有 runs 状态，跳过（它在下方单独给状态行文案）。
        for slot in self.flow_slots():
            if slot.optional:
                continue
            state = states.get(slot.stage)
            if state is None:
                continue
            progress = (state["done"], state["total"]) if state["total"] else None
            # 步骤条只表达"第几步 / 执行到哪"：completed 决定徽标是否打勾，
            # status 决定副标题文案与颜色（重试失败不会让已完成步骤退回未完成）
            self.step_bar.set_step_status(
                slot.bar_index, state["status"], progress,
                completed=state["completed"],
            )
        self._show_running_submit_on_steps(states)
        stage = self.current_stage()
        if stage == IMPOSITION_STAGE:
            # 「图片拼版」伪步骤在 runs.json 里没有状态可读；执行按钮组也
            # 整体隐藏（见 _select_imposition_detail），这里只给状态行文案。
            self._set_stage_status(
                "图片拼版：可选节点（勾选「在流程中启用图片拼版」后，"
                "PDF排版使用拼版结果）"
            )
            return
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
        # ⚠️ **查表，别写死 2**：提交折叠在「图片去底色」那一格，而那一格的
        #    格序随流程走（自定义流程里它可能是第 1 格）。写死 2 在那条流程下
        #    会把进度显示到别的节点上（同 ``runner`` 里那两处已改用
        #    ``stack_index_of_step``）。
        index = self.bar_index_of_step("rembg")
        if index is None:
            return
        self.step_bar.set_step_status(
            index, "running", (done, total) if total else None,
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
        """重算"上游比本步新"与"取图来源已换"的判定缓存。

        ⚠️ 只在**运行收尾**、**切任务**、**拼版开关变化**时调，别放进
        ``_refresh_stage_views`` 的热路径：判定要读整份 runs.json，而那里运行期
        每 ≤200ms 就跑一次。
        """
        self._print_source_stale = False
        if not self.task_id:
            self._stale_notices = {}
            return
        # 一次读全（五个阶段逐个 list_stage_runs 会把 runs.json 读五遍）
        runs = self.store.all_stage_runs(self.task_id)
        # ⚠️ 上游链**按本任务的流程图算**，不用写死的那张表：用户加/删/换了步骤
        #    之后，写死的链会指错上游（提示"上游已重新执行"却指到不相干的步骤），
        #    或者漏掉真正影响它的那一步。
        from desktop.services.stale_chain import upstream_from_diagram

        self._stale_notices = stale_upstream(
            runs, upstream_from_diagram(self.store.task_diagram(self.task_id))
        )
        # 取图来源是否已换（拼版开关）——同一份 runs.json 顺手算掉，不额外读盘
        try:
            from desktop.services.stale_chain import print_source_switched

            self._print_source_stale = print_source_switched(
                runs, self.print_source_stage()
            )
        except Exception:  # noqa: BLE001 - 判定失败不该拦住界面刷新
            self._print_source_stale = False

    def _regenerate_notice(self, stage: str) -> str | None:
        """本步产物"需要重新生成"的提示文案（没有则 None）。

        三种来源，顺序即优先级：

        1. 第四步的逐图坐标刚被版面编辑器改过（``_print_dirty``）——用户的直接
           改动，最该被看见；
        2. **取图来源换了**（``_print_source_stale``）——勾上/取消「图片拼版」
           之后，磁盘上那份 PDF 是上一轮来源的产物，旧数据不该再被当成结果；
        3. **上游重新执行过**（``services/stale_chain`` 的时间戳链）——本步产物是
           那之前生成的，可能已经不是最新参数下的结果。

        ⚠️ 第 2 条读**缓存**（``_print_source_stale``）而不是现算：本方法经
        ``_refresh_stage_views`` 在执行期间每 ≤200ms 被拉一次，而现算要读
        runs.json + 拼版文档。缓存由 :meth:`_refresh_stale_notices` 在切任务/
        运行收尾、以及拼版开关变化时重算（见 ``imposition._refresh_print_source``）。
        """
        if stage == "print":
            if getattr(self, "_print_dirty", False):
                return "● 版面已修改，点击「生成PDF」生效"
            if getattr(self, "_print_source_stale", False):
                # ⚠️ 认 effective：区域模式不支持时来源确实已回到去底色，
                #    这里必须跟着说"去底色"而不是说"拼版"（否则界面与执行打架）
                where = (
                    IMPOSITION_LABEL if self.imposition_effective()
                    else "去底色"
                )
                return f"● 取图来源已改为{where}，请重新「生成PDF」"
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

        与第三步「提交本次任务」待重新提交时的视觉语言一致：**用加粗**点明
        该动作，但**不阻止**用户先干别的——只提示，不自动重跑。
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
        # ⚠️ **两套下标，这里必须显式分开**（用户 2026-10-06 报障的根因之一）：
        #    无参调用时手上只有 ``preview_stack.currentIndex()``，那是**栈页号**；
        #    而 ``stage_at_index`` 收的是**步骤条格序**。自定义流程里两者不等
        #    （detect 可以是格序 0 / 栈页号 1），混用会刷错那一步的预览——
        #    表现为"插了图，左侧列表却不动"。
        #    所以这里统一走 ``stage_at_stack_index``：调用方给的是栈页号或
        #    ``None``，都按栈页号这一层理解（``_select_stage`` 传的格序经
        #    ``stack_index`` 转一下，见调用处）。
        page = self.preview_stack.currentIndex() if index is None else index
        stage = self.stage_at_stack_index(page)
        if stage is None:
            return
        # ⚠️ 进detect/rembg 前按"这一步的输入目录"兜一次清单：流程里没有
        #    extract 时清单不会被任何阶段刷新，用户放进stages/input/ 的图
        #    就成了"明明有图却显示暂无图片"（用户 2026-10-06）。
        self._sync_manifest_to_input()
        if stage == "extract":
            self.extract_result_viewer.set_images(self._manifest_paths())
        elif stage == "detect":
            self.detect_viewer.set_images(self._manifest_paths())
            # 清单可能变了（增删页/切任务/批量检测跑完）→ 统计跟着重算
            self._refresh_detect_stats()
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
            # 记下本次列表的来源：进入路径在 _refresh_print_source 里是"只作废
            # 缓存不重建"，不在这里补记的话，进第四步后每次后台合成回调都会
            # 把整批列表白重建一遍（同步解码首图，UI 冻结）
            self._print_source_cache = str(self.print_source_dir())
            # 若此前已生成过 PDF，恢复下载按钮状态。
            # ⚠️ 走 _current_print_pdf_path（不是 _latest_print_pdf_path）：
            # 拼版开关一改，磁盘上那份 PDF 就是旧来源的产物，得让下载按钮
            # 灭掉——用户 2026-10-03："旧的数据不显示"。
            self.print_preview.set_pdf_path(self._current_print_pdf_path())

    # ------------------------------------------------------------------ 工具
    def _toast(self, kind: str, title: str, content: str) -> None:
        """弹 InfoBar；实现收在 :mod:`desktop.ui.toast`（与独立任务页共用）。"""
        show_toast(self, kind, title, content)

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

        目前是第四步的版面画布与拼版画布：拖动中不落盘，只在松手/补发时提交。

        ⚠️ **只按具体的类 `findChildren`，绝不用 `getattr(widget, ...)` 探测能力**：
        四个阶段面板是 `LazyPanelHost`，属性转发（`__getattr__`）会**立刻把面板
        构造出来**——那就把用户要求的「不进去就不建」破坏掉了。（2026-09-26 自己
        踩到：写成 `getattr(w, "flush_pending", None)` 之后，`detail_prewarm`
        护栏直接红成"四个面板全建"。）
        ⚠️ 拼版画布是**直接构造**的（不在 LazyPanelHost 里），按类查安全。
        """
        from desktop.components.imposition.canvas import ImpositionCanvas
        from desktop.components.viewers.print_layout_canvas import PrintLayoutCanvas

        for cls in (PrintLayoutCanvas, ImpositionCanvas):
            for canvas in self.findChildren(cls):
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
