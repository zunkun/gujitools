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
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
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


class NameLabel(QLabel):
    """任务名标签：按可用宽度自动省略中间部分。

    ``QTableWidgetItem`` 会自己省略，换成 QLabel 后得自己来——否则长名字
    把拉伸列越撑越宽、表格被挤出横向滚动条。
    ⚠️ 省略时机放在 ``resizeEvent`` 而不是建表时：那时表格还没布局、
    ``columnWidth()`` 只有几十像素，会把名字截成空串（已踩，表现为「名称列空白」）。
    宽度不足 ``_MIN_ELIDE_WIDTH`` 时一律显示全名，等真实宽度来了再收。

    下划线改为 ``paintEvent`` 自绘：字体原生下划线紧贴字形底部，间距不可调；
    自绘后用 ``_UNDERLINE_GAP`` 控制【基线】到下划线的留白，线宽 1px，颜色跟随
    ``linkColor``（hover 切换时同步更新）。
    """

    _MIN_ELIDE_WIDTH = 96
    # 【基线到下划线的距离px】，直接调这个，越大间距越远，推荐 4~8
    _UNDERLINE_GAP = 4

    def __init__(self, text: str, parent=None):
        """记下完整名字，先按全名显示，等布局给出真实宽度再省略。"""
        super().__init__(text, parent)
        self._full = text
        # 当前链接色：paintEvent 画下划线时取这个值，与文字颜色保持一致。
        self._link_color = QColor(T.ACCENT)
        # 开启文字垂直居中
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    def setLinkColor(self, color: QColor) -> None:
        """同步文字颜色与下划线颜色。

        不再依赖 stylesheet 里的 ``color:``（paintEvent 解析不了），
        统一走这个方法——hover 进入/离开都调它。
        """
        self._link_color = QColor(color)
        super().setStyleSheet(
            f"QLabel {{ color: {self._link_color.name()}; background:transparent; }}"
        )
        self.update()  # 触发重绘，下划线颜色跟着变

    def linkColor(self) -> QColor:
        return self._link_color

    def full_text(self) -> str:
        """完整任务名（省略后的 ``text()`` 可能带 …）。"""
        return self._full

    def resizeEvent(self, event):
        """宽度变化时重算省略；宽度还没定（未布局）就保持全名。"""
        super().resizeEvent(event)
        if self.width() < self._MIN_ELIDE_WIDTH:
            self.setText(self._full)
            return
        fm = QFontMetrics(self.font())
        self.setText(
            fm.elidedText(self._full, Qt.TextElideMode.ElideMiddle, self.width())
            or self._full
        )

    def paintEvent(self, event):
        """先让父类画文字，再在文字下方自绘一条同色下划线。
        ✅ 使用字体基线计算位置，不再依赖boundingRect，gap修改生效。
        下划线只覆盖**实际文字宽度**（不铺满整个 label），和网页 <a> 行为一致；
        """
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(self._link_color)
        pen.setWidth(1)
        painter.setPen(pen)

        fm = QFontMetrics(self.font())
        text = self.text()
        if not text:
            return

        # 文字水平起始位置
        cr = self.contentsRect()
        text_w = fm.horizontalAdvance(text)
        x1 = cr.left()
        x2 = cr.left() + text_w

        # 🔑 核心修复：计算【基线】
        # label垂直居中，文本块总高度 = ascent + descent
        text_block_h = fm.ascent() + fm.descent()
        # 文本块垂直起点
        text_top = cr.top() + (cr.height() - text_block_h) / 2
        # 基线Y坐标 = 文本块顶部 + ascent
        baseline_y = text_top + fm.ascent()

        # 基线向下偏移，就是下划线位置，_UNDERLINE_GAP 可以随便改 0~15 都生效
        line_y = baseline_y + self._UNDERLINE_GAP

        painter.drawLine(x1, line_y, x2, line_y)
        painter.end()


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
        self.table.cellClicked.connect(self._on_cell_clicked)

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

    def _on_cell_clicked(self, row: int, column: int) -> None:
        """点击「任务名称」单元格跳详情。

        标签自己覆盖了链接文字那一块，这里补的是**同一格里的空白区域**
        （标签右侧的留白）——点哪儿都该有反应，否则「明明点在名字上却没跳」。
        ⚠️ 别担心重复触发：标签在 ``mousePressEvent`` 里 ``accept()`` 了事件，
        事件不会再冒泡到视口，一次点击只会走一条路径。
        """
        if column != 1:
            return
        item = self.table.item(row, column)
        if not item:
            return
        task_id = item.data(Qt.UserRole)
        if task_id:
            self.open_detail.emit(task_id)

    # ------------------------------------------------------------------ 任务名
    def _name_widget(self, task: dict) -> QWidget:
        """任务名单元格：链接样式标签（自绘下划线 + 主色 + hover 变深 + 手型光标）。

        ⚠️ 容器必须与 StageChips 一样锁成整行高：qfluent 的
        ``TableItemDelegate.updateEditorGeometry`` 用「改高度前」的容器高算居中
        偏移、随后又把高度改成整格高，容器高 ≠ 行高时标签在真实运行中会偏到行底。
        ⚠️ 颜色取 ``theme.ACCENT/ACCENT_HOVER``——主题里**没有** ``PRIMARY``，
        写错名字是 AttributeError，一进列表页就崩（已踩）。
        """
        w = QWidget()
        w.setFixedHeight(ROW_HEIGHT)
        layout = QHBoxLayout(w)
        layout.setContentsMargins(T.SPACE_SM, 0, T.SPACE_SM, 0)
        layout.setSpacing(0)

        label = NameLabel(str(task["name"]))
        # 不再用 font.setUnderline(True)：字体下划线紧贴字形、间距不可调；
        # 改为 paintEvent 自绘下划线，间距由 _UNDERLINE_GAP 控制。
        label.setCursor(Qt.CursorShape.PointingHandCursor)
        label.setToolTip(str(task.get("source_path") or task["name"]))
        label.setLinkColor(QColor(T.ACCENT))
        # 外部设置字号
        # font = label.font()
        # font.setPointSize(11)
        # label.setFont(font)

        def _enter(event):
            label.setLinkColor(QColor(T.ACCENT_HOVER))
            return QLabel.enterEvent(label, event)

        def _leave(event):
            label.setLinkColor(QColor(T.ACCENT))
            return QLabel.leaveEvent(label, event)

        def _press(event, tid=str(task["id"])):
            if event.button() == Qt.MouseButton.LeftButton:
                # 必须 accept：否则事件冒泡到视口，cellClicked 会再跳一次详情。
                event.accept()
                self.open_detail.emit(tid)

        label.enterEvent = _enter
        label.leaveEvent = _leave
        label.mousePressEvent = _press

        layout.addWidget(label)
        layout.addStretch()
        return w

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
                # ⚠️ 名称列 item **必须留空文本**：文字交给 _name_widget 的 QLabel，
                # 单元格控件是透明的，item 再画一遍就是「同一条名字显示两次」的重影。
                # item 只保留一件事：UserRole 存任务 id。Tooltip交给NameLabel。
                "",
                datetime.fromtimestamp(task["created_at"]).strftime("%Y-%m-%d %H:%M"),
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col in (0, 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)

            # ⚠️ 名称格的 item **不能省**：select_task() 靠它取 UserRole 定位行。
            # 不要 setForeground——item 透明绘制，否则会和 NameLabel 文字重影。
            name_item = self.table.item(row, 1)
            name_item.setData(Qt.UserRole, task["id"])

            self.table.setCellWidget(row, 1, self._name_widget(task))
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
