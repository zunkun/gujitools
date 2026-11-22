# -*- coding: utf-8 -*-
"""任务详情页的**装配点**：信号、任务级类属性、``__init__``、方向键入口。

由 ``page.py`` 拆出（只搬不改）。其余职责分散在兄弟模块的 Mixin 里：
- task_switch：任务切换、源文件副本补建、返回列表
- nodes：节点索引 / 槽位查询 / 当前阶段
- stage_switch：编辑菜单分派、阶段切换、上次停留
- stage_state：阶段状态与「上游已过期」提示
- run_control：执行权与按钮状态
- page_preview：预览刷新、阶段位图释放、聚合起点轮询
- lifecycle：toast、关窗口、关前补发、worker 收尾
- edit_menu：``can_edit_* / edit_*`` 编辑菜单分派
- constants：模块级常量

⚠️ Signal 必须声明在这个 QWidget 子类里（Mixin 是普通类，声明不了）。"""

from __future__ import annotations

from pathlib import Path
from desktop.services.font_catalog import start_background_scan
from desktop.steps import ports
from desktop.components.viewers.image_actions import ImageEditActionsMixin
from desktop.workers import WorkerHost
from desktop.pages.taskdetail.detect import DetectMixin, VersionedBoxCache
from desktop.pages.taskdetail.flow_mixin import FlowMixin
from desktop.pages.taskdetail.history import HistoryMixin
from desktop.pages.taskdetail.imposition import ImpositionMixin
from desktop.pages.taskdetail.manifest import PageListMixin
from desktop.pages.taskdetail.params_draft import ParamDraftMixin
from desktop.pages.taskdetail.print_list import PrintListMixin
from desktop.pages.taskdetail.rembg_live import RembgLiveMixin
from desktop.pages.taskdetail.runner import StageRunnerMixin
from desktop.pages.taskdetail.submit import SubmitMixin
from desktop.pages.taskdetail.view import DetailViewMixin
from ._qt import QProcess, Qt, QTimer, Signal, QAbstractItemView, QAbstractSlider, QAbstractSpinBox, QApplication, QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QWidget
from typing import TYPE_CHECKING, Any

from .edit_menu import EditMenuMixin
from .lifecycle import PageLifecycleMixin
from .nodes import NodeIndexMixin
from .page_preview import PagePreviewMixin
from .run_control import RunControlMixin
from .stage_state import StageStateMixin
from .stage_switch import StageSwitchMixin
from .task_switch import TaskSwitchMixin


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


class TaskDetailPage(TaskSwitchMixin, NodeIndexMixin, EditMenuMixin, StageSwitchMixin, StageStateMixin, RunControlMixin, PagePreviewMixin, PageLifecycleMixin, StageRunnerMixin, SubmitMixin, RembgLiveMixin, PrintListMixin, ParamDraftMixin, HistoryMixin, DetectMixin, ImpositionMixin, PageListMixin, DetailViewMixin, FlowMixin, ImageEditActionsMixin, QWidget, WorkerHost):
    """任务详情页：由多个 Mixin 组合，固定四阶段流程。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _export_print_image: Any
        _init_annotation_batch: Any
        _init_imposition_compose: Any
        _init_log_coalescer: Any
        _init_progress_ui: Any
        _init_rembg_feedback: Any
        _init_rembg_live: Any
        _init_ui: Any
        _init_worker_host: Any
        _install_draft_hooks: Any
        _on_aggregate_start_poll: Any
        _run_source_backup: Any
        _wire_history_switch: Any
        current_stage: Any
        print_preview: Any

    back_requested = Signal()

    #: 页头「查看 / 编辑流程」被点了（携带任务号）——宿主（壳层）切到
    #: **流程编辑二级页**（2026-10-06 起不再弹模态窗）。
    #:
    #: ⚠️ 必须声明在**这个 QWidget 子类**里：Mixin 是普通类，在里面写
    #: ``Signal(...)`` 不会注册进 Qt 元数据（发不出去）。
    # ⚠️ FlowMixin 把它声明成 ``Callable[..., Any]``（Mixin 是普通类，声明不了
    # Signal），运行时这里才是真身。故意覆盖、不改名——改名会断掉壳层的连接。
    flow_edit_requested = Signal(str)  # type: ignore[reportAssignmentType]

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
        #: 正在跑的**节点实例** id（B 方案，2026-10-17）。收尾时按它决定产物
        #: 落点/页清单归属——用户可能跑到一半就切到同一步骤的另一个节点去了，
        #: 那时 ``current_node()`` 已经不是"跑的那个节点"了。
        self.running_node: str | None = None
        self.cancel_requested = False
        self.detect_process: QProcess | None = None
        #: 「执行权」占用标记。**必须**独立于 self.process：run_stage 收到点击后
        #: 还要校验参数、组装 effects、写运行配置，做完才 QProcess.start()，
        #: 这段同步重活里 self.process 仍是 None——没有这个标记，连点第二下
        #: 就能溜过守卫、起出第二个 worker 子进程（torch 各自加载一遍）。
        #: 存名字（"步骤"/"单页检测"）而非 bool，提示里能直接说清"什么在跑"。
        self._run_claim: str | None = None
        #: 上次**真正启动进程**的时刻（monotonic）。⚠️ 防抖量的是"距上次启动"，
        #: 而**不是**"距上次受理"：一次没跑起来的尝试（参数错、无输出、无需续跑、
        #: 提交被前置条件拒绝）不该罚掉用户紧接着的下一次点击。
        self._run_launched_at = 0.0
        #: 源文件副本缺失时的「延时后台补一份」定时器（见 _schedule_source_backup）
        self._backup_timer = QTimer(self)
        self._backup_timer.setSingleShot(True)
        self._backup_timer.timeout.connect(self._run_source_backup)
        self._backup_task_id: str | None = None
        #: 聚合任务汇集期间的「分批显示」轮询（见 _schedule_aggregate_start_poll）：
        #: 后台复制是逐文件进行的，清单不必等全部复制完才出现——每 1.2s 重刷
        #: 一次起点清单，文件落一批显示一批（用户 2026-11-18）。
        self._aggregate_start_poll = QTimer(self)
        self._aggregate_start_poll.setSingleShot(True)
        self._aggregate_start_poll.timeout.connect(self._on_aggregate_start_poll)
        #: 「按源 PDF 名派生第四步默认 PDF 名/古籍名」的挂起值：第四步面板是
        #: 惰性的，set_task 只记下源名，等面板真被建出来再应用（见 view.py
        #: 的 _apply_pending_source_defaults）
        self._pending_source_stem: str | None = None
        #: 当前格对应的**节点实例 id**（B 方案，2026-10-17）：同一步骤可以有多个
        #: 节点（图片拼版 / 检测文本框 / 图片去底色 / PDF排版…），它们共用同一
        #: 页面板，靠这个字段把数据（产物目录 / 参数暂存 / 状态）**按节点**重定向。
        #: ``None`` = 当前格没有对应节点（构造期 / 未接入的灰节点）。
        self._current_node_id: str | None = None
        #: 本任务**全部节点**的产物目录（缩略图白名单，B 方案）。只在切步骤/
        #: 重建步骤条时算一次——``flow_slots`` 每次都读盘解析 flow.bpmn，不能
        #: 放进逐页热路径（``_page_thumb_for`` 每页都要判白名单）。
        self._node_dirs: set[Path] = set()
        #: 产物目录 → 节点 id 的反查表（同一次重算填，见 :meth:`_rebuild_node_index`）。
        #: 用来回答"这张页面图是哪个节点产的"（尺寸基准按节点存时要问它）。
        self._node_of_dir: dict[Path, str] = {}
        #: **产物目录 → 上次看过时的逐文件指纹**（``{路径: (大小, mtime_ns)}``）。
        #: 切步骤时拿它回答两个问题：①这一步的输入产物**内容**变了没有（上游产物
        #: 常被**同名覆盖**——拼版成品重合成、单页重提取、编辑器回写，路径一个字
        #: 都没变）；②**哪几张**变了——按页失效旧版面（``print.json`` 的逐图 rect）
        #: 与旧缩略图缓存要靠它（用户 2026-10-18：「上一步更新了哪些图片要有记录，
        #: 图片页面缓存现在还是有」）。
        self._dir_files: dict[str, dict[str, tuple[int, int]]] = {}
        #: 节点 id → 运行阶段；界面步骤 key → 该步骤的**主节点** id（B 方案，
        #: 同一次重算填）。`node_of_stage` 这类热路径只查这两张表，不解析流程图。
        self._node_stage: dict[str, str] = {}
        self._stage_primary: dict[str, str | None] = {}
        #: 运行阶段 → 该阶段全部节点 id，**按流程条先后**（bar 序）。
        #: 「（1）/（2）」这类给人看的序号取它——与用户看到的顺序一致。
        self._stage_nodes: dict[str, list[str]] = {}
        self.detect_cache: dict[str, list[tuple] | None] = VersionedBoxCache()
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
        # 「执行记录」区块的总开关（设置 →「功能」）：开关一变就立刻重算显隐，
        # 不必让用户退出再进详情页
        self._wire_history_switch()
        # 进度事件的界面刷新节流器（见 StageRunnerMixin._PROGRESS_UI_MS）
        self._init_progress_ui()
        # 执行日志的合并器（见 desktop/ui/log_throttle，StageRunnerMixin._init_log_coalescer）
        self._init_log_coalescer()
        # 页面尺寸/检测框的攒批落盘（见 StageRunnerMixin._ANNOT_FLUSH_MS）
        self._init_annotation_batch()
        # 去底色执行期的阶段反馈（见 StageRunnerMixin._REMBG_UI_MS）
        self._init_rembg_feedback()
        # 第三步实时预览：改参数/翻页时只重算当前页（只显示，不写正式产物）
        self._init_rembg_live()
        # 参数暂存：面板报到"用户改了参数"就防抖写 drafts/<阶段>.json
        self._install_draft_hooks()
        # 图片拼版的合成防抖定时器（后台落 stages/imposition）
        self._init_imposition_compose()
        # 字体列表后台预热：一进任务（还在第一/二/三步）就起后台线程扫系统
        # 字体，等用户翻到第四步时列表已就绪。扫描全局只跑一次、结果写磁盘
        # 缓存，且**不阻塞**任何界面操作（详见 desktop.services.font_catalog）。
        start_background_scan()

    def can_edit_download_image(self) -> bool:
        if self.current_stage() == "print":
            return self.print_preview.export_image_button.isEnabled()
        return super().can_edit_download_image()

    def edit_download_image(self) -> None:
        if self.current_stage() == "print":
            self._export_print_image()
            return
        super().edit_download_image()

    def can_edit_print_image(self) -> bool:
        if self.current_stage() == "print":
            return self.print_preview.print_button.isEnabled()
        return super().can_edit_print_image()

    def edit_print_image(self) -> None:
        if self.current_stage() == "print":
            self.print_preview.print_current()
            return
        super().edit_print_image()

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
