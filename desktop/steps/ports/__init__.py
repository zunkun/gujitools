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
- **运行阶段**多一个（2026-10-22 起）：
  ``detect_submit``——第二步「检测文本框」右上「提交本次任务」按钮触发的
  **同一步骤的第二个动作**（先检测出框到 ``boxes.json``，提交时才逐框裁图
  把页面图裁到 ``stages/detect``）。端口系统必须认得它，否则这一步的产物
  没有落点、下一步也没有输入。

    ====================  ==========================================
    运行阶段               步骤 key / 端口
    ====================  ==========================================
    ``extract``            ``extract``：in=pdf / out=pages
    ``detect``              ``detect``：in=pages / out=boxes（只检测，出框）
    ``detect_submit``       ``detect``：in=pages / out=pages（逐框裁图）
    ``rembg``               ``rembg``：in=pages / out=pages（整图去底色成品）
    ``print``              ``print``：in=pages / out=pdf
    ====================  ==========================================

⚠️ 本模块**纯逻辑、不 import 任何 Qt**，因此可以被自测、CLI 与将来的
BPM 编排引擎安全导入（与 :mod:`desktop.steps.spec` 同一约束）。

2026-11-22 起按职责拆成子包（原文件 898 行）：常量表在
:mod:`desktop.steps.ports.constants`、端口声明在 ``declaration``、落点规则在
``locations``、连线与就绪判定在 ``connections``、图上的节点语义在 ``nodes``。
本 ``__init__`` 只做重导出，既有 ``from desktop.steps.ports import X`` 全部不变；
子模块之间不要反过来导入本包（会形成循环）。
"""

from desktop.steps.ports.connections import (
    describe,
    flow_entry_input_kind,
    flow_entry_node,
    flow_entry_stage,
    flow_needs_entry_images,
    input_ready,
    is_entry_stage,
    missing_stages,
    node_blocking_inputs,
    ports_stage_order,
    print_input_overrides,
    print_pages_supplier,
    resolve_input,
    resolve_input_with_entry,
    stage_blocking_inputs,
    supplier_of,
)
from desktop.steps.ports.constants import (
    ARTIFACT_BOXES,
    ARTIFACT_INPUT,
    ARTIFACT_LABELS,
    ARTIFACT_PAGES,
    ARTIFACT_PDF,
    GATEWAY_GUARD_STAGE,
    IMPOSITION_ANCHOR,
    OPTIONAL_INPUT_PORTS,
    PORT_ARTIFACTS,
    PORT_LABELS,
    SOURCE_PDF_NODE_NAMES,
    SOURCE_PDF_STAGE,
    STAGE_LABELS,
    STAGE_LOCATIONS,
    STAGE_STEPS,
    SUPPLIERS,
    SUPPLY_TASK_INPUT,
    SUPPLY_TASK_SOURCE,
    TASK_INPUT_LOCATION,
)
from desktop.steps.ports.declaration import (
    action_outputs,
    artifact_of,
    fold_forward,
    spec_for_stage,
    stage_artifacts,
    stage_inputs,
    stage_label,
    stage_outputs,
)
from desktop.steps.ports.locations import (
    artifact_path,
    copy_location,
    location_of,
    node_location,
    node_scope_from_output_dir,
    rembg_methods_path,
    sanitize_node_id,
    scoped_name,
    suffix_last_segment,
    task_input_dir,
)
from desktop.steps.ports.nodes import (
    flow_crops_pages,
    flow_needs_source_pdf,
    is_source_pdf_node,
    orphaned_end_event_ids,
    orphaned_gateway_ids,
    paired_node_for_stage,
    source_pdf_node_ids,
)

__all__ = [
    "ARTIFACT_BOXES",
    "ARTIFACT_LABELS",
    "ARTIFACT_PAGES",
    "ARTIFACT_PDF",
    "GATEWAY_GUARD_STAGE",
    "PORT_ARTIFACTS",
    "PORT_LABELS",
    "STAGE_LABELS",
    "STAGE_LOCATIONS",
    "STAGE_STEPS",
    "SUPPLIERS",
    "SUPPLY_TASK_INPUT",
    "SUPPLY_TASK_SOURCE",
    "TASK_INPUT_LOCATION",
    "action_outputs",
    "artifact_of",
    "artifact_path",
    "copy_location",
    "describe",
    "flow_crops_pages",
    "flow_entry_input_kind",
    "fold_forward",
    "flow_entry_node",
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
    "node_blocking_inputs",
    "node_location",
    "node_scope_from_output_dir",
    "OPTIONAL_INPUT_PORTS",
    "orphaned_end_event_ids",
    "orphaned_gateway_ids",
    "print_input_overrides",
    "print_pages_supplier",
    "resolve_input",
    "resolve_input_with_entry",
    "sanitize_node_id",
    "scoped_name",
    "suffix_last_segment",
    "spec_for_stage",
    "stage_artifacts",
    "stage_blocking_inputs",
    "stage_inputs",
    "stage_label",
    "stage_outputs",
    "supplier_of",
    "task_input_dir",
]
