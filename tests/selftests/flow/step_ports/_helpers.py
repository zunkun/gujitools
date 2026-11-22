# -*- coding: utf-8 -*-
"""``step_ports`` 包的模块级常量与无状态助手。"""

from __future__ import annotations

from pathlib import Path

#: 模块页源码目录（相对仓库根）
_MODULES_DIR = Path("desktop") / "modules"

#: **普通步骤页**（应当继承 ``StepModulePage`` 的那批）。
#: ⚠️ 不写死数量：判断依据是"是不是一个带 command 的普通步骤"。拼版页**有意**
#: 不在其中（它的源是一批图、执行是纯函数导出，外壳对不上），见第 5 节。
_REGULAR_KEYS = ("extract", "detect", "rembg", "print")


def _spec_for(stage: str):
    """取某一步的元数据；查不到直接断（查不到就是元数据表漏了，不是"没关系"）。"""
    from desktop.steps import ports

    spec = ports.spec_for_stage(stage)
    assert spec is not None, f"步骤表里没有「{stage}」这一项"
    return spec


#: 一条**不含 extract** 的自定义流程（detect 打头）——用户 2026-10-06 的报障现场。
_FLOW_WITHOUT_EXTRACT = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
 xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
 xmlns:guji="http://guji.local"
 id="Defs_1" targetNamespace="http://bpmn.io/schema/bpmn">
 <bpmn:process id="Process_1" isExecutable="false">
  <bpmn:startEvent id="start"><bpmndi:OMNDIOSExtension/></bpmn:startEvent>
  <bpmn:task id="t_detect" name="检测文本框" guji:stage="detect"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="t_rembg" name="图片去底色" guji:stage="rembg"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="t_print" name="生成PDF" guji:stage="print"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="t_detect"/>
  <bpmn:sequenceFlow id="f2" sourceRef="t_detect" targetRef="t_rembg"/>
  <bpmn:sequenceFlow id="f3" sourceRef="t_rembg" targetRef="t_print"/>
 </bpmn:process>
 <bpmndi:BPMNDiagram id="D1"><bpmndi:BPMNPlane id="P1" bpmnElement="Process_1"/></bpmndi:BPMNDiagram>
</bpmn:definitions>
"""


#: 一条**去底色打头**的自定义流程（用户 2026-10-06 的报障现场）：没有
#: 「检测文本框」，所以 ``rembg`` 的 ``boxes`` 在这张图上**没有供给方**。
_FLOW_REMBG_FIRST = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
  xmlns:guji="http://guji.local"
  id="Defs_1" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_1" isExecutable="false">
   <bpmn:startEvent id="start"><bpmndi:OMNDIOSExtension/></bpmn:startEvent>
   <bpmn:task id="t_rembg" name="图片去底色" guji:stage="rembg"><bpmndi:OMNDIOSExtension/></bpmn:task>
   <bpmn:task id="t_print" name="生成PDF" guji:stage="print"><bpmndi:OMNDIOSExtension/></bpmn:task>
   <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="t_rembg"/>
   <bpmn:sequenceFlow id="f2" sourceRef="t_rembg" targetRef="t_print"/>
  </bpmn:process>
  <bpmndi:BPMNDiagram id="D1"><bpmndi:BPMNPlane id="P1" bpmnElement="Process_1"/></bpmndi:BPMNDiagram>
</bpmn:definitions>
"""
