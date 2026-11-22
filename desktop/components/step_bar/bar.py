# -*- coding: utf-8 -*-
"""横向步骤条 :class:`StepBar`（真实步骤 + 条件「图片拼版」可选节点）。"""

from __future__ import annotations

from desktop.components.step_bar._qt import QHBoxLayout, Qt, QWidget, Signal

from desktop.components.step_bar.constants import _STATUS_LABELS
from desktop.components.step_bar.drawing import _StepBarPaintMixin
from desktop.components.step_bar.widgets import (
    StepItem,
    _Connector,
    _ImpositionNode,
)


class StepBar(_StepBarPaintMixin, QWidget):
    """横向步骤条：真实步骤按顺序排列，当前步骤高亮、已完成步骤打勾。

    除真实步骤外还支持一个**条件虚线节点**（「图片拼版」可选节点）：
    默认隐藏，``set_imposition_visible(True)`` 时插在**指定位置**——位置由
    构造参数 ``optional_after`` 决定（默认流程 = 插在倒数两个步骤之间）。
    伪步骤下标 ``imposition_index`` 是**步骤条上的格序**（含可选节点占位），
    ``set_current`` / ``current_changed`` 都以它表达"当前在看拼版详情"。

    ⚠️ **BPM 驱动**（``docs/tasks/bpm.md`` 的 M2）：真实步骤的顺序与可选
    节点的位置都来自本任务流程的槽位表（宿主
    ``TaskDetailPage._bar_step_titles`` / ``_optional_after_index`` 传入），
    换流程只换参数——本组件不认 ``STAGES``、也不数下标猜位置。

    节点有两组互相独立的状态线（别合并）：
    - **选择态**（``set_imposition_selected``）：节点自己的外观——副标题
      「已选择/未选择」**加上徽标**（处理过 → 绿勾；没处理过 → 灰色「＋」）。
      判据是"这一格自己有没有拼版页"，按节点算（同一步骤可有多个拼版节点）。
    - **流向**（``set_imposition_active``）：这条支路是否真的承载流程，判据
      是「在流程中启用图片拼版」开关（＝第四步从哪取图）。生效 → 两侧连接线
      常规点亮；未生效 → 两侧连接线灰色虚线，同时「去底色 → PDF排版」画一条
      从节点上方绕过的绕行线（``_draw_imposition_bypass``）——关掉开关时
      第四步取的是上一步产物，线不能说谎。
    ⚠️ 2026-10-23 用户报障前这两条是拧在一起的（徽标跟流向走、流向跟"有没有
    拼版页"走），于是"有拼版页但没启用"时流程仍然经过拼版。分成两条后：
    有页+未启用 = 绿勾 + 绕行线。

    节点的宽度与间距分成两件事（都踩过坑，别再合并）：
    - **槽位**与真实步骤等宽（``imposition_slot`` + stretch 1）→ 步骤间距均分；
    - **节点框**只在槽位里靠左、宽度不超过内容但有统一默认下限
      （``QSizePolicy.Maximum`` + ``_NODE_MIN_W``）→ 不被拉宽、宽窄一致。
    """

    current_changed = Signal(int)
    #: 流程条上点了「图片拼版」虚线节点（宿主据此切到占位详情）。
    #: ⚠️ 同一步骤可以有**多个**可选节点（两个「图片拼版」），所以新增
    #: :attr:`optional_clicked`（带格序）；本信号只为兼容老接线保留，
    #: 只在**第一个**可选节点被点时发出。
    imposition_clicked = Signal()
    #: 点了某个可选节点（携带它的**格序**）——多可选节点下的唯一正确寻址。
    optional_clicked = Signal(int)

    def __init__(
        self,
        steps,
        parent=None,
        optional_after=None,
        unmapped=None,
        bar_indices=None,
        optional_bar_index=None,
        optionals=None,
    ):
        """按给定步骤标题逐项构建；steps 允许传生成器。

        ``optional_after`` 是**可选节点（拼版）插在第几个真实步骤之后**
        （``None`` = 插在最后一步之前，沿用旧行为；``-1`` = 插在**最前**，
        拼版排在所有真实步骤之前——流程图这么画时宿主要能如实渲染，
        任务 #0027 踩坑）。⚠️ 这是 BPM 驱动的
        关键参数（``docs/tasks/bpm.md`` 的 M2）：默认流程下它等于
        ``len(steps) - 1``（拼版在「图片去底色」与「PDF排版」之间，与旧
        硬编码一致）；自定义流程把拼版排到别处时，宿主按槽位表的
        ``bar_index`` 算出来传进来，**连线/绕行线也跟着挪**。

        ⚠️ **``optionals``：可选节点的完整清单**（B 方案，2026-10-17）：
        ``[(插在第几个真实步骤之后, 格序, 标题), …]``。同一步骤可以画多个
        可选节点（两个「图片拼版」），只传一个的话第二个在流程条上**凭空
        消失**——用户看到的就是"任务详情没有完整显示自定义流程"。
        不给 ``optionals`` 时按 ``optional_after`` / ``optional_bar_index``
        推导出**一个**（既有调用方与全部现存流程一字不改）；清单为空也照样
        建一个隐藏占位（``imposition_node`` 等属性必须始终存在）。

        ⚠️⚠️ **下标只有一种语义 = 步骤条格序 ``bar_index``**（``docs/tasks/bpm.md``
        「三套下标」里的第①种，**含可选节点自己占的格子**）。``bar_indices``
        是"第几个真实步骤 ↔ 它的 ``bar_index``"的映射表，由宿主按本任务槽位表
        给（``view.py::_build_step_bar``）；``optional_bar_index`` 是拼版节点
        自己的格序。

        此前 :class:`StepItem` 拿的是**真实步骤的序数**（``enumerate(steps)``），
        与格序只差"可选节点之前"那一段——默认流程里 ``print`` 序数 3 / 格序 4，
        于是：点「PDF排版」发出去的是 3，宿主按格序查表得到**图片拼版**（点一个
        步骤打开另一个步骤）；``set_step_status(4)`` 撞上 ``0 <= 4 < 4`` 被
        **静默 return**，PDF排版的状态/进度/打勾从来不上屏（用户 2026-10-06
        报"bug 非常多"）。现在寻址一律走格序，徽标数字仍按**真实步骤序**显示
        （那是给人看的"第几步"，与寻址无关，见 :meth:`_sync`）。
        """
        super().__init__(parent)
        steps = list(steps)  # 调用方传的是生成器（STAGE_LABELS[s] for s in STAGES）
        self.buttons: list[StepItem] = []
        self.connectors: list[_Connector] = []
        self._completed: set[int] = set()
        #: 当前步骤的**格序**（``-1`` = 无选中）。与 :attr:`imposition_index` 同口径。
        self._current = 0
        #: 第 i 个真实步骤的格序 / 格序 → 位置的互查表（寻址全走它）
        self._bar_of_pos = (
            [int(b) for b in bar_indices]
            if bar_indices is not None
            else list(range(len(steps)))
        )
        if len(self._bar_of_pos) != len(steps):
            # 映射表与步骤数对不上 = 宿主算错了；宁可退回序数也不能错位寻址
            self._bar_of_pos = list(range(len(steps)))
        self._pos_of_bar = {b: i for i, b in enumerate(self._bar_of_pos)}
        #: 可选节点插在第几个真实步骤之后（构造期算出，见 ``optional_after``）。
        #: 下游找"拼版左右邻居"一律走它，不再写死 ``buttons[-2]``。
        #: ⚠️ **-1 = 插在最前**（拼版排在所有真实步骤之前，任务 #0027 的
        #:    「拼版→PDF排版」流程）：不能按旧口径钳到 0，否则视觉上跑到
        #:    第一步后面，与流程图相反。``None``（宿主没传）仍按旧默认
        #:    "最后一步之前"处理，那是默认流程的形状。
        self._optional_after = (
            len(steps) - 1 if optional_after is None else int(optional_after)
        )
        # ⚠️ 越界兜底：-1（最前，没有左邻居）到 len(steps)-1（最后，没有
        #    右邻居）都是合法自定义流程，夹进可用范围，别让 ``insert_at``
        #    算出负下标或越界下标。
        self._optional_after = max(
            -1, min(self._optional_after, max(len(steps) - 1, 0))
        )
        #: 伪步骤（拼版节点）的下标与控件；节点默认隐藏。
        #: ⚠️ ``imposition_index`` 是**步骤条上的格序**（含可选节点占位），
        #:    自定义流程下不再等于 ``len(steps)``。宿主给了
        #:    ``optional_bar_index`` 就用它（真源＝槽位表），否则退回
        #:    "插在第 ``_optional_after`` 个之后"这个推导值。
        self.imposition_index = (
            int(optional_bar_index)
            if optional_bar_index is not None
            else self._optional_after + 1
        )
        #: **全部可选节点**的规格（B 方案）：``[(after, bar_index, title), …]``。
        #: 宿主（``view._optional_bar_specs``）按槽位表给全清单；不给时按旧参数
        #: 推导出**一个**——这样"同一步骤只有一个可选节点"的现存流程与默认流程
        #: 在流程条上与改造前逐像素一致。
        if optionals is None:
            specs = [(self._optional_after, self.imposition_index, "图片拼版")]
        else:
            specs = [
                (
                    max(-1, min(int(after), max(len(steps) - 1, 0))),
                    int(bar_index),
                    str(title),
                )
                for after, bar_index, title in optionals
            ]
        if not specs:
            specs = [(self._optional_after, self.imposition_index, "图片拼版")]
        #: 兼容面用的"那一个"格序 = **第一个**可选节点的格序（宿主给的清单是
        #: 真源；``imposition_index`` 在下面按规格重设一次，避免两处不一致）。
        self.imposition_index = int(specs[0][1])
        #: 每个可选节点的控件与几何邻居——**按规格顺序**（自左向右）排列：
        #: ``optional_nodes[0]`` 恒是"第一个"可选节点（``imposition_node`` 兼容
        #: 面指向它）。所以下面虽然**从右往左插**（插入点才不会被推位），却按
        #: 原下标写回。
        self.optional_nodes: list[_ImpositionNode] = [None] * len(specs)  # type: ignore[list-item]
        self.optional_slots: list[QWidget] = [None] * len(specs)  # type: ignore[list-item]
        self.optional_connectors: list[_Connector] = [None] * len(specs)  # type: ignore[list-item]
        self.optional_afters: list[int] = [spec[0] for spec in specs]
        self.optional_bar_indices: list[int] = [spec[1] for spec in specs]
        self.optional_front_connectors: list[_Connector | None] = [None] * len(specs)
        #: 每个可选节点**各自**的支路生效态（B 方案）：同一步骤可以有多个
        #: 「图片拼版」节点，各连各的、互不替代——一个生效不代表另一个生效
        #: （用户 2026-10-18：操作了(1)，(2)却也显示成已处理）。下标与
        #: :attr:`optional_nodes` 同序。
        self._optional_flow: list[bool] = [False] * len(specs)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(0)
        self._row = row
        #: 「图上有、还没功能」的下标集合——这些节点画成灰的。
        #: ⚠️ 这是**真实步骤的序数**（与 ``steps`` 序列一致），不是格序：
        #:    宿主算的就是这个序列的下标。
        self._unmapped_indices = {int(i) for i in (unmapped or ())}
        for pos, title in enumerate(steps):
            # ⚠️ StepItem 拿的是**格序**：它 clicked 发出去的下标要能被宿主
            #    直接当格序查表（``page._select_stage`` 收的就是格序）。
            item = StepItem(self._bar_of_pos[pos], title, self)
            if pos in self._unmapped_indices:
                item.set_unmapped(True)
            item.clicked.connect(self._on_click)
            self.buttons.append(item)
            row.addWidget(item, 1)
            if pos < len(steps) - 1:
                connector = _Connector(self)
                self.connectors.append(connector)
                row.addWidget(connector, 0, Qt.AlignmentFlag.AlignVCenter)
        # 把「可选节点 + 它后面的连接线」逐个插到**它自己那个真实步骤之后**：
        # 布局此时为 [item0, conn0, item1, conn1, ...]，第 k 个真实步骤占下标
        # ``2k``，它**后面**那条连接件占 ``2k+1``。所以要"插在第 k 个之后"
        # = 插到下标 ``2k+2``（即下一个步骤的原位置）。
        # 默认流程 ``_optional_after = len(steps)-1`` 时正好等于旧口径的
        # ``row.count()-1``（两者都是"最后一项"的位置，完全等价）。
        # ⚠️ 必须是 2k+2：算成 2k+1 会插到 conn[k] 前面，箭头全跑到
        #    虚线框后面（用户截图报过：虚线前面没有箭头、后面挤两个）。
        # ⚠️ 多个可选节点时**按下标从大到小插**：先插靠右的，靠左的插入点
        #    才不会被前面的插入推位（插在同一个 after 之后的多个按原顺序插）。
        for order in sorted(range(len(specs)), key=lambda i: -specs[i][0]):
            after, bar_index, title = specs[order]
            node = _ImpositionNode(title, self)
            node.clicked.connect(
                lambda _checked=False, index=bar_index: self._on_optional_click(index)
            )
            connector = _Connector(self)
            # 节点**槽位**：与真实步骤等宽（stretch 1 → 间距均分），虚线框在槽位里
            # 靠左、宽度仍贴合文字。这两件事必须分开——合成一个控件就只能二选一：
            # 槽位等宽 = 虚线框被拉宽（用户 2026-09-30 报过），框贴合文字 = 最后一段
            # 挤在一起（用户同日报「不均分步骤」，实测间距 406 vs 147px）。与
            # StepItem「外框等宽拉伸 + 内层 pill 贴合内容」是同一套写法。
            slot = QWidget(self)
            slot_row = QHBoxLayout(slot)
            slot_row.setContentsMargins(0, 0, 8, 0)  # 与 StepItem 外边距一致
            slot_row.setSpacing(0)
            slot_row.addWidget(
                node, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            slot_row.addStretch(0)
            # ⚠️ 夹到 ``row.count()``：流程只有**一个**真实步骤时（自定义流程
            #    删掉了其它步骤），``2*after+2`` 会等于 2 而布局里只有 1 项，
            #    Qt 打出 ``QBoxLayout::insert: index 2 out of range (max: 1)``
            #    并**丢掉这次插入**——可选节点就静默不显示了（用户 2026-11-01
            #    的报错）。夹到末尾等价于"插在这个步骤之后"，语义不变。
            insert_at = min(2 * after + 2, row.count())
            row.insertWidget(
                insert_at, connector, 0, Qt.AlignmentFlag.AlignVCenter
            )
            # 槽位 stretch **1**：与真实步骤平分多余空间（间距才均匀）；虚线框自身
            # 靠 Maximum 策略贴在槽位左侧，不会被拉宽。
            row.insertWidget(insert_at, slot, 1)
            #: 节点**前面**那条连接线——布局上就是紧挨着槽位左边的那条，也就是原本的
            #  「去底色→PDF」。绕行线的起终点现取左右胶囊几何（见 _bypass_points），
            #  本属性只用于标认「前端那格」。
            # ⚠️ 可选节点插在**最前**（after = -1）时它左边没有任何连接件；
            #    插在**最后一步之后**时同理（左侧直接是 item[n-1]），取最后一条
            #    常规连接件，没有则 None。
            if after < 0:
                front = None
            elif after < len(self.connectors):
                front = self.connectors[after]
            else:
                front = self.connectors[-1] if self.connectors else None
            node.setVisible(False)
            connector.setVisible(False)
            self.optional_nodes[order] = node
            self.optional_slots[order] = slot
            self.optional_connectors[order] = connector
            self.optional_front_connectors[order] = front
        # 兼容面：老代码/自测只认"那一个拼版节点"，一律指向**第一个**可选节点。
        # ⚠️ 别删这几个属性：``detail_structure`` / ``last_stage`` / ``flow_ui``
        #    都直接读 ``step_bar.imposition_node`` / ``imposition_slot`` /
        #    ``_imposition_connector`` / ``imposition_front_connector``。
        self.imposition_node = self.optional_nodes[0]
        self.imposition_slot = self.optional_slots[0]
        self._imposition_connector = self.optional_connectors[0]
        self.imposition_front_connector = self.optional_front_connectors[0]
        row.addStretch(0)
        self._sync()

    # ------------------------------------------------------------------ 接口
    def _on_click(self, index: int) -> None:
        self.set_current(index)
        self.current_changed.emit(index)

    def _on_imposition_click(self) -> None:
        self._on_optional_click(self.imposition_index)

    def _on_optional_click(self, bar_index: int) -> None:
        """某个可选节点被点击：高亮切到**它自己的格序**并发信号。

        ⚠️ 同一步骤有多个可选节点时，"点的是哪一个"只有格序能回答——宿主
        据此切到对应节点详情（``view`` 接 :attr:`optional_clicked`）。
        ``imposition_clicked`` 只为老接线保留，且只在第一个节点上发。
        """
        self._current = int(bar_index)
        self._sync()
        self.optional_clicked.emit(int(bar_index))
        if int(bar_index) == self.imposition_index:
            self.imposition_clicked.emit()

    def set_current(self, index: int) -> None:
        """设置当前步骤的**格序**并同步各步骤高亮与徽标。"""
        self._current = int(index)
        self._sync()

    def mark_completed(self, index: int) -> None:
        """标记某步骤已完成（徽标改为对勾，连接线着色）。

        ``index`` 是**格序**（与 :meth:`set_step_status` 同一口径）。
        """
        if int(index) not in self._pos_of_bar:
            return
        self._completed.add(int(index))
        self._sync()

    def set_steps(self, texts) -> None:
        """兼容旧调用：只更新标题文本。"""
        for item, text in zip(self.buttons, texts):
            item.set_title(text)

    def set_imposition_visible(self, visible: bool) -> None:
        """显示/隐藏**全部**可选（虚线）节点（随流程图里有没有这一格）。

        ⚠️ 槽位要一起隐藏：只藏节点的话，那格等宽槽位还占着位置，流程条上会
        留出一段空白（第四步/PDF 看起来被推远）。
        另外节点显示时行顶边距 6→18：给绕行线留一条**走线带**——拼版未生效
        时「去底色 → PDF排版」的线要贴着节点上方绕过去（见
        ``_draw_imposition_bypass``），不预留高度弧线会顶到卡片边框。
        """
        for node in self.optional_nodes:
            node.setVisible(visible)
        for slot in self.optional_slots:
            slot.setVisible(visible)
        for connector in self.optional_connectors:
            connector.setVisible(visible)
        margins = self._row.contentsMargins()
        self._row.setContentsMargins(
            margins.left(), 18 if visible else 6, margins.right(), margins.bottom()
        )
        self._sync()

    def set_imposition_selected(self, selected: bool) -> None:
        """把**全部**可选节点设成同一个选择态（兼容面：单节点流程/自测用）。

        ⚠️ 选择态其实是**按节点**的（B 方案：同一步骤多个「图片拼版」各选各的，
        见 :meth:`set_imposition_node_state`）。这个方法只负责"一刀切"——
        现在只有"单节点流程"与自测会走到它，宿主的多节点刷新走按节点那一个。
        """
        for node in self.optional_nodes:
            node.set_selected(selected)
        self._sync()

    def set_imposition_node_state(self, bar_index: int, *,
                                  selected: bool | None = None,
                                  active: bool | None = None) -> None:
        """按**格序**设**某一个**可选节点的选择态/流向（B 方案）。

        - ``selected``：这一格**自己**处理过没有（副标题 + 徽标），按节点算；
        - ``active``：这条支路**在不在流程里**（连接线点亮 or 绕行），按流程级
          的启用开关算，所以同一步骤的多个节点通常一样。

        ⚠️ 同一步骤可以有多个「图片拼版」节点（用户 2026-10-17 的流程图：开头
        一个、网关「是」分支里又一个）：操作了(1) 不该让(2) 也变成「已选择」/
        绿勾（用户 2026-10-18 报障）。所以宿主要**逐节点**算、逐节点刷；
        ``set_imposition_selected`` / ``set_imposition_active`` 那种"一刀切"
        只在单节点流程里等价。
        """
        for order, index in enumerate(self.optional_bar_indices):
            if int(index) != int(bar_index):
                continue
            node = self.optional_nodes[order]
            if selected is not None:
                node.set_selected(bool(selected))
            if active is not None:
                flow = bool(active)
                self._optional_flow[order] = flow
                node.set_flow_active(flow)
            self._sync()
            return

    def set_imposition_active(self, active: bool) -> None:
        """把**全部**可选节点设成同一个生效态（兼容面：单节点流程/自测用）。

        生效 → 两侧连接线常规点亮；未生效 → 两侧连接线灰色虚线、主流程改走
        节点上方的绕行线。与 ``set_imposition_selected``（节点自己的选择外观
        + 徽标）互不取代：选了但还没启用时，节点显示「已选择」+ 绿勾，但线
        仍然是灰色虚线 + 绕行。

        ⚠️ **一刀切**：多节点流程里宿主走 :meth:`set_imposition_node_state`。
        """
        active = bool(active)
        changed = False
        for order, node in enumerate(self.optional_nodes):
            if self._optional_flow[order] != active:
                self._optional_flow[order] = active
                changed = True
            node.set_flow_active(active)
        if changed:
            self._sync()

    def set_step_status(
        self,
        index: int,
        status: str,
        progress: tuple | None = None,
        completed: bool | None = None,
    ) -> None:
        """设置某步骤状态；progress 为 (已完成, 总数) 时拼出 "成功 · 84/84"。

        ``index`` 是**格序 ``bar_index``**（与 :meth:`mark_completed`、
        :meth:`set_current`、``current_changed`` 同一口径）。⚠️ 早先这里拿它
        当 ``self.buttons`` 的**位置**下标，于是可选节点之后的每一步都差一段
        ——默认流程里「PDF排版」格序 4 而 ``len(buttons) == 4``，撞上
        ``0 <= 4 < 4`` 被**静默 return**，它的状态/进度/打勾从来不上屏。

        completed=False 但 status='success' 不可能出现；completed=True 而
        status 为失败/中断时，徽标保持对勾、副标题仍显示最近一次的结果。
        """
        pos = self._pos_of_bar.get(int(index))
        if pos is None:
            return
        detail = _STATUS_LABELS.get(status, status)
        if progress and progress[1]:
            detail = f"{detail} · {progress[0]}/{progress[1]}"
        done = status == "success" if completed is None else bool(completed)
        if done:
            self._completed.add(int(index))
        else:
            self._completed.discard(int(index))
        self.buttons[pos].set_status(
            status, detail, badge_status="success" if done else status
        )
        self._sync()

    def reset_statuses(self) -> None:
        """全部步骤恢复为未执行，并清空已完成标记。"""
        self._completed.clear()
        for item in self.buttons:
            item.set_status("pending", _STATUS_LABELS["pending"])
        self._sync()

    def _imposition_shown(self) -> bool:
        """**有任意一个**可选节点被配置为显示。

        ⚠️ 用 ``isHidden()``（只反映显式 ``setVisible(False)``）而不是
        ``isVisible()``（还要求整条窗口已经 show）：构建期/未显示时算出来的
        "未显示"会把两侧连接线压灰，而之后不一定再有 ``_sync`` 把它们点亮。
        """
        return any(not node.isHidden() for node in self.optional_nodes)

    def _sync(self) -> None:
        for pos, item in enumerate(self.buttons):
            # ⚠️ 徽标数字按**真实步骤序**（``pos + 1``，不含可选节点），
            #    高亮判定按**格序**（``item.index``）。两者是不同的东西：
            #    前者是给人看的"第几步"，后者是寻址用的（默认流程里 PDF排版
            #    徽标是 4 而格序是 4——拼版占了第 3 格）。
            item.badge.set_state(pos + 1, item._badge_status)
            item.set_current(item.index == self._current)
        for bar_index, node in zip(self.optional_bar_indices, self.optional_nodes):
            node.set_current(bar_index == self._current)
        # 连接线（含拼版两侧）的点亮/虚线状态由 ``_connector_segments`` 在
        # 绘制时从 ``_completed`` / ``_optional_flow`` 现算——控件不再存状态。
        self.update()


__all__ = ["StepBar"]
