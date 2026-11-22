# -*- coding: utf-8 -*-
"""流程定义的 BPMN 序列化：写 ``flow.bpmn`` / 从文件读回坐标。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from desktop.steps import ports
from desktop.steps.flow.constants import (
    BPMNDI_NS,
    BPMN_NS,
    DC_NS,
    DI_NS,
    GUJI_NS,
    _local,
    _q,
)
from desktop.steps.flow.layout import FlowLayout
from desktop.steps.flow.model import FlowEdge


class FlowSerializationPart:
    """:class:`FlowDefinition` 的序列化部分（BPMN 2.0 读写）。

    只声明本部分要用到的字段，字段本身由 :class:`FlowDefinition` 定义。
    """

    stages: tuple[str, ...]
    edges: dict[tuple[str, str], list[FlowEdge]]

    def suppliers(self) -> list[FlowEdge]:
        """全部边（扁平化，节点编辑器/自测遍历用）。"""
        return [edge for group in self.edges.values() for edge in group]

    # ------------------------------------------------------------ 序列化
    def to_xml(self, layout: "FlowLayout | None" = None) -> bytes:
        """序列化成 BPMN 2.0 文件（``flow.bpmn`` 的内容）。

        结构分两段，**都是 BPMN 2.0 标准件**，不是自定义格式：

        - ``bpmn:process``——语义段：``startEvent`` / ``task`` / ``endEvent``
          与 ``sequenceFlow``。连线带**双向引用**：``sourceRef``/``targetRef``
          属性给解析用，``<bpmn:incoming>``/``<bpmn:outgoing>`` 子元素给
          图形工具用（缺了它们，标准 BPMN 渲染器画不出箭头）；
        - ``bpmndi:BPMNDiagram``——**图形段（DI）**：每个节点一个
          ``bpmndi:BPMNShape`` 带 ``dc:Bounds``（x/y/width/height），
          每条连线一个 ``bpmndi:BPMNEdge`` 带若干 ``di:waypoint``。

        ⚠️ 节点坐标**存在 DI 段的 ``dc:Bounds`` 里**，这正是流程编辑器
        （含本项目 M4 的拖拽画布）读写布局的标准位置。``layout`` 缺省时给
        一份默认横向排布，保证文件在任何工具里打开都有完整图形。
        """
        ET.register_namespace("bpmn", BPMN_NS)
        ET.register_namespace("bpmndi", BPMNDI_NS)
        ET.register_namespace("dc", DC_NS)
        ET.register_namespace("di", DI_NS)
        ET.register_namespace("guji", GUJI_NS)
        definitions = ET.Element(
            _q(BPMN_NS, "definitions"),
            {
                "id": "guji-definitions",
                "targetNamespace": GUJI_NS,
                "exporter": "guji",
                "exporterVersion": "1.0",
            },
        )
        process = ET.SubElement(
            definitions,
            _q(BPMN_NS, "process"),
            {"id": "guji_task", "isExecutable": "false"},
        )

        edges = self.suppliers()
        # 连线 id 要**先**定下来：节点的 <incoming>/<outgoing> 得引用它们
        flow_ids = {id(edge): f"flow{index}" for index, edge in enumerate(edges)}
        incoming: dict[str, list[str]] = {}
        outgoing: dict[str, list[str]] = {}
        for edge in edges:
            source = (
                "start"
                if edge.supplier == ports.SUPPLY_TASK_SOURCE
                else edge.supplier
            )
            outgoing.setdefault(source, []).append(flow_ids[id(edge)])
            incoming.setdefault(edge.consumer, []).append(flow_ids[id(edge)])

        def _refs(parent, tag: str, values: list[str]) -> None:
            for value in values:
                ET.SubElement(parent, _q(BPMN_NS, tag)).text = value

        start = ET.SubElement(
            process, _q(BPMN_NS, "startEvent"),
            {"id": "start", "name": "源 PDF"},
        )
        _refs(start, "outgoing", outgoing.get("start", []))

        nodes: list[tuple[str, str]] = [("start", "源 PDF")]
        for stage in self.stages:
            # ⚠️ 走 ports.stage_label 而不是 spec.stage_name()：后者对
            #    ``detect_submit`` 会回落到 ``detect`` 的名字，流程图上就出现
            #    **两个「检测文本框」**节点，用户分不清哪个是提交定稿。
            name = ports.stage_label(stage)
            task = ET.SubElement(
                process, _q(BPMN_NS, "task"),
                {"id": stage, "name": name, _q(GUJI_NS, "stage"): stage},
            )
            _refs(task, "incoming", incoming.get(stage, []))
            _refs(task, "outgoing", outgoing.get(stage, []))
            nodes.append((stage, name))

        ET.SubElement(
            process, _q(BPMN_NS, "endEvent"), {"id": "end", "name": "完成"}
        )
        # ⚠️ end 事件也要进 DI 段：漏了它，BPMN 工具打开时流程图**没有终点**
        # （语义段有、图形段没有——这类"两段不一致"最难查，标准渲染器只读 DI）。
        nodes.append(("end", "完成"))

        for edge in edges:
            source = (
                "start"
                if edge.supplier == ports.SUPPLY_TASK_SOURCE
                else edge.supplier
            )
            attrs = {
                "id": flow_ids[id(edge)],
                "sourceRef": source,
                "targetRef": edge.consumer,
                _q(GUJI_NS, "port"): edge.port,
            }
            if edge.condition:
                attrs[_q(GUJI_NS, "condition")] = edge.condition
            ET.SubElement(process, _q(BPMN_NS, "sequenceFlow"), attrs)

        if layout is None:
            layout = FlowLayout.auto(self)
        self._append_di(definitions, nodes, edges, flow_ids, layout)

        ET.indent(definitions, space="  ")
        return ET.tostring(definitions, encoding="utf-8", xml_declaration=True)

    def _append_di(self, definitions, nodes, edges, flow_ids,
                   layout: "FlowLayout") -> None:
        """补上 ``bpmndi:BPMNDiagram`` 图形段（坐标 + 连线折点）。"""
        diagram = ET.SubElement(
            definitions, _q(BPMNDI_NS, "BPMNDiagram"), {"id": "guji-diagram"}
        )
        plane = ET.SubElement(
            diagram, _q(BPMNDI_NS, "BPMNPlane"),
            {"id": "guji-plane", "bpmnElement": "guji_task"},
        )
        for node_id, _name in nodes:
            box = layout.node_box(node_id)
            shape = ET.SubElement(
                plane, _q(BPMNDI_NS, "BPMNShape"),
                {
                    "id": f"{node_id}_di",
                    "bpmnElement": node_id,
                    # 事件是圆、任务是圆角矩形：isMarkerVisible 之外的形状由
                    # 渲染器按元素类型自己定，这里只给几何。
                    "isHorizontal": "true",
                },
            )
            ET.SubElement(
                shape, _q(DC_NS, "Bounds"),
                {
                    "x": f"{box[0]:.0f}",
                    "y": f"{box[1]:.0f}",
                    "width": f"{box[2]:.0f}",
                    "height": f"{box[3]:.0f}",
                },
            )
        # 每条边在"进其消费方的所有边"里的序号（落点纵向错开，见 edge_points）
        grouped: dict[str, list] = {}
        for edge in edges:
            grouped.setdefault(edge.consumer, []).append(edge)
        landing_index: dict[int, int] = {}
        landing_total: dict[str, int] = {}
        for consumer, group in grouped.items():
            for order, edge in enumerate(group):
                landing_index[id(edge)] = order
            landing_total[consumer] = len(group)
        for edge in edges:
            source = (
                "start"
                if edge.supplier == ports.SUPPLY_TASK_SOURCE
                else edge.supplier
            )
            order = landing_index[id(edge)]
            total = landing_total[edge.consumer]
            # ⚠️ 条件边**永远绕行**（与 GUI 画布 ``_bypass_points`` 同一口径）：
            # 它是"命中才走"的备选路径，画成与主路径重合的直线就等于没画。
            if edge.condition:
                points = layout.bypass_points(source, edge.consumer, order, total)
            else:
                points = layout.edge_points(source, edge.consumer, order, total)
            edge_el = ET.SubElement(
                plane, _q(BPMNDI_NS, "BPMNEdge"),
                {"id": f"{flow_ids[id(edge)]}_di", "bpmnElement": flow_ids[id(edge)]},
            )
            for x, y in points:
                ET.SubElement(
                    edge_el, _q(DI_NS, "waypoint"),
                    {"x": f"{x:.0f}", "y": f"{y:.0f}"},
                )

    def save(self, path: Path | str, layout: "FlowLayout | None" = None) -> Path:
        """原子落盘（写 ``.part`` 再 ``os.replace``，防半截文件）。

        ``layout`` 缺省给默认排布——文件在任何 BPMN 工具里打开都有完整图形。
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, part_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=path.name + ".", suffix=".part"
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(self.to_xml(layout))
            os.replace(part_name, path)
        except BaseException:
            try:
                os.unlink(part_name)
            except OSError:
                pass
            raise
        return path

    @staticmethod
    def load_layout(path: Path | str) -> FlowLayout:
        """从 ``flow.bpmn`` 的 **DI 段**读回节点坐标（拖拽结果）。

        读不到 / 文件坏 / 缺 DI 段时**回默认排布**并按实际节点集合补全——
        布局是"锦上添花"，缺了不该让流程定义整个打不开（:meth:`load` 才负责
        语义校验）。
        """
        path = Path(path)
        if not path.is_file():
            return FlowLayout()
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            return FlowLayout()
        layout = FlowLayout()
        for shape in root.iter(_q(BPMNDI_NS, "BPMNShape")):
            node_id = shape.get("bpmnElement", "")
            bounds = shape.find(_q(DC_NS, "Bounds"))
            if not node_id or bounds is None:
                continue
            try:
                layout.boxes[node_id] = (
                    float(bounds.get("x", 0)),
                    float(bounds.get("y", 0)),
                    float(bounds.get("width", 0)),
                    float(bounds.get("height", 0)),
                )
            except (TypeError, ValueError):
                continue
        return layout
