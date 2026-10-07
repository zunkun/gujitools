# -*- coding: utf-8 -*-
"""流程弹窗（查看 / 编辑 bpmn 文件），任务详情页与创建任务弹窗共用。

对应 ``docs/tasks/bpm.md``：

> 按照 bpmn 节点渲染节点……**同时可以修改 bpmn 节点**

## 两个入口

- **任务详情页**页头的「查看 / 编辑流程」——看当前任务实际在跑的流程；
- **创建任务**弹窗里的「编辑流程」——建任务之前把流程编好。

## 为什么打开就是编辑态（2026-10-05 第三轮）

上一版是"只读图 + 一个「编辑流程」按钮"，点一下才换成画布。用户反馈
「流程编辑现在还无法做到编辑流程」——多一跳不是主因，**主因是画布上什么
按钮都没有**（加节点/删除/改名全是死代码）。现在内容区直接就是
:class:`~desktop.components.bpmn_editor_panel.BpmnEditorPanel`：工具栏摆在
最上面，"能做什么"一眼可见。只读场景传 ``editable=False`` 即可。

## 有意取舍

⚠️ 改完流程**不自动重建详情页**。步骤条/两个栈全要重排，而页面此刻可能正
跑着某一阶段（进度条在动），重建会撕碎运行态。所以只落盘 + 提示"重新进入
任务生效"，让用户在安全时机自己切。宿主（``flow_mixin``）负责这条提示。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    CaptionLabel, PrimaryPushButton, PushButton, StrongBodyLabel,
)

from desktop import ui
from desktop.components.bpmn_editor_panel import BpmnEditorPanel
from desktop.components.dialog_shell import shell_dialog
from desktop.steps.bpmn_diagram import FlowDiagram
from desktop.steps.scheduler import CONDITIONS
from desktop.ui import theme as T

DIALOG_TITLE = "任务流程"
VIEW_HINT = "这是本任务当前在用的流程（就是 tasks/<任务号>/flow.bpmn 这份文件）。"
EDIT_HINT = (
    "从左侧面板拖一个节点到画布即可添加（已经有的会置灰）；"
    "按住节点边上的圆点拖到目标节点即可连线（上下左右四个连接点，"
    "位置自动匹配）；拖动节点排版，点「自动排版」一键整理；"
    "点空白处可以选中连线（再点「重命名」写分支条件）；双击节点改名；"
    "判断节点摆好即可、不必连线（是否拼版在「图片拼版」面板里开）；"
    "不要的节点选中后「删除」，想全部撤回就点「恢复默认」。"
)


def summarize(diagram: FlowDiagram) -> str:
    """一行摘要：几句话讲清这条流程要跑哪几步、在哪儿分支。"""
    stages = diagram.stage_order()
    if not stages:
        return "这条流程里还没有可执行的步骤。"
    from desktop.steps import ports

    labels = " → ".join(ports.stage_label(s) for s in stages)
    gateways = [n.name for n in diagram.nodes if n.is_gateway and n.name]
    text = f"共 {len(stages)} 步：{labels}"
    if gateways:
        text += f"；分支判断：{'、'.join(gateways)}"
    unknown = [n.name for n in diagram.nodes
               if n.kind == "task" and not n.stage and n.name]
    if unknown:
        text += f"；未接入运行的步骤：{'、'.join(unknown)}"
    return text


class FlowPanel(QWidget):
    """流程弹窗的**内容**（不含外壳，便于自测直接实例化）。

    对外只认三件事：:meth:`result_diagram`（保存后的图，``None`` = 没保存）、
    :meth:`edited`（是否点过保存）、:meth:`done`（结束信号）。
    """

    #: 面板结束（True = 保存，False = 关闭/取消），供外壳接
    done = Signal(bool)

    def __init__(self, diagram: FlowDiagram, parent=None, *,
                 editable: bool = True, reset_factory=None,
                 embedded: bool = False, close_window: bool = True,
                 show_buttons: bool = True):
        """``embedded``：**内嵌到别的页面**里（创建任务页），藏掉自带标题
        ——宿主已经有标题了，两套标题会让人以为进了两个窗口。

        ``close_window``：结束时要不要去关所属窗口。⚠️ 内嵌/独立**页面**里
        ``self.window()`` 就是**那一页**，原来的 ``_close_window`` 会把整页
        关掉（用户点"取消"结果页面消失）。这两种场合传 ``False``，改由宿主
        听 :attr:`done` 信号自己切页。
        """
        super().__init__(parent)
        self._accepted = False
        self._editable = editable
        self._reset_factory = reset_factory
        self._embedded = bool(embedded)
        self._close_window_on_end = bool(close_window)
        self._show_buttons = bool(show_buttons)
        self._build_ui(diagram)

    def _build_ui(self, diagram: FlowDiagram) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG)
        root.setSpacing(T.SPACE_MD)

        self.title_label = StrongBodyLabel(DIALOG_TITLE)
        root.addWidget(self.title_label)
        if self._embedded:
            # 内嵌时宿主自带标题（"编辑流程"那一行），这里别再摆一套
            self.title_label.setVisible(False)
        self.hint = CaptionLabel(EDIT_HINT if self._editable else VIEW_HINT)
        ui.apply_to(self.hint, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        # ---- 画布（编辑态自带工具栏；只读态是纯渲染）----
        self.editor_panel = BpmnEditorPanel(
            diagram, editable=self._editable,
            reset_factory=self._reset_factory)
        self.editor_panel.diagram_changed.connect(self._refresh_summary)
        root.addWidget(self.editor_panel, 1)

        # 兼容旧自测的属性名（旧版把只读图叫 self.view、把编辑态画布叫 _editor）
        self.view = self.editor_panel._canvas
        self._scroll = self.editor_panel._scroll

        self.summary = CaptionLabel(summarize(diagram))
        ui.apply_to(self.summary, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        # ---- 底部按钮 ----
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = PushButton("关闭")
        self.cancel_button.clicked.connect(self._close)
        buttons.addWidget(self.cancel_button)
        self.confirm_button = PrimaryPushButton("保存流程")
        self.confirm_button.clicked.connect(self.accept)
        buttons.addWidget(self.confirm_button)
        if self._show_buttons:
            root.addLayout(buttons)
        if not self._editable:
            self.confirm_button.setVisible(False)

    # ------------------------------------------------------------ 状态
    def edited(self) -> bool:
        """用户是否点过「保存流程」。"""
        return self._accepted

    def result_diagram(self) -> FlowDiagram | None:
        """保存后的图；只看了没保存（或取消）返回 ``None``。"""
        if not self._accepted:
            return None
        return self.editor_panel.diagram()

    def result_layout(self):
        """兼容旧调用：没有单独的"布局对象"了（坐标就在图里），返回 ``None``。"""
        return None

    def _close_window(self) -> None:
        """关掉**所属窗口**（外壳弹窗）。

        ⚠️ ``close_window=False``（内嵌/独立页面）时**什么都不做**——宿主听
        :attr:`done` 信号自己切页；这里去关会把整页关没。

        ⚠️ 面板自身没窗口（只是外壳的内容控件），``self.close()`` 关不掉
        弹窗——现象是点了「关闭/保存」弹窗还在屏幕上。
        """
        if not self._close_window_on_end:
            return          # 内嵌/独立页面：宿主听 done 信号自己切页
        win = self.window()
        if win is not None and win is not self:
            win.close()
        else:
            self.close()

    def _close(self) -> None:
        self._accepted = False
        self.done.emit(False)
        self._close_window()

    def accept(self) -> None:
        """保存：把（可能改过的）图交给宿主，并关窗。

        ⚠️ 保存前先过**合法性校验**（:func:`desktop.steps.validate.validate_flow`
        ——``docs/tasks/bpm测试.md``：不合法的流程在保存时当场拒绝）。
        硬错误（如「PDF排版」不在最后、没有任何可执行步骤）弹提示**不落盘**；
        警告（缺判断节点之类）只提示，不拦。
        """
        from desktop.steps.validate import validate_flow
        from desktop.ui.toast import show_toast

        result = validate_flow(self.editor_panel.diagram())
        if not result.ok:
            message = "；".join(result.errors)
            self.summary.setText(f"⚠ {message}")
            show_toast(self.window(), "warning", "流程不合法，未保存", message)
            return
        if result.warnings:
            message = "；".join(result.warnings)
            self.summary.setText(f"⚠ {message}")
            show_toast(self.window(), "warning", "流程已保存（有提示）", message)
        self._accepted = True
        self.done.emit(True)
        self._close_window()

    def _refresh_summary(self) -> None:
        self.summary.setText(summarize(self.editor_panel.diagram()))


class FlowDialog:
    """把 :class:`FlowPanel` 装进外壳的薄壳。

    ⚠️ **唯一弹窗入口是** :meth:`exec`；自测不碰它（离屏真弹模态会挂住进程），
    改用 :meth:`build_panel` 直接拿内容面板。
    """

    def __init__(self, diagram: FlowDiagram, parent=None, *,
                 editable: bool = True, reset_factory=None):
        self.panel = FlowPanel(diagram, None, editable=editable,
                               reset_factory=reset_factory)
        # ⚠️ own_chrome=True：面板自带标题、说明与按钮行，外壳不再加一套
        self.dialog = shell_dialog(
            DIALOG_TITLE, self.panel, parent, size=(1040, 720), own_chrome=True,
        )

    def build_panel(self) -> FlowPanel:
        """暴露内容面板（自测用：不弹窗也能验面板行为）。"""
        return self.panel

    def exec(self) -> bool:  # noqa: A003 - 与 Dialog.exec 同名是刻意的
        self.dialog.exec()
        return self.panel.edited()

    def result_diagram(self) -> FlowDiagram | None:
        return self.panel.result_diagram()


__all__ = [
    "CONDITIONS", "DIALOG_TITLE", "EDIT_HINT", "FlowDialog", "FlowPanel",
    "VIEW_HINT", "summarize",
]
