# -*- coding: utf-8 -*-
"""读写 ``flow.bpmn``：解析、序列化、原子落盘、DI 段坐标读回。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from desktop.steps.bpmn_diagram.constants import (
    BPMNDI_NS,
    BPMN_NS,
    DC_NS,
    DI_NS,
    GUJI_NS,
    KIND_TASK,
    KNOWN_KINDS,
)
from desktop.steps.bpmn_diagram.elements import DiagramFlow, DiagramNode, DiagramNote
from desktop.steps.bpmn_diagram.helpers import (
    _is_note_id,
    _local,
    _q,
    _read_node_seq,
    stage_of_name,
)


class _SerializationMixin:
    """``FlowDiagram`` 的 BPMN 读写部分。"""

    # ------------------------------------------------------------ 解析
    @classmethod
    def load(cls, path: Path | str) -> "FlowDiagram":
        """从 ``.bpmn`` 文件读回整张图（节点/连线/坐标）。

        ⚠️ 与 :meth:`desktop.steps.flow.FlowDefinition.load` 的区别：那个只读
        **能跑的阶段**、认不出就抛错；这个读**图上画的一切**、认不出也保留。
        页面渲染用这个，运行语义用那个（或状态机）。
        """
        path = Path(path)
        if not path.is_file():
            raise ValueError(f"流程图文件不存在：{path}")
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            raise ValueError(f"流程图不是合法 XML：{path}（{exc}）") from exc

        process = next((el for el in root if _local(el.tag) == "process"), None)
        if process is None:
            raise ValueError(f"流程图里没有 <process>：{path}")

        nodes: list[DiagramNode] = []
        flows: list[DiagramFlow] = []
        notes: list[DiagramNote] = []
        note_links: dict[str, str] = {}
        raw_links: list[tuple[str, str]] = []
        for element in process:
            kind = _local(element.tag)
            if kind in KNOWN_KINDS:
                name = element.get("name", "") or ""
                # ⚠️ **只有 ``task`` 才映射运行阶段**：事件（尤其结束事件）常
                #    叫「生成PDF」这类名字，按名字查表会把它误认成 ``print``
                #    阶段——那会让状态机多跑一遍、顺序也全乱（实测踩过）。
                #    网关、事件都是**图形/控制**元素，不产生运行阶段。
                stage = None
                if kind == KIND_TASK:
                    stage = stage_of_name(name, element.get(_q(GUJI_NS, "stage")))
                nodes.append(
                    DiagramNode(
                        id=element.get("id", ""),
                        kind=kind,
                        name=name,
                        stage=stage,
                    )
                )
            elif kind == "sequenceFlow":
                flows.append(
                    DiagramFlow(
                        id=element.get("id", ""),
                        source=element.get("sourceRef", ""),
                        target=element.get("targetRef", ""),
                        label=element.get("name", "") or "",
                    )
                )
            elif kind == "textAnnotation":
                # ⚠️ 注释正文在**子元素** ``<bpmn:text>`` 里，不在属性上。
                body = element.find(_q(BPMN_NS, "text"))
                text = (body.text or "") if body is not None else ""
                notes.append(
                    DiagramNote(
                        id=element.get("id", ""),
                        text=text.strip(),
                    )
                )
            elif kind == "association":
                raw_links.append(
                    (element.get("sourceRef", ""), element.get("targetRef", ""))
                )

        # ⚠️ 挂接关系**延后**解析：``association`` 可能写在 ``textAnnotation``
        #    前面（XML 元素顺序没保证），当场判"哪头是注释"会漏掉一半。
        #    方向：sourceRef=被说明的节点，targetRef=注释（bpmn.io 的写法）；
        #    反过来写也认（别的工具可能反过来）。
        for source, target in raw_links:
            if not source or not target:
                continue
            if _is_note_id(target, notes):
                note_links[target] = source
            elif _is_note_id(source, notes):
                note_links[source] = target

        diagram = cls(
            nodes=tuple(nodes),
            flows=tuple(flows),
            notes=tuple(notes),
            note_links=note_links,
            process_id=process.get("id", "guji_task"),
            node_seq=_read_node_seq(process, nodes),
        )
        _read_di(root, diagram)
        has_node_box = any(n.id in diagram.boxes for n in diagram.nodes)
        return diagram if has_node_box else cls.auto_layout(diagram)

    # ------------------------------------------------------------ 序列化
    def to_xml(self) -> bytes:
        """写回 BPMN 2.0（含 DI 段），保证 bpmn.io 等工具能原样打开。

        ⚠️ 连线必须**双向引用**：``sourceRef``/``targetRef`` 属性给解析用，
        节点里的 ``<bpmn:incoming>``/``<bpmn:outgoing>`` 子元素给渲染器用
        —— 缺了后者，标准渲染器画不出箭头。
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
                "exporterVersion": "2.0",
            },
        )
        process = ET.SubElement(
            definitions,
            _q(BPMN_NS, "process"),
            {"id": self.process_id, "isExecutable": "false"},
        )
        # 节点号水位落盘（见 :attr:`node_seq`）：编辑端读回它才能保证新节点 id
        # **永不复用**。存量老图没这个属性时读端会从 ``Node_<n>`` 反推兜底。
        if self.node_seq > 0:
            process.set(_q(GUJI_NS, "node_seq"), str(int(self.node_seq)))
        for item in self.nodes:
            attrs = {"id": item.id, "name": item.name}
            # ⚠️ **阶段身份必须落盘**（``guji:stage``），不能只活在名字里。
            #    ``load`` 本来就会优先读它（见 :func:`stage_of_name`），但以前
            #    ``to_xml`` 从来不写——于是我们自己编辑器存的图，重读时也只能
            #    靠名字**猜**阶段：用户把「图片去底色」改成「AI 抠图」，存盘重进
            #    就接不回来了（"默认流程突然出现"的机制性原因）。
            #    外部工具（bpmn.io）可能丢弃它不认识的属性，丢了就退回名字匹配
            #    ＋降级告警——那条路照旧，不受影响。
            if item.kind == KIND_TASK and item.stage:
                attrs[_q(GUJI_NS, "stage")] = item.stage
            element = ET.SubElement(process, _q(BPMN_NS, item.kind), attrs)
            for flow in self.flows:
                if flow.target == item.id:
                    ET.SubElement(element, _q(BPMN_NS, "incoming")).text = flow.id
            for flow in self.flows:
                if flow.source == item.id:
                    ET.SubElement(element, _q(BPMN_NS, "outgoing")).text = flow.id
        for flow in self.flows:
            attrs = {
                "id": flow.id,
                "sourceRef": flow.source,
                "targetRef": flow.target,
            }
            if flow.label:
                attrs["name"] = flow.label
            ET.SubElement(process, _q(BPMN_NS, "sequenceFlow"), attrs)

        # ---- 文字注释 + 挂接（写回，别把用户写在图上的话丢了）----
        for note in self.notes:
            element = ET.SubElement(
                process, _q(BPMN_NS, "textAnnotation"), {"id": note.id}
            )
            ET.SubElement(element, _q(BPMN_NS, "text")).text = note.text
        for note in self.notes:
            host = self.note_links.get(note.id)
            if not host:
                continue
            ET.SubElement(
                process,
                _q(BPMN_NS, "association"),
                {
                    "id": f"Association_{note.id}",
                    "associationDirection": "None",
                    "sourceRef": host,
                    "targetRef": note.id,
                },
            )

        plane = ET.SubElement(
            ET.SubElement(
                definitions, _q(BPMNDI_NS, "BPMNDiagram"), {"id": "guji-diagram"}
            ),
            _q(BPMNDI_NS, "BPMNPlane"),
            {"id": "guji-plane", "bpmnElement": self.process_id},
        )
        for item in self.nodes:
            x, y, w, h = self.node_box(item.id)
            shape = ET.SubElement(
                plane,
                _q(BPMNDI_NS, "BPMNShape"),
                {
                    "id": f"{item.id}_di",
                    "bpmnElement": item.id,
                },
            )
            if item.is_gateway:
                shape.set("isMarkerVisible", "true")
            ET.SubElement(
                shape,
                _q(DC_NS, "Bounds"),
                {
                    "x": f"{x:.0f}",
                    "y": f"{y:.0f}",
                    "width": f"{w:.0f}",
                    "height": f"{h:.0f}",
                },
            )
        for note in self.notes:
            x, y, w, h = self.note_box(note.id)
            shape = ET.SubElement(
                plane,
                _q(BPMNDI_NS, "BPMNShape"),
                {
                    "id": f"{note.id}_di",
                    "bpmnElement": note.id,
                },
            )
            ET.SubElement(
                shape,
                _q(DC_NS, "Bounds"),
                {
                    "x": f"{x:.0f}",
                    "y": f"{y:.0f}",
                    "width": f"{w:.0f}",
                    "height": f"{h:.0f}",
                },
            )
        for flow in self.flows:
            points = self.waypoints.get(flow.id) or self.route(flow)
            edge = ET.SubElement(
                plane,
                _q(BPMNDI_NS, "BPMNEdge"),
                {
                    "id": f"{flow.id}_di",
                    "bpmnElement": flow.id,
                },
            )
            for px, py in points:
                ET.SubElement(
                    edge,
                    _q(DI_NS, "waypoint"),
                    {
                        "x": f"{px:.0f}",
                        "y": f"{py:.0f}",
                    },
                )
        return ET.tostring(definitions, encoding="utf-8", xml_declaration=True)

    def save(self, path: Path | str) -> Path:
        """原子落盘（写 ``.part`` 再 ``os.replace``，防半截文件）。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, part = tempfile.mkstemp(
            dir=str(path.parent), prefix=path.name + ".", suffix=".part"
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(self.to_xml())
            os.replace(part, path)
        except BaseException:
            try:
                os.unlink(part)
            except OSError:
                pass
            raise
        return path


def _read_di(root: ET.Element, diagram: "FlowDiagram") -> None:
    """把 DI 段的坐标读进 ``diagram.boxes`` / ``waypoints``（就地改）。"""
    for shape in root.iter(_q(BPMNDI_NS, "BPMNShape")):
        node_id = shape.get("bpmnElement", "")
        bounds = shape.find(_q(DC_NS, "Bounds"))
        if not node_id or bounds is None:
            continue
        try:
            diagram.boxes[node_id] = (
                float(bounds.get("x", 0)),
                float(bounds.get("y", 0)),
                float(bounds.get("width", 0)),
                float(bounds.get("height", 0)),
            )
        except (TypeError, ValueError):
            continue
    for edge in root.iter(_q(BPMNDI_NS, "BPMNEdge")):
        flow_id = edge.get("bpmnElement", "")
        points: list[tuple[float, float]] = []
        for point in edge.findall(_q(DI_NS, "waypoint")):
            try:
                points.append((float(point.get("x", 0)), float(point.get("y", 0))))
            except (TypeError, ValueError):
                continue
        if flow_id and len(points) >= 2:
            diagram.waypoints[flow_id] = points
