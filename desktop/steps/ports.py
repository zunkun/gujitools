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

#: 全部产物类型 → 中文名（提示语与界面文案用，别处不另写一份）。
ARTIFACT_LABELS: dict[str, str] = {
    ARTIFACT_PDF: "PDF",
    ARTIFACT_PAGES: "图片",
    ARTIFACT_BOXES: "检测框",
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
    "STAGE_LOCATIONS",
    "STAGE_STEPS",
    "SUPPLIERS",
    "SUPPLY_TASK_SOURCE",
    "artifact_of",
    "artifact_path",
    "describe",
    "input_ready",
    "location_of",
    "missing_stages",
    "print_input_overrides",
    "print_pages_supplier",
    "resolve_input",
    "spec_for_stage",
    "stage_artifacts",
    "stage_inputs",
    "stage_outputs",
    "supplier_of",
]