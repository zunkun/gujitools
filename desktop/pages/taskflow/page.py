# -*- coding: utf-8 -*-
"""**任务流程编辑**二级页面（详情页页头「查看 / 编辑流程」进入）。

用户 2026-10-06：

> 任务流程可以在任务详情中提供编辑按钮，随时进入任务 bpm 编辑页面

⚠️ 原来是 :class:`~desktop.components.flow_dialog.FlowDialog` 模态弹窗。
既然「创建任务」已经改成二级页面，流程编辑也该有自己的页面——否则详情页里
点一下按钮又被弹窗盖住，而弹窗里再套编辑器就是第三层（历史上三个弹窗都出过
"关不掉/盖住下面"的问题，见 ``docs/tasks/bpm.md`` 的坑 7）。

## 与弹窗版的差别

``FlowPanel`` 多了两个开关（``embedded`` / ``close_window``）：

- 本页**不用** ``embedded``（页面自己会摆标题，所以让面板保留自己的），
- 但必须 ``close_window=False``：面板默认会 ``self.window().close()``，而
  ``self.window()`` 在这里就是**本页**——点「保存流程」会把整页关没。改成
  听 :attr:`~desktop.components.flow_dialog.FlowPanel.done` 信号自己切页。

## 保存去哪

:attr:`flow_saved` 发出任务号，壳层据此回详情页并**重新加载**（流程图换了，
步骤条/槽位/取图来源都要按新图重排）。

## 聚合任务（用户 2026-11-18）

> 聚合任务 0025，详情页面右上角有个详情流程入口，进入流程入口，现在显示的
> 是常规任务流程，应当显示聚合任务的子任务相关信息，跟创建聚合任务时候一样

同一个入口进来看的东西按 ``record["kind"]`` 分流：

- 普通任务 ⇒ 只有流程画布（本页原来的样子）；
- 聚合任务 ⇒ **聚合面板**（``AggregateCreatePanel(inspect=True)``）：子任务
  表格（各自已完成的节点）+ 起始节点 + 派生流程，与创建聚合任务时同一套
  控件、同一套文案。成员**只读**（改成员集合＝重建聚合任务），**起始节点
  可改**；画布仍可编辑，保存落 ``flow.bpmn``（与普通任务同一条落盘路径）。
- ⚠️ 改了起始节点再保存流程 ⇒ 先弹确认（用户 2026-11-18）：「起始节点丢失、
  聚合任务之前历史处理数据都丢失」。确认后：record 的 ``member_stage`` 一起
  改（:meth:`store.tasks.TaskStore.set_aggregate_start`）、发
  :attr:`aggregate_start_changed` 让壳层**按新起点重新汇集**（旧数据被覆盖，
  这正是"历史数据作废"的落地方式）；取消则不落盘、留在本页。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    FluentIcon as FIF, PrimaryPushButton, PushButton, StrongBodyLabel,
    ToolButton,
)

from desktop import ui
from desktop.components.flow_dialog import FlowPanel
from desktop.ui import theme as T

#: 路由键（壳层反查用）
ROUTE_FLOW = "flow"


class TaskFlowPage(QWidget):
    """任务流程页：整页就是编辑器 + 返回/保存（聚合任务换成聚合面板）。"""

    #: 用户保存了流程（携带任务号）——宿主据此回详情页并重载
    flow_saved = Signal(str)
    #: 聚合任务的**起始节点被改了**并已保存（携带任务号）——宿主按新起点重新
    #: 汇集成员产物（旧数据作废，见模块头）
    aggregate_start_changed = Signal(str)
    #: 用户关闭/返回（没保存），宿主回详情页
    closed = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._task_id: str | None = None
        self._panel: FlowPanel | None = None
        #: 聚合任务用的面板（``None`` = 当前不是聚合任务）
        self._aggregate_panel = None
        #: 成员「详情」开出来的预览窗：``{任务号: 窗口}``（同一任务不重复开）
        self._previews: dict[str, object] = {}
        self._build_chrome()


    # ------------------------------------------------------------------ UI
    def _build_chrome(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(
            T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG
        )
        root.setSpacing(T.SPACE_MD)

        top = QHBoxLayout()
        top.setSpacing(T.SPACE_SM)
        self.back_button = ToolButton(FIF.RETURN)
        self.back_button.setToolTip("返回任务详情")
        self.back_button.setFixedSize(34, 34)
        self.back_button.clicked.connect(lambda: self.closed.emit())
        top.addWidget(self.back_button)
        self.title = StrongBodyLabel("任务流程")
        ui.apply_to(self.title, T.SIZE_SUBTITLE, bold=True, color=T.INK)
        top.addWidget(self.title)
        top.addStretch()
        # ⚠️ 保存/关闭放**顶部**而不是面板底部：页面里的画布很高，按钮排在
        #    最下面时屏幕不够高就看不到——等于"没法保存"（实测截图确认）。
        self.save_button = PrimaryPushButton("保存流程")
        self.save_button.clicked.connect(lambda: self._on_done(True))
        top.addWidget(self.save_button)
        self.cancel_button = PushButton("关闭")
        self.cancel_button.clicked.connect(lambda: self._on_done(False))
        top.addWidget(self.cancel_button)
        root.addLayout(top)

        #: 编辑器宿主（每次 open_task 重建 FlowPanel 填进来）
        self.host = QWidget()
        self._host_layout = QVBoxLayout(self.host)
        self._host_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.host, 1)

    # ------------------------------------------------------------------ 用法
    def open_task(self, task_id: str) -> bool:
        """打开某个任务的流程页。任务号无效/流程读不出返回 ``False``。

        ⚠️ 每次进来都**重新读盘**（不缓存）：用户在别处改过流程（比如在创建
        任务页编的）时，进本页看到的必须是当前那一份。

        ⚠️ **聚合任务走另一套界面**（用户 2026-11-18）：不是"光一张流程图"，
        而是和创建聚合任务时一样的聚合面板（子任务表格 + 起始节点 + 流程）。
        """
        record = self.store.get_task(task_id) or {}
        if str(record.get("kind") or "") == "aggregate":
            return self._open_aggregate(task_id, record)

        from desktop.steps.scheduler import load_default_diagram

        diagram = self.store.task_diagram(task_id)
        if not diagram.nodes:
            return False
        self._task_id = task_id
        self._aggregate_panel = None
        name = str(record.get("name") or task_id)
        self.title.setText(f"任务流程 · {name}")
        self._clear_host()

        # ⚠️ close_window=False：默认行为会去关 self.window()，而那就是本页
        self._panel = FlowPanel(
            diagram, self, editable=True,
            reset_factory=load_default_diagram,
            close_window=False, show_buttons=False,
        )
        self._panel.done.connect(self._on_done)
        self._host_layout.addWidget(self._panel)
        return True

    def _open_aggregate(self, task_id: str, record: dict) -> bool:
        """聚合任务的流程页：聚合面板（成员/起始节点只读，画布可编辑）。

        成员与起始节点来自 record（``members`` / ``member_stage``），画布初始
        内容是**磁盘上那张** ``flow.bpmn``（创建时可能被用户改过）；万一流程
        文件读不出，按起始节点派生一张兜底，别让用户看到空白页。
        """
        from desktop.components.aggregate_create_panel import AggregateCreatePanel
        from desktop.steps.aggregate import derive_aggregate_diagram

        start_stage = str(record.get("member_stage") or "")
        members = [str(m) for m in (record.get("members") or []) if str(m).strip()]
        diagram = self.store.task_diagram(task_id)
        if not diagram.nodes and start_stage:
            diagram = derive_aggregate_diagram(start_stage)
        if not diagram.nodes:
            return False
        self._task_id = task_id
        self._panel = None
        name = str(record.get("name") or task_id)
        self.title.setText(f"聚合任务流程 · {name}")
        self._clear_host()

        panel = AggregateCreatePanel(
            self.store, self,
            inspect=True,
            members=members,
            start_stage=start_stage or "",
            initial_diagram=diagram,
        )
        # 行内「详情」＝非模态预览窗（与创建页同一个实现：创建到一半/正在看流程
        # 都不该被跳走，也不该弹模态）
        panel.detail_requested.connect(self._open_member_preview)
        self._aggregate_panel = panel
        # ⚠️ 聚合面板很高（成员表 + 起始节点 + 整张画布），而它的画布是
        #    ``scroll=False``（不自己滚，见 AggregateCreatePanel._rebuild_editor）
        #    ⇒ 这里必须给一个外层纵向滚动区，否则下面的画布会被页面裁掉。
        scroll = QScrollArea(self.host)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(panel)
        self._host_layout.addWidget(scroll)
        return True

    def _clear_host(self) -> None:
        """摘掉上一个任务的控件（deleteLater，不能只 hide——换任务后旧图还在
        内存里）。"""
        while self._host_layout.count():
            item = self._host_layout.takeAt(0)
            # count() 非零时 takeAt 必返回条目，这里只为让类型检查器收窄
            assert item is not None
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    # ------------------------------------------------------- 成员详情预览
    def _open_member_preview(self, task_id: str):
        """开（或前置）子任务的**非模态详情预览窗**（与创建页同一套口径）。"""
        if not task_id:
            return None
        existing = self._previews.get(task_id)
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.raise_()
                    existing.activateWindow()
                    return existing
            except RuntimeError:      # 底层对象已被销毁：当没有，重开一个
                self._previews.pop(task_id, None)
        from desktop.pages.taskdetail.preview import TaskPreviewDialog

        dialog = TaskPreviewDialog(self.store, task_id, self)
        self._previews[task_id] = dialog
        dialog.destroyed.connect(
            lambda *_args, _tid=task_id: self._previews.pop(_tid, None)
        )
        dialog.show()
        return dialog

    def _close_previews(self) -> None:
        """关掉全部预览窗（离开本页时用，别让旧任务的窗口飘着）。"""
        for dialog in list(self._previews.values()):
            try:
                dialog.close()
            except RuntimeError:      # 已经销毁
                pass
        self._previews.clear()

    def _current_diagram(self):
        """本页画布上的当前图（普通任务取 FlowPanel，聚合任务取聚合面板）。"""
        if self._aggregate_panel is not None:
            return self._aggregate_panel.current_diagram()
        if self._panel is not None:
            # ⚠️ 取"当前图"而不是 ``result_diagram()``：后者只在点过面板自己的
            #    「保存」之后才非 None，而本页把按钮收走了（show_buttons=False）。
            # 直接问面板要图（``editor()`` 在可编辑时返回画布本身，本页恒为可编辑）。
            return self._panel.editor_panel.diagram()
        return None

    def _on_done(self, ok: bool) -> None:
        """「保存流程」/「关闭」。保存成功才 emit ``flow_saved``。

        ⚠️ 顶部按钮直接走这里，**不**绕 ``FlowPanel.accept()``——那个方法会
        再发一次 ``done`` 信号（页面自己就是发起方，转一圈会重复落盘）。
        所以**合法性校验要在这里再做一遍**（与 ``FlowPanel.accept`` 同一份
        :func:`desktop.steps.validate.validate_flow`）：不合法的流程弹提示、
        不落盘、也不切页，用户留在本页改。
        """
        task_id = self._task_id
        if ok and task_id:
            stage_changed = (
                self._aggregate_panel is not None
                and self._aggregate_panel.stage_changed()
            )
            if stage_changed:
                old = self._aggregate_panel.record_stage()
                new = self._aggregate_panel.current_stage()
                if not self._confirm_start_change(old, new):
                    # 取消：不落盘、不切页，用户留在本页（可以改回去再保存）
                    return
            diagram = self._current_diagram()
            if diagram is not None:
                from desktop.steps.validate import validate_flow
                from desktop.ui.toast import show_toast

                result = validate_flow(diagram)
                if not result.ok:
                    show_toast(self, "warning", "流程不合法，未保存",
                               "；".join(result.errors))
                    return
                if result.warnings:
                    show_toast(self, "warning", "流程已保存（有提示）",
                               "；".join(result.warnings))
                # ⚠️ 起点先落 record 再落流程图：详情页一进来就按 `member_stage`
                #    找起点节点，两处必须是"同一次保存"的结果。
                if stage_changed:
                    self.store.set_aggregate_start(
                        task_id, self._aggregate_panel.current_stage()
                    )
                    self._aggregate_panel.mark_stage_saved()
                self.store.save_task_diagram(task_id, diagram)
                if stage_changed:
                    # ⚠️ **先**发这一条：壳层据此立刻起"重新汇集"（详情页马上
                    #    进入「正在汇集」态），再发 ``flow_saved`` 切回详情页时
                    #    看到的就是真话，而不是"这一步没有输入"。
                    self.aggregate_start_changed.emit(task_id)
                self.flow_saved.emit(task_id)
                return
        self._close_previews()
        self.closed.emit()

    # --------------------------------------------------- 起始节点变更确认
    def _build_start_change_dialog(self, old: str, new: str):
        """构造（**不弹出**）「起始节点已变更」确认框。

        ⚠️ 构造与 ``exec()`` 分开：离屏自测绝不真弹模态（项目硬规则），自测
        只造框、验文案/宽度，验完 ``deleteLater()``。

        用户 2026-11-18 原话：「如果变更了保存流程的时候，提示起始节点丢失，
        聚合任务之前历史处理数据都丢失」——所以正文必须把两件事说透：
        ①起点从哪个换成哪个；②**已汇集的输入与历史处理结果会丢**，且保存后
        会按新起点重新汇集（这就是"丢失"之后的重建方式）。
        """
        import html

        from desktop.steps.aggregate import aggregate_start_label
        from desktop.ui import theme as T
        from desktop.ui.confirm_dialog import ConfirmDialog

        red = T.DANGER
        old_label = html.escape(aggregate_start_label(old))
        new_label = html.escape(aggregate_start_label(new))
        content = (
            f"起始节点将从「{old_label}」改为"
            f'<font color="{red}">「{new_label}」</font>。<br><br>'
            "保存后，本聚合任务"
            f'<font color="{red}">之前汇集的输入与历史处理结果全部作废</font>'
            "（数据会丢失），流程按新起点重建；确认后立刻按新起点重新汇集"
            "各成员的产物。<br><br>此操作不可撤销，确定保存吗？"
        )
        return ConfirmDialog(
            "起始节点已变更", content, self,
            yes_text="保存并作废旧数据",
            rich=True,
        )

    def _confirm_start_change(self, old: str, new: str) -> bool:
        """弹确认框问"起点的历史数据要作废，还保存吗"（返回用户是否确认）。"""
        dialog = self._build_start_change_dialog(old, new)
        try:
            return bool(dialog.exec())
        finally:
            dialog.deleteLater()


__all__ = ["ROUTE_FLOW", "TaskFlowPage"]
