# -*- coding: utf-8 -*-
"""「选择拼版」弹窗（**模块一：选择拼版** 的 UI）。

从**剩余未被选择拼版的图片**（源清单里还没被任何一页用过的，见
``services.imposition.remaining_files``）里**自由多选**——选择阶段不限
张数、不做任何配对；点「开始拼版」时才把勾选的图按源清单顺序**每两张
配成一页**（序号在前的进右槽），落单的不拼。

「删除图片」把勾选的图移出选择范围（**软删除**：黑名单由宿主落盘到
``drafts/imposition.json`` 的 ``removed`` 字段，源文件不动）；
「查看删除的图片」切换到已删除视图，可勾选批量恢复。

这里只做控件与信号；弹窗怎么被唤起、选中之后怎么建页落盘，见
``desktop/pages/taskdetail/imposition_pages.py``（模块一控制器）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from qframelesswindow import FramelessDialog
from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImageReader, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QStackedWidget,
    QVBoxLayout, QWidget,
)
from qfluentwidgets import CheckBox, PrimaryPushButton, PushButton

from desktop.services.imposition import SOURCE_FULL, classify_source
from desktop.ui import theme as T
from desktop.ui.widgets import apply_to
from desktop.ui.window_size import apply_window_size

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
#: "CPU 跑满、界面像崩了"。同项目别处的分批装载都留了间隔（见
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
    scaled = image.scaled(
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

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = Path(path)
        self._checked = False
        self._pixmap = QPixmap()
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{self.path}\n勾选后：序号在前的排到拼版页右侧")

        column = QVBoxLayout(self)
        # ⚠️ 上留白必须够放下勾选框：勾选框画在卡片的 paintEvent 里，而缩略图是
        # **子控件**、会盖在卡片之上——不给它留位置，勾选标记就被缩略图压住，
        # 只剩一角露出来（实测像个残缺的弧线）。
        column.setContentsMargins(10, CARD_HEAD, 10, 8)
        column.setSpacing(6)
        self.thumb = QLabel(self)
        self.thumb.setFixedSize(THUMB_W, THUMB_H)
        self.thumb.setAlignment(Qt.AlignCenter)
        column.addWidget(self.thumb, 0, Qt.AlignHCenter)
        self.name = QLabel(self.path.stem, self)
        self.name.setAlignment(Qt.AlignCenter)
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
        painter.setRenderHint(QPainter.Antialiasing)
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
            painter.setPen(QPen(QColor(T.ACCENT), 2.0, Qt.SolidLine,
                                Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
        painter.end()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.rect().contains(
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
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

    def add_card(self, card: _SourceCard) -> None:
        self._cards.append(card)
        self._relayout(force=True)

    def detach_cards(self) -> None:
        """把当前卡片全部摘出布局（不销毁；实例还在宿主的字典里复用）。"""
        for old in self._cards:
            self.grid.removeWidget(old)
        self._cards = []

    def adopt_cards(self, cards: list) -> None:
        """装入一批卡片并重排（调用前必须先 ``detach_cards`` 两边网格——

        ⚠️ 卡片会在两个网格间迁移：若目标网格装入时卡片还挂在另一个网格的
        布局里，Qt 的布局一致性会被打破（实测段错误）。所以宿主 ``_sync_grids``
        的顺序是：先两边都 detach，再各自 adopt。
        """
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
    """「选择拼版」弹窗：从剩余未使用的源图里勾选两张。

    两种模式（2026-09-30 新增 ``mode`` 参数）：

    - **``"pick"``**（默认，选页）：自由多选，1 张单独成页 / 2 张拼一页；
    - **``"append"``**（单图页「新增图片」）：**只能勾 1 张**，确认按钮叫
      「添加」——宿主把这张图并进当前那一页拼版（见模块一控制器）。

    **卡片网格**：一行摆好几张（列数随窗口宽度自动变），卡片 ``CARD_W×CARD_H``、
    缩略图固定 ``THUMB_W×THUMB_H``（用户要求「一行好几个、选框宽一些」且
    「图片要正常显示、要有文字」）。

    **可缩放**（用户 2026-09-30 要求）：底座是 ``qframelesswindow.FramelessDialog``，
    恢复它的最小化/最大化按钮与「双击标题栏放大/还原」；边缘还能拖拽调整大小，
    网格列数跟着窗口宽度自动变。

    **删除/恢复**（用户 2026-09-30 要求）：勾选卡片可「删除图片」——移出选择
    范围（软删除，源文件不动，黑名单由宿主落盘）；「查看删除的图片」切到
    已删除视图，勾选后「恢复选中」或「全部恢复」。

    源清单顺序在前的图会被放到拼版页**右侧**（用户口径），这里按同一顺序
    展示，勾选结果也按**源清单顺序**返回（不是点选先后）。
    """

    def __init__(self, files: list, parent=None, removed_files=None,
                 mode: str = "pick"):
        super().__init__(parent)
        self._mode = "append" if mode == "append" else "pick"
        # ``files`` 是**候选池**：剩余未用 + 已删除（宿主按源清单顺序合并传入），
        # 实际候选 = 池子减去黑名单——这样"恢复"后的图才有地方回去。
        self._files = [Path(f) for f in files]
        self._removed: list[Path] = []
        seen: set[str] = set()
        for f in removed_files or []:
            key = str(Path(f))
            if key not in seen:
                seen.add(key)
                self._removed.append(Path(f))
        self._initial_removed = {str(p) for p in self._removed}
        self._pixmaps: dict[str, QPixmap] = {}  # 解码好的缩略图（路径 → 图）
        self._cand_cards: dict[str, _SourceCard] = {}
        self._rem_cards: dict[str, _SourceCard] = {}
        self.cards: list[_SourceCard] = []  # 候选视图当前卡片（源清单顺序）
        self.removed_cards: list[_SourceCard] = []  # 已删除视图当前卡片
        self._removed_view_visited = False
        # append 模式（单图页「新增图片」）：标题与确认按钮换文案
        self.setWindowTitle("新增图片" if self._mode == "append" else "选择拼版")
        self.setModal(True)
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
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.body = _CardGrid()  # 第 0 页：候选
        self.removed_body = _CardGrid()  # 第 1 页：已删除
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.body)
        self.stack.addWidget(self.removed_body)
        self.scroll.setWidget(self.stack)
        column.addWidget(self.scroll, 1)

        self.status = QLabel("", self)
        self.status.setWordWrap(True)
        apply_to(self.status, T.SIZE_CAPTION, color=T.INK_SOFT)
        column.addWidget(self.status)

        # 「从这张图片开始自动拼版」：**恰好勾 1 张**时出现在下方（不限
        # 整幅/半幅，用户 2026-10-01 定）——勾上后点「开始拼版」，宿主从
        # 这张图起把剩余候选按自动拼版规则（整幅单独一页、左半幅+右半幅
        # 配对）全部拼完。
        self.auto_checkbox = CheckBox("从这张图片开始自动拼版", self)
        self.auto_checkbox.setToolTip(
            "只勾选 1 张图片时可用：从这张图起，把剩余未拼版的图片按顺序"
            "自动拼完——整幅图单独一页，左半幅与紧随其后的右半幅拼成一页"
            "（序号在前的排在右侧），落单的图单独一页。"
        )
        self.auto_checkbox.toggled.connect(self._update_status)
        self.auto_checkbox.hide()
        column.addWidget(self.auto_checkbox)

        self.restore_button = PushButton("恢复选中", self)
        self.restore_button.clicked.connect(self._on_restore_clicked)
        self.restore_button.hide()
        self.restore_all_button = PushButton("全部恢复", self)
        self.restore_all_button.clicked.connect(self._on_restore_all)
        self.restore_all_button.hide()
        self.removed_entry_button = PushButton("查看删除的图片", self)
        self.removed_entry_button.clicked.connect(
            lambda: self._show_removed_view(True)
        )
        self.back_button = PushButton("返回选择", self)
        self.back_button.clicked.connect(lambda: self._show_removed_view(False))
        self.back_button.hide()
        self.delete_button = PushButton("删除图片", self)
        self.delete_button.clicked.connect(self._on_delete_clicked)
        buttons = QHBoxLayout()
        buttons.addWidget(self.restore_button)
        buttons.addWidget(self.restore_all_button)
        buttons.addStretch(1)
        buttons.addWidget(self.removed_entry_button)
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.delete_button)
        cancel = PushButton("取消", self)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.ok_button = PrimaryPushButton(
            "添加" if self._mode == "append" else "开始拼版", self
        )
        self.ok_button.setEnabled(False)
        self.ok_button.clicked.connect(self.accept)
        buttons.addWidget(self.ok_button)
        column.addLayout(buttons)

        self._populate()
        self._update_status()

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
        title = QLabel(self.windowTitle(), self.titleBar)
        apply_to(title, T.SIZE_BODY, bold=True, color=T.INK)
        self.titleBar.hBoxLayout.insertSpacing(0, 12)
        self.titleBar.hBoxLayout.insertWidget(1, title, 0, Qt.AlignLeft)

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
        """候选视图的卡片数（已删除的不算）。"""
        return len(self.cards)

    def checked_files(self) -> list[Path]:
        """用户勾选的源图（**按源清单顺序**，不是勾选先后）。

        张数不限——配对（每两张一页）由宿主在「开始拼版」后做。
        """
        chosen = {str(card.path) for card in self.cards if card.is_checked()}
        return [path for path in self._candidate_paths() if str(path) in chosen]

    #: 兼容旧名（宿主与护栏历史上叫 picked_files）
    def picked_files(self) -> list[Path]:
        return self.checked_files()

    def auto_mode_file(self) -> Path | None:
        """「从这张图片开始自动拼版」生效的那张图（不生效返回 None）。

        生效条件：勾选框被勾上、且**恰好勾了 1 张图**——选项只在恰好
        勾 1 张时出现（不限整幅/半幅，用户 2026-10-01 定），多选不走自动。
        """
        if not self.auto_checkbox.isChecked():
            return None
        picked = self.checked_files()
        return picked[0] if len(picked) == 1 else None

    def auto_sequence(self) -> list[Path]:
        """自动拼版的图片序列：从勾选那张起到候选清单末尾（源清单顺序）。

        「自此之后」= 含勾选的那张本身；它之前的图片不参与（留在候选池，
        之后仍可手动拼）。
        """
        file = self.auto_mode_file()
        if file is None:
            return []
        candidates = self._candidate_paths()
        return candidates[candidates.index(file):]

    def removed_files(self) -> list[Path]:
        """当前黑名单（含会话内新删的，不含已恢复的）。"""
        return list(self._removed)

    def removed_changed(self) -> bool:
        """黑名单与打开时是否不同（宿主据此决定要不要落盘）。"""
        return {str(p) for p in self._removed} != self._initial_removed

    def toggle_card(self, card: _SourceCard) -> None:
        """切换一张候选卡片的勾选（自由多选，不设上限）。"""
        card.set_checked(not card.is_checked())
        self._update_status()

    # -------------------------------------------------------------- 删除/恢复
    def _on_delete_clicked(self) -> None:
        """「删除图片」：勾选的候选移入黑名单（软删除，可恢复）。"""
        picked = self.checked_files()
        if not picked:
            return
        self._removed.extend(picked)
        self._sync_grids()
        self._update_status()

    def _on_restore_clicked(self) -> None:
        """「恢复选中」：勾选的已删除图移回候选。"""
        chosen = {str(c.path) for c in self.removed_cards if c.is_checked()}
        if not chosen:
            return
        self._removed = [p for p in self._removed if str(p) not in chosen]
        self._sync_grids()
        self._update_status()

    def _on_restore_all(self) -> None:
        """「全部恢复」：清空黑名单。"""
        if not self._removed:
            return
        for card in self.removed_cards:
            card.set_checked(False)
        self._removed.clear()
        self._sync_grids()
        self._update_status()

    def _show_removed_view(self, on: bool) -> None:
        """在候选 / 已删除两个视图间切换。"""
        self.stack.setCurrentIndex(1 if on else 0)
        if on:
            self._removed_view_visited = True
            QTimer.singleShot(0, self._fill_thumbs)
        self._update_status()

    def _on_card_clicked(self, card: _SourceCard) -> None:
        """卡片点击分发：候选走「最多两张」的勾选规则，已删除随便勾（批量恢复）。"""
        if card in self.removed_cards:
            card.set_checked(not card.is_checked())
            self._update_status()
            return
        self.toggle_card(card)

    # ------------------------------------------------------------------ 填充
    def _candidate_paths(self) -> list[Path]:
        removed = {str(p) for p in self._removed}
        return [p for p in self._files if str(p) not in removed]

    def _sync_grid(self, grid, store: dict, keys: list[str]) -> list:
        """把一个网格收敛到 ``keys`` 这批卡片：多退少补、顺序重排。

        ⚠️ 卡片**不跨网格复用**（删除/恢复时旧卡销毁、新卡重建，只把解码好的
        QPixmap 转移过去）。跨网格搬 widget 实例要在布局间摘了又挂，这条路径
        在 Qt 里脆弱（实测能段错误）；缩略图与卡片分离后，销毁重建只是几个
        空壳控件的事。
        """
        want = set(keys)
        for key in [k for k in store if k not in want]:
            store.pop(key).deleteLater()
        cards = []
        for key in keys:
            card = store.get(key)
            if card is None:
                card = _SourceCard(Path(key), grid)
                card.clicked.connect(self._on_card_clicked)
                card.set_pixmap(self._pixmaps.get(key, QPixmap()))
                store[key] = card
            cards.append(card)
        grid.detach_cards()
        grid.adopt_cards(cards)
        return cards

    def _sync_grids(self) -> None:
        """按当前候选/黑名单重建两个网格。"""
        removed_keys = [str(p) for p in self._removed]
        removed_set = set(removed_keys)
        self.cards = self._sync_grid(
            self.body, self._cand_cards,
            [str(p) for p in self._files if str(p) not in removed_set],
        )
        self.removed_cards = self._sync_grid(
            self.removed_body, self._rem_cards, removed_keys,
        )

    def _populate(self) -> None:
        self._sync_grids()
        # 缩略图分批解码：一次全解上百张大图会把弹窗卡住几秒
        QTimer.singleShot(0, self._fill_thumbs)

    def _fill_thumbs(self) -> None:
        """给还没有缩略图的卡片分批解码（已删除视图访问过才解它的图）。

        ⚠️ 批次之间走 :data:`THUMB_GAP_MS` **有间隔**，不是 ``singleShot(0)``
        ——零间隔会让这一串重解码无缝连着跑满 CPU（用户 2026-10-03 报
        「程序容易跑崩溃，cpu 跑满」）。间隔期间事件循环能真正空出来，
        界面滚动/勾选/关闭都还有响应。
        """
        try:
            self.stack.currentIndex()  # noqa: B018 - 真访问 C++：弹窗已销毁就退出
        except RuntimeError:
            return  # 弹窗已被销毁（延迟队列里的 singleShot 才轮到）
        pools = self.cards + self.removed_cards \
            if self._removed_view_visited else self.cards
        todo = [card for card in pools
                if str(card.path) not in self._pixmaps]
        for card in todo[:THUMB_BATCH]:
            pixmap = _source_thumb_pixmap(card.path)
            self._pixmaps[str(card.path)] = pixmap
            card.set_pixmap(pixmap)
        if len(todo) > THUMB_BATCH:
            QTimer.singleShot(THUMB_GAP_MS, self._fill_thumbs)

    # ------------------------------------------------------------------ 状态
    def _update_status(self) -> None:
        """说明行/状态行 + 各按钮的显隐与可用性。

        口径：
        1. 勾 **1 张**（整幅或半幅）→「开始拼版」可点，单张单独成页；
           同时下方出现「从这张图片开始自动拼版」（不限整幅/半幅，
           用户 2026-10-01 定），勾上即走自动拼版；
        2. 勾 **2 张**（半幅）→ 拼成一页，序号在前的排右侧；
        3. 自动拼版从勾选那张起拼完剩余候选（整幅单独一页；半幅按
           「前一左＋后一右」且页号连续配对）。
        勾 0 张或 ≥3 张时「开始拼版」不可点。已删除视图里可恢复。

        **append 模式**（单图页「新增图片」）：只能勾 **1 张**——0 张或
        ≥2 张时「添加」不可点，「自动拼版」选项整段隐藏（加进已有页的
        动作与自动拼版互斥）。
        """
        removed_view = self.stack.currentIndex() == 1
        candidates = self._candidate_paths()
        picked = self.checked_files()
        append_mode = self._mode == "append"
        auto_available = (
            not append_mode
            and not removed_view and len(picked) == 1
        )
        self.auto_checkbox.setVisible(auto_available)
        if not auto_available and self.auto_checkbox.isChecked():
            # 选项只在恰好勾 1 张时有意义：离开该状态就复位，避免残留旧勾选
            self.auto_checkbox.setChecked(False)
        self.ok_button.setEnabled(len(picked) in ((1,) if append_mode else (1, 2)))
        self.removed_entry_button.setVisible(not removed_view)
        self.delete_button.setVisible(not removed_view)
        self.ok_button.setVisible(not removed_view)
        self.restore_button.setVisible(removed_view)
        self.restore_all_button.setVisible(removed_view)
        self.back_button.setVisible(removed_view)
        self.removed_entry_button.setText(f"查看删除的图片 ({len(self._removed)})")
        self.delete_button.setEnabled(bool(picked))
        self.restore_button.setEnabled(
            any(c.is_checked() for c in self.removed_cards)
        )
        self.restore_all_button.setEnabled(bool(self._removed))
        if removed_view:
            self.note.setText(
                f"以下 {len(self._removed)} 张图片已被移出「选择拼版」范围"
                "（源文件不受影响）。勾选后「恢复选中」，或「全部恢复」，"
                "恢复后重新进入选择范围。"
            )
            self.status.setStyleSheet(f"color:{T.INK_SOFT};")
            self.status.setText(
                f"已删除 {len(self._removed)} 张。"
                if self._removed else "没有已删除的图片。"
            )
            return
        if append_mode:
            self.note.setText(
                f"从剩余未拼版的 {len(candidates)} 张图片中选 1 张，"
                "添加到当前这一页拼版（「删除图片」把不用的图移出选择范围）。"
            )
            self.status.setStyleSheet(f"color:{T.INK_SOFT};")
            count = len(picked)
            if count == 0:
                self.status.setText("已选 0 张。点卡片勾选 1 张图片。")
            elif count == 1:
                self.status.setText(
                    f"已选 1 张：「{picked[0].stem}」。"
                    "点「添加」把它加进当前页拼版。"
                )
            else:
                self.status.setText(
                    f"已选 {count} 张：本页只能再添加 1 张，请取消多余的勾选。"
                )
            return
        self.note.setText(
            f"从剩余未拼版的 {len(candidates)} 张图片中勾选："
            "1 张单独成一页，2 张拼成一页（序号在前的排在右侧）；"
            "只勾 1 张图片时可勾选下方「从这张图片开始自动拼版」，"
            "从那张图起自动拼完。「删除图片」把不用的图移出选择范围。"
        )
        self.status.setStyleSheet(f"color:{T.INK_SOFT};")
        count = len(picked)
        if count == 0:
            self.status.setText(
                "已选 0 张。点卡片勾选：1 张单独成页，2 张拼成一页。"
            )
            return
        if count == 1:
            tag = "（整幅）" if classify_source(picked[0]) == SOURCE_FULL else ""
            self.status.setText(
                f"已选 1 张：「{picked[0].stem}」{tag}。点「开始拼版」"
                "单独成一页；也可勾选下方「从这张图片开始自动拼版」"
                "从这张起自动拼完。"
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
