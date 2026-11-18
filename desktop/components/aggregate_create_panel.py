# -*- coding: utf-8 -*-
"""**聚合任务**创建面板（创建任务页「任务类型：聚合任务」的内容）。

## 用户口径（2026-11-17）

> 同一部书有多个 PDF 子集，每个子集作为一个任务处理；拼版之后想把所有
> 拼版后的图片组合成一个 PDF——创建一个聚合任务，选择多个子任务、选择
> 图片拼版节点，同时可以对这几个子任务进行排序。

面板三件事：

1. **选子任务**：「选择子任务…」按钮弹「选择子任务」弹窗多选
   (:class:`AggregateMemberPicker`，**搜索 + 分页的勾选表格**，与任务管理
   列表同一套观感：节点状态胶囊/匹配判据/分页控件全部复用)；已选成员进
   下方成员表格，弹窗里勾掉已有的成员即移除，新勾的按任务号追加在后面
   ——**已排好的顺序不被弹窗冲掉**；
2. **成员表格**（用户 2026-11-17 晚：列表升级为表格，操作全在行内）：
   列 = 序号 / 任务名称 / **任务节点** / 操作——
   - **任务节点**：该子任务**已经完成**的节点（只读展示，不含「提取图片」）
     ——它是"起始节点能选什么"的依据，一眼看到每个子任务各自跑到了哪；
     列宽按**内容实测**放宽（最长那行的节点名全显示，不再裁字）；
   - **操作**：行内「详情 / 上移 / 下移 / 删除」（详情＝**非模态预览窗**，
     不再跳走创建页；顺序有意义，决定合并页序）；
   - 表格上方「选择子任务…」随时追加（同一个弹窗）。
3. **起始节点**（用户 2026-11-17 本轮：checkbox 列表 + **单选**）：
   候选 = 所选子任务里**任意一个已经完成**的任务节点（逐成员取
   :meth:`store.completed_aggregate_stages`，再用
   :func:`desktop.steps.aggregate.any_member_stages` 求**并集**；用户
   2026-11-18 口径，取代早先"每个成员都完成过"的交集）。全体子任务共用这
   一个节点，选它就等于选"流程从哪开始"。
   ⚠️ 并集的代价必须让用户看见：选中的节点有成员没跑过 ⇒ 汇集时缺它的
   页面，所以候选下方**点名**这些子任务（:func:`missing_members`）。
   ⚠️ 勾选是**单选**：勾一个别的自动灭；点掉当前唯一勾选不生效（不可能
   出现"没有起始节点"）。还没选成员、或并集为空时兜底列出全部候选
   （提交时 ``store`` 仍会校验）。
4. **流程**：起始节点变化 ⇒ 流程编辑器换到新派生图（开始节点自动变化）。

流程编辑器常驻（与普通创建页同一条纪律）：展示
:func:`desktop.steps.aggregate.derive_aggregate_diagram` 的派生图，用户可以
继续拖改；改过就随 ``submitted`` 一起交出去，没改过传 ``None``（store 落
派生图本身）。

⚠️ 起始节点变化会**整体重建编辑器**（派生图变了，旧图不能原地改）；
用户在旧根下做的流程编辑随之丢弃——起始节点是流程的根，根换了的
"自定义"没有意义。同理，成员集合变化导致候选集变化时，起始节点若不在
新候选里就自动落到新候选的第一个（见 :meth:`_sync_candidates`）。
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CheckBox,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    TableWidget,
    ToolButton,
)
from qfluentwidgets import FluentIcon as FIF

from desktop import ui
from desktop.components.pagination import DEFAULT_PAGE_SIZE, Pager, Pagination
from desktop.components.task_table import StageChips, task_row_matches
from desktop.steps.aggregate import (
    AGGREGATE_START_STAGES,
    aggregate_start_label,
    any_member_stages,
    derive_aggregate_diagram,
    missing_members,
    preferred_start_stage,
)
from desktop.ui import theme as T

#: 成员表格**每页最多**几行（用户 2026-11-18：「最多能 10 条一页显示，多余 10 条
#: 分页显示，但是没有 10 条不能占用 10 条高度」）。表格高度按**当前页实际行数**
#: 算（见 ``_fit_table_height``），不再是一个固定值。
MEMBER_PAGE_SIZE = 10

#: 表头高度（px）：算表格总高 = 表头 + 行数 × 行高。
MEMBER_HEADER_HEIGHT = 38

#: 默认起始节点：用户的典型场景是"各子任务拼版之后合并成一本书"。
DEFAULT_START_STAGE = "imposition"


class AggregateMemberPicker(QWidget):
    """「选择子任务」弹窗的**内容**（搜索 + 分页的勾选表格；外壳由
    :func:`shell_dialog` 给）。

    列 = 勾选（表头只有复选框、无文字）/ 序号 / 任务名称 / 节点状态 / 创建时间，与任务管理列表同一套
    观感（边框/圆角/表头/行高取 :class:`desktop.components.task_table.TaskTable`
    的参数）；搜索与分页复用 ``Pagination``/``Pager``，匹配判据共用
    ``task_table.task_row_matches``——「过滤 → 分页 → 填表」的数据流向与
    列表页一致：搜索/翻页只重画，不重新读盘。

    - 候选：普通任务（聚合任务不能再嵌套聚合），按任务号**倒序**（新建的排
      最前，用户 2026-11-18：「任务列表要倒序」——刚建的任务不用翻到末页找）；
    - 勾选状态记在 ``self._checked``：**翻页 / 搜索 / 换每页条数都不会丢**；
    - ``checked_ids()`` 按**列表顺序**（任务号倒序）返回——面板端「勾掉即移除、
      新勾追加」的语义不变。

    勾选列放**真 CheckBox 控件**而不是勾选型表格项：qfluent 的表格委托只
    自绘复选框（``_drawCheckBox``），不处理点击切换（``editorEvent`` 未重写），
    原生 toggle 矩形和自绘位置对不齐——控件是唯一点击行为确定的做法。

    数据来源：调用方给**含 stages 的全量行**（``TaskRowsWorker`` 的产物，
    与任务管理列表同一份数据），节点状态胶囊复用 ``task_table.StageChips``；
    行缺 stages 时按空处理。⚠️ 离屏自测**不会**真弹模态：直接实例化本类、
    操作 ``set_rows`` / ``set_checked`` 验证逻辑，``build_dialog()`` 只在真用时才调。
    """

    # 第 0 列表头不放文字（用户 2026-11-18：「表头"勾选"这个文字不需要」
    # ——那一格住的是全选本页的复选框，见 ``header_check``）。
    COLUMNS = ["", "序号", "任务名称", "节点状态", "创建时间"]

    #: 行高与任务管理列表一致（56px）：节点状态胶囊的容器锁这个高
    ROW_HEIGHT = 56

    # 各列宽度；None 表示拉伸（任务名称列）。
    _CHECK_WIDTH = 64
    _NUMBER_WIDTH = 72
    # 节点状态列：与 TaskTable 同宽（最多 5 枚胶囊，见那边算账）
    _STAGES_WIDTH = 320
    _TIME_WIDTH = 150

    _HEADER_ALIGN = {
        0: Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
        1: Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
        2: Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        3: Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        4: Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
    }

    def __init__(self, rows: list[dict], checked_ids: list[str], parent=None):
        super().__init__(parent)
        # 候选：普通任务（聚合任务不嵌套聚合），按任务号**倒序**——最新建的
        # 任务排在第一页（用户 2026-11-18）
        self._all_rows = self._normalize(rows)
        self._checked = set(checked_ids or [])
        self._keyword = ""
        self._page = 1
        self._page_size = DEFAULT_PAGE_SIZE
        self._filtered: list[dict] = []
        self._page_rows: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_SM)

        hint = CaptionLabel(
            "勾选要参与聚合的任务（普通任务）；聚合任务不能再嵌套聚合。"
        )
        ui.apply_to(hint, T.SIZE_CAPTION, color=T.INK_FAINT)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ---- 搜索条：与列表页同一套交互（打字即过滤，只影响展示）----
        search_row = QHBoxLayout()
        search_row.setSpacing(T.SPACE_SM)
        self.search_edit = SearchLineEdit()
        self.search_edit.setPlaceholderText("搜索任务名或源文件名")
        self.search_edit.setFixedWidth(280)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_keyword_changed)
        search_row.addWidget(self.search_edit)
        self.match_hint = CaptionLabel()
        ui.apply_to(self.match_hint, T.SIZE_CAPTION, color=T.INK_FAINT)
        search_row.addWidget(self.match_hint, 1)
        layout.addLayout(search_row)

        # ---- 表格 ----
        from qfluentwidgets import TableWidget

        self.table = TableWidget()
        self.table.setObjectName("aggregateMemberTable")
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)

        # 表头对齐跟随列内容（与 TaskTable 同一条纪律：水平对齐必须或上
        # AlignVCenter，否则表头文字顶到上沿）
        for col, align in self._HEADER_ALIGN.items():
            header_item = self.table.horizontalHeaderItem(col)
            if header_item is not None:
                header_item.setTextAlignment(align)

        header = self.table.horizontalHeader()
        header.setFixedHeight(38)
        header.setHighlightSections(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate(
            [self._CHECK_WIDTH, self._NUMBER_WIDTH, None,
             self._STAGES_WIDTH, self._TIME_WIDTH]
        ):
            if width is None:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
            else:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
                header.resizeSection(col, width)

        # ---- 表头「勾选」列的**全选本页**复选框（用户 2026-11-18：表头
        # 「勾选」要能一次勾选本页所有列表数据）----
        # QHeaderView 不支持 setCellWidget，只能把真 CheckBox 作为 header 的
        # 子控件盖在第 0 列上，位置随列宽/横滚/表头尺寸同步（_place_header_check）。
        self.header_check = CheckBox(header)
        self.header_check.setToolTip("勾选/取消本页全部任务")
        self.header_check.toggled.connect(self._on_header_check_toggled)
        header.sectionResized.connect(lambda *_: self._place_header_check())
        header.sectionMoved.connect(lambda *_: self._place_header_check())
        header.geometriesChanged.connect(self._place_header_check)
        self.table.horizontalScrollBar().valueChanged.connect(
            lambda *_: self._place_header_check()
        )

        # ⚠️ 必须先定行数：qfluent 的 TableWidget 不会因 setItem/setCellWidget
        # 自动扩行（TaskTable 同款写法），漏了这行表格就是 0 行。
        self.table.setRowCount(0)
        layout.addWidget(self.table, 1)

        # ---- 分页条：复用列表页的 Pagination（总数/每页条数/翻页）----
        # 占满整行（stretch=1）：控件内部自带的 stretch 会把「共 N 条」顶到
        # 左沿、「每页条数/翻页」顶到**右沿**——与任务管理列表同一布局
        # （用户 2026-11-18：分页应该在右边，不是挤在中间）。
        pager_row = QHBoxLayout()
        pager_row.setContentsMargins(0, 0, 0, 0)
        self.pagination = Pagination(self._page_size)
        self.pagination.changed.connect(self._on_page_changed)
        self.pagination.page_size_changed.connect(self._on_page_size_changed)
        pager_row.addWidget(self.pagination, 1)
        layout.addLayout(pager_row)

        self._render()

    # ---------------------------------------------------------------- 数据
    @staticmethod
    def _normalize(rows: list[dict]) -> list[dict]:
        """候选行：剔除聚合任务、按任务号**倒序**（新建的排前面）。

        ⚠️ 排序对象是**字符串**任务号（四位零填充），字典序与数字序一致；
        换成正序就是"翻到最后一页才能找到刚建的任务"——用户 2026-11-18 报的
        正是这个。
        """
        return sorted(
            (r for r in rows if r.get("kind") != "aggregate"),
            key=lambda r: str(r.get("id", "")),
            reverse=True,
        )

    def set_rows(self, rows: list[dict]) -> None:
        """整批替换候选行（后台读完/回填用）；页码回第 1 页。"""
        self._all_rows = self._normalize(rows)
        self._page = 1
        self._render()

    # ---------------------------------------------------------------- 渲染
    def _render(self) -> None:
        """过滤 → 分页 → 填表（只依赖缓存，不读盘，搜索时可逐字符调）。"""
        keyword = self._keyword.strip()
        self._filtered = [
            r for r in self._all_rows if task_row_matches(r, keyword)
        ]
        pager = Pager(len(self._filtered), self._page_size, self._page)
        # 页码可能越界（搜索后结果变少），一律用钳制后的页码算切片
        self._page = pager.clamped_page
        self._fill_table(pager.page_slice(self._filtered))
        self.pagination.set_pager(pager)

        total, matched = len(self._all_rows), len(self._filtered)
        if keyword and matched != total:
            self.match_hint.setText(f"匹配 {matched} / {total} 个任务")
        elif keyword:
            self.match_hint.setText(f"匹配 {matched} 个任务")
        else:
            self.match_hint.setText("")

    def _fill_table(self, rows: list[dict]) -> None:
        """填当前页；勾选框按 ``self._checked`` 回显。"""
        self._page_rows = list(rows)
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))
        for row, task in enumerate(rows):
            tid = str(task.get("id", ""))
            self.table.setCellWidget(row, 0, self._check_widget(tid))
            number_item = QTableWidgetItem(tid)
            number_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, number_item)
            self.table.setItem(row, 2, QTableWidgetItem(str(task.get("name") or "")))
            self.table.setCellWidget(row, 3, StageChips(task.get("stages") or []))
            created_at = task.get("created_at") or 0
            time_item = QTableWidgetItem(
                datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M")
                if created_at
                else ""
            )
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, time_item)
            self.table.setRowHeight(row, self.ROW_HEIGHT)
        self._sync_header_check_state()
        self._place_header_check()

    def _check_widget(self, task_id: str) -> QWidget:
        """勾选格：真 CheckBox 居中（点击行为确定，见类头说明）。"""
        box = CheckBox()
        box.setChecked(task_id in self._checked)
        # setChecked 只在值变化时发 toggled——回显不会误改 _checked
        box.toggled.connect(
            lambda checked, tid=task_id: self._on_check_toggled(tid, checked)
        )
        wrap = QWidget()
        wrap.setFixedHeight(self.ROW_HEIGHT)
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(box, 0, Qt.AlignmentFlag.AlignCenter)
        return wrap

    # ------------------------------------------------------------ 搜索/分页
    def _on_keyword_changed(self, text: str) -> None:
        """搜索框变化：重置到第 1 页再渲染（与列表页同一处理）。"""
        self._keyword = text or ""
        self._page = 1
        self._render()

    def _on_page_changed(self, page: int) -> None:
        self._page = page
        self._render()

    def _on_page_size_changed(self, page_size: int) -> None:
        """换每页条数：页码按比例换算，别让用户看着列表乱跳（同列表页）。"""
        pager = Pager(len(self._filtered), self._page_size, self._page)
        self._page = pager.with_page_size(page_size).page
        self._page_size = page_size
        self._render()

    # ---------------------------------------------------------------- 勾选
    def _on_check_toggled(self, task_id: str, checked: bool) -> None:
        """勾选状态集中记在 ``self._checked``——翻页/搜索不丢。"""
        if checked:
            self._checked.add(task_id)
        else:
            self._checked.discard(task_id)
        self._sync_header_check_state()

    def _place_header_check(self) -> None:
        """表头复选框盖在第 0 列的居中位置（随列宽/横滚/表头尺寸同步）。"""
        header = self.table.horizontalHeader()
        width, height = header.sectionSize(0), header.height()
        hint = self.header_check.sizeHint()
        if hint.width() <= 0:
            return
        self.header_check.setGeometry(
            max(0, header.sectionViewportPosition(0) + (width - hint.width()) // 2),
            max(0, (height - hint.height()) // 2),
            hint.width(),
            hint.height(),
        )

    def _sync_header_check_state(self) -> None:
        """表头复选框回显：本页**全部**勾上才亮（部分勾选显示为空）。"""
        ids = [str(r.get("id", "")) for r in self._page_rows]
        box = self.header_check
        box.blockSignals(True)  # 回显不能被当成用户操作（否则自噬）
        box.setChecked(bool(ids) and all(t in self._checked for t in ids))
        box.blockSignals(False)

    def _on_header_check_toggled(self, checked: bool) -> None:
        """表头复选框：一次勾选/取消**本页**全部任务（用户 2026-11-18）。

        其他页已勾的状态不动（``self._checked`` 集中记，跨页/搜索不丢）；
        点掉当前页的勾也不会误伤别的页。
        """
        for task in self._page_rows:
            tid = str(task.get("id", ""))
            if checked:
                self._checked.add(tid)
            else:
                self._checked.discard(tid)
        self._fill_table(self._page_rows)

    def set_checked(self, task_id: str, checked: bool) -> None:
        """程序化勾选/取消（自测与回填用；与手点同一入口）。"""
        self._on_check_toggled(str(task_id), bool(checked))
        # 当前页上这行已经画出来的话，同步勾选框显示
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item is not None and str(item.text()) == str(task_id):
                box = self.table.cellWidget(row, 0).findChildren(CheckBox)
                if box:
                    box[0].setChecked(bool(checked))
                break

    def checked_ids(self) -> list[str]:
        """勾选中的任务号，按**列表顺序**（任务号倒序，最新的在前）。"""
        return [
            str(r.get("id", ""))
            for r in self._all_rows
            if str(r.get("id", "")) in self._checked
        ]

    def build_dialog(self, parent=None):
        """把本面板装进外壳（真用时才调；自测直接操作面板本身）。

        ``resizable=True``（用户 2026-11-18）：「选择子任务弹窗要显示窗口功能，
        放大缩小」——标题栏出现最小化/最大化按钮，也能拖边拉伸。默认尺寸
        1040×720 只是**开窗**尺寸，最小尺寸由外壳按 3/4 兜底。
        """
        from desktop.components.dialog_shell import shell_dialog

        return shell_dialog(
            "选择子任务",
            self,
            parent,
            size=(1040, 720),
            ok_text="确定",
            resizable=True,
        )


class AggregateCreatePanel(QWidget):
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

    # -------------------------------------------------------- 起始节点候选
    def start_candidates(self) -> tuple[str, ...]:
        """当前候选起始节点（按拓扑序；含「提取图片」，可作起点）。

        候选 = 所选子任务里**任意一个已经完成**的任务节点（用户 2026-11-18，
        取代早先"每个成员都完成过"的交集）：逐成员取
        :meth:`store.completed_aggregate_stages`（历史上成功过才算完成，
        拼版=已启用且有拼版页），再用
        :func:`desktop.steps.aggregate.any_member_stages` 求**并集**
        ——"现有任务已经存在生效的节点是提取/检测/去底，因此可以从这些节点
        里挑一个"。交集口径在"各子集进度不同步"时会收成空集（实测三个子集
        分别完成 检测/检测/去底 ⇒ 交集为空），列表就退化成兜底全集，等于
        没跟着子任务变。

        ⚠️ 并集意味着某些成员可能缺这个节点，汇集时缺它的页面——
        :meth:`_refresh_stage_hint` 会点名这些子任务。

        还没选成员、或并集为空时兜底成全部候选：列表空着用户连"先选一个"
        都做不到（提交时 ``store`` 仍会校验）。

        ⚠️ 查看模式（``inspect``）额外一条：**落库的那个起始节点必须在候选
        里**。它当年是按成员当时的进度选的，成员后来重跑/清理过的话并集可能
        已经不含它——那样勾选框里就看不到"当前起点"，看着像坏了。这里把它
        按拓扑序补回清单（只影响显示，不改落库值）。
        """
        done = self._member_done_lists()
        union = any_member_stages(done)
        stages = tuple(union or AGGREGATE_START_STAGES)
        if self._inspect and self._start_stage not in stages:
            wanted = set(stages) | {self._start_stage}
            stages = tuple(s for s in AGGREGATE_START_STAGES if s in wanted)
        return stages

    def _member_done_lists(self) -> list[tuple[str, ...]]:
        """逐成员**已完成**的节点（与 :meth:`members` 对齐；读失败按空算）。"""
        return [self._member_completed_of(tid) for tid in self._members]

    def _member_completed_of(self, task_id: str) -> tuple[str, ...]:
        """某个子任务**已经完成**的节点（读不出来返回空元组，交给兜底）。"""
        try:
            return tuple(self._store.completed_aggregate_stages(task_id))
        except Exception:  # noqa: BLE001 —— 进度读坏了不能拖死创建页
            return ()

    def _member_name(self, task_id: str) -> str:
        """子任务名（读不到回落任务号；提示文案用）。"""
        try:
            record = self._store.get_task(task_id) or {}
        except Exception:  # noqa: BLE001 —— 提示文案读不到名字不算错
            record = {}
        return str(record.get("name") or task_id)

    def _sync_candidates(self) -> None:
        """重算候选并重建勾选框；起始节点不在候选里就按
        :func:`preferred_start_stage` 落一个默认值。

        ⚠️ 起始节点被**挪**了（成员换了一批，原来那个节点没人完成过）时必须
        重建派生图——否则勾着的和图上画的是两个不同的起点（自测实测：
        只剩「拼版/排版」的成员加进来后，勾选框是拼版、图上还从 PDF排版
        开始）。
        """
        done = self._member_done_lists()
        self._candidates = tuple(self.start_candidates())
        moved = False
        if self._start_stage not in self._candidates:
            fallback = preferred_start_stage(done, self._start_stage)
            if fallback not in self._candidates:
                fallback = self._candidates[0] if self._candidates else DEFAULT_START_STAGE
            if fallback != self._start_stage:
                self._start_stage = fallback
                moved = True
        self._rebuild_stage_boxes()
        if moved:
            self._rebuild_editor()
            self._refresh_summary()

    def _rebuild_stage_boxes(self) -> None:
        """按候选重建 checkbox 列表（回显当前起始节点）。"""
        while self._stage_layout.count():
            item = self._stage_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._stage_boxes = {}
        self._syncing_stage = True
        try:
            for stage in self._candidates:
                box = CheckBox(aggregate_start_label(stage))
                box.setChecked(stage == self._start_stage)
                box.toggled.connect(
                    lambda checked, s=stage: self._on_stage_box_toggled(s, checked)
                )
                # 查看模式下**也可以改**（用户 2026-11-18：「起始节点可以切换
                # 变更」）——改完保存流程时会弹确认，讲清"历史汇集数据作废"。
                box.setToolTip(
                    f"选择「{aggregate_start_label(stage)}」"
                    if not self._inspect
                    else "改起始节点会让已汇集的输入与历史处理结果作废"
                    "（保存流程时会再确认一次）"
                )
                self._stage_layout.addWidget(box)
                self._stage_boxes[stage] = box
            self._stage_layout.addStretch()
        finally:
            self._syncing_stage = False
        self._refresh_stage_hint()

    def _refresh_stage_hint(self) -> None:
        """候选来源一句话 + **选中的节点有谁没跑过**（并集的代价必须可见）。"""
        count = len(self._members)
        if not count:
            hint = (
                "先选择子任务；候选 = 所选子任务里任意一个已经完成的任务节点"
                "（单选：选哪个节点，流程就从哪个节点开始）。"
            )
        else:
            done = self._member_done_lists()
            if not any(done):
                # 一个节点都没完成 ⇒ 候选是兜底全集（不是"推出来的"），
                # 说真话：别让用户以为这些节点都能直接拿来当起点。
                hint = (
                    f"所选 {count} 个子任务都还没有完成任何节点；"
                    "候选暂列全部节点，等子任务跑出结果后这里会跟着变。"
                )
            else:
                hint = (
                    f"候选来自 {count} 个子任务里任意一个已经完成的任务节点"
                    "（并集，单选）：选哪个节点，聚合流程就从哪个节点开始，"
                    "它前面的步骤会被丢弃。"
                )
                missing = missing_members(self._start_stage, done)
                if missing:
                    names = "、".join(
                        self._member_name(self._members[i]) for i in missing
                    )
                    hint += (
                        f"\n⚠️ 未完成「{aggregate_start_label(self._start_stage)}」："
                        f"{names} —— 汇集时不会带上这些子任务的页面。"
                    )
        if self._inspect:
            hint += (
                "\n（子任务只读；起始节点可以改——改了保存时会提示"
                "「历史汇集数据将作废」，确认后按新起点重新汇集。）"
            )
        self.stage_hint.setText(hint)

    def _on_stage_box_toggled(self, stage: str, checked: bool) -> None:
        """**单选**语义：勾一个别的全灭；点掉当前唯一勾选不生效。

        ⚠️ 点掉不生效是刻意的：不可能存在"没有起始节点"的聚合任务；也不再
        弹提示（用户只是想看看点一下，弹窗会烦）。``_syncing_stage`` 期间的
        信号一律忽略——批量改勾选状态不能被当成用户操作（否则自噬）。
        """
        if self._syncing_stage:
            return
        if not checked:
            box = self._stage_boxes.get(stage)
            if stage == self._start_stage and box is not None:
                self._syncing_stage = True
                try:
                    box.setChecked(True)
                finally:
                    self._syncing_stage = False
            return
        if stage == self._start_stage:
            return
        self._syncing_stage = True
        try:
            for key, box in self._stage_boxes.items():
                box.setChecked(key == stage)
        finally:
            self._syncing_stage = False
        self._start_stage = stage
        # 派生图跟着换（旧图不能原地改：根变了，那份"自定义"没有意义）
        self._rebuild_editor()
        self._refresh_summary()
        # 换节点 ⇒ "谁没跑过这一步"跟着变（提示里的点名要重算）
        self._refresh_stage_hint()

    # ------------------------------------------------------------ 成员
    def _member_pager(self) -> Pager:
        """成员表格的分页状态（每页固定 ``MEMBER_PAGE_SIZE`` 行）。"""
        return Pager(len(self._members), MEMBER_PAGE_SIZE, self._page)

    def _member_index(self, local_row: int) -> int:
        """表格里的行号（当前页内）→ **成员下标**；非法行返回 ``-1``。"""
        if local_row < 0:
            return -1
        index = (self._page - 1) * MEMBER_PAGE_SIZE + local_row
        return index if index < len(self._members) else -1

    def _member_local_row(self, index: int) -> int:
        """成员下标 → 表格行号（不在当前页时返回 ``-1``，选中会退化成不选）。"""
        row = index - (self._page - 1) * MEMBER_PAGE_SIZE
        return row if 0 <= row < self.member_table.rowCount() else -1

    def _on_member_page_changed(self, page: int) -> None:
        """翻页：只重画当前页（成员顺序与已选集合都不动）。"""
        self._page = max(1, int(page))
        self._fill_members()

    def _fit_table_height(self, rows: int) -> None:
        """表格高度跟**当前页实际行数**走（用户 2026-11-18）。

        「最多 10 条一页，但是没有 10 条不能占用 10 条高度」——所以不是固定
        高度，而是 ``表头 + 行数 × 行高``；0 条时也有一行空白占位（见
        ``_fill_members``），高度跟那一行走。
        """
        height = MEMBER_HEADER_HEIGHT + max(0, int(rows)) * self.MEMBER_ROW_HEIGHT
        self.member_table.setFixedHeight(int(height) + 2)

    def _fill_members(self) -> None:
        """按 ``self._members`` 重画成员表格的**当前页**。

        数据仍是 `self._members`（有序、全量）；表格只画 ``[start, end)`` 这
        一段，行内按钮回调带上**成员下标**（不是表格行号），翻页才不会错位。
        """
        pager = self._member_pager()
        # 删掉/减少后页码越界：跟着钳制回来（末页删空不能停在空白页）
        self._page = pager.clamped_page
        start, end = pager.slice_bounds()
        page_ids = self._members[start:end]

        # 0 条时给**一行空白占位**（用户 2026-11-18）：表格塌成只剩表头看着
        # 像坏了；占位行不带任何控件，纯空行撑起一行的高度。
        rows: list = page_ids if page_ids else [None]

        self.member_table.setRowCount(0)
        self.member_table.setRowCount(len(rows))
        for local_row, tid in enumerate(rows):
            if tid is None:
                self.member_table.setRowHeight(local_row, self.MEMBER_ROW_HEIGHT)
                continue
            index = start + local_row
            record = self._store.get_task(tid)
            name = str(record.get("name") or "") if record else ""
            number_item = QTableWidgetItem(tid)
            number_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.member_table.setItem(local_row, 0, number_item)
            self.member_table.setItem(local_row, 1, QTableWidgetItem(name))
            self.member_table.setCellWidget(
                local_row, 2, self._node_widget(self._completed_stages(tid))
            )
            self.member_table.setCellWidget(
                local_row, 3, self._action_widget(index)
            )
            self.member_table.setRowHeight(local_row, self.MEMBER_ROW_HEIGHT)

        self._fit_stage_column()
        self._fit_table_height(len(rows))
        # 只有超过一页才出现分页条（10 条以内翻页没有意义，白占一行高度）
        self.member_pager.setVisible(pager.total > MEMBER_PAGE_SIZE)
        self.member_pager.set_pager(pager)

        count = len(self._members)
        self.member_hint.setText(
            f"已选 {count} 个（顺序即合并页序）" if count else "尚未选择子任务"
        )

    def _completed_stages(self, tid: str) -> list[str]:
        """该子任务**已经完成**的节点（读失败按"没完成"降级）。"""
        try:
            return list(self._store.completed_aggregate_stages(tid))
        except Exception:  # noqa: BLE001 - 进度读失败按"没完成"降级
            return []

    def _fit_stage_column(self) -> None:
        """任务节点列宽按**实际控件**放宽（用户 2026-11-17：「宽一些，能够显示
        完整节点」）。

        ⚠️ 量的是**已经建好的那一格**的 ``sizeHint()``（标签自己的字号 + 两侧
        内边距），不另算一份 ``QFontMetrics``：另起一份字体去度量，量出来的
        和画出来的未必是同一套（字体回退/DPI 一换就错位，结果就是"量着够宽、
        实际照样被裁"）。
        ⚠️ 只**加宽**不缩窄（下限 ``_STAGE_WIDTH``），且封顶
        ``_STAGE_WIDTH_MAX``：再长就让任务名称列（拉伸列）让位，别把表格撑出
        可视区。
        """
        needed = self._STAGE_WIDTH
        for row in range(self.member_table.rowCount()):
            wrap = self.member_table.cellWidget(row, 2)
            if wrap is not None:
                needed = max(needed, wrap.sizeHint().width() + 4)
        width = min(needed, self._STAGE_WIDTH_MAX)
        self.member_table.horizontalHeader().resizeSection(2, int(width))

    def _node_widget(self, done: list[str]) -> QWidget:
        """任务节点格：该子任务**已经完成**的节点（只读）。

        数据走 :meth:`store.completed_aggregate_stages`——与起始节点候选
        **同一份判据**（含「提取图片」，用户 2026-11-18）：用户看着每行各自
        完成了什么，就知道下面那排候选为什么是这几个。没有已完成节点时给
        灰字占位，别让格子空着像坏了。
        """
        wrap = QWidget()
        wrap.setFixedHeight(self.MEMBER_ROW_HEIGHT)
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(T.SPACE_SM, 0, T.SPACE_SM, 0)
        if done:
            label = BodyLabel("、".join(aggregate_start_label(s) for s in done))
            ui.apply_to(label, T.SIZE_CAPTION, color=T.INK)
            label.setToolTip(
                "该子任务已完成、可作为聚合节点的任务节点：\n"
                + "\n".join(aggregate_start_label(s) for s in done)
            )
        else:
            label = CaptionLabel("（暂无已完成节点）")
            ui.apply_to(label, T.SIZE_CAPTION, color=T.INK_FAINT)
        lay.addWidget(label)
        lay.addStretch()
        return wrap

    def _action_widget(self, row: int) -> QWidget:
        """操作格：行内「详情 / 上移 / 下移 / 删除」（行内即点即生效）。

        ⚠️ 「删除」是**文字按钮**（用户 2026-11-17：「移除按钮改成删除按钮」）：
        图标 × 看不出是"移出聚合"，文字最直接；tooltip 再说清它只影响本次
        聚合、不删任务本身。
        """
        wrap = QWidget()
        wrap.setFixedHeight(self.MEMBER_ROW_HEIGHT)
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(T.SPACE_SM, 0, T.SPACE_SM, 0)
        # 与任务列表行内操作列同款间距（那边也是 详情 + 危险色删除）
        lay.setSpacing(T.SPACE_SM)
        detail_btn = PushButton("详情")
        detail_btn.setFixedSize(52, 30)
        detail_btn.setToolTip("弹窗查看该子任务的详情（不离开本页）")
        detail_btn.clicked.connect(
            lambda: self.detail_requested.emit(self._members[row])
        )
        lay.addWidget(detail_btn)
        if self._inspect:
            # 查看模式只留「详情」：排序/删除会改成员集合（已汇集的输入随之失效）
            lay.addStretch()
            return wrap
        up = ToolButton(FIF.UP)
        up.setToolTip("上移（合并页序提前）")
        up.clicked.connect(lambda: self._on_move_from(row))
        down = ToolButton(FIF.DOWN)
        down.setToolTip("下移（合并页序靠后）")
        down.clicked.connect(lambda: self._on_move_from(row, delta=1))
        remove = PushButton("删除")
        remove.setFixedSize(52, 30)
        remove.setToolTip("从本次聚合里删掉这一行（不会删除该任务本身）")
        # ⚠️ 危险色走共享的一份（`theme.danger_button_qss`）：任务列表的行内
        #    「删除」就是这颗按钮，两处必须长得一样（用户 2026-11-17 要"删除
        #    按钮"，不是图标 ×）。
        remove.setStyleSheet(T.danger_button_qss())
        remove.clicked.connect(lambda: self._on_remove_from(row))
        for button in (up, down):
            button.setFixedSize(30, 30)
            lay.addWidget(button)
        lay.addWidget(remove)
        lay.addStretch()
        return wrap

    def _on_move_from(self, row: int, delta: int = -1) -> None:
        """上移/下移指定**成员下标**（行内按钮；顺序有意义）。"""
        target = row + delta
        if not (0 <= target < len(self._members)):
            return
        self._members[row], self._members[target] = (
            self._members[target],
            self._members[row],
        )
        self._fill_members()
        self.member_table.selectRow(self._member_local_row(target))

    def _on_remove_from(self, row: int) -> None:
        """删除指定**成员下标**（行内按钮）；成员变了候选也可能变。"""
        if not (0 <= row < len(self._members)):
            return
        del self._members[row]
        self._sync_candidates()
        self._fill_members()

    # 兼容旧调用（自测/外部的无参入口）：按当前选中行操作
    def _selected_member_row(self) -> int:
        """当前选中行 → **成员下标**（跨页也成立：表格只画当前页）。"""
        return self._member_index(self.member_table.currentRow())

    def _on_move(self, delta: int) -> None:
        """上移/下移**当前选中**的成员。"""
        row = self._selected_member_row()
        if row >= 0:
            self._on_move_from(row, delta)

    def _on_remove(self) -> None:
        """删除**当前选中**的成员。"""
        row = self._selected_member_row()
        if row >= 0:
            self._on_remove_from(row)

    def _open_picker(self) -> None:
        """弹「选择子任务」：勾掉的移除、新勾的按**列表顺序**追加在已排好的后面。

        ⚠️ 列表是任务号**倒序**（新的在前），所以新勾的追加顺序也是新的在前；
        用户手动排过的成员（上移/下移）位置不动——弹窗只影响"有没有选中"。
        """
        rows = self._load_task_rows()
        if rows is None:
            return
        picker = AggregateMemberPicker(rows, self._members, self)
        dialog = picker.build_dialog(self.window())
        if not dialog.exec():
            return
        self._apply_checked(picker.checked_ids())

    def _apply_checked(self, checked: list[str]) -> None:
        """把弹窗的勾选结果落回成员表（``_open_picker`` 拆出的落点，可测）。

        - 勾 **0 条**不算错误（用户 2026-11-18）：用户可能只是翻翻没挑，
          这里直接返回——成员保持原样，**不弹 toast、不清空已有成员**；
        - 勾了：已排好序的成员保序保留，新成员按弹窗列表顺序（任务号倒序）
          追加；成员变了候选节点可能变（共有节点少了一个），起始节点跟着收敛。
        """
        if not checked:
            return
        kept = [m for m in self._members if m in checked]
        known = set(kept)
        appended = [m for m in checked if m not in known]
        self._members = kept + appended
        # 新加的可能排得很后，回第一页更符合"刚选完"的预期
        self._page = 1
        self._sync_candidates()
        self._fill_members()

    def _load_task_rows(self) -> list[dict] | None:
        """读全量任务行（含节点状态胶囊），供「选择子任务」弹窗展示。

        数据与任务管理列表**同一来源**（``TaskRowsWorker``：逐任务读
        runs.json + 流程图，勾选弹窗里才能看到与列表一致的节点状态）。

        ⚠️ 这里**内联**跑 worker（不起后台线程）：行组装只是轻 IO，列表回程
        实测毫秒级；弹窗本来就是「点按钮等一下」的场景，不值得为它引入线程
        生命周期管理。列表页把同一个 worker 放后台，是为了「先画窗口再填
        数据」的**启动**体验，两个场景不矛盾。

        读失败返回 ``None``（弹 toast 让用户重试），不让弹窗开着空表。
        """
        from desktop.ui.toast import show_toast
        from desktop.workers import TaskRowsWorker

        worker = TaskRowsWorker(self._store)
        rows: list[dict] = []
        failures: list[str] = []
        worker.completed.connect(rows.extend)
        worker.failed.connect(failures.append)
        worker.run()
        if failures:
            show_toast(
                self.window(), "warning", "读取任务列表失败",
                f"{failures[0]}（请重试）",
            )
            return None
        return rows

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


__all__ = [
    "AggregateCreatePanel",
    "AggregateMemberPicker",
    "DEFAULT_START_STAGE",
    "MEMBER_HEADER_HEIGHT",
    "MEMBER_PAGE_SIZE",
]
