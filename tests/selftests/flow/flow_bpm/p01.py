# -*- coding: utf-8 -*-
"""``flow_bpm`` 第 1 章：旧运行语义模型 + 文件往返。"""

from __future__ import annotations


def run(st) -> None:
    _check_default_matches_ports(st.ok)
    _check_roundtrip(st.ctx, st.ok)


# ---------------------------------------------------------------- 1. 旧运行语义模型
def _check_default_matches_ports(ok) -> None:
    """① ``FlowDefinition.default()`` 仍 = ports 静态表（**旧运行语义模型**）。

    ⚠️ 注意口径：**它不是"默认流程"**。默认流程是
    ``desktop/static/task_default.bpmn`` 那张图（见 ``p02._check_task_flow``）；
    ``FlowDefinition`` 是**端口级依赖边表**的模型，回答"这一步去谁那儿取产物"，
    现在只剩少数旧调用方在用。这一节守的是"那张表还没跟代码漂移"。
    """
    from desktop.steps import ports
    from desktop.steps.flow import CONDITION_IMPOSITION, FlowDefinition

    flow = FlowDefinition.default()

    for consumer, wiring in ports.SUPPLIERS.items():
        for port, supplier in wiring.items():
            got = flow.supplier_of(consumer, port)
            ok(f"默认流程 {consumer}.{port} ← {supplier}（与 ports 一致）",
               got == supplier, f"got {got!r}")

    # 条件边：拼版生效时 print 的上游换成 imposition（从 overrides 派生）。
    ok("默认流程带拼版条件边",
       flow.supplier_of("print", "pages", {"imposition": True}) == "imposition",
       str(flow.supplier_of("print", "pages", {"imposition": True})))
    ok("条件不命中走无条件边",
       flow.supplier_of("print", "pages", {"imposition": False})
       == "rembg")
    conditional = [e for e in flow.suppliers() if e.condition]
    ok("条件边只有一条、名为 imposition",
       len(conditional) == 1
       and conditional[0].condition == CONDITION_IMPOSITION
       and (conditional[0].consumer, conditional[0].port) == ("print", "pages"),
       str(conditional))

    # 节点顺序：覆盖全部运行阶段，且每个上游都排在自己的消费方前面。
    order = list(flow.stages)
    ok("节点覆盖全部运行阶段",
       set(order) == set(ports.STAGE_STEPS),
       f"{sorted(order)} vs {sorted(ports.STAGE_STEPS)}")
    for edge in flow.suppliers():
        if edge.supplier == ports.SUPPLY_TASK_SOURCE:
            continue
        ok(f"拓扑序：{edge.supplier} 在 {edge.consumer} 之前",
           order.index(edge.supplier) < order.index(edge.consumer),
           str(order))

    # 缺上游检查按本流程的连线判断（语义与 ports.missing_stages 一致）。
    ok("默认顺序没有缺上游",
       flow.missing_stages() == [], str(flow.missing_stages()))
    ok("打乱顺序会点名缺上游",
       flow.missing_stages(["extract", "rembg", "detect"]) != [])


# ---------------------------------------------------------------- 2. 往返
def _check_roundtrip(ctx, ok) -> None:
    """② save→load 无损；产物是合法 BPMN XML。"""
    from pathlib import Path
    from xml.etree import ElementTree as ET

    from desktop.steps.flow import FlowDefinition

    flow = FlowDefinition.default()
    path = Path(ctx.tmp) / "task_default.bpmn"
    flow.save(path)

    tree = ET.parse(path)  # 不是合法 XML 会在这里直接炸
    root = tree.getroot()
    process = [el for el in root if el.tag.endswith("}process")]
    ok("XML 里有 <process>", len(process) == 1)
    tasks = [el for el in process[0] if el.tag.endswith("}task")]
    ok("每个阶段一个 <task> 节点", len(tasks) == len(flow.stages))
    flows = [el for el in process[0] if el.tag.endswith("}sequenceFlow")]
    ok("每条边一个 <sequenceFlow>", len(flows) == len(flow.suppliers()))

    loaded = FlowDefinition.load(path)
    ok("往返后节点顺序一致", loaded.stages == flow.stages,
       f"{loaded.stages} vs {flow.stages}")
    ok("往返后连线一致", loaded.suppliers() == flow.suppliers(),
       f"{loaded.suppliers()} vs {flow.suppliers()}")
