# -*- coding: utf-8 -*-
"""BPMN 流程图**编辑控件**：拖节点、连边、改名、增删。

## 设计要点

- **改的是同一份 :class:`FlowDiagram`**（页面看到的图 = 文件里的图），保存
  即写回 ``.bpmn``。没有"界面模型"与"文件模型"两份东西。
- **拖节点只改坐标**，不动连线语义——拖拽是排版操作。连线折点若文件里
  有，拖动后**清掉重算**（旧折点会指向老地方，线会歪）。挂在节点上的
  **文字注释跟着节点一起走**（用户 2026-10-08：注释是写在节点旁的说明，
  节点挪了而注释留在原地，虚线会横穿整张图）。
- **注释也能单独拖**（用户 2026-10-08）：注释是图上的内容，位置该由用户说了算；
  拖它只改坐标，**挂接关系不变**（虚线依旧连回原来那个节点）。
- **连线只有一条主路**：每个节点有上下左右**四个中线连接点**（悬停/
  选中时显示），按住任一个拖到目标节点即连上；起止两端的连接点按两
  节点相对方位**自动匹配**（横向主导走左右、纵向主导走上下）。
  ⚠️ 工具栏的「连线」按钮已撤（用户 2026-11-17：拖连接点就够，
  按钮是多余的）；画布内部的连线模式（:meth:`set_link_mode`）保留，
  供程序化驱动与测试用。
- **「是否拼版」网关不是可自由增删的组件**（用户 2026-10-08）：它依附
  「图片拼版」那一步，只能随模板文件来——面板与工具栏都**没有**"添加判断"
  入口（用户原话："其实根本就没有判断这个组件"）。删掉「图片拼版」时它
  跟着删（判据在 :func:`desktop.steps.ports.orphaned_gateway_ids`）；
  反方向不成立——「图片拼版」可以没有网关。
- **节点与连线各有一套选中**，互斥；选中后工具栏的「删除」才可用。
  这条是硬需求：之前只有"点一下变个色"，用户不知道选中能干什么。
  改名走**双击节点**（工具栏「重命名」按钮已撤，用户 2026-11-17）。
- 所有鼠标/键盘事件 ``try/except``（控件在弹窗里，一次未捕获异常会连用户
  编好的图一起丢）。

⚠️ 编辑结果落在 :meth:`diagram` 返回的那份图上（原地改），由宿主调
:meth:`save_to` 落盘。

⚠️ 2026-11-22 起按职责拆成子包：常量/几何 ``constants``、宿主类型面
``_host``、交互与绘制 ``interaction``、对话框 ``dialogs``、主体 ``editor``。
本 ``__init__`` 只做重导出——既有 ``from desktop.components.bpmn_editor
import X`` 全部不变，子模块之间不要反过来导入本包（会形成循环）。
"""

from __future__ import annotations

from pathlib import Path

from desktop.components.bpmn_editor._qt import QPointF, QSizePolicy, Qt, Signal

from desktop.components.bpmn_editor.constants import NEW_NODE_GAP, PLACE_TRIES
from desktop.components.bpmn_editor.dialogs import _DialogMixin
from desktop.components.bpmn_editor.interaction import _InteractionMixin
from desktop.components.bpmn_view import BpmnView
from desktop.steps.bpmn_diagram import (
    KIND_TASK, DiagramFlow, DiagramNode, FlowDiagram, default_size,
)


class BpmnEditor(_DialogMixin, _InteractionMixin, BpmnView):
    """可编辑的 BPMN 视图（继承 :class:`BpmnView` 的渲染，加交互）。"""

    #: 图被改动（宿主据此标"未保存"）
    diagram_changed = Signal()
    #: 选中节点变化（空串 = 清空）
    selection_changed = Signal(str)
    #: 选中连线变化（空串 = 清空）
    flow_selection_changed = Signal(str)
    #: 连线模式开关变化
    link_mode_changed = Signal(bool)
    # 🗑 已删 ``stage_unbound``："改名把阶段接丢"这个事件**不再可能发生**——
    #    :meth:`rename_node` 现在是"改名不断绑"（认不出的名字只改显示，保留原
    #    阶段；身份还落盘在 ``guji:stage``）。留着一个永不触发的信号，只会让
    #    后人误以为"改名仍会断绑"而不敢动这块逻辑。

    #: 画布尺寸下限（类属性而非纯实例属性：``BpmnView.__init__`` 会先调一次
    #: ``_update_size``，那时 ``__init__`` 里赋的实例属性还不存在）。
    _floor: tuple[float, float] = (1.0, 1.0)

    def __init__(self, diagram: FlowDiagram | None = None, parent=None, *,
                 name_source: FlowDiagram | None = None):
        """
        :param name_source: 给**新加节点**取名字时参考的另一张图（通常是默认
            模板）。用户在模板里把 ``print`` 那格叫「PDF排版」，新加的节点就该
            沿用这个叫法——凭空起名会与结束事件撞名。
        """
        self._floor = (1.0, 1.0)
        super().__init__(diagram, parent)
        self._name_source = name_source
        self._drag_id: str | None = None
        self._drag_offset = QPointF()
        #: 正在拖动的**注释** id（与 ``_drag_id`` 互斥：一次只拖一个东西）
        self._drag_note: str | None = None
        self._drag_note_offset = QPointF()
        # 拖动中**冻结的连接点**（flow_id → route_anchor 结果）：拖动时连线
        # 的锚点不换边、线跟着节点平滑走；松手 :meth:`_finish_drag` 清掉重匹配
        self._drag_sides: dict[str, tuple] = {}
        self._press_pos: QPointF | None = None
        self._moved = False
        self._link_from: str | None = None
        self._link_pos: QPointF | None = None
        self._link_mode = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        # 键盘（Delete 删选中）需要焦点
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ------------------------------------------------------------ 数据
    def set_diagram(self, diagram: FlowDiagram) -> None:
        super().set_diagram(diagram)
        self._drag_id = None
        self._drag_note = None
        self._link_from = None
        self._link_pos = None
        self._drag_sides = {}

    def set_selected(self, node_id: str | None) -> None:
        """选中节点。

        ⚠️ 节点与连线**互斥**：选中一个就清掉另一个。不互斥的话界面上会出现
        "两个东西都高亮"，而「删除」只能删一个——用户按下去删错了才发现。
        这里用 ``super()`` 直接改状态，避免两个 setter 互相递归。
        """
        super().set_selected(node_id)
        self.selection_changed.emit(node_id or "")
        if node_id and self._selected_flow:
            super().set_selected_flow(None)
            self.flow_selection_changed.emit("")

    def set_selected_flow(self, flow_id: str | None) -> None:
        """选中连线（同样互斥，见 :meth:`set_selected`）。"""
        super().set_selected_flow(flow_id)
        self.flow_selection_changed.emit(flow_id or "")
        if flow_id and self.selected():
            super().set_selected(None)
            self.selection_changed.emit("")

    # ------------------------------------------------------------ 画布尺寸
    def set_canvas_floor(self, width: float, height: float) -> None:
        """给画布一个"至少这么大"的下限。

        ⚠️ 为什么需要：编辑时得**有地方放节点**。只按内容尺寸给大小的话，
        图很小时控件就只有一小条，用户想把节点拖到旁边都拖不出去（鼠标一出
        控件就从滚动区走了）。宿主把它设成视口尺寸，画布就总是铺满可见区。
        """
        floor = (float(max(width, 1)), float(max(height, 1)))
        if floor != self._floor:
            self._floor = floor
            self._update_size()

    def _update_size(self) -> None:
        """编辑态尺寸 = max(内容, 下限)；**min = max** 钉死，避免布局反复拉扯。"""
        width, height = self.content_size()
        w = int(max(width, self._floor[0]))
        h = int(max(height, self._floor[1]))
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setMinimumSize(w, h)
        self.setMaximumSize(w, h)
        if self.width() != w or self.height() != h:
            self.resize(w, h)
        self.update()

    # ------------------------------------------------------------ 连线模式
    def link_mode(self) -> bool:
        return self._link_mode

    def set_link_mode(self, enabled: bool) -> None:
        """开/关「点两下连线」模式（开时禁用拖拽，避免两种手势打架）。"""
        enabled = bool(enabled)
        if enabled == self._link_mode:
            return
        self._link_mode = enabled
        self._link_from = None
        self._link_pos = None
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.link_mode_changed.emit(enabled)
        self.update()

    # ------------------------------------------------------------ 编辑动作
    def add_node(self, kind: str = KIND_TASK, name: str = "新步骤",
                 stage: str | None = None,
                 at: tuple[float, float] | None = None,
                 connect_from: str | None = None) -> str:
        """加一个节点，返回它的 id。

        :param at: 画布坐标（**像素**，控件坐标）——从面板拖放的落点走这里，
            节点以该点为中心。不给就用 :meth:`_free_slot` 自动找空位。
        :param connect_from: 加完顺手连一条 ``connect_from → 新节点``
            （拖放时若正选中着某节点，就等于"接在它后面"）。
        """
        return self._add_node(kind, name, stage, at, connect_from)

    def add_step(self, token: str, at: tuple[float, float] | None = None,
                 connect_from: str | None = None) -> str | None:
        """按**步骤 key**加节点（固定节点面板拖放的入口）。

        ⚠️ **只认步骤 key**：网关（「是否拼版」）不再是可拖的条目——它依附
        「图片拼版」那一步、只能随模板文件来（见模块文档）。认不出的 token
        一律返回 ``None``，不凭空造节点。
        """
        from desktop.components.bpmn_palette import palette_name, step_stage

        if not token:
            return None
        stage = step_stage(token)
        if stage is None:
            return None
        # ⚠️ **同一步骤可以加多个节点**（B 方案，2026-10-17）：同类型步骤
        #    （图片拼版 / 检测文本框 / 图片去底色 / PDF排版）允许多个实例，
        #    它们彼此独立（各自参数、各自产物落点 ``stages/<阶段>~<node_id>``，
        #    见 ``docs/tasks/bpm.md``）。所以这里**不再拦**第二、第三个同格
        #    节点——节点 id 由水位分配器保证永不重复，运行时按 ``node_id``
        #    寻址，各跑各的。
        name = palette_name(token, self.diagram(), self._name_source)
        return self._add_node(KIND_TASK, name, stage, at, connect_from)

    def _add_node(self, kind: str, name: str, stage: str | None,
                  at: tuple[float, float] | None,
                  connect_from: str | None) -> str:
        """加节点的实现（``add_node`` / ``add_step`` 都汇到这里）。

        ⚠️ **只有 ``task`` 才按名字接运行阶段**（与 :meth:`FlowDiagram.load`
        同一口径）：事件/网关是图形控制元素，名字碰巧撞上阶段名也不该占一格。
        不在这里接的话，用户新加的「图片拼版」会以"未被识别"的灰状态存在
        ——图上有、运行时却不跑，正是最容易被误判成 bug 的现象。
        """
        from desktop.steps.bpmn_diagram import default_size, stage_of_name

        if stage is None and kind == KIND_TASK:
            stage = stage_of_name(name)
        diagram = self.diagram()
        # ⚠️ 节点 id **永不复用**：走图模型的水位分配器（``Node_<n>`` 只增不减），
        #    别再用"当前节点数 + 1"——删掉最后一个节点再加一个会**复用同一 id**，
        #    而副本产物目录 / 参数草稿按 id 命名，会读到已删节点的残留（串味）。
        node_id = diagram.next_node_id()
        if at is None:
            x, y, w, h = self._free_slot(kind)
        else:
            # 从面板拖过来：**以落点为中心**放节点（所见即所得），并夹在画布内
            w, h = default_size(kind)
            ox, oy = self._offset()
            x = max(4.0, float(at[0]) - ox - w / 2)
            y = max(4.0, float(at[1]) - oy - h / 2)
        diagram.nodes = diagram.nodes + (
            DiagramNode(id=node_id, kind=kind, name=name, stage=stage),
        )
        diagram.boxes[node_id] = (float(x), float(y), float(w), float(h))
        # 拖放时若正选中着某个节点，顺手接一条线（"挂在它后面"）——省一次连线
        if connect_from and connect_from != node_id \
                and diagram.node(connect_from) is not None:
            self.connect(connect_from, node_id)
        self._update_size()
        self.set_selected_flow(None)
        self.set_selected(node_id)
        self.diagram_changed.emit()
        self.update()
        return node_id

    def rename_node(self, node_id: str, name: str) -> None:
        """改节点名（就地换 dataclass：frozen，只能重建）。

        ⚠️ **改名不断绑**：阶段身份是节点的属性（落盘在 ``guji:stage``，见
        :meth:`FlowDiagram.to_xml`），名字只是显示标签——**兼**给外部工具
        （bpmn.io，不写扩展属性）做绑定提示。规则：

        - 新名字能认出阶段 ⇒ 换绑到那个阶段（"改名切换步骤类型"，有意保留）；
        - 新名字认不出 ⇒ **保留原阶段**，只改显示（以前这里直接置空，于是
          「图片去底色」改成「AI 抠图」就接不回任何阶段，整张图被判"坏图"
          而回落默认流程——用户只是改了个标签，流程却被换掉了）；
        - 本来就没阶段的节点 ⇒ 仍是 None（改名不许**凭空**接上阶段，
          否则随手一改就多出一个运行步骤）。

        要解绑（留着节点但不跑）请删节点——改名不提供这条路，省得一次手滑
        把运行中的步骤改成灰节点还找不到原因。
        """
        from desktop.steps.bpmn_diagram import stage_of_name

        diagram = self.diagram()
        old = diagram.node(node_id)
        if old is None:
            return
        if old.kind == KIND_TASK:
            resolved = stage_of_name(name)
            new = resolved if resolved is not None else old.stage
        else:
            new = None
        diagram.nodes = tuple(
            DiagramNode(id=n.id, kind=n.kind, name=name, stage=new)
            if n.id == node_id else n
            for n in diagram.nodes
        )
        self.diagram_changed.emit()
        self.update()

    def rename_flow(self, flow_id: str, label: str) -> None:
        """改连线上的文字（如网关分支的「否」）。"""
        diagram = self.diagram()
        diagram.flows = tuple(
            DiagramFlow(id=f.id, source=f.source, target=f.target, label=label)
            if f.id == flow_id else f
            for f in diagram.flows
        )
        self.diagram_changed.emit()
        self.update()

    def remove_node(self, node_id: str) -> None:
        """删节点：连到它的线一起删（悬空连线会让渲染与解析都出错）。"""
        diagram = self.diagram()
        doomed = [
            f.id for f in diagram.flows
            if f.source == node_id or f.target == node_id
        ]
        # ⚠️ 挂在它身上的**文字注释**也要一起删：节点没了、注释还留着，
        #    会变成一条漂在空白处的孤儿说明（虚线也没地方挂）。
        orphan_notes = [n.id for n in diagram.notes
                        if diagram.note_links.get(n.id) == node_id]
        diagram.nodes = tuple(n for n in diagram.nodes if n.id != node_id)
        diagram.flows = tuple(f for f in diagram.flows if f.id not in doomed)
        diagram.boxes.pop(node_id, None)
        if orphan_notes:
            diagram.notes = tuple(
                n for n in diagram.notes if n.id not in orphan_notes)
            for note_id in orphan_notes:
                diagram.note_links.pop(note_id, None)
                diagram.boxes.pop(note_id, None)
        for flow_id in doomed:
            diagram.waypoints.pop(flow_id, None)
            self._drag_sides.pop(flow_id, None)
        if self.selected() == node_id:
            self.set_selected(None)
        if self._link_from == node_id:
            self._link_from = None
        self._update_size()
        self.diagram_changed.emit()
        self.update()

    def remove_flow(self, flow_id: str) -> None:
        diagram = self.diagram()
        diagram.flows = tuple(f for f in diagram.flows if f.id != flow_id)
        diagram.waypoints.pop(flow_id, None)
        self._drag_sides.pop(flow_id, None)
        if self.selected_flow() == flow_id:
            self.set_selected_flow(None)
        self.diagram_changed.emit()
        self.update()

    def remove_selected(self) -> bool:
        """删掉当前选中的（连线优先）。删到了返回 ``True``。

        ⚠️ 节点**成对删**（用户 2026-10-06）：「上传 PDF」与「提取图片」必须
        成对存在，Delete 键与工具栏「删除」是**同一个动作**的两条入口——
        只在 :meth:`ask_delete_selected` 里做联动，键盘删就会漏（表现为
        "按 Delete 删掉提取图片，源 PDF 还在那儿，界面照样催上传 PDF"）。
        联动判据统一走 :func:`ports.paired_node_for_stage`。
        ⚠️ 附在它后面的**结束事件**也跟着删（用户 2026-10-07）：删掉
        「PDF排版」后「生成PDF」一条入线不剩，留着就是误导——判据走
        :func:`ports.orphaned_end_event_ids`。
        ⚠️ 依附它的**「是否拼版」网关**也跟着删（用户 2026-10-08）：网关不是
        独立组件，只服务于「图片拼版」——判据走
        :func:`ports.orphaned_gateway_ids`。
        """
        flow_id = self.selected_flow()
        if flow_id:
            self.remove_flow(flow_id)
            return True
        node_id = self.selected()
        if node_id:
            from desktop.steps import ports

            partner_id = ports.paired_node_for_stage(self.diagram(), node_id)
            doomed = [node_id, *([partner_id] if partner_id else [])]
            orphan_ids = ports.orphaned_end_event_ids(self.diagram(), *doomed)
            gateway_ids = ports.orphaned_gateway_ids(self.diagram(), *doomed)
            self.remove_node(node_id)
            for other in (partner_id, *orphan_ids, *gateway_ids):
                if other:
                    self.remove_node(other)
            return True
        return False

    def rename_selected(self, name: str) -> bool:
        """给选中的（连线优先）改名。改到了返回 ``True``。"""
        flow_id = self.selected_flow()
        if flow_id:
            self.rename_flow(flow_id, name)
            return True
        node_id = self.selected()
        if node_id:
            self.rename_node(node_id, name)
            return True
        return False

    def connect(self, source: str, target: str, label: str = "") -> str | None:
        """连一条边；自连/重复/悬空都拒绝（返回 ``None``）。"""
        if source == target:
            return None
        diagram = self.diagram()
        if diagram.node(source) is None or diagram.node(target) is None:
            return None
        if any(f.source == source and f.target == target for f in diagram.flows):
            return None
        used = {f.id for f in diagram.flows}
        index = len(used) + 1
        flow_id = f"Flow_{index}"
        while flow_id in used:
            index += 1
            flow_id = f"Flow_{index}"
        diagram.flows = diagram.flows + (
            DiagramFlow(id=flow_id, source=source, target=target, label=label),
        )
        # ⚠️ 折点**不要**现在算：位置可能还要变，渲染时按坐标现算更准
        #    （文件里存的是"这一刻"的折点，拖动后会过时）。
        self.diagram_changed.emit()
        self.update()
        return flow_id

    # ------------------------------------------------------------ 找空位
    def _free_slot(self, kind: str = KIND_TASK
                   ) -> tuple[float, float, float, float]:
        """给新节点找个**不压住别人**的位置。

        锚点优先取当前选中的节点（"在我选中的后面加一步"最符合直觉），
        没有选中就用最右边那个。先往右试，压住了就往下挪。
        """
        diagram = self.diagram()
        width, height = default_size(kind)
        boxes = [
            diagram.node_box(n.id) for n in diagram.nodes if n.id in diagram.boxes
        ]
        if not boxes:
            return (60.0, 60.0, width, height)
        anchor = self.selected()
        if anchor and anchor in diagram.boxes:
            ax, ay, aw, _ah = diagram.node_box(anchor)
        else:
            ax, ay, aw, _ah = max(boxes, key=lambda b: b[0] + b[2])

        def overlaps(x, y) -> bool:
            for bx, by, bw, bh in boxes:
                if (x < bx + bw + 8 and bx < x + width + 8
                        and y < by + bh + 8 and by < y + height + 8):
                    return True
            return False

        x = ax + aw + NEW_NODE_GAP
        y = ay
        for step in range(PLACE_TRIES):
            if not overlaps(x, y):
                break
            # 先往下、再往右（保证"在同一条链上往下排"的观感）
            if step % 2 == 0:
                y += height + NEW_NODE_GAP
            else:
                x += width + NEW_NODE_GAP
        return (float(x), float(y), float(width), float(height))

    # ------------------------------------------------------------ 落盘
    def save_to(self, path: Path | str) -> Path:
        """把当前图写回 ``.bpmn`` 文件（原子写）。"""
        return self.diagram().save(path)

    # ------------------------------------------------------------ 排版
    def auto_layout(self) -> None:
        """整图**自动排版**（:meth:`FlowDiagram.relayout`）。

        分层铺开 + 连线按新坐标现算（连接点自动匹配）。⚠️ 入口是工具栏按钮
        而不是鼠标事件——Qt 槽函数里没 catch 的话异常只进终端，用户看到的
        就是"点了没反应"（与鼠标事件同一条教训），所以这里自己兜住。
        """
        try:
            self.diagram().relayout()
        except Exception:  # noqa: BLE001 - 排版失败也别丢用户的图
            return
        self._update_size()
        self.diagram_changed.emit()
        self.update()


__all__ = ["BpmnEditor"]
