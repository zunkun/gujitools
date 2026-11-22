# -*- coding: utf-8 -*-
"""``flow_ui`` 包内共享的常量与无状态助手。"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

def _click_at(widget, x: float, y: float) -> None:
    """在控件坐标 ``(x, y)`` 处合成一次左键点击。

    ⚠️ 自绘控件（``BpmnEditor``）走**合成事件直调**，不是 ``QTest.mouseClick``
    ——后者要控件挂到已显示的窗口上并按窗口坐标系派发，离屏下常点不中。
    """
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    pos = QPointF(float(x), float(y))
    widget.mousePressEvent(QMouseEvent(
        QEvent.Type.MouseButtonPress, pos, widget.mapToGlobal(pos.toPoint()),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    widget.mouseReleaseEvent(QMouseEvent(
        QEvent.Type.MouseButtonRelease, pos, widget.mapToGlobal(pos.toPoint()),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))


def _stroke(widget, points: list[tuple[float, float]]) -> None:
    """合成一次「按下 → 移动 … → 松开」的鼠标轨迹（拖连接点连线的手势）。"""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    def _event(type_, x, y, button, buttons):
        pos = QPointF(float(x), float(y))
        return QMouseEvent(type_, pos, widget.mapToGlobal(pos.toPoint()),
                           button, buttons, Qt.KeyboardModifier.NoModifier)

    first, last = points[0], points[-1]
    widget.mousePressEvent(_event(QEvent.Type.MouseButtonPress, *first,
                                  Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
    for x, y in points[1:-1]:
        widget.mouseMoveEvent(_event(QEvent.Type.MouseMove, x, y,
                                     Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))
    widget.mouseReleaseEvent(_event(QEvent.Type.MouseButtonRelease, *last,
                                    Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton))




_FLOW_4_SLOTS = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
 xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:guji="http://guji.local"
 id="D1" targetNamespace="http://bpmn.io/schema/bpmn">
 <bpmn:process id="P1" isExecutable="false">
  <bpmn:startEvent id="s"><bpmndi:OMNDIOSExtension/></bpmn:startEvent>
  <bpmn:task id="a" name="检测文本框" guji:stage="detect"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="b" name="图片去底色" guji:stage="rembg"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="c" name="图片拼版" guji:stage="imposition"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="d" name="PDF排版" guji:stage="print"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:sequenceFlow id="f1" sourceRef="s" targetRef="a"/>
  <bpmn:sequenceFlow id="f2" sourceRef="a" targetRef="b"/>
  <bpmn:sequenceFlow id="f3" sourceRef="b" targetRef="c"/>
  <bpmn:sequenceFlow id="f4" sourceRef="c" targetRef="d"/>
 </bpmn:process>
 <bpmndi:BPMNDiagram id="DD"><bpmndi:BPMNPlane id="PP" bpmnElement="P1"/></bpmndi:BPMNDiagram>
</bpmn:definitions>
"""

_FLOW_REMBG_FIRST = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
 xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:guji="http://guji.local"
 id="D1" targetNamespace="http://bpmn.io/schema/bpmn">
 <bpmn:process id="P1" isExecutable="false">
  <bpmn:startEvent id="s"><bpmndi:OMNDIOSExtension/></bpmn:startEvent>
  <bpmn:task id="a" name="图片去底色" guji:stage="rembg"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="b" name="PDF排版" guji:stage="print"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:sequenceFlow id="f1" sourceRef="s" targetRef="a"/>
  <bpmn:sequenceFlow id="f2" sourceRef="a" targetRef="b"/>
 </bpmn:process>
 <bpmndi:BPMNDiagram id="DD"><bpmndi:BPMNPlane id="PP" bpmnElement="P1"/></bpmndi:BPMNDiagram>
</bpmn:definitions>
"""

_FLOW_WITH_EXTRACT = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
 xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:guji="http://guji.local"
 id="D1" targetNamespace="http://bpmn.io/schema/bpmn">
 <bpmn:process id="P1" isExecutable="false">
  <bpmn:startEvent id="pdf" name="源PDF"><bpmndi:OMNDIOSExtension/></bpmn:startEvent>
  <bpmn:task id="ex" name="提取图片" guji:stage="extract"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="dt" name="检测文本框" guji:stage="detect"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="pr" name="PDF排版" guji:stage="print"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:sequenceFlow id="f1" sourceRef="pdf" targetRef="ex"/>
  <bpmn:sequenceFlow id="f2" sourceRef="ex" targetRef="dt"/>
  <bpmn:sequenceFlow id="f3" sourceRef="dt" targetRef="pr"/>
 </bpmn:process>
 <bpmndi:BPMNDiagram id="DD"><bpmndi:BPMNPlane id="PP" bpmnElement="P1"/></bpmndi:BPMNDiagram>
</bpmn:definitions>
"""

_FLOW_PRINT_WITH_END = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
 xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:guji="http://guji.local"
 id="D1" targetNamespace="http://bpmn.io/schema/bpmn">
 <bpmn:process id="P1" isExecutable="false">
  <bpmn:startEvent id="pdf" name="源PDF"><bpmndi:OMNDIOSExtension/></bpmn:startEvent>
  <bpmn:task id="ex" name="提取图片" guji:stage="extract"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="pr" name="PDF排版" guji:stage="print"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:endEvent id="end" name="生成PDF"><bpmndi:OMNDIOSExtension/></bpmn:endEvent>
  <bpmn:sequenceFlow id="f1" sourceRef="pdf" targetRef="ex"/>
  <bpmn:sequenceFlow id="f2" sourceRef="ex" targetRef="pr"/>
  <bpmn:sequenceFlow id="f3" sourceRef="pr" targetRef="end"/>
 </bpmn:process>
 <bpmndi:BPMNDiagram id="DD"><bpmndi:BPMNPlane id="PP" bpmnElement="P1"/></bpmndi:BPMNDiagram>
</bpmn:definitions>
"""

_FLOW_DETECT_FIRST = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
 xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:guji="http://guji.local"
 id="D1" targetNamespace="http://bpmn.io/schema/bpmn">
 <bpmn:process id="P1" isExecutable="false">
  <bpmn:startEvent id="s"><bpmndi:OMNDIOSExtension/></bpmn:startEvent>
  <bpmn:task id="a" name="检测文本框" guji:stage="detect"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="b" name="PDF排版" guji:stage="print"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:sequenceFlow id="f1" sourceRef="s" targetRef="a"/>
  <bpmn:sequenceFlow id="f2" sourceRef="a" targetRef="b"/>
 </bpmn:process>
 <bpmndi:BPMNDiagram id="DD"><bpmndi:BPMNPlane id="PP" bpmnElement="P1"/></bpmndi:BPMNDiagram>
</bpmn:definitions>
"""

def _viewer_entry_button(viewer, tooltip: str):
    """按 tooltip 在查看器里找那颗输入入口按钮（「＋」/「📁」；没有给 ``None``）。"""
    from qfluentwidgets import ToolButton

    for button in viewer.findChildren(ToolButton):
        if button.toolTip() == tooltip:
            return button
    return None

def _pump(app, rounds: int = 60) -> None:
    """空转事件循环等后台复制落地（自测里不能真sleep 等线程）。"""
    import time

    for _ in range(rounds):
        app.processEvents()
        time.sleep(0.05)

def _rebuild_keeps_highlight(page, store, task_id: str) -> bool:
    """只重建步骤条时，高亮仍停在**原来那一步**（用户 2026-10-06 报障根因）。

    ⚠️ 刻意**不**走 ``set_task``：那条链路末尾的 ``_select_stage``（"上次停留
    的步骤"）会把高亮按 key 重新找回，于是**掩盖**了重建本身的错位——上一条
    断言改前也绿就是这么来的。这里直接调 ``_rebuild_step_bar()``，把重建
    单独拎出来看。

    场景：停在「图片去底色」（默认流程格序 2），此时从磁盘删掉「提取图片」
    （格序 0）⇒ 去底色在新流程里是格序 1。改前重建拿**旧格序 2** 去查
    **新**槽位表（``flow_slots()`` 读的是磁盘那张新图），查到的是「图片拼版」
    ⇒ 高亮默默挪到别的步骤上。
    """
    from desktop.steps.bpmn_diagram import FlowDiagram

    # 复位成默认五格流程（前面几节已把图改成三格）
    from desktop.steps.scheduler import load_default_diagram

    store.save_task_diagram(task_id, load_default_diagram())
    page._rebuild_step_bar()
    target = page.bar_index_of_step("rembg")
    if target is None:
        return False
    page._select_stage(target)

    diagram = store.task_diagram(task_id)
    victim = next((n for n in diagram.nodes if n.stage == "extract"), None)
    if victim is None:
        return False
    trimmed = FlowDiagram(
        nodes=tuple(n for n in diagram.nodes if n.id != victim.id),
        flows=tuple(f for f in diagram.flows
                    if f.source != victim.id and f.target != victim.id),
    )
    store.save_task_diagram(task_id, trimmed)

    page._rebuild_step_bar()
    return page.step_at_index(page.step_bar._current) == "rembg"

def _open_detail_failure_shows_page(shell, page) -> bool:
    """``set_task`` 被拒（模拟步骤在跑）后，详情页仍被切到前台**且有提示**。

    ⚠️ 直接把 ``set_task`` 替换成返回 False 的替身：真实拒绝条件是
    "QProcess 在跑"，而离屏下起不了子进程，构造不出那个状态。

    ⚠️⚠️ 判据**必须包含"用户当时在流程页"**：只验"详情页在前台"是假绿——
    保存链路走完时详情页本来就已在前台，旧代码那句
    ``if busy: setCurrentWidget(page)`` 不 busy 时什么都不做，可详情页
    照样"在前台"（它从没被切走）⇒ 断言恒真。真正的差别是：**先切到流程页**
    （模拟用户此刻正在编辑器里），再触发重载失败——此时用户会不会被留在
    流程页上，且有没有一句解释。
    """
    # 先把用户放到流程页上（这才是"被留在流程页"的现场）
    flow_page = shell.flow_page()
    shell.pages.setCurrentWidget(flow_page)

    seen: list[tuple] = []
    original_toast = page._toast
    page._toast = lambda *a, **k: seen.append(a)
    original = page.set_task
    page.set_task = lambda _task_id: False
    try:
        shell.open_detail(page.task_id)
        # ⚠️ ``_toast(kind, title, content)``：标题是**第二个**参数。
        #    早先写成 item[0]（那是 kind="info"）⇒ any() 恒 False，断言假红，
        #    差点让我以为修复没生效（差点去改已经正确的生产代码）。
        return (
            shell.pages.currentWidget() is page
            and any(len(item) > 1 and str(item[1]) == "流程已保存"
                    for item in seen)
        )
    finally:
        page.set_task = original
        page._toast = original_toast

def _label_text_color(label) -> str:
    """取标签的**实际文字颜色**（``apply_to`` 按控件类型分了两条路）。

    ⚠️ qfluentwidgets 的标签（``FluentLabelBase`` 子类）走 ``setTextColor``，
    原生 ``QLabel`` 走 **palette**——两条都试一遍，否则拿到空字符串
    （项目记忆里记过这个坑：明明设了 palette，渲染出来仍是黑的）。
    """
    try:
        return str(label.textColor().name())
    except (AttributeError, TypeError):
        pass
    try:
        return str(label.palette().color(label.foregroundRole()).name())
    except (AttributeError, TypeError):
        return ""
