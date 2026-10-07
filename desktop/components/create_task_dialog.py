# -*- coding: utf-8 -*-
"""**创建任务弹窗**（``docs/tasks/bpm.md`` 的 M3）。

用户 2026-10-05 的要求（原文）：

> 任务列表中 导入PDF 改成 "创建任务"，出现弹窗
>
> - 默认任务流程/自定义任务流程 checkbox 组件
> - 默认任务流程下有选择PDF，上传 PDF 后自动进入任务详情界面
> - 自定义任务流程下面有任务流程bpmn 节点渲染，默认是 task_detail.bpmn 的
>   节点渲染，同时提供按钮 "编辑流程" 点击调用 bpmn 自定义面板，编辑后同步到
>   弹窗中，同时提供确认流程 按钮，进入详情页面

后来用户又补了一条（这就是本版改动的由来）：

> 默认流程在 创建任务的时候，弹窗上面显示，**无论是否选择"使用自定义流程"
> 选项，下面都要告诉用户，当前流程是怎样的**，所以要显示默认流程

所以布局不再是"默认页 = 选 PDF / 自定义页 = 看流程"的**互斥两页**，而是：

::

    [ ] 使用自定义任务流程        ← 决定用哪份流程
    说明文字（随勾选变化，含步骤串——"当前流程"由它承担）
    ────────────────────────────
    选择 PDF   [选择文件…]  已选择：xxx.pdf     ← 两种模式都要选 PDF
    ────────────────────────────
    [编辑流程] [恢复默认流程]                  ← 仅自定义模式可用（右对齐）
    ┌ 流程节点图（按 bpmn 文件渲染）┐
    └───────────────────────────┘
    共 4 步：提取图片 → 检测文本框 → 图片拼版 → 生成 PDF
    ────────────────────────────
    [取消]  [创建任务]

三层结构（每层只干一件事）：

- :class:`CreateTaskPanel` —— 弹窗内容；
- :class:`CreateTaskDialog` —— 把它装进外壳的薄壳；
- :mod:`desktop.pages.tasklist.page` —— 拿到结果后走原有的指纹查重 → 建任务
  → 预热详情页链路（**不重复实现导入逻辑**）。

⚠️ **默认模式不传图**（:meth:`CreateTaskPanel.result_diagram` 返回 ``None``）：
默认流程 = ``desktop/static/task_default.bpmn`` 这份文件，由 store **原样字节
拷贝**进任务目录。过一次 ``FlowDiagram.to_xml`` 会把它重新序列化，而
``FlowDiagram`` 不建模连线上的端口标记（``guji:port``）——那会把信息抹掉。
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CheckBox,
    FluentIcon as FIF,
    PrimaryPushButton,
    PushButton,
    ToolButton,
)

from desktop import ui
from desktop.components.bpmn_view import BpmnView
from desktop.components.dialog_shell import shell_dialog
from desktop.steps.bpmn_diagram import FlowDiagram
from desktop.ui import theme as T
from desktop.utils.files import default_open_dir, package_dir

#: 弹窗标题
DIALOG_TITLE = "创建任务"
#: 默认模式的提示**前半句**；后半句（哪几步）由**文件内容**生成，见
#: :func:`default_hint`。
#:
#: ⚠️ 为什么拆开：以前这里手写死了"提取图片 → 检测文本框 → 图片去底色 →
#: 生成 PDF"，与 ``task_default.bpmn`` 实际内容**各说各话**（用户 2026-10-05
#: 明确指出："默认流程必须跟 task_default.bpmn 一样……不要你自己设计默认流程"）。
#: 现在步骤串一律从文件读，写错的可能性被结构性消除。
DEFAULT_HINT_PREFIX = "使用默认任务流程："
CUSTOM_HINT = "使用自定义任务流程（点「编辑流程」可改）："
#: 自定义初值文件缺失时的告警（⚠️ 缺了它「自定义」会退化成与默认一样）
CUSTOM_MISSING_HINT = (
    "⚠ 找不到 desktop/static/task_detail.bpmn，自定义模式暂用默认流程；"
    "请先恢复该文件，否则「自定义」与「默认」看起来一模一样。"
)
#: **没选** PDF 时那一行的提示（唯一来源，:meth:`CreateTaskPanel.clear_pdf` 也用）
EMPTY_PDF_HINT = "可留空，之后在任务详情里补选"
#: 「已选择：xxx.pdf」那行文字的宽度上限（px）。封顶是为了长书名不会把后面的
#: 「清除」按钮顶出窗口——而那按钮恰是选错文件时最需要够到的。
PDF_STATE_MAX_WIDTH = 420


def default_hint(diagram: FlowDiagram) -> str:
    """默认模式的完整提示：前缀 + **文件里真实的**步骤串。"""
    from desktop.components.flow_dialog import summarize

    return DEFAULT_HINT_PREFIX + summarize(diagram)


#: 流程区的最小高度（节点图比它高时由滚动区接管）
FLOW_MIN_HEIGHT = 240

#: 自定义流程的初值文件名（放在 ``desktop/static/``，随打包进``_internal/``）。
CUSTOM_INIT_FILE = "task_detail.bpmn"


def custom_init_path() -> Path:
    """自定义流程初值文件的标准位置。"""
    return package_dir() / "static" / CUSTOM_INIT_FILE


def custom_init_missing() -> bool:
    """初值文件是不是不见了。

    ⚠️ 单独暴露这个判断，是因为"文件不见了"必须**说出来**：
    :func:`load_custom_init` 找不到文件会回落默认流程（功能不能崩），但那样
    「自定义」和「默认」长得一模一样——用户会以为"勾了没用"。这个现象真的
    发生过（2026-10-05）。
    """
    return not custom_init_path().is_file()


def load_custom_init() -> FlowDiagram:
    """读 ``desktop/static/task_detail.bpmn`` 作自定义模式的初值（整张图）。

    返回 :class:`FlowDiagram`——**坐标就在图里**（来自文件的 DI 段），不再
    单独返回一份布局对象：页面渲染的就是文件本身，两份东西必然漂移。

    ⚠️ 文件缺失或损坏**一律回落默认流程**（不抛）：这是"给用户一个可上手
    改的起点"的增强项，缺了它功能应当退化而不是崩。调用方不必处理异常。
    """
    from desktop.steps.scheduler import load_default_diagram

    path = custom_init_path()
    try:
        if path.is_file():
            return FlowDiagram.load(path)
    except (OSError, ValueError):
        pass
    fallback = load_default_diagram()
    return fallback if fallback.nodes else FlowDiagram()


class CreateTaskPanel(QWidget):
    """创建任务弹窗的**内容**（不含Dialog 外壳，便于自测直接实例化）。

    对外只认三件事：:meth:`selected_pdf`（选了哪个 PDF）、
    :meth:`result_diagram`（用哪份流程图建任务）、:meth:`uses_custom_flow`
    （是不是自定义）。任务列表页拿这三样走原有的建任务链路。
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

    def __init__(self, parent=None, flow: FlowDiagram | None = None, *,
                 outer_margins: bool = True):
        """``outer_margins``：要不要自带外层留白（默认带，弹窗形态需要）。

        ⚠️ 内嵌进**创建任务页**时传 ``False``：页面根布局已有
        ``SPACE_XL`` 边距，面板再 pad 一层就成了"任务名称顶格、创建任务
        多缩进 24px"的双层缩进（用户 2026-10-06 截图确认）。与
        ``ImpositionPanel(enable_switch=…)`` 同一条纪律——宿主专属的布局
        差异用构造参数声明，组件不猜自己在哪。
        """
        super().__init__(parent)
        # ⚠️ 自定义模式的**初值**取 ``desktop/static/task_detail.bpmn``（用户
        # 在 bpm.md 里点名的文件）。它是**整张图**（含坐标），页面照着它渲染
        # ——与 bpmn.io 里看到的完全一致。文件缺失/损坏 → 回落默认模板。
        self._custom_init_missing = custom_init_missing()
        self._custom_diagram = flow or load_custom_init()
        # 默认流程 = 默认模板文件那份图（**只用于预览**；建任务时走字节拷贝）
        self._default_diagram = self._load_default_diagram()
        self._pdf: Path | None = None
        self._editor = None
        self._outer_margins = bool(outer_margins)
        self._build_ui()
        self._refresh_mode()

    @staticmethod
    def _load_default_diagram() -> FlowDiagram:
        from desktop.steps.scheduler import load_default_diagram

        diagram = load_default_diagram()
        return diagram if diagram.nodes else FlowDiagram()

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

        # ---- 流程模式 checkbox（文档要求的核心组件）----
        self.custom_check = CheckBox("使用自定义任务流程")
        self.custom_check.setChecked(False)
        self.custom_check.stateChanged.connect(self._on_mode_changed)
        layout.addWidget(self.custom_check)

        self.mode_hint = BodyLabel()
        ui.apply_to(self.mode_hint, T.SIZE_BODY, color=T.INK_SOFT)
        self.mode_hint.setWordWrap(True)
        layout.addWidget(self.mode_hint)

        # ---- 选 PDF：**可留空**（用户 2026-10-06「PDF 输入不是必须的」）----
        pick_row = QHBoxLayout()
        pick_row.setSpacing(T.SPACE_SM)
        self.pdf_label = BodyLabel("PDF 源文件：")
        pick_row.addWidget(self.pdf_label)
        self.pick_button = PushButton("选择文件…")
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
        layout.addLayout(pick_row)

        # ---- 「编辑流程/恢复默认流程」按钮行（右对齐）----
        # ⚠️ 原来这行左边还有一个「当前流程：默认/自定义任务流程」标题
        #    （用户 2026-10-06 要求删掉）：上面 mode_hint 已经说了用哪条流程
        #    （默认模式是完整步骤串，自定义模式点名"自定义任务流程"），再摆
        #    一行标题是重复信息。只留右侧两个按钮。
        flow_button_row = QHBoxLayout()
        flow_button_row.setSpacing(T.SPACE_SM)
        flow_button_row.addStretch()
        self.edit_button = PushButton("编辑流程")
        self.edit_button.clicked.connect(self._on_edit_flow)
        flow_button_row.addWidget(self.edit_button)
        self.reset_button = PushButton("恢复默认流程")
        self.reset_button.clicked.connect(self._on_reset_flow)
        flow_button_row.addWidget(self.reset_button)
        layout.addLayout(flow_button_row)

        self.flow_view = BpmnView(self._default_diagram)
        scroll = QScrollArea()
        # ⚠️ 不 setWidgetResizable：它会按视口拉伸内层控件，把"内容多大就
        #    多大"变成"永远填满视口"——节点图下方拖出一大片空白。
        # ⚠️ 垂直**居中**而不是顶对齐：画布只有 ~144 高、视口有 400+，
        #    顶对齐会让空白全堆在图**下方**（看着像图没画完）；居中把空白
        #    对称分到上下，观感是"图居中显示"。横向仍左对齐——图比视口宽时
        #    居中会导致左边一截永远够不着、横向滚动条起点诡异。
        scroll.setWidgetResizable(False)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        scroll.setWidget(self.flow_view)
        scroll.setMinimumHeight(FLOW_MIN_HEIGHT)
        layout.addWidget(scroll, 1)
        self.flow_scroll = scroll

        self.flow_summary = CaptionLabel()
        ui.apply_to(self.flow_summary, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.flow_summary.setWordWrap(True)
        layout.addWidget(self.flow_summary)

        # ---- 内嵌的流程编辑器（点「编辑流程」时显示，**替代**上面的预览）----
        # ⚠️ 为什么内嵌而不是再弹一层（用户 2026-10-06）：创建任务已改成
        #    **二级页面**，页面里再弹模态窗就成了"页面套页面"——层次多一层
        #    就多一处"盖住下面/关不掉"的问题（历史上三个弹窗都踩过）。
        self._editor_host = QWidget()
        self._editor_layout = QVBoxLayout(self._editor_host)
        self._editor_layout.setContentsMargins(0, 0, 0, 0)
        self._editor_host.setVisible(False)
        layout.addWidget(self._editor_host, 1)

        # ---- 底部按钮 ----
        # ⚠️ 包一层容器而不是直接 addLayout：编辑流程时要把**整行**藏起来
        #    （内嵌编辑器自带「关闭/保存流程」，两排确认按钮同屏会让人不知
        #    点哪组——用户 2026-10-06 截图反馈），QLayout 没有可靠的整行显隐。
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

    # ------------------------------------------------------------ 模式切换
    def _on_mode_changed(self) -> None:
        self._refresh_mode()

    def _refresh_mode(self) -> None:
        """按 checkbox 换**当前显示的流程**、文案与按钮可见性。

        ⚠️ 节点图**不隐藏**（这是本轮的核心改动）：未勾选时显示默认流程，
        勾上后显示自定义流程。用户任何时候都能看到"这次会用哪条流程"。
        """
        custom = self.uses_custom_flow()
        if custom:
            self.mode_hint.setText(CUSTOM_MISSING_HINT if self._custom_init_missing else CUSTOM_HINT)
        else:
            self.mode_hint.setText(default_hint(self._default_diagram))
        self.edit_button.setVisible(custom)
        self.reset_button.setVisible(custom)
        self.confirm_button.setText("确认流程并创建" if custom else "创建任务")
        self.flow_view.set_diagram(self.current_diagram())
        # 换图后高度可能变（默认 8 节点 vs 自定义 4 节点），给个贴合的最小高度
        self.flow_scroll.setMinimumHeight(max(FLOW_MIN_HEIGHT, self.flow_view.sizeHint().height() + 24))
        self._flow_summary_update()

    def current_diagram(self) -> FlowDiagram:
        """当前**显示**的图（未勾=默认流程，勾了=自定义流程）。"""
        return self._custom_diagram if self.uses_custom_flow() else self._default_diagram

    # ------------------------------------------------------------ 选 PDF
    def _on_pick_pdf(self) -> None:
        """选源 PDF。

        ⚠️ 用**原生** ``QFileDialog``（不设 ``DontUseNativeDialog``）——
        项目硬规则：「资源管理器」指的是原生选择对话框，不是浏览窗口。
        """
        filename, _ = QFileDialog.getOpenFileName(self, "选择 PDF", str(default_open_dir()), "PDF (*.pdf)")
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

        清四样：已选 PDF、勾选状态、自定义流程图（回到初值文件那份）、以及
        正开着的流程编辑器。

        ⚠️ **自定义流程图也要清**：用户编了半天流程，建完任务再进来却还带着
        那张图——他要建第二个任务时会以为"又得从头编一遍"（其实这是上一本
        书的流程）。回到 ``load_custom_init()`` 才是"每次都从初值起步"的
        干净语义。
        ⚠️ **编辑器要销毁**：``_editor_host`` 可见时复位，用户会看到一个
        开着的编辑器却已经没有任何输入了；而且编辑器面板里抱着旧图，不销毁
        就会被下次「编辑流程」复用（见 :meth:`_on_edit_flow`）。
        """
        self.clear_pdf()
        if self._editor is not None:
            # ⚠️ **销毁**而不是只收起：编辑器是**原地改图**的，面板里还抱着
            #    上一次那张图；只收起的话下次「编辑流程」会复用旧面板——用户
            #    看到的就是上一本书的流程（2026-10-07 报的正是这个现象）。
            #    反正每次进编辑都会重建（见 _on_edit_flow），这里直接丢掉。
            self._editor.setParent(None)
            self._editor.deleteLater()
            self._editor = None
        self._editor_host.setVisible(False)
        self._set_flow_preview_visible(True)
        # ⚠️ 顺序要紧：先清 checkbox（触发 _refresh_mode 走一遍默认流程），
        #    再换自定义图——反过来会拿着旧的自定义图去刷默认模式的预览。
        self.custom_check.setChecked(False)
        self._custom_diagram = load_custom_init()
        self._refresh_mode()

    def selected_pdf(self) -> Path | None:
        return self._pdf

    # ------------------------------------------------------------ 编辑流程
    def _on_edit_flow(self) -> None:
        """**就地**编辑流程（不再二次弹窗，用户 2026-10-06）。

        点「编辑流程」→ 上面的流程图预览**换成**编辑器；「保存流程」回写并
        切回预览，「关闭」丢弃改动。

        ⚠️ **每次进编辑都重建编辑器**（2026-10-07 用户报"流程编辑保存着上次
        编辑的数据，没有恢复到默认流程图"）：上一版把面板缓存进
        ``self._editor`` 复用——``reset()`` 换掉 ``_custom_diagram`` 之后，旧
        编辑器还抱着**上一本书那张图**，再点「编辑流程」看到的不是当前流程。
        重建还顺带修好「关闭丢不掉改动」：编辑器是**原地改图**的
        （``BpmnEditor.add_node`` 等直接改持有的对象），所以传进去的是
        ``_custom_diagram`` 的**副本**——「保存」把改完的副本交回来
        （:meth:`set_custom_diagram`），「关闭」把副本扔掉，原图毫发无损。

        ⚠️ ``FlowPanel(embedded=True, close_window=False)``：藏掉它自带的标题
        （本面板已经有标题），且**不让它去关所属窗口**——内嵌时
        ``self.window()`` 就是宿主页面，关掉会把整页关没。
        「恢复默认」= 回到自定义初值文件（``task_detail.bpmn``）。
        """
        from desktop.components.flow_dialog import FlowPanel

        if self._editor is not None:
            self._editor.setParent(None)
            self._editor.deleteLater()
            self._editor = None
        panel = FlowPanel(
            deepcopy(self._custom_diagram),
            self,
            editable=True,
            reset_factory=load_custom_init,
            embedded=True,
            close_window=False,
        )
        panel.done.connect(self._on_editor_done)
        self._editor = panel
        self._editor_layout.addWidget(panel)
        self._set_flow_preview_visible(False)
        self._editor_host.setVisible(True)

    def _on_editor_done(self, ok: bool) -> None:
        """内嵌编辑器结束：保存了才回写，然后切回流程图预览。"""
        if ok and self._editor is not None:
            updated = self._editor.result_diagram()
            if updated is not None:
                self.set_custom_diagram(updated)
        self._editor_host.setVisible(False)
        self._set_flow_preview_visible(True)

    def _set_flow_preview_visible(self, visible: bool) -> None:
        """流程**预览**那一组控件的显隐（编辑时让位给编辑器）。

        ⚠️ 面板没有"预览/编辑"两层容器（2026-10-05 改成"恒定显示当前流程"
        之后就没有 ``content_stack`` 了），所以这里显隐的是这一组控件：
        图、摘要、编辑/恢复两个按钮，**以及底部按钮行**——编辑器自带
        「关闭/保存流程」，两排确认按钮同屏分不清哪组管哪层（用户
        2026-10-06）。⚠️ 漏掉任何一个都会在编辑时露出来——图和按钮同时
        可见，用户以为没切进编辑。
        """
        custom = self.uses_custom_flow()
        for widget in (self.flow_scroll, self.flow_summary):
            widget.setVisible(visible)
        # 「编辑流程/恢复默认」只在自定义模式下出现（默认流程没得编）
        self.edit_button.setVisible(visible and custom)
        self.reset_button.setVisible(visible and custom)
        # 底部「取消/确认流程并创建」只在预览态出现（编辑态由编辑器的
        # 「保存流程/关闭」接管，保存后自动回到预览态）
        self._button_bar.setVisible(visible)

    def _on_reset_flow(self) -> None:
        """恢复默认流程：回到**初值文件**那一份（``task_detail.bpmn``）。"""
        self.set_custom_diagram(load_custom_init())

    def set_custom_diagram(self, diagram: FlowDiagram) -> None:
        """换自定义流程图并刷新预览（编辑弹窗确认后由 :meth:`_on_edit_flow` 调）。"""
        self._custom_diagram = diagram
        if self.uses_custom_flow():
            self.flow_view.set_diagram(diagram)
            self.flow_scroll.setMinimumHeight(max(FLOW_MIN_HEIGHT, self.flow_view.sizeHint().height() + 24))
            self._flow_summary_update()

    def _flow_summary_update(self) -> None:
        from desktop.components.flow_dialog import summarize

        self.flow_summary.setText(summarize(self.flow_view.diagram()))

    def result_diagram(self) -> FlowDiagram | None:
        """用哪份流程图建任务。

        - 自定义模式：返回用户编的那张图（store 会写进 ``flow.bpmn``）；
        - 默认模式：返回 ``None`` —— 语义是"用默认模板"，store 会**原样字节
          拷贝** ``task_default.bpmn``，不经 ``FlowDiagram`` 的重新序列化
          （那会把连线上的 ``guji:port`` 抹掉）。
        """
        if self.uses_custom_flow():
            return self._custom_diagram
        return None

    def uses_custom_flow(self) -> bool:
        return self.custom_check.isChecked()

    def set_custom_mode(self, enabled: bool) -> None:
        """设流程模式（自测与将来"记住上次选择"用）。"""
        self.custom_check.setChecked(bool(enabled))

    # ------------------------------------------------------------ 提交
    def can_submit(self) -> bool:
        """能不能点「创建任务」。

        ⚠️ **不再要求已选 PDF**（用户 2026-10-06：「PDF 输入不是必须的」）：
        先把任务建出来、之后再去详情页补文件也是常见做法。所以这里恒为
        True——按钮的可用性不该由"还没挑文件"决定（用户同一条反馈：
        「创建任务按钮不必等上传 pdf 才可以点」）。

        真要拦，只剩一种情况：建任务的过程中（重复点击），那由宿主页面的
        ``_busy`` 负责，不归这里。
        """
        return True

    def submit(self) -> None:
        """点「创建任务」：发 :attr:`submitted`，**不碰窗口**。

        ⚠️⚠️ 这里原来有一句 ``self.window().close()``，面板被内嵌进
        **创建任务页**之后它就是**整个主窗口**——点一次「创建任务」把整个
        程序关掉（用户 2026-10-06 报："创建任务成功，但是程序 gui 不可见了"）。
        和 :meth:`reject` 同一条纪律：**面板只发信号，去哪儿由宿主决定**
        （弹窗时期宿主接 ``dialog.accept()``，页面时期宿主切到详情页）。
        """
        self._refresh_confirm()
        if not self.can_submit():
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
        `try` 之外 ⇒ 自定义模式点「确认流程并创建」直接没反应。
        """
        return self.panel.result_diagram()

    def uses_custom_flow(self) -> bool:
        return self.panel.uses_custom_flow()


__all__ = [
    "CUSTOM_HINT",
    "CUSTOM_INIT_FILE",
    "CUSTOM_MISSING_HINT",
    "CreateTaskDialog",
    "CreateTaskPanel",
    "DEFAULT_HINT_PREFIX",
    "DIALOG_TITLE",
    "EMPTY_PDF_HINT",
    "custom_init_missing",
    "custom_init_path",
    "default_hint",
    "load_custom_init",
]
