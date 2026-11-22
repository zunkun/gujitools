# -*- coding: utf-8 -*-
"""页头组装、任务改名与 Esc 取消（从原 ``view.py`` 拆出）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from qfluentwidgets import PushButton, ToolButton
from qfluentwidgets import FluentIcon as FIF

from desktop.components.log_panel import LogPanel
from desktop.ui import theme as T
from desktop.ui.icons import PDF_FILE
from desktop.ui.widgets import Card, apply_to, mark_input_entry

from desktop.pages.taskdetail.view._qt import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QObject,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from desktop.pages.taskdetail.view._host import DetailViewHost
else:
    DetailViewHost = object


class DetailHeaderMixin(DetailViewHost):
    """页头卡片、根布局与任务名行内编辑。"""
    # ------------------------------------------------------------------ 组装
    def _init_ui(self) -> None:
        # ⚠️ Mixin 里 self 的静态类型不是 QWidget；宿主 TaskDetailPage 必是
        #    QWidget，cast 只是给类型检查看的（运行时原样返回）。
        root = QVBoxLayout(cast("QWidget", self))
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
        #    用户 2026-10-18：从"纯图标"改成**图标 + 文字**（打开任务目录），
        #    且打开目标从**任务根目录**改成**当前流程节点**的产物目录。
        self.task_dir_button = PushButton(FIF.FOLDER, "打开任务目录")
        self.task_dir_button.setToolTip("打开当前任务节点的数据目录")
        self.task_dir_button.clicked.connect(self._open_task_dir)
        self.log_panel.set_task_dir_action(self.task_dir_button)
        root.addWidget(self.log_panel)

        self._update_run_buttons()

    def _build_header(self) -> Card:
        card = Card(padding=0, spacing=0, radius=T.RADIUS_MD, layout="h")
        row = card.box
        row.setContentsMargins(T.SPACE_MD, T.SPACE_SM, T.SPACE_MD, T.SPACE_SM)
        row.setSpacing(T.SPACE_MD)

        self.back_button = ToolButton(FIF.RETURN)
        self.back_button.setToolTip("返回任务列表")
        self.back_button.setFixedSize(34, 34)
        self.back_button.clicked.connect(self._on_back)
        row.addWidget(self.back_button)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(1)
        # 任务名 + 任务编号同一行：编号是任务的**主键**（任务目录名，创建后
        # 不变），与可随时改名的任务名不是一回事。用淡色小字紧跟标题，既能
        # 核对任务、又不会和名字混读（用户 2026-10-24）。
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(T.SPACE_SM)
        self.detail_title = QLabel("任务详情")
        apply_to(self.detail_title, T.SIZE_SUBTITLE, bold=True, color=T.INK)
        title_row.addWidget(self.detail_title)
        # 任务名**行内编辑**（2026-10-06「非必需，可随时修改」）。
        # ⚠️ 不用 QInputDialog：那也是模态窗，离屏自测不能真弹（项目硬规则），
        #    而且页头本来就有标题的位置，行内改最省一次点击。
        self.rename_edit = QLineEdit()
        self.rename_edit.setVisible(False)
        self.rename_edit.setMinimumWidth(280)
        self.rename_edit.editingFinished.connect(self._commit_rename)
        self.rename_edit.installEventFilter(cast("QObject", self))  # Esc 取消
        title_row.addWidget(self.rename_edit)
        self.task_no_label = QLabel("")
        apply_to(self.task_no_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.task_no_label.setToolTip("任务编号（任务目录名，创建后不变）")
        title_row.addWidget(self.task_no_label)
        title_row.addStretch()
        text_column.addLayout(title_row)
        self.source_label = QLabel("")
        apply_to(self.source_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        text_column.addWidget(self.source_label)
        # ---- 「流程要 PDF 而这个任务还没有」的红色提示（用户 2026-10-06）----
        # ⚠️ 放**页头里**而不是 toast：toast 会自己消失，而这件事在用户处理完
        #    之前一直成立（四个步骤都跑不了）。它得**一直在**，直到补上文件。
        #    默认隐藏——不是每个任务都缺文件，常驻一条红字会变成噪声。
        self.source_warning = QLabel("")
        apply_to(self.source_warning, T.SIZE_CAPTION, bold=True, color=T.DANGER)
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

        # ---- 聚合任务：重新汇集成员产物（仅聚合任务显示）----
        # 聚合任务的输入/产出是**创建那一刻**按成员顺序复制进来的快照；成员
        # 后来又重跑了某一步，这份快照就过期了。没有这个入口，用户只能删掉
        # 聚合任务重建（成员表格要重选、顺序要重排）。
        # ⚠️ 显隐由 ``_refresh_source_actions`` 统一管（普通任务恒藏）。
        self.aggregate_refresh_button = ToolButton(FIF.SYNC)
        self.aggregate_refresh_button.setToolTip(
            "重新汇集成员任务在起始节点上的输入与产出（成员重跑之后用）"
        )
        self.aggregate_refresh_button.setFixedSize(34, 34)
        self.aggregate_refresh_button.setVisible(False)
        self.aggregate_refresh_button.clicked.connect(self.refresh_aggregate_inputs)
        row.addWidget(self.aggregate_refresh_button)

        # ---- 补选源 PDF（用户 2026-10-06「PDF 输入不是必须的」）----
        # 创建任务时可以先不选文件，建出来的就是"空壳任务"。这个按钮是它的
        # 另一半：**恒在**（不随有没有源文件显隐）——文件被移走/删除时它同样
        # 是补救入口，藏起来等于让用户没法自己修。
        # ⚠️ 图标用**现成的自绘 ``PDF_FILE``**（用户 2026-10-06："图标使用
        #    PDF_FILE 现成的"）：内置 ``FIF.DOCUMENT`` 是**纯空白文档**，放进
        #    这个按钮会被读成"打开文档"而不是"选 PDF"，与列表页「创建任务」
        #    按钮、第四步「下载 PDF」用的都是同一枚图标才一致。
        self.source_button = ToolButton(PDF_FILE)
        self.source_button.setToolTip("为这个任务选择 PDF/DjVu 文件")
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
        self.insert_button.setToolTip("为本任务插入图片（放到入口图片目录，可多选）")
        self.insert_button.setFixedSize(34, 34)
        self.insert_button.clicked.connect(self.insert_pages)
        mark_input_entry(self.insert_button)
        row.addWidget(self.insert_button)

        # 📁 同样红框：整目录导入（文件对话框选不了目录，得单独一个入口）
        self.insert_dir_button = ToolButton(FIF.FOLDER)
        self.insert_dir_button.setToolTip(
            "把一个文件夹里的图片批量插入（放到入口图片目录）"
        )
        self.insert_dir_button.setFixedSize(34, 34)
        self.insert_dir_button.clicked.connect(self.insert_pages_from_folder)
        mark_input_entry(self.insert_dir_button)
        row.addWidget(self.insert_dir_button)
        # ⚠️「打开任务目录」**从页头移走**（用户 2026-10-06"统一放到右下
        #    角"）——它不是输入入口，是"去磁盘上看产物"的辅助动作，混在输入
        #    按钮里会让人以为也是一种输入方式。摆在底部状态条最右端。
        return card

    # ------------------------------------------------------------ 任务改名
    def _begin_rename(self) -> None:
        """点铅笔：标题换成行内输入框（不用弹窗——见上面 rename_edit 处的注释）。"""
        task_id = getattr(self, "task_id", None)
        if not task_id:
            return
        record = self.store.get_task(task_id) or {}
        self.rename_edit.setText(str(record.get("name") or ""))
        self.rename_edit.setVisible(True)
        self.detail_title.setVisible(False)
        # 编号让位给输入框：两者同处一行，留着会把输入框挤到标题后面
        self.task_no_label.setVisible(False)
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
            return  # 没在编辑态（Esc 取消后失焦会再触发一次）
        typed = self.rename_edit.text().strip()
        self.rename_edit.setVisible(False)
        self.detail_title.setVisible(True)
        self.task_no_label.setVisible(True)
        if not typed:
            return  # 留空 = 不改（rename_task 的空回落只在
            # 明确"清空后保存"时用）
        task_id = self.task_id
        if task_id is None:
            return  # 没有任务可改（详情页必然已开任务）
        try:
            changed = self.store.rename_task(task_id, typed)
        except Exception as exc:  # noqa: BLE001 - 落盘失败要说清，不能静默
            self._toast("error", "改名失败", f"{type(exc).__name__}: {exc}")
            return
        if changed:
            record = self.store.get_task(task_id) or {}
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

        if (
            watched is self.rename_edit
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_Escape
        ):
            # ⚠️ **先清文本再失焦**：``clearFocus`` 会触发 ``editingFinished``
            # → ``_commit_rename``，那里看到非空文本就会**真的存下去**，
            # Esc 等于"改名并保存"，与预期相反。
            self.rename_edit.clear()
            self.rename_edit.clearFocus()
            return True
        return False
