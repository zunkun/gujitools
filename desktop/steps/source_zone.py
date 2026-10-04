# -*- coding: utf-8 -*-
"""共用「大输入区」：拖拽 / 点选，把**文件或文件夹**交给一个步骤。

用户 2026-10-02 的要求（原话）：

> 你就在左侧这些目录点上去，页面上有一个大的输入框，可以输入图片和输入文件，
> 或者输入目录，也可以把文件拖进去，目录投进去。

于是有了这一块：**一个控件同时承担"选择"和"放下"两件事**，三条入口都通——

1. 拖**文件**进来；
2. 拖**文件夹**进来（含图片/PDF 的目录）；
3. **点按钮**选（空态底部两个真按钮「选择文件 / 选择文件夹」；已选态右端
   「更换」）——也可以点空态空白处或按回车，那条老入口仍留着。

⚠️ 第 3 条为什么要做成**看得见的按钮**（用户 2026-10-03 报）：原先只有"点
空白处弹两选项小菜单"这一条隐式入口，界面上没有任何东西提示它能点，用户看到
的只是一句"把 PDF 拖到这里"，于是报「不能直接点击按钮选择文件或文件夹」。
入口既然是主路径，就得画出来。

⚠️⚠️ **点空白处不再弹"选文件 / 选文件夹"那个两选项小菜单**（用户 2026-10-03
第二次提要求：「能否底部不设置选择图片或者目录的弹窗」）。那个小菜单锚在控件
**底部**，正是用户说的"底部弹窗"。现在点空白处 = **直接开选择对话框**（选文件），
不再先问一遍"你要文件还是目录"。

⚠️⚠️⚠️ **"选择对话框" ≠ "资源管理器窗口"**（2026-10-03 用户第三次纠正）。
曾经误实现成"弹一个 ``explorer.exe`` 窗口 + 监听用户在窗口里的选中项"，用户
明确否掉：「不对，现在直接打开资源浏览器了，而不是调用资源浏览器选择文件或者
目录」。二者区别很大：

- **要的**：资源管理器那套**选文件/选目录的对话框**，选完直接拿到结果 ——
  也就是 :class:`QFileDialog` 的**原生**对话框（不设 ``DontUseNativeDialog``，
  Windows 上它本来就是资源管理器式的那套界面），有"打开/取消"、结果确定；
- **不要的**：另开一个**浏览用的资源管理器窗口**，再靠轮询/监听去猜他点了谁 ——
  用户还得自己双击文件夹去定位，程序只能猜，且弹出的窗口与"选文件"无关。

它是 :mod:`desktop.steps` 层的一部分，所以左侧三个模块与任务流程**共用同一份
实现**——这正是用户要的"抽成公共组件、定义好入口/出口 API"。

设计要点（改之前先读）：

- **只管"用户给了哪些路径"，不管"这算不算合法输入"**。归一化（一堆文件/文件夹
  → 一个"源"）由 :meth:`desktop.steps.spec.StepSpec.resolve_source` 负责，
  那是纯逻辑、可以脱离 Qt 单测；本控件只把原始路径经 ``paths_chosen`` 发出去。
  这样"拼图"这种要整份清单的调用方也能直接复用本控件。
- **虚框自绘、按钮用真控件**：外框、图标、两行文案、清空 ✕ 都是 ``paintEvent``
  画的（项目规矩：基础控件不引样式表），但「选择文件 / 选择文件夹 / 更换」
  必须是 :class:`qfluentwidgets.PushButton` —— 它们要 hover、按下、焦点态，
  自绘等于把这些交互重写一遍还写不好。因此本控件内部**有一个子控件层**，
  几何由 :meth:`SourceZone._relayout_buttons` 手工摆（空态摆在文案下方、
  已选态右端一枚），自绘内容按同一个基准排（见 :meth:`_empty_block_top`）。
- **空态的"文案 + 按钮"是一整块、垂直居中**（用户 2026-10-03 截图反馈）：
  独占模式下控件高达 700px+，若文案贴顶、按钮钉在框底，中间是一大片空白，
  看着像两个不相干的区域。``_empty_block_height`` 把按钮也算进整块高度，
  两边共用 ``_empty_block_top`` ⇒ 文案与按钮永远贴在一起、一起居中。
- **拖拽热区**：拖到控件上（或宿主页面上，见 ``ModulePage``）时描边与底色变主色，
  给"松手就放这儿"的反馈。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QSizePolicy,
    QWidget,
)
from qfluentwidgets import FluentIcon as FIF, PushButton, Theme

from desktop.steps.spec import StepSpec
from desktop.ui import theme as T
from desktop.ui.icons import PDF_FILE
from desktop.utils.files import default_open_dir

#: 空态高度（px）：要"大"，一眼看出这里是主入口。
#:
#: ⚠️ 底部要给**文案与按钮整块**留位（用户 2026-10-03 报「有框说可以拖入，
#: 但没法直接点击按钮选择文件或文件夹」）：只靠"点空白处弹小菜单"这条隐式
#: 入口，用户根本不知道哪里能点。现在空态底部摆两个真按钮，且**与文案一起
#: 垂直居中**（见 ``_empty_block_top``）。
EMPTY_HEIGHT = 168
#: 已选态高度（px）：收窄成一行，把纵向空间还给预览
FILLED_HEIGHT = 74
#: 空态图标盒子边长（px）
ICON_BOX = 30
#: 清空按钮的点击盒边长（px）
CLOSE_BOX = 26
#: 选择按钮高度（px）与按钮之间的间距（px）
BUTTON_HEIGHT = 30
BUTTON_GAP = 10
#: 内容与虚框的左右留白（px）
PAD = T.SPACE_LG
#: **独占模式**（页面上再没有别的控件，见
#: :meth:`desktop.modules.base.ModulePage.show_workspace`）下的高度：
#: 撑满整幅，让"当前页只有一个输入框"看起来是**刻意设计**而不是内容没加载出来。
SOLO_HEIGHT = 320
#: 独占模式的最小宽度（px）：再窄就换行/省略，不必保持
SOLO_MIN_WIDTH = 360
#: 「高度不设上限」用的哨兵值 = Qt 自己的 ``QWIDGETSIZE_MAX``。
#:
#: ⚠️ Qt 的 ``QWIDGETSIZE_MAX`` 在 PySide6 里**没有导出**（``QtCore`` 与
#: ``QtWidgets`` 都 import 不到），所以按它的定义写死：它是 ``(1 << 24) - 1``，
#: 即 16777215。
#:
#: ⚠️⚠️ **必须是 ``- 1``，不能写 ``1 << 24``**（用户 2026-10-03 报「单独拼板
#: 界面报错」）：``setMaximumHeight(16777216)`` 超过 Qt 的硬上限，Qt 会往
#: stderr 打 ``QWidget::setMaximumSize: The largest allowed size is
#: (16777215,16777215)`` 并把值**截断**回 16777215。功能上无害（截断后正是
#: 我们要的"不设上限"），但拼板独立页初始就是独占模式，每次进页面都刷这条
#: 警告，看着像报错。控件实际高度由布局决定，永远碰不到这个上限。
HEIGHT_UNLIMITED = (1 << 24) - 1


class SourceZone(QWidget):
    """一个步骤的**大输入区**：拖入 / 点选文件或文件夹（自绘，可清空）。

    信号：

    - ``paths_chosen(list)``：用户拖入或选中了一批路径（``list[str]``，**原始**，
      未做任何合法性判断）；空拖拽不会发。
    - ``cleared()``：用户点了右上角的清空。
    - ``rejected(str)``：**控件自己没能完成这次选择**（如选择对话框根本打不开）
      —— 一句给用户看的话。调用方通常转成页头的 toast/状态行。

    ⚠️ **"用户取消了对话框"不算 rejected**（用户2026-10-04）：那是"我什么都没
    选"，弹提示是噪声。**"给的东西一步都跑不了"也不走这里**——那属于归一化
    层的判断，由 :meth:`StepSpec.resolve_source` 给出理由并经宿主的 ``status``
    通道呈现（见 :meth:`offer`）。

    显示与语义分离：``set_source()`` 只负责"把现在选中的源画出来"，不发信号，
    因此宿主（:class:`~desktop.steps.control.StepControl`）说了算——它才是
    "文件/目录 → 一个源"的归一化权威。
    """

    paths_chosen = Signal(list)
    cleared = Signal()
    rejected = Signal(str)

    def __init__(self, spec: StepSpec, parent=None):
        """按 ``spec`` 取文案/图标/过滤串；初始为空态。"""
        super().__init__(parent)
        self.spec = spec
        self._source: Path | None = None
        self._detail = ""
        self._hot = False        # 有东西正拖在本控件上方
        self._hover = False      # 鼠标悬停
        self._close_rect = QRectF()
        #: 独占模式：页面上再没有别的控件（只有这一个输入框），撑满整幅
        self._solo = False
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(260)
        self._sync_height()
        self.setToolTip(self._hint_text())
        self._build_buttons()

    # ------------------------------------------------------------------ 按钮
    def _build_buttons(self) -> None:
        """空态摆**两个真按钮**：「选择文件」「选择文件夹」。

        ⚠️ 为什么必须有按钮（用户 2026-10-03 报）：此前唯一的入口是"点大输入区
        空白处 → 弹一个两选项的小菜单"。功能上确实通，但界面上**没有任何东西
        提示这里能点**，用户看到的只有一行"把 PDF 拖到这里"，于是报
        「不能直接点击按钮选择文件或文件夹」。把入口显式画成按钮，意图就不用猜了。

        ``accepts_dir=False`` 的步骤不摆"选择文件夹"（摆一个注定被拒的入口
        是骗人）——「PDF 只支持文件」的图片提取就是这一档，此时页面上只有
        「选择文件」一枚；此时点空白处也直接开文件对话框，菜单那一层整个省掉。

        几何见 :meth:`_relayout_buttons`（摆在文案下方，与文案一起居中）。
        """
        self._button_row = QWidget(self)
        self._button_row.setObjectName("sourceZoneButtons")
        row = QHBoxLayout(self._button_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(BUTTON_GAP)
        row.addStretch(1)

        # 图标跟着步骤的输入物走：入口是 PDF 就用带 "PDF" 字样的自绘图
        # （``FIF.DOCUMENT`` 是空文档，会被读成"文档"），图片步骤仍旧用它。
        file_icon = (PDF_FILE if self.spec.input_noun() == "PDF" else FIF.DOCUMENT)
        self.file_button = PushButton(file_icon, self.spec.pick_label, self)
        self.file_button.setFixedHeight(BUTTON_HEIGHT)
        self.file_button.setToolTip(f"从磁盘上挑一个{self.spec.input_noun()}文件")
        self.file_button.clicked.connect(lambda: self._browse_kind(from_files=True))
        row.addWidget(self.file_button)

        self.dir_button: PushButton | None = None
        if self.spec.accepts_dir:
            self.dir_button = PushButton(FIF.FOLDER, "选择文件夹", self)
            self.dir_button.setFixedHeight(BUTTON_HEIGHT)
            self.dir_button.setToolTip("选一个文件夹，按里面可用的文件批量处理")
            self.dir_button.clicked.connect(
                lambda: self._browse_kind(from_files=False)
            )
            row.addWidget(self.dir_button)
        row.addStretch(1)

        # 已选态的「更换」：不重新走清空，直接再选一次。
        self._swap_button = PushButton(FIF.SYNC, "更换", self)
        self._swap_button.setToolTip("换一个文件或文件夹（不清空当前选择）")
        self._swap_button.clicked.connect(self._browse_soon)
        self._swap_button.setVisible(False)
        self._relayout_buttons()

    def _relayout_buttons(self) -> None:
        """摆按钮行：空态**紧跟在文案下方**并与整块内容一起居中；已选态放右端。

        ⚠️ 空态的按钮**不再钉在框底边**（用户 2026-10-03 截图反馈）：独占模式下
        控件高达 700px+，按钮贴在最底、图标文案在最上，中间是一大片空白，
        看起来像两个不相干的区域。改成"文案 + 按钮 = 一整块，垂直居中"，
        这才像一个完整的输入区。
        """
        # ⚠️ ``_sync_height()`` 在 ``_build_buttons()`` **之前**就被调过一次
        #    （构造顺序：先定高度再挂子控件），那时按钮还不存在。
        if getattr(self, "_button_row", None) is None:
            return
        row = self._button_row
        empty = self._source is None
        self._swap_button.setVisible(not empty)
        row.setVisible(empty)
        if empty:
            # 按钮顶边 = 整块内容（图标+标题+提示）底边，再加一点间距
            top = self._empty_block_bottom() + BUTTON_GAP
            row.setGeometry(0, top, self.width(), BUTTON_HEIGHT)
        else:
            # 已选态：右端并排放「更换」与清空 ✕
            w = self._swap_button.sizeHint().width()
            self._swap_button.setFixedHeight(FILLED_HEIGHT - 22)
            self._swap_button.setGeometry(
                max(0, self.width() - CLOSE_BOX - T.SPACE_MD - w),
                (self.height() - self._swap_button.height()) // 2,
                w,
                self._swap_button.height(),
            )
        # 空态整块可点（点空白 = 选文件）；已选态只有按钮与 ✕ 是交互区
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if empty else Qt.CursorShape.ArrowCursor
        )

    # ------------------------------------------------------------------ 对外
    def source(self) -> Path | None:
        """当前**显示**的源（宿主设进来的；未设为 ``None``）。"""
        return self._source

    def set_source(self, path: Path | str | None, detail: str = "") -> None:
        """把"当前源"画出来（不发 ``paths_chosen``，避免与宿主来回打环）。

        ``path=None`` 回到空态；``detail`` 是已选态的第二行小字（如"文件夹 ·
        12 个文件"），留空时按路径自动生成。
        """
        self._source = Path(path) if path else None
        self._detail = detail or self._auto_detail(self._source)
        self._sync_height()
        self.setToolTip(self._hint_text())
        self.update()

    def offer(self, paths) -> None:
        """把一批路径当作用户给的输入送出去（拖拽/点选/宿主转发都走这里）。

        ⚠️ **空列表一律静默**（用户 2026-10-04：「如果没有导入完全没有必要提示」）：
        走到这里只有一种情形——**用户在选择对话框里点了「取消」**（`_pick` 拿到
        空结果）。那是"我什么都没选"，不是"你给的东西用不了"，弹一句
        「这个用不上 / 没有拿到可用的文件或文件夹」纯属噪声（用户反馈的正是这条）。

        **"东西真的给过、但一步都跑不了"是另一回事**，由
        :meth:`StepSpec.resolve_source` 给出理由（目录里没有目标文件、后缀不符…），
        走宿主的 ``status`` 通道说清楚；只有**控件自己**失败（对话框根本打不开，
        见 :meth:`_open_dialog`）才发 ``rejected``。
        """
        cleaned = [str(p) for p in (paths or []) if str(p or "").strip()]
        if not cleaned:
            return
        self.paths_chosen.emit(cleaned)

    def set_hot(self, hot: bool) -> None:
        """外部（宿主页面的整页拖拽）切换"正在拖入"高亮。"""
        if self._hot != bool(hot):
            self._hot = bool(hot)
            self.update()

    def clear(self) -> None:
        """清空当前源并发 ``cleared``（点右上角 ✕ 与宿主主动复位走同一条）。"""
        self.set_source(None)
        self.cleared.emit()

    def busy_lock(self, locked: bool) -> None:
        """执行中禁用（拖拽也不收），并保持当前画面。"""
        self.setEnabled(not locked)

    def set_solo_mode(self, solo: bool) -> None:
        """切**独占模式**：页面上再没有别的控件，本控件撑满整幅（空态）。

        由 :meth:`desktop.modules.base.ModulePage.show_workspace` 调用——
        用户 2026-10-03 要求「初始就只有一个输入框，下面的操作面板和预览
        这些都要选择输入文件后才显示出来」。分栏一收，页面上半屏是框、
        下半屏一片空白，看着像没加载完；独占模式把这个观感补回来。

        ⚠️ **已选态不参与**：源一旦选中就切回常规高度（``FILLED_HEIGHT``），
        因为那时分栏会回来，输入区要还给预览让出纵向空间。
        """
        self._solo = bool(solo)
        self._sync_height()
        self.setMinimumWidth(SOLO_MIN_WIDTH if self._solo else 260)
        self.update()

    # ------------------------------------------------------------ 拖 / 点 / 键
    @staticmethod
    def paths_from_mime(mime) -> list[str]:
        """从拖拽数据里取**本地**路径（URL 形式的文件/文件夹，非本地的丢掉）。

        单独抽成 staticmethod 是为了能直接单测——不用去合成 Qt 拖拽事件。
        """
        if mime is None or not mime.hasUrls():
            return []
        found: list[str] = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            local = url.toLocalFile()
            if local:
                found.append(local)
        return found

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """有东西拖上来：认得本地文件/文件夹就收，并亮起来。"""
        paths = self.paths_from_mime(event.mimeData())
        if not paths:
            event.ignore()
            return
        self.set_hot(True)
        event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """拖拽移动中：保持接受（Qt 要求显式接受才会给 drop）。"""
        if self.paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """拖出控件：熄灭高亮。"""
        self.set_hot(False)
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """松手放下：把原始路径交给宿主。"""
        paths = self.paths_from_mime(event.mimeData())
        self.set_hot(False)
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self.offer(paths)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """鼠标进来：底色淡一档（可点的暗示）。"""
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """鼠标离开：恢复底色。"""
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """回车/空格 = 点一下（键盘可达）。"""
        if event.key() in (
            Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space,
        ):
            self._browse_soon()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """点清空 = 清空；点已选态的 ✕ = 清空；点其余任何地方 = 换源（开对话框）。

        ⚠️ **已选态"点哪都能换源"是 2026-10-03 改回来的**（此前是"只有右上角那枚
        「更换」按钮能点"，因为担心用户只是想点空白让控件失焦）。改回来的理由是
        用户报「更换点了没反应」：那一枚按钮是**子控件**（见 :meth:`_build_buttons`），
        它能否收到点击取决于几何是否已随布局重排——一旦布局晚一步（懒构造的模块页
        正是如此），按钮画出来了却还不在正确位置，事件就落到了父控件上，而父控件
        那时又什么都不做 ⇒ 用户看到的就是"点了完全没反应"。

        把整条已选态都做成入口，就**不再依赖任何子控件的几何**：无论按钮在哪、
        是否被盖住，点这块区域都能换源。右上角 ✕ 优先（它更靠右、语义不同）。
        """
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if self._source is not None:
            if self._close_rect.contains(event.position()):
                self.clear()
            else:
                self._browse_soon()
            event.accept()
            return
        self._browse_soon()
        event.accept()

    def _browse_soon(self) -> None:
        """把"弹对话框"推迟到当前鼠标/键盘事件**返回之后**再执行。

        ⚠️ 别在 ``mousePressEvent`` 里直接 ``self.browse()``：选择对话框是**模态**的，
        压在**同一个尚未返回**的鼠标事件里，Windows 上会表现为"点了没反应"。

        ``QTimer.singleShot(0, ...)`` 让当前事件先返回、Qt 的鼠标抓取状态归位，
        下一轮事件循环再开对话框——这是"在控件事件里开模态"的标准做法。
        """
        QTimer.singleShot(0, self.browse)

    # ------------------------------------------------------------------ 选择
    def browse(self) -> None:
        """点空白处 / 按回车 = 直接开**选文件**对话框。

        ⚠️ 2026-10-03 用户要求「底部不设置选择图片或者目录的弹窗」：原先这里
        会先弹一个"选文件 / 选文件夹"的两选项小菜单（锚点就在控件**底部**，
        见旧的 ``_anchor_point``），用户点完小菜单**紧接着**才看到真正的选择
        界面——两层弹窗叠着，正对应用户说的"底部弹窗"。现在那一层整个去掉：
        点空白处直接进选择对话框。

        ⚠️ 只能默认"选文件"：``accepts_dir=True`` 的步骤想选目录有专门的
        「选择文件夹」按钮（那是显式入口），不必在这里再问一遍。
        """
        self._browse_kind(from_files=True)

    def _browse_kind(self, from_files: bool) -> None:
        """按"选文件 / 选文件夹"去选（按钮与 :meth:`browse` 共用）。

        推迟到事件返回之后再执行的原因见 :meth:`_browse_soon`。
        """
        QTimer.singleShot(0, lambda: self._open_dialog(from_files))

    def _open_dialog(self, from_files: bool) -> None:
        """开选择对话框；选完把原始路径经 :meth:`offer` 发出去。

        ⚠️ 用的是 :class:`QFileDialog` 的**原生**对话框（不设
        ``DontUseNativeDialog``），在 Windows 上它**就是资源管理器那套
        选文件/选文件夹界面** —— 这正是用户 2026-10-03 要的「调用资源浏览器
        选择文件或者目录」：一次调用、带"打开/取消"、点完直接拿到结果。

        ⚠️ **别再改成"弹一个资源管理器窗口 + 监听选中项"**（2026-10-03 用户
        明确否过：「不对，现在直接打开资源浏览器了，而不是调用资源浏览器
        选择文件或者目录」）。那是**浏览**窗口，不是**选择**对话框：用户还得
        自己双击文件夹去定位，程序只能靠轮询猜他点了谁。

        ⚠️ **整段包 try/except，并经 ``rejected`` 把话说出来**：本方法是被
        ``QTimer.singleShot`` 调的，Qt 会把回调里的异常吞掉（只往 stderr 打印），
        界面上一声不响——用户看到的就是"点了更换，什么都没发生"，而且**没有
        任何可查的错误线索**。这里兜住并转成用户能读的一句话。
        """
        try:
            self._pick(from_files)
        except Exception as exc:  # noqa: BLE001 - 模态框失败要说给用户听
            self.rejected.emit(f"打不开选择对话框：{exc}")

    def _pick(self, from_files: bool) -> None:
        """真正弹选择对话框（异常由 :meth:`_open_dialog` 兜）。"""
        # ⚠️ 起始目录**不能传空串**：QFileDialog 空串会回退到进程工作目录
        #    （打包后就是程序所在目录 / 可能只读），入口很别扭。走项目既有约定
        #    `desktop.utils.files.default_open_dir()`（文档目录起步）。
        start = str(default_open_dir())
        if from_files:
            if self.spec.allow_multi:
                paths, _ = QFileDialog.getOpenFileNames(
                    self.window(), self.spec.pick_label, start, self.spec.file_filter
                )
            else:
                one, _ = QFileDialog.getOpenFileName(
                    self.window(), self.spec.pick_label, start, self.spec.file_filter
                )
                paths = [one] if one else []
        else:
            directory = QFileDialog.getExistingDirectory(
                self.window(), "选择文件夹", start
            )
            paths = [directory] if directory else []
        self.offer(paths)

    # ------------------------------------------------------------------ 绘制
    def _sync_height(self) -> None:
        """空态/已选态用两个固定高度，切换时重排一次父布局。

        独占模式（``set_solo_mode``）只在**空态**生效：此时页面上只有本控件，
        撑到 :data:`SOLO_HEIGHT`；已选态一律回 ``FILLED_HEIGHT``，把纵向空间
        让给分栏（那时分栏是显示着的）。

        ⚠️ 独占模式用 **setMinimumHeight + 拉伸策略**而不是 ``setFixedHeight``：
        固定高会把控件钉在 320px，多余的空间被 Qt 摊给**页头**（实测副标题
        飘到页面中间、输入框被挤到底边）。给一个"最小 320 + 可拉伸"，
        空出来的地方就落在输入框自己身上——这才是"整幅只有一个输入框"。
        """
        expanding = self._source is None and self._solo
        if expanding:
            self.setMinimumHeight(SOLO_HEIGHT)
            # ⚠️ 必须**同时**放开 maximumHeight：曾经 setFixedHeight(320) 把它
            #    钉在 320，只改 minimumHeight 不改上限的话控件仍然长不大
            #    （实测：整页只有一条 320px 的框，上下各留一片空白）。
            self.setMaximumHeight(HEIGHT_UNLIMITED)
            self.setSizePolicy(
                self.sizePolicy().horizontalPolicy(),
                QSizePolicy.Policy.Expanding,
            )
        else:
            self.setMinimumHeight(0)
            self.setSizePolicy(
                self.sizePolicy().horizontalPolicy(),
                QSizePolicy.Policy.Fixed,
            )
            self.setFixedHeight(
                EMPTY_HEIGHT if self._source is None else FILLED_HEIGHT
            )
        self._relayout_buttons()
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """尺寸变了：按钮行跟着重新居中。"""
        super().resizeEvent(event)
        self._relayout_buttons()

    def _font(self, size: int, bold: bool = False) -> QFont:
        """按设计令牌造字体（不引样式表，与自绘控件保持一致）。"""
        font = QFont(self.font())
        font.setPixelSize(size)
        font.setBold(bold)
        return font

    @staticmethod
    def _elide(painter: QPainter, text: str, width: float) -> str:
        """按可用宽度做省略号截断（路径很长时不要撑破虚框）。"""
        metrics = QFontMetrics(painter.font())
        return metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, int(width))

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """画底（圆角虚线框）+ 内容（空态两行 / 已选态一行）。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)

        # ⚠️ 高亮只认 `_hot`（有东西正拖在上面），**不认 hasFocus()**：输入区是
        #    页面里第一个可聚焦控件，启动时往往就持有焦点——按焦点上色的话，
        #    每个模块页一进来就是"已激活"的样子，看不出"可以拖进来"这件事。
        lit = self._hot
        if self._hot:
            fill = T.ACCENT_SOFT
        elif self._hover:
            fill = T.SURFACE_HOVER
        else:
            fill = T.SURFACE_SOFT
        painter.setBrush(QColor(fill))
        pen = QPen(QColor(T.ACCENT if lit else T.BORDER_STRONG), 1.5)
        pen.setStyle(Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([4, 3])
        painter.setPen(pen)
        painter.drawRoundedRect(rect, T.RADIUS_MD, T.RADIUS_MD)

        if self._source is None:
            self._paint_empty(painter, rect)
        else:
            self._paint_filled(painter, rect)
        painter.end()

    def _paint_empty(self, painter: QPainter, rect: QRectF) -> None:
        """空态：图标 + 标题 + 提示，作为**一整块垂直居中**。

        ⚠️ 按钮行是**子控件**（``PushButton``，要 hover/按下/焦点态），父类
        自绘不能压到它身上。所以"整块居中"由 :meth:`_empty_block_top` 统一
        算：自绘三段用它，按钮行由 :meth:`_relayout_buttons` 摆在文案下方，
        两边共用同一个基准 ⇒ 文案与按钮永远贴在一起、一起居中。

        ⚠️ 独占模式下控件高达 700px+，若文案贴顶、按钮钉在框底，中间就是一大
        片空白，看起来像两个不相干的区域（用户 2026-10-03 截图反馈）。所以整
        块（文案 + 按钮）作为一个整体居中。
        """
        rect = self._content_rect(rect)
        top = self._empty_block_top(rect)
        icon_rect = QRectF(
            rect.center().x() - ICON_BOX / 2, top, ICON_BOX, ICON_BOX,
        )
        self._icon().render(painter, icon_rect, Theme.LIGHT)

        painter.setFont(self._font(T.SIZE_LABEL, bold=True))
        painter.setPen(QColor(T.ACCENT if self._hot else T.INK))
        title_rect = QRectF(
            rect.left() + PAD, icon_rect.bottom() + T.SPACE_SM,
            rect.width() - 2 * PAD, 22,
        )
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            self._elide(painter, self.spec.drop_title_text(), title_rect.width()),
        )

        painter.setFont(self._font(T.SIZE_CAPTION))
        painter.setPen(QColor(T.ACCENT if self._hot else T.INK_FAINT))
        hint_rect = QRectF(
            rect.left() + PAD, title_rect.bottom() + 2,
            rect.width() - 2 * PAD, 18,
        )
        painter.drawText(
            hint_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            self._elide(painter, self.spec.drop_hint_text(), hint_rect.width()),
        )

    @staticmethod
    def _empty_block_height() -> float:
        """空态**整块**（自绘三段 + 按钮行）的自然高度（px）。

        ⚠️ 把按钮算进来，居中才是"整块居中"而不是"文案居中、按钮掉队"。
        """
        return ICON_BOX + T.SPACE_SM + 22 + 2 + 18 + BUTTON_GAP + BUTTON_HEIGHT

    def _empty_block_top(self, rect: QRectF | None = None) -> float:
        """空态整块的顶边 Y（在可用区里垂直居中；高度不够时退化为贴顶）。"""
        if rect is None:
            rect = self._content_rect(
                QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
            )
        slack = max(0.0, rect.height() - self._empty_block_height())
        return rect.top() + slack / 2.0

    def _empty_block_bottom(self) -> float:
        """空态**自绘**部分的底边 Y（按钮行顶边 = 它 + ``BUTTON_GAP``）。"""
        return self._empty_block_top() + self._empty_block_height() - BUTTON_GAP - BUTTON_HEIGHT

    def _content_rect(self, rect: QRectF) -> QRectF:
        """自绘内容可用区：空态留出上下各一点余量，已选态就是整块。

        ⚠️ 空态**不再**扣掉底部按钮行——按钮已改成紧跟文案（见
        :meth:`_empty_block_top`），整块一起居中，所以这里只需要给整块
        一点上下呼吸空间。
        """
        if self._source is not None:
            return rect
        pad = T.SPACE_MD
        return QRectF(
            rect.left(), rect.top() + pad, rect.width(),
            max(40.0, rect.height() - 2 * pad),
        )

    def _paint_filled(self, painter: QPainter, rect: QRectF) -> None:
        """已选态：图标 + 名字 + 路径 + 右侧「更换」与清空 ✕。"""
        icon_rect = QRectF(
            rect.left() + PAD, rect.center().y() - ICON_BOX / 2 * 0.8,
            ICON_BOX * 0.8, ICON_BOX * 0.8,
        )
        self._icon().render(painter, icon_rect, Theme.LIGHT)

        text_left = icon_rect.right() + T.SPACE_MD
        # 右侧要给「更换」按钮（真实控件，不知道文案多宽）与清空 ✕ 各留一份
        swap_w = self._swap_button.width() + T.SPACE_MD
        text_width = rect.right() - CLOSE_BOX - swap_w - T.SPACE_MD - text_left
        if text_width < 40:
            return

        painter.setFont(self._font(T.SIZE_LABEL, bold=True))
        painter.setPen(QColor(T.INK))
        name = self._source.name or str(self._source)
        painter.drawText(
            QRectF(text_left, rect.top() + T.SPACE_LG, text_width, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._elide(painter, name, text_width),
        )

        painter.setFont(self._font(T.SIZE_CAPTION))
        painter.setPen(QColor(T.INK_FAINT))
        painter.drawText(
            QRectF(text_left, rect.top() + T.SPACE_LG + 20, text_width, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._elide(painter, self._detail or str(self._source), text_width),
        )

        self._close_rect = QRectF(
            rect.right() - CLOSE_BOX - T.SPACE_SM,
            rect.center().y() - CLOSE_BOX / 2,
            CLOSE_BOX, CLOSE_BOX,
        )
        FIF.CLOSE.render(painter, self._close_rect, Theme.LIGHT)

    def _icon(self):
        """步骤声明的大图标（``StepSpec.drop_icon``，未知名字回退到文件夹）。

        经 ``resolve_nav_icon`` 解析而不是 ``getattr(FIF, ...)``：拖放区要和
        导航一样能用 ``svg:`` 前缀的自绘图（内置图标里没有 PDF，空文档的
        ``DOCUMENT`` 会被读成"文档"而不是 PDF）。未知名字仍回退文件夹。
        """
        from desktop.ui.icons import resolve_nav_icon
        from qfluentwidgets import FluentIcon as FIF

        try:
            return resolve_nav_icon(self.spec.drop_icon)
        except AttributeError:
            return FIF.FOLDER_ADD

    # ------------------------------------------------------------------ 文案
    def _hint_text(self) -> str:
        """tooltip：空态给完整说明，已选态给完整路径（名字被截断时能看全）。"""
        if self._source is None:
            return f"{self.spec.drop_title_text()}\n{self.spec.drop_hint_text()}"
        return str(self._source)

    def _auto_detail(self, source: Path | None) -> str:
        """已选态第二行小字（宿主没给 ``detail`` 时的兜底）。

        - 文件夹 → ``完整路径 · N 个可用文件``（N 按本步骤的后缀数）；
        - 文件 → 它所在的目录。
        """
        if source is None:
            return ""
        if source.is_dir():
            count = len(self.spec.listing(source))
            return f"{source} · {count} 个可用文件"
        return str(source.parent)


__all__ = [
    "BUTTON_HEIGHT",
    "EMPTY_HEIGHT",
    "FILLED_HEIGHT",
    "SourceZone",
]
