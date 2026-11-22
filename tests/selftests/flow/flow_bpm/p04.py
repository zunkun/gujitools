# -*- coding: utf-8 -*-
"""``flow_bpm`` 第 4 章：BPMN 2.0 结构 / DI 坐标 / 默认模板 / 节点命名。"""

from __future__ import annotations

from pathlib import Path


def run(st) -> None:
    _check_bpmn2_structure(st.ok)
    _check_di_layout(st.ok)
    _check_default_template(st.ok)
    _check_node_names_unique(st.ok)


def _check_bpmn2_structure(ok) -> None:
    """文件必须是**标准 BPMN 2.0**：命名空间 + 双向引用 + DI 图形段。

    用户 2026-10-05 明确要求「使用 bpmn2.0」。这一组钉死三件最容易被省掉
    的事：``xmlns:bpmndi``/``dc``/``di`` 三个命名空间、连线的
    ``<bpmn:incoming>``/``<bpmn:outgoing>`` 引用（缺了它标准渲染器画不出
    箭头）、以及 ``bpmndi:BPMNDiagram`` 图形段。
    """
    from xml.etree import ElementTree as ET

    from desktop.steps.flow import (
        BPMNDI_NS,
        BPMN_NS,
        DC_NS,
        DI_NS,
        FlowDefinition,
    )

    flow = FlowDefinition.default()
    root = ET.fromstring(flow.to_xml())

    ok("根元素是 bpmn:definitions", root.tag == f"{{{BPMN_NS}}}definitions",
       root.tag)
    ok("声明了 BPMN 2.0 MODEL 命名空间",
       root.tag.startswith(f"{{{BPMN_NS}}}"))
    ok("带 targetNamespace（标准渲染器识别流程所属）",
       bool(root.get("targetNamespace")), str(root.get("targetNamespace")))

    process = root.find(f"{{{BPMN_NS}}}process")
    ok("有 bpmn:process 段", process is not None)
    if process is None:
        return

    tasks = [el for el in process if el.tag == f"{{{BPMN_NS}}}task"]
    start = process.find(f"{{{BPMN_NS}}}startEvent")
    end = process.find(f"{{{BPMN_NS}}}endEvent")
    flows = [el for el in process if el.tag == f"{{{BPMN_NS}}}sequenceFlow"]
    ok("含 startEvent / task… / endEvent",
       start is not None and tasks and end is not None,
       f"start={start is not None} tasks={len(tasks)} end={end is not None}")
    ok("task 节点都带 guji:stage 显式标记",
       all(el.get(f"{{https://guji.tools/bpmn/2025}}stage") for el in tasks),
       "有个 task 缺 guji:stage")
    ok("每个 task 都有 name（界面文案来源）",
       all(el.get("name") for el in tasks))

    # ---- 双向引用：sourceRef/targetRef 属性 + incoming/outgoing 子元素 ----
    flow_ids = {el.get("id") for el in flows}
    ok("每条 sequenceFlow 都有 id/sourceRef/targetRef",
       all(el.get("id") and el.get("sourceRef") and el.get("targetRef")
           for el in flows))
    node_refs_ok = True
    for node in [start, *tasks, end]:
        for tag in ("incoming", "outgoing"):
            for ref in node.findall(f"{{{BPMN_NS}}}{tag}"):
                if (ref.text or "") not in flow_ids:
                    node_refs_ok = False
    ok("节点的 incoming/outgoing 都能对上 sequenceFlow 的 id", node_refs_ok)
    ok("startEvent 有 outgoing（入口边可被渲染器找到）",
       start is not None and start.find(f"{{{BPMN_NS}}}outgoing") is not None)
    # 「完成」事件是纯终点符号：没有阶段把产物喂给它，所以**不该**有 incoming。
    # 写成"没有 incoming 也要能过"这种恒真断言等于没断言。

    # ---- DI 图形段 ----
    diagram = root.find(f"{{{BPMNDI_NS}}}BPMNDiagram")
    ok("有 bpmndi:BPMNDiagram 图形段（标准存坐标的地方）",
       diagram is not None)
    if diagram is None:
        return
    plane = diagram.find(f"{{{BPMNDI_NS}}}BPMNPlane")
    ok("BPMNPlane 指向 process（图形与语义挂钩）",
       plane is not None and plane.get("bpmnElement") == "guji_task",
       str(plane.get("bpmnElement") if plane is not None else None))
    assert plane is not None
    shapes = plane.findall(f"{{{BPMNDI_NS}}}BPMNShape")
    edges = plane.findall(f"{{{BPMNDI_NS}}}BPMNEdge")
    ok("每个节点都有 BPMNShape + dc:Bounds",
       len(shapes) == len(tasks) + 2
       and all(s.find(f"{{{DC_NS}}}Bounds") is not None for s in shapes),
       f"shapes={len(shapes)} tasks={len(tasks)}")
    ok("每条连线都有 BPMNEdge + di:waypoint",
       len(edges) == len(flows)
       and all(e.findall(f"{{{DI_NS}}}waypoint") for e in edges),
       f"edges={len(edges)} flows={len(flows)}")
    ok("BPMNShape 的 bpmnElement 都能对上节点 id",
       {s.get("bpmnElement") for s in shapes}
       == {"start", "end", *flow.stages})


def _check_di_layout(ok) -> None:
    """拖出来的坐标要能经 ``dc:Bounds`` 往返，且拖拽**不改语义**。"""
    from desktop.steps.flow import FlowDefinition, FlowLayout

    flow = FlowDefinition.default()
    layout = FlowLayout.auto(flow)
    ok("自动排布：节点数 = 阶段数 + 起点终点",
       len(layout.boxes) == len(flow.stages) + 2, str(len(layout.boxes)))
    ok("自动排布：一行（所有 y 相同或仅事件居中差）",
       len({round(box[1], 1) for node, box in layout.boxes.items()
            if node not in ("start", "end")}) == 1)

    # 拖一个节点
    before = flow.stages
    edges_before = flow.suppliers()
    layout.move("detect", 400, 300)
    ok("拖动只改坐标：阶段顺序不变", flow.stages == before)
    ok("拖动只改坐标：连线不变", flow.suppliers() == edges_before)
    ok("move 改了 y", layout.node_box("detect")[1] == 300,
       str(layout.node_box("detect")))
    ok("move 不改尺寸", layout.node_box("detect")[2:4] == (148.0, 56.0),
       str(layout.node_box("detect")))

    # 落盘 → 读回
    import tempfile

    path = Path(tempfile.mkdtemp()) / "flow.bpmn"
    try:
        flow.save(path, layout)
        back = FlowDefinition.load_layout(path)
        ok("DI 坐标往返：节点数一致",
           len(back.boxes) == len(layout.boxes),
           f"{len(back.boxes)} vs {len(layout.boxes)}")
        ok("DI 坐标往返：detect 位置一致",
           abs(back.node_box("detect")[1] - 300) < 1
           and abs(back.node_box("detect")[0] - 400) < 1,
           str(back.node_box("detect")))
        # 语义往返不受坐标影响
        reloaded = FlowDefinition.load(path)
        ok("带 DI 的文件语义往返不变", reloaded.stages == flow.stages)
        ok("带 DI 的文件连线往返不变",
           sorted((e.supplier, e.consumer, e.port, e.condition)
                  for e in reloaded.suppliers())
           == sorted((e.supplier, e.consumer, e.port, e.condition)
                     for e in flow.suppliers()))
    finally:
        path.unlink(missing_ok=True)
        path.parent.rmdir()

    # 条件边永远绕行（与 GUI 画布同一口径）
    conditional = [e for e in flow.suppliers() if e.condition]
    ok("默认流程有条件边（拼版生效那条）", bool(conditional))
    if conditional:
        edge = conditional[0]
        pts = layout.bypass_points("imposition", edge.consumer)
        ok("条件边折点 ≥4 个（真的绕了一行，不是直连）",
           len(pts) >= 4, str(pts))
        ok("条件边绕行 y 在所有节点下方",
           all(pts[1][1] > layout.node_box(n)[1] + layout.node_box(n)[3]
               for n in layout.boxes),
           str(pts[1][1]))


def _check_default_template(ok) -> None:
    """默认流程模板必须存在、能解析、有可执行步骤。

    ⚠️ 口径：模板是**手工真源**，页面照着它渲染、状态机照着它排顺序，
    用户直接编辑它；自定义流程的初值就是这份模板（"从默认流程开始改"）。
    所以**不比内容与代码是否一致**——内容由人决定，没有"正确答案"。
    """
    import sys

    # 包形态：tests/selftests/flow/flow_bpm/p04.py → 仓库根是 parents[4]
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    from tools.gen_default_bpmn import TEMPLATE_NAME, template_path

    from desktop.steps.bpmn_diagram import FlowDiagram

    path = template_path()
    ok(f"流程模板 {TEMPLATE_NAME} 存在", path.is_file(), str(path))
    if path.is_file():
        diagram = FlowDiagram.load(path)
        ok(f"{TEMPLATE_NAME} 有节点", len(diagram.nodes) > 0,
           str(len(diagram.nodes)))
        ok(f"{TEMPLATE_NAME} 有可执行步骤（节点能认出运行阶段）",
           len(diagram.stage_order()) > 0, str(diagram.stage_order()))

    # 默认流程**必须是流程图，不是端口依赖表**。端口依赖表的指纹很明确：
    # 每条 `sequenceFlow` 上都带 `guji:port`（那是"取哪个产物端口"，
    # 与"先做哪一步"无关）。`extract --pages--> rembg/imposition/detect_submit`
    # 就是这么来的——画出来是从「提取图片」炸出去的一团。
    default_path_ = template_path()
    if default_path_.is_file():
        text = default_path_.read_text(encoding="utf-8")
        flows_with_port = [
            line.strip() for line in text.splitlines()
            if "sequenceFlow" in line and "guji:port" in line
        ]
        ok("默认流程的连线不带 guji:port（否则是端口依赖表冒充流程图）",
           not flows_with_port, str(flows_with_port[:2]))


def _check_node_names_unique(ok) -> None:
    """流程图上**不许出现两个同名节点**。

    背景（2026-10-05 实际踩到）：``detect_submit`` 与 ``detect`` 共用同一份
    :class:`StepSpec`，节点名直接取 ``spec.stage_name()`` 时两者都叫
    「检测文本框」——用户在图上根本分不清哪个是"检测"、哪个是"提交定稿"。
    修法是节点名一律走 ``ports.stage_label()``（那里对 ``detect_submit`` 有
    独立文案）。这条断言就是钉死那个修法，别让将来有人"简化"回spec 取名。
    """
    from desktop.steps import ports
    from desktop.steps.flow import FlowDefinition

    flow = FlowDefinition.default()
    names = [ports.stage_label(stage) for stage in flow.stages]
    ok("流程图上没有重名节点", len(set(names)) == len(names), str(names))
    ok("detect_submit 走独立文案（不与 detect 同名）",
       ports.stage_label("detect_submit") != ports.stage_label("detect"),
       f'{ports.stage_label("detect_submit")} vs {ports.stage_label("detect")}')
    # store 那张文案表也必须跟着同一口径，否则步骤条与流程图对不上
    from desktop.store.tasks import STAGE_LABELS

    ok("步骤条文案与流程图节点名同源",
       all(STAGE_LABELS.get(s) == ports.stage_label(s)
           for s in ("extract", "detect", "detect_submit", "rembg", "print")),
       str({s: STAGE_LABELS.get(s) for s in
            ("extract", "detect", "detect_submit", "rembg", "print")}))
