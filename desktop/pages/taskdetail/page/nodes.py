# -*- coding: utf-8 -*-
"""任务详情页的节点索引：流程槽位、节点寻址、当前阶段。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any


class NodeIndexMixin:
    """节点索引与槽位查询（B 方案：同一步骤可有多个节点实例）。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _PENDING_STATE: Any
        _current_node_id: Any
        _slot_at_index: Any
        _slot_of_node: Any
        step_bar: Any
        store: Any
        task_id: Any

    # ------------------------------------------------------------------ 流程槽位（BPM）
    def flow_slots(self) -> tuple:
        """本任务流程投影出的**界面槽位**（BPM 驱动界面的唯一入口）。

        没有任务（构造期/已离开）时给**默认流程**的槽位表，让步骤条在
        还没有任务时也能正常建出来——它此时只是个静态展示。

        ⚠️ 步骤条上那一格的 ``bar_index`` 就是 :attr:`StepBar._current` 的
        语义；``stack_index`` 才是 ``control_stack`` / ``preview_stack`` 的页号。
        两者在默认流程下与旧的 ``STAGES[index]`` 逐值相等（自测 ``detail_structure``
        钉死），所以换流程不用改栈的建页。
        """
        task_id = self.task_id
        if not task_id:
            # 没任务时给**默认模板**的槽位（静态展示）。⚠️ 与任务态同源：
            # 任务态走 store.task_slots（也是读 bpmn 文件），口径不会漂。
            from desktop.steps.scheduler import load_default_diagram

            return load_default_diagram().stage_slots()
        # ⚠️ 先收窄到局部变量再调：self.task_id 是 str | None，
        # getattr 那道判空对类型检查器不生效（它不跟踪 getattr）。
        return self.store.task_slots(task_id)

    def step_at_index(self, index: int) -> str | None:
        """步骤条格序 → **界面步骤 key**；这一格不在本流程里返回 ``None``。

        取代旧代码里的 ``STAGES[index]``（自定义流程下那个下标可能根本不存在）。
        """
        for slot in self.flow_slots():
            if slot.bar_index == index:
                return slot.step
        return None

    def stage_at_index(self, index: int) -> str | None:
        """步骤条格序 → **运行阶段**（``control_stack`` 页号语义那一层）。

        取代 ``ports.spec_for_stage(STAGES[index])`` 里的 ``STAGES[index]``。
        """
        for slot in self.flow_slots():
            if slot.bar_index == index:
                return slot.stage
        return None

    def stack_index_of(self, index: int) -> int:
        """步骤条格序 → ``control_stack`` / ``preview_stack`` 的页号。

        这一格不在本流程里时**兜回 0**（回第一步）并由调用方按"没找到"
        处理——绝不能拿一个越界页号去 ``setCurrentIndex``。
        """
        for slot in self.flow_slots():
            if slot.bar_index == index:
                return slot.stack_index
        return 0

    def bar_index_of_step(self, step: str) -> int | None:
        """界面步骤 key → 步骤条格序；这一步不在本流程里返回 ``None``。"""
        for slot in self.flow_slots():
            if slot.step == step:
                return slot.bar_index
        return None

    def flow_entry_step(self) -> str | None:
        """本流程**第一个真实步骤**的 step key（跳过可选节点）。

        ⚠️ "第一步"在自定义流程里不是"静态步骤表的第一格"——预热面板、
        缺输入提示等都得问图（``bar_index == 0`` 的那一格）。

        ⚠️ 刻意**跳过可选节点**：拼版永远是占位详情页（``mapped`` 语义上
        不算真正的入口步骤），否则"第一步是拼版"会让预热去建一个占位面板。
        """
        for slot in sorted(self.flow_slots(), key=lambda s: s.bar_index):
            if not slot.optional and slot.mapped:
                return slot.step
        return None

    def stage_at_stack_index(self, page: int) -> str | None:
        """``control_stack`` / ``preview_stack`` **页号** → 运行阶段。

        与 :meth:`stage_at_index` 是一对（那边是步骤条格序→ 阶段）。
        默认流程下两种下标逐值相等，自定义流程下必须分开查。
        """
        for slot in self.flow_slots():
            if slot.stack_index == page:
                return slot.stage
        return None

    # ------------------------------------------------------------------ 节点寻址（B 方案）
    def bar_index_of_node(self, node_id: str | None) -> int | None:
        """**节点实例 id** → 它在步骤条上占的那一格（``None`` = 本流程里没有它）。

        与 :meth:`bar_index_of_step` 的区别（B 方案，2026-10-17）：同一步骤有
        多个节点时，那个方法只能给"第一个"，而调用方要的多半是**具体哪个节点**
        的格子（恢复高亮、定位产物、把进度画到对的那一格）。
        """
        slot = self._slot_of_node(node_id)
        return None if slot is None else slot.bar_index

    def node_at_index(self, index: int) -> str | None:
        """步骤条**格序** → 该格对应的**节点实例 id**（没有节点返回 ``None``）。

        B 方案（2026-10-17）：同一步骤可以有多个节点，每个节点各占一格。界面
        把这一格对应的节点记成 :attr:`_current_node_id`，随后所有产物/参数
        寻址都按它走。
        """
        slot = self._slot_at_index(index)
        return (slot.node_id or None) if slot is not None else None

    def current_node(self) -> str | None:
        """当前格对应的**节点实例 id**（没有则为 ``None``）。"""
        return self._current_node_id

    def node_of_stage(self, stage: str) -> str | None:
        """该运行阶段在**当前上下文**对应的**节点 id**。

        判据：当前选中的节点（:attr:`_current_node_id`）属于这个阶段（或其所属
        界面格，如 ``detect_submit`` 与 ``detect`` 同格）⇒ 用它；否则退回该阶段的
        **主节点**（:meth:`~desktop.steps.bpmn_diagram.FlowDiagram.primary_of`）。

        单节点流程下恒等于主节点 ⇒ 产物落点与改造前逐字节一致（零迁移）。
        同一步骤有多个节点时，"用户正看着的那个"才是要寻址的那个。

        ⚠️ 两张映射表来自 :meth:`_rebuild_node_index`（切格时算一次），**不在这里
        解析流程图**：本方法被 ``_node_dir`` / ``_node_scope`` / 状态刷新这类
        ≤200ms 一次的热路径调用，逐次读盘解析 ``flow.bpmn`` 会明显拖慢界面。
        """
        if not stage or not self.task_id:
            return None
        from desktop.steps import ports as _ports

        step = _ports.STAGE_STEPS.get(stage, stage)
        current = self._current_node_id
        if current:
            current_step = _ports.STAGE_STEPS.get(
                self._node_stage.get(current, ""), ""
            )
            if current_step == step:
                return current
        return self._stage_primary.get(step)

    def _node_dir(self, stage: str) -> Path:
        """该运行阶段**当前上下文节点**的产物目录（B 方案；单节点时 = 旧目录）。

        按节点取落点，主节点沿用旧路径（``stages/<阶段>``），副本落到
        ``stages/<阶段>~<节点>``——界面按格显示某节点时就读它自己的产物。
        """
        if not self.task_id:
            return Path()
        return self.store.node_or_stage_output(
            self.task_id, self.node_of_stage(stage), stage, "pages"
        )

    def _node_scope(self, node_id: str | None = None) -> dict:
        """给按节点隔离的**读写**（页清单 / 参数暂存 / 检测框 / 尺寸）用的作用域。

        ``node_id`` 缺省 = 当前格对应的节点（:meth:`current_node`）。返回值直接
        展开进 ``store.load_pages(**scope)`` 这类调用，调用方不必自己查主节点。
        """
        if not self.task_id:
            return {"node_id": None, "primary_id": None}
        target = self.current_node() if node_id is None else node_id
        return self.store.scoped_file_scope(self.task_id, target)

    def node_display_suffix(self, node_id: str | None) -> str:
        """节点在界面上的**区分后缀**：同一步骤有多个节点时给「（2）」，否则空串。

        用在步骤条标题、日志行、"开始执行"提示这类**人对人**的地方：同一步骤
        两个节点都叫「图片去底色」时，用户没法判断刚才跑的是哪个、现在看的是
        哪个（这是 B 方案最直接的可用性代价）。

        序号口径 = **流程条上的先后**（``_stage_nodes``，bar 序），不是文件声明
        顺序：用户看到的顺序才该是 1、2、3——按声明顺序编号会出现"流程图里
        第一个节点叫（2）"（用户 2026-10-17 截图里就是这个错位）。

        ⚠️ **单节点恒为空串**：默认流程与所有现存任务的标题、日志必须与改造前
        **逐字一致**（用户习惯与自测都钉着这一点）。
        """
        if not node_id or not self.task_id:
            return ""
        stage = self.store.node_stage_of(self.task_id, node_id)
        if not stage:
            return ""
        ids = self._stage_nodes.get(stage)
        if not ids:
            # 索引还没建（探针/替身宿主）：退回图模型的声明顺序
            try:
                ids = list(self.store.task_diagram(self.task_id).node_ids_of(stage))
            except Exception:  # noqa: BLE001 - 图坏了不该让标题刷不出来
                return ""
        if len(ids) <= 1 or node_id not in ids:
            return ""
        return f"（{ids.index(node_id) + 1}）"

    def _scope_of(self, node_id: str | None) -> dict:
        """**某个具体文件**所属节点的作用域；``node_id`` 为 None ⇒ 不分节点（旧路径）。

        与 :meth:`_node_scope` 的分工（别混）：

        - :meth:`_node_scope` 把"没给节点"理解成"**界面当前**这一步的节点"，
          给"当前步骤的清单/暂存/待打印列表"这类读写用；
        - 本方法用于"**这个文件**属于哪个节点"的场合（如按目录反查出来的
          ``_size_node_for``）：查不到所属节点时就是"没有节点"，**不许借用
          当前节点**——否则「图片提取」产出的页会被记成「检测文本框」这一步的
          清单/尺寸（用户 2026-10-17 实测：流程里没有提取节点，第二步的页清单
          却被预览时的单页提取写进去了）。
        """
        if not self.task_id or not node_id:
            return {"node_id": None, "primary_id": None}
        return self.store.scoped_file_scope(self.task_id, node_id)

    def _size_node_for(self, path_text: str) -> str | None:
        """这张页面图的尺寸记在**哪个节点**名下（按它所在的产物目录反查）。

        走 :attr:`_node_of_dir`（``_rebuild_node_dirs`` 时算好的目录→节点表，
        O(1)）而不是遍历槽位表：本方法在 ``_page_thumb_for`` 里**逐页**调用，
        逐页解析 ``flow.bpmn`` 会把重建缩略图拖慢一个量级。
        """
        try:
            return self._node_of_dir.get(Path(path_text).parent)
        except TypeError:  # 路径非法（空串等）：当作没有节点
            return None

    def _node_stage_state(self, stage: str) -> dict:
        """某阶段在**当前上下文（当前节点）**下的状态（B 方案）。

        同一步骤的多个节点各有自己的运行记录；"这一步能不能提交/是不是失败过"
        一律问它，别问阶段——阶段状态是"这个阶段最近一次运行"，可能是**另一个
        节点**跑的。
        """
        if not self.task_id:
            return dict(self._PENDING_STATE)
        node = self.node_of_stage(stage)
        if node:
            state = self.store.node_states(self.task_id).get(node)
            if state is not None:
                return state
            return dict(self._PENDING_STATE)
        return self.store.stage_states(self.task_id).get(
            stage
        ) or dict(self._PENDING_STATE)

    def _rebuild_node_index(self) -> None:
        """重算本任务的**节点索引**（B 方案）——切步骤/重建步骤条时算一次。

        一次算清四件事，全部供热路径 O(1) 查询：

        - ``_node_dirs``：全部节点的产物目录（缩略图白名单）；
        - ``_node_of_dir``：产物目录 → 节点 id（"这张页面图是哪个节点产的"，
          尺寸基准按节点存时要问它）；
        - ``_node_stage``：节点 id → 运行阶段；
        - ``_stage_primary``：界面步骤 key → 该步骤的**主节点** id。

        ⚠️ 只在切步骤/切任务时算，**不要**放进逐页/逐 tick 热路径：``flow_slots``
        与 ``task_diagram`` 都要读盘解析 ``flow.bpmn``（单步切换读两次没问题，
        逐页读就是几十~几百次文件解析）。
        """
        from desktop.steps import ports as _ports

        self._node_dirs = set()
        self._node_of_dir = {}
        self._node_stage = {}
        self._stage_primary = {}
        self._stage_nodes = {}
        task_id = self.task_id
        if not task_id:
            return
        for slot in self.flow_slots():
            if not slot.mapped or not slot.node_id:
                continue
            self._node_stage[slot.node_id] = slot.stage
            # 同阶段节点按**流程条顺序**记录（编号给人看，必须跟着用户看到的顺序）
            self._stage_nodes.setdefault(slot.stage, []).append(slot.node_id)
            # 页面图产物目录（extract/detect_submit/rembg/imposition）
            try:
                pages_dir = self.store.node_output(task_id, slot.node_id, "pages")
            except KeyError:
                pages_dir = None
            if pages_dir is not None:
                self._node_dirs.add(pages_dir)
                self._node_of_dir[pages_dir] = slot.node_id
            # 「PDF排版」的产物是 PDF 不是页面图：白名单里带上它的输出目录
            # （缩略图判据按目录比，旧行为要保住；但**不**进 _node_of_dir——
            # 那目录里没有"页面图"，别让它答"这页是哪个节点产的"）。
            if slot.stage == "print":
                self._node_dirs.add(
                    self.store.scoped_stage_dir(task_id, slot.node_id, "print")
                )
        # 保底：主节点的 PDF 目录（流程里没有 print 节点时也认）
        self._node_dirs.add(self.store.print_output_pdf(task_id).parent)
        # 主节点表：走**图模型**（声明顺序里第一个 = 沿用旧路径的那个）
        try:
            diagram = self.store.task_diagram(task_id)
        except Exception:  # noqa: BLE001 - 图坏了不该让整个页面刷不出来
            return
        for stage in _ports.STAGE_LOCATIONS:
            step = _ports.STAGE_STEPS.get(stage, stage)
            if step in self._stage_primary:
                continue
            try:
                self._stage_primary[step] = diagram.primary_of(step)
            except Exception:  # noqa: BLE001
                self._stage_primary[step] = None

    def _rembg_step_index(self) -> int:
        """"图片去底色"这一步的**格序**（拼版节点消失时退回的那一步）。

        ⚠️ 旧代码写死 ``2``（第三步）。自定义流程里第三步未必在下标 2，
        写死会把用户送到别的步骤去。本流程里没有这一步时兜回 0。
        """
        index = self.bar_index_of_step("rembg")
        return 0 if index is None else index

    def panel_host_of_step(self, step: str) -> Any:
        """界面步骤 key → ``control_stack`` 里那一页的宿主控件。

        ⚠️ **取别的步骤的面板只有这一个入口**（MEMORY「三套下标」）：两个栈是
        按 ``FLOW_STAGES + OPTIONAL_STEPS`` 一次建好**固定页数**的，所以
        ``control_stack.widget(2)`` 恰好是「图片去底色」——那是"静态步骤表
        顺序"的性质，**不是**流程图的性质。自定义流程一旦换序、``SPECS``
        一旦增删一步，它就读错面板；流程里压根没有那一步时还会**把不在流程
        里的面板构造出来**（破坏"谁进去谁才建"，还会读到用户没填过的参数）。

        ⚠️ 返回 ``Any``：拿到的要么是 ``LazyPanelHost``（惰性宿主，属性转发给
        内部面板），要么是真面板本身——调用方一律按鸭子类型用（``peek`` /
        ``get_args`` / ``apply_args`` …），标成 QWidget 会让这些全变成
        「未知属性」。

        本流程没有这一步 ⇒ 返回 ``None``，调用方必须自己降级（别再兜一个
        "随便哪一步"——那正是界面说 A、执行做 B 的来源）。

        ``step`` 是**界面步骤 key**（``extract``/``detect``/``rembg``/``print``），
        不是运行阶段 key（``detect_submit`` 请传 ``"detect"``）。
        """
        index = self.stack_index_of_step(step)
        if index is None or index < 0:   # NO_PAGE = -1
            return None
        stack = getattr(self, "control_stack", None)
        if stack is None or index >= stack.count():
            return None
        return stack.widget(index)

    def stack_index_of_step(self, step: str) -> int | None:
        """界面步骤 key → 两个栈的页号；这一步不在本流程里返回 ``None``。"""
        for slot in self.flow_slots():
            if slot.step == step:
                return slot.stack_index
        return None

    # ------------------------------------------------------------------ 阶段切换/状态
    def current_stage(self) -> str:
        """返回当前所处阶段的key（extract/detect/rembg/print/imposition）。

        以步骤条高亮下标反查**本任务流程**的槽位表（BPM 驱动：自定义流程
        换了顺序/删了节点，这里如实反映）；下标为负时按 0 兜底处理。
        「图片拼版」是**可选节点**（``StepSpec.role == "optional"``），
        返回它的专用 key：调用方凡是拿这个 key 去 STAGES/STAGE_LABELS/runs
        里查的，都必须先挡掉（见 _refresh_stage_views / _apply_control_width
        等处的守卫）。
        """
        current = self.step_bar._current
        stage = self.stage_at_index(max(current, 0))
        if stage is not None:
            return stage
        # ⚠️ 兜底走**本流程**第一格，不是 ``STAGES[0]``（那是静态步骤表的
        #    第一格 = 恒为 extract）。自定义流程里压根没有 extract 时，回退到
        #    一个不在流程里的阶段会让进度/参数回填全都打到别的步骤上。
        for slot in sorted(self.flow_slots(), key=lambda s: s.bar_index):
            if not slot.optional and slot.mapped:
                return slot.stage
        # ⚠️ 本流程里一个「非可选且已映射」的槽位都没有（畸形流程/全空流程）：
        #    返回空串当"当前阶段"的哨值，而不是 None——本方法的返回类型是 str，
        #    调方都拿它去查 STAGES/STAGE_LABELS，None 会一路炸到那里。
        return ""
