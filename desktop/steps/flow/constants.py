# -*- coding: utf-8 -*-
"""BPMN 命名空间、流程文件名与 XML 限定名小工具。"""

from __future__ import annotations

#: BPMN 2.0 标准命名空间（写文件用前缀 ``bpmn:``，读文件按命名空间解析）。
BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
#: BPMN 2.0 **图形交换**（DI）命名空间：节点框坐标与连线折点都在这一段里。
#: 这是 BPMN 2.0 存布局的标准位置——流程图编辑器拖出来的节点位置就该落在
#: ``bpmndi:BPMNShape/dc:Bounds`` 上，而不是我们自造一个旁挂的 JSON。
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
#: OMG DC（Drawing Canvas）命名空间：``dc:Bounds`` / ``dc:Point``。
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
#: OMG DI（Diagram Interchange）命名空间：``di:waypoint``（连线的折点）。
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
#: 本仓库的 BPMN 扩展命名空间（``guji:stage`` / ``guji:port`` / ``guji:condition``）。
GUJI_NS = "https://guji.tools/bpmn/2025"

#: BPMN 2.0 XSD 位置（写进 ``xsi:schemaLocation``，让校验器/编辑器知道按哪版校验）
BPMN_XSD = "http://www.omg.org/spec/BPMN/20100524/MODEL/BPMN20.xsd"

#: 任务目录里流程定义文件的固定名（``tasks/<任务号>/flow.bpmn``）。
FLOW_FILENAME = "flow.bpmn"

#: ``guji:condition`` 现有唯一的条件名：拼版是否生效（用户在详情页的
#: 「启用拼版」开关）。:meth:`TaskStore.stage_input` 按它传上下文。
CONDITION_IMPOSITION = "imposition"


def _q(ns: str, tag: str) -> str:
    """命名空间限定名（ElementTree 需要 ``{ns}tag`` 形状）。"""
    return f"{{{ns}}}{tag}"


def _local(tag: str) -> str:
    """剥掉 ``{ns}`` 前缀取局部名（读文件时不用关心命名空间具体串）。"""
    return tag.rsplit("}", 1)[-1]
