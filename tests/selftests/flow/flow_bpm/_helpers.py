# -*- coding: utf-8 -*-
"""``flow_bpm`` 包的模块级常量（无状态件）。"""

from __future__ import annotations

#: 自测用的自定义流程图：**整条「图片去底色」都去掉了**
#: （``start → extract → detect → print → end``）。
#:
#: ⚠️ 为什么专门做这么一张：要验"**声明的上游不在流程里时按图回退**"。
#: 去底色一旦不在流程里，`print.pages` 声明的上游 `rembg` 就跟着不在了，
#: 必须沿图往前找到 `extract`。若换成"图里有 rembg"的版本，`rembg` 是**活的**，
#: 走的是声明表，验不到回退那条路。
#:
#: 同时它印证**新契约**：流程连线表达"先做哪一步"，**不表达"去谁那儿取文件"**
#: （两者混在一起正是默认模板曾经长成一团乱线的原因，见 ``docs/tasks/bpm.md``）。
_CUSTOM_WIRING = """\
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:guji="https://guji.tools/bpmn/2025">
  <bpmn:process id="guji_custom" isExecutable="false">
    <bpmn:startEvent id="start" name="源 PDF"/>
    <bpmn:task id="extract" name="提取图片"/>
    <bpmn:task id="detect" name="检测文本框"/>
    <bpmn:task id="print" name="生成 PDF"/>
    <bpmn:endEvent id="end" name="完成"/>
    <bpmn:sequenceFlow id="f0" sourceRef="start" targetRef="extract"/>
    <bpmn:sequenceFlow id="f1" sourceRef="extract" targetRef="detect"/>
    <bpmn:sequenceFlow id="f2" sourceRef="detect" targetRef="print"/>
    <bpmn:sequenceFlow id="f3" sourceRef="print" targetRef="end"/>
  </bpmn:process>
</bpmn:definitions>
"""

#: 自定义流程：把 detect 摘掉、拼版排到**最前**（异位），并让 print 改吃
#: extract。真实场景未必这么连，只为证明"步骤条顺序与寻址都跟着流程走"。
_CUSTOM_ORDER_WIRING = """\
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:guji="https://guji.tools/bpmn/2025">
  <bpmn:process id="guji_reorder" isExecutable="false">
    <bpmn:startEvent id="start" name="源 PDF"/>
    <bpmn:task id="extract" name="提取PDF图片" guji:stage="extract"/>
    <bpmn:task id="imposition" name="图片拼版" guji:stage="imposition"/>
    <bpmn:task id="rembg" name="图片去底色" guji:stage="rembg"/>
    <bpmn:task id="print" name="PDF排版" guji:stage="print"/>
    <bpmn:endEvent id="end" name="完成"/>
    <bpmn:sequenceFlow id="f0" sourceRef="start" targetRef="extract" guji:port="pdf"/>
    <bpmn:sequenceFlow id="f1" sourceRef="extract" targetRef="imposition" guji:port="pages"/>
    <bpmn:sequenceFlow id="f2" sourceRef="imposition" targetRef="rembg" guji:port="pages"/>
    <bpmn:sequenceFlow id="f3" sourceRef="rembg" targetRef="print" guji:port="pages"/>
  </bpmn:process>
</bpmn:definitions>
"""
