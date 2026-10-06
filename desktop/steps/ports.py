# -*- coding: utf-8 -*-
"""步骤的**输入 / 输出端口**：把「这一步吃什么、吐什么」写成可连线的声明。

用户 2026-10-03 的口径：

> 任务流程每一步解耦，后续我会使用 bpm 流程处理不同的任务流程顺序，
> 因此每一步都有输入，输出就可以了

本模块只回答三个问题，**不碰界面、不碰算法、不决定顺序**：

1. **数据"是什么"** —— :data:`ARTIFACTS` 里的**产物类型**（PDF / 图片 /
   检测框）。BPM 连线按它匹配：上游只要吐出 ``pages``，无论它来自图片提取
   还是图片拼版，下游都接得上。**这是"解耦"真正落地的地方**——下游不认
   上游是谁，只认产物类型。
2. **这一步要什么、给什么** —— :func:`stage_inputs` / :func:`stage_outputs`，
   它们从 :class:`~desktop.steps.spec.StepSpec` 的 ``inputs`` / ``outputs``
   字段派生（那是**唯一的端口声明处**），不在这里另写一份。
3. **产物落在哪** —— :data:`STAGE_LOCATIONS` 给出每个端口在
   ``tasks/<任务号>/`` 下的相对落点，:func:`artifact_path` 解析成绝对路径。

**顺序与连线**由 :data:`SUPPLIERS` 一处决定：键是消费阶段，值是
``{端口名: 供给阶段}``。将来的 BPM 换顺序 / 换连线只改这张表，算法、界面、
任务目录布局全都不用动。

⚠️ **运行阶段名与步骤 key 不是一回事**（本模块唯一的额外概念）：

- 步骤 key 是 :data:`~desktop.steps.spec.STEP_KEYS` 里的 ``extract`` /
  ``detect`` / ``rembg`` / ``print`` / ``imposition``，描述"这是什么功能"；
- **运行阶段**多一个 ``rembg_submit``——它是第三步「去底色」面板上的
  「提交本次任务」按钮触发的**同一步骤的第二个动作**（先生成整页预览图到
  ``stages/rembgpreview``，用户确认后才把最终图落到 ``stages/rembg``）。
  端口系统必须认得它，否则第三步的产物没有落点、第四步也没有输入。

    ====================  ==========================================
    运行阶段               步骤 key / 端口
    ====================  ==========================================
    ``extract``            ``extract``：in=pdf / out=pages
    ``detect``             ``detect``：in=pages / out=boxes
    ``rembg``              ``rembg``：in=pages,boxes / out=pages（预览）
    ``rembg_submit``       ``rembg``：in=pages / out=pages（最终图）
    ``print``              ``print``：in=pages / out=pdf
    ====================  ==========================================

⚠️ 本模块**纯逻辑、不 import 任何 Qt**，因此可以被自测、CLI 与将来的
BPM 编排引擎安全导入（与 :mod:`desktop.steps.spec` 同一约束）。
"""

from __future__ import annotations

from pathlib import Path

from desktop.steps.spec import StepSpec, spec_by_key

# ---------------------------------------------------------------- 产物类型
#: 源 PDF（任务自带的备份副本）。任务流程只有提取这一步吃它。
ARTIFACT_PDF = "pdf"
#: 页面图片（一批，目录形态）。流水线里流通的主力产物。
ARTIFACT_PAGES = "pages"
#: 检测框坐标（``boxes.json``，单文件）。只有 rembg 消费它。
ARTIFACT_BOXES = "boxes"
#: **流程入口图片**：用户直接放进任务里的那批图。
#:
#: ⚠️ 为什么需要这个产物类型（用户 2026-10-06）：
#: > 如果某个节点作为第一个节点，一定要可以有输入可用。
#:
#: 以前"图片输入"只有一条来路——上游的 ``pages`` 端口。于是自定义流程把
#: 「检测文本框」放在第一位时，它的 ``pages`` 输入沿图回溯不到任何供给方，
#: 落成 ``None``⇒ 点执行弹"输入未接好"，预览永远"暂无图片，请先完成提取"。
#: 那不是"用户没跑前一步"，而是**这条流程本来就不需要前一步**——它需要的是
#: 一个属于自己的入口。
ARTIFACT_INPUT = "input"

#: 全部产物类型 → 中文名（提示语与界面文案用，别处不另写一份）。
ARTIFACT_LABELS: dict[str, str] = {
    ARTIFACT_PDF: "PDF",
    ARTIFACT_PAGES: "图片",
    ARTIFACT_BOXES: "检测框",
    ARTIFACT_INPUT: "入口图片",
}

#: 端口名 → 产物类型。:class:`StepSpec` 的 ``inputs``/``outputs`` 里写的
#: 就是这些端口名，两处靠这张表对上——**端口名本身不表示类型以外的任何事**。
PORT_ARTIFACTS: dict[str, str] = {
    "pdf": ARTIFACT_PDF,
    "pages": ARTIFACT_PAGES,
    "boxes": ARTIFACT_BOXES,
}

#: 端口名 → 中文名（"输入：图片"这种提示用）。
PORT_LABELS: dict[str, str] = {
    name: ARTIFACT_LABELS[kind] for name, kind in PORT_ARTIFACTS.items()
}


def artifact_of(port: str) -> str:
    """端口名 → 产物类型；未知端口按"页面图片"兜底（别让界面崩）。"""
    return PORT_ARTIFACTS.get(port, ARTIFACT_PAGES)


# ---------------------------------------------------------------- 端口声明
#: 运行阶段 → 步骤 key。⚠️ **多数阶段与步骤 key 同名**，只有
#: ``rembg_submit`` 例外（它是 ``rembg`` 步骤的第二个动作，见模块 docstring）。
STAGE_STEPS: dict[str, str] = {
    "extract": "extract",
    "detect": "detect",
    "rembg": "rembg",
    "rembg_submit": "rembg",
    "print": "print",
    "imposition": "imposition",
}


def stage_inputs(stage: str) -> tuple[str, ...]:
    """这一步**消费**哪些端口（来自 ``StepSpec.inputs``，不另写一份）。

    ``rembg_submit`` 是"把预览图定稿"的提交动作，不重新检测，所以它**不吃**
    ``boxes``（框在预览那一步已经用过了）；这里显式覆盖，其余阶段直接取 spec。
    """
    if stage == "rembg_submit":
        return ("pages",)
    spec = spec_by_key(STAGE_STEPS.get(stage, stage))
    return tuple(spec.inputs) if spec else ()


def stage_outputs(stage: str) -> tuple[str, ...]:
    """这一步**产出**哪些端口（来自 ``StepSpec.outputs``，不另写一份）。"""
    spec = spec_by_key(STAGE_STEPS.get(stage, stage))
    return tuple(spec.outputs) if spec else ()


#: 运行阶段 → 流程图上显示的**中文节点名**。
#:
#: ⚠️ 只有 ``rembg_submit`` 需要单独一句：它和 ``rembg`` 共用 ``rembg`` 的
#: :class:`StepSpec`，直接取 ``stage_name()`` 会让流程图上出现**两个同名节点**
#: （都叫「图片去底色」），用户在图上根本分不清哪个是"生成预览"、哪个是
#: "提交定稿"。这里给它独立文案，与 :data:`desktop.store.tasks.STAGE_LABELS`
#: 的口径一致——但**真源在这里**：store 那张表改为从本函数派生。
#:
#: ⚠️ 别把它当"步骤名"用：步骤条上不显示 ``rembg_submit``（它折叠进第三步格，
#: 见 :func:`desktop.steps.flow.FlowDefinition` 的槽位折叠）。
STAGE_LABELS: dict[str, str] = {
    "rembg_submit": "提交去底色结果",
}


def stage_label(stage: str) -> str:
    """运行阶段 → 流程图节点名（默认走 spec，只有 ``rembg_submit`` 单独一句）。

    页面里凡是"按 stage 给这个阶段起个中文名"（BPMN 节点名、进度/日志文案）
    都走本函数，**不要**自己 ``spec_by_key(stage)``——那会在
    ``rembg_submit`` 上拿到 ``None`` 或与 ``rembg`` 同名。
    """
    override = STAGE_LABELS.get(stage)
    if override:
        return override
    spec = spec_for_stage(stage)
    return spec.stage_name() if spec else stage


def spec_for_stage(stage: str) -> StepSpec | None:
    """运行阶段 → 它对应的 :class:`StepSpec`（界面查表统一走这里）。

    ⚠️ 这一层映射（:data:`STAGE_STEPS`）在：``rembg_submit`` 要拿 ``rembg`` 的
    声明（它是同一步骤的第二个动作），而 ``imposition`` 虽是**伪步骤**（不在
    ``STAGES`` 里）却也有自己的 spec。页面里凡是"按 stage 取这一步的界面元数据"
    （按钮文案、控制列宽度、预览控件名、右栏专属区块）都必须走本函数，
    **不要**自己 ``spec_by_key(stage)``——那会在 ``rembg_submit`` 上拿到 None。
    """
    return spec_by_key(STAGE_STEPS.get(stage, stage))


def stage_artifacts(stage: str) -> tuple[str, ...]:
    """这一步消费哪些**产物类型**（端口名翻译过来）。"""
    return tuple(artifact_of(port) for port in stage_inputs(stage))


#: 「上传 PDF（源）」与「提取图片」是**一对**：只有 extract 吃源 PDF，而源 PDF
#: 在图上就是那个 ``startEvent``。删掉其中任何一个，另一个就**没有意义**——
#: 删了 extract 而留着 startEvent＝图上有个入口却不产出图片，第一步照样跑不动；
#: 删了 startEvent 而留着 extract＝extract 的输入没有来源，界面上还会一直催
#: "上传 PDF"（那正是用户 2026-10-06 说的"右侧不需要 PDF 图标"）。
#:
#: ⚠️ 这是**成对关系**的事实声明处。删除联动（:func:`paired_node_for_stage` 的
#: 使用方）与界面显隐都从这里取，别在两处各写一遍"extract↔startEvent"。
SOURCE_PDF_STAGE = "extract"
#: 源 PDF 在图上不是阶段、而是一个事件节点，用**它在这张图里的名字**认。
SOURCE_PDF_NODE_NAMES = ("源PDF", "源 PDF", "上传PDF", "上传 PDF", "PDF")


def source_pdf_node_ids(diagram) -> tuple[str, ...]:
    """图里代表「源 PDF」的节点 id（没有则空元组）。

    认法有两条，任一命中即可：

    1. **事件型**节点（``startEvent``）——BPMN 里流程入口就是它；
    2. **名字**在 :data:`SOURCE_PDF_NODE_NAMES` 里——用户可以把它改名，
       事件型仍是主判据；名字判据兜住"被改成 task 型"或用户自己画的。

    ⚠️ **别按 stage 判**：「源 PDF」没有 ``stage``（它不是运行阶段，
    :data:`desktop.steps.ports.SUPPLY_TASK_SOURCE` 才是它的语义标记）。
    """
    if diagram is None or not getattr(diagram, "nodes", ()):
        return ()
    from desktop.steps.bpmn_diagram import KIND_START

    return tuple(
        n.id for n in diagram.nodes
        if n.kind == KIND_START
        or (n.name or "").strip() in SOURCE_PDF_NODE_NAMES
    )


def is_source_pdf_node(diagram, node_id: str) -> bool:
    """这个节点是不是「源 PDF」（图上那个入口事件）。"""
    return node_id in source_pdf_node_ids(diagram)


def paired_node_for_stage(diagram, node_id: str) -> str | None:
    """删掉 ``node_id`` 时**该一起删掉**的配对节点 id；没有则 ``None``。

    用户 2026-10-06：

    > 流程编辑中，如果删除了 上传pdf或者 pdf图片提取中的一个，
    > 另外���个的存在没有意义，因此需要同步删除另外一个

    成对关系是双向的：

    - 删「源 PDF」事件 ⇒ 一并删 ``extract`` 节点；
    - 删 ``extract`` 节点 ⇒ 一并删「源 PDF」事件。

    ⚠️ **只删一个会留下坏图**：留着 startEvent 时第一步的``pages`` 沿图回溯
    不到任何产出者，界面就一直催"上传图片"；留着 extract 时它吃的是
    :data:`SUPPLY_TASK_SOURCE`（任务源 PDF），而界面上那个 PDF 图标会**仍然
    亮着**催你上传——正是用户说的"不需要 PDF 上传图标"。

    ⚠️ 返回 ``None``（而不是"没有配对就不删"里的空字符串）表示"无配对"；
    调用方**必须自己再判一次** ``extract`` 节点是否真的在图里（可能已经被
    用户先删了），别假定它一定存在。
    """
    if diagram is None or not getattr(diagram, "nodes", ()):
        return None
    if is_source_pdf_node(diagram, node_id):
        # 反向：源 PDF 被删 ⇒ 同格删掉 extract
        for item in diagram.nodes:
            if item.stage == SOURCE_PDF_STAGE:
                return item.id
        return None
    item = diagram.node(node_id)
    if item is not None and item.stage == SOURCE_PDF_STAGE:
        # 正向：extract 被删 ⇒ 同格删掉源 PDF 事件
        for other in source_pdf_node_ids(diagram):
            return other
    return None


def flow_needs_source_pdf(diagram) -> bool:
    """**这条流程**里有没有直接吃源 PDF 的阶段吗（要问图，别写死）。
    ⚠️ **两处界面问的是同一个问题**（用户 2026-10-06）：
      ①创建任务页——"流程要 PDF 而用户没给，是否问一句"；
      ②任务详情页——"流程要 PDF 而这个任务还没源文件，按钮该高亮 + 顶部
      该红字提示 + 进页面该弹窗"。所以这个判据**只有这一份实现**，
      别在两个页面各写一遍（漂移起来是"创建时问了、详情页却不提示"）。

    阶段→"要不要源 PDF"走 :meth:`StepSpec.needs_source_pdf`（端口声明
    ``inputs`` 含 ``pdf``）；⚠️ **别拿** ``input_noun()`` 判——它是给人看的
    称呼，四步里三步都写着"选择图片"，用它会把去底色/生成 PDF 也算进去
    （它们吃的是上游产出的页，不是用户的文件）。

    :param diagram: :class:`~desktop.steps.bpmn_diagram.FlowDiagram`；
        空图/``None`` 一律 False（没有流程就没有"要不要"可言）。
    """
    if diagram is None or not getattr(diagram, "nodes", ()):
        return False
    from desktop.steps.scheduler import Scheduler

    # ⚠️ imposition 传 False：条件不满足时那一格被剔除，而我们问的是"有没有
    #    哪一步要 PDF"，剔除它不影响答案。
    sched = Scheduler.from_diagram(diagram, {"imposition": False})
    for stage in sched.stages:
        spec = spec_for_stage(stage)
        if spec is not None and spec.needs_source_pdf():
            return True
    return False


# ---------------------------------------------------------------- 产物落点
#: 运行阶段 → ``{端口名: 相对 tasks/<任务号>/ 的落点}``。
#:
#: ⚠️ **这张表就是"任务目录布局"的唯一事实来源**：以前它散在
#: ``desktop.store.tasks`` 的 ``extract_output_dir`` / ``rembg_output_dir`` /
#: ``rembg_preview_output_dir`` / ``print_output_pdf`` 四个方法里，加一步要
#: 新写一个方法。现在加一步只加一行，调用方走 :func:`artifact_path`。
#:
#: - ``detect`` 的 ``boxes`` 落在**任务根**（``boxes.json``）而不是
#:   ``stages/detect/``：它不是一堆图片、是一个坐标文件，且第三步 rembg
#:   直接按这个固定名读（``utils.box_geometry`` 的槽位约定也按它对齐）。
#:   detect 另有一个 ``thumbnails/detect`` 参考缩略图目录，但那**不是产物**
#:   （只是给界面看的缓存），所以不进这张表。
STAGE_LOCATIONS: dict[str, dict[str, str]] = {
    "extract": {"pages": "stages/extract"},
    "detect": {"boxes": "boxes.json"},
    "rembg": {"pages": "stages/rembgpreview"},
    "rembg_submit": {"pages": "stages/rembg"},
    "imposition": {"pages": "stages/imposition"},
    "print": {"pdf": "stages/print/print.pdf"},
}


def location_of(stage: str, port: str) -> str | None:
    """运行阶段某端口的相对落点；没有登记返回 ``None``。"""
    return STAGE_LOCATIONS.get(stage, {}).get(port)


def artifact_path(task_dir: Path | str, stage: str, port: str) -> Path | None:
    """产物在任务目录下的**绝对路径**；该阶段没登记这个端口则 ``None``。

    ``task_dir`` 传 ``tasks/<任务号>/``（不是数据根）。
    """
    location = location_of(stage, port)
    if location is None:
        return None
    return Path(task_dir) / location


# ---------------------------------------------------------------- 连线（BPM 的边）
#: **谁供给哪个端口** → 消费阶段。键是消费阶段，值是 ``{端口名: 供给阶段}``。
#:
#: 这张表就是"流程顺序"的全部知识。换顺序、换连线（BPM 的价值所在）**只改
#: 这里**，不必碰 :func:`artifact_path`、算法与界面。
#:
#: :data:`SUPPLY_TASK_SOURCE` 这个哨兵值表示"由任务自己供给"（任务目录里
#: 备份的源 PDF），不是任何阶段——它是流程的**入口**，天然无上游。
SUPPLY_TASK_SOURCE = "<task>"

#: **流程入口图片**哨兵：表示"由用户直接放进任务的图片供给"。
#:
#: ⚠️ 它与 :data:`SUPPLY_TASK_SOURCE`（源 PDF）**是两件事**：后者是"任务自带
#: 备份的 PDF"，只有提取这一步吃它；本哨兵是"一批图片"，任何**缺上游的
#: 步骤**都可以拿它当输入——流程的第一个节点就是这么跑的。
SUPPLY_TASK_INPUT = "<task-input>"

#: 入口图片在任务目录下的落点（**布局的唯一声明处**，别处不写死）。
TASK_INPUT_LOCATION = "stages/input"


def task_input_dir(task_dir: Path | str) -> Path:
    """入口图片目录的绝对路径（``tasks/<任务号>/stages/input/``）。

    ⚠️ **目录不需要事先存在**：它是"用户往里放图"的地方，任务刚建出来时
    本来就是空的。判"有没有图"要看里面有没有图片文件，别只看目录在不在。
    """
    return Path(task_dir) / TASK_INPUT_LOCATION

SUPPLIERS: dict[str, dict[str, str]] = {
    # 提取：吃任务自带的 PDF 副本，没有上游。
    "extract": {"pdf": SUPPLY_TASK_SOURCE},
    # 检测：吃提取出的页面图。
    "detect": {"pages": "extract"},
    # 去底色预览：吃提取的页面图 **和** 检测的框。
    "rembg": {"pages": "extract", "boxes": "detect"},
    # 提交：把预览图定稿到最终目录，仍以提取的页面图为输入。
    "rembg_submit": {"pages": "extract"},
    # 拼版：吃提取的页面图（与去底色并行，不是它的下游）。
    "imposition": {"pages": "extract"},
    # 生成 PDF：默认吃第三步提交的成品图；拼版生效时改由 imposition 供给
    # （见 :func:`print_pages_supplier`——那是**运行时**的一处覆盖，
    # 与这张静态表分开，免得把"用户开了拼版开关"这种运行态写成静态结构）。
    "print": {"pages": "rembg_submit"},
}


def supplier_of(stage: str, port: str) -> str | None:
    """某阶段某端口由谁供给；没有连线返回 ``None``。"""
    return SUPPLIERS.get(stage, {}).get(port)


def print_pages_supplier(imposition_active: bool) -> str:
    """生成 PDF 取图的上游：拼版生效时是 ``imposition``，否则是第三步提交。

    ⚠️ 抽成函数而不是在 :data:`SUPPLIERS` 里写死，是为了让"拼版生效"这种
    **运行态开关**（用户在详情页勾了拼版节点）有一个明确、可测的出口：
    BPM 编排时这正是"条件连线"的落点。
    """
    return "imposition" if imposition_active else "rembg_submit"


#: 可选节点（拼版）在流程里**排在哪个阶段之前**。
#:
#: ⚠️ 这条不是"流程顺序"（那是 :data:`~desktop.steps.spec.FLOW_STAGES` 的事），
#: 而是"拼版插在第四步前面"这一事实的**唯一声明处**：步骤条把节点插在最后一位
#: 之前（``desktop/components/step_bar.py``），任务列表的子任务胶囊也按它把
#: 「拼版」排在「PDF」之前（``desktop/workers/task_rows_worker.py``）。两处
#: 都别自己数下标——BPM 换顺序时只改这里。
IMPOSITION_ANCHOR: str = "print"


def print_input_overrides(imposition_active: bool) -> dict[tuple[str, str], str]:
    """打印阶段的运行时连线覆盖（拼版开关 → 上游换成 imposition）。

    传给 :func:`resolve_input` / :func:`input_ready`。⚠️ 返回**新字典**：
    调用方可能缓存它，别让一次运行的状态漏进下一次。
    """
    return {("print", "pages"): print_pages_supplier(imposition_active)}


def resolve_input(task_dir: Path | str, stage: str, port: str,
                  overrides: dict[tuple[str, str], str] | None = None) -> Path | None:
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


def input_ready(task_dir: Path | str, stage: str, port: str,
                overrides: dict[tuple[str, str], str] | None = None) -> bool:
    """这个端口的输入**已经就位**吗（落点存在且非空）。

    只看"有没有东西"，不判断内容对不对——那是功能层的事。
    """
    path = resolve_input(task_dir, stage, port, overrides)
    if path is None:
        return False
    if path.is_dir():
        return any(path.iterdir())
    return path.exists()


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
    return not diagram.nearest_producer(stage, "pages", set(active or ports_stage_order(diagram)))


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
    """
    if diagram is None or not getattr(diagram, "nodes", ()):
        return None
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


def ports_stage_order(diagram) -> tuple[str, ...]:
    """流程图上的可运行阶段（拓扑序）——``is_entry_stage`` 的内部助手。

    单独抽出来只为让上面那句 ``stage not in ...`` 读起来是"这一步在流程里
    吗"，而不是把 ``stage_order()`` 的取用摊进判断表达式里。
    """
    return diagram.stage_order()


def resolve_input_with_entry(task_dir: Path | str, stage: str, port: str,
                             supplier: str | None,
                             overrides: dict[tuple[str, str], str] | None = None
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
    waiting: list[str] = []
    for stage in order:
        if stage in done:
            continue
        for port in stage_inputs(stage):
            supplier = supplier_of(stage, port)
            # ⚠️ **必须放过任务源哨兵**（``<task>``）：它不是阶段、永远不会出现在
            #    ``done`` 里，当成"上游缺失"会把流程入口（extract）永远判成不能跑。
            #    入口阶段本来就该直接放行——它的输入由任务自己供给，不靠谁先跑。
            if supplier in (None, SUPPLY_TASK_SOURCE) or supplier in done:
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


__all__ = [
    "ARTIFACT_BOXES",
    "ARTIFACT_LABELS",
    "ARTIFACT_PAGES",
    "ARTIFACT_PDF",
    "PORT_ARTIFACTS",
    "PORT_LABELS",
    "STAGE_LABELS",
    "STAGE_LOCATIONS",
    "STAGE_STEPS",
    "SUPPLIERS",
    "SUPPLY_TASK_INPUT",
    "SUPPLY_TASK_SOURCE",
    "TASK_INPUT_LOCATION",
    "artifact_of",
    "artifact_path",
    "describe",
    "flow_entry_stage",
    "flow_needs_entry_images",
    "flow_needs_source_pdf",
    "is_source_pdf_node",
    "paired_node_for_stage",
    "source_pdf_node_ids",
    "input_ready",
    "is_entry_stage",
    "location_of",
    "missing_stages",
    "print_input_overrides",
    "print_pages_supplier",
    "resolve_input",
    "resolve_input_with_entry",
    "spec_for_stage",
    "stage_artifacts",
    "stage_inputs",
    "stage_label",
    "stage_outputs",
    "supplier_of",
    "task_input_dir",
]