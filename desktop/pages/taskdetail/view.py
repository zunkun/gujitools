# -*- coding: utf-8 -*-
"""任务详情页的视图构建：头部/步骤条/预览区/控制列/日志的 UI 组装。

只做控件创建与信号连接，业务动作全部委托给宿主页面的其他 Mixin。

视觉结构（自上而下）：
1. 页头卡片：返回 + 任务名 + 源文件标签 + 流程编辑 + 选 PDF + 插入图片/文件夹；
2. 步骤条卡片：四步流程与状态；
3. 主体：左侧预览卡片（自适应）+ 右侧参数卡片（固定宽度区间）；
4. 底部：执行日志状态条（常驻一行，点击唤出不挤压布局的日志浮层），
   ���**最右端是「打开任务数据目录」**（用户 2026-10-06 从页头移来）。
"""

from __future__ import annotations

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QStackedWidget, QTabWidget, QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel, ComboBox, PrimaryPushButton, PushButton, ToolButton,
)
from qfluentwidgets import FluentIcon as FIF

from desktop.components import PANEL_CLASSES
from desktop.components.detect_stats import DetectStatsWidget
from desktop.components.imposition import ImpositionPanel, ImpositionViewWidget
from desktop.components.log_panel import LogPanel
from desktop.components.step_bar import StepBar
from desktop.components.viewers import (
    ImageViewerWidget, PdfViewerWidget,
    PrintPreviewWidget, RembgPreviewWidget,
)
from desktop.steps.spec import FLOW_STAGES
from desktop.store import IMPOSITION_STAGE
from desktop.ui import theme as T
from desktop.ui.icons import PDF_FILE
from desktop.ui.widgets import (
    Card, Divider, ProgressLine, SectionTitle, apply_to, combo_box,
    mark_input_entry,
)
from desktop.pages.taskdetail.submit import SUBMIT_TEXT


class LazyPanelHost(QWidget):
    """阶段面板的**惰性宿主**：真正被取用时才构造内部面板。

    为什么需要：详情页一进来停在第一步，而第四步的 ``PrintPanel`` 构造要
    ~128 ms（占整个详情页构造的**一半**——它那张参数表单 ``build_form`` 单项
    就 106 ms）。用户可能从头到尾都不点第四步，却每次进详情页都在为它买单。

    属性访问一律转发给内部面板，所以 ``control_stack.widget(3).get_args()``
    这类既有写法照常工作。Qt 自己的 ``sizeHint`` / ``paintEvent`` 等由 C++
    层调用，**不走 Python 的 __getattr__**，不会误触发构造。
    """

    def __init__(self, factory, hooks=(), parent=None):
        """factory() 造真面板；hooks 是"内部面板构造完成"后的回调（接线用）。"""
        super().__init__(parent)
        self._factory = factory
        self._hooks = list(hooks)
        self._inner: QWidget | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._host_layout = layout

    def add_created_hook(self, fn) -> None:
        """注册"内部面板构造完成"回调；**若已构造则立刻执行**。

        ⚠️ 必须支持挂多个回调：视图层要接预览刷新、暂存层要接 param_edited，
        它们分属不同 Mixin，各自只知道自己的接线，不能互相覆盖。
        """
        if self._inner is not None:
            fn(self._inner)
        else:
            self._hooks.append(fn)

    def peek(self) -> QWidget | None:
        """**不触发构造**地看内部面板；尚未构造时返回 None。"""
        return self._inner

    @property
    def panel(self) -> QWidget:
        """内部真面板，首次访问时构造（并把挂着的回调全部执行一遍）。"""
        if self._inner is None:
            self._inner = self._factory()
            self._host_layout.addWidget(self._inner)
            hooks, self._hooks = self._hooks, []
            for hook in hooks:
                hook(self._inner)
        return self._inner

    def __getattr__(self, name: str):
        # 只有在类上找不到该属性时才会走到这里；_factory/_inner 都在 __dict__
        factory = self.__dict__.get("_factory")
        if factory is None:
            raise AttributeError(name)
        return getattr(self.panel, name)


class DetailViewMixin:
    """依赖宿主页面提供的方法：_on_back、_select_stage、各预览联动槽、
    current_stage()、_update_run_buttons() 等。"""

    # ------------------------------------------------------------------ 组装
    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG)
        root.setSpacing(T.SPACE_MD)
        #: 根布局留引用：``_rebuild_step_bar`` 要按位置把旧步骤条换成新的
        #: （BPM 驱动——本任务可能是自定义流程，步骤顺序与可选节点位置不同）。
        self._root_layout = root

        # ⚠️ 留个引用：提示层要按「页头下沿」定遮罩上沿（见
        #    ``manifest.py::_content_top``）。之前只能从根布局的第 0 项
        #    反查，那行没存引用、读起来绕。
        self.header_card = self._build_header()
        root.addWidget(self.header_card)
        bar = self._build_step_bar()
        root.addWidget(bar)
        #: 步骤条在根布局里的位置（``_rebuild_step_bar`` 按它换控件，
        #: 不写死 1——header 之后还有别的行时 1 就错了）。
        self._step_bar_row = root.indexOf(bar)
        body = QHBoxLayout()
        body.setSpacing(T.SPACE_MD)
        body.addWidget(self._build_preview_card(), 1)
        body.addWidget(self._build_control_card())
        root.addLayout(body, 1)

        self.log_panel = LogPanel()
        # 页面各处沿用的 self.log_view 直接指向面板内的文本域
        self.log_view = self.log_panel.log_view
        # ⚠️ 「打开任务数据目录」摆在**底部状态条最右端**（右下角，用户
        #    2026-10-06："右上角的打开任务数据目录，统一放到右下角"）。
        #    它不是输入入口，是"去磁盘上看产物/自己放文件"的辅助动作——
        #    和页头那排输入按钮混在一起会让人以为也是一种输入方式。
        #    ⚠️ 必须**在 addWidget 之后立刻**交给 log_panel：状态条是固定高
        #    控件，晚一步挂进来布局要等下一次 show 才生效。
        self.task_dir_button = ToolButton(FIF.FOLDER)
        self.task_dir_button.setToolTip("打开任务数据目录")
        self.task_dir_button.setFixedSize(26, 26)
        self.task_dir_button.clicked.connect(self._open_task_dir)
        self.log_panel.set_task_dir_action(self.task_dir_button)
        root.addWidget(self.log_panel)

        self._update_run_buttons({"status": "pending"})

    def _build_header(self) -> Card:
        card = Card(padding=0, spacing=0, radius=T.RADIUS_MD, layout="h")
        row = card.box
        row.setContentsMargins(T.SPACE_MD, T.SPACE_SM, T.SPACE_MD, T.SPACE_SM)
        row.setSpacing(T.SPACE_MD)

        back_btn = ToolButton(FIF.RETURN)
        back_btn.setToolTip("返回任务列表")
        back_btn.setFixedSize(34, 34)
        back_btn.clicked.connect(self._on_back)
        row.addWidget(back_btn)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(1)
        self.detail_title = QLabel("任务详情")
        apply_to(self.detail_title, T.SIZE_SUBTITLE, bold=True, color=T.INK)
        text_column.addWidget(self.detail_title)
        # 任务名**行内编辑**（2026-10-06「非必需，可随时修改」）。
        # ⚠️ 不用 QInputDialog：那也是模态窗，离屏自测不能真弹（项目硬规则），
        #    而且页头本来就有标题的位置，行内改最省一次点击。
        self.rename_edit = QLineEdit()
        self.rename_edit.setVisible(False)
        self.rename_edit.editingFinished.connect(self._commit_rename)
        self.rename_edit.installEventFilter(self)   # Esc 取消
        text_column.addWidget(self.rename_edit)
        self.source_label = QLabel("")
        apply_to(self.source_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        text_column.addWidget(self.source_label)
        # ---- 「流程要 PDF 而这个任务还没有」的红色提示（用户 2026-10-06）----
        # ⚠️ 放**页头里**而不是 toast：toast 会自己消失，而这件事在用户处理完
        #    之前一直成立（四个步骤都跑不了）。它得**一直在**，直到补上文件。
        #    默认隐藏——不是每个任务都缺文件，常驻一条红字会变成噪声。
        self.source_warning = QLabel("")
        apply_to(self.source_warning, T.SIZE_CAPTION, bold=True,
                 color=T.DANGER)
        self.source_warning.setVisible(False)
        text_column.addWidget(self.source_warning)
        row.addLayout(text_column)
        row.addStretch()

        # ---- BPM：查看/编辑本任务流程（bpm.md「同时可以修改 bpmn 节点」）----
        # ⚠️ 为什么放在页头而不是别处：步骤条本身**就是**流程的渲染（用户天天
        #    看它），把"改流程"的入口放在它旁边才符合直觉；放角落会没人找得到。
        # 改名：铅笔按钮，紧挨任务名（"可随时修改"就得伸手可及）
        self.rename_button = ToolButton(FIF.EDIT)
        self.rename_button.setToolTip("修改任务名称")
        self.rename_button.setFixedSize(34, 34)
        self.rename_button.clicked.connect(self._begin_rename)
        row.addWidget(self.rename_button)

        self.flow_button = ToolButton(FIF.LAYOUT)
        self.flow_button.setToolTip("查看 / 编辑本任务的流程")
        self.flow_button.setFixedSize(34, 34)
        self.flow_button.clicked.connect(self._on_show_flow)
        row.addWidget(self.flow_button)

        # ---- 补选源 PDF（用户 2026-10-06「PDF 输入不是必须的」）----
        # 创建任务时可以先不选文件，建出来的就是"空壳任务"。这个按钮是它的
        # 另一半：**恒在**（不随有没有源文件显隐）——文件被移走/删除时它同样
        # 是补救入口，藏起来等于让用户没法自己修。
        # ⚠️ 图标用**现成的自绘 ``PDF_FILE``**（用户 2026-10-06："图标使用
        #    PDF_FILE 现成的"）：内置 ``FIF.DOCUMENT`` 是**纯空白文档**，放进
        #    这个按钮会被读成"打开文档"而不是"选 PDF"，与列表页「创建任务」
        #    按钮、第四步「下载 PDF」用的都是同一枚图标才一致。
        self.source_button = ToolButton(PDF_FILE)
        self.source_button.setToolTip("为这个任务选择 PDF 源文件")
        self.source_button.setFixedSize(34, 34)
        self.source_button.clicked.connect(self._on_pick_source)
        row.addWidget(self.source_button)

        # ---- 插入图片：给「流程第一步不吃 PDF」的步骤准备输入 ----
        # ⚠️ 为什么放**页头**而不是只靠预览区的「＋」（用户 2026-10-06）：自定义
        #    流程把「检测文本框」之类放第一步时，它的输入是入口图片目录
        #    （``stages/input/``），而预览区那排按钮**此刻可能被提示层盖住**
        #    ——页头这一排永远在遮罩之上、照常可点（用户 2026-10-06 明确要求
        #    "那个导入按钮，你不能把它给遮住啊"）。
        # ⚠️ **红框常驻**（用户 2026-10-06"都是红色框住"）：这两个按钮是"给
        #    这一步喂图片"的入口，自定义流程第一步不吃 PDF 时**全靠它们**。
        #    常驻红框＝"这排按钮里红的那两个就是输入入口"，一眼能找到，不必
        #    先判断当前缺不缺东西。⚠️ 与 ``_set_tool_highlight`` 的"缺什么亮
        #    什么"是**两码事**：那个是动态提醒（补上就灭），这个是常驻标识。
        #    实现上不能互相覆盖，故由 ``_INPUT_ENTRY_MARK`` 统一给样式。
        self.insert_button = ToolButton(FIF.PHOTO)
        self.insert_button.setToolTip(
            "为本任务插入图片（放到入口图片目录，可多选）")
        self.insert_button.setFixedSize(34, 34)
        self.insert_button.clicked.connect(self.insert_pages)
        mark_input_entry(self.insert_button)
        row.addWidget(self.insert_button)

        # 📁 同样红框：整目录导入（文件对话框选不了目录，得单独一个入口）
        self.insert_dir_button = ToolButton(FIF.FOLDER)
        self.insert_dir_button.setToolTip(
            "把一个文件夹里的图片批量插入（放到入口图片目录）")
        self.insert_dir_button.setFixedSize(34, 34)
        self.insert_dir_button.clicked.connect(self.insert_pages_from_folder)
        mark_input_entry(self.insert_dir_button)
        row.addWidget(self.insert_dir_button)
        # ⚠️「打开任务数据目录」**从页头移走**（用户 2026-10-06"统一放到右下
        #    角"）——它不是输入入口，是"去磁盘上看产物"的辅助动作，混在输入
        #    按钮里会让人以为也是一种输入方式。摆在底部状态条最右端。
        return card

    # ------------------------------------------------------------ 任务改名
    def _begin_rename(self) -> None:
        """点铅笔：标题换成行内输入框（不用弹窗——见上面 rename_edit 处的注释）。"""
        if not getattr(self, "task_id", None):
            return
        record = self.store.get_task(self.task_id) or {}
        self.rename_edit.setText(str(record.get("name") or ""))
        self.rename_edit.setVisible(True)
        self.detail_title.setVisible(False)
        self.rename_edit.setFocus()
        self.rename_edit.selectAll()

    def _commit_rename(self) -> None:
        """行内编辑结束（回车/失焦）→ 落盘并刷新标题。"""
        # ⚠️ 判"在不在编辑态"必须用 ``isHidden()``（只看控件自身显隐），
        #    **不能**用 ``isVisible()``：后者在祖先不可见时恒为 False——详情页
        #    不在前台时（刚从流程编辑页回来、或停在别的页）改名会被这一行
        #    **静默丢掉**，表现为"改名没反应"。
        #
        # ⚠️ 方向别搞反：``isHidden()`` 为 True = 控件已被隐藏 = **没在编辑**
        #    ⇒ 该 return。（写成 ``not isHidden()`` 会变成"可见才 return"，
        #    改名永远不生效——这个错我犯过一次。）
        if self.rename_edit.isHidden():
            return                      # 没在编辑态（Esc 取消后失焦会再触发一次）
        typed = self.rename_edit.text().strip()
        self.rename_edit.setVisible(False)
        self.detail_title.setVisible(True)
        if not typed:
            return                      # 留空 = 不改（rename_task 的空回落只在
                                        # 明确"清空后保存"时用）
        try:
            changed = self.store.rename_task(self.task_id, typed)
        except Exception as exc:        # noqa: BLE001 - 落盘失败要说清，不能静默
            self._toast("error", "改名失败", f"{type(exc).__name__}: {exc}")
            return
        if changed:
            record = self.store.get_task(self.task_id) or {}
            self.detail_title.setText(str(record.get("name") or typed))
            self._toast("info", "已改名", f"任务名称已改为「{typed}」")

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt 命名
        """任务名输入框里按 Esc = 放弃编辑（不改盘上）。

        ⚠️ ``return False`` 而不是 ``super().eventFilter(...)``：本类是
        Mixin，``super()`` 后面未必有实现 ``eventFilter`` 的类（对象默认
        没有这个方法）⇒ 调 ``super().eventFilter`` 会 AttributeError。
        返回 False = "不拦截，事件照常交给控件"，正是我们要的。
        """
        # ⚠️ ``QKeyEvent`` 在 **QtGui**（QtCore 里只有 ``QEvent`` 枚举与
        # ``Qt``），从 QtCore import 会 ImportError（自测一跑就炸）。
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent

        if (watched is self.rename_edit
                and event.type() == QEvent.KeyPress
                and isinstance(event, QKeyEvent)
                and event.key() == Qt.Key_Escape):
            # ⚠️ **先清文本再失焦**：``clearFocus`` 会触发 ``editingFinished``
            # → ``_commit_rename``，那里看到非空文本就会**真的存下去**，
            # Esc 等于"改名并保存"，与预期相反。
            self.rename_edit.clear()
            self.rename_edit.clearFocus()
            return True
        return False

    def _build_step_bar(self) -> StepBar:
        # 步骤条自带卡片底（paintEvent 绘制），不再套一层 Card，避免"卡片套卡片"
        # ⚠️ **记下这份槽位快照**（2026-10-06）：重建时要用**它**把旧下标解析成
        #    步骤 key。解析"旧高亮在哪一步"绝不能去问 ``flow_slots()``——那读的是
        #    磁盘上那张（可能已经改过的）新流程图，旧格序会被解释成新格序，
        #    高亮就默默挪到了别的步骤上。快照是"这条步骤条**当时**按哪张图建的"
        #    唯一可靠凭据。
        self._step_bar_slots = self.flow_slots()
        self.step_bar = StepBar(
            self._bar_step_titles(), optional_after=self._optional_after_index(),
            unmapped=self._unmapped_step_indices(),
            # ⚠️ 下标只有一种语义＝格序 bar_index（MEMORY「三套下标」第①种）。
            #    少传这一张映射表，StepBar 就会退回"真实步骤序"，于是点「生成
            #    PDF」打开的是「图片拼版」、它的状态也永远上不了屏。
            bar_indices=self._bar_step_indices(),
            optional_bar_index=self._optional_bar_index(),
        )
        self.step_bar.current_changed.connect(self._select_stage)
        # 「图片拼版」虚线节点：点击切到可选节点的占位详情（ImpositionMixin）
        self.step_bar.imposition_clicked.connect(self._select_optional_node)
        return self.step_bar

    def _bar_step_titles(self) -> list[str]:
        """步骤条上**真实步骤**的标题序列（按本任务流程顺序）。

        可选节点（拼版）**不在这里**——它由 :class:`StepBar` 按
        ``optional_after`` 插进去；这里只给真实步骤，顺序取槽位表的
        ``bar_index``。构造期还没有任务（``flow_slots`` 回落默认流程），
        此时就是默认流程的步骤序列。
        """
        slots = sorted(
            (s for s in self.flow_slots() if not s.optional),
            key=lambda s: s.bar_index,
        )
        return [s.label for s in slots]

    def _bar_step_indices(self) -> list[int]:
        """真实步骤序列里每一格的**格序 ``bar_index``**（喂 :class:`StepBar`）。

        ⚠️ 与 :meth:`_bar_step_titles` **同序同长**（都过滤掉可选节点），
        两者按下标一一对应。序数 ≠ 格序：默认流程里「生成 PDF」序数 3 而
        格序 4（拼版占了第 3 格），两者混用就是"点一个步骤打开另一个步骤"。
        """
        slots = sorted(
            (s for s in self.flow_slots() if not s.optional),
            key=lambda s: s.bar_index,
        )
        return [s.bar_index for s in slots]

    def _optional_bar_index(self) -> int | None:
        """拼版节点自己的格序（``None`` = 本流程没有这一格）。"""
        for slot in self.flow_slots():
            if slot.optional and slot.step == IMPOSITION_STAGE:
                return slot.bar_index
        return None

    def _unmapped_step_indices(self) -> set[int]:
        """步骤条上"图上有、但还没有功能"的下标集合（2026-10-05）。

        口径 = 槽位表里 ``mapped=False`` 的那些格（真实步骤序列里的下标）。
        它们仍占格子，只是画成灰色并标注"未接入"——用户能在流程图上画任意
        节点，界面上就必须**看得见**那一步，否则"改了流程图没反应"。

        ⚠️ 只算**真实步骤**（``optional`` 的拼版不算），下标要与
        :meth:`_bar_step_titles` 的序列一致——那个序列过滤掉了可选节点。
        """
        return {i for i, slot in enumerate(
            (s for s in self.flow_slots() if not s.optional))
            if not slot.mapped}

    def _optional_after_index(self) -> int | None:
        """可选节点插在**第几个真实步骤之后**（喂 :class:`StepBar`）。

        口径与算法都在 :meth:`FlowDiagram.optional_after`（⚠️ 那是
        "真实步骤列表里的下标"，**不是**槽位表的 ``bar_index``——后者含了
        可选节点自己占的格子，两者不相等）。本流程没有可选节点时返回
        ``None``。
        """
        if not getattr(self, "task_id", None):
            # 没任务时按**默认模板**算（静态展示）。⚠️ 此前这里是
            # ``FlowDefinition.default().optional_after(...)``——那是**旧模型**
            # 从端口边表派生的一份流程，与 ``FlowDiagram.optional_after``
            # 算法不同；模板文件缺失时两条路会给出不同的插入位（步骤条上
            # 拼版节点与槽位表对不上）。
            from desktop.steps.scheduler import load_default_diagram

            return load_default_diagram().optional_after(IMPOSITION_STAGE)
        # ⚠️ 走**图模型**（能读 bpmn.io 的网关/自定义 id）；旧 `task_flow`
        #    读不了就静默回落默认流程 ⇒ 步骤条永远长的像 task_default。
        return self.store.task_diagram(self.task_id).optional_after(
            IMPOSITION_STAGE)

    @staticmethod
    def _step_key_at(slots, bar_index: int) -> str | None:
        """**给定**槽位表里第 ``bar_index`` 格的步骤 key；没有这一格返回 ``None``。

        ⚠️ 为什么要单独一个"吃 slots 的"版本：解析"旧步骤条的 ``_current``
        到底是哪一步"时，**不能**用 :meth:`flow_slots`（它读磁盘上那张图，
        而磁盘已经是**新**流程了），必须用**旧步骤条建时那份**槽位。
        """
        for slot in slots or ():
            if slot.bar_index == bar_index:
                return slot.step
        return None

    def _rebuild_step_bar(self) -> None:
        """按**当前任务流程**重建步骤条（BPM 驱动）。

        步骤条在 ``_init_ui`` 期间就建好了，那时还没有任务、只能按默认流程
        排；``set_task`` 拿到 ``task_id`` 后本任务可能是自定义流程（换了步骤
        顺序或把可选节点排到别处），这时重建一次，让步骤条与流程一致。

        ⚠️ 必须重建**而不是只改标题**：可选节点的位置
        （``optional_after``）决定布局插入点与连接线/绕行线的几何，改标题
        改不动它们。
        ⚠️ 重建会丢当前高亮与完成态，所以先把它们按**步骤 key** 存下来，
        重建后按新流程的格序恢复（换流程后某一步可能被删，匹配不上就回第
        一格——那里是流程的入口，缺上游也不该从中间起跑）。
        """
        old_bar = getattr(self, "step_bar", None)
        if old_bar is None:
            return
        # ⚠️⚠️ **用旧步骤条自己记的那份槽位解析旧下标**（2026-10-06 用户报障
        #    "顶部流程图编辑后不立即更新"）。这里**不能**调 ``flow_slots()``：
        #    它读的是**磁盘上那张新流程图**，而 ``old_bar._current`` 是**旧
        #    流程**的格序——两者语义已经错位。实测：停在「图片去底色」（旧格序
        #    2），删掉「提取图片」后它在新流程里是格序 1，用新表查旧下标 2
        #    得到的是「图片拼版」⇒ 重建完高亮默默挪到了别的步骤上，用户看着
        #    就是"步骤条没更新"。完成态 ``_completed`` 同理（存的是旧格序）。
        old_slots = getattr(self, "_step_bar_slots", None)
        if not old_slots:
            # 没有记录（构造期的第一条）：退回按当前表解析，最坏退回第一格
            old_slots = self.flow_slots()
        current_step = self._step_key_at(old_slots, old_bar._current)
        completed_steps = [
            s.step for s in old_slots
            if not s.optional and s.bar_index in old_bar._completed
        ]
        # ⚠️ 先把旧步骤条从根布局里摘掉再换新的，否则两个步骤条叠在一起
        #    （旧控件还占着位置、只是被遮住，自测里的几何断言会全错）。
        #    ⚠️ 不能用 ``replaceWidget(old, None)``——传 None 给它会抛
        #    ``addLayoutOwnership`` 的 RuntimeError（Qt 不接受 None 接管布局项）。
        root = getattr(self, "_root_layout", None)
        if root is not None:
            root.removeWidget(old_bar)
            old_bar.setParent(None)
            old_bar.deleteLater()
        self.step_bar = self._build_step_bar()
        if root is not None:
            row = getattr(self, "_step_bar_row", 1)
            root.insertWidget(row, self.step_bar)
        for slot in self.flow_slots():
            if slot.optional or slot.step not in completed_steps:
                continue
            self.step_bar.mark_completed(slot.bar_index)
        if current_step is not None:
            index = self.bar_index_of_step(current_step)
            self.step_bar.set_current(0 if index is None else index)

    def _select_optional_node(self) -> None:
        """点了「图片拼版」虚线节点 → 切到它在本流程里的那一格。"""
        index = self.bar_index_of_step(IMPOSITION_STAGE)
        if index is not None:
            self._select_stage(index)

    def _build_preview_card(self) -> Card:
        card = Card(padding=T.SPACE_SM, spacing=0, radius=T.RADIUS_MD)
        card.box.addWidget(self._build_preview_stack())
        return card

    def _build_preview_stack(self) -> QStackedWidget:
        self.preview_stack = QStackedWidget()
        # extract：双标签页
        self.extract_tabs = QTabWidget()
        self.source_pdf_viewer = PdfViewerWidget("尚未导入 PDF")
        self.source_pdf_viewer.page_count_changed.connect(self._pdf_page_count_ready)
        self.extract_tabs.addTab(self.source_pdf_viewer, "PDF 预览")
        self.extract_result_viewer = ImageViewerWidget(
            editable=True, empty_hint="尚未提取，点击右侧「执行本子任务」",
            thumb_provider=self._page_thumb_for,
        )
        self.extract_result_viewer.current_changed.connect(self._image_selected)
        self.extract_result_viewer.delete_requested.connect(self.delete_selected_page)
        self.extract_result_viewer.insert_requested.connect(self.insert_pages)
        # 「选文件夹」：文件对话框选不了目录，整目录导入必须走这条（2026-10-06）
        self.extract_result_viewer.insert_folder_requested.connect(
            self.insert_pages_from_folder)
        self.extract_tabs.addTab(self.extract_result_viewer, "提取结果")
        self.preview_stack.addWidget(self.extract_tabs)

        # detect：图片 + 检测框
        # ⚠️ 空态文案**不写死"请先完成提取"**（用户2026-10-06）：自定义流程
        #    可能把这一步放在第一位、压根没有提取这一步可完成，那时这句话
        #    会把用户引到一个不存在的目标上。统一说"插入图片/文件夹"，
        #    对有无上游都成立。
        self.detect_viewer = ImageViewerWidget(
            editable=True, show_boxes=True,
            empty_hint="暂无图片，请点下方「＋」插入图片或整个文件夹，"
                       "或把图片放进本任务的输入目录",
            image_size_provider=self._original_image_size,
            thumb_provider=self._page_thumb_for,
        )
        self.detect_viewer.current_changed.connect(self._detect_image_selected)
        self.detect_viewer.delete_requested.connect(self.delete_selected_page)
        self.detect_viewer.insert_requested.connect(self.insert_pages)
        self.detect_viewer.insert_folder_requested.connect(
            self.insert_pages_from_folder)
        self.detect_viewer.boxes_edited.connect(self._save_manual_boxes)
        # 编辑器「完成」覆盖原图后：同步 sizes.json/缩略图并刷新显示
        self.extract_result_viewer.image_saved.connect(self._on_page_image_saved)
        self.detect_viewer.image_saved.connect(self._on_page_image_saved)
        self.preview_stack.addWidget(self.detect_viewer)

        # rembg：原图/结果对比
        self.rembg_viewer = RembgPreviewWidget()
        self.rembg_viewer.image_saved.connect(self._on_page_image_saved)
        self.preview_stack.addWidget(self.rembg_viewer)

        # print：左缩略图条 + 右「打印效果」预览（可拖动排序/删除/插入）
        # ⚠️ params_provider 必须传：缺了它预览永远显示"未接入打印参数，已显示原图"，
        # 标题/页码/纸张效果一概看不到（组件自测传了参数，测不出宿主漏接线）。
        self._print_dirty = False  # 版面编辑器改过坐标、尚未重新生成 PDF
        #: 已生成的 PDF 是否已因**取图来源换掉**（拼版开关）而作废。缓存，
        #: 由 ``_refresh_stale_notices`` 重算（见 page.py）——状态行经
        #: ``_regenerate_notice`` 在执行期间每 ≤200ms 读它，不能现算。
        self._print_source_stale = False
        self.print_preview = PrintPreviewWidget(
            empty_hint="暂无图片，请先在第三步「生成预览」并「提交本次任务」",
            params_provider=self._print_params,
            # 提交阶段预生成的缩略图（thumbnails/print）：不再对每条目现解码
            # 6000px 原图（2026-09-27 用户反馈第四步缩略图渲染慢）
            thumb_provider=self._print_thumb_provider,
        )
        self.print_preview.order_changed.connect(self._save_print_order)
        self.print_preview.insert_requested.connect(self._insert_print_images)
        self.print_preview.download_requested.connect(self._download_print_pdf)
        # 编辑器覆盖了某张待打印图：记日志提示「点生成 PDF 即生效」
        self.print_preview.image_saved.connect(self._on_page_image_saved)
        # 单页导出：当前页排进 A4 后的效果图（精度与 PDF 同级 300dpi）
        self.print_preview.export_image_requested.connect(self._export_print_image)
        self.print_preview.export_finished.connect(self._on_export_finished)
        self.print_preview.export_failed.connect(self._on_export_failed)
        # 单页打印：同一份 A4 效果渲染，交系统打印对话框
        self.print_preview.print_finished.connect(self._on_print_finished)
        self.print_preview.print_failed.connect(self._on_print_failed)
        # 版面编辑：某一页图片坐标被拖拽/缩放后落盘 print.json 并标脏
        self.print_preview.layout_changed.connect(self._on_print_layout_changed)
        self.print_preview.hint.connect(
            lambda message: self._toast("info", "提示", message)
        )
        self.preview_stack.addWidget(self.print_preview)

        # 拼版伪步骤（index 4）：左列拼版页 + 右侧拼版操作画布
        self.preview_stack.addWidget(self._build_imposition_preview())
        return self.preview_stack

    def _build_imposition_preview(self) -> Card:
        """「图片拼版」页面：左侧拼版页清单（模块一）+ 右侧操作画布（模块二）。

        左列是「第一页 / 第二页 / …」加末尾一个**虚线**「＋ 选择拼版」；
        右侧画布可拖动 / 缩放拉伸 / 旋转当前页的两张图。业务动作全部委托给
        拼版控制器（``imposition.py`` 基元 + ``imposition_pages`` /
        ``imposition_layout`` 两模块的 Mixin）。
        """
        card = Card(padding=T.SPACE_SM, spacing=0, radius=T.RADIUS_MD)
        self.imposition_view = ImpositionViewWidget()
        self.imposition_view.page_selected.connect(
            self._on_imposition_page_selected
        )
        self.imposition_view.add_requested.connect(
            self._on_imposition_add_requested
        )
        self.imposition_view.page_reorder_requested.connect(
            self._on_imposition_page_reorder
        )
        self.imposition_view.page_remove_requested.connect(
            self._on_imposition_release_page
        )
        self.imposition_view.pages_batch_delete_requested.connect(
            self._on_imposition_batch_delete
        )
        self.imposition_view.items_changed.connect(
            self._on_imposition_items_changed
        )
        self.imposition_view.slot_selected.connect(
            self._on_imposition_slot_selected
        )
        self.imposition_view.item_preview_requested.connect(
            self._open_imposition_item_preview
        )
        self.imposition_view.spread_preview_requested.connect(
            self._open_imposition_spread_preview
        )
        self.imposition_view.item_edit_requested.connect(
            self._open_imposition_item_edit
        )
        self.imposition_view.spread_edit_requested.connect(
            self._open_imposition_spread_edit
        )
        card.box.addWidget(self.imposition_view)
        return card

    def _build_imposition_panel(self) -> Card:
        """「图片拼版」详情面板（模块二的右侧控制区，控件实体在
        ``desktop/components/imposition/panel.py``），这里只接线。

        启用开关决定**第四步的取图来源**：勾选且有拼版页时，生成 PDF 用拼版
        结果，否则回到第三步的去底色产物（见 ``print_source_dir``）。
        """
        panel = ImpositionPanel()
        panel.enabled_toggled.connect(self._on_imposition_enabled_toggled)
        panel.whole_rotate_delta.connect(self._on_imposition_whole_rotate)
        panel.item_rotation_edited.connect(self._on_imposition_item_rotate)
        panel.reset_requested.connect(self._on_imposition_reset_layout)
        # 「新增图片」（单图页才出现）/「删除选中图片」（选中图才出现的按钮）
        panel.add_image_requested.connect(self._on_imposition_add_image)
        panel.item_delete_requested.connect(self._on_imposition_delete_item)
        panel.clear_requested.connect(self._on_imposition_clear)
        self.imposition_panel = panel
        # 既有控制器/自测沿用的宿主别名（控件实体在 panel 里）
        self.imposition_enabled_checkbox = panel.enabled_checkbox
        self.imposition_panel_status = panel.status_label
        return panel

    def _build_control_card(self) -> QWidget:
        card = Card(padding=T.SPACE_MD, spacing=T.SPACE_MD, radius=T.RADIUS_MD)
        column = card.box

        self.control_stack = QStackedWidget()
        # ⚠️ **四个阶段面板全部惰性**（2026-09-25 用户要求：进详情只建第一步，
        # 第 2/3/4 步"谁进去谁才建"）。面板构造是纯 Qt + Python 密集活：第四步
        # print_panel 单项就 ~150ms（空闲机器），是详情页构造的大头；而机器若
        # 正在跑导入后台（PyMuPDF 连续攥 GIL），同样的代码会被拖成 ~2 秒。
        # 用户可能整场都不点某一步，不该为它买单。
        # 接线一律走 LazyPanelHost 的 created 回调（hooks），**绝不在构造期
        # 直接 `widget(i)` 取面板**——属性转发会立刻把它建出来，惰性就白做了。
        _HOOKS = {
            "detect": self._wire_detect_panel,
            "rembg": self._wire_rembg_panel,
            "print": self._wire_print_panel,
        }
        # ⚠️ 接线**按步骤 key**，不按 ``PANEL_CLASSES`` 的下标：那张元组与
        # ``FLOW_STAGES`` 同序（都由 ``SPECS`` 的 ``role=="stage"`` 派生），
        # 下标在这里只是巧合——``SPECS`` 前面插一个 stage，三个钩子会**集体
        # 错位一格**（rembg 的联动刷新接到 print 上），且没有任何报错。
        for index, panel_class in enumerate(PANEL_CLASSES):
            key = FLOW_STAGES[index] if index < len(FLOW_STAGES) else None
            hook = _HOOKS.get(key)
            self.control_stack.addWidget(
                LazyPanelHost(panel_class, hooks=[hook] if hook else [])
            )
        # 拼版伪步骤（追加在主链之后）：占位详情面板——只在流程条点了虚线节点时
        # 显示，不属于任何真实阶段（STAGES/runs 机制不感知它）
        self.control_stack.addWidget(self._build_imposition_panel())
        column.addWidget(self.control_stack, 1)
        # 第二步右侧的「检测结果统计」：只在 detect 阶段显示（见 _select_stage），
        # 位置就是其它步骤「执行记录」的那块——执行记录对 detect 无用（无表单
        # 参数可回填，用户 2026-09-29 定），这一步改显统计。
        self.detect_stats = DetectStatsWidget()
        self.detect_stats.page_clicked.connect(self._goto_stats_page)
        self.detect_stats.hide()
        column.addWidget(self.detect_stats)
        # 边距级联的挂起值：print 面板还没建时先把当前值记下来（见
        # _sync_print_margin_default 与 _wire_print_panel）
        self._pending_print_border = None
        self._sync_print_margin_default()
        # 第四步面板建好时补「按源 PDF 名派生默认 PDF 名/古籍名」：set_task 只
        # 记下 _pending_source_stem，**不强制构造面板**（见 page.set_task）
        print_host = self.panel_host_of_step("print")
        if print_host is not None:
            print_host.add_created_hook(self._apply_pending_source_defaults)
            # 同理补「切任务时挂起的第四步状态复位」
            self._pending_print_reset = False
            print_host.add_created_hook(self._apply_pending_print_reset)

        column.addWidget(Divider())
        self._build_history_controls(column)
        column.addWidget(Divider())
        self._build_run_controls(column)

        # 控制面板限宽：参数表单需要舒适宽度，第四步 YAML 编辑器尤甚
        self.control_widget = card
        self._apply_control_width()
        return self.control_widget

    def _wire_detect_panel(self, detect_panel) -> None:
        """第二步面板**首次构造后**的接线（LazyPanelHost 的 created 回调）。"""
        # detect 面板「检测本页」：手动触发当前页的 YOLO 检测（不自动执行）
        detect_panel.detect_page_requested.connect(self._detect_current_page)
        # 整页模式：等价于把第三步 area 切到 4（跳过 YOLO，整页作为一个框）
        detect_panel.whole_page_toggled.connect(self._set_whole_page_mode)
        # 人工干预：选中框类型（左框/右框/整幅）与删除选中框
        detect_panel.box_kind_changed.connect(self._set_selected_box_kind)
        detect_panel.delete_box_requested.connect(self._delete_selected_box)
        # 预览里点/删/画框会改变选中态 → 回填面板的「选中框类型」高亮
        self.detect_viewer.selection_changed.connect(self._on_box_selection_changed)
        # 超框数上限（整幅 1 个 / 半幅 2 个）时给出可操作的提示
        self.detect_viewer.box_edit_rejected.connect(self._on_box_edit_rejected)

    def _wire_rembg_panel(self, rembg_panel) -> None:
        """第三步面板**首次构造后**的接线（LazyPanelHost 的 created 回调）。"""
        # ⚠️ 联动刷新必须**去抖**（2026-09-26 第二轮审计 GUI-H1）：textChanged/
        #    valueChanged 是逐字符/逐格触发，而一次联动 = 全量 boxes.json × N 页
        #    重读（_refresh_reference_boxes → _build_entries 逐页查 detect_cache）
        #    + runs.json × 3 次读 + 目录扫描（_update_submit_button）。大任务上
        #    逐字符输入明显卡顿。200ms 防抖与第四步 _print_preview_timer 同法。
        self._rembg_panel_timer = QTimer(self)
        self._rembg_panel_timer.setSingleShot(True)
        self._rembg_panel_timer.setInterval(200)
        self._rembg_panel_timer.timeout.connect(self._on_rembg_panel_refresh)

        def _on_rembg_panel_changed(*_):
            self._rembg_panel_timer.start()

        # rembg 面板的参数变化决定检测框标注与去底色预览区域，联动刷新
        rembg_panel.area.currentTextChanged.connect(_on_rembg_panel_changed)
        rembg_panel.border.textChanged.connect(_on_rembg_panel_changed)
        # 去底参数变化会改变预览图 → 「提交」按钮的新版本提示需实时刷新
        rembg_panel.type.currentTextChanged.connect(_on_rembg_panel_changed)
        rembg_panel.offset.valueChanged.connect(_on_rembg_panel_changed)
        rembg_panel.seal.toggled.connect(_on_rembg_panel_changed)
        rembg_panel.sealcolor.toggled.connect(_on_rembg_panel_changed)
        rembg_panel.sealarea.valueChanged.connect(_on_rembg_panel_changed)
        rembg_panel.sealmin_sat.valueChanged.connect(_on_rembg_panel_changed)
        # 面板建好时补一次当前 border（构造前它拿不到级联值）
        self._on_rembg_panel_refresh()

    def _on_rembg_panel_refresh(self) -> None:
        """第三步参数联动刷新（已去抖）：checkbox 回填 / 框标注 / 提交按钮 / 级联。"""
        # area 可能被第二步的整页开关改动，勾选状态需回填
        self._sync_whole_page_checkbox()
        self._refresh_reference_boxes()
        self._update_submit_button(
            bool(self.process and self.process.state() != QProcess.NotRunning)
        )
        # 第三步 border 级联第四步默认边距：border 变化时把上游 border
        # 同步给 print 面板（用户未手动改边距时，默认值随级联变 0/20）
        self._sync_print_margin_default()
        # ⚠️ 拼版节点的**可见性不看这里的参数**（2026-10-05 起只看流程图）；
        #    但这一步仍会牵动「选择/生效态」的显示，顺手同步一次（幂等）。
        self._refresh_imposition_node()

    def _wire_print_panel(self, panel) -> None:
        """第四步面板**首次构造后**的接线（LazyPanelHost 的 created 回调）。"""
        # 参数变化 → 效果预览按新参数重画（只是重画内存位图，不执行、不提交、
        # 不生成 PDF）。防抖 250ms：边距/颜色是逐字符输入，每次都重载一遍大图
        # 会明显卡顿。
        self._print_preview_timer = QTimer(self)
        self._print_preview_timer.setSingleShot(True)
        self._print_preview_timer.setInterval(250)
        self._print_preview_timer.timeout.connect(self.print_preview.refresh_display)
        panel.params_changed.connect(self._print_preview_timer.start)
        # 补一次"面板还没建时"挂起的边距级联
        try:
            panel.set_upstream_border(getattr(self, "_pending_print_border", None))
        except Exception:
            pass

    def _print_params(self) -> dict:
        """第四步打印参数（供「打印效果」预览）：直接读面板表单。

        颜色/边距填到一半时 ``get_args()`` 会抛 ValueError，这里**不吞**——
        由 ``PrintPreviewWidget`` 捕获后退回「原图」并在说明行给出原因，
        避免用户每敲一个字符就弹窗。
        """
        host = self.panel_host_of_step("print")
        if host is None:
            # 本流程没有「生成 PDF」这一格：没有表单可读（调用方会把预览退回
            # 「原图」，不该拿别的面板的参数冒充打印参数）
            raise ValueError("当前流程里没有「生成 PDF」这一步")
        return host.get_args()

    def _apply_pending_source_defaults(self, panel=None) -> None:
        """把「当前任务的源 PDF 名」派生的默认值补给第四步面板。

        ⚠️ 面板是惰性的：``set_task`` 只记下 ``_pending_source_stem``，真正应用
        由本方法负责——面板已建就立刻用，没建就等 created 回调在它建好时调用。
        """
        stem = getattr(self, "_pending_source_stem", None)
        if not stem:
            return
        if panel is None:
            host = self.panel_host_of_step("print")
            if host is None:
                return
            peek = getattr(host, "peek", None)
            panel = peek() if callable(peek) else host
        if panel is None:
            return
        try:
            panel.set_source_defaults(stem)
        except Exception:  # noqa: BLE001 - 面板版本差异不该影响进任务
            pass

    def _apply_pending_print_reset(self, panel=None) -> None:
        """清掉第四步面板上「属于上一个任务」的已应用参数快照。

        ⚠️ 为什么需要（2026-09-26 审计）：`print_panel._last_applied` 是「放弃本次
        修改」的回填源。切任务时不清，在任务 B 点「放弃本次修改」会把**任务 A 的
        参数**（含 A 派生的 pdf_name / title_text）回填进 B 的表单，后续可能用 A 的
        名字生成 B 的 PDF。

        与 `_apply_pending_source_defaults` 同一套惰性惯例：`set_task` 只置
        `_pending_print_reset`，**不强制构造面板**；面板已建就立刻清，没建就等
        它被建出来时由这里的 created 回调清。
        """
        if not getattr(self, "_pending_print_reset", False):
            return
        if panel is None:
            host = self.panel_host_of_step("print")
            if host is None:
                return
            peek = getattr(host, "peek", None)
            panel = peek() if callable(peek) else host
            if panel is None:
                return  # 还没建：留着标记，等 created 回调
        try:
            panel._last_applied = None
        except Exception:  # noqa: BLE001 - 面板版本差异不该影响切任务
            return
        self._pending_print_reset = False

    def _sync_print_margin_default(self) -> None:
        """把第三步 rembg 面板的当前 border 同步给第四步面板做默认级联。

        读取 rembg 面板的 border 原始文本（不触发其 get_args 校验，避免
        填写中途的非法值抛错），交给 print 面板自行决定是否覆盖默认边距。
        """
        try:
            rembg_host = self.panel_host_of_step("rembg")
            # ⚠️ 必须用 peek()（不触发构造）：第三步面板没建时它的 border 就是
            # 默认空值，等它建好会由 _wire_rembg_panel 补一次同步。
            # ⚠️ 流程里没有去底色这一格 ⇒ 没有 border 可级联，按"无上游"处理。
            rembg_peek = getattr(rembg_host, "peek", None)
            if callable(rembg_peek):
                rembg_panel = rembg_peek()
                border = (
                    (rembg_panel.border.text() or "").strip() or None
                    if rembg_panel is not None
                    else None
                )
            elif rembg_host is None:
                border = None
            else:
                border = (rembg_host.border.text() or "").strip() or None
        except Exception:
            border = None
        host = self.panel_host_of_step("print")
        if host is None:
            return
        peek = getattr(host, "peek", None)
        panel = peek() if callable(peek) else host
        if panel is None:
            # 第四步面板还没构造：先记住，等它建好时由 _wire_print_panel 补同步。
            # ⚠️ 这里绝不能走属性转发——rembg 参数一变就会把它建出来，
            #    惰性就白做了。
            self._pending_print_border = border
            return
        try:
            panel.set_upstream_border(border)
        except Exception:
            pass

    def _on_print_layout_changed(self, index: int, rect: list) -> None:
        """版面编辑器改了某页坐标：落盘 print.json 并标脏，提示可重新生成 PDF。

        落盘走 ``_save_print_order``（直接序列化当前条目，rect 已随条目携带），
        下次点「生成 PDF」时 runner 会从 print.json 收集 page_rects 注入生成。
        """
        if not self.task_id:
            return
        self._save_print_order(silent=True)  # 拖拽频繁落盘，不打列表日志
        self._print_dirty = True
        # 与"上游已重跑"共用同一套产出（文案 + 警示色），避免两处各写一份；
        # 下一次 _refresh_stage_views 也由 _regenerate_notice 把它重新显出
        self._set_stage_status("● 版面已修改，点击「生成 PDF」生效", alert=True)
        rx, ry, rw, rh = (list(rect) + [0, 0, 0, 0])[:4]
        self.log_view.append(
            f"第 {index + 1} 页版面已更新（x={rx:.0f}, y={ry:.0f}, "
            f"w={rw:.0f}, h={rh:.0f} mm），点击「生成 PDF」生效"
        )

    def _build_history_controls(self, control: QVBoxLayout) -> None:
        # ---- 历史执行配置选择（detect 阶段整体隐藏，见 _select_stage）----
        # ⚠️ 必须包成独立 block 再整体 setVisible：散着藏的话，切到第二步要
        #    记住藏三个控件，漏一个就露出半截「执行记录」。
        self.history_block = QWidget()
        block = QVBoxLayout(self.history_block)
        block.setContentsMargins(0, 0, 0, 0)
        block.setSpacing(T.SPACE_SM)
        block.addWidget(SectionTitle("执行记录"))
        self.history_caption = CaptionLabel("历史执行配置（选择后回填到表单）")
        apply_to(self.history_caption, T.SIZE_CAPTION, color=T.INK_FAINT)
        block.addWidget(self.history_caption)
        self.history_combo = self._make_history_combo()
        block.addWidget(self.history_combo)
        control.addWidget(self.history_block)

        self.stage_status = CaptionLabel("未执行")
        apply_to(self.stage_status, T.SIZE_CAPTION, color=T.INK_SOFT)
        control.addWidget(self.stage_status)
        # 细进度条：只表达"执行到多少页"，不抢视觉
        self.stage_progress = ProgressLine()
        control.addWidget(self.stage_progress)

    def _make_history_combo(self) -> ComboBox:
        combo = combo_box()
        combo.currentIndexChanged.connect(self._on_history_selected)
        return combo

    def _build_run_controls(self, control: QVBoxLayout) -> None:
        self.run_button = PrimaryPushButton(FIF.PLAY, "执行本子任务")
        self.run_button.setFixedHeight(36)
        self.run_button.clicked.connect(lambda: self.run_stage(resume=False))
        # 步骤三（rembg）专用：把预览结果按 area/border 合成为最终图片
        # ⚠️ 文案取 SUBMIT_TEXT（submit.py 的唯一来源）：并排一行后放不下
        #    更长的写法，"有新版本"由加粗 + 下方红字提示表达。
        self.submit_button = PrimaryPushButton(FIF.ACCEPT, SUBMIT_TEXT)
        self.submit_button.setFixedHeight(36)
        self.submit_button.setToolTip(
            "将「生成预览」的去底色图片按「区域模式 / 边距」合成为真正想要的最终图片"
        )
        self.submit_button.clicked.connect(self.run_rembg_submit)
        self.submit_button.setVisible(False)
        # 「生成预览 / 提交本次任务」并排一行：第三步的这两件事是**同一段动作的
        # 前后两跳**（先看效果、再落地成最终图），竖着堆叠会让人误以为是两个
        # 步骤。与「继续执行 / 中断执行」同一理由。
        # ⚠️ 没有提交按钮的步骤（1/2/4）只有 run_button 可见，stretch=1 让它
        #    自动占满整行，视觉与并排前一致。
        # ⚠️ 整行包进独立 QWidget（与 followup_row 同理）：拼版详情页要整组隐藏
        #    执行按钮（`_select_imposition_detail`），用 addLayout 的话行高仍在，
        #    控制区底部会留一条空白。
        self.action_row = QWidget()
        action = QHBoxLayout(self.action_row)
        action.setContentsMargins(0, 0, 0, 0)
        action.setSpacing(T.SPACE_SM)
        action.addWidget(self.run_button, 1)
        action.addWidget(self.submit_button, 1)
        # 新版本提示：生成预览参数/结果变化后、提交前常驻提醒（位于提交按钮下方）
        self.submit_hint = CaptionLabel("")
        self.submit_hint.setWordWrap(True)
        apply_to(self.submit_hint, T.SIZE_CAPTION)
        self.submit_hint.hide()
        # 「继续执行 / 中断执行」并排一行：两者是同一时刻的两种后续动作
        # （没跑完 → 继续；跑着 → 中断），上下堆叠会让人误以为是两个步骤。
        # 「跳过已完成」这层含义降级到 tooltip，按钮上只留动词。
        # ⚠️ 整行包进独立 QWidget：拼版详情页要整组隐藏（见
        #    ``_select_imposition_detail``），只藏两个按钮的话行高仍在，
        #    控制区底部会留一条空白。
        self.followup_row = QWidget()
        row = QHBoxLayout(self.followup_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(T.SPACE_SM)
        self.resume_button = PushButton(FIF.UPDATE, "继续执行")
        self.resume_button.setFixedHeight(34)
        self.resume_button.setToolTip("跳过已完成的页，只补做剩下的")
        self.resume_button.clicked.connect(lambda: self.run_stage(resume=True))
        self.cancel_button = PushButton(FIF.CLOSE, "中断执行")
        self.cancel_button.setFixedHeight(34)
        self.cancel_button.setToolTip("立刻停止当前正在执行的子任务")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_stage)
        row.addWidget(self.resume_button, 1)
        row.addWidget(self.cancel_button, 1)
        control.addWidget(self.action_row)
        control.addWidget(self.submit_hint)
        control.addWidget(self.followup_row)

    # ------------------------------------------------------------------ 宽度
    def _apply_control_width(self) -> None:
        """按当前阶段调整右侧控制面板宽度：**查 spec**（不再 `if stage == "print"`）。

        第四步参数最多（版面/页码/字体…），要更宽的编辑区；其余步骤用 340~440px
        的舒适表单宽度（标签不折行、输入框不被压扁）。区间由
        ``StepSpec.control_width`` 声明，加一步要更宽只改它的 spec。
        """
        from desktop.steps import ports
        from desktop.steps.spec import StepSpec

        spec = ports.spec_for_stage(self.current_stage())
        minimum, maximum = (
            spec.control_width if spec else StepSpec().control_width
        )
        self.control_widget.setMinimumWidth(minimum)
        self.control_widget.setMaximumWidth(maximum)
