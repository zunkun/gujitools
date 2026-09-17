# -*- coding: utf-8 -*-
"""任务列表表格组件：每行带阶段状态胶囊与 详情/删除 操作按钮。

「子任务状态」原来是一整串 ``提取图片:成功  检测文本框:成功 …`` 纯文本，
列宽一紧就被截断、颜色上也没法区分成败。现在改为 4 个状态胶囊
（提取 / 检测 / 去底 / PDF），颜色来自统一的语义色，鼠标悬停能看到
完整阶段名与进度。
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QTableWidgetItem, QVBoxLayout, QWidget,
)
from qfluentwidgets import PushButton, TableWidget

from desktop import ui
from desktop.ui import theme as T

ROW_HEIGHT = 56

# 危险操作按钮（删除）：实例级样式表顶掉 qfluent 默认按钮外观，让删除
# 在一排灰白按钮里一眼可辨。四个状态必须写全——实例样式表会把库自带的
# 按钮样式整体顶掉，缺哪态哪态就退回默认渲染、没有视觉反馈。
_DANGER_BUTTON_QSS = f"""
QPushButton {{
    background-color: {T.DANGER};
    color: {T.SURFACE};
    border: none;
    border-radius: {T.RADIUS_SM}px;
}}
QPushButton:hover {{
    background-color: {T.DANGER_HOVER};
}}
QPushButton:pressed {{
    background-color: {T.DANGER_PRESSED};
}}
QPushButton:disabled {{
    background-color: {T.DANGER_SOFT};
    color: {T.INK_DISABLED};
}}
"""


class StageChips(QWidget):
    """一行 4 个阶段状态胶囊。"""

    def __init__(self, stages: list[dict], parent=None):
        """按 stages 逐项生成状态胶囊；每项需含 short/status/tip。"""
        super().__init__(parent)
        # 锁定为整行高：qfluent 的 TableItemDelegate.updateEditorGeometry 用
        # 「设geometry前」的控件高度算垂直居中偏移、随后又把高度改成整格高，
        # 容器高度不等于行高时位置随时序漂移（胶囊/按钮偏到行底）。
        # 高度恒等于 ROW_HEIGHT 后 y = rect.y 恒成立，任何时序都收敛为填满单元格。
        self.setFixedHeight(ROW_HEIGHT)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(T.SPACE_SM, 0, T.SPACE_SM, 0)
        layout.setSpacing(T.SPACE_XS)
        for stage in stages:
            chip = ui.StatusChip(stage["short"], stage["status"])
            chip.setToolTip(stage["tip"])
            layout.addWidget(chip)
        layout.addStretch()


class TaskTable(QWidget):
    """任务列表表格：每行带阶段状态胶囊与 详情/删除 操作。

    列固定为 序号 / 任务名 / 创建时间 / 子任务状态 / 操作；源文件路径
    不成列，仅作为任务名 tooltip。open_detail / delete_request 信号
    分别携带任务 id。
    """

    open_detail = Signal(str)
    delete_request = Signal(str)

    COLUMNS = ["序号", "任务名称", "创建时间", "子任务状态", "操作"]

    # 各列宽度；None 表示该列自适应拉伸。
    # 「任务名称」是主体信息，拉伸列给它；「子任务状态」4 个胶囊的
    # 实际宽度约 244px（4×54 + 间隙/边距），固定 256 留少量余量。
    _COLUMN_WIDTHS = [56, None, 168, 256, 132]
    # 各列对齐：与内容保持一致，否则表头和数据看着"错位"。
    # 水平对齐必须再或上 AlignVCenter——只给水平分量时垂直分量为 0，
    # 表头文字会顶到上沿（qfluent 的 section 样式只有左右 padding）。
    _HEADER_ALIGN = {
        0: Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
        1: Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        2: Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
        3: Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        4: Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
    }

    def __init__(self, parent=None):
        """初始化表格：5 列布局、行高与表头对齐。

        表头对齐跟随各列内容（序号/时间居中、名称/状态左对齐，均垂直居中）；
        任务名称列自适应拉伸（占主要宽度），其余列按 _COLUMN_WIDTHS 固定宽度。
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table = TableWidget()
        self.table.setObjectName("taskTable")
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
        # 表头对齐跟随列内容
        for col, align in self._HEADER_ALIGN.items():
            header_item = self.table.horizontalHeaderItem(col)
            if header_item is not None:
                header_item.setTextAlignment(align)

        header = self.table.horizontalHeader()
        header.setFixedHeight(38)
        header.setHighlightSections(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate(self._COLUMN_WIDTHS):
            if width is None:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
            else:
                header.resizeSection(col, width)
        self.table.setMinimumHeight(360)
        layout.addWidget(self.table)

    # ------------------------------------------------------------------ 数据
    def set_data(self, rows: list[dict], start_index: int = 1) -> None:
        """rows: [{id, name, source_path, created_at, stages}]

        stages 为 ``[{"short": "提取", "status": "success", "tip": "..."}]``；
        source_path 不单独成列，仅作任务名的悬浮提示。

        ⚠️ ``start_index`` 是本页第一条在**整表**里的序号（1-based）。
        分页后「序号」列要显示全局序号，不能是页内行号——否则第二页又是
        从 1 开始，看着像数据重复。默认 1 保持不分页时的行为。
        """
        self.table.setRowCount(len(rows))
        for row, task in enumerate(rows):
            values = [
                str(start_index + row),
                task["name"],
                datetime.fromtimestamp(task["created_at"]).strftime("%Y-%m-%d %H:%M"),
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col in (0, 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)
            name_item = self.table.item(row, 1)
            name_item.setData(Qt.UserRole, task["id"])
            name_item.setToolTip(str(task.get("source_path") or ""))
            name_item.setForeground(QColor(T.INK))
            self.table.setCellWidget(row, 3, StageChips(task.get("stages", [])))
            self.table.setCellWidget(row, 4, self._action_widget(task["id"]))
        for row in range(len(rows)):
            self.table.setRowHeight(row, ROW_HEIGHT)

    def select_task(self, task_id: str) -> bool:
        """选中并滚动到指定任务所在行，返回是否找到。"""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item and item.data(Qt.UserRole) == task_id:
                self.table.selectRow(row)
                self.table.scrollToItem(item)
                return True
        return False

    # ------------------------------------------------------------------ 操作列
    def _action_widget(self, task_id: str) -> QWidget:
        w = QWidget()
        # 锁定为整行高，原理见 StageChips：否则容器高度随布局时序漂移，
        # 详情/删除按钮在真实运行中会偏到行底（离屏探针因时序不同无法复现）。
        w.setFixedHeight(ROW_HEIGHT)
        layout = QHBoxLayout(w)
        layout.setContentsMargins(T.SPACE_SM, 0, T.SPACE_SM, 0)
        layout.setSpacing(T.SPACE_SM)
        detail_btn = PushButton("详情")
        detail_btn.setFixedSize(QSize(52, 30))
        detail_btn.setToolTip("打开任务详情")
        detail_btn.clicked.connect(lambda: self.open_detail.emit(task_id))
        layout.addWidget(detail_btn)
        delete_btn = PushButton("删除")
        delete_btn.setFixedSize(QSize(52, 30))
        delete_btn.setToolTip("删除任务及其全部中间产物")
        delete_btn.setStyleSheet(_DANGER_BUTTON_QSS)
        delete_btn.clicked.connect(lambda: self.delete_request.emit(task_id))
        layout.addWidget(delete_btn)
        return w
