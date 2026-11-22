# -*- coding: utf-8 -*-
"""端口 / 落点 / 连线相关的常量表（唯一事实来源，别处不另写一份）。"""

from __future__ import annotations

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

#: **缺了也不阻塞就绪**的输入端口：这些端口是"锦上添花"，没有它这一步照样跑得出结果。
#:
#: - ``boxes``（检测框）：``detect`` **可能一框未检**（空白页 / 无文字页 / 整页模式），
#:   那时 ``boxes.json`` 本来就不会存在——它不是失败，是**正常结果**。
#:
#: ⚠️ 2026-10-22 起默认流程里**没有任何一步把 boxes 声明为输入**（去底色不再
#:    按框裁图），这张表因此暂时不起作用；保留它是给"将来某一步要吃检测框"
#:    留的唯一开关，别在别处另写一份"这个端口缺了也行"的判断。
OPTIONAL_INPUT_PORTS = frozenset({ARTIFACT_BOXES})

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


# ---------------------------------------------------------------- 端口声明
#: 运行阶段 → 步骤 key。⚠️ **多数阶段与步骤 key 同名**，只有
#: ``detect_submit`` 例外（它是 ``detect`` 步骤的第二个动作，见模块 docstring）。
STAGE_STEPS: dict[str, str] = {
    "extract": "extract",
    "detect": "detect",
    "detect_submit": "detect",
    "rembg": "rembg",
    "print": "print",
    "imposition": "imposition",
}

#: 运行阶段 → 流程图上显示的**中文节点名**。
#:
#: ⚠️ 「提交检测结果」要单独一句：它与「检测文本框」共用同一份
#: :class:`StepSpec`，直接取 ``stage_name()`` 会让流程图上出现**同名节点**
#: （两个「检测文本框」），用户在图上根本分不清哪个是检测、哪个是提交。
#: 这里给独立文案，与 :data:`desktop.store.tasks.STAGE_LABELS` 的口径一致
#: ——但**真源在这里**：store 那张表改为从本函数派生。
#:
#: ⚠️ 别把它当"步骤名"用：步骤条上不显示 ``detect_submit``（它折叠进
#: ``detect`` 那一格，见 :func:`desktop.steps.flow.FlowDefinition` 的槽位折叠）。
STAGE_LABELS: dict[str, str] = {
    "detect_submit": "提交检测结果",
}

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
#: ⚠️ 默认模板里它叫「上传文件」（用户 2026-11-17：「源PDF 应该改成上传文件」
#: ——它管的不只是 PDF，DjVu 也走这里）。
SOURCE_PDF_NODE_NAMES = ("上传文件", "源PDF", "源 PDF", "上传PDF", "上传 PDF", "PDF")

#: 「是否拼版」（排他网关）守着的那一格。
#:
#: 用户 2026-10-08：
#:
#: > 其实根本就没有判断这个组件，只有「是否拼版」这个特殊的判断组件，
#: > 也就是说是否拼版依附拼版……是否拼版其实是拼版组件中的一个属性是否启用
#:
#: 所以图上的网关**不是**一个可自由增删的独立组件，它是「图片拼版」这一步的
#: 附属图形（与 :func:`paired_node_for_stage` 同一类事实，只是方向是单向的）：
#:
#: - 「图片拼版」没了 ⇒ 它守着的那个问题不存在，网关跟着删
#:   （:func:`orphaned_gateway_ids`）；
#: - 反方向**不成立**——「图片拼版」可以没有网关（用户 2026-10-08 前一条口径：
#:   "图片拼版可以不需要判断是否拼版"），那时这一步无条件执行，启用与否仍由
#:   「图片拼版」参数面板的开关决定（:data:`~desktop.steps.scheduler.CONDITIONS`）。
#:
#: ⚠️ 这也是编辑器**不再提供"添加判断"入口**的理由：网关只能随模板文件来，
#: 不由用户在界面上凭空摆一个。
GATEWAY_GUARD_STAGE = "imposition"


# ---------------------------------------------------------------- 产物落点
#:
#: 运行阶段 → ``{端口名: 相对 tasks/<任务号>/ 的落点}``。
#: ⚠️ **这张表就是"任务目录布局"的唯一事实来源**：以前它散在
#: ``desktop.store.tasks`` 的 ``extract_output_dir`` / ``rembg_output_dir`` /
#: ``print_output_pdf`` 三个方法里，加一步要新写一个方法。现在加一步只加一行，
#: 调用方走 :func:`artifact_path`。
#:
#: - ``detect`` 的 ``boxes`` 落在**任务根**（``boxes.json``）而不是
#:   ``stages/detect/``：它不是一堆图片、是一个坐标文件，第二步的预览标注与
#:   YOLO 导出都按这个固定名读（``utils.box_geometry`` 的槽位约定也按它对齐）。
#:   detect 另有一个 ``thumbnails/detect`` 参考缩略图目录，但那**不是产物**
#:   （只是给界面看的缓存），所以不进这张表。
STAGE_LOCATIONS: dict[str, dict[str, str]] = {
    "extract": {"pages": "stages/extract"},
    # detect 两个产物分两处（2026-10-22）：
    #   · ``boxes`` 落在**任务根**（``boxes.json``）——它不是一堆图片、是一个
    #     坐标文件，第二步预览与 YOLO 导出都按这个固定名读；
    #   · ``pages`` 是「分割图片」逐框裁出来的成品图，落 ``stages/detect``，
    #     给第三步「图片去底色」当输入（未提交 ⇒ 这个目录是空的/不存在，
    #     第三步自然转不过去，正是"提交才算本步完成"的落地方式）。
    "detect": {"boxes": "boxes.json"},
    "detect_submit": {"pages": "stages/detect"},
    # 去底色：单一步动作，整图全局 Otsu 后直接落成品图（白底转透明）。
    "rembg": {"pages": "stages/rembg"},
    "imposition": {"pages": "stages/imposition"},
    "print": {"pdf": "stages/print/print.pdf"},
}


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

SUPPLIERS: dict[str, dict[str, str]] = {
    # 提取：吃任务自带的 PDF 副本，没有上游。
    "extract": {"pdf": SUPPLY_TASK_SOURCE},
    # 检测：吃提取出的页面图（或流程入口图片）。
    "detect": {"pages": "extract"},
    # 提交检测结果：逐框裁图，同样吃上游页面图（检测框是同一步的产物，
    # 由提交动作自己按任务目录读，不占输入端口）。
    "detect_submit": {"pages": "extract"},
    # 去底色：吃**「检测文本框」提交后的裁图**（2026-10-22）。
    # ⚠️ 这是本次大改造的关键一条：以前去底色吃原始页 + 检测框、自己在提交时
    #    按 border 裁；现在裁剪发生在第二步的提交里，去底色只做整图去底色。
    "rembg": {"pages": "detect_submit"},
    # 拼版：吃去底色的成品图（``stages/rembg``）。
    "imposition": {"pages": "rembg"},
    # PDF排版：默认吃第三步的成品图；拼版生效时改由 imposition 供给
    # （见 :func:`print_pages_supplier`——那是**运行时**的一处覆盖，
    # 与这张静态表分开，免得把"用户开了拼版开关"这种运行态写成静态结构）。
    "print": {"pages": "rembg"},
}


#: 可选节点（拼版）在流程里**排在哪个阶段之前**。
#:
#: ⚠️ 这条不是"流程顺序"（那是 :data:`~desktop.steps.spec.FLOW_STAGES` 的事），
#: 而是"拼版插在第四步前面"这一事实的**唯一声明处**：步骤条把节点插在最后一位
#: 之前（``desktop/components/step_bar.py``），任务列表的节点胶囊也按它把
#: 「拼版」排在「PDF」之前（``desktop/workers/task_rows_worker.py``）。两处
#: 都别自己数下标——BPM 换顺序时只改这里。
IMPOSITION_ANCHOR: str = "print"
