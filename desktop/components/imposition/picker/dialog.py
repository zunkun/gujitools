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
from qfluentwidgets import CheckBox, FluentIcon as FIF, PrimaryPushButton, PushButton

from desktop.components.imposition.picker._qt import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPixmap,
    QScrollArea,
    QSize,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)
from desktop.components.imposition.picker.cards import _CardGrid, _SourceCard
from desktop.components.imposition.picker.constants import DIALOG_H, DIALOG_W
from desktop.components.imposition.picker.fill import _FillMixin
from desktop.components.imposition.picker.status import _StatusMixin
from desktop.components.print_insert_dialog import IMAGE_FILTER, image_paths
from desktop.ui import theme as T
from desktop.ui.widgets import apply_to
from desktop.ui.window_size import apply_window_size
from desktop.utils.files import default_open_dir
from utils.crash_log import breadcrumb


class ImpositionPickerDialog(_FillMixin, _StatusMixin, FramelessDialog):
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

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """留一条面包屑：这个弹窗是**独立顶层窗口**，崩在窗口几何计算上时
        能据此判断"是不是刚开了它"（2026-11-21 排查用）。"""
        super().showEvent(event)
        breadcrumb(f"拼版选图弹窗显示：候选 {len(self._files)} 张，"
                   f"mode={self._mode}")

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
        # 系统选图框是**真窗口**（IFileOpenDialog），崩溃点在窗口几何计算上时
        # 这两条面包屑能把"是不是它"钉死（2026-11-21）。
        breadcrumb("打开系统选图对话框")
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", str(default_open_dir()), IMAGE_FILTER
        )
        breadcrumb(f"系统选图对话框返回：{len(filenames or [])} 张")
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
        breadcrumb(f"选图弹窗新增上传 {len(added)} 张")
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
