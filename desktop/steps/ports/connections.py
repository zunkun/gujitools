# -*- coding: utf-8 -*-
"""连线（BPM 的边）与就绪判定：谁供给谁、输入解析、入口判定。"""

from __future__ import annotations

from pathlib import Path

from desktop.steps.ports.constants import (
    ARTIFACT_PAGES,
    PORT_LABELS,
    STAGE_STEPS,
    SUPPLIERS,
    SUPPLY_TASK_INPUT,
    SUPPLY_TASK_SOURCE,
)
from desktop.steps.ports.declaration import (
    spec_for_stage,
    stage_inputs,
    stage_outputs,
)
from desktop.steps.ports.locations import artifact_path, task_input_dir


def supplier_of(stage: str, port: str) -> str | None:
    """某阶段某端口由谁供给；没有连线返回 ``None``。"""
    return SUPPLIERS.get(stage, {}).get(port)


def print_pages_supplier(imposition_active: bool) -> str:
    """PDF排版（``print``）取图的上游：拼版生效时是 ``imposition``，否则是去底色。

    ⚠️ 抽成函数而不是在 :data:`SUPPLIERS` 里写死，是为了让"拼版生效"这种
    **运行态开关**（用户在详情页勾了拼版节点）有一个明确、可测的出口：
    BPM 编排时这正是"条件连线"的落点。
    """
    return "imposition" if imposition_active else "rembg"


def print_input_overrides(imposition_active: bool) -> dict[tuple[str, str], str]:
    """打印阶段的运行时连线覆盖（拼版开关 → 上游换成 imposition）。

    传给 :func:`resolve_input` / :func:`input_ready`。⚠️ 返回**新字典**：
    调用方可能缓存它，别让一次运行的状态漏进下一次。
    """
    return {("print", "pages"): print_pages_supplier(imposition_active)}


def resolve_input(
    task_dir: Path | str,
    stage: str,
    port: str,
    overrides: dict[tuple[str, str], str] | None = None,
) -> Path | None:
    """**按连线**解析某阶段某端口的输入绝对路径。

    ``overrides`` 是 ``{(阶段, 端口): 供给阶段}`` 的运行时覆盖（拼版开关
    就是用它），优先级高于 :data:`SUPPLIERS`。解析不出来返回 ``None``。
    """
    supplier = (overrides or {}).get((stage, port))
    if supplier is None:
        supplier = supplier_of(stage, port)
    if supplier is None:
        return None
    return artifact_path(task_dir, supplier, port)


def input_ready(
    task_dir: Path | str,
    stage: str,
    port: str,
    overrides: dict[tuple[str, str], str] | None = None,
) -> bool:
    """这个端口的输入**已经就位**吗（落点存在且非空）。

    只看"有没有东西"，不判断内容对不对——那是功能层的事。
    """
    path = resolve_input(task_dir, stage, port, overrides)
    if path is None:
        return False
    if path.is_dir():
        return any(path.iterdir())
    return path.exists()


def stage_blocking_inputs(diagram, stage: str, active=None) -> tuple[str, ...]:
    """这一步在**这张流程图上**真正要等就位的输入端口（就绪判据的唯一来源）。

    :func:`stage_inputs` 回答"这一步**可能**吃什么"（静态声明，来自
    ``StepSpec.inputs``），本函数回答"**在本流程里**它吃什么"。自定义流程
    下两者会分叉，**就绪守卫必须用后者**，否则会出现"守卫比流程还严"：

    · **任务自己供给**的端口（``pdf`` ← 任务备份的源 PDF）不在列。它不是某个
      阶段的产物目录，而是任务自己的文件（由 ``_missing_source`` 与 extract
      分支的 ``Path(source_path).exists()`` 负责）。拿它当目录去 ``exists()``
      恒为 ``False`` ⇒「图片提取」永远被判成"输入不齐"，**extract 被自己的
      守卫锁死**（``resolve_input_with_entry`` 对任务哨兵返回 ``None`` 就是
      这个意思：那里没有目录可解析）。
    · **本流程里没人产出**的端口不在列。典型：自定义流程把「图片去底色」放
      第一个节点、没有「检测文本框」，``boxes`` 就没有供给方——那种流程里
      这一步压根不吃检测数据（去底色固定整图处理，见
      ``functions/text_region.py``），用一个解析不出东西的端口挡它，用户只
      会看到"输入还没就位"的假提示（用户 2026-10-06 报障）。反过来，默认
      流程里 ``boxes`` 的供给方（``detect``）**在**，它照旧是阻塞端口——
      「检测文本框」与它的提交仍然要等 extract 跑完。

    在列的端口：

    · ``pages`` **恒在**：没有上游时它回落到入口图片目录
      （:func:`resolve_input_with_entry`）——"没有上游"不等于"不需要图"。
    · 其余（``boxes`` 等）要**图上确实有产出方**才算。

    ⚠️ 这一步压根不在图上时**照声明返回**：那种情况该由"这一步不在流程里"
    那条守卫（``runner`` 里的状态机守卫）来说，端口判据不该抢着给答案。
    """
    declared = stage_inputs(stage)
    if not declared:
        return ()
    if diagram is None or not getattr(diagram, "nodes", ()):
        return declared
    order = ports_stage_order(diagram)
    if stage not in order:
        return declared
    active_set = set(active) if active is not None else set(order)
    required: list[str] = []
    for port in declared:
        if supplier_of(stage, port) in (SUPPLY_TASK_SOURCE, SUPPLY_TASK_INPUT):
            continue  # 任务自己供给：不是阶段产物目录，别当路径查
        if port == ARTIFACT_PAGES or diagram.nearest_producer(stage, port, active_set):
            required.append(port)
    return tuple(required)


def node_blocking_inputs(diagram, node_id: str, active=None) -> tuple[str, ...]:
    """:func:`stage_blocking_inputs` 的**节点粒度**版本（B 方案）。

    规则与阶段版逐条一致，只是把"本流程里有没有产出方"落到**节点实例**上：
    ``boxes`` 的产出方从"整阶段有检测节点"细化为"喂给 ``node_id`` 的那个
    具体节点"（:meth:`FlowDiagram.nearest_producer_node`）。同阶段只有一个
    节点的流程下与阶段版结果相同。
    """
    if diagram is None or not getattr(diagram, "nodes", ()):
        return ()
    item = diagram.node(node_id)
    if item is None or not item.stage:
        return ()
    stage = item.stage
    declared = stage_inputs(stage)
    if not declared:
        return ()
    order = ports_stage_order(diagram)
    if stage not in order:
        return declared
    active_set = set(active) if active is not None else set(order)
    required: list[str] = []
    for port in declared:
        if supplier_of(stage, port) in (SUPPLY_TASK_SOURCE, SUPPLY_TASK_INPUT):
            continue
        if port == ARTIFACT_PAGES or diagram.nearest_producer_node(
            node_id, port, active_set
        ):
            required.append(port)
    return tuple(required)


def is_entry_stage(diagram, stage: str, active=None) -> bool:
    """这一步在流程里是不是**入口**（沿图往前没有任何在流程里的阶段）。

    判据是"上游有没有活着的阶段"，不是"它是不是 ``extract``"——判后者的
    旧写法有一处硬伤：自定义流程把「检测文本框」放在第一位时它是入口，可
    ``extract`` 也不在流程里，两个都"不是"，于是取图无处落地（用户
    2026-10-06 报障：没有前置提取时检测页压根没法输入图片）。

    与 :meth:`FlowDiagram.nearest_producer` 的区别：那个问"谁给我供给"，
    这个只问"我有没有上游"——前者会返回具体阶段，后者只需要一个布尔。

    :param diagram: :class:`~desktop.steps.bpmn_diagram.FlowDiagram`；
    :param active: 本流程实际要跑的阶段集合（缺省按图求拓扑序）。
    """
    if diagram is None or not getattr(diagram, "nodes", ()):
        return False
    if stage not in ports_stage_order(diagram):
        return False
    return not diagram.nearest_producer(
        stage, "pages", set(active or ports_stage_order(diagram))
    )


def flow_entry_node(diagram) -> str | None:
    """**流程的入口节点 id**（沿图往前没有任何产出方），没有则 ``None``。

    ⚠️ **入口是"节点"的性质，不是"阶段"的性质**（B 方案，2026-10-17 用户报障）：
    用户画的是"图片拼版 → 检测文本框 → 图片去底色 → 是否拼版 →(是) 图片拼版 →
    PDF排版"，图上有**两个** ``imposition`` 节点。按阶段判"谁没有上游"会被
    第二个拼版节点带偏（它有上游 = 图片去底色），于是**任何阶段都不是入口**
    ⇒ 界面三颗输入按钮全藏、第一步没有任何输入入口（用户原话："图片拼版节点
    作为第一个节点，没有输入入口"）。

    判据：按**节点拓扑序**取第一个"沿图回溯不到 ``pages`` 产出方"的节点。

    ⚠️ 认不出阶段的节点（网关/事件/未接入的 task）**不占入口位**——它们不是
    可运行的步骤，让它们当"入口"会把输入控件挂到一个没有功能的节点上。
    """
    if diagram is None or not getattr(diagram, "nodes", ()):
        return None
    order = ports_stage_order(diagram)
    for node_id, stage in diagram.node_order():
        if stage not in order:
            continue
        if diagram.nearest_producer_node(node_id, "pages", set(order)) is None:
            return node_id
    return None


def flow_entry_stage(diagram) -> str | None:
    """**流程的入口阶段**（沿图往前没有任何在流程里的阶段），没有则 ``None``。

    用户 2026-10-06：「非图片提取节点如果做第一个节点，输入目前没做好，
    应该提醒上传输入目录或者图片」。回答这个问题需要知道"第一步是谁"——
    它是入口时，用户要往 :func:`task_input_dir`（``stages/input/``）放图，
    界面就该提醒"上传图片"而不是"上传 PDF"。

    ⚠️ **不能只问"第一个阶段是不是 ``extract``"**：自定义流程把「检测文本框」
    放第一位时，``extract`` 压根不在流程里，两个都"不是"，于是取图无处落地
    （用户 2026-10-06 报障）。判据统一走 :func:`is_entry_stage`（问"有没有
    上游"），所以"入口"是一个**图上的性质**，不是某个步骤的名字。

    ⚠️ 有多个入口时取**拓扑序里的第一个**（入口节点通常不止一个时，用户面对
    的是流程的第一格）。全都不是入口（空图/只有孤立终点）⇒ ``None``。

    ⚠️ **优先按节点判**（:func:`flow_entry_node`）：同一步骤有多个节点时，
    按阶段判会被"第二个同类节点有上游"带偏（见那里的说明）。只有节点级判据
    给不出答案（例如图坏了）才退回阶段级。
    """
    if diagram is None or not getattr(diagram, "nodes", ()):
        return None
    node = flow_entry_node(diagram)
    if node is not None:
        item = diagram.node(node)
        if item is not None and item.stage:
            return item.stage
    order = ports_stage_order(diagram)
    for stage in order:
        if is_entry_stage(diagram, stage, set(order)):
            return stage
    return None


def flow_needs_entry_images(diagram) -> bool:
    """**这条流程**是不是要用户自己提供入口图片（而不是从 PDF 提取）。

    判据：流程的入口阶段**不吃源 PDF**。入口阶段的 ``pages`` 输入会回落到
    :func:`task_input_dir`（见 :func:`resolve_input_with_entry`），而那个目录
    空着的话第一步就无从下手——所以界面要提醒"上传输入目录或者图片"
    （用户 2026-10-06）。

    ⚠️ 入口阶段是 ``extract`` 时**不算**：它吃的是源 PDF，"缺输入"该说
    "去补 PDF"（:func:`flow_needs_source_pdf` 那一路），两件事别混。
    """
    stage = flow_entry_stage(diagram)
    if stage is None:
        return False
    spec = spec_for_stage(stage)
    return spec is not None and not spec.needs_source_pdf()


def flow_entry_input_kind(diagram) -> str:
    """流程**入口这一步**要用户提供什么输入：``"pdf"`` / ``"images"`` / ``""``。

    用户 2026-10-06 给输入按钮定的过滤规则，判据**只在这一份实现**：
      ①「图片提取」打头 ⇒ 入口吃源 PDF ⇒ ``"pdf"``——界面**只显示 PDF
        输入**（图片/目录入口整对藏起来）；
      ②检测文本框/图片排版/图片去底色/生成PDF 打头 ⇒ 入口不吃 PDF，
        ``pages`` 回落到入口图片目录 ⇒ ``"images"``——**不显示 PDF，只
        显示图片输入和文件夹输入**；
      ③图上没有可运行的入口（空图/打头的节点没接功能）⇒ ``""``——
        **这些输入控件都不存在**。

    ⚠️ 这些输入控件只属于**第一个流程节点**：非入口步骤的输入来自上游
    产物，不配输入控件（规则③）。页头三颗按钮、预览区左下角「＋/📁」、
    缺输入提示层全部按返回值过滤，别在界面各处自判。
    """
    stage = flow_entry_stage(diagram)
    if stage is None:
        return ""
    spec = spec_for_stage(stage)
    if spec is None:
        return ""
    return "pdf" if spec.needs_source_pdf() else "images"


def ports_stage_order(diagram) -> tuple[str, ...]:
    """流程图上的可运行阶段（拓扑序）——``is_entry_stage`` 的内部助手。

    单独抽出来只为让上面那句 ``stage not in ...`` 读起来是"这一步在流程里
    吗"，而不是把 ``stage_order()`` 的取用摊进判断表达式里。
    """
    return diagram.stage_order()


def resolve_input_with_entry(
    task_dir: Path | str,
    stage: str,
    port: str,
    supplier: str | None,
    overrides: dict[tuple[str, str], str] | None = None,
) -> Path | None:
    """按供给方解析输入路径，并把**入口回落**收在这一处。

    :func:`resolve_input` 是纯端口查表（给自测与不关心流程的场景用）；这里
    多做一件事：当 ``supplier`` 解析不出东西（``None``）而这一步吃的是
    ``pages`` 时，回落到 :func:`task_input_dir`。

    ⚠️ **回落只认"这一步真的吃 pages"这一个端口**：``boxes`` / ``pdf`` 没有
    "用户直接提供"的说法（用户不会手写 boxes.json），让它们也回落等于把
    "接口没接好"伪装成"有输入了"，那比报错更难查。
    ⚠️ 判据必须落在**这个端口自己**身上，不能写成 ``port in stage_inputs(stage)``
    ——``rembg`` 的输入声明是 ``("pages", "boxes")``，那种写法会让它的
    ``boxes`` 端口也回落到入口目录，于是"没接检测框"被伪装成"有输入了"
    （自测 ``step_ports`` 钉住这一条）。
    同理，**产出** pages 的步骤（``extract`` 声明的是 ``("pdf",)``）压根不吃
    pages，问它"pages 输入"会拿到入口目录，而它要的其实是那个目录**自己**
    （产物落点），两回事。
    """
    if supplier is None and port == "pages" and "pages" in stage_inputs(stage):
        return task_input_dir(task_dir)
    if supplier in (None, SUPPLY_TASK_SOURCE, SUPPLY_TASK_INPUT):
        return None
    return artifact_path(task_dir, supplier, port)


def missing_stages(order: list[str], *, start: str | None = None) -> list[str]:
    """给定顺序，返回**输入还缺上游**的阶段（按顺序）。

    :data:`SUPPLIERS` 是静态声明，它默认"每个上游都跑过"。真要上线 BPM
    编排时，用它在执行前先做一次依赖检查：某个阶段的输入端口若由一个
    **还没执行**的上游供给，它就是当前不该跑的。

    ⚠️ 不在这里判断"目录里有没有文件"——那要读磁盘、不是纯逻辑。运行态
    的就绪判断走 :func:`input_ready`。
    """
    done = {start} if start else set()

    def _satisfied(supplier: str | None) -> bool:
        """这个供给方算不算"已经跑过"。

        ⚠️ 同格多动作（``detect`` / ``detect_submit``）不是独立的流程格，
        ``order`` 里只有步骤 key——按原名比对会把"缺上游"误报在它们身上
        （顺序正确也报 ``detect`` 未就绪）。所以再看一眼它所属的**界面格**。
        """
        if supplier in done:
            return True
        step = STAGE_STEPS.get(supplier or "")
        return bool(step and step != supplier and step in done)

    waiting: list[str] = []
    for stage in order:
        if stage in done:
            continue
        for port in stage_inputs(stage):
            supplier = supplier_of(stage, port)
            # ⚠️ **必须放过任务源哨兵**（``<task>``）：它不是阶段、永远不会出现在
            #    ``done`` 里，当成"上游缺失"会把流程入口（extract）永远判成不能跑。
            #    入口阶段本来就该直接放行——它的输入由任务自己供给，不靠谁先跑。
            if supplier in (None, SUPPLY_TASK_SOURCE) or _satisfied(supplier):
                continue
            waiting.append(stage)
            break
        done.add(stage)
    return waiting


def describe(stage: str) -> str:
    """一行可读描述（``去底色：图片 + 检测框 → 图片``，日志/自测用）。"""
    ins = " + ".join(PORT_LABELS.get(p, p) for p in stage_inputs(stage)) or "—"
    outs = " + ".join(PORT_LABELS.get(p, p) for p in stage_outputs(stage)) or "—"
    return f"{stage}：{ins} → {outs}"
