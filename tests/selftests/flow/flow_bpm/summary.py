# -*- coding: utf-8 -*-
"""**BPM 流程定义**（``desktop/steps/flow.py``）的自测。

守护九件事：

1. **默认流程不另写一份事实**（口径已于 2026-10-05 更新）——**模板文件
   ``desktop/static/task_default.bpmn`` 就是默认流程**，它是一张真正的
   流程图；页面照它渲染、状态机照它排顺序，**没有任何代码去"设计"它**。
   （旧口径是"从 ``ports.SUPPLIERS`` 派生默认流程"，那会把**端口级依赖**
   写成流程连线，画出来不是流程图——已废，见 ``docs/tasks/bpm.md``）；
2. **文件往返无损**——save→load 后节点顺序、连线、条件全部一致，且产物
   是合法 XML（``<process>`` + ``sequenceFlow``）；
3. **建任务即带流程定义**——``create_task`` 落下 ``flow.bpmn``，
   ``TaskStore.stage_input`` 按它解析，与 ``ports.resolve_input`` 逐端口
   相等（老任务没有 flow.bpmn 也走默认流程，行为不变）；
4. **换连线只换文件**——手写一份改过连线的 ``flow.bpmn``，``stage_input``
   立刻按新连线解析，代码一行不动；文件写坏则回落默认流程，任务不崩；
5. **BPM 驱动界面**——流程节点序列折叠成界面槽位（``stage_slots``），
   可选节点位置由 ``optional_after`` 给出，自定义流程换了顺序后寻址跟着变；
6. **标准 BPMN 2.0**（用户 2026-10-05 明确要求）——``bpmn:`` /
   ``bpmndi:`` / ``dc:`` / ``di:`` 四个命名空间、连线的
   ``<bpmn:incoming>``/``<bpmn:outgoing>`` 双向引用、``bpmndi:BPMNDiagram``
   图形段（``dc:Bounds`` 坐标 + ``di:waypoint`` 折点）；
7. **拖拽只改坐标**——``FlowLayout.move`` 不动语义，坐标经 DI 段往返一致，
   条件边永远绕行（不因同行就与主路径重合）；
8. **模板可用**——``task_default.bpmn``（默认流程，自定义初值也是它）
   存在、解析得动、有可执行步骤；连线**不带
   ``guji:port``**（带了就是端口依赖表冒充流程图）；
9. **流程图上没有重名节点**——节点名一律走 ``ports.stage_label()``，
   ``detect_submit`` 与 ``detect`` 不同名（曾两个都叫「检测文本框」），
   步骤条文案与流程图节点名同源。

不跑 YOLO、不起子进程、不建页面，全是纯逻辑断言。

拆分约定（``docs/dev/testing-standards.md`` §2.1）：本章按原文件的章节注释
切分；跨片夹具（``ctx`` 与 ``ok``）挂在 ``st`` 上，分片之间不靠全局变量传值。
"""

from __future__ import annotations

from types import SimpleNamespace

from . import p01, p02, p03, p04, p05

NAME = "flow_bpm"
DEPENDS: list[str] = []
TITLE = "BPM 流程定义与默认流程"

#: 按顺序执行的分片（改哪章只动哪个 ``pNN.py``）。
PARTS = (
    (p01, "1. 旧运行语义模型 / 文件往返"),
    (p02, "2. 任务流程 / 自定义流程 / 坏文件回落"),
    (p03, "3. 界面槽位投影"),
    (p04, "4. BPMN 2.0 结构 / DI / 默认模板 / 节点命名"),
    (p05, "5. 栈页号 / 未接入节点 / 列表胶囊"),
)


def run(ctx) -> None:
    from tests.selftests._context import ok

    st = SimpleNamespace(ctx=ctx, ok=ok)
    for part, _title in PARTS:
        part.run(st)


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
