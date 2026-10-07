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
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
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
    """任务流程编辑页：整页就是编辑器 + 返回/保存。"""

    #: 用户保存了流程（携带任务号）——宿主据此回详情页并重载
    flow_saved = Signal(str)
    #: 用户关闭/返回（没保存），宿主回详情页
    closed = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._task_id: str | None = None
        self._panel: FlowPanel | None = None
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
        """打开某个任务的流程编辑。任务号无效/流程读不出返回 ``False``。

        ⚠️ 每次进来都**重新读盘**（不缓存）：用户在别处改过流程（比如在创建
        任务页编的）时，进本页看到的必须是当前那一份。
        """
        from desktop.steps.scheduler import load_default_diagram

        diagram = self.store.task_diagram(task_id)
        if not diagram.nodes:
            return False
        self._task_id = task_id
        record = self.store.get_task(task_id) or {}
        name = str(record.get("name") or task_id)
        self.title.setText(f"任务流程 · {name}")

        # 旧的编辑器先摘掉（deleteLater，不能只 hide——换任务后旧图还在内存里）
        while self._host_layout.count():
            item = self._host_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        # ⚠️ close_window=False：默认行为会去关 self.window()，而那就是本页
        self._panel = FlowPanel(
            diagram, self, editable=True,
            reset_factory=load_default_diagram,
            close_window=False, show_buttons=False,
        )
        self._panel.done.connect(self._on_done)
        self._host_layout.addWidget(self._panel)
        return True

    def _on_done(self, ok: bool) -> None:
        """「保存流程」/「关闭」。保存成功才 emit ``flow_saved``。

        ⚠️ 顶部按钮直接走这里，**不**绕 ``FlowPanel.accept()``——那个方法会
        再发一次 ``done`` 信号（页面自己就是发起方，转一圈会重复落盘）。
        所以**合法性校验要在这里再做一遍**（与 ``FlowPanel.accept`` 同一份
        :func:`desktop.steps.validate.validate_flow`）：不合法的流程弹提示、
        不落盘、也不切页，用户留在本页改。
        """
        task_id = self._task_id
        if ok and self._panel is not None and task_id:
            # ⚠️ 取"当前图"而不是 ``result_diagram()``：后者只在点过面板自己的
            #    「保存」之后才非 None，而本页把按钮收走了（show_buttons=False）。
            diagram = self._panel.editor_panel.editor().diagram()
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
                self.store.save_task_diagram(task_id, diagram)
                self.flow_saved.emit(task_id)
                return
        self.closed.emit()


__all__ = ["ROUTE_FLOW", "TaskFlowPage"]
