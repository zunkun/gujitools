# -*- coding: utf-8 -*-
"""端口声明：某一步吃什么、吐什么，以及端口名与产物类型的翻译。"""

from __future__ import annotations

from desktop.steps.ports.constants import (
    ARTIFACT_PAGES,
    PORT_ARTIFACTS,
    STAGE_LABELS,
    STAGE_STEPS,
)
from desktop.steps.spec import StepSpec, spec_by_key


def artifact_of(port: str) -> str:
    """端口名 → 产物类型；未知端口按"页面图片"兜底（别让界面崩）。"""
    return PORT_ARTIFACTS.get(port, ARTIFACT_PAGES)


def stage_inputs(stage: str) -> tuple[str, ...]:
    """这一步**消费**哪些端口（来自 ``StepSpec.inputs``，不另写一份）。

    ``detect_submit`` 是"把检测结果定稿"的动作，不重新检测、也不看检测框，
    只吃上游的 ``pages``；这里显式覆盖，其余阶段直接取 spec。
    """
    if stage == "detect_submit":
        return ("pages",)
    spec = spec_by_key(STAGE_STEPS.get(stage, stage))
    return tuple(spec.inputs) if spec else ()


def stage_outputs(stage: str) -> tuple[str, ...]:
    """这一步**产出**哪些端口（来自 ``StepSpec.outputs``，不另写一份）。

    ⚠️ 这是**步骤级**声明：``detect`` 声明 ``("boxes", "pages")``——这一步整体
    两样都给（框在"检测"、图在"提交"）。凡是要问"图上这个节点能不能供给某个
    端口"（:meth:`FlowDiagram.nearest_producer`）都用它，否则第二步之后的下游
    会沿图跳过检测节点、直接去拿提取的原图。

    动作级（"这一下具体写了什么文件"）见 :func:`action_outputs`。
    """
    spec = spec_by_key(STAGE_STEPS.get(stage, stage))
    return tuple(spec.outputs) if spec else ()


def action_outputs(stage: str) -> tuple[str, ...]:
    """**动作级**产出端口：同格的每个动作各自只产一样（:func:`fold_forward` 用）。

    ``detect`` 那一下只写 ``boxes.json``、``detect_submit`` 才裁图。折返时
    必须按这个粒度挑"最靠后的、也产出该端口的动作"，否则 `detect.pages`
    会折到 ``detect`` 自己（它声明了 pages，却没有那个落点）。
    """
    if stage == "detect":
        return ("boxes",)
    if stage == "detect_submit":
        return ("pages",)
    return stage_outputs(stage)


#: **同格多动作的前折**：把图上认出的阶段升级到**同一界面格里最靠后的、
#: 也产出该端口的动作**。定义就是下面这个函数，这里只留一段说明：
#:
#: 唯一的实际用处是「检测文本框」这一步：图上只有一个「检测文本框」节点，
#: 但同一格里有 ``detect``（只出框 → ``boxes.json``）与 ``detect_submit``
#: （提交时逐框裁图 → ``stages/detect``）两个动作，而**消费方要的是裁好的图**。
#: 按图回退时若直接取 ``detect``，拿到的是没有那个落点的阶段——"打印出来是
#: 没提交的图"，比报错更难发现。
#:
#: ⚠️ 折叠**只在按图解析产出方**时做（``store._node_ref_path`` /
#: ``FlowDiagram.nearest_producer*``），别拿它去算节点自己的产物目录。


def fold_forward(stage: str, port: str) -> str:
    """把阶段折到**同格里最靠后的、也产出该端口的动作**。

    判定完全从 :data:`STAGE_STEPS`（同格关系）与 :func:`action_outputs`
    （**每个动作**产什么）派生，**不另写一张表**：同格里多个阶段都产出该端口时取声明
    顺序里最靠后的那个；没有同格伙伴时原样返回。语义与用途见上面那段说明。
    """
    step = STAGE_STEPS.get(stage, stage)
    siblings = [
        sibling
        for sibling, owner in STAGE_STEPS.items()
        if owner == step and port in action_outputs(sibling)
    ]
    return siblings[-1] if siblings else stage


def stage_label(stage: str) -> str:
    """运行阶段 → 流程图节点名（默认走 spec，只有 ``detect_submit`` 单独一句）。

    页面里凡是"按 stage 给这个阶段起个中文名"（BPMN 节点名、进度/日志文案）
    都走本函数，**不要**自己 ``spec_by_key(stage)``——那会在
    ``detect_submit`` 上拿到 ``None`` 或与 ``detect`` 同名。
    """
    override = STAGE_LABELS.get(stage)
    if override:
        return override
    spec = spec_for_stage(stage)
    return spec.stage_name() if spec else stage


def spec_for_stage(stage: str) -> StepSpec | None:
    """运行阶段 → 它对应的 :class:`StepSpec`（界面查表统一走这里）。

    ⚠️ 这一层映射（:data:`STAGE_STEPS`）在：``detect_submit`` 要拿 ``detect``
    的声明（它是同一步骤的第二个动作），而 ``imposition`` 虽是**伪步骤**（不在
    ``STAGES`` 里）却也有自己的 spec。页面里凡是"按 stage 取这一步的界面元数据"
    （按钮文案、控制列宽度、预览控件名、右栏专属区块）都必须走本函数，
    **不要**自己 ``spec_by_key(stage)``——那会在 ``detect_submit`` 上拿到 None。
    """
    return spec_by_key(STAGE_STEPS.get(stage, stage))


def stage_artifacts(stage: str) -> tuple[str, ...]:
    """这一步消费哪些**产物类型**（端口名翻译过来）。"""
    return tuple(artifact_of(port) for port in stage_inputs(stage))
