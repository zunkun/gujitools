# -*- coding: utf-8 -*-
"""按流程图解析某阶段/某节点的输入供给方与产物落点。

从 ``desktop/store/tasks.py`` 拆出（2026-11-22）。规则（图优先、静态兜底）
只在这里一份；"输入是否真的就绪"见 ``readiness.py``。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from desktop.steps import ports
from desktop.store.tasks.base import TaskMixinBase


class TaskInputMixin(TaskMixinBase):
    """阶段/节点粒度的输入解析与落点。"""

    if TYPE_CHECKING:
        task_dir: Callable[[str], Path]
        task_diagram: Callable[[str], Any]
        scheduler_flags: Callable[[str, bool], dict[str, bool]]
        node_action_executed: Callable[[str, str | None, str], bool]
        detect_submit_fresh: Callable[[str, str | None], bool]

    def stage_input(self, task_id: str, stage: str, port: str = "pages",
                    imposition_active: bool = False) -> Path | None:
        """按**本任务的流程定义**解析某阶段某端口的输入绝对路径。

        ⚠️ 这是 BPM 化的关键入口：调用方不再问"第三步的图片在哪"，而是问
        "这一步的 ``pages`` 输入在哪"——连线由任务的 ``flow.bpmn`` 决定
        （没有就用默认流程，与 :data:`desktop.steps.ports.SUPPLIERS` 逐边
        相等）。``imposition_active`` 对应那条唯一的**条件连线**（拼版生效
        时换上游），以条件名 ``"imposition"`` 传入解析上下文。

        ⚠️ **沿图回溯不出上游时回落到入口图片目录**（用户 2026-10-06：
        「如果某个节点作为第一个节点，一定要可以有输入可用」）。落点是
        :func:`desktop.steps.ports.task_input_dir`（``stages/input/``），
        界面的「插入图片」也写进那里（见 ``manifest.insert_pages``）。
        回落由 :func:`~desktop.steps.ports.resolve_input_with_entry` 统一做，
        **只对 ``pages`` 生效**——``boxes``/``pdf`` 没得回落。
        """
        supplier = self.stage_supplier(task_id, stage, port, imposition_active)
        return ports.resolve_input_with_entry(
            self.task_dir(task_id), stage, port, supplier
        )

    def task_input_dir(self, task_id: str) -> Path:
        """**流程入口图片**目录（``stages/input/``）。

        供"没有上游的步骤"当输入：用户往这里放图/从界面插图，第一个节点
        （例如自定义流程里的「检测文本框」）就拿它当pages 输入。落点由
        :data:`desktop.steps.ports.TASK_INPUT_LOCATION` 唯一声明。
        """
        return ports.task_input_dir(self.task_dir(task_id))

    def required_stage_inputs(self, task_id: str, stage: str,
                              imposition_active: bool = False) -> tuple[str, ...]:
        """本流程里这一步**真正要等就位**的输入端口。

        规则只在 :func:`desktop.steps.ports.stage_blocking_inputs` 一份（那里
        解释了为什么"声明的端口"不能直接当就绪判据：``pdf`` 由任务供给、
        ``boxes`` 在没有「检测文本框」的流程里压根没人产出）。

        :param imposition_active: 拼版开关的运行态（调用方传 effective）。
        """
        from desktop.steps.scheduler import Scheduler

        diagram = self.task_diagram(task_id)
        flags = self.scheduler_flags(task_id, imposition_active)
        active = Scheduler.from_diagram(diagram, flags).stages
        return ports.stage_blocking_inputs(diagram, stage, set(active))

    def stage_supplier(self, task_id: str, stage: str, port: str,
                       imposition_active: bool = False) -> str | None:
        """本任务里 ``(stage, port)`` 的**实际供给方**（运行时按图求解）。

        ⚠️ **这一步是"运行时跟着图走"的关键**：以前直接查代码里的端口级边表
        （``ports.SUPPLIERS``），一旦用户把流程改成不含某一步（例如去掉
        「图片去底色」），边表给的供给方就不在流程里了——按它取路径会指向
        **永远不会产生的文件**（现象是"PDF排版找不到输入"，而不是流程报错，
        极难查）。

        规则（先声明、后回退）：
        1. 取 ``ports`` 声明的供给方（``print/pages`` 走拼版开关那条特例）；
        2. 它**在本流程里**⇒ 就用它；
        3. 不在 ⇒ 沿图往前找**最近的、产出该端口的在流程阶段**
           （:meth:`FlowDiagram.nearest_producer`）。

        ⚠️ **"在流程里"要按"界面格子"判，不能按节点判**：
        ``detect_submit``（提交检测结果）是第二步内的**第二个动作**，用户画图
        时通常不会给它单独开一个节点（界面槽位也把它折回「检测文本框」那一格）。
        若按"图里有没有这个节点"判，就会认为它不在流程里，于是 ``rembg.pages``
        回退到 ``detect`` ——而 ``detect`` 只出坐标、没有裁好的图。
        所以判据是"它所属的**界面格**在不在流程里"（:data:`ports.STAGE_STEPS`
        给出 stage→step 的折叠关系）。
        ⚠️⚠️ **图优先，静态表兜底**（2026-10-06 掉头）。原先的规则是**反的**
        （"先静态声明、后沿图回退"），后果是 ``ports.SUPPLIERS``——一份**写死在
        代码里的默认流程连线**——在它给的供给方还留在流程里时**压过用户画的
        连线**。实测两条节点集合相同、连线不同的流程（默认的
        ``extract→detect→rembg→print`` 与用户自己连的 ``extract→print``），
        ``print`` 的取图目录**完全一样**——用户明确要求的连线被静默丢弃。
        这就是"自定义流程里总是冒出默认流程逻辑"的**病根**：BPM 化只覆盖了
        **顺序**，没覆盖**语义**。

        现在的规则：

        1. **图能给出唯一答案**（沿图可达的产出方恰好一个）⇒ **图说了算**；
        2. 图给不出、或给出**多个**（默认流程的「是否拼版」网关就是这种：沿图
           回溯 ``print`` 会同时看到「图片拼版」与「图片去底色」）⇒ 退回静态
           声明 + 条件开关（``ports.print_pages_supplier`` 建模的那一条）；
        3. 静态声明是**任务源**哨兵（``extract`` 的 ``pdf``）⇒ 直接返回，它
           本来就没有上游。

        ⚠️ 第2 条是**确定性**的要求，不是将就：网关分支要用"拼版开关"这个
        运行态来选，两条边在图上都是实线，靠遍历顺序选是随机的。
        """
        from desktop.steps.scheduler import Scheduler

        diagram = self.task_diagram(task_id)
        flags = self.scheduler_flags(task_id, imposition_active)
        active = set(Scheduler.from_diagram(diagram, flags).stages)
        # 本流程里"活着"的**界面格**（例如 detect_submit 与 detect 同属一格）
        live_steps = {ports.STAGE_STEPS.get(s, s) for s in active}

        def in_flow(name: str) -> bool:
            """该阶段（或它所属的那一格）在不在本流程里。"""
            if name in active:
                return True
            return ports.STAGE_STEPS.get(name, name) in live_steps

        declared = ports.supplier_of(stage, port)
        if stage == "print" and port == "pages":
            # 拼版生效时换上游（这是 ports 里唯一一条条件连线）
            declared = ports.print_pages_supplier(bool(imposition_active))
        if declared == ports.SUPPLY_TASK_SOURCE:
            return declared
        # ⚠️⚠️ **这一步压根不声明这个端口 ⇒ 没有这个输入**（返回 ``None``）。
        #    这一条必须在"图说了算"**之前**：``producers_of`` 只问"图上谁能产出
        #    它"，不问"这一步吃不吃它"——于是 ``print`` 明明不吃 ``boxes``，
        #    沿图回溯却能撞上 ``detect`` 并给出 ``boxes.json``（自测抓到）。
        #    端口声明（``ports.stage_inputs``）才是"这一步吃什么"的唯一真源。
        if port not in ports.stage_inputs(stage):
            return declared

        # ---- 1. 图说了算（图能给出唯一产出方时）----
        producers = diagram.producers_of(stage, port, active)
        if len(producers) == 1:
            return producers[0]

        # ---- 2. 图说不清 ⇒ 退回静态声明 + 条件 ----
        if declared is not None and in_flow(declared):
            return declared
        # 静态声明不可用时，最后才沿图随便取一个（老行为，保底）
        return producers[0] if producers else diagram.nearest_producer(
            stage, port, active
        )

    # ---------- 节点实例（B 方案：同阶段可以有多个节点）----------
    @staticmethod
    def _stage_live(stage: str, active: set[str]) -> bool:
        """某运行阶段（或它所属的**界面格**）在不在本流程里（`detect_submit`
        跟着 `detect` 那一格一起活着，见 ``ports.STAGE_STEPS``）。"""
        if stage in active:
            return True
        return ports.STAGE_STEPS.get(stage, stage) in {
            ports.STAGE_STEPS.get(s, s) for s in active
        }

    @staticmethod
    def _primary_of_stage(diagram, stage: str) -> str | None:
        """运行阶段 → 它的**主节点** id（`detect_submit` 映射到 `detect` 节点）。"""
        step_key = ports.STAGE_STEPS.get(stage, stage)
        return diagram.primary_of(step_key)

    def _node_ref_path(self, task_id: str, ref: str | None, port: str,
                       diagram) -> Path | None:
        """把"产出方引用"解析成产物绝对路径。

        ``ref`` 可以是**节点 id**、**阶段名**（静态声明兜底/旧调用方）或任务
        哨兵（:data:`ports.SUPPLY_TASK_SOURCE` / :data:`ports.SUPPLY_TASK_INPUT`）。
        """
        if ref is None:
            return None
        task_dir = self.task_dir(task_id)
        if ref == ports.SUPPLY_TASK_SOURCE:
            return None
        if ref == ports.SUPPLY_TASK_INPUT:
            return ports.task_input_dir(task_dir)
        item = diagram.node(ref)
        if item is not None and item.stage:
            effective = ports.fold_forward(item.stage, port)
            return ports.artifact_path(
                task_dir, effective, port, ref, diagram.primary_of(item.stage)
            )
        # 阶段名兜底：映射到该阶段的主节点（没有主节点则用旧落点）
        step_key = ports.STAGE_STEPS.get(ref, ref)
        primary = diagram.primary_of(step_key)
        effective = ports.fold_forward(step_key, port)
        return ports.artifact_path(task_dir, effective, port, primary, primary)

    def node_supplier(self, task_id: str, node_id: str, port: str,
                      imposition_active: bool = False) -> str | None:
        """本任务里某**节点实例**某端口的实际供给方（返回**节点 id** 或哨兵）。

        与 :meth:`stage_supplier` 同一套规则（图优先、静态兜底），区别是把
        "图说的产出方"落到**节点粒度**：同阶段有多个节点时，喂给 ``node_id``
        的是图上那个**具体节点**，而不是"整阶段的主节点"。
        """
        from desktop.steps.scheduler import Scheduler

        diagram = self.task_diagram(task_id)
        item = diagram.node(node_id)
        if item is None or not item.stage:
            return None
        stage = item.stage
        flags = self.scheduler_flags(task_id, imposition_active)
        active = set(Scheduler.from_diagram(diagram, flags).stages)
        # ⚠️ **不在这里判"消费方在不在流程里"**（与 :meth:`stage_supplier` 保持
        #    一致）：那一步该由 runner 的状态机守卫去说，而这里要能回答
        #    "**如果**要跑这一步，它的输入在哪"。
        #    反例（2026-10-17 自测抓到"弹窗里删除的图片没落盘"）：拼版开关没勾时
        #    ``imposition`` 不在 ``active`` 里，早退会让 ``node_input`` 拿不到
        #    上游、回落成入口图片目录（``stages/input``，空的）——拼版详情页于是
        #    "一张候选都没有"，连「删除图片」都无从落盘。``stage_supplier`` 靠
        #    **静态声明兜底**（下面第 2 步）照样给出 ``stages/rembg``，这里也一样。

        declared = ports.supplier_of(stage, port)
        if stage == "print" and port == "pages":
            declared = ports.print_pages_supplier(bool(imposition_active))
        if declared == ports.SUPPLY_TASK_SOURCE:
            return declared
        if port not in ports.stage_inputs(stage):
            return declared
        # ⚠️ **图上的入口节点（一条入边都没有）就是不接上游**，别退回静态声明
        #    （B 方案，2026-10-17 用户报障）：用户画的"图片拼版 → 检测文本框 →…"
        #    里第一个「图片拼版」没有任何上游，本该回落到入口图片目录
        #    （``stages/input/``）；按静态声明兜底会给出 ``stages/rembg``
        #    ——那是**下游**才有的目录，结果第一步"看着有输入、跑起来找不到图"。
        if not diagram.incoming(node_id):
            return None

        # 1. 图说了算（图上恰好一个产出方）
        producers = diagram.producer_nodes_of(node_id, port, active)
        if len(producers) == 1:
            return producers[0]
        # 2. 图说不清 ⇒ 退回静态声明 + 条件（把声明的阶段映射成它的主节点）
        if declared is not None and self._stage_live(declared, active):
            return declared
        if producers:
            return producers[0]
        return diagram.nearest_producer_node(node_id, port, active)

    def node_supplier_stage(self, task_id: str, node_id: str, port: str,
                            imposition_active: bool = False) -> str | None:
        """节点粒度的供给方，但结果折成**阶段 key**（不是节点 id）。

        :meth:`node_supplier` 回答的是"喂你的是哪个**节点**"（B 方案寻址要用
        节点 id）；而"记进 runs 历史、供旧数据判定比对"的那个字段
        （``args["source_stage"]`` ← :func:`desktop.services.stale_chain.print_source_switched`）
        历来是**阶段 key**（``detect_submit`` / ``imposition``）。两者不是一回事，
        所以这里折一道：节点 → 它的运行阶段 →（同格多动作再折）该端口成品的
        产出阶段。哨兵值原样透传。
        """
        ref = self.node_supplier(task_id, node_id, port, imposition_active)
        if ref is None or ref.startswith("<"):
            return ref
        stage = self.node_stage_of(task_id, ref)
        if stage is None:
            return ref if ref in ports.STAGE_STEPS else None
        return ports.fold_forward(stage, port)

    def node_input(self, task_id: str, node_id: str, port: str = "pages",
                   imposition_active: bool = False) -> Path | None:
        """某**节点实例**某端口输入的绝对路径（带**入口回落**）。

        与 :meth:`stage_input` 同构，只是把消费方定位到**节点**：没有上游而该
        节点确实吃 ``pages`` 时，回落到入口图片目录（``stages/input/``）。
        """
        diagram = self.task_diagram(task_id)
        ref = self.node_supplier(task_id, node_id, port, imposition_active)
        if ref is None and port == "pages":
            item = diagram.node(node_id)
            if item is not None and item.stage and "pages" in ports.stage_inputs(
                item.stage
            ):
                return self.task_input_dir(task_id)
        return self._node_ref_path(task_id, ref, port, diagram)

    def node_output(self, task_id: str, node_id: str, port: str = "pages",
                    stage: str | None = None) -> Path:
        """某**节点实例**某端口产物的绝对路径（**落点的唯一入口**）。

        ``stage`` 缺省取节点自身的阶段；显式给时表示"同一步骤的第二个动作"
        （如 ``detect`` 节点的 ``detect_submit`` 裁图落点）。主节点沿用旧落点，
        副本落到 ``~<node_id>`` 后缀的副本落点。
        """
        diagram = self.task_diagram(task_id)
        item = diagram.node(node_id)
        if item is None or not item.stage:
            raise KeyError(f"节点 {node_id!r} 没有对应的运行阶段")
        effective = stage or item.stage
        path = ports.artifact_path(
            self.task_dir(task_id), effective, port, node_id,
            diagram.primary_of(item.stage),
        )
        if path is None:
            raise KeyError(f"阶段 {effective!r} 没有登记端口 {port!r} 的落点")
        return path

    def required_node_inputs(self, task_id: str, node_id: str,
                             imposition_active: bool = False) -> tuple[str, ...]:
        """某**节点实例**真正要等就位的输入端口（节点粒度的就绪判据）。"""
        from desktop.steps.scheduler import Scheduler

        diagram = self.task_diagram(task_id)
        flags = self.scheduler_flags(task_id, imposition_active)
        active = Scheduler.from_diagram(diagram, flags).stages
        return ports.node_blocking_inputs(diagram, node_id, set(active))

    def node_ids(self, task_id: str) -> tuple[str, ...]:
        """本任务流程图里**全部可运行节点**的 id（拓扑序）——界面按它建页。"""
        return tuple(nid for nid, _stage in self.task_diagram(task_id).node_order())

    def node_or_stage_output(self, task_id: str, node_id: str | None,
                             stage: str, port: str = "pages") -> Path:
        """**落点的统一入口**：有节点按节点取，没节点/没登记回落该阶段的旧落点。

        主节点与"没有节点信息"（程序化调用、旧测试探针）都拿到 ``stages/<阶段>``
        ——与改造前逐字节相同。副本节点拿到 ``stages/<阶段>~<节点>``。

        调用方（执行端、取图、缩略图）一律走它，别自己 ``if node:`` 分叉：
        分叉处漏一处，就是"副本节点跑完产物写到主节点去了"。
        """
        if node_id:
            try:
                return self.node_output(task_id, node_id, port, stage)
            except KeyError:
                pass
        return self.artifact(task_id, stage, port)

    def scoped_stage_dir(self, task_id: str, node_id: str | None,
                         name: str) -> Path:
        """``stages/<name>`` 的**节点作用域**版本。

        主节点/无节点 ⇒ ``stages/<name>``（零迁移）；副本 ⇒
        ``stages/<name>~<节点>``。用于**没有登记在 STAGE_LOCATIONS 里**的
        辅助目录（如 detect 的标注图目录）。
        """
        scope = self.scoped_file_scope(task_id, node_id)
        return (
            self.task_dir(task_id)
            / "stages"
            / ports.scoped_name(name, scope["node_id"], scope["primary_id"])
        )

    def node_stage_of(self, task_id: str, node_id: str) -> str | None:
        """节点实例 → 它的**运行阶段**（不是界面步骤 key）；认不出返回 ``None``。"""
        try:
            item = self.task_diagram(task_id).node(node_id)
        except Exception:  # noqa: BLE001 - 图坏了不该拖垮寻址
            return None
        return item.stage if item is not None else None

    def node_primary_of(self, task_id: str, node_id: str) -> str | None:
        """节点实例 → 它所属阶段的**主节点** id（"沿用旧路径"的那一个）。"""
        stage = self.node_stage_of(task_id, node_id)
        if not stage:
            return None
        try:
            return self.task_diagram(task_id).primary_of(stage)
        except Exception:  # noqa: BLE001
            return None

    def scoped_file_scope(self, task_id: str, node_id: str | None
                          ) -> dict[str, str | None]:
        """给 ``load_pages``/``save_draft``/``boxes_path`` 这类按节点隔离的读写
        用的**作用域参数**：``{"node_id": …, "primary_id": …}``。

        统一在这里算，调用方不必各自去查"谁是主节点"——那是**只有图知道**的
        事实（见 :meth:`~desktop.steps.bpmn_diagram.FlowDiagram.primary_of`），
        散在各处迟早漂移。``node_id`` 为空时给 ``{"node_id": None,
        "primary_id": None}``，所有读写都落回**旧路径**（零迁移）。
        """
        if not node_id:
            return {"node_id": None, "primary_id": None}
        return {
            "node_id": node_id,
            "primary_id": self.node_primary_of(task_id, node_id),
        }
