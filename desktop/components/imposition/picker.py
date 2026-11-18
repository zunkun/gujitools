# -*- coding: utf-8 -*-
"""「选择拼版」/「插入拼版」弹窗（**模块一：选择拼版** 的 UI）。

**一个列表，没有页签**（用户 2026-11-16 定的 UI）：

- 列表里是**所有还能用的图**——上一节点传过来、还没被任何拼版页用掉的成品图，
  加上**用户自己上传过的图**（上传即复制进任务目录，之后一直是候选，删掉拼版页
  也会回到这里）。自由多选：1 张单独成一页、2 张拼成一页；点确认才把勾选的图
  按**列表顺序**成页（序号在前的进右槽，落单的单独一页）；
- 没有想要的图时点「上传图片…」或直接把图拖进窗口：上传的图排在列表末尾、
  默认勾上、**带缩略图**；同一张图可以上传多次（每次都是独立的一条候选）。

三种用法（``mode``）：

- ``"pick"``（默认）：左列「＋ 选择拼版」——确认后追加到清单末尾；
- ``"insert"``：左列右键「向前 / 向后插入拼版」——``position`` 给出默认落点
  （当前页之前/之后，弹窗里可改），确认后插到那个位置；
- ``"append"``：单图页「新增图片」——只能勾 1 张，确认按钮叫「添加」。

⚠️ **上传的图本弹窗不落盘**：它只把本地路径交回去（:meth:`chosen_items` 里
``uploaded=True``），复制进任务目录由宿主调
``services.imposition_insert.resolve_chosen`` 统一做。弹窗写任务目录会让
"取消"也留下垃圾文件，而且自测还得准备目录。

⚠️ **上传的图与缩略图都不许写进上一步的目录/清单**（用户 2026-11-16）：
复制落点是 ``<任务目录>/inserted/imposition/``（见
``services.imposition_insert.upload_dir``），那既不是 ``stages/`` 下的阶段产物，
也不与打印侧的 ``inserted/`` 混放——上一步的页面清单不会因此多出一条，
打印侧插入的图也不会混进拼版候选。

这里只做控件与信号；弹窗怎么被唤起、选完之后怎么建页落盘，见
``desktop/pages/taskdetail/imposition_pages.py``（任务流程控制器）与
``desktop/modules/imposition/page.py``（独立拼图页）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from qframelesswindow import FramelessDialog
from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImageReader, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea,
    QVBoxLayout, QWidget,
)
from qfluentwidgets import CheckBox, FluentIcon as FIF, PrimaryPushButton, PushButton
from qfluentwidgets import RadioButton

from desktop.components.print_insert_dialog import IMAGE_FILTER, image_paths
from desktop.services.imposition import SOURCE_FULL, classify_source
from desktop.ui import theme as T
from desktop.ui.widgets import apply_to
from desktop.ui.window_size import apply_window_size
from desktop.utils.files import default_open_dir
from desktop.utils.image_scaling import smooth_downscale

#: 弹窗缩略图的**固定框**（源图按比例缩进这个框，白底居中）
THUMB_W, THUMB_H = 156, 196
#: 卡片尺寸（比缩略图宽一圈；用户要求「选框宽一些」）。
#: 高度 = 上留白(30) + 缩略图(196) + 间距(6) + 名字(~16) + 下留白(8) ≈ 264。
CARD_W, CARD_H = 188, 264
#: 卡片顶部留给勾选框的「页眉」高度
CARD_HEAD = 30
#: 卡片之间的间距
CARD_GAP = 12
#: 弹窗默认尺寸（够宽才能一行摆下好几张；用户要求「宽度大一些」）
DIALOG_W, DIALOG_H = 1000, 680
#: 每轮事件循环补几张缩略图（避免一次性解码上百张大图把弹窗卡住）
THUMB_BATCH = 6
#: 批与批之间的间隔（ms）——**必须有间隔**（用户 2026-10-03 报「程序容易跑
#: 崩溃，cpu 跑满」）。
#:
#: ⚠️ 这里原先是 ``QTimer.singleShot(0, self._fill_thumbs)``，即"下一轮事件
#: 循环空闲就立刻再解一批"，批与批之间**零间隔**。配上 :func:`_source_thumb_pixmap`
#: 的**整幅解码 + 平滑缩放**（每张源图都是几千像素见方），N 张候选图就是
#: ``ceil(N/6)`` 轮零间隔的连续重解码，全程占着 GUI 主线程 —— 用户看到的就是
#: "CPU 跑满、界面像崩溃了"。同项目别处的分批装载都留了间隔（见
#: ``ThumbsMixin.BATCH_GAP_MS = 150``），这里属于疏漏。
THUMB_GAP_MS = 150


def _source_thumb_pixmap(path) -> QPixmap:
    """源图 → **固定尺寸**的缩略图（白底居中、按比例缩进 ``THUMB_W×THUMB_H``）。

    ⚠️ 必须**整幅解码再自己缩**，不要走 ``QImageReader.setScaledSize``：
    去底成品是「1bit 调色板 + tRNS」的透明 PNG，解码器的缩放读取在这种图上
    会给出尺寸异常的图，缩略图就变成一小条（用户实测：卡片里只有一段残图）。
    固定尺寸还有一个好处：不管源图多大，卡片格子永远一样大、图不会被拉变形。
    """
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        return QPixmap()
    canvas = QPixmap(THUMB_W, THUMB_H)
    canvas.fill(QColor(T.SURFACE))
    # 分档折半 + 平滑收尾：源图动辄几千像素，一次缩到 96px 会跳采样。
    scaled = smooth_downscale(image, max(THUMB_W, THUMB_H)).scaled(
        THUMB_W, THUMB_H, Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter = QPainter(canvas)
    painter.drawImage(
        QPoint((THUMB_W - scaled.width()) // 2, (THUMB_H - scaled.height()) // 2),
        scaled,
    )
    painter.end()
    return canvas


class _SourceCard(QFrame):
    """一张可勾选的源图卡片：缩略图 + 名字 + 勾选标记，整张可点。

    ⚠️ 用**真控件**而不是 QListWidget 的图标模式：图标模式的缩略图尺寸/文字
    由委托按 sizeHint 自己算，在真机（高分屏 + 真实透明 PNG）上会把卡片内容
    画成一小条、文字也看不见（用户 2026-09-30 截图报过）。这里缩略图是固定
    ``THUMB_W×THUMB_H`` 的 QLabel、名字是独立 QLabel，尺寸完全由我们说了算。
    """

    clicked = Signal(object)  # 传出自己，宿主负责切换勾选

    def __init__(self, path: Path, parent=None, key: str = "", uploaded=False):
        super().__init__(parent)
        self.path = Path(path)
        #: 这条候选的**身份键**（宿主用：列表里的图 = 路径串；本次上传的图 =
        #: 每次上传一个唯一键）。同一张图上传两次会是两条不同键的候选。
        self.cand_key = key or str(self.path)
        #: 是否本次上传的图（`True` ⇒ 确认后宿主先把文件复制进任务目录）
        self.uploaded = bool(uploaded)
        self._checked = False
        self._pixmap = QPixmap()
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(
            f"{self.path}\n勾选后：序号在前的排到拼版页右侧"
            + ("\n（本次上传的图片，确认后复制进任务目录）" if self.uploaded else "")
        )

        column = QVBoxLayout(self)
        # ⚠️ 上留白必须够放下勾选框：勾选框画在卡片的 paintEvent 里，而缩略图是
        # **子控件**、会盖在卡片之上——不给它留位置，勾选标记就被缩略图压住，
        # 只剩一角露出来（实测像个残缺的弧线）。
        column.setContentsMargins(10, CARD_HEAD, 10, 8)
        column.setSpacing(6)
        self.thumb = QLabel(self)
        self.thumb.setFixedSize(THUMB_W, THUMB_H)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignHCenter)
        self.name = QLabel(self.path.stem, self)
        self.name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_to(self.name, T.SIZE_CAPTION, color=T.INK)
        column.addWidget(self.name, 0)
        column.addStretch(1)

    # ------------------------------------------------------------------ 状态
    def set_pixmap(self, pixmap: QPixmap) -> None:
        """回填缩略图（分批解码，见 ImpositionPickerDialog._fill_thumbs）。"""
        if pixmap.isNull():
            return
        self._pixmap = pixmap
        self.thumb.setPixmap(pixmap)
        self.update()

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool) -> None:
        if checked == self._checked:
            return
        self._checked = bool(checked)
        self.update()

    def toggle(self) -> None:
        self.clicked.emit(self)

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, _event) -> None:  # noqa: N802
        """卡片底 + 描边 + 左上角勾选框（勾中给主色浅底与对勾）。

        自绘而不是样式表：样式表一旦进子树，Qt 会把 QFrame 底色填白，还会连带
        改子 QLabel 的取色路径（见 step_bar 的教训）。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        if self._checked:
            painter.setPen(QPen(QColor(T.ACCENT), 1.6))
            painter.setBrush(QColor(T.ACCENT_SOFT))
        else:
            painter.setPen(QPen(QColor(T.BORDER), 1.0))
            painter.setBrush(QColor(T.SURFACE))
        painter.drawRoundedRect(rect, T.RADIUS_MD, T.RADIUS_MD)

        # 缩略图框：浅底 + 细边，让留白页也有边界感
        painter.setPen(QPen(QColor(T.BORDER_SOFT), 1.0))
        painter.setBrush(QColor(T.SURFACE_SOFT))
        painter.drawRoundedRect(QRectF(self.thumb.geometry()), T.RADIUS_SM,
                                T.RADIUS_SM)

        # 勾选框（画在卡片顶部的"页眉"里，不会被缩略图压住）
        box = QRectF(10.0, 8.0, 16.0, 16.0)
        painter.setPen(QPen(QColor(T.ACCENT if self._checked else T.BORDER_STRONG),
                            1.4))
        painter.setBrush(QColor(T.SURFACE))
        painter.drawRoundedRect(box, 4, 4)
        if self._checked:
            path = QPainterPath()
            path.moveTo(box.x() + 4.0, box.y() + 8.4)
            path.lineTo(box.x() + 6.8, box.y() + 11.2)
            path.lineTo(box.x() + 12.2, box.y() + 4.8)
            painter.setPen(QPen(QColor(T.ACCENT), 2.0, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        painter.end()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit(self)
        super().mouseReleaseEvent(event)


class _CardGrid(QWidget):
    """卡片容器：按可用宽度**自动算列数**（flex 换行），一行摆好几个。

    Qt 没有内置流式布局，用 ``QGridLayout`` + ``resizeEvent`` 重排即可：
    窗口变宽一行放更多、变窄自动折行，并保持卡片自身尺寸不变（不拉伸变形）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[_SourceCard] = []
        self._cols = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(CARD_GAP)
        self.grid.setVerticalSpacing(CARD_GAP)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

    def add_card(self, card: _SourceCard) -> None:
        self._cards.append(card)
        self._relayout(force=True)

    def detach_cards(self) -> None:
        """把当前卡片全部摘出布局（不销毁；实例还在宿主的字典里复用）。"""
        for old in self._cards:
            self.grid.removeWidget(old)
        self._cards = []

    def adopt_cards(self, cards: list) -> None:
        """装入一批卡片并重排（调用前必须先 ``detach_cards``）。"""
        self._cards = list(cards)
        self._cols = 0
        self._relayout(force=True)

    def columns(self) -> int:
        """当前一行摆了几张（护栏用；0 = 还没排过）。"""
        return self._cols

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self, force: bool = False) -> None:
        width = self.width() or self.sizeHint().width()
        cols = max(1, (width + CARD_GAP) // (CARD_W + CARD_GAP))
        if cols == self._cols and not force:
            return
        self._cols = cols
        for index, card in enumerate(self._cards):
            self.grid.addWidget(card, index // cols, index % cols)
        # 右侧/底部留一个可伸缩的空格：卡片靠左靠上排，不被摊开
        for column in range(cols):
            self.grid.setColumnStretch(column, 0)
        self.grid.setColumnStretch(cols, 1)


class ImpositionPickerDialog(FramelessDialog):
    """拼版选图弹窗：**一个候选列表**（上游剩余图 + 自己上传的图）。

    三种 ``mode`` 见模块 docstring。``files`` 是**候选池**（宿主按源清单顺序给：
    上游还没用过的图 + 这个任务上传过、现在又没被页引用的图）。
    本次新上传的图追加在后面（``uploaded=True``，确认后才由宿主复制落盘）。

    **卡片网格**：一行摆好几张（列数随窗口宽度自动变），卡片 ``CARD_W×CARD_H``、
    缩略图固定 ``THUMB_W×THUMB_H``（用户要求「一行好几个、选框宽一些」且
    「图片要正常显示、要有文字」）。

    **可缩放**（用户 2026-09-30 要求）：底座是 ``qframelesswindow.FramelessDialog``，
    恢复它的最小化/最大化按钮与「双击标题栏放大/还原」；边缘还能拖拽调整大小，
    网格列数跟着窗口宽度自动变。

    列表顺序在前的图会被放到拼版页**右侧**（用户口径），这里按同一顺序展示，
    勾选结果也按**列表顺序**返回（不是点选先后）。
    """

    if TYPE_CHECKING:
        # ⚠️ ``scroll`` 遮住了基类 FramelessDialog.scroll() 方法，类型检查器
        # 会按基类方法解析、判成「不是 QScrollArea」。类型侧声明钉回真实类型，
        # 只影响类型检查、运行时零副作用。
        scroll: QScrollArea

    def __init__(self, files: list, parent=None, mode: str = "pick",
                 thumb_provider=None, position: str = "after",
                 current_row: int = -1, total: int = 0):
        super().__init__(parent)
        self._mode = mode if mode in ("insert", "append") else "pick"
        #: 候选图的**预生成缩略图**来源：``(path_text) -> Path | None``。
        #: 由宿主给出（任务流程里是「上一节点的成品小图 / 入口图片小图」）；
        #: 拿不到就回落整幅解码原图（见 :meth:`_thumb_pixmap_for`）。
        self._thumb_provider = thumb_provider
        #: 候选池（列表口径：宿主的"上游剩余 + 本任务上传过的"）
        self._files = [Path(f) for f in files]
        #: 本次**上传**的图：``[(候选键, 本地路径)]``。键每次上传唯一（同一张图
        #: 上传两次是两条候选，符合「图片可以多次上传」的规范）。
        self._uploads: list[tuple[str, Path]] = []
        self._upload_seq = 0
        self._pixmaps: dict[str, QPixmap] = {}  # 解码好的缩略图（候选键 → 图）
        self._cand_cards: dict[str, _SourceCard] = {}
        self.cards: list[_SourceCard] = []  # 当前卡片（列表顺序）
        #: 插入模式的页数/当前页（底部「插入第 x 页之前/之后」用它算页号）
        self._total = max(0, int(total))
        self._current_row = int(current_row)
        self.setWindowTitle(
            {"append": "新增图片", "insert": "插入拼版"}.get(self._mode, "选择拼版")
        )
        self.setModal(True)
        # 拖进来的图片直接进候选（用户 2026-11-16：没有想要的图片可以自己上传）
        self.setAcceptDrops(True)
        # 默认 1000×680 是**期望值**：1366×768 @125%（逻辑可用约 1093×574）
        # 之类的机器上 680 高会顶出屏幕，统一按可用区域夹一次。
        apply_window_size(self, QSize(DIALOG_W, DIALOG_H))
        self._setup_title_bar()

        column = QVBoxLayout(self)
        # ⚠️ 顶部要给标题栏让位：标题栏是**盖在窗口上沿**的 32px 浮层，
        # 不让位的话第一行内容会被它压住。
        column.setContentsMargins(
            T.SPACE_LG, T.SPACE_LG + self.titleBar.height(), T.SPACE_LG,
            T.SPACE_LG,
        )
        column.setSpacing(T.SPACE_SM)

        self.note = QLabel("", self)
        self.note.setWordWrap(True)
        apply_to(self.note, T.SIZE_CAPTION, color=T.INK_FAINT)
        column.addWidget(self.note)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.body = _CardGrid()
        self.scroll.setWidget(self.body)
        column.addWidget(self.scroll, 1)

        self.status = QLabel("", self)
        self.status.setWordWrap(True)
        apply_to(self.status, T.SIZE_CAPTION, color=T.INK_SOFT)
        column.addWidget(self.status)

        # ---- 自己上传图片（用户 2026-11-16）----
        self.upload_row = QWidget(self)
        upload_row = QHBoxLayout(self.upload_row)
        upload_row.setContentsMargins(0, 0, 0, 0)
        upload_row.setSpacing(T.SPACE_MD)
        self.upload_button = PushButton(FIF.ADD, "上传图片…", self.upload_row)
        self.upload_button.setToolTip(
            "从本机选图片加入候选（也可以直接把图片拖进这个窗口）。\n"
            "同一张图片可以上传多次，每次都是独立的一条候选；"
            "上传的图会复制进任务目录，删掉拼版页后仍会回到这个列表。"
        )
        self.upload_button.clicked.connect(self._choose_uploads)
        upload_row.addWidget(self.upload_button)
        self.upload_hint = QLabel("", self.upload_row)
        apply_to(self.upload_hint, T.SIZE_CAPTION, color=T.INK_FAINT)
        upload_row.addWidget(self.upload_hint)
        upload_row.addStretch(1)
        column.addWidget(self.upload_row)

        # ---- 插入落点（仅 insert 模式）：第 x 页之前 / 之后 ----
        self.position_row = self._build_position_row(position)
        column.addWidget(self.position_row)

        # 「从这张图片开始自动拼版」：**恰好勾 1 张**时出现在下方（不限
        # 整幅/半幅，用户 2026-10-01 定）——勾上后点确认，宿主从这张图起把
        # 剩余候选按自动拼版规则（整幅单独一页、左半幅+右半幅配对）全部拼完。
        # ⚠️ 只在 pick 模式出现：插入是"插到某个位置的 1~2 页"，从某张起把
        # 后面全部拼完与"插入"的语义冲突。
        self.auto_checkbox = CheckBox("从这张图片开始自动拼版", self)
        self.auto_checkbox.setToolTip(
            "只勾选 1 张图片时可用：从这张图起，把剩余未拼版的图片按顺序"
            "自动拼完——整幅图单独一页，左半幅与紧随其后的右半幅拼成一页"
            "（序号在前的排在右侧），落单的图单独一页。"
        )
        self.auto_checkbox.toggled.connect(self._update_status)
        self.auto_checkbox.hide()
        column.addWidget(self.auto_checkbox)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = PushButton("取消", self)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.ok_button = PrimaryPushButton(
            {"append": "添加", "insert": "插入"}.get(self._mode, "开始拼版"), self
        )
        self.ok_button.setEnabled(False)
        self.ok_button.clicked.connect(self.accept)
        buttons.addWidget(self.ok_button)
        column.addLayout(buttons)

        self._populate()

    # -------------------------------------------------------------- 标题栏
    def _setup_title_bar(self) -> None:
        """恢复最小化/最大化/双击缩放，并把标题文字摆进标题栏。

        ⚠️ ``qframelesswindow`` 的 ``FramelessDialog`` 默认按"对话框不可缩放"
        处理：藏掉最小化/最大化按钮、禁掉双击、还把窗口样式的 ``WS_MAXIMIZEBOX``
        位清了。用户要的是普通可缩放窗口，这里三样都恢复。
        """
        self.titleBar.minBtn.show()
        self.titleBar.maxBtn.show()
        self.titleBar.setDoubleClickEnabled(True)
        self._restore_maximize_style()
        # 选图窗是主窗口的"子窗口"（owned）：默认没有任务栏按钮（用户
        # 2026-11-18：要在任务栏看到多个窗口）。补 WS_EX_APPWINDOW（失败
        # 不致命——按钮、缩放都不依赖这个位，与 _restore_maximize_style 同口径）。
        from desktop.ui.native_minimize import enable_taskbar_button

        enable_taskbar_button(self)
        title = QLabel(self.windowTitle(), self.titleBar)
        apply_to(title, T.SIZE_BODY, bold=True, color=T.INK)
        self.titleBar.hBoxLayout.insertSpacing(0, 12)
        self.titleBar.hBoxLayout.insertWidget(1, title, 0, Qt.AlignmentFlag.AlignLeft)

    def _restore_maximize_style(self) -> None:
        """把被基类清掉的 ``WS_MAXIMIZEBOX`` 加回去（win32 样式位）。

        只在 Windows 上有效（本项目只发 Windows 包）；失败不致命——按钮还在，
        双击与拖边缘缩放也不依赖这个位。
        """
        if sys.platform != "win32":
            return
        try:
            import win32con
            import win32gui

            hwnd = int(self.winId())
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            win32gui.SetWindowLong(
                hwnd, win32con.GWL_STYLE, style | win32con.WS_MAXIMIZEBOX
            )
        except Exception:  # noqa: BLE001 - 样式位丢了只影响原生最大化动画
            pass

    # ------------------------------------------------------------------ 接口
    def count(self) -> int:
        """列表里的卡片数（含本次上传的图）。"""
        return len(self.cards)

    def checked_files(self) -> list[Path]:
        """用户勾选的图（**按列表顺序**，不是勾选先后）。

        张数不限——配对（每两张一页）由宿主做。⚠️ 同一个本地文件被上传两次时
        这里会出现**两条相同路径**（那正是"同一张图多次使用"的口径），宿主
        复制时会各自落成不同的文件名（见 ``services.imposition_insert``）。
        """
        return [card.path for card in self.cards if card.is_checked()]

    def chosen_items(self) -> list[dict]:
        """勾选的候选（带"是不是本次上传"的标记），宿主据此决定要不要复制。

        形状：``[{"path": Path, "uploaded": bool}, ...]``，顺序同 :meth:`checked_files`。
        """
        return [
            {"path": card.path, "uploaded": card.uploaded}
            for card in self.cards if card.is_checked()
        ]

    def uploaded_files(self) -> list[Path]:
        """本次上传过的图（不管勾没勾；复制落盘只看勾选的那些）。"""
        return [path for _key, path in self._uploads]

    #: 兼容旧名（宿主与护栏历史上叫 picked_files）
    def picked_files(self) -> list[Path]:
        return self.checked_files()

    def auto_mode_file(self) -> Path | None:
        """「从这张图片开始自动拼版」生效的那张图（不生效返回 None）。

        生效条件：勾选框被勾上、且**恰好勾了 1 张**——选项只在恰好
        勾 1 张时出现（不限整幅/半幅，用户 2026-10-01 定），多选不走自动。
        本次上传的图**不参与自动拼版**（它没有页号/半幅标记可依）。
        """
        if not self.auto_checkbox.isChecked() or self._mode != "pick":
            return None
        picked = [card for card in self.cards if card.is_checked()]
        if len(picked) != 1 or picked[0].uploaded:
            return None
        return picked[0].path

    def auto_sequence(self) -> list[Path]:
        """自动拼版的图片序列：从勾选那张起到**列表末尾**（列表顺序）。

        「自此之后」= 含勾选的那张本身；它之前的图片不参与（留在候选里，
        之后仍可手动拼）。本次上传的图不在序列里（见 :meth:`auto_mode_file`）。
        """
        file = self.auto_mode_file()
        if file is None:
            return []
        candidates = self._source_candidate_paths()
        keys = [str(p) for p in candidates]
        if str(file) not in keys:
            return []
        return candidates[keys.index(str(file)):]

    def position(self) -> str:
        """插入落点（只 insert 模式有单选；其余模式恒 ``"after"``）。"""
        if self.before_radio is not None and self.before_radio.isChecked():
            return "before"
        return "after"

    def toggle_card(self, card: _SourceCard) -> None:
        """切换一张卡片的勾选（自由多选，不设上限）。"""
        card.set_checked(not card.is_checked())
        self._update_status()

    def _on_card_clicked(self, card: _SourceCard) -> None:
        """卡片点击：切换勾选（勾选数不设上限，确认按钮按 1/2 张判可用）。"""
        card.set_checked(not card.is_checked())
        self._update_status()

    # ------------------------------------------------------------------ 上传
    def _choose_uploads(self) -> None:
        """「上传图片…」：本机选图加进列表（可多选，同一张也能选两次）。"""
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", str(default_open_dir()), IMAGE_FILTER
        )
        if filenames:
            self.add_uploads(filenames)

    def add_uploads(self, paths) -> None:
        """把本地图片加进列表（拖放与文件框共用）。

        ⚠️ **不去重**（用户 2026-11-16：「同一张图片可以多次上传」）：每次上传
        都是一个新候选键，确认后由宿主复制成 ``x.png`` / ``x-1.png``。
        新上传的图默认勾上（已勾满 2 张时不再替用户做决定）。

        ⚠️ 加完**必须**再排一次缩略图（``_fill_thumbs``）：分批解码只由
        "打开弹窗"时的那一次 ``singleShot`` 驱动，那时新卡片还不存在——不补这
        一下，用户的图上来了但卡片是**空白**的（用户 2026-11-16 报的就是这个）。
        """
        added: list[str] = []
        for text in paths or []:
            path = Path(str(text))
            if not path.is_file():
                continue
            self._upload_seq += 1
            key = f"upload#{self._upload_seq}"
            self._uploads.append((key, path))
            added.append(key)
        if not added:
            return
        self._sync_grids()
        for key in added:
            checked = sum(1 for card in self.cards if card.is_checked())
            if checked >= (1 if self._mode == "append" else 2):
                break
            card = self._cand_cards.get(key)
            if card is not None:
                card.set_checked(True)
        self._update_status()
        # 新卡片补缩略图（分批判，见 _fill_thumbs）；顺手滚到列表末尾，
        # 让用户立刻看见"加进来了"
        QTimer.singleShot(0, self._fill_thumbs)
        QTimer.singleShot(0, self._scroll_to_end)

    def _scroll_to_end(self) -> None:
        """把滚动条拖到最底部（新上传的图排在列表末尾）。"""
        try:
            bar = self.scroll.verticalScrollBar()
        except RuntimeError:  # 弹窗已销毁（延迟队列里的 singleShot 才轮到）
            return
        bar.setValue(bar.maximum())

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if image_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if image_paths(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = image_paths(event.mimeData())
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self.add_uploads(paths)

    # ------------------------------------------------------------------ 填充
    def _source_candidate_paths(self) -> list[Path]:
        """宿主给的候选（不含本次上传的；自动拼版序列用它）。"""
        return list(self._files)

    def _candidate_entries(self) -> list[tuple[str, Path, bool]]:
        """列表内容：``[(键, 路径, 是否本次上传)]``，宿主候选在前、上传的在后。"""
        entries: list[tuple[str, Path, bool]] = [
            (str(path), path, False) for path in self._source_candidate_paths()
        ]
        entries.extend((key, path, True) for key, path in self._uploads)
        return entries

    def _sync_grid(self, grid, store: dict, entries: list) -> list:
        """把网格收敛到 ``entries`` 这批卡片：多退少补、顺序重排。

        ⚠️ 卡片**不跨网格复用**（删/加时旧卡销毁、新卡重建，只把解码好的
        QPixmap 转移过去）。跨网格搬 widget 实例要在布局间摘了又挂，这条路径
        在 Qt 里脆弱（实测能段错误）；缩略图与卡片分离后，销毁重建只是几个
        空壳控件的事。
        """
        want = {key for key, _path, _up in entries}
        for key in [k for k in store if k not in want]:
            store.pop(key).deleteLater()
        cards = []
        for key, path, uploaded in entries:
            card = store.get(key)
            if card is None:
                card = _SourceCard(path, grid, key=key, uploaded=uploaded)
                card.clicked.connect(self._on_card_clicked)
                card.set_pixmap(self._pixmaps.get(key, QPixmap()))
                store[key] = card
            cards.append(card)
        grid.detach_cards()
        grid.adopt_cards(cards)
        return cards

    def _sync_grids(self) -> None:
        """按当前候选重建网格（一个列表，没有页签）。"""
        self.cards = self._sync_grid(
            self.body, self._cand_cards, self._candidate_entries()
        )

    def _populate(self) -> None:
        self._sync_grids()
        self._update_status()
        # 缩略图分批解码：一次全解上百张大图会把弹窗卡住几秒
        QTimer.singleShot(0, self._fill_thumbs)

    def _thumb_pixmap_for(self, card: _SourceCard) -> QPixmap:
        """一张候选的缩略图：**优先用宿主给的预生成小图**，拿不到才整幅解码。

        用户 2026-10-17：弹窗此前对每张候选图**整幅解码**源图再缩——几千像素的
        扫描件一张就要几十 MB 内存、几十毫秒。而这两种候选图**本来就有**
        预生成的 256px 小图：

        - 上游是「图片去底色」的**提交成品** ⇒ ``thumbnails/print[~<节点>]``；
        - 这一步是**流程第一个节点**（候选=入口图片）⇒ ``thumbnails/input/``。

        本次上传的图没有预生成小图（刚选进来），直接整幅解码——它们通常只有
        几张，可以接受。

        ⚠️ **回落路径必须保留**：去底色成品是「1bit 调色板 + tRNS」的透明 PNG，
        缩放读取会给出异常尺寸，只能整幅解码——这条坑见 :func:`_source_thumb_pixmap`。
        """
        if card.uploaded:
            return _source_thumb_pixmap(card.path)
        provided = None
        if self._thumb_provider is not None:
            try:
                provided = self._thumb_provider(str(card.path))
            except Exception:  # noqa: BLE001 - provider 坏掉不该让弹窗整片空白
                provided = None
        if provided:
            pixmap = _source_thumb_pixmap(provided)
            if not pixmap.isNull():
                return pixmap
        return _source_thumb_pixmap(card.path)

    def _fill_thumbs(self) -> None:
        """给还没有缩略图的卡片分批解码。

        ⚠️ 批次之间走 :data:`THUMB_GAP_MS` **有间隔**，不是 ``singleShot(0)``
        ——零间隔会让这一串重解码无缝连着跑满 CPU（用户 2026-10-03 报
        「程序容易跑崩溃，cpu 跑满」）。间隔期间事件循环能真正空出来，
        界面滚动/勾选/关闭都还有响应。
        """
        try:
            self.body.columns()  # noqa: B018 - 真访问 C++：弹窗已销毁就退出
        except RuntimeError:
            return  # 弹窗已被销毁（延迟队列里的 singleShot 才轮到）
        todo = [card for card in self.cards if card.cand_key not in self._pixmaps]
        for card in todo[:THUMB_BATCH]:
            pixmap = self._thumb_pixmap_for(card)
            self._pixmaps[card.cand_key] = pixmap
            card.set_pixmap(pixmap)
        if len(todo) > THUMB_BATCH:
            QTimer.singleShot(THUMB_GAP_MS, self._fill_thumbs)

    # ------------------------------------------------------- 落点选项（插入）
    def _build_position_row(self, default_position: str) -> QWidget:
        """底部「插入第 x 页之前 / 之后」——**只 insert 模式显示**。

        ⚠️ 右键菜单已经表达了落点（向前/向后），这里再给一次单选是为了
        "能在弹窗里改"：「PDF排版 → 插入图片」也是这个口径（用户 2026-10-31）。
        """
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_MD)
        self.before_radio: RadioButton | None = None
        self.after_radio: RadioButton | None = None
        if self._total <= 0:
            label = QLabel("清单为空，插入的页会放到最前面。")
            apply_to(label, T.SIZE_CAPTION, color=T.INK_SOFT)
            layout.addWidget(label)
            layout.addStretch()
            row.setVisible(False)
            return row
        page_no = min(max(self._current_row, 0) + 1, self._total)
        self.before_radio = RadioButton(f"插入第 {page_no} 页之前", row)
        self.after_radio = RadioButton(f"插入第 {page_no} 页之后", row)
        (self.before_radio if default_position == "before"
         else self.after_radio).setChecked(True)
        layout.addWidget(self.before_radio)
        layout.addWidget(self.after_radio)
        layout.addStretch()
        row.setVisible(self._mode == "insert")
        return row

    # ------------------------------------------------------------------ 状态
    def _update_status(self) -> None:
        """说明行/状态行 + 确认按钮的可用性。

        口径：
        1. 勾 **1 张** → 确认可点，单张单独成一页；
        2. 勾 **2 张** → 拼成一页，序号在前的排右侧；
        3. 勾 0 张或 ≥3 张 → 确认不可点（宿主的兜底逻辑按 1/2 张处理）；
        4. 只勾 1 张且是**宿主候选**（不是本次上传）时，pick 模式下方出现
           「从这张图片开始自动拼版」。

        **append 模式**（单图页「新增图片」）：只能勾 **1 张**——0 张或
        ≥2 张时「添加」不可点，「自动拼版」选项整段隐藏。
        """
        append_mode = self._mode == "append"
        picked = [card for card in self.cards if card.is_checked()]
        self.position_row.setVisible(self._mode == "insert")
        auto_available = (
            not append_mode and self._mode == "pick"
            and len(picked) == 1 and not picked[0].uploaded
        )
        self.auto_checkbox.setVisible(auto_available)
        if not auto_available and self.auto_checkbox.isChecked():
            # 选项只在恰好勾 1 张时有意义：离开该状态就复位，避免残留旧勾选
            self.auto_checkbox.setChecked(False)
        self.ok_button.setEnabled(len(picked) in ((1,) if append_mode else (1, 2)))
        uploaded = len(self._uploads)
        self.upload_hint.setText(
            f"本次已上传 {uploaded} 张（排在列表末尾、默认勾选）" if uploaded else ""
        )
        if append_mode:
            self.note.setText(
                f"从剩余未拼版的 {self.count()} 张图片中选 1 张，"
                "添加到当前这一页拼版；也可以拖入/上传自己的图片。"
            )
        elif self._mode == "insert":
            page_no = min(max(self._current_row, 0) + 1, max(self._total, 1))
            where = "之前" if self.position() == "before" else "之后"
            self.note.setText(
                f"从剩余未拼版的 {self.count()} 张图片中勾选，插到第 {page_no} 页"
                f"{where}：1 张单独成一页，2 张拼成一页（序号在前的排在右侧）；"
                "也可以拖入/上传自己的图片。"
            )
        else:
            self.note.setText(
                f"从剩余未拼版的 {self.count()} 张图片中勾选："
                "1 张单独成一页，2 张拼成一页（序号在前的排在右侧）；"
                "只勾 1 张图片时可勾选下方「从这张图片开始自动拼版」，"
                "从那张图起自动拼完。也可以拖入/上传自己的图片。"
            )
        self.status.setStyleSheet(f"color:{T.INK_SOFT};")
        count = len(picked)
        if count == 0:
            self.status.setText(
                "已选 0 张。点卡片勾选：1 张单独成页，2 张拼成一页。"
            )
            return
        if count == 1:
            first = picked[0]
            tag = ""
            if not first.uploaded and classify_source(first.path) == SOURCE_FULL:
                tag = "（整幅）"
            self.status.setText(
                f"已选 1 张：「{first.path.stem}」{tag}。"
                + ("点「插入」把它插到目标位置。" if self._mode == "insert"
                   else "点「开始拼版」单独成一页；也可勾选下方"
                        "「从这张图片开始自动拼版」从这张起自动拼完。")
            )
            return
        if count == 2:
            self.status.setText(
                "已选 2 张：将拼成一页，序号在前的排在右侧。"
            )
            return
        self.status.setText(
            f"已选 {count} 张：最多勾 2 张——两张拼一页，或 1 张单独成页。"
        )


__all__ = ["ImpositionPickerDialog", "THUMB_W", "THUMB_H", "CARD_W", "CARD_H"]
