# -*- coding: utf-8 -*-
"""BPMN **固定节点面板**：拖一个节点到画布上，就加了一格。

用户 2026-10-05 的口径：

> 编辑呢，我希望能够有 BPMN.js 那种（bpmn.io）可以编辑的节点。或许我们不需要
> 那么多节点，**我们的节点是固定的**，拖拖拽拽就行了。我们节点默认是在页面画好
> 的，它可能有些节点不需要，他就删了就行了，可以恢复。

所以这里**不提供"任意节点类型"**：条目就是本工具认识的步骤
（提取图片 / 检测文本框 / 图片去底色 / 图片拼板 / PDF 排版）+ 一个「判断」网关。
拖到画布上是"添加"，画布上删掉是"不需要"，工具栏「恢复默认」是"恢复"。

## 两个细节

1. **已在流程里的步骤置灰**：同一步骤加两遍没有意义（运行阶段是按名字接回的，
   两个同名节点只会让 :meth:`FlowDiagram.stage_order` 去重、界面更乱）。
2. **节点名沿用流程图里已有的叫法**：``print`` 那格在默认模板里叫「PDF排版」
   （与 :attr:`StepSpec.stage_title` 一致），再拖一次就该还叫「PDF排版」——
   不要凭空长出一个新名字，更别和结束事件「生成PDF」重名。
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QListWidgetItem
from qfluentwidgets import ListWidget

from desktop.steps import ports
from desktop.ui import theme as T
from desktop.steps.spec import FLOW_STAGES, OPTIONAL_STEPS, spec_by_key

#: 拖放用的自定义 MIME 类型；负载 = 步骤 key（网关用 :data:`GATEWAY_TOKEN`）
NODE_MIME = "application/x-guji-bpmn-node"
#: 面板里「判断」那一项的负载（不是步骤 key，画布据此建排他网关）
GATEWAY_TOKEN = "__gateway__"
#: 「判断」节点的默认名
GATEWAY_NAME = "判断"

#: 面板宽度（够放"检测文本框"四个字 + 拖拽手柄）
PALETTE_WIDTH = 132


def palette_steps() -> list[str]:
    """面板上的**步骤 key**（顺序 = 静态步骤表：主链 + 可选节点）。"""
    return list(tuple(FLOW_STAGES) + tuple(OPTIONAL_STEPS))


def step_stage(step: str) -> str | None:
    """步骤 key → 拿它当节点名时要写的**运行阶段**。

    ``rembg`` 那一格下挂着两个阶段（``rembg`` 与 ``rembg_submit``），这里取
    **同名那个**（``rembg``）——它就是这一格的代表。
    """
    if step in ports.STAGE_STEPS:
        return step
    for stage in ports.STAGE_STEPS:
        if ports.STAGE_STEPS[stage] == step:
            return stage
    return None


def palette_name(step: str, *diagrams) -> str:
    """这一格该叫什么名字。

    优先沿用**已有流程图**里的叫法（用户的词汇），其次 ``ports.stage_label``。
    ⚠️ 一定要沿用：``print`` 那格现在正式叫「PDF排版」，若面板另起一个
    「生成PDF」，拖进去就会与**结束事件**同名（渲染与自检都会炸）。
    """
    for diagram in diagrams:
        if diagram is None:
            continue
        for node in diagram.nodes:
            if node.stage and ports.STAGE_STEPS.get(node.stage, node.stage) == step:
                return node.name
    stage = step_stage(step)
    return ports.stage_label(stage) if stage else step


def is_optional_step(step: str) -> bool:
    spec = spec_by_key(step)
    return bool(spec and spec.role == "optional")


class NodePalette(ListWidget):
    """可拖拽的固定节点列表。

    拖出去的是 :data:`NODE_MIME`（负载为步骤 key），由
    :class:`~desktop.components.bpmn_editor.BpmnEditor` 的 ``dropEvent`` 接收。

    用 qfluentwidgets 的 ``ListWidget``（它是 ``QListWidget`` 子类，``mimeData``
    照样能改写）：原生 ``QListWidget`` 在本界面里长得像异类。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(PALETTE_WIDTH)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setUniformItemSizes(True)
        self.setSpacing(2)
        self.setToolTip("拖一个到右边画布上即可添加；已经在流程里的会置灰")

    # ------------------------------------------------------------ 构建
    def refresh(self, diagram=None, *, template=None) -> None:
        """重建条目，并把**已在流程里**的步骤置灰。

        ``diagram`` = 当前正在编辑的流程图（判"已经有了"）；
        ``template`` = 默认模板（取名字用，保证新加的节点用的是既有叫法）。
        """
        present = set()
        if diagram is not None:
            for node in diagram.nodes:
                if node.stage:
                    present.add(
                        ports.STAGE_STEPS.get(node.stage, node.stage)
                    )
        self.clear()
        for step in palette_steps():
            exists = step in present
            suffix = "（可选）" if is_optional_step(step) else ""
            item = QListWidgetItem(
                f"{palette_name(step, diagram, template)}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, step)
            if exists:
                # 置灰且**不可拖**（禁用项选不中，也就拖不走）
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                item.setToolTip("流程里已经有这一步了")
                # ⚠️ 光靠"禁用"在 qfluentwidgets 的列表里**看不出区别**
                #    （实测与可用项一个色），必须显式上灰——否则用户不知道
                #    哪几条能拖。
                item.setForeground(QColor(T.INK_DISABLED))
            else:
                item.setToolTip("拖到画布上添加这一步")
            self.addItem(item)
        gateway = QListWidgetItem(GATEWAY_NAME)
        gateway.setData(Qt.ItemDataRole.UserRole, GATEWAY_TOKEN)
        gateway.setToolTip(
            "拖到画布上添加一个分支判断（排他网关）。是否拼版由「图片拼版」"
            "参数面板的开关决定，判断节点摆好即可，不必连线")
        self.addItem(gateway)

    # ------------------------------------------------------------ 拖放负载
    def mimeData(self, items):  # noqa: N802 - Qt 命名
        data = QMimeData()
        if items:
            token = items[0].data(Qt.ItemDataRole.UserRole) or ""
            data.setData(NODE_MIME, str(token).encode("utf-8"))
        return data


__all__ = [
    "GATEWAY_NAME", "GATEWAY_TOKEN", "NODE_MIME", "NodePalette",
    "PALETTE_WIDTH", "is_optional_step", "palette_name", "palette_steps",
    "step_stage",
]
