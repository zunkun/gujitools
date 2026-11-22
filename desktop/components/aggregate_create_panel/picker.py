# -*- coding: utf-8 -*-
"""「选择子任务」弹窗内容：搜索 + 分页的勾选表格（:class:`AggregateMemberPicker`）。"""

from __future__ import annotations

from datetime import datetime

from desktop.components.aggregate_create_panel._qt import (
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    Qt,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    CheckBox,
    SearchLineEdit,
    TableWidget,
)

from desktop import ui
from desktop.components.pagination import DEFAULT_PAGE_SIZE, Pager, Pagination
from desktop.components.task_table import StageChips, task_row_matches
from desktop.ui import theme as T


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


__all__ = ["AggregateMemberPicker"]
