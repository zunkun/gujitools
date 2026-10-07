# -*- coding: utf-8 -*-
"""**创建任务**二级页面（用户 2026-10-06：不再弹窗，改成进入页面）。

## 为什么要改成页面

原来是 :class:`~desktop.components.create_task_dialog.CreateTaskDialog`
——一个**模态弹窗**。用户在同一轮里连着提了三件事：改页面、流程编辑别再
弹第二层、详情页也能随时编辑流程。既然「创建任务」已经是一级动作，就该给
它一个**页面**，而不是一个盖在列表上的对话框（弹窗有三个老毛病：盖住下面
的列表、关不掉、里面再套一层）。

## 页面长什么样

页面**沿用面板原样**（同一套控件与顺序，用户的"页面跟现在的一样"），只多
一行「任务名称」：

::

    [← 创建任务]
    任务名称  [ 一本古籍            ]  ← 最多 360px，placeholder＝任务#0007
    留空则使用默认名「任务#0007」；PDF 可以之后在任务详情里补选。
    ┌ CreateTaskPanel ────────────────────────┐
    │ ☑ 使用自定义任务流程                     │
    │ …                                        │
    │ [取消]                     [创建任务]    │  ← 面板自带按钮
    └─────────────────────────────────────────┘

「编辑流程」**就地**展开在本页里（:class:`CreateTaskPanel` 内嵌
``FlowPanel``），不再弹第二层——见该面板的 ``_on_edit_flow``。

## 任务名称（用户 2026-10-06）

**非必需、可随时修改**，回落是**两级**：

- 用户填了 ⇒ 用填的；
- 留空 ＋ 选了 PDF ⇒ 用**文件名**（选完 PDF 还会自动填进框里，省一次输入）；
- 留空 ＋ 没选 PDF ⇒ 用默认名「**任务#XXXX**」，XXXX 是任务序号。

⚠️ 默认名里的序号在**落库那一刻**由 ``TaskStore.create_task`` 用**实际分配
到的**任务号现算（``store.default_task_name()`` 给的只是占位提示）——占号是
原子的、可能被顺延，用预测值会让「任务#0008」落在 0009 号任务上。

建完任务后在**详情页页头**也能随时改名（``store.rename_task``，空名同样走
上面那两级回落）。

## PDF 非必需（用户 2026-10-06）

「PDF 输入不是必须的」「创建任务按钮不必等上传 pdf 才可以点」——所以：

- :meth:`CreateTaskPanel.can_submit` **恒为 True**，按钮不因"还没挑文件"而灰；
- 没选 PDF 时第一个参数传空串，列表页建一个**空壳任务**（``source_path``
  存空串），详情页显示「尚未选择 PDF」并提供补选入口
  （``store.set_task_source``）——**不是**弹「PDF 缺失」错误框，那是"文件
  丢了"，与"还没选"是两回事。

## 它不做什么

不负责指纹计算、查重确认、预热详情页——那些都在任务列表页的既有链路里
（``_start_import``）。本页只**收集输入**并把结果 emit 出去，由列表页走
原来的流程（逻辑一字未改），建完直接 ``open_detail`` 进详情。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon as FIF, LineEdit, MessageBox,
    StrongBodyLabel, ToolButton,
)

from desktop import ui
from desktop.components.create_task_dialog import CreateTaskPanel
from desktop.ui import theme as T
from desktop.ui.widgets import CONTROL_HEIGHT

#: 路由键（在 :class:`desktop.shell.ModuleShell` 里反查用）
ROUTE_CREATE = "create"

#: 「任务名称」输入框的**上限宽度**（px）。
#:
#: ⚠️ 用户 2026-10-06 报"长度占满几乎整个屏幕太长"：原来这一行是
#:    ``addWidget(self.name_edit, 1)``，在 1920 宽的窗口上被拉到 ~1800px，
#:    一个撑满整行的输入框既难看又让人以为"这行字会跑出去"。任务名实际
#:    都是几个字，给个够用���上限 + 右侧留白，视觉上才像"一个字段"而不是
#:    "一条横幅"。
NAME_EDIT_MAX_WIDTH = 360


class CreateTaskPage(QWidget):
    """创建任务页：选 PDF + 任务名称 + 看/编流程 → 交给列表页建任务。"""

    #: 用户填完了，可以建任务：(pdf 路径, 任务名, 流程图 or None, 是否自定义)
    create_requested = Signal(str, str, object, bool)
    #: 用户点了「取消」/「返回」，宿主切回列表
    closed = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._busy = False
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(
            T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG
        )
        root.setSpacing(T.SPACE_MD)

        # ---- 返回：回任务管理（与详情页的返回一致，用户 2026-09-30 定的操作）----
        top = QHBoxLayout()
        top.setSpacing(T.SPACE_SM)
        self.back_button = ToolButton(FIF.RETURN)
        self.back_button.setToolTip("返回任务管理")
        self.back_button.setFixedSize(34, 34)
        self.back_button.clicked.connect(self._on_back)
        top.addWidget(self.back_button)
        top.addWidget(StrongBodyLabel("创建任务"))
        top.addStretch()
        root.addLayout(top)

        # ---- 任务名称（非必需；留空回落）----
        name_row = QHBoxLayout()
        name_row.setSpacing(T.SPACE_SM)
        label = BodyLabel("任务名称：")
        ui.apply_to(label, T.SIZE_BODY, color=T.INK)
        name_row.addWidget(label)
        # ⚠️ 用 qfluentwidgets 的 ``LineEdit`` 而不是裸 ``QLineEdit``（用户
        #    2026-10-06："输入框不好看，而且高度不够"）：裸的那个在 Windows
        #    上是 21px 高的原生编辑框，和同页 33px 的按钮并排明显矮一截，
        #    边框还是系统灰。``LineEdit`` 自带 33px（= ``CONTROL_HEIGHT``，
        #    见 desktop/ui/widgets.py）与项目其余表单一致。
        self.name_edit = LineEdit()
        self.name_edit.setFixedHeight(CONTROL_HEIGHT)
        self.name_edit.setMaximumWidth(NAME_EDIT_MAX_WIDTH)
        self.name_edit.setPlaceholderText(self.default_name())
        self.name_edit.setClearButtonEnabled(True)
        self.name_edit.textChanged.connect(self._refresh_hint)
        name_row.addWidget(self.name_edit)
        # ⚠️ 右侧留白：不加 stretch 的话输入框会顶着 hint 标签；加了之后
        #    标签紧跟输入框右缘，字段感才成立。
        name_row.addStretch()
        root.addLayout(name_row)

        # 选 PDF 之后才更新（"留空就用哪个文件名"得说清，否则用户不知道留空的后果）
        self.name_hint = CaptionLabel("可留空；不选 PDF 也能先建任务。")
        ui.apply_to(self.name_hint, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.name_hint.setWordWrap(True)
        root.addWidget(self.name_hint)

        # ---- 面板原样搬过来（自带标题、流程图、按钮行）----
        # ⚠️ outer_margins=False：页面根布局已有 SPACE_XL 边距，面板再 pad
        #    一层会让「创建任务」标题比上面的「任务名称」多缩进 24px
        #    （用户 2026-10-06 截图反馈的对齐问题）。
        self.panel = CreateTaskPanel(self, outer_margins=False)
        self.panel.submitted.connect(self._on_submit)
        self.panel.cancelled.connect(self._on_back)
        # ⚠️ 清掉 PDF 时，**任务名里那个自动填的文件名也要回退**（否则留下一个
        #    指向已清掉文件的名字，用户看着以为文件还在）。见 _on_pdf_cleared。
        self.panel.pdf_cleared.connect(self._on_pdf_cleared)
        # 选了 PDF 就自动填上文件名（可随时改；清空则回落文件名，见模块头）
        self.panel.pick_button.clicked.connect(self._autofill_name)
        root.addWidget(self.panel, 1)

    # ------------------------------------------------------------- 名称联动
    def _on_pdf_cleared(self, previous) -> None:
        """面板清掉了已选 PDF ⇒ 任务名若是**它自动填的文件名**就一起回退。

        ⚠️ 只在"名字仍等于那个 stem"时才清：用户自己改过的名字（"永乐大典
        上册"）跟文件没关系，替他清掉就是**丢用户输入**。
        """
        stem = Path(str(previous or "")).stem
        if stem and self.name_edit.text().strip() == stem:
            self.name_edit.clear()
        self._refresh_hint()

    def _autofill_name(self) -> None:
        """选了 PDF 之后：把文件名填进「任务名称」（不覆盖用户已填的内容）。

        ⚠️ 判据是"输入框为空"，不是"内容等于默认名"：placeholder 只是灰字
        提示，``text()`` 拿不到它，所以空框在两种情况下都是空——用户没动过
        （该填文件名）与用户主动清空（想用默认名）都归到这里。
        """
        path = self.panel.selected_pdf()
        if path is None:
            return
        if not self.name_edit.text().strip():
            self.name_edit.setText(path.stem)
        self._refresh_hint()

    def _refresh_hint(self, *_args) -> None:
        """提示行：说清"留空会用什么名字"（否则用户不知道留空会怎样）。

        两种回落（用户 2026-10-06）：有 PDF ⇒ 用**文件名**；没 PDF ⇒ 用
        ``任务#XXXX``。所以提示必须跟着"选了没选"变。
        """
        path = self.panel.selected_pdf()
        typed = self.name_edit.text().strip()
        if typed:
            self.name_hint.setText(f"任务名将使用「{typed}」。")
        elif path is not None:
            self.name_hint.setText(
                f"留空则使用 PDF 文件名「{path.stem}」。")
        else:
            self.name_hint.setText(
                f"留空则使用默认名「{self.default_name()}」；"
                "PDF 可以之后在任务详情里补选。")

    def default_name(self) -> str:
        """默认任务名「任务#XXXX」（XXXX = 预测的下一个任务号）。

        ⚠️ 只是**占位提示**：真正落库时 ``TaskStore.create_task`` 会用
        **实际分配到的**任务号重算（占号可能顺延，见该方法说明）。所以这
        里只用于 placeholder 与提示文案。
        """
        try:
            return self.store.default_task_name()
        except Exception:  # noqa: BLE001 - 纯提示文案，取不到就退回裸格式
            return "任务#XXXX"

    def task_name(self) -> str:
        """本页收集到的任务名（**可能为空**＝调用方按默认口径回落）。"""
        return self.name_edit.text().strip()

    def set_name(self, name: str) -> None:
        """回填任务名（快路径/测试用）。"""
        self.name_edit.setText(str(name or ""))

    def reset(self) -> None:
        """回到**刚打开**的样子（用户 2026-10-06：上一次创建任务信息没清理）。

        面板那份（已选 PDF / 勾选 / 自定义流程图 / 开着的编辑器）由
        :meth:`CreateTaskPanel.reset` 清；这里清本页自己的两样：

        - **任务名输入框**（截图里留着的正是它）；
        - ``_busy`` 与控件禁用态——上一次建任务途中点「返回」会留下永久
          灰着的控件（``set_busy(True)`` 没被复原），之后这页就半残了。

        ⚠️ 默认名占位文字**要重算**：刚才那次创建已经占掉一个任务号，
        placeholder 还写着旧的「任务#0007」就是错的（用户会以为下一个任务叫
        那个号）。
        """
        self.name_edit.setText("")
        self.panel.reset()
        self._busy = False
        self.panel.setEnabled(True)
        self.name_edit.setEnabled(True)
        self.back_button.setEnabled(True)
        self.name_edit.setPlaceholderText(self.default_name())
        self._refresh_hint()

    # ------------------------------------------------------------- 状态与提交
    def set_busy(self, busy: bool, message: str = "") -> None:
        """建任务进行中：锁住输入并说明在等什么。

        ⚠️ 指纹计算与查重确认都发生在**列表页**的链路里（`_start_import`），
        所以这里只能"锁住 + 说清在等"，真正的进度条不在本页。
        """
        self._busy = bool(busy)
        self.panel.setEnabled(not busy)
        self.name_edit.setEnabled(not busy)
        self.back_button.setEnabled(not busy)
        if message:
            self.name_hint.setText(message)
        elif not busy:
            self._refresh_hint()

    def _on_back(self, *_args) -> None:
        if self._busy:
            return          # 正在建任务时不许走（半路放弃会留下悬空状态）
        self.closed.emit()

    def _on_submit(self, *_args) -> None:
        """面板说"可以创建了" → 可能先问一句，再把输入交出去。

        ⚠️ **PDF 可以不给**（用户 2026-10-06：「PDF 输入不是必须的」＋
        「创建任务按钮不必等上传 pdf 才可以点」）：没有 PDF 时第一个参数传
        空串，由列表页建一个"空壳任务"（见 ``TaskListPage.start_create``）。

        ⚠️ 但**流程里要源 PDF、用户却没选**时先问一句（用户 2026-10-06第2 条：
        「创建任务的时候检测流程中有源 PDF，但是用户没有上传 PDF 文件，此时
        提醒用户确认，用户可以上传 PDF，也可以不上传」）。不是拦住不让建——两条
        路都合法：现在补一个文件，或者先建空壳、之后在详情页页头补选。
        """
        if self._busy:
            return
        if self.panel.selected_pdf() is None and self._flow_needs_source_pdf():
            if not self._confirm_without_pdf():
                return          # 用户想在确认框里补选文件（它会替我们提交）
            #落到这里 = 用户选择"先不传"，按空壳任务建
        self._emit_create()

    def _emit_create(self) -> None:
        """把当前输入交出去（真正发信号的那一步）。"""
        path = self.panel.selected_pdf()
        self.create_requested.emit(
            str(path) if path is not None else "",
            self.task_name(),
            self.panel.result_diagram(), self.panel.uses_custom_flow(),
        )

    def _flow_needs_source_pdf(self) -> bool:
        """**当前这条流程**里有没有直接吃源 PDF 的阶段吗（要问图，别写死）。

        ⚠️ 判据是流程图**当前显示的那张**（默认或自定义，跟着
        ``current_diagram`` 走）：用户自定义流程可能把「提取图片」删了，
        那整条流程就不碰源 PDF，不该问他要文件。

        真正的判据在 :func:`desktop.steps.ports.flow_needs_source_pdf`——
        **与详情页共用同一份**（两处问的是同一个问题，各写一份必然漂移成
        "创建时问了、详情页却不提示"）。
        """
        from desktop.steps.ports import flow_needs_source_pdf

        return flow_needs_source_pdf(self.panel.current_diagram())

    def _confirm_without_pdf(self) -> bool:
        """问一句"要不要现在补个PDF"；``True`` = 继续建空壳，``False`` = 已处理。

        ⚠️ 判据与弹窗**分开**（``_should_ask_missing_pdf``）——离屏自测
        绝不真弹模态（项目硬规则），自测把判据替掉就能验两条分支。

        用户答"要"⇒ 顺手把选择对话框开出来；他在那儿选了文件就直接提交
        （**本方法不发信号**，由 :meth:`_on_pick_source_then_submit` 发），
        这样"补一个文件"不用再点一次「创建任务」。
        """
        if not self._should_ask_missing_pdf():
            return True
        dialog = MessageBox(
            "流程需要一个 PDF 源文件",
            "当前流程里有「提取图片」这一步，它需要一个 PDF 源文件。\n\n"
            "· 现在就选一个 → 任务建好后直接进详情页即可开始处理；\n"
            "· 先不选 → 任务照样能建，只是暂时不能执行，"
            "之后在任务详情页右上角可以随时补选。",
            self,
        )
        dialog.yesButton.setText("现在选择")
        dialog.cancelButton.setText("先不传")
        if dialog.exec():
            self._pick_source_then_submit()
            return False
        return True

    def _should_ask_missing_pdf(self) -> bool:
        """该问吗（True = 需要问）。

        已经选了文件就不问；流程里压根没有要源 PDF 的步骤也不问（那种任务
        不需要源文件，问了是白问）。
        """
        if self.panel.selected_pdf() is not None:
            return False
        return self._flow_needs_source_pdf()

    def _pick_source_then_submit(self) -> None:
        """在确认框里答了"现在选择" → 开选择框，选中即直接建任务。

        选了但又取消（``selected_pdf`` 仍为 ``None``）时**不发信号**：用户
        明明表示"不传"，不能替他建一个空壳出来。
        """
        # ⚠️ 直接调面板的选文件动作，不要走 ``pick_button.click()``：后者会
        #    连带触发本页挂在它上面的 ``_autofill_name``，而这里自己再调一次
        #    就成了填两遍（第二遍因输入框已非空而无害，但依赖那个"无害"很脆）。
        self.panel._on_pick_pdf()
        if self.panel.selected_pdf() is None:
            return
        self._autofill_name()
        self._emit_create()


__all__ = ["CreateTaskPage", "ROUTE_CREATE"]
