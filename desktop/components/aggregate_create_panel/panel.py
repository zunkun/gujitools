# -*- coding: utf-8 -*-
"""聚合任务创建面板主体 :class:`AggregateCreatePanel`（组合两个 Mixin）。"""

from __future__ import annotations

from desktop.components.aggregate_create_panel._qt import (
    QHBoxLayout,
    QHeaderView,
    Qt,
    QVBoxLayout,
    QWidget,
    Signal,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CheckBox,
    PrimaryPushButton,
    PushButton,
    TableWidget,
)

from desktop import ui
from desktop.components.aggregate_create_panel.constants import (
    DEFAULT_START_STAGE,
    MEMBER_PAGE_SIZE,
)
from desktop.components.aggregate_create_panel.members import _MembersMixin
from desktop.components.aggregate_create_panel.start_stage import _StartStageMixin
from desktop.components.pagination import Pagination
from desktop.steps.aggregate import (
    AGGREGATE_START_STAGES,
    aggregate_start_label,
    derive_aggregate_diagram,
)
from desktop.ui import theme as T


class AggregateCreatePanel(_StartStageMixin, _MembersMixin, QWidget):
    """聚合任务面板：选成员 → 成员表格（排序/删除）→ 起始节点 → 流程图 → 提交。

    对外只认 :attr:`submitted`（成员 / 各成员节点 / 是否带了编辑过的流程图）
    与 :attr:`cancelled`；任务名称由宿主页面（创建任务页）统一收集。

    ## 两种用途（``inspect``）

    - ``inspect=False``（默认）：**创建**聚合任务（创建任务页用）——能挑成员、
      能排序/删除、能改起始节点、底部有「创建聚合任务」。
    - ``inspect=True``：**查看 / 继续编辑**一个已经建好的聚合任务（详情页 →
      「查看 / 编辑流程」二级页用，用户 2026-11-18：「进入流程入口……应当显示
      聚合任务的子任务相关信息，跟创建聚合任务时候一样」）——**成员只读**
      （改成员集合等于重建聚合任务），起始节点**可以改**（用户 2026-11-18：
      「起始节点可以切换变更，如果变更了保存流程的时候，提示起始节点丢失，
      聚合任务之前历史处理数据都丢失」⇒ 改完由宿主在保存时弹确认），行内只留
      「详情」，底部按钮行收起（保存/关闭在页面顶栏），流程画布仍可编辑。
    """

    #: 用户点了「创建聚合任务」：
    #: (成员任务号列表, 各成员节点 key 列表, 编辑过的流程图 or None)
    #: ⚠️ 起始节点**全体共用**（用户 2026-11-17 本轮口径），所以第二个参数
    #: 是 ``[起始节点] * 成员数``——落库字段 ``member_stages`` 的形状不变，
    #: store 照旧按"逐成员节点"校验，值恰好一致而已。
    submitted = Signal(list, list, object)
    #: 点了成员行内的「详情」——宿主（创建页 → 壳层）负责切到该子任务详情页
    detail_requested = Signal(str)
    #: 用户点了「取消」——面板不碰窗口（与 CreateTaskPanel 同一条纪律）
    cancelled = Signal()


    #: 成员表格列（用户 2026-11-17 晚定的四列；任务节点=只读的已完成节点）
    MEMBER_COLUMNS = ["序号", "任务名称", "任务节点", "操作"]
    MEMBER_ROW_HEIGHT = 48
    # 各列宽度；None 表示拉伸（任务名称列）
    _NUMBER_WIDTH = 96
    # 任务节点列：**下限**——实际宽度按内容实测放宽（见 _fit_stage_column），
    # 用户 2026-11-17：「任务节点 项宽一些，能够显示完整节点」。
    # 300 是"四个中文节点名 + 三个顿号"的实测宽度（约 280）再留一点余量。
    _STAGE_WIDTH = 300
    #: 任务节点列的宽度上限：再长就回到"挤掉任务名称"的老问题（超出仍可
    #: 看 tooltip 全文）。
    _STAGE_WIDTH_MAX = 520
    #: 操作列：详情 + 上移 + 下移 + 删除（文字按钮），用户 2026-11-17 要求加宽
    _ACTION_WIDTH = 236

    def __init__(
        self,
        store,
        parent=None,
        *,
        inspect: bool = False,
        members: list[str] | None = None,
        start_stage: str = DEFAULT_START_STAGE,
        initial_diagram=None,
    ):
        """
        :param inspect: ``True`` = 查看已建好的聚合任务（成员/起始节点只读，
            收起底部按钮行）。见类头「两种用途」。
        :param members: 初始成员（``inspect`` 时由调用方从 record 回填）。
        :param start_stage: 初始起始节点（同上；不在合法清单里就回默认）。
        :param initial_diagram: 初始画布内容（``inspect`` 时传**已落盘的**
            ``flow.bpmn``，用户看到的才是他上次存下的那张图；只在第一次建
            编辑器时用一次，之后换起始节点仍按派生图重建）。
        """
        super().__init__(parent)
        self._store = store
        #: 查看模式（成员/起始节点只读、没有提交按钮），见类头
        self._inspect = bool(inspect)
        #: 成员任务号，**列表顺序即合并顺序**
        self._members: list[str] = [
            str(m) for m in (members or []) if str(m).strip()
        ]
        #: 起始节点（全体成员共用；必须落在 :meth:`start_candidates` 里）
        self._start_stage = (
            start_stage if start_stage in AGGREGATE_START_STAGES
            else DEFAULT_START_STAGE
        )
        #: 首次建编辑器要用的图（``inspect`` 时是磁盘上那张；用一次就清）
        self._initial_diagram = initial_diagram
        #: **落库的**起始节点（``inspect`` 时用来判断"用户改没改"；保存成功后
        #: 由 :meth:`mark_stage_saved` 追平，见 :meth:`stage_changed`）
        self._record_stage = self._start_stage
        #: 当前候选节点（按拓扑序；成员变化时重算，见 :meth:`_sync_candidates`）
        self._candidates: tuple[str, ...] = ()
        #: 候选 → 勾选框（单选；重建时整体换掉）
        self._stage_boxes: dict[str, CheckBox] = {}
        #: 程序化勾/灭期间为 True：抑制 ``toggled`` 里的联动（否则自噬）
        self._syncing_stage = False
        self._flow_edited = False
        self._editor_panel = None
        self._build_ui()
        self._sync_candidates()
        self._fill_members()
        self._rebuild_editor()
        self._refresh_summary()


    # ---------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_MD)

        # ---- 成员行：选择按钮 + 提示 ----
        member_row = QHBoxLayout()
        member_row.setSpacing(T.SPACE_SM)
        member_label = BodyLabel("子任务：")
        # ⚠️ 行内标题一律**加粗**（用户 2026-11-17：任务类型/任务名称/子任务/
        #    上传文件 这些标签要加粗，才像"字段名"而不是正文）。
        ui.apply_to(member_label, T.SIZE_BODY, bold=True, color=T.INK)
        member_row.addWidget(member_label)
        self.pick_button = PushButton("选择子任务…")
        self.pick_button.setToolTip("弹「选择子任务」挑选要参与聚合的任务")
        self.pick_button.clicked.connect(self._open_picker)
        # 查看模式（详情页的流程入口）不给改成员：成员集合变了，已汇集的输入
        # 就失效了——那是"重建聚合任务"，不是"看流程"。
        self.pick_button.setVisible(not self._inspect)
        member_row.addWidget(self.pick_button)
        self.member_hint = CaptionLabel()
        ui.apply_to(self.member_hint, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.member_hint.setWordWrap(True)
        member_row.addWidget(self.member_hint, 1)
        layout.addLayout(member_row)

        # ---- 成员表格：序号 / 名称 / 任务节点（已完成节点）/ 操作（行内按钮）----
        self.member_table = TableWidget()
        self.member_table.setObjectName("aggregateMemberEditTable")
        self.member_table.setColumnCount(len(self.MEMBER_COLUMNS))
        self.member_table.setHorizontalHeaderLabels(self.MEMBER_COLUMNS)
        self.member_table.verticalHeader().setVisible(False)
        self.member_table.setEditTriggers(self.member_table.EditTrigger.NoEditTriggers)
        self.member_table.setSelectionBehavior(
            self.member_table.SelectionBehavior.SelectRows
        )
        self.member_table.setSelectionMode(self.member_table.SelectionMode.SingleSelection)
        self.member_table.setWordWrap(False)
        self.member_table.setShowGrid(False)
        self.member_table.setAlternatingRowColors(False)
        self.member_table.setBorderVisible(True)
        self.member_table.setBorderRadius(8)
        # ⚠️ 高度**不固定**：按当前页实际行数算（用户 2026-11-18：没有 10 条不许
        #    占 10 条的高度）。见 ``_fit_table_height``。
        self._fit_table_height(0)

        for col, align in {
            0: Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            1: Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            2: Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            3: Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
        }.items():
            header_item = self.member_table.horizontalHeaderItem(col)
            if header_item is not None:
                header_item.setTextAlignment(align)

        header = self.member_table.horizontalHeader()
        header.setFixedHeight(38)
        header.setHighlightSections(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate(
            [self._NUMBER_WIDTH, None, self._STAGE_WIDTH, self._ACTION_WIDTH]
        ):
            if width is None:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
            else:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
                header.resizeSection(col, width)

        # ⚠️ 必须先定行数：qfluent 的 TableWidget 不会因 setItem/setCellWidget
        # 自动扩行（见 picker 同款注释），漏了这行表格就是 0 行。
        self.member_table.setRowCount(0)
        layout.addWidget(self.member_table)

        # ---- 分页条：超过 MEMBER_PAGE_SIZE 才出现（用户 2026-11-18）----
        # 复用列表页那套 ``Pagination``，但**不给每页条数下拉**（规格就是最多
        # 10 行/页，让人改成 50 会直接把表格撑成 50 行高）。
        self.member_pager = Pagination(MEMBER_PAGE_SIZE, size_selector=False)
        self.member_pager.changed.connect(self._on_member_page_changed)
        self.member_pager.setVisible(False)
        layout.addWidget(self.member_pager)
        #: 成员表格当前页（1-based；越界由 :class:`Pager` 钳制）
        self._page = 1

        # ---- 起始节点：候选来自所选子任务的任务节点，checkbox 单选 ----
        #
        # 为什么是 checkbox 而不是下拉框（用户 2026-11-17 本轮）：「列举出来」
        # ——候选节点一眼全在，不用点开才知道有哪些；单选语义自己实现（勾一个
        # 别的灭），见 ``_on_stage_box_toggled``。
        stage_row = QHBoxLayout()
        stage_row.setSpacing(T.SPACE_MD)
        stage_label = BodyLabel("起始节点：")
        ui.apply_to(stage_label, T.SIZE_BODY, bold=True, color=T.INK)
        stage_row.addWidget(stage_label)
        # ⚠️ 用普通 QHBoxLayout 而不是 qfluent 的 FlowLayout：候选最多四项，
        # 一行放得下；FlowLayout 的 takeAt 在本机 PySide 下会抛
        # "expected QLayoutItem, got CheckBox" 警告（重建勾选框时 takeAt 触发），
        # 多一层宿主控件不值得。
        self._stage_layout = QHBoxLayout()
        self._stage_layout.setContentsMargins(0, 0, 0, 0)
        self._stage_layout.setSpacing(T.SPACE_LG)
        stage_row.addLayout(self._stage_layout, 1)
        layout.addLayout(stage_row)

        self.stage_hint = CaptionLabel()
        ui.apply_to(self.stage_hint, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.stage_hint.setWordWrap(True)
        layout.addWidget(self.stage_hint)

        # ---- 流程编辑器（常驻；起始节点变化整体重建）----
        self._editor_host = QWidget()
        self._editor_layout = QVBoxLayout(self._editor_host)
        self._editor_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._editor_host, 1)

        self.flow_summary = CaptionLabel()
        ui.apply_to(self.flow_summary, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.flow_summary.setWordWrap(True)
        layout.addWidget(self.flow_summary)

        # ---- 底部按钮 ----
        self._button_bar = QWidget()
        buttons = QHBoxLayout(self._button_bar)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addStretch()
        self.cancel_button = PushButton("取消")
        self.cancel_button.clicked.connect(self.cancelled.emit)
        buttons.addWidget(self.cancel_button)
        self.confirm_button = PrimaryPushButton("创建聚合任务")
        self.confirm_button.clicked.connect(self.submit)
        buttons.addWidget(self.confirm_button)
        layout.addWidget(self._button_bar)
        # 查看模式：没有"创建"这回事，按钮行整块收起（保存/关闭在页面顶栏）
        self._button_bar.setVisible(not self._inspect)

    # ------------------------------------------------------------ 编辑器
    def _rebuild_editor(self) -> None:
        """按**当前起始节点**重建流程编辑器（整体重建，见模块头）。

        ⚠️ 首次构建时若给了 ``initial_diagram``（查看已建好的聚合任务：磁盘上
        的 ``flow.bpmn``，可能被用户在创建时改过），就用它——否则用户进"查看
        流程"看到的会是派生图，而不是自己存下的那张。用过一次即清空，之后
        换起始节点仍按派生图重建（根变了，旧图不能原地改）。
        """
        from desktop.components.bpmn_editor_panel import BpmnEditorPanel

        if self._editor_panel is not None:
            self._editor_panel.setParent(None)
            self._editor_panel.deleteLater()
            self._editor_panel = None
        initial = self._initial_diagram
        self._initial_diagram = None
        diagram = initial if getattr(initial, "nodes", None) else None
        panel = BpmnEditorPanel(
            diagram if diagram is not None else derive_aggregate_diagram(self._start_stage),
            self,
            editable=True,
            # 「恢复默认」回到**当前起始节点**的派生图（不是全局默认模板）
            reset_factory=lambda: derive_aggregate_diagram(self._start_stage),
            # 画布不自己滚动：创建任务页整体纵向滚动（用户 2026-11-18）
            scroll=False,
        )
        panel.diagram_changed.connect(self._on_diagram_changed)
        self._editor_layout.addWidget(panel)
        self._editor_panel = panel
        self._flow_edited = False

    def _on_diagram_changed(self) -> None:
        self._flow_edited = True
        self._refresh_summary()

    # ------------------------------------------------------------ 查询
    def current_stage(self) -> str:
        """当前起始节点（全体成员共用；无成员时回落默认值）。"""
        return self._start_stage

    def record_stage(self) -> str:
        """**落库的**起始节点（用户没改过时与 :meth:`current_stage` 相同）。"""
        return self._record_stage

    def stage_changed(self) -> bool:
        """用户是否改了起始节点（改没改决定保存时要不要弹"数据作废"确认）。

        ⚠️ 判据是"与落库值比"而不是"点过没有"——用户改回原值再保存不该弹框。
        """
        return self._start_stage != self._record_stage

    def mark_stage_saved(self) -> None:
        """起始节点已落库：把记录值追平，之后 :meth:`stage_changed` 复归 ``False``。"""
        self._record_stage = self._start_stage

    def members(self) -> list[str]:
        """当前成员（只读副本）。"""
        return list(self._members)

    def member_stages(self) -> list[str]:
        """各成员的节点（与 :meth:`members` 对齐；全体共用起始节点 ⇒ 值相同）。

        ⚠️ 形状保持"逐成员"是为了跟 store 的 ``member_stages`` 字段一致——
        用户 2026-11-17 本轮改回**全体共用一个节点**，值必然一模一样。
        """
        return [self._start_stage] * len(self._members)

    def set_members(self, members: list[str]) -> None:
        """回填成员（自测快路径）：候选与起始节点按新成员重算。"""
        self._members = [str(m) for m in (members or []) if str(m).strip()]
        self._page = 1          # 换了一批成员就回第一页（旧页码没有意义）
        self._sync_candidates()
        self._fill_members()

    def set_start_stage(self, stage: str) -> None:
        """设起始节点（自测/回填用）：走勾选框，信号链自然跑一遍。

        不在候选里的节点直接忽略（它对这个成员集合不存在）——不偷偷改数据，
        免得界面勾着的和实际用的不是同一个（用户点不到的东西不该被设上）。
        """
        box = self._stage_boxes.get(stage)
        if box is None:
            return
        box.setChecked(True)

    def current_diagram(self):
        """编辑器手里那张图（派生图或用户改过的版本）。"""
        if self._editor_panel is not None:
            return self._editor_panel.diagram()
        return derive_aggregate_diagram(self._start_stage)

    def result_diagram(self):
        """要落盘的流程图：编辑过 = 用户那张；没动过 = ``None``（store 落派生图）。"""
        return self.current_diagram() if self._flow_edited else None

    def uses_custom_flow(self) -> bool:
        return self._flow_edited

    def _refresh_summary(self) -> None:
        diagram = self.current_diagram()
        from desktop.components.flow_dialog import summarize

        self.flow_summary.setText(
            f"起始节点「{aggregate_start_label(self._start_stage)}」——{summarize(diagram)}"
        )

    # ------------------------------------------------------------ 提交
    def can_submit(self) -> bool:
        return bool(self._members)

    def _validate_flow(self) -> bool:
        """提交前过流程合法性（与普通创建面板同一道闸；没编辑过不校验）。

        ⚠️ 必须带上 ``aggregate_start``（硬规则 ⑦）：用户编辑过的图把别的
        步骤挪到起始节点前面，「聚合输入」汇集的产物就喂错了步骤——保存时
        当场拒绝。没编辑过时画布就是按起始节点派生的图，天然满足，不必验。
        """
        if not self._flow_edited:
            return True
        from desktop.steps.validate import validate_flow
        from desktop.ui.toast import show_toast

        result = validate_flow(
            self.current_diagram(), aggregate_start=self._start_stage
        )
        if not result.ok:
            show_toast(
                self.window(), "warning", "流程不合法，未创建",
                "；".join(result.errors),
            )
            return False
        if result.warnings:
            show_toast(
                self.window(), "warning", "流程提示",
                "；".join(result.warnings),
            )
        return True

    def submit(self) -> None:
        """校验通过就发 :attr:`submitted`；成员为空先拦（聚合没有成员不成立）。"""
        from desktop.ui.toast import show_toast

        if not self.can_submit():
            show_toast(
                self.window(), "warning", "还没有选择子任务",
                "点「选择子任务…」至少选一个子任务再创建聚合任务。",
            )
            return
        if not self._validate_flow():
            return
        self.submitted.emit(
            self.members(), self.member_stages(), self.result_diagram()
        )

    def reset(self) -> None:
        """回到刚打开的样子：成员清空、候选回到全部节点、起始节点回默认。"""
        self._members = []
        self._page = 1
        self._start_stage = DEFAULT_START_STAGE
        # 没有成员 ⇒ 候选 = 全部节点；先重算候选再重建编辑器（顺序别反）
        self._sync_candidates()
        self._fill_members()
        self._rebuild_editor()
        self._refresh_summary()


__all__ = ["AggregateCreatePanel"]
