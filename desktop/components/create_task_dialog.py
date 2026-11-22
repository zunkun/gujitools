# -*- coding: utf-8 -*-
"""**创建任务弹窗**（``docs/tasks/bpm.md`` 的 M3）。

用户 2026-10-05 的要求（原文，历史记录）：

> 任务列表中 导入PDF 改成 "创建任务"，出现弹窗
>
> - 默认任务流程/自定义任务流程 checkbox 组件
> - 自定义任务流程下面有任务流程bpmn 节点渲染，默认是 task_default.bpmn 的
>   节点渲染（自定义初值即默认模板），同时提供按钮 "编辑流程" 点击调用 bpmn 自定义面板……

## 2026-11-17 两轮改造（均出自用户当日反馈）

第一轮：撤「使用自定义任务流程」复选框——默认流程本身就可编辑。

第二轮（本轮）：**编辑器直接常驻**——

> 默认就直接展示流程编辑功能，不再通过点击 "编辑流程" 触发

面板内容区从此就是 :class:`~desktop.components.bpmn_editor_panel.BpmnEditorPanel`
（工具栏 + 画布 + 「恢复默认」），打开页面即可拖节点/连线/改名；
「编辑流程」按钮与只读预览图（``BpmnView``）整体退役：

::

    选择 PDF   [选择文件…]  已选择：xxx.pdf     ← 流程不吃源文件时**整行隐藏**
    说明文字（随是否编辑过变化，含步骤串——"当前流程"由它承担）
    ┌ BpmnEditorPanel（工具栏 + 画布 + 恢复默认）┐   ← 恒在、恒可编辑
    └────────────────────────────────┘
    共 5 步：提取图片 → …（摘要随编辑实时刷新）
    ────────────────────────────
    [取消]  [创建任务]

（选文件行在上、说明行紧贴编辑器——用户 2026-11-17 截图要求两行对调。）

落不落自定义图仍由 :attr:`_flow_edited` 判：**编辑器内容变过**（收到
``diagram_changed``）才算自定义（``result_diagram()`` 传图落盘）；没动过返回
``None``，store 走**字节拷贝**默认模板。点编辑器工具栏的「恢复默认」清掉
标记，回到字节拷贝语义。

⚠️ **合法性校验挪到点「创建任务」时**（原来在编辑器的「保存流程」里，
而那个按钮已随常驻编辑器一起退役）：:func:`desktop.steps.validate.validate_flow`
报硬错误就 toast 并挡下本次提交；警告只提示不拦。未编辑过（默认模板）
不校验——那份文件本来就是好的。

三层结构（每层只干一件事）：

- :class:`CreateTaskPanel` —— 弹窗内容；
- :class:`CreateTaskDialog` —— 把它装进外壳的薄壳；
- :mod:`desktop.pages.tasklist.page` —— 拿到结果后走原有的指纹查重 → 建任务
  → 预热详情页链路（**不重复实现导入逻辑**）。

⚠️ **没编辑过不传图**（:meth:`CreateTaskPanel.result_diagram` 返回 ``None``）：
默认流程 = ``desktop/static/task_default.bpmn`` 这份文件，由 store **原样字节
拷贝**进任务目录。过一次 ``FlowDiagram.to_xml`` 会把它重新序列化，而
``FlowDiagram`` 不建模连线上的端口标记（``guji:port``）——那会把信息抹掉。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon as FIF,
    PrimaryPushButton,
    PushButton,
    ToolButton,
)

from desktop import ui
from desktop.components.dialog_shell import shell_dialog
from desktop.steps.bpmn_diagram import FlowDiagram
from desktop.ui import theme as T
from desktop.utils.files import default_open_dir

#: 弹窗标题
DIALOG_TITLE = "创建任务"
#: 默认模式的提示**前半句**；后半句（哪几步）由**文件内容**生成，见
#: :func:`default_hint`。
#:
#: ⚠️ 为什么拆开：以前这里手写死了"提取图片 → 检测文本框 → 图片去底色 →
#: PDF排版"，与 ``task_default.bpmn`` 实际内容**各说各话**（用户 2026-10-05
#: 明确指出："默认流程必须跟 task_default.bpmn 一样……不要你自己设计默认流程"）。
#: 现在步骤串一律从文件读，写错的可能性被结构性消除。
DEFAULT_HINT_PREFIX = "使用默认任务流程（下方编辑器可直接改）："
CUSTOM_HINT = "使用自定义任务流程（已修改，下方编辑器可继续调整）："
#: **没选** PDF 时那一行的提示（唯一来源，:meth:`CreateTaskPanel.clear_pdf` 也用）
EMPTY_PDF_HINT = "可留空，之后在任务详情里补选"
#: 「已选择：xxx.pdf」那行文字的宽度上限（px）。封顶是为了长书名不会把后面的
#: 「清除」按钮顶出窗口——而那按钮恰是选错文件时最需要够到的。
PDF_STATE_MAX_WIDTH = 420


def default_hint(diagram: FlowDiagram) -> str:
    """默认模式的完整提示：前缀 + **文件里真实的**步骤串。"""
    from desktop.components.flow_dialog import summarize

    return DEFAULT_HINT_PREFIX + summarize(diagram)


def load_custom_init() -> FlowDiagram:
    """编辑器的初值（整张图）——即默认模板那份图。

    ⚠️ 历史别名：以前初值是独立的 ``desktop/static/task_detail.bpmn``，
    2026-10-08 起只保留 ``task_default.bpmn``，自定义就是"从默认流程开始改"。
    保留本函数只是为了兼容既有调用方（自测/截图脚本），新代码请直接用
    :func:`desktop.steps.scheduler.load_default_diagram`。

    模板缺失/损坏时返回空图（不抛）：调用方不必处理异常。
    """
    from desktop.steps.scheduler import load_default_diagram

    fallback = load_default_diagram()
    return fallback if fallback.nodes else FlowDiagram()


class CreateTaskPanel(QWidget):
    """创建任务弹窗的**内容**（不含 Dialog 外壳，便于自测直接实例化）。

    对外只认三件事：:meth:`selected_pdf`（选了哪个 PDF）、
    :meth:`result_diagram`（用哪份流程图建任务）、:meth:`uses_custom_flow`
    （流程是否编辑过）。任务列表页拿这三样走原有的建任务链路。

    ⚠️ 流程**编辑器恒在**（用户 2026-11-17：默认直接展示编辑功能，不再点
    「编辑流程」触发）——编辑走 :attr:`editor_panel`，改动实时生效。
    """

    #: 用户点了「创建任务」且条件齐备（已选 PDF）
    submitted = Signal()
    #: 用户点了「取消」/ 返回。⚠️ **面板自己不关窗**——它可能被内嵌进页面，
    #: 那时 ``self.window()`` 就是那一页，关掉等于把整页关没（用户 2026-10-06
    #: 改成二级页面后才暴露）。一律由宿主听这个信号决定去哪儿。
    cancelled = Signal()
    #: 已选 PDF 被清掉了（带被清掉的路径）。⚠️ ``reset()`` 也会发它——那是
    #: "该清的都要清"，创建页的槽对两种情况一视同仁，所以不必区分。
    pdf_cleared = Signal(object)

    def __init__(
        self,
        parent=None,
        flow: FlowDiagram | None = None,
        *,
        outer_margins: bool = True,
    ):
        """``outer_margins``：要不要自带外层留白（默认带，弹窗形态需要）。

        ⚠️ 内嵌进**创建任务页**时传 ``False``：页面根布局已有
        ``SPACE_XL`` 边距，面板再 pad 一层就成了"任务名称顶格、创建任务
        多缩进 24px"的双层缩进（用户 2026-10-06 截图确认）。与
        ``ImpositionPanel(enable_switch=…)`` 同一条纪律——宿主专属的布局
        差异用构造参数声明，组件不猜自己在哪。

        ``flow``：编辑器的初值（缺省 = 默认模板）。调用方显式给了就视为
        "用户带来的自定义图"（要落盘）。
        """
        super().__init__(parent)
        self._init_flow = flow
        # ⚠️ 复选框已撤（用户 2026-11-17）：单一模式，流程恒从默认模板起步、
        # 恒可编辑。落不落自定义图改由这个标记判：**编辑器内容变过**才算
        # 自定义（见 result_diagram）。
        self._flow_edited = flow is not None
        # 默认流程 = 默认模板文件那份图（**只用于提示文案**；建任务时未编辑
        # 走字节拷贝）
        self._default_diagram = self._load_default_diagram()
        self._pdf: Path | None = None
        self._editor_panel = None
        self._outer_margins = bool(outer_margins)
        self._build_ui()
        self._refresh_mode()

    @staticmethod
    def _load_default_diagram() -> FlowDiagram:
        from desktop.steps.scheduler import load_default_diagram

        diagram = load_default_diagram()
        return diagram if diagram.nodes else FlowDiagram()

    @property
    def _custom_diagram(self) -> FlowDiagram:
        """当前流程图（编辑器手里那张；编辑器还没建时是初值/默认模板）。

        ⚠️ **只读别名**（自测与旧调用方读它）；要**换图**走
        :meth:`set_custom_diagram`——编辑器拿到的是传入图的**副本**，
        外面那张毫发无损。
        """
        if self._editor_panel is not None:
            return self._editor_panel.diagram()
        return self._init_flow or self._default_diagram

    @property
    def editor_panel(self):
        """内嵌的常驻编辑器（:class:`BpmnEditorPanel`；``reset()`` 重建后换新实例）。"""
        return self._editor_panel

    @property
    def reset_button(self):
        """「恢复默认」按钮（编辑器工具栏那颗；兼容旧调用方/自测的入口）。

        ⚠️ 没有了面板级的「编辑流程」按钮：编辑器恒在，无需入口。
        """
        return getattr(self._editor_panel, "reset_button", None)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        if self._outer_margins:
            layout.setContentsMargins(T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG)
        else:
            # 页面宿主已给外层边距，这里全归零（见 __init__ 说明）
            layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_MD)

        # ⚠️ 面板**不带**「创建任务」标题（用户 2026-10-07）：内嵌进创建任务页
        #    后页头已有标题，再摆一行就是重复；弹窗形态（``CreateTaskDialog``）
        #    的窗口标题栏仍由 ``DIALOG_TITLE`` 提供。

        # ---- 选 PDF：**可留空**（用户 2026-10-06「PDF 输入不是必须的」）----
        # ⚠️ 包一层容器而不是直接 addLayout：这一行要**整行显隐**——流程里
        #    删掉「上传文件/提取图片」后选的文件就没有意义（用户 2026-11-17），
        #    QLayout 没有可靠的整行显隐。
        # ⚠️ 这一排在**说明行上面**（用户 2026-11-17 截图要求两行对调）。
        self._pdf_row = QWidget()
        pick_row = QHBoxLayout(self._pdf_row)
        pick_row.setContentsMargins(0, 0, 0, 0)
        pick_row.setSpacing(T.SPACE_SM)
        self.pdf_label = BodyLabel("上传文件：")
        # 字段名加粗（用户 2026-11-17：与「任务类型 / 任务名称」同一档视觉）
        ui.apply_to(self.pdf_label, T.SIZE_BODY, bold=True, color=T.INK)
        pick_row.addWidget(self.pdf_label)
        self.pick_button = PushButton("选择 PDF/DjVu 文件")
        self.pick_button.clicked.connect(self._on_pick_pdf)
        pick_row.addWidget(self.pick_button)
        self.pdf_state = BodyLabel(EMPTY_PDF_HINT)
        ui.apply_to(self.pdf_state, T.SIZE_BODY, color=T.INK_FAINT)
        # ⚠️ 给个宽度上限：书名可能很长，不封顶的话文件名会把清除按钮顶到
        #    窗口外面去（而那个按钮恰恰是"选错了要反悔"时最需要够到的）。
        self.pdf_state.setMaximumWidth(PDF_STATE_MAX_WIDTH)
        pick_row.addWidget(self.pdf_state)
        # ---- 清除已选 PDF（用户 2026-10-06）----
        # ⚠️ 选错文件是常事（选到别的书、选到中间那本），没有清除只能重开
        #    一次「选择文件…」再点取消。按钮**只在已选时出现**，且**紧贴
        #    文件名**（不是丢在行末——那太远，看不出它管的是哪个文件）。
        #    显隐用 setVisible 而非 setEnabled：没东西可清时，禁用按钮摆
        #    在那儿只会让人多点一下。图标用 FIF.CANCEL，与「放弃本次修改」
        #    同一枚，语义一致。
        self.clear_pdf_button = ToolButton(FIF.CANCEL)
        self.clear_pdf_button.setToolTip("清除已选的 PDF")
        self.clear_pdf_button.setFixedSize(28, 28)
        self.clear_pdf_button.clicked.connect(self.clear_pdf)
        pick_row.addWidget(self.clear_pdf_button)
        self.clear_pdf_button.setVisible(False)
        pick_row.addStretch(1)
        layout.addWidget(self._pdf_row)

        # ---- 流程说明行（"当前用哪条流程"由它承担；随编辑状态变文案）----
        # ⚠️ 原来上面还有一个「使用自定义任务流程」复选框（用户 2026-11-17
        #    撤掉）：默认流程本身就可编辑，不需要一个开关来"解锁"编辑。
        # ⚠️ 摆在选文件行**下面**、紧贴编辑器（用户 2026-11-17：两行对调）——
        #    "下方编辑器可直接改"这句话挨着编辑器才成立。
        self.mode_hint = BodyLabel()
        ui.apply_to(self.mode_hint, T.SIZE_BODY, color=T.INK_SOFT)
        self.mode_hint.setWordWrap(True)
        layout.addWidget(self.mode_hint)

        # ---- 流程编辑器（**恒在**，用户 2026-11-17：默认直接展示编辑功能，
        #      不再点「编辑流程」触发）----
        # ⚠️ 包一层容器而不是把编辑器直接 addWidget：reset()/换图要**整体
        #    重建**编辑器（它原地改图，抱着旧图的面板不能复用），套一层
        #    host 就不必在主布局里搬动索引。
        self._editor_host = QWidget()
        self._editor_layout = QVBoxLayout(self._editor_host)
        self._editor_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._editor_host, 1)
        self._rebuild_editor(self._init_flow)

        self.flow_summary = CaptionLabel()
        ui.apply_to(self.flow_summary, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.flow_summary.setWordWrap(True)
        layout.addWidget(self.flow_summary)

        # ---- 底部按钮（恒在：编辑器常驻后不再有"预览/编辑"两态切换）----
        self._button_bar = QWidget()
        buttons = QHBoxLayout(self._button_bar)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addStretch()
        self.cancel_button = PushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        self.confirm_button = PrimaryPushButton("创建任务")
        self.confirm_button.clicked.connect(self.submit)
        buttons.addWidget(self.confirm_button)
        layout.addWidget(self._button_bar)

        self._refresh_confirm()

    # ------------------------------------------------------------ 编辑器
    def _rebuild_editor(self, diagram: FlowDiagram | None = None) -> None:
        """重建内嵌编辑器（``reset()`` / :meth:`set_custom_diagram` 共用）。

        ⚠️ **每次都重建**而不是复用（2026-10-07 事故的延续防线）：编辑器是
        **原地改图**的，旧面板里抱着上一张图。``BpmnEditorPanel`` 构造时会把
        传入图 **deepcopy** 一份（见该类说明），所以这里可以直接把"别人的图"
        交给它，外面那张毫发无损。
        """
        from desktop.components.bpmn_editor_panel import BpmnEditorPanel

        if self._editor_panel is not None:
            self._editor_panel.setParent(None)
            self._editor_panel.deleteLater()
            self._editor_panel = None
        panel = BpmnEditorPanel(
            diagram if diagram is not None else load_custom_init(),
            self,
            editable=True,
            reset_factory=load_custom_init,
            # 画布**不自己滚动**：创建任务页整体纵向滚动，流程图一次看全
            # （用户 2026-11-18）。
            scroll=False,
        )
        panel.diagram_changed.connect(self._on_diagram_changed)
        if panel.reset_button is not None:
            # ⚠️ 连接顺序有意**晚于**编辑器自己的 _on_reset：它先跑（换图并
            #    发 diagram_changed ⇒ 标记被置 True），本槽后跑清回 False
            #    ——「恢复默认」= 回到默认模板 = 字节拷贝语义。
            panel.reset_button.clicked.connect(self._on_flow_reset_default)
        self._editor_layout.addWidget(panel)
        self._editor_panel = panel

    def _on_diagram_changed(self) -> None:
        """编辑器内容变了 ⇒ 算自定义（要落盘），文案与摘要跟着刷。"""
        self._flow_edited = True
        self._refresh_mode()

    def _on_flow_reset_default(self) -> None:
        """编辑器工具栏「恢复默认」：清掉"已编辑"标记。

        ⚠️ 时序见 :meth:`_rebuild_editor` 的连接顺序注——本槽在编辑器自己
        的 reset（会发 ``diagram_changed``）之后执行，所以这里清回 ``False``
        就是最终状态。
        """
        self._flow_edited = False
        self._refresh_mode()

    # ------------------------------------------------------------ 模式刷新
    def _refresh_mode(self) -> None:
        """刷提示文案、摘要与选文件行显隐（编辑器内容由它自己持有，不碰画布）。"""
        self.mode_hint.setText(
            CUSTOM_HINT if self._flow_edited else default_hint(self._default_diagram)
        )
        self._sync_pdf_row()
        self._flow_summary_update()

    def _sync_pdf_row(self) -> None:
        """「选源文件」整行随**流程是否吃源文件**显隐。

        用户 2026-11-17：先把文件选好了，又把「上传文件/提取图片」节点删掉
        ——这个文件就没有意义了，行要藏起来（点「恢复默认」或把节点加回来
        会自动回来）。判据唯一走 :func:`desktop.steps.ports.flow_needs_source_pdf`
        （与详情页缺文件提示是同一份，别另写）。
        """
        from desktop.steps.ports import flow_needs_source_pdf

        self._pdf_row.setVisible(flow_needs_source_pdf(self.current_diagram()))

    def current_diagram(self) -> FlowDiagram:
        """当前**显示**的图（未编辑 = 默认模板那份的副本，编辑过 = 用户那张）。"""
        return self._custom_diagram

    # ------------------------------------------------------------ 选 PDF
    def _on_pick_pdf(self) -> None:
        """选源文件（PDF / DjVu）。

        ⚠️ 用**原生** ``QFileDialog``（不设 ``DontUseNativeDialog``）——
        项目硬规则：「资源管理器」指的是原生选择对话框，不是浏览窗口。
        """
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择 PDF/DjVu",
            str(default_open_dir()),
            "PDF/DjVu 文件 (*.pdf *.djvu *.djv)",
        )
        if not filename:
            return
        self.set_pdf(Path(filename))

    def set_pdf(self, path: Path) -> None:
        """设已选 PDF（自测与"创建后直接进详情"的快路径用）。"""
        self._pdf = Path(path)
        self.pdf_state.setText(f"已选择：{self._pdf.name}")
        ui.apply_to(self.pdf_state, T.SIZE_BODY, color=T.INK)
        self._sync_clear_button()
        self._refresh_confirm()

    def clear_pdf(self) -> None:
        """清掉已选 PDF（页面上那个「清除」按钮、:meth:`reset` 与自测共用）。

        ⚠️ 文案要回到"可留空"那句——留着"已选择：xxx.pdf"却其实没选文件，
        用户会以为文件还在（界面上一个假的已选状态比没有更糟）。
        ⚠️ **发信号时把被清掉的路径带出去**：任务名是选 PDF 时自动填的文件名，
        文件被清掉后那个名字也得跟着回退（见 ``CreateTaskPage._on_pdf_cleared``），
        否则会留下一个指向已清掉文件的名字。
        """
        previous = self._pdf
        self._pdf = None
        self.pdf_state.setText(EMPTY_PDF_HINT)
        ui.apply_to(self.pdf_state, T.SIZE_BODY, color=T.INK_FAINT)
        self._sync_clear_button()
        self._refresh_confirm()
        if previous is not None:
            self.pdf_cleared.emit(previous)

    def _sync_clear_button(self) -> None:
        """「清除」按钮跟着文件的有无显隐（没选文件时没什么可清）。"""
        button = getattr(self, "clear_pdf_button", None)
        if button is not None:
            button.setVisible(self._pdf is not None)

    def reset(self) -> None:
        """回到**刚打开**的样子（用户 2026-10-06：上一次创建任务信息要清掉）。

        清三样：已选 PDF、「编辑过流程」标记、编辑器内容（重建回默认模板
        那份）。

        ⚠️ **编辑器内容也要清**：用户编了半天流程，建完任务再进来却还带着
        那张图——他要建第二个任务时会以为"又得从头编一遍"（其实这是上一本
        书的流程）。重建回 ``load_custom_init()`` 才是"每次都从初值起步"的
        干净语义（2026-10-07 事故回归钉见自测 ``_check_create_page_reset``）。
        """
        self.clear_pdf()
        # ⚠️ **重建**而不是复用：编辑器原地改图，里面抱着上一次编到一半的图。
        self._rebuild_editor()
        self._flow_edited = False
        self._refresh_mode()

    def selected_pdf(self) -> Path | None:
        return self._pdf

    # ------------------------------------------------------------ 流程图
    def set_custom_diagram(self, diagram: FlowDiagram) -> None:
        """换流程图：整张交给编辑器（它内部拿副本），并标记"已编辑"。

        供外部喂图（自测 / 将来"带入上次流程"）用；用户手上普通的编辑直接
        在常驻编辑器里做，不需要调这里。
        """
        self._rebuild_editor(diagram)
        self._flow_edited = True
        self._refresh_mode()

    def _flow_summary_update(self) -> None:
        from desktop.components.flow_dialog import summarize

        self.flow_summary.setText(summarize(self.current_diagram()))

    def result_diagram(self) -> FlowDiagram | None:
        """用哪份流程图建任务。

        - **编辑器内容变过**：返回用户编的那张图（store 会写进 ``flow.bpmn``）；
        - **没动过**：返回 ``None`` —— 语义是"用默认模板"，store 会**原样字节
          拷贝** ``task_default.bpmn``，不经 ``FlowDiagram`` 的重新序列化
          （那会把连线上的 ``guji:port`` 抹掉）。
        """
        if self._flow_edited:
            return self._custom_diagram
        return None

    def uses_custom_flow(self) -> bool:
        """流程是不是**自定义**的（= 编辑器内容变过；兼容旧调用方保留此名）。"""
        return self._flow_edited

    def set_custom_mode(self, enabled: bool) -> None:
        """设"是否自定义流程"（自测兼容入口；等效于标记已编辑）。

        ⚠️ 只动标记，不换编辑器内容——要喂图走 :meth:`set_custom_diagram`。
        """
        self._flow_edited = bool(enabled)
        self._refresh_mode()

    # ------------------------------------------------------------ 提交
    def can_submit(self) -> bool:
        """能不能点「创建任务」。

        ⚠️ **不再要求已选 PDF**（用户 2026-10-06：「PDF 输入不是必须的」）：
        先把任务建出来、之后再去详情页补文件也是常见做法。所以这里恒为
        True——按钮的可用性不该由"还没挑文件"决定（用户同一条反馈：
        「创建任务按钮不必等上传 pdf 才可以点」）。

        真要拦，只剩两种情况：建任务的过程中（重复点击，归宿主页面的
        ``_busy``），以及**流程不合法**（见 :meth:`_validate_flow`）。
        """
        return True

    def _validate_flow(self) -> bool:
        """提交前过一遍**流程合法性**（:func:`desktop.steps.validate.validate_flow`）。

        ⚠️ 原来这道闸在编辑器的「保存流程」里；编辑器常驻后没有保存动作，
        校验挪到提交时（用户 2026-11-17）。硬错误 ⇒ toast 并挡下本次提交；
        警告 ⇒ 只提示不拦。**没编辑过不校验**——默认模板那份文件本来就是
        好的，别让模板自己的历史包袱拦住用户。
        """
        if not self._flow_edited:
            return True
        from desktop.steps.validate import validate_flow
        from desktop.ui.toast import show_toast

        result = validate_flow(self.current_diagram())
        if not result.ok:
            message = "；".join(result.errors)
            show_toast(self.window(), "warning", "流程不合法，未创建", message)
            return False
        if result.warnings:
            show_toast(self.window(), "warning", "流程提示", "；".join(result.warnings))
        return True

    def submit(self) -> None:
        """点「创建任务」：流程合法就发 :attr:`submitted`，**不碰窗口**。

        ⚠️⚠️ 这里原来有一句 ``self.window().close()``，面板被内嵌进
        **创建任务页**之后它就是**整个主窗口**——点一次「创建任务」把整个
        程序关掉（用户 2026-10-06 报："创建任务成功，但是程序 gui 不可见了"）。
        和 :meth:`reject` 同一条纪律：**面板只发信号，去哪儿由宿主决定**
        （弹窗时期宿主接 ``dialog.accept()``，页面时期宿主切到详情页）。
        """
        self._refresh_confirm()
        if not self.can_submit():
            return
        if not self._validate_flow():
            return
        self.submitted.emit()

    def _refresh_confirm(self) -> None:
        self.confirm_button.setEnabled(self.can_submit())

    def reject(self) -> None:
        """取消：**只发 :attr:`cancelled`，不碰窗口**。

        ⚠️ 原实现是"关掉 ``self.window()``"。面板被内嵌进页面后，那等于
        "点取消把整页关掉"（用户 2026-10-06 改二级页面后暴露）。关窗交给
        宿主：弹窗时期接 ``dialog.reject()``，页面时期切回列表。
        """
        self.cancelled.emit()


class CreateTaskDialog:
    """把 :class:`CreateTaskPanel` 装进外壳的薄壳。

    ⚠️ 离屏自测**不会**真弹模态：直接实例化 :class:`CreateTaskPanel` 验逻辑，
    或 monkeypatch 本类的 :meth:`exec`（项目硬规则：离屏自测里绝不真弹模态）。
    """

    def __init__(self, parent=None, flow: FlowDiagram | None = None):
        # ⚠️ **不要**用 qfluentwidgets 的 ``Dialog``：它只支持"一段文字+两个
        #    按钮"（第二参是字符串 content，且**没有** ``viewLayout()``），
        #    塞不进本面板这么成套的内容。统一走 dialog_shell（见该模块说明）。
        # own_chrome=True：面板自带标题与底部按钮（``confirm_button`` 等），
        # 外壳不再重复加一套——两套标题两排按钮会很难看。
        # ⚠️ 面板**不要**传 parent：它是外壳的内容控件，parent 给外壳即可，
        #    自己再挂一层会出现"控件被 reparent 两次"，尺寸失真。
        self.panel = CreateTaskPanel(None, flow)
        self.dialog = shell_dialog(
            DIALOG_TITLE,
            self.panel,
            parent,
            size=(980, 760),
            own_chrome=True,
        )
        # ⚠️ 面板**只发信号不碰窗口**（它可能被内嵌进页面，那时
        #    ``self.window()`` 是那一页，自己关会把整页关没），所以关窗
        #    由外壳接。弹窗形态保留给自测与旧调用方。
        self.panel.cancelled.connect(self.dialog.reject)

    def exec(self) -> bool:  # noqa: A003 - 与 Dialog.exec 同名是刻意的
        """弹窗。返回 True = 用户确认（PDF 可留空，见 :meth:`can_submit`）。"""
        self.dialog.exec()
        return self.panel.can_submit()

    def selected_pdf(self) -> Path | None:
        return self.panel.selected_pdf()

    def result_diagram(self) -> FlowDiagram | None:
        """用哪份流程图建任务（⚠️ 任务列表页调的就是它；``None`` = 用默认模板）。

        缺这个方法时 `page.import_pdf` 会 **AttributeError**，而按钮在
        `try` 之外 ⇒ 自定义模式点「创建任务」直接没反应。
        """
        return self.panel.result_diagram()

    def uses_custom_flow(self) -> bool:
        return self.panel.uses_custom_flow()


__all__ = [
    "CUSTOM_HINT",
    "CreateTaskDialog",
    "CreateTaskPanel",
    "DEFAULT_HINT_PREFIX",
    "DIALOG_TITLE",
    "EMPTY_PDF_HINT",
    "default_hint",
    "load_custom_init",
]
