# -*- coding: utf-8 -*-
"""BPMN **编辑器面板**：工具栏 + 可滚动画布 + 选中状态行。

## 为什么单独一个控件

用户 2026-10-05 的反馈：

> 流程编辑现在还无法做到编辑流程，元素添加，选择，两个任务关联等

根因是 :class:`~desktop.components.bpmn_editor.BpmnEditor` **只有画布**——
``ask_add_node`` / ``ask_delete_selected`` 这些动作早就写好了，但**没有任何
按钮去调它们**（死代码）。本模块把"动作"摆成看得见的按钮：

==========================  ==========================================
添加步骤                      从已知阶段里挑一个接上流程（能被运行时认出来）
添加判断                      加排他网关（分支菱形）——只摆节点，不连线
连线                          开连线模式：点起点 → 点终点（日常用拖连接点）
重命名                        改节点名 / 连线上的字（如「否」）
删除                          删选中的节点或连线
自动排版                      整图分层铺开，连线按新坐标重算
==========================  ==========================================

画布外面套滚动区，并把画布的**下限**跟着视口走（否则图很小时没地方拖节点）。

⚠️ 本控件不做落盘：宿主拿 :meth:`diagram` 交给 store 写 ``flow.bpmn``。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from qfluentwidgets import CaptionLabel, PushButton, ToolButton
from qfluentwidgets import FluentIcon as FIF

from desktop import ui
from desktop.components.bpmn_editor import BpmnEditor
from desktop.components.bpmn_palette import NodePalette
from desktop.components.bpmn_view import BpmnView
from desktop.steps.bpmn_diagram import FlowDiagram
from desktop.ui import theme as T

#: 画布下方最少留多少高度（面板很矮时也别把图压成一条缝）
MIN_CANVAS_HEIGHT = 320


class BpmnEditorPanel(QWidget):
    """工具栏 + 画布 的组合控件。

    :param editable: ``False`` = 只读（不建工具栏，画布换成
        :class:`~desktop.components.bpmn_view.BpmnView`）。
    """

    #: 图被改动
    diagram_changed = Signal()

    def __init__(self, diagram: FlowDiagram, parent=None, *,
                 editable: bool = True, reset_factory=None):
        """
        :param reset_factory: 无参可调用，返回一张"默认流程"的**新图**。给了就
            在工具栏右侧出「恢复默认」——用户把节点删光了也能一键回到起点
            （用户 2026-10-05："他可能有些节点不需要，删了就行了，**可以恢复**"）。
            不给就没有这个按钮（详情页看流程时不需要）。
        """
        super().__init__(parent)
        self._editable = editable
        self._diagram = diagram
        self._reset_factory = reset_factory
        #: 给新节点取名字时参考的图（惰性读默认模板，见 _name_source）
        self._template: FlowDiagram | None = None
        self._canvas: BpmnEditor | BpmnView
        self._build_ui()

    # ------------------------------------------------------------ 构建
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(T.SPACE_SM)

        self.toolbar: QWidget | None = None
        if self._editable:
            self.toolbar = self._build_toolbar()
            root.addWidget(self.toolbar)

        # ---- 画布区：左边固定节点面板（拖出来就加一格）+ 右边画布 ----
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(T.SPACE_SM)
        self.palette: NodePalette | None = None
        if self._editable:
            self.palette = NodePalette()
            body.addWidget(self.palette)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        # ⚠️ 编辑态用**左上对齐**（不是居中）：拖动时鼠标坐标直接映射到画布
        #    坐标，居中会在不同窗口尺寸下产生不同的偏移，手感飘。
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        if self._editable:
            canvas = BpmnEditor(self._diagram, name_source=self._name_source())
            canvas.diagram_changed.connect(self._on_changed)
            canvas.selection_changed.connect(lambda _=None: self._sync_status())
            canvas.flow_selection_changed.connect(lambda _=None: self._sync_status())
            canvas.link_mode_changed.connect(self._sync_link_button)
            self._canvas = canvas
            self._scroll.viewport().installEventFilter(self)
        else:
            self._canvas = BpmnView(self._diagram)
        self._scroll.setWidget(self._canvas)
        self._scroll.setMinimumHeight(MIN_CANVAS_HEIGHT)
        body.addWidget(self._scroll, 1)
        root.addLayout(body, 1)

        self.status = CaptionLabel("")
        ui.apply_to(self.status, T.SIZE_CAPTION, color=T.INK_FAINT)
        root.addWidget(self.status)

        self._sync_status()
        self._sync_floor()
        self._refresh_palette()

    def _name_source(self) -> FlowDiagram:
        """给新节点取名字时参考的图（默认模板，缓存一次）。

        取的是"本工具认定的叫法"（例如 ``print`` 那格叫「PDF排版」），
        免得新拖进来的节点与流程图里已有的节点重名。
        """
        if self._template is None:
            from desktop.steps.scheduler import load_default_diagram

            self._template = load_default_diagram()
        return self._template

    def _refresh_palette(self) -> None:
        """重建面板条目，并把**已经在流程里**的步骤置灰（防重复）。"""
        if self.palette is None:
            return
        self.palette.refresh(self._canvas.diagram(),
                             template=self._name_source())

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(T.SPACE_SM)

        self.add_button = PushButton("添加步骤")
        self.add_button.setIcon(FIF.ADD)
        self.add_button.setToolTip("在流程里加一个可运行的步骤")
        self.add_button.clicked.connect(self._on_add)
        row.addWidget(self.add_button)

        self.gateway_button = PushButton("添加判断")
        self.gateway_button.setIcon(FIF.TAG)
        self.gateway_button.setToolTip(
            "加一个分支判断（排他网关）。是否拼版由「图片拼版」参数面板的"
            "开关决定，判断节点摆好即可，不必连线")
        self.gateway_button.clicked.connect(self._on_add_gateway)
        row.addWidget(self.gateway_button)

        self.link_button = PushButton("连线")
        self.link_button.setIcon(FIF.LINK)
        self.link_button.setCheckable(True)
        self.link_button.setToolTip("开着它：先点起点节点、再点终点节点")
        self.link_button.clicked.connect(self._on_toggle_link)
        row.addWidget(self.link_button)

        self.rename_button = PushButton("重命名")
        self.rename_button.setIcon(FIF.EDIT)
        self.rename_button.clicked.connect(self._on_rename)
        row.addWidget(self.rename_button)

        self.delete_button = PushButton("删除")
        self.delete_button.setIcon(FIF.DELETE)
        self.delete_button.setToolTip("删除选中的节点或连线（Delete 键同效）")
        self.delete_button.clicked.connect(self._on_delete)
        row.addWidget(self.delete_button)

        row.addStretch()
        self.layout_button = PushButton("自动排版")
        self.layout_button.setIcon(FIF.LAYOUT)
        self.layout_button.setToolTip(
            "按流程顺序一键整理布局（节点位置与连线走线都会重排）")
        self.layout_button.clicked.connect(self._on_auto_layout)
        row.addWidget(self.layout_button)
        self.reset_button: PushButton | None = None
        if self._reset_factory is not None:
            self.reset_button = PushButton("恢复默认")
            self.reset_button.setIcon(FIF.ROTATE)
            self.reset_button.setToolTip("把流程恢复成默认的那份（会丢掉本次改动）")
            self.reset_button.clicked.connect(self._on_reset)
            row.addWidget(self.reset_button)
        self.fit_button = ToolButton(FIF.FIT_PAGE)
        self.fit_button.setToolTip("按内容重新收紧画布")
        self.fit_button.clicked.connect(self._on_fit)
        row.addWidget(self.fit_button)
        return bar

    # ------------------------------------------------------------ 对外
    def diagram(self) -> FlowDiagram:
        return self._canvas.diagram()

    def canvas(self):
        return self._canvas

    def editor(self) -> BpmnEditor | None:
        if not self._editable:
            return None
        canvas = self._canvas
        # 编辑态下 _canvas 恒为 BpmnEditor（见 _build_ui 的两个分支）
        assert isinstance(canvas, BpmnEditor)
        return canvas

    # ------------------------------------------------------------ 事件
    def eventFilter(self, obj, event):  # noqa: N802 - Qt 命名
        """视口尺寸变了就同步画布下限（否则缩窗口后没地方拖节点）。"""
        if obj is self._scroll.viewport() and event.type() == event.Type.Resize:
            self._sync_floor()
        return super().eventFilter(obj, event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_floor()

    def _sync_floor(self) -> None:
        editor = self.editor()
        if editor is None:
            return
        viewport = self._scroll.viewport().size()
        editor.set_canvas_floor(viewport.width(), viewport.height())

    def _on_fit(self) -> None:
        """收紧画布：把下限复位到视口，再让内容决定尺寸。"""
        self._sync_floor()
        self._canvas.update()

    def _on_reset(self) -> None:
        """恢复默认：**换一张新图**（不改旧对象，避免"恢复"后又被人拿旧引用改）。"""
        if self._reset_factory is None:
            return
        fresh = self._reset_factory()
        if fresh is None or not getattr(fresh, "nodes", None):
            return
        self._diagram = fresh
        self._canvas.set_diagram(fresh)
        self._sync_floor()
        self._sync_status()
        self._refresh_palette()
        self.diagram_changed.emit()

    def _on_changed(self) -> None:
        self._sync_status()
        # 图变了 ⇒ "哪些步骤已经有了"跟着变，面板的置灰要重算
        self._refresh_palette()
        self.diagram_changed.emit()

    # ------------------------------------------------------------ 工具栏动作
    def _on_add(self) -> None:
        editor = self.editor()
        if editor is not None:
            editor.ask_add_node()

    def _on_add_gateway(self) -> None:
        """加一个判断节点（只摆节点，不连线、不进连线模式）。"""
        editor = self.editor()
        if editor is not None:
            editor.add_gateway()

    def _on_auto_layout(self) -> None:
        """整图自动排版（分层铺开 + 连线按新坐标重算）。"""
        editor = self.editor()
        if editor is not None:
            editor.auto_layout()

    def _on_toggle_link(self, checked: bool | None = None) -> None:
        """⚠️ ``checked`` 允许缺省：qfluentwidgets 的 ``clicked`` 在这里发的是
        **无参**信号（实测），按 ``bool`` 形参接会直接 TypeError。"""
        editor = self.editor()
        if editor is not None:
            enabled = self.link_button.isChecked() if checked is None \
                else bool(checked)
            editor.set_link_mode(enabled)

    def _sync_link_button(self, enabled: bool) -> None:
        if self._editable and self.link_button.isChecked() != enabled:
            self.link_button.setChecked(enabled)
        self._sync_status()

    def _on_rename(self) -> None:
        editor = self.editor()
        if editor is not None:
            editor.ask_rename_selected()

    def _on_delete(self) -> None:
        editor = self.editor()
        if editor is not None:
            editor.ask_delete_selected()

    # ------------------------------------------------------------ 状态行
    def _sync_status(self) -> None:
        """选中状态 + 操作提示。这一段是"选择有意义"的关键：

        以前选中只换个边框色，用户不知道选中能干什么。这里把"选中了什么、
        能做什么"直接写出来。
        """
        if not self._editable:
            self.status.setText("")
            self._sync_buttons(False, False)
            return
        editor = self.editor()
        assert editor is not None
        flow_id = editor.selected_flow()
        node_id = editor.selected()
        if flow_id:
            flow = next((f for f in editor.diagram().flows if f.id == flow_id), None)
            source = editor.diagram().node(flow.source) if flow else None
            target = editor.diagram().node(flow.target) if flow else None
            text = (f"已选中连线：{source.name if source else '?'} → "
                    f"{target.name if target else '?'}"
                    f"（可「重命名」写分支条件，或「删除」）")
        elif node_id:
            item = editor.diagram().node(node_id)
            name = item.name if item else node_id
            stage = getattr(item, "stage", None)
            if item is not None and (item.is_gateway or item.is_event):
                text = f"已选中「{name}」（图形元素，不占运行步骤）"
            elif stage:
                text = f"已选中步骤「{name}」——运行阶段：{stage}"
            else:
                text = (f"已选中步骤「{name}」——**未被识别为运行步骤**，"
                        f"改成已知阶段名即可参与运行")
        elif editor.link_mode():
            text = "连线模式：点起点节点，再点终点节点"
        else:
            text = ("按住节点边上的圆点拖到目标节点即可连线；拖动节点排版，"
                    "点「自动排版」一键整理；点空白处可选中连线；双击节点改名")
        self.status.setText(text)
        self._sync_buttons(bool(node_id), bool(flow_id or node_id))

    def _sync_buttons(self, has_node: bool, has_any: bool) -> None:
        if not self._editable:
            return
        self.rename_button.setEnabled(has_any)
        self.delete_button.setEnabled(has_any)
        self.add_button.setEnabled(True)


__all__ = ["BpmnEditorPanel", "MIN_CANVAS_HEIGHT"]
