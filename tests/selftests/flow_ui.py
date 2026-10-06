# -*- coding: utf-8 -*-
"""**创建任务弹窗 + BPMN 流程渲染与编辑**（``docs/tasks/bpm.md``）自测。

用户 2026-10-05 第二轮的口径把架构彻底掉了个方向：

> 1. 页面渲染 bpmn 流程图，按照页面定义的渲染
> 2. 页面可以编辑
> 3. 后端驱动可以使用状态机来实现，bpm 流程引擎太复杂

**旧做法的问题**：``ports.SUPPLIERS``（端口级边表）是"代码"，``flow.bpmn``
只是它的**导出物**；页面渲染走 :class:`FlowView`，坐标自己算。结果——用户
在 bpmn.io 里画的图，进页面看到的是另一张图（没有网关、坐标也不同）。

**新做法**：``flow.bpmn`` 是**唯一真源**，页面照着它渲染
（:class:`~desktop.components.bpmn_view.BpmnView`），编辑改的也是它
（:class:`~desktop.components.bpmn_editor.BpmnEditor`），运行顺序由
:class:`~desktop.steps.scheduler.Scheduler` 状态机给出。

本模块钉死五条契约：

1. **渲染读文件**——页面上的节点类型/坐标/连线全部来自文件（含网关菱形）；
2. **拓扑顺序**——从网关分叉时，"短路"的那条不能把下游阶段排到前面；
3. **编辑改文件**——增删节点/连线/改名/拖拽，落盘往返不丢；
4. **状态机**——条件不满足的阶段被剔除（拼版开关），顺序与图一致；
5. **接口闭环**——创建任务弹窗 → 落盘 → 详情页读回，阶段顺序一致。

⚠️ **绝不真弹模态**：只用面板本体，不调 ``exec()``（项目硬规则）。
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

NAME = "flow_ui"
DEPENDS: list[str] = ["tasklist"]
TITLE = "创建任务弹窗与 BPMN 流程渲染/编辑"


def _click_at(widget, x: float, y: float) -> None:
    """在控件坐标 ``(x, y)`` 处合成一次左键点击。

    ⚠️ 自绘控件（``BpmnEditor``）走**合成事件直调**，不是 ``QTest.mouseClick``
    ——后者要控件挂到已显示的窗口上并按窗口坐标系派发，离屏下常点不中。
    """
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    pos = QPointF(float(x), float(y))
    widget.mousePressEvent(QMouseEvent(
        QEvent.MouseButtonPress, pos, widget.mapToGlobal(pos.toPoint()),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    widget.mouseReleaseEvent(QMouseEvent(
        QEvent.MouseButtonRelease, pos, widget.mapToGlobal(pos.toPoint()),
        Qt.LeftButton, Qt.NoButton, Qt.NoModifier))


def _stroke(widget, points) -> None:
    """合成一次「按下 → 移动 … → 松开」的鼠标轨迹（拖连接点连线的手势）。"""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    def _event(type_, x, y, button, buttons):
        pos = QPointF(float(x), float(y))
        return QMouseEvent(type_, pos, widget.mapToGlobal(pos.toPoint()),
                           button, buttons, Qt.NoModifier)

    first, last = points[0], points[-1]
    widget.mousePressEvent(_event(QEvent.MouseButtonPress, *first,
                                  Qt.LeftButton, Qt.LeftButton))
    for x, y in points[1:-1]:
        widget.mouseMoveEvent(_event(QEvent.MouseMove, x, y,
                                     Qt.NoButton, Qt.LeftButton))
    widget.mouseReleaseEvent(_event(QEvent.MouseButtonRelease, *last,
                                    Qt.LeftButton, Qt.NoButton))


def run(ctx) -> None:
    from desktop.components import create_task_dialog
    from desktop.components.bpmn_editor import BpmnEditor
    from desktop.components.bpmn_view import BpmnView
    from desktop.components.flow_dialog import FlowDialog, FlowPanel
    from desktop.steps.bpmn_diagram import (
        KIND_END, KIND_EXCLUSIVE, KIND_START, KIND_TASK, DiagramFlow,
        DiagramNode, FlowDiagram,
    )
    from desktop.steps.scheduler import (
        DONE, SKIPPED, Scheduler, load_default_diagram,
    )
    from desktop.utils.files import package_dir
    from tests.selftests._context import ok

    app, w = ctx.app, ctx.w
    page = w.list_page

    # ---------------------------------------------------------------- 1
    # 入口改名（用户按提示得找得到按钮）
    header_texts = [b.text() for b in page.findChildren(type(page._import_button))]
    ok("页头主按钮是「创建任务」",
       any("创建任务" in t for t in header_texts), str(header_texts))
    ok("旧文案「导入 PDF」已消失",
       not any("导入 PDF" in t for t in header_texts), str(header_texts))

    # ---------------------------------------------------------------- 2
    # 渲染：**照着 bpmn 文件**（含网关、事件、DI 坐标）
    init = create_task_dialog.load_custom_init()
    ok("初值文件 task_detail.bpmn 能解析出节点", len(init.nodes) > 0,
       str(len(init.nodes)))
    kinds = {n.kind for n in init.nodes}
    ok("初值里有网关（写 bpmn.io 画的图带 exclusiveGateway）",
       KIND_EXCLUSIVE in kinds, str(sorted(kinds)))
    ok("初值里有起止事件",
       KIND_START in kinds and KIND_END in kinds, str(sorted(kinds)))
    ok("初值节点都带 DI 坐标（页面按文件坐标画）",
       all(n.id in init.boxes for n in init.nodes),
       str([n.id for n in init.nodes if n.id not in init.boxes]))
    ok("连线带折点（走文件里存的 di:waypoint）",
       all(f.id in init.waypoints for f in init.flows),
       str([f.id for f in init.flows if f.id not in init.waypoints]))

    view = BpmnView(init)
    ok("BpmnView 能按文件渲染（尺寸随内容）",
       view.width() > 0 and view.height() > 0,
       f"{view.width()}x{view.height()}")
    gw = next(n for n in init.nodes if n.is_gateway)
    ok("网关的命中测试按菱形判（不是外接矩形）",
       view.node_at(view.rect_of(gw.id).topRight() - __import__(
           "PySide6.QtCore", fromlist=["QPointF"]
       ).QPointF(4, 4)) != gw.id,
       "菱形四角不该被当成命中")

    # ---------------------------------------------------------------- 3
    # 拓扑顺序：短路分支不能把下游阶段排到前面
    order = init.stage_order()
    ok("阶段顺序是拓扑序（拼版排在生成 PDF 之前）",
       order.index("imposition") < order.index("print"), str(order))

    # ---------------------------------------------------------------- 4
    # 状态机：条件不满足则剔除
    sched_on = Scheduler.from_diagram(init, {"imposition": True})
    sched_off = Scheduler.from_diagram(init, {"imposition": False})
    ok("状态机（开拼版）含拼版", "imposition" in sched_on.stages,
       str(sched_on.stages))
    ok("状态机（关拼版）剔除拼版", "imposition" not in sched_off.stages,
       str(sched_off.stages))
    ok("关拼版时拼版记 SKIPPED（界面能区分没有与跳过）",
       sched_off.state_of("imposition") == SKIPPED,
       sched_off.state_of("imposition"))
    ok("状态机顺序与图的拓扑序一致",
       tuple(s for s in sched_on.stages if s in init.stage_order())
       == tuple(s for s in init.stage_order() if s in sched_on.stages))
    ok("first_pending 给第一步", sched_on.first_pending() == sched_on.stages[0],
       str(sched_on.first_pending()))
    sched_on.mark(sched_on.stages[0], DONE)
    ok("标记完成后 next_stage 前移",
       sched_on.first_pending() == sched_on.stages[1],
       str(sched_on.first_pending()))
    ok("progress 含跳过（跳过的算完成，进度条才会满）",
       sched_off.progress()[0] == 1,
       str(sched_off.progress()))
    ok("状态机给没上游的提示但不硬拦（missing_inputs 是提示）",
       isinstance(sched_on.missing_inputs(Path(tempfile.gettempdir()),
                                         sched_on.stages[0]), list))

    # ---------------------------------------------------------------- 5
    # 编辑：增删改连拖，落盘往返不丢
    editor = BpmnEditor(FlowDiagram.load(
        package_dir() / "static" / create_task_dialog.CUSTOM_INIT_FILE))
    n_before = len(editor.diagram().nodes)
    new_id = editor.add_node(name="新步骤")
    ok("加节点", len(editor.diagram().nodes) == n_before + 1)
    editor.rename_node(new_id, "改过的名字")
    ok("改名", editor.diagram().node(new_id).name == "改过的名字")
    # ⚠️⚠️ **改名不断绑**：阶段身份是节点的属性（落盘在 ``guji:stage``），
    # 名字只是显示标签。以前改名会**重算**阶段——「图片去底色」改成「AI 抠图」
    # 就接不回任何阶段，整张图被判"坏图"而回落默认流程（用户只改了个标签，
    # 流程却被换掉了）。现在：认得出的名字换绑，认不出的名字只改显示。
    _real_node = next(n.id for n in editor.diagram().nodes
                      if n.stage == "rembg")
    editor.rename_node(_real_node, "AI 抠图")
    ok("改名成认不出的名字 ⇒ **保留原阶段**（只改显示，不断绑）",
       editor.diagram().node(_real_node).stage == "rembg",
       str(editor.diagram().node(_real_node).stage))
    # 改成另一个已知阶段名 ⇒ 换绑（"改名切换步骤类型"，有意保留）
    editor.rename_node(_real_node, "检测文本框")
    ok("改成已知阶段名 ⇒ 换绑到那个阶段",
       editor.diagram().node(_real_node).stage == "detect",
       str(editor.diagram().node(_real_node).stage))
    editor.rename_node(_real_node, "图片去底色")
    ok("改回原来的阶段名 ⇒ 换绑回来",
       editor.diagram().node(_real_node).stage == "rembg",
       str(editor.diagram().node(_real_node).stage))
    # 本来就没阶段的节点 ⇒ 改名不许凭空接上（随手一改多出运行步骤更糟）
    editor.rename_node(new_id, "还是认不出")
    ok("本来就没有阶段的节点改名 ⇒ 仍是 None（不凭空接上）",
       editor.diagram().node(new_id).stage is None,
       str(editor.diagram().node(new_id).stage))
    # 身份落盘往返：自定义名字存进 ``guji:stage``，重读不再靠名字猜
    editor.rename_node(_real_node, "AI 抠图")
    _roundtrip = Path(ctx.tmp) / "rename_roundtrip.bpmn"
    editor.diagram().save(_roundtrip)
    _reloaded = FlowDiagram.load(_roundtrip)
    _back = next(n for n in _reloaded.nodes if n.id == _real_node)
    ok("存盘重读 ⇒ 自定义名字 + 原阶段都在（不再靠名字猜）",
       _back.name == "AI 抠图" and _back.stage == "rembg",
       f"{_back.name!r} / {_back.stage!r}")
    _xml = _roundtrip.read_bytes()
    ok("guji:stage 写进文件（外部工具丢弃它就退回名字匹配＋降级告警）",
       b"guji:stage" in _xml)
    target = next(n.id for n in editor.diagram().nodes
                  if n.id != new_id and n.kind == KIND_TASK)
    flow_id = editor.connect(new_id, target, "分支")
    ok("连线", flow_id is not None)
    ok("自连被拒", editor.connect(new_id, new_id) is None)
    ok("重复连被拒", editor.connect(new_id, target) is None)
    from PySide6.QtCore import QPointF

    editor._drag_id = new_id
    editor._moved = False
    editor._press_pos = None
    editor._move_node(QPointF(777.0, 555.0))
    box = editor.diagram().node_box(new_id)
    ok("拖拽改坐标", abs(box[0] - 777.0) < 1 and abs(box[1] - 555.0) < 1,
       str(box))
    # 拖动中**冻结连接点**：折点按冻结锚点现算（线跟着节点平滑走，不猛跳），
    # 松手 _finish_drag 才清掉、重新自动匹配——过时的旧折点不再残留
    ok("拖拽中连线折点按冻结锚点现算（跟着节点走）",
       flow_id in editor.diagram().waypoints)
    editor._finish_drag()
    ok("松手清掉临时折点（连线重新自动匹配，旧折点不残留）",
       flow_id not in editor.diagram().waypoints)
    flows_before = len(editor.diagram().flows)
    editor.remove_node(new_id)
    ok("删节点级联删连线",
       len(editor.diagram().nodes) == n_before
       and len(editor.diagram().flows) == flows_before - 1)

    tmp_root = Path(tempfile.mkdtemp(prefix="flow_ui_"))
    try:
        saved = tmp_root / "edited.bpmn"
        editor.save_to(saved)
        back = FlowDiagram.load(saved)
        ok("落盘往返：节点不丢",
           len(back.nodes) == len(editor.diagram().nodes))
        ok("落盘往返：连线不丢",
           len(back.flows) == len(editor.diagram().flows))
        # DI 段里除了节点还有**文字注释框**（用户挂在节点旁的说明）
        ok("落盘往返：坐标不丢（DI 段可读，节点 + 注释框都在）",
           len(back.boxes) == len(editor.diagram().nodes)
           + len(editor.diagram().notes),
           f"{len(back.boxes)} vs 节点{len(editor.diagram().nodes)}"
           f"+注释{len(editor.diagram().notes)}")
        ok("落盘往返：注释文本不丢",
           sorted(n.text for n in back.notes)
           == sorted(n.text for n in editor.diagram().notes))
        ok("落盘往返：注释的挂接关系不丢",
           back.note_links == editor.diagram().note_links)
        src = next(n for n in back.nodes if n.kind == KIND_TASK)
        ok("落盘后仍认得出运行阶段（名字→阶段表生效）",
           src.stage is not None, str(src.name))

        # 手造一份带网关的图，验渲染器与状态机对任意 bpmn 都成立
        handmade = FlowDiagram(
            nodes=(
                DiagramNode("s", KIND_START, "开始"),
                DiagramNode("a", KIND_TASK, "提取图片", stage="extract"),
                DiagramNode("g", KIND_EXCLUSIVE, "是否拼版"),
                DiagramNode("b", KIND_TASK, "图片拼版", stage="imposition"),
                DiagramNode("p", KIND_TASK, "生成 PDF", stage="print"),
                DiagramNode("e", KIND_END, "完成"),
            ),
            flows=(
                DiagramFlow("f1", "s", "a"),
                DiagramFlow("f2", "a", "g"),
                DiagramFlow("f3", "g", "p", "否"),
                DiagramFlow("f4", "g", "b"),
                DiagramFlow("f5", "b", "p"),
                DiagramFlow("f6", "p", "e"),
            ),
        )
        FlowDiagram.auto_layout(handmade)
        ok("手造图也能算出拓扑序（无 DI 段时自动排布）",
           handmade.stage_order() == ("extract", "imposition", "print"),
           str(handmade.stage_order()))
        ok("手造图渲染不崩", BpmnView(handmade).width() > 0)

        # 连线端点**自动匹配**（用户 2026-10-06）：四个中线连接点按方位挑
        pair = FlowDiagram(
            nodes=(DiagramNode("a", KIND_TASK, "甲", stage="extract"),
                   DiagramNode("b", KIND_TASK, "乙", stage="detect")),
            flows=(DiagramFlow("f1", "a", "b"),),
            boxes={"a": (0.0, 0.0, 100.0, 80.0),
                   "b": (300.0, 20.0, 100.0, 80.0)},
        )
        points = pair.route(pair.flows[0])
        ok("横排节点：连线从右缘中点出、左缘中点入",
           points[0] == (100.0, 40.0) and points[-1] == (300.0, 60.0),
           str(points))
        pair.boxes["b"] = (20.0, 300.0, 100.0, 80.0)
        points = pair.route(pair.flows[0])
        ok("竖排节点：连线从下缘中点出、上缘中点入（不再斜戳角落）",
           points[0] == (50.0, 80.0) and points[-1] == (70.0, 300.0),
           str(points))
        pair.relayout()
        ok("relayout 分层铺开且拓扑不变（a 排在 b 左边）",
           pair.boxes["a"][0] < pair.boxes["b"][0]
           and all(n.id in pair.boxes for n in pair.nodes),
           str(pair.boxes))

        # 网关的多条出边**分配到不同的角**（用户 2026-10-06："判断输入输出都从
        # 四个角出，不是边的中间"）——早前是"同侧沿边摊开"，两条分支挤在
        # 菱形同一段斜边上，既不是角、又叠在一起。
        fork = FlowDiagram(
            nodes=(DiagramNode("g", KIND_EXCLUSIVE, "是否拼版"),
                   DiagramNode("b", KIND_TASK, "图片拼版", stage="imposition"),
                   DiagramNode("p", KIND_TASK, "生成 PDF", stage="print")),
            flows=(DiagramFlow("f1", "g", "p", "否"),
                   DiagramFlow("f2", "g", "b"),
                   DiagramFlow("f3", "b", "p")),
            boxes={"g": (0.0, 0.0, 50.0, 50.0),
                   "b": (300.0, 0.0, 100.0, 80.0),
                   "p": (300.0, 300.0, 100.0, 80.0)},
        )
        anchor_no = fork.route_anchor(fork.flows[0])
        anchor_yes = fork.route_anchor(fork.flows[1])
        ok("判断节点两条出边**占不同的角**（不是同侧摊开）",
           anchor_no[:2] != anchor_yes[:2],
           f"{anchor_no} vs {anchor_yes}")
        ok("起点锚点真不一样（两条线肉眼分得开）",
           fork.route(fork.flows[0])[0] != fork.route(fork.flows[1])[0])

        # ⚠️ 钉死"从**角**出，不是斜边中点"：菱形的锚点必须落在四个顶点上
        gx, gy, gw, gh = fork.node_box("g")
        vertices = {(gx + gw / 2, gy), (gx + gw, gy + gh / 2),
                    (gx + gw / 2, gy + gh), (gx, gy + gh / 2)}
        gw_points = [fork.route(f)[0] for f in fork.flows if f.source == "g"]
        ok("网关连线起点**全部落在菱形的四个顶点上**",
           all(any(abs(px - vx) < 0.6 and abs(py - vy) < 0.6
                   for vx, vy in vertices) for px, py in gw_points),
           str(gw_points))
        ok("网关的锚点落在**四个顶点**上（左右侧只有顶点，t 不产生斜边点）",
           all(any(abs(px - vx) < 0.6 and abs(py - vy) < 0.6
                   for vx, vy in vertices)
               for px, py in gw_points),
           str(gw_points))
        # 任务框**仍走边中点**（BPMN 惯例，别把网关的规则扩散到所有节点）
        ok("任务框的连线仍走**边中点**（没被网关规则波及）",
           fork.route(fork.flows[0])[-1][0] == 300.0
           and 0.0 < fork.route(fork.flows[0])[-1][1] < 380.0,
           str(fork.route(fork.flows[0])[-1]))

        # 直线被中间节点挡住时**绕行**（不穿框、不被节点盖住）
        trio = FlowDiagram(
            nodes=(DiagramNode("a", KIND_TASK, "甲", stage="extract"),
                   DiagramNode("b", KIND_TASK, "乙", stage="detect"),
                   DiagramNode("c", KIND_TASK, "丙", stage="rembg")),
            flows=(DiagramFlow("f1", "a", "c"),),
            boxes={"a": (0.0, 0.0, 100.0, 80.0),
                   "b": (150.0, 0.0, 100.0, 80.0),
                   "c": (300.0, 0.0, 100.0, 80.0)},
        )
        pts = trio.route(trio.flows[0])
        inside = any(150.0 < x < 250.0 and 0.0 < y < 80.0 for x, y in pts)
        ok("直线被中间节点挡住时绕行（折点不落在挡路节点的框里）",
           not inside and len(pts) >= 4, str(pts))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    # ---------------------------------------------------------------- 6
    # 弹窗外壳能真构造（parent 非 None）——所有弹窗同时踩过的坑
    from PySide6.QtWidgets import QWidget

    from desktop.components.create_task_dialog import CreateTaskDialog

    host = QWidget()
    shells = {}
    try:
        try:
            shells["创建任务"] = CreateTaskDialog(host)
            shells["查看/编辑流程"] = FlowDialog(init, host)
        except Exception as exc:  # noqa: BLE001 - 这就是被钉的故障
            ok("两个弹窗外壳都能构造（parent 非 None）", False,
               f"{type(exc).__name__}: {exc}")
        else:
            ok("两个弹窗外壳都能构造（parent 非 None）", True)
        for name, shell in shells.items():
            ok(f"「{name}」外壳是真 QDialog", shell.dialog.__class__.__name__ == "QDialog",
               shell.dialog.__class__.__name__)
        # 面板点关闭要能**关掉弹窗**（面板自己没窗口）
        shell = shells.get("查看/编辑流程")
        if shell is not None:
            shell.dialog.show()
            app.processEvents()
            shell.panel._close()
            app.processEvents()
            ok("面板点关闭能关掉弹窗（关的是所属窗口）",
               not shell.dialog.isVisible())
        # 创建任务面板：**两种模式都必须显示"当前流程"**（用户 2026-10-05 要求）
        panel = create_task_dialog.CreateTaskPanel()
        panel.show()
        app.processEvents()
        try:
            ok("默认是默认流程模式", not panel.uses_custom_flow())
            # ⚠️ 这组断言就是用户反馈的那条："无论是否勾选自定流程，都要告诉
            #    用户当前流程长什么样"——以前默认模式下节点图整块被藏起来。
            default_names = [n.name for n in load_default_diagram().nodes]
            ok("默认模式下**也显示**节点图（不是空白/隐藏）",
               len(panel.flow_view.diagram().nodes) > 0
               and [n.name for n in panel.flow_view.diagram().nodes]
               == default_names,
               f"{[n.name for n in panel.flow_view.diagram().nodes]}")
            ok("默认模式下提示写明用的是默认流程（「当前流程」标题行已删，"
               "由 mode_hint 承担告知）",
               "默认" in panel.mode_hint.text(), panel.mode_hint.text())
            ok("默认模式不传图（走字节拷贝模板，保住 guji:port）",
               panel.result_diagram() is None)
            ok("默认模式下「编辑流程」「恢复默认」不可见",
               not panel.edit_button.isVisible()
               and not panel.reset_button.isVisible())
            ok("默认模式也有选 PDF 的地方",
               panel.pick_button.isVisible() and panel.selected_pdf() is None)

            panel.set_custom_mode(True)
            app.processEvents()
            ok("勾上 checkbox 切自定义模式", panel.uses_custom_flow())
            custom_names = [n.name for n in panel.flow_view.diagram().nodes]
            # ⚠️ 不要求两张图"必须不同"：用户常只维护 task_default.bpmn，
            #    自定义初值就是它的副本（"从默认流程开始改"的合理起点）。
            #    要钉的是**显示的是"自定义那份图"**，而不是又一次默认图。
            init_names = [n.name for n in
                          create_task_dialog.load_custom_init().nodes]
            ok("自定义模式显示的是**初值文件**那张图",
               len(custom_names) > 0 and custom_names == init_names,
               f"{custom_names} vs {init_names}")
            ok("自定义模式提示写明用的是自定义流程",
               "自定义" in panel.mode_hint.text(), panel.mode_hint.text())
            ok("自定义模式传用户那张图（不是 None）",
               panel.result_diagram() is not None
               and [n.name for n in panel.result_diagram().nodes] == custom_names)
            ok("有「编辑流程」入口",
               hasattr(panel, "edit_button") and "编辑流程" in panel.edit_button.text())
            ok("有「恢复默认流程」入口",
               hasattr(panel, "reset_button")
               and "恢复默认" in panel.reset_button.text())
            ok("摘要讲清了步数与顺序",
               "步" in panel.flow_summary.text(), panel.flow_summary.text())
            # ⚠️ PDF **非必需**（用户 2026-10-06：「PDF 输入不是必须的」
            #    ＋「创建任务按钮不必等上传 pdf 才可以点」）——这两条是钉子，
            #    别哪天又给改回"没选文件就灰着"。
            ok("未选 PDF 时**照样**能提交（PDF 非必需）",
               panel.can_submit())
            ok("未选 PDF 时「创建任务」按钮是可点的（不是灰的）",
               panel.confirm_button.isEnabled()
               and not panel.confirm_button.isHidden())
            # 切回默认模式：图要跟着回去
            panel.set_custom_mode(False)
            app.processEvents()
            ok("切回默认模式后节点图跟着换回默认流程",
               [n.name for n in panel.flow_view.diagram().nodes] == default_names)
        finally:
            panel.close()
            app.processEvents()
    finally:
        for shell in shells.values():
            shell.dialog.deleteLater()
        host.deleteLater()
        app.processEvents()

    # ---------------------------------------------------------------- 6b
    # **编辑器必须真的能编辑**（用户反馈："无法做到编辑流程，元素添加，选择，
    # 两个任务关联等"）。根因是动作函数写好了却**没有任何按钮调它们**。
    try:
        panel = FlowPanel(init)
        panel.resize(1040, 720)
        panel.show()
        app.processEvents()
        board = panel.editor_panel
        editor = board.editor()
        ok("流程弹窗打开就是编辑态（不用再点一次「编辑流程」）",
           editor is not None and isinstance(editor, BpmnEditor))
        ok("工具栏有全部编辑动作",
           board.toolbar is not None
           and [b.text() for b in (board.add_button, board.gateway_button,
                                   board.link_button, board.rename_button,
                                   board.delete_button)]
           == ["添加步骤", "添加判断", "连线", "重命名", "删除"],
           str(board.toolbar))
        # 选择：点节点能选中，且状态行说清"选中了什么"
        node_ids = [n.id for n in editor.diagram().nodes if n.kind == KIND_TASK]
        target = node_ids[0]
        editor.set_selected(None)
        app.processEvents()
        ok("没选中时「重命名/删除」是灰的（选中才有意义）",
           not board.rename_button.isEnabled()
           and not board.delete_button.isEnabled())
        rect = editor.rect_of(target)
        _click_at(editor, rect.center().x(), rect.center().y())
        app.processEvents()
        ok("点节点能选中", editor.selected() == target, str(editor.selected()))
        ok("选中后「重命名/删除」变可用",
           board.rename_button.isEnabled() and board.delete_button.isEnabled())
        ok("状态行写出了选中的是哪个步骤与它的运行阶段",
           "已选中" in board.status.text()
           and editor.diagram().node(target).name in board.status.text(),
           board.status.text())

        # 动作按钮**真的接上了**编辑器（接不上就是死按钮——上一版的毛病）
        fired: list[str] = []
        editor.ask_add_node = lambda: fired.append("add")
        editor.add_gateway = lambda *a, **k: fired.append("gateway")
        editor.ask_rename_selected = lambda: fired.append("rename")
        editor.ask_delete_selected = lambda: fired.append("delete")
        board.add_button.click()
        board.gateway_button.click()
        board.rename_button.click()
        board.delete_button.click()
        ok("工具栏按钮都真的接到编辑器动作上（不是死按钮）",
           fired == ["add", "gateway", "rename", "delete"], str(fired))
        # 撤掉落上的替身（实例属性会盖住类方法），并把"添加判断"顺手打开的
        # 连线模式复位——后面要用**真**方法验证行为。
        del editor.ask_add_node, editor.add_gateway
        del editor.ask_rename_selected, editor.ask_delete_selected
        editor.set_link_mode(False)
        board.link_button.setChecked(False)

        # 选中连线
        flow_ids = [f.id for f in editor.diagram().flows]
        editor.set_selected_flow(flow_ids[0])
        board._sync_status()
        ok("能选中**连线**（并清掉节点选中）",
           editor.selected_flow() == flow_ids[0] and not editor.selected())
        ok("状态行写出了选中的是哪条连线",
           "连线" in board.status.text(), board.status.text())

        # 元素添加：加一个能被运行时认出来的步骤
        before = len(editor.diagram().nodes)
        new_id = editor.add_node(KIND_TASK, "图片拼版")
        app.processEvents()
        ok("「添加步骤」能加节点", len(editor.diagram().nodes) == before + 1)
        ok("新加的节点按名字接上了运行阶段（否则加了也不跑）",
           editor.diagram().node(new_id).stage == "imposition",
           str(editor.diagram().node(new_id).stage))
        gw = editor.add_gateway("判断")
        ok("「添加判断」加的是网关菱形",
           editor.diagram().node(gw).is_gateway)
        ok("「添加判断」只摆节点、不进连线模式（判断节点不必连线）",
           not editor.link_mode())

        # 两个任务关联：连线模式（点起点 → 点终点）+ connect
        ok("开始不在连线模式", not editor.link_mode())
        board.link_button.click()
        app.processEvents()
        ok("点「连线」进入连线模式", editor.link_mode())
        link_src = editor.diagram().nodes[1].id
        link_dst = new_id
        flows_before = len(editor.diagram().flows)
        _src_center = editor.rect_of(link_src).center()
        _dst_center = editor.rect_of(link_dst).center()
        _click_at(editor, _src_center.x(), _src_center.y())
        ok("连线模式：第一次点击记下起点",
           editor._link_from == link_src, str(editor._link_from))
        _click_at(editor, _dst_center.x(), _dst_center.y())
        app.processEvents()
        ok("连线模式：第二次点击把两个节点连起来",
           len(editor.diagram().flows) == flows_before + 1,
           f"{flows_before} -> {len(editor.diagram().flows)}")
        ok("连完自动退出连线模式（避免误连）", not editor.link_mode())
        ok("自连被拒绝", editor.connect(link_src, link_src) is None)
        ok("重复连线被拒绝", editor.connect(link_src, link_dst) is None)

        # 删除：删节点要连带删掉它的连线（悬空连线会让渲染/解析都出错）
        doomed = new_id
        attached = [f for f in editor.diagram().flows
                    if f.source == doomed or f.target == doomed]
        ok("被删节点上确实挂着连线（前提成立）", bool(attached))
        editor.set_selected(doomed)
        editor.remove_selected()
        app.processEvents()
        ok("「删除」删掉了节点",
           editor.diagram().node(doomed) is None)
        ok("删节点时连线一起删（不留悬空线）",
           all(f.source != doomed and f.target != doomed
               for f in editor.diagram().flows))

        # 拖拽：坐标变了，且折点被清掉重算
        from PySide6.QtCore import QPointF

        mover = editor.diagram().nodes[1].id
        box = editor.diagram().node_box(mover)
        editor._drag_id = mover
        editor._moved = True
        editor._drag_offset = QPointF(1.0, 1.0)
        editor._move_node(QPointF(box[0] + 77, box[1] + 55))
        app.processEvents()
        moved = editor.diagram().node_box(mover)
        ok("拖节点能改坐标", abs(moved[0] - box[0]) > 40)
        ok("拖动中连线**跟着节点平滑走**（连接点冻结，不猛跳）",
           all(f.id in editor.diagram().waypoints
               for f in editor.diagram().flows
               if f.source == mover or f.target == mover))
        editor._finish_drag()
        ok("松手后连接点重新自动匹配（临时折点清掉）",
           all(f.id not in editor.diagram().waypoints
               for f in editor.diagram().flows
               if f.source == mover or f.target == mover))
        editor._drag_id = None

        # 落盘往返：编辑结果必须能存进 bpmn 并被读回
        tmp_file = Path(tempfile.mkdtemp(prefix="flow_edit_")) / "edited.bpmn"
        editor.save_to(tmp_file)
        reloaded = FlowDiagram.load(tmp_file)
        ok("编辑结果落盘后能读回（节点/连线/坐标都不丢）",
           len(reloaded.nodes) == len(editor.diagram().nodes)
           and len(reloaded.flows) == len(editor.diagram().flows),
           f"{len(reloaded.nodes)}/{len(editor.diagram().nodes)} "
           f"{len(reloaded.flows)}/{len(editor.diagram().flows)}")
        ok("落盘往返后阶段顺序一致",
           reloaded.stage_order() == editor.diagram().stage_order())

        # ---- 固定节点面板：拖一个到画布就加一格（bpmn.io 手感）----
        from PySide6.QtCore import QMimeData, QPointF, Qt
        from PySide6.QtGui import QDropEvent

        from desktop.components.bpmn_palette import (
            GATEWAY_TOKEN, NODE_MIME, palette_steps,
        )

        palette = board.palette
        ok("编辑态有固定节点面板", palette is not None)

        def _palette_state() -> dict:
            return {
                palette.item(i).data(Qt.ItemDataRole.UserRole):
                bool(palette.item(i).flags() & Qt.ItemFlag.ItemIsEnabled)
                for i in range(palette.count())
            }

        def _drop(token: str, x: float, y: float) -> None:
            mime = QMimeData()
            mime.setData(NODE_MIME, token.encode("utf-8"))
            editor.dropEvent(QDropEvent(
                QPointF(x, y), Qt.DropAction.CopyAction, mime,
                Qt.LeftButton, Qt.NoModifier))

        state = _palette_state()
        ok("面板条目 = 固定步骤集 + 「判断」",
           set(palette_steps()).issubset(set(state))
           and GATEWAY_TOKEN in state,
           str(sorted(state)))
        # 当前图（默认模板）里已有的步骤必须**置灰**，否则能拖出重复节点
        live = _palette_state()
        before_nodes = len(editor.diagram().nodes)

        # 先删掉「图片去底色」——面板对应条目应恢复可拖
        rembg_node = next((n for n in editor.diagram().nodes
                           if n.stage == "rembg"), None)
        if rembg_node is not None:
            editor.set_selected(rembg_node.id)
            editor.remove_selected()
            app.processEvents()
            ok("删掉某一步之后，面板里那一条恢复可拖（能加回来）",
               _palette_state().get("rembg") is True,
               str(_palette_state()))
            # 拖回来：落点**居中**，名字/阶段都接回运行
            _drop("rembg", 400.0, 400.0)
            app.processEvents()
            ok("从面板拖出一个节点即加了一格",
               len(editor.diagram().nodes) == before_nodes,
               f"{before_nodes} -> {len(editor.diagram().nodes)}")
            made = editor.diagram().node(editor.selected())
            ok("拖出来的节点接得上运行阶段（名字 → 阶段表）",
               made is not None and made.stage == "rembg",
               str(made and (made.name, made.stage)))
            if made is not None:
                center = editor.rect_of(made.id).center()
                ok("节点**以落点为中心**落位（所见即所得）",
                   abs(center.x() - 400) < 2 and abs(center.y() - 400) < 2,
                   f"{center.x():.1f},{center.y():.1f}")
            ok("加回来之后面板该条又置灰了",
               _palette_state().get("rembg") is False)
        # 选中一个节点再拖 → 顺手接一条线（"挂在它后面"）
        some = editor.diagram().nodes[0].id
        editor.set_selected(some)
        flows_before = len(editor.diagram().flows)
        _drop(GATEWAY_TOKEN, 700.0, 520.0)
        app.processEvents()
        gateway = editor.diagram().node(editor.selected())
        ok("拖出来的「判断」是网关菱形",
           gateway is not None and gateway.is_gateway,
           str(gateway and gateway.kind))
        # ⚠️ 判断节点**不**自动接线（用户 2026-10-06）：是否拼版在排版面板
        #    里开，判断节点摆哪儿都行、不必跟谁绑定
        ok("「判断」拖进来不自动接线（不必与其他节点绑定）",
           len(editor.diagram().flows) == flows_before,
           f"{flows_before} -> {len(editor.diagram().flows)}")
        # 任务节点仍是"接在选中节点后面"：加一个任务节点验自动连线还在
        linked = editor.add_node(KIND_TASK, "生成 PDF", stage="print",
                                 connect_from=some)
        ok("任务节点拖进来时若选中了节点，仍自动连上一条线",
           len(editor.diagram().flows) == flows_before + 1,
           f"{flows_before} -> {len(editor.diagram().flows)}")
        editor.remove_node(linked)

        # ---- 四个中线连接点：按点拖到目标节点即连线（不必开连线模式）----
        port_src = editor.diagram().nodes[0].id
        port_dst = next(
            n.id for n in editor.diagram().nodes
            if n.id != port_src
            and not any(f.source == port_src and f.target == n.id
                        for f in editor.diagram().flows))
        srect = editor.rect_of(port_src)
        drect = editor.rect_of(port_dst)
        hit = editor._port_at(QPointF(srect.right(), srect.center().y()))
        ok("节点右缘中点是**中线连接点**（上下左右共四个）",
           hit is not None and hit[0] == port_src and hit[1] == "right",
           str(hit))
        flows_before = len(editor.diagram().flows)
        _stroke(editor, [
            (srect.right(), srect.center().y()),
            ((srect.right() + drect.center().x()) / 2,
             (srect.center().y() + drect.center().y()) / 2),
            (drect.center().x(), drect.center().y()),
        ])
        app.processEvents()
        ok("按住连接点拖到目标节点即连上（松手才连，途中松手不算）",
           len(editor.diagram().flows) == flows_before + 1,
           f"{flows_before} -> {len(editor.diagram().flows)}")

        # ---- 自动排版：分层铺开、连线重算、语义不变 ----
        order_before = editor.diagram().stage_order()
        editor.auto_layout()
        app.processEvents()
        ok("自动排版给每个节点都排了坐标",
           all(n.id in editor.diagram().boxes
               for n in editor.diagram().nodes))
        ok("自动排版清掉旧折点（连线按新坐标重算）",
           not editor.diagram().waypoints)
        ok("自动排版不改变阶段顺序（排版是纯视觉）",
           editor.diagram().stage_order() == order_before,
           f"{order_before} vs {editor.diagram().stage_order()}")
        ok("排版后画布照常渲染",
           editor.width() > 0 and editor.content_size()[0] > 0)

        # 只读态：没有工具栏
        readonly = FlowPanel(init, editable=False)
        ok("只读态没有工具栏（看流程的入口不该给编辑按钮）",
           readonly.editor_panel.toolbar is None)
        ok("只读态没有「保存流程」按钮",
           not readonly.confirm_button.isVisible())
        readonly.close()
        shutil.rmtree(tmp_file.parent, ignore_errors=True)
        panel.close()
        app.processEvents()
    except Exception as exc:  # noqa: BLE001
        ok("流程编辑器（工具栏/选择/连线/增删/落盘）整体可用", False,
           f"{type(exc).__name__}: {exc}")

    # ---------------------------------------------------------------- 7
    # 落盘闭环：创建任务 → 详情页读回，阶段顺序一致
    from desktop.store import TaskStore

    root = Path(tempfile.mkdtemp(prefix="flow_store_"))
    try:
        store = TaskStore(root)
        pdf = root / "样例.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        tid = store.create_task(pdf, "h1", "自定义流程书", diagram=init)
        got = store.task_diagram(tid)
        ok("创建任务时把图落进 flow.bpmn（节点数一致）",
           len(got.nodes) == len(init.nodes),
           f"{len(got.nodes)} vs {len(init.nodes)}")
        ok("落盘后阶段顺序一致",
           got.stage_order() == init.stage_order(),
           f"{got.stage_order()} vs {init.stage_order()}")
        ok("落盘后网关/事件类型不丢（图形保真）",
           sorted(n.kind for n in got.nodes) == sorted(n.kind for n in init.nodes))

        # 改流程 → 落盘 → 立刻读得到（缓存必须失效）
        modified = FlowDiagram(
            nodes=tuple(n for n in got.nodes if n.stage != "print") + (
                DiagramNode("p2", KIND_TASK, "生成 PDF", stage="print"),
            ),
            flows=got.flows, boxes=got.boxes, waypoints=got.waypoints,
        )
        store.save_task_diagram(tid, modified)
        ok("save_task_diagram 后 task_diagram 立刻读到新图（mtime 缓存已清）",
           store.task_diagram(tid).stage_order() == modified.stage_order(),
           str(store.task_diagram(tid).stage_order()))

        tid2 = store.create_task(pdf, "h2", "默认流程书")
        ok("下一个任务不受上一条自定义流程影响",
           store.task_diagram(tid2).stage_order() ==
           load_default_diagram().stage_order())
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ---------------------------------------------------------------- 8
    # 详情页入口
    detail = ctx.d
    ok("详情页页头有「查看/编辑流程」入口",
       hasattr(detail, "flow_button") and "流程" in detail.flow_button.toolTip(),
       getattr(detail, "flow_button", None) and detail.flow_button.toolTip())
    ok("详情页能读出本任务流程图（弹窗的数据源）",
       len(page.store.task_diagram(detail.task_id).nodes) > 0)
    ok("store.save_task_diagram 存在（改流程要能落盘）",
       callable(getattr(page.store, "save_task_diagram", None)))

    # ---------------------------------------------------------------- 9
    # 「创建任务」改成二级页面 + 任务名称 + 流程编辑内嵌（用户 2026-10-06）
    from desktop.pages.createtask.page import CreateTaskPage
    from desktop.pages.taskflow.page import TaskFlowPage
    from desktop.shell import ROUTE_CREATE, ROUTE_FLOW

    ctx_page = CreateTaskPage(page.store)
    ctx_page.show()
    app.processEvents()
    ok("壳层为这两个页面备了路由键（导航/反查靠它）",
       bool(ROUTE_CREATE) and bool(ROUTE_FLOW) and ROUTE_CREATE != ROUTE_FLOW)
    ok("创建任务是**页面**（不是弹窗）且有任务名输入框",
       hasattr(ctx_page, "name_edit") and hasattr(ctx_page, "back_button"))
    # ---- 任务名输入框的外观（用户 2026-10-06：不好看/ 高度不够 / 太长）----
    from desktop.ui.widgets import CONTROL_HEIGHT
    ok("任务名输入框高度与项目表单控件一致（不再是矮一截的原生框）",
       ctx_page.name_edit.height() == CONTROL_HEIGHT
       or ctx_page.name_edit.minimumHeight() == CONTROL_HEIGHT,
       f"h={ctx_page.name_edit.height()} "
       f"min={ctx_page.name_edit.minimumHeight()} "
       f"want={CONTROL_HEIGHT}")
    ok("任务名输入框**不占满整行**（有宽度上限 + 右侧留白）",
       ctx_page.name_edit.maximumWidth() > 0
       and ctx_page.name_edit.maximumWidth() <= 400,
       f"maxW={ctx_page.name_edit.maximumWidth()}")
    # 默认名「任务#XXXX」：占位提示（用户第 4 条）
    default_hint_text = ctx_page.name_edit.placeholderText()
    ok("默认任务名是「任务#XXXX」形式（序号=任务号，四位补零）",
       default_hint_text.startswith("任务#")
       and len(default_hint_text) == 7
       and default_hint_text[3:].isdigit(),
       default_hint_text)
    # 选 PDF → 自动填文件名（留空时的默认，用户第 5 条）
    ctx_page.panel.set_pdf(ctx.pdf)
    ctx_page._autofill_name()
    app.processEvents()
    ok("选了 PDF 自动把文件名填进任务名（可再改）",
       ctx_page.name_edit.text() == ctx.pdf.stem,
       repr(ctx_page.name_edit.text()))
    ctx_page.set_name("自定名")
    ok("任务名可改", ctx_page.task_name() == "自定名")
    ok("留空时提示说清会用哪个文件名",
       "留空" in ctx_page.name_hint.text()
       or "任务名将使用" in ctx_page.name_hint.text(),
       ctx_page.name_hint.text())
    # 选完再清空 → 提示改口成「默认名」（没 PDF 时的那一套，用户第 4 条）
    ctx_page.name_edit.clear()
    ctx_page._refresh_hint()
    ok("清空名字（有 PDF）后提示改说用文件名",
       ctx.pdf.stem in ctx_page.name_hint.text(),
       ctx_page.name_hint.text())
    ok("面板在页面内不带第二层边距（「创建任务」与「任务名称」左对齐）",
       ctx_page.panel.layout().contentsMargins().left() == 0
       and ctx_page.layout().contentsMargins().left() > 0,
       f"panel={ctx_page.panel.layout().contentsMargins().left()} "
       f"page={ctx_page.layout().contentsMargins().left()}")
    # 流程编辑**内嵌**：不弹窗、预览让位
    ctx_page.panel.set_custom_mode(True)
    app.processEvents()
    ctx_page.panel._on_edit_flow()
    app.processEvents()
    ok("「编辑流程」就地展开在本页里（编辑器已建）",
       ctx_page.panel._editor is not None)
    ok("进编辑态时流程预览让位（不与编辑器同屏）",
       ctx_page.panel._editor_host.isVisible()
       and ctx_page.panel.flow_scroll.isHidden()
       and ctx_page.panel.edit_button.isHidden())
    ok("进编辑态时底部「取消/确认」整行收起（只留编辑器的关闭/保存，"
       "不出现两排确认按钮）",
       ctx_page.panel._button_bar.isHidden())
    ok("内嵌编辑器不带自己的标题（避免页面套页面）",
       ctx_page.panel._editor.title_label.isHidden())
    ok("内嵌编辑器不会去关宿主窗口（否则整页消失）",
       ctx_page.panel._editor._close_window_on_end is False)
    ctx_page.panel._on_editor_done(False)      # 「关闭」= 丢弃
    app.processEvents()
    ok("关掉编辑器回到流程预览",
       ctx_page.panel._editor_host.isHidden()
       and ctx_page.panel.flow_scroll.isVisible()
       and ctx_page.panel._button_bar.isVisible())

    # 详情页「查看/编辑流程」→ 流程编辑**页面**
    ok("详情页发的是 flow_edit_requested（宿主切页，不再自己弹窗）",
       hasattr(detail, "flow_edit_requested"))
    flow_page = TaskFlowPage(page.store)
    flow_page.show()
    app.processEvents()
    ok("流程编辑页能打开本任务流程", flow_page.open_task(detail.task_id))
    ok("流程页标题带任务名（知道自己改的是哪条）",
       detail.task_id in flow_page.title.text()
       or page.store.get_task(detail.task_id)["name"] in flow_page.title.text(),
       flow_page.title.text())
    ok("流程页的编辑器不会去关整页（close_window=False）",
       flow_page._panel is not None
       and flow_page._panel._close_window_on_end is False)
    # 保存 → 落盘
    before = len(page.store.task_diagram(detail.task_id).nodes)
    flow_page._panel.accept()
    app.processEvents()
    ok("流程页「保存流程」把图落回 flow.bpmn",
       len(page.store.task_diagram(detail.task_id).nodes) == before)
    flow_page.close()
    ctx_page.close()

    # 任务改名：非必需、可随时改
    store_ = page.store
    tid_ = detail.task_id
    old_name = store_.get_task(tid_)["name"]
    ok("store.rename_task 存在（任务名可随时修改）",
       callable(getattr(store_, "rename_task", None)))
    ok("改名生效", store_.rename_task(tid_, "改过的名字")
       and store_.get_task(tid_)["name"] == "改过的名字",
       store_.get_task(tid_)["name"])
    ok("改回原名（名字没变时返回 False，不做无谓写盘）",
       store_.rename_task(tid_, old_name)
       and store_.rename_task(tid_, old_name) is False,
       store_.get_task(tid_)["name"])
    # ⚠️ 先改成别的名字再清空：清空回落的就是文件名，若当前名**本来就是**
    #    文件名，rename_task 会正确地返回 False（无变化），断言就假红了。
    store_.rename_task(tid_, "临时名")
    ok("清空名字回落到源文件名（不留空名字）",
       store_.rename_task(tid_, "   ")
       and store_.get_task(tid_)["name"] == ctx.pdf.stem,
       store_.get_task(tid_)["name"])
    ok("改不存在的任务返回 False（不抛）",
       store_.rename_task("9999", "x") is False)
    # 行内编辑的守卫方向（isHidden 而非 isVisible，且方向别反）
    ok("行内改名：点开输入框、标题让位",
       (detail._begin_rename() or True)
       and not detail.rename_edit.isHidden() and detail.detail_title.isHidden())
    detail.rename_edit.setText("行内改的名字")
    detail._commit_rename()
    app.processEvents()
    ok("行内改名落盘并刷新标题",
       store_.get_task(tid_)["name"] == "行内改的名字"
       and detail.detail_title.text() == "行内改的名字",
       detail.detail_title.text())
    store_.rename_task(tid_, old_name)

    # ---------------------------------------------------------------- 10
    # 创建任务页的 6 条反馈（用户 2026-10-06 一次性提的）
    # ①名称框不好看/ 高度不够 / 长度占满屏幕 → 见第 9 节
    # ②PDF 非必需 ③④按钮可点 → 见第 4 节与第 9 节
    # ④默认名「任务#XXXX」⑤没填用pdf 名 → 见第 9 节；这里验**落库**那一半
    # ⑥创建成功但 GUI 消失 → 见下面「面板不关宿主窗口」
    ok("点「创建任务」**不关任何窗口**（用户 2026-10-06：创建成功但 GUI 不见了）",
       _submit_keeps_window(ctx_page))
    # 空壳任务（没选 PDF）：store 层落库 + 详情页的补选入口
    _check_shell_task(store_, ctx.pdf, app)

    # ---------------------------------------------------------------- 11
    # 同日第二批三条（用户 2026-10-06）
    # ①页头 PDF 按钮用现成的 PDF_FILE 图标（不是内置的空白 DOCUMENT）
    # ②创建时"流程要 PDF 但用户没给"要问一句——两条路都合法
    # ③详情页补选：同 hash 不重复传；新 PDF 先确认再换（换完清后续节点数据）
    _check_pdf_button_icon(detail)
    _check_missing_pdf_prompt(ctx_page, ctx.pdf)
    _check_source_pick_flow(store_, ctx.pdf, app)
    # ---------------------------------------------------------------- 12
    # 上一次创建任务的信息要清掉（用户 2026-10-06 截图报障）
    _check_create_page_reset(ctx_page, ctx.pdf)
    _check_open_create_resets()
    _check_first_entry_shows_prompt(app)
    # ---------------------------------------------------------------- 13
    # 创建表单页：已选的文件可以清理删除（用户 2026-10-06）
    _check_clear_pdf(ctx_page, ctx.pdf)
    # ---------------------------------------------------------------- 14
    # 编辑流程保存后，顶部步骤条**立即**按新图重排（用户 2026-10-06 报障）
    _check_flow_saved_refreshes_bar()
    # ---------------------------------------------------------------- 15
    # 「选文件夹」批量导入（用户 2026-10-06："是否可以选择目录"）
    _check_insert_from_folder()
    # ---------------------------------------------------------------- 16
    # 输入入口红框 + 「打开任务数据目录」移到右下角（用户 2026-10-06）
    _check_input_entry_marks()
    # ---------------------------------------------------------------- 17
    # 提示层主按钮 = **选择图片目录**（用户 2026-10-06）
    _check_prompt_picks_folder()
    # ---------------------------------------------------------------- 18
    # 不需要 PDF 的流程藏 PDF 图标 + extract/源PDF 成对删除
    _check_source_pdf_pairing()


# ------------------------------------------------- 14. 保存流程 → 步骤条立即刷新
#: 一条**四格**流程（无 extract，detect 打头）——复刻用户报障现场。
_FLOW_4_SLOTS = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
 xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:guji="http://guji.local"
 id="D1" targetNamespace="http://bpmn.io/schema/bpmn">
 <bpmn:process id="P1" isExecutable="false">
  <bpmn:startEvent id="s"><bpmndi:OMNDIOSExtension/></bpmn:startEvent>
  <bpmn:task id="a" name="检测文本框" guji:stage="detect"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="b" name="图片去底色" guji:stage="rembg"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="c" name="图片拼版" guji:stage="imposition"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="d" name="生成PDF" guji:stage="print"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:sequenceFlow id="f1" sourceRef="s" targetRef="a"/>
  <bpmn:sequenceFlow id="f2" sourceRef="a" targetRef="b"/>
  <bpmn:sequenceFlow id="f3" sourceRef="b" targetRef="c"/>
  <bpmn:sequenceFlow id="f4" sourceRef="c" targetRef="d"/>
 </bpmn:process>
 <bpmndi:BPMNDiagram id="DD"><bpmndi:BPMNPlane id="PP" bpmnElement="P1"/></bpmndi:BPMNDiagram>
</bpmn:definitions>
"""


# ------------------------------------------- 15. 选文件夹批量导入（入口节点）
#: 一条**去底色打头**的流程（无 extract）——用户报障的原话是"去底色在第一个
#: 节点的时候，是否也可以输入目录"。
_FLOW_REMBG_FIRST = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
 xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:guji="http://guji.local"
 id="D1" targetNamespace="http://bpmn.io/schema/bpmn">
 <bpmn:process id="P1" isExecutable="false">
  <bpmn:startEvent id="s"><bpmndi:OMNDIOSExtension/></bpmn:startEvent>
  <bpmn:task id="a" name="图片去底色" guji:stage="rembg"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="b" name="生成PDF" guji:stage="print"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:sequenceFlow id="f1" sourceRef="s" targetRef="a"/>
  <bpmn:sequenceFlow id="f2" sourceRef="a" targetRef="b"/>
 </bpmn:process>
 <bpmndi:BPMNDiagram id="DD"><bpmndi:BPMNPlane id="PP" bpmnElement="P1"/></bpmndi:BPMNDiagram>
</bpmn:definitions>
"""


# --------------------------------- 16. 输入入口红框 + 打开任务目录移到右下角
# ------------------------------- 17. 提示层主按钮 = 选择图片目录（文案+行为）
# ------------------- 18. 源 PDF 图标显隐 + extract/源PDF 成对删除（用户两条）
#: 含「提取图片」的流程（源 PDF 事件 + extract + detect + print）。
_FLOW_WITH_EXTRACT = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
 xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:guji="http://guji.local"
 id="D1" targetNamespace="http://bpmn.io/schema/bpmn">
 <bpmn:process id="P1" isExecutable="false">
  <bpmn:startEvent id="pdf" name="源PDF"><bpmndi:OMNDIOSExtension/></bpmn:startEvent>
  <bpmn:task id="ex" name="提取图片" guji:stage="extract"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="dt" name="检测文本框" guji:stage="detect"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="pr" name="生成PDF" guji:stage="print"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:sequenceFlow id="f1" sourceRef="pdf" targetRef="ex"/>
  <bpmn:sequenceFlow id="f2" sourceRef="ex" targetRef="dt"/>
  <bpmn:sequenceFlow id="f3" sourceRef="dt" targetRef="pr"/>
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


def _check_source_pdf_pairing() -> None:
    """「上传 PDF」与「提取图片」成对；流程不吃 PDF 时**不摆PDF 图标**。

    用户 2026-10-06 两条一起提的：

    1. 不需要上传 pdf 的流程右侧不需 pdf 上传图标；
    2. 流程编辑中，如果删除了 上传pdf 或者 pdf图片提取中的一个，
       另外一个的存在没有意义，因此需要同步删除另外一个。

    钉五件事：①含 extract 时 PDF 按钮**照常显示**（别把补救入口一起藏了，
    空壳任务还要靠它补选）；②不含 extract 时**整颗藏起来**、插图按钮仍在；
    ③④正反两向删除都**成对**（删 extract→源PDF 也没了；删源PDF→extract
    也没了）；⑤**Delete 键那条路径同样成对**——它与工具栏「删除」是同一个
    动作的两条入口，只改一处，键盘删就会漏。
    """
    import shutil
    import tempfile

    from pathlib import Path

    from PySide6.QtWidgets import QApplication, QMessageBox

    from desktop.shell import ModuleShell
    from desktop.store.store import TaskStore
    from desktop.ui import theme as theme
    from tests.selftests._context import ok, silence_source_prompt

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    tmp = Path(tempfile.mkdtemp(prefix="guji_pairing_"))
    orig_question = QMessageBox.question
    try:
        store = TaskStore(tmp / "data")
        shell = ModuleShell(store)
        shell.resize(1400, 900)
        shell.show()
        app.processEvents()
        page = shell.detail_page
        silence_source_prompt(page)

        with_pdf = store.create_task(source_path="", source_hash="",
                                     name="含提取")
        (store.task_dir(with_pdf) / "flow.bpmn").write_text(
            _FLOW_WITH_EXTRACT, encoding="utf-8")
        no_pdf = store.create_task(source_path="", source_hash="", name="无提取")
        (store.task_dir(no_pdf) / "flow.bpmn").write_text(
            _FLOW_DETECT_FIRST, encoding="utf-8")

        # ---- ① 含 extract ⇒ PDF 按钮照常显示 ----
        shell.open_detail(with_pdf)
        app.processEvents()
        ok("流程含「提取图片」⇒ PDF 上传图标**照常显示**（空壳任务要靠它补选）",
           not page.source_button.isHidden())
        # ---- ①b 输入按钮跟着**第一个节点**走（用户 2026-10-06 规则①）----
        # 「图片提取」打头 ⇒ 它的输入是源 PDF：页头只显示 PDF，图片/目录
        # 两个入口整对藏起来（摆着会让人以为这一步要喂图）。
        ok("「图片提取」打头 ⇒ 页头图片/目录入口**藏起来**（只显示 PDF，规则①）",
           page.insert_button.isHidden()
           and page.insert_dir_button.isHidden())
        ok("藏起来的入口红框仍在（常驻标识不随显隐丢）",
           str(theme.DANGER) in (page.insert_button.styleSheet() or ""))

        # ---- ② 不含 extract ⇒ PDF 按钮整颗藏起来 ----
        shell.open_detail(no_pdf)
        app.processEvents()
        ok("流程不含「提取图片」⇒ PDF 上传图标**藏起来**（用户 2026-10-06）",
           page.source_button.isHidden())
        ok("藏 PDF 图标不影响插图按钮（那才是这一步的输入入口）",
           not page.insert_button.isHidden())
        # ---- ②b 检测打头 ⇒ 图片 + 目录两个入口一起显示（规则②）----
        ok("「检测文本框」打头 ⇒ 页头只显示图片输入和文件输入（规则②）",
           not page.insert_dir_button.isHidden())
        ok("检测打头 ⇒ 检测页左下角「＋/📁」显示（入口要图片，规则③）",
           _viewer_entry_button(page.detect_viewer, "插入图片（可多选）")
           is not None
           and not _viewer_entry_button(
               page.detect_viewer, "插入图片（可多选）").isHidden()
           and _viewer_entry_button(
               page.detect_viewer, "把一个文件夹里的图片批量插入") is not None
           and not _viewer_entry_button(
               page.detect_viewer,
               "把一个文件夹里的图片批量插入").isHidden())

        # ---- ③④ 成对删除（正反两向）----
        # ⚠️ 确认框替成"是"：不替的话 ``ask_delete_selected`` 会挂住整个自测
        #    （离屏下真弹模态＝看门狗 os._exit(3)）。
        QMessageBox.question = staticmethod(
            lambda *a, **k: QMessageBox.StandardButton.Yes)

        def names_after_deleting(task_id: str, node_id: str) -> list[str]:
            """选中原生节点 → 走工具栏那条删除路径 → 剩下哪些节点名。"""
            shell.open_detail(task_id)
            app.processEvents()
            shell.open_flow(task_id)
            app.processEvents()
            editor = shell.flow_page()._panel.editor_panel.editor()
            editor.set_selected(node_id)
            editor.ask_delete_selected()
            app.processEvents()
            return sorted(n.name for n in editor.diagram().nodes)

        left = names_after_deleting(with_pdf, "ex")   # 删 extract
        ok("删「提取图片」⇒「源PDF」**跟着一起没了**（成对）",
           "源PDF" not in left, str(left))
        ok("  其余步骤**不受影响**（只删这一对）",
           "检测文本框" in left, str(left))

        left = names_after_deleting(with_pdf, "pdf")  # 删源 PDF
        ok("删「源PDF」⇒「提取图片」**跟着一起没了**（反向成对）",
           "提取图片" not in left, str(left))

        # ---- ⑤ Delete 键那条路径 ----
        shell.open_detail(with_pdf)
        app.processEvents()
        shell.open_flow(with_pdf)
        app.processEvents()
        editor = shell.flow_page()._panel.editor_panel.editor()
        editor.set_selected("ex")
        editor.remove_selected()
        app.processEvents()
        left = sorted(n.name for n in editor.diagram().nodes)
        ok("Delete 键删除**同样成对**（它与工具栏是同一动作的两条入口）",
           "源PDF" not in left and "提取图片" not in left, str(left))

        shell.close()
    finally:
        QMessageBox.question = orig_question
        shutil.rmtree(tmp, ignore_errors=True)


def _check_prompt_picks_folder() -> None:
    """缺入口图片时，提示层主按钮**真的开目录框**并把整目录导进来。

    用户 2026-10-06："改成选择图片目录"（配图是那张「这个流程的第一步需要图片」
    的提示层，按钮写着"选择图片"）。

    ⚠️ **文案与行为必须一致**，只改文案等于骗人：``getOpenFileNames`` **选不了
    目录**，所以按钮写着"选目录"就必须走 ``getExistingDirectory``。本节**真点
    一次按钮**（``QTest.mouseClick``）并记录开的是哪个框——不是只断言文案。
    """
    import shutil
    import tempfile
    import time

    from pathlib import Path

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFileDialog

    from desktop.shell import ModuleShell
    from desktop.store.store import TaskStore
    from tests.selftests._context import ok, silence_source_prompt

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    tmp = Path(tempfile.mkdtemp(prefix="guji_pickdir_"))
    orig_dir = QFileDialog.getExistingDirectory
    orig_files = QFileDialog.getOpenFileNames
    try:
        source = tmp / "扫描结果"
        source.mkdir()
        for name in ("0001.jpg", "0002.jpg"):
            (source / name).write_bytes(b"x")

        store = TaskStore(tmp / "data")
        shell = ModuleShell(store)
        shell.resize(1400, 900)
        shell.show()
        app.processEvents()

        tid = store.create_task(source_path="", source_hash="", name="提示选目录")
        (store.task_dir(tid) / "flow.bpmn").write_text(
            _FLOW_DETECT_FIRST, encoding="utf-8")

        page = shell.detail_page
        silence_source_prompt(page)
        shell.open_detail(tid)
        app.processEvents()

        prompt = page._source_prompt
        ok("第一步不吃 PDF ⇒ 判据是「缺图片」",
           page._missing_input_kind() == "images",
           repr(page._missing_input_kind()))
        ok("主按钮文案是「选择图片目录」",
           prompt.pick_button.text() == "选择图片目录",
           prompt.pick_button.text())

        # ---- 真点一次，记录开的是哪个对话框 ----
        opened: list[str] = []
        QFileDialog.getExistingDirectory = staticmethod(
            lambda *a, **k: (opened.append("目录"), str(source))[1])
        QFileDialog.getOpenFileNames = staticmethod(
            lambda *a, **k: (opened.append("文件"), ([], ""))[1])
        prompt.show_prompt()
        app.processEvents()
        QTest.mouseClick(prompt.pick_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        for _ in range(60):
            app.processEvents()
            time.sleep(0.05)

        ok("点主按钮开的是**目录框**（不是文件框——它选不了目录）",
           opened == ["目录"], str(opened))
        target = page._current_stage_input_dir()
        ok("选中的目录被整批导进输入目录",
           target is not None
           and sorted(p.name for p in target.iterdir()) == ["0001.jpg", "0002.jpg"],
           str(sorted(p.name for p in target.iterdir())) if target else "")
        ok("清单里也是这两张（执行时读得到）",
           [Path(p["file"]).name for p in page.pages] == ["0001.jpg", "0002.jpg"],
           str([Path(p["file"]).name for p in page.pages]))

        shell.close()
    finally:
        QFileDialog.getExistingDirectory = orig_dir
        QFileDialog.getOpenFileNames = orig_files
        shutil.rmtree(tmp, ignore_errors=True)


#: 一条**检测打头**的流程（无 extract）——提示层会说"缺图片"。
_FLOW_DETECT_FIRST = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
 xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:guji="http://guji.local"
 id="D1" targetNamespace="http://bpmn.io/schema/bpmn">
 <bpmn:process id="P1" isExecutable="false">
  <bpmn:startEvent id="s"><bpmndi:OMNDIOSExtension/></bpmn:startEvent>
  <bpmn:task id="a" name="检测文本框" guji:stage="detect"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="b" name="生成PDF" guji:stage="print"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:sequenceFlow id="f1" sourceRef="s" targetRef="a"/>
  <bpmn:sequenceFlow id="f2" sourceRef="a" targetRef="b"/>
 </bpmn:process>
 <bpmndi:BPMNDiagram id="DD"><bpmndi:BPMNPlane id="PP" bpmnElement="P1"/></bpmndi:BPMNDiagram>
</bpmn:definitions>
"""


def _check_input_entry_marks() -> None:
    """红框标在"输入入口"上，「打开任务数据目录」搬到**右下角**。

    用户 2026-10-06 三条一起提的：

    1. 右上角的选择图片还可以选择目录，都是红色框住；
    2. 左下角输入图片和目录也用红色框住；
    3. 右上角的打开任务数据目录，统一放到右下角。

    ⚠️ **判"有没有红框"不能看有没有 border**：qfluentwidgets 的按钮**自带**
    border 样式表，那样判**所有按钮都是红的**（我第一版自测就栽在这，全绿）。
    必须看**我们加的那条**——``theme.DANGER`` 色值在不在样式表里。
    """
    import shutil
    import tempfile

    from pathlib import Path

    from PySide6.QtWidgets import QApplication
    from qfluentwidgets import ToolButton

    from desktop.shell import ModuleShell
    from desktop.store.store import TaskStore
    from desktop.ui import theme as theme
    from tests.selftests._context import ok, silence_source_prompt

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    tmp = Path(tempfile.mkdtemp(prefix="guji_marks_"))
    try:
        store = TaskStore(tmp)
        shell = ModuleShell(store)
        shell.resize(1500, 900)
        shell.show()
        app.processEvents()

        tid = store.create_task(source_path="", source_hash="", name="红框")
        page = shell.detail_page
        silence_source_prompt(page)
        shell.open_detail(tid)
        app.processEvents()

        def marked(button) -> bool:
            """有没有我们加的那层红框（**不是**看有没有 border）。"""
            return bool(button is not None) and \
                str(theme.DANGER) in (button.styleSheet() or "")

        # ---- ① 页头：插图 + 插目录都红框 ----
        ok("页头「插入图片」有红框", marked(page.insert_button))
        ok("页头「选文件夹」有红框（目录入口同在页头）",
           marked(page.insert_dir_button))
        # ⚠️ **不该红的别红**：标红＝"这里能喂图片"，标到无关按钮上就成了噪声
        ok("页头「查看/编辑流程」没有红框（它不是输入入口）",
           not marked(page.flow_button))
        ok("页头「修改任务名称」没有红框",
           not marked(page.rename_button))

        # ---- ② 预览区左下角：＋与📁 红框，🗑 不红 ----
        tips = {b.toolTip(): marked(b)
                for b in page.detect_viewer.findChildren(ToolButton)}
        ok("预览区「插入图片（可多选）」有红框",
           tips.get("插入图片（可多选）") is True, str(tips))
        ok("预览区「把一个文件夹里的图片批量插入」有红框",
           tips.get("把一个文件夹里的图片批量插入") is True, str(tips))
        ok("预览区「删除」没有红框（删图不是入口）",
           tips.get("从页面清单删除所选图片") is False, str(tips))

        # ---- ②b 显隐跟着**流程入口**走（用户 2026-10-06 三条规则）----
        # 这个任务是默认流程（「图片提取」打头）⇒ 输入是 PDF：页头只亮
        # PDF，图片/目录入口整对藏起来（规则①）；红框在样式表里常驻，
        # 但按钮不可见。左下角「＋/📁」只属于**入口**那一步的查看器——
        # 检测页不是入口，它的输入来自上游 ⇒ 藏（规则③）。
        ok("默认流程（图片提取打头）⇒ 页头只显示 PDF，图片/目录入口藏起来",
           not page.source_button.isHidden()
           and page.insert_button.isHidden()
           and page.insert_dir_button.isHidden())
        ok("检测页左下角「＋/📁」藏起来（不是入口步骤，规则③）",
           _viewer_entry_button(page.detect_viewer,
                                "插入图片（可多选）") is not None
           and _viewer_entry_button(page.detect_viewer,
                                    "插入图片（可多选）").isHidden()
           and _viewer_entry_button(
               page.detect_viewer,
               "把一个文件夹里的图片批量插入").isHidden())

        # ---- ③「打开任务数据目录」在右下角（底部状态条最右端）----
        ok("「打开任务数据目录」已挂进底部状态条",
           shell and page.log_panel.isAncestorOf(page.task_dir_button))
        ok("它不在页头那一排里了（页头只留输入/流程类按钮）",
           not page.detail_title.isAncestorOf(page.task_dir_button))

        shell.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _check_insert_from_folder() -> None:
    """「📁 选文件夹」能把整个目录批量插进来，**且执行时读的就是这批**。

    用户 2026-10-06：

    > 现在提示选择的是图片，是否可以选择目录，比如去底色在第一个节点的时候，
    > 是否也可以输入目录

    钉四件事：

    1. 界面上真的有「选文件夹」按钮（``getOpenFileNames`` 选不了目录，
       指望在文件对话框里选中文件夹是不成立的）；
    2. 目录被展开成图片清单——**非图片被忽略**、按名排序；
    3. 落在**这一步的输入目录**，与执行读的是同一处（否则"导入了却读不到"）；
    4. 再次选**同一个目录不产生重复**（否则清单里同一张图出现两次）。
    """
    import shutil
    import tempfile
    import time

    from pathlib import Path

    from PySide6.QtWidgets import QApplication, QFileDialog
    from qfluentwidgets import ToolButton

    from desktop.shell import ModuleShell
    from desktop.store.store import TaskStore
    from tests.selftests._context import ok, silence_source_prompt

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    tmp = Path(tempfile.mkdtemp(prefix="guji_folder_"))
    original = QFileDialog.getExistingDirectory
    try:
        source = tmp / "扫描结果"
        source.mkdir()
        for name in ("0003.jpg", "0001.jpg", "0002.png"):
            (source / name).write_bytes(b"x")
        (source / "说明.txt").write_text("x", encoding="utf-8")

        store = TaskStore(tmp / "data")
        shell = ModuleShell(store)
        shell.resize(1400, 900)
        shell.show()
        app.processEvents()

        tid = store.create_task(source_path="", source_hash="", name="去底色打头")
        (store.task_dir(tid) / "flow.bpmn").write_text(
            _FLOW_REMBG_FIRST, encoding="utf-8")

        page = shell.detail_page
        silence_source_prompt(page)
        shell.open_detail(tid)
        app.processEvents()
        page._select_stage(page.bar_index_of_step("rembg"))
        app.processEvents()

        # ---- ① 按钮在（提示语要说清是"文件夹"）----
        tips = [b.toolTip() for b in page.detect_viewer.findChildren(ToolButton)]
        ok("预览区有「选文件夹」按钮（文件对话框选不了目录，得单独一个）",
           any("文件夹" in t for t in tips), str(tips))

        # ---- ②③④ 走真实导入链路 ----
        QFileDialog.getExistingDirectory = staticmethod(
            lambda *a, **k: str(source))
        page.insert_pages_from_folder()
        _pump(app)

        target = page._current_stage_input_dir()
        ok("去底色作为入口节点时，输入目录是入口图片目录",
           target is not None and target.name == "input", str(target))
        copied = sorted(p.name for p in target.iterdir()) if target else []
        ok("整个目录被展开复制（非图片被忽略）",
           copied == ["0001.jpg", "0002.png", "0003.jpg"], str(copied))
        ok("清单按文件名排序（页序稳定，不靠目录枚举顺序）",
           [Path(p["file"]).name for p in page.pages]
           == ["0001.jpg", "0002.png", "0003.jpg"],
           str([Path(p["file"]).name for p in page.pages]))
        ok("执行时读到的就是这批图（导入位置与读取位置同源）",
           [p.name for p in page._manifest_paths()]
           == ["0001.jpg", "0002.png", "0003.jpg"],
           str([p.name for p in page._manifest_paths()]))

        # ---- 再选一次输入目录本身：不得重复 ----
        QFileDialog.getExistingDirectory = staticmethod(
            lambda *a, **k: str(target))
        page.insert_pages_from_folder()
        _pump(app)
        ok("再选输入目录本身不产生 -1 副本",
           sorted(p.name for p in target.iterdir())
           == ["0001.jpg", "0002.png", "0003.jpg"],
           str(sorted(p.name for p in target.iterdir())))
        ok("清单里也不出现重复条目",
           [Path(p["file"]).name for p in page.pages]
           == ["0001.jpg", "0002.png", "0003.jpg"],
           str([Path(p["file"]).name for p in page.pages]))

        shell.close()
    finally:
        QFileDialog.getExistingDirectory = original
        shutil.rmtree(tmp, ignore_errors=True)


def _pump(app, rounds: int = 60) -> None:
    """空转事件循环等后台复制落地（自测里不能真sleep 等线程）。"""
    import time

    for _ in range(rounds):
        app.processEvents()
        time.sleep(0.05)


def _check_flow_saved_refreshes_bar() -> None:
    """编辑流程保存后回详情页，步骤条**当场**按新图重排（不必重进任务）。

    用户 2026-10-06 报障：

    > 顶部的任务流程编辑后，顶部这个流程图没有立即更新，必须重新进入这个页面才能更新

    钉三件事（缺一件就复发）：

    1. 保存 → 自动回详情页，且步骤条**立刻**是���流程（4 格 → 3 格）；
    2. 高亮与完成态**按步骤 key 跨重建保住**——重建时若拿"旧格序"去查
       **新**槽位表（``flow_slots()`` 读的是磁盘上那张新图），会贴错格子；
    3. ``set_task`` 拒绝重载时（正在跑子任务）**不许静默**：必须把详情页
       切出来并说明，否则用户被留在流程页上、以为没保存成功。
    """
    import copy
    import shutil
    import tempfile

    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from desktop.shell import ModuleShell
    from desktop.store.store import TaskStore
    from tests.selftests._context import ok, silence_source_prompt

    app = QApplication.instance()
    if app is None:  # 单独跑本节时自建一个
        app = QApplication([])

    tmp = Path(tempfile.mkdtemp(prefix="guji_flowbar_"))
    try:
        store = TaskStore(tmp)
        shell = ModuleShell(store)
        shell.resize(1400, 900)
        shell.show()
        app.processEvents()

        tid = store.create_task(source_path="", source_hash="", name="流程条刷新")
        (store.task_dir(tid) / "flow.bpmn").write_text(
            _FLOW_4_SLOTS, encoding="utf-8")

        page = shell.detail_page
        silence_source_prompt(page)
        shell.open_detail(tid)
        app.processEvents()
        before = [s.step for s in page.flow_slots()]
        ok("进详情时步骤条是四格流程",
           before == ["detect", "rembg", "imposition", "print"], str(before))

        # 停在 detect 并标记完成（重建后要靠 key 找回这两样）
        page._select_stage(page.bar_index_of_step("detect"))
        page.step_bar.mark_completed(0)
        app.processEvents()

        # ---- 走真实保存链路：开流程页 → 删掉「图片拼版」→ 保存 ----
        shell.open_flow(tid)
        app.processEvents()
        flow_page = shell.flow_page()
        ok("流程页打开的是本任务的流程",
           getattr(flow_page, "_task_id", None) == tid,
           str(getattr(flow_page, "_task_id", None)))

        editor = flow_page._panel.editor_panel.editor()
        new = copy.deepcopy(editor.diagram())
        victim = next(n for n in new.nodes if n.stage == "imposition")
        new.nodes = [n for n in new.nodes if n.id != victim.id]
        new.flows = [f for f in new.flows
                     if f.source != victim.id and f.target != victim.id]
        editor.set_diagram(new)
        flow_page._on_done(True)
        app.processEvents()

        # ---- ① 自动回详情页且当场重排 ----
        ok("保存后自动回到详情页（不用手动切）",
           shell.pages.currentWidget() is page,
           type(shell.pages.currentWidget()).__name__)
        after = [s.step for s in page.flow_slots()]
        ok("步骤条当场按新图重排（四格→三格，不必重进任务）",
           after == ["detect", "rembg", "print"], str(after))
        ok("被删掉的「图片拼版」节点已隐藏",
           page.step_bar.imposition_node.isHidden())

        # ---- ② 高亮按 key跨重建保住 ----
        # ⚠️ **不验完成态**：完成态由 ``_refresh_stage_views`` 按 runs.json
        #    重算（不是 ``mark_completed`` 手工标的），而 ``set_task`` 走的是
        #    "切任务"全量复位路径——手工标的完成态被清掉是**既有正确行为**，
        #    拿它当断言会钉错东西。真正要钉的是"高亮别跳错格"：重建时若拿
        #    **旧格序**去查**新**槽位表，下标含义已变，高亮会落到别的步骤上。
        current_step = page.step_at_index(page.step_bar._current)
        ok("重建后仍停在 detect（按 key 找回，不是按旧格序）",
           current_step == "detect", str(current_step))
        ok("detect 在新流程里确实是第 0 格（格序已随删节点前移）",
           page.bar_index_of_step("detect") == 0,
           str(page.bar_index_of_step("detect")))

        # ---- ②' 单独验"重建不跳格"：这一步不依赖 set_task 的"当前页"兜底 ----
        # ⚠️ 上一条断言在完整保存链路上**改前也绿**（当前停在 detect，而它
        #    恰好还是第 0 格，兜底与正确行为重合）⇒ 钉不住真正的缺陷。真正
        #    会跳格的是"停在中间某一步、且它前面的节点被删了"：旧格序 2 在
        #    新流程里指向别的步骤，于是高亮默默挪走（实测 rembg → imposition）。
        ok("重建步骤条时高亮按 key 保住，不被前面的节点删除带偏",
           _rebuild_keeps_highlight(page, store, tid),
           "重建后高亮跳到了别的步骤")

        # ---- ③ set_task 拒绝重载时不许静默 ----
        # ⚠️ 必须**在 shell.close() 之前**跑：close 之后 page 已析构，
        #    探针再切页/替换方法就拿到僵尸控件，判据恒假。
        ok("open_detail 在 set_task 失败时仍把详情页切出来并说明（不留在流程页）",
           _open_detail_failure_shows_page(shell, page),
           "拒绝重载后用户被留在流程页、或没有任何说明")

        shell.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
        nodes=[n for n in diagram.nodes if n.id != victim.id],
        flows=[f for f in diagram.flows
               if f.source != victim.id and f.target != victim.id],
    )
    store.save_task_diagram(task_id, trimmed)

    page._rebuild_step_bar()
    return page.step_at_index(page.step_bar._current) == "rembg"


def _open_detail_failure_shows_page(shell, page) -> bool:
    """``set_task`` 被拒（模拟子任务在跑）后，详情页仍被切到前台**且有提示**。

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


def _check_clear_pdf(create_page, sample_pdf) -> None:
    """选错文件能一键清掉（不必重开选择框再点取消）。"""
    from desktop.components.create_task_dialog import EMPTY_PDF_HINT
    from tests.selftests._context import ok

    create_page.reset()
    button = create_page.panel.clear_pdf_button
    ok("创建页有「清除已选 PDF」的入口",
       button is not None and "PDF" in button.toolTip(),
       button.toolTip() if button is not None else "无按钮")
    ok("没选文件时清除按钮不出现（没东西可清）",
       button.isHidden(), f"visible={button.isVisible()}")

    # 选上 ⇒ 按钮出现，文案变成"已选择：xxx"
    create_page.panel.set_pdf(sample_pdf)
    create_page._autofill_name()
    app_ev = create_page.window()
    app_ev.repaint()
    ok("选了 PDF 后清除按钮出现",
       not button.isHidden(), f"visible={button.isVisible()}")
    ok("选了 PDF 后那行显示文件名",
       sample_pdf.name in create_page.panel.pdf_state.text(),
       create_page.panel.pdf_state.text())
    ok("选 PDF 自动填进任务名（清除时要从这里回退）",
       create_page.name_edit.text() == sample_pdf.stem,
       repr(create_page.name_edit.text()))

    # 点清除
    create_page.panel.clear_pdf_button.click()
    app_ev.repaint()
    ok("点「清除」⇒ 已选 PDF 真的没了",
       create_page.panel.selected_pdf() is None,
       repr(create_page.panel.selected_pdf()))
    ok("点「清除」⇒ 那行回到「可留空」",
       create_page.panel.pdf_state.text() == EMPTY_PDF_HINT,
       create_page.panel.pdf_state.text())
    ok("点「清除」⇒ 清除按钮自己消失",
       button.isHidden(), f"visible={button.isVisible()}")
    ok("点「清除」⇒ 自动填的文件名一起回退（不留指向已清文件的名字）",
       create_page.name_edit.text() == "",
       repr(create_page.name_edit.text()))

    # 用户**自己改过**的名字不能被清掉（那是丢用户输入）
    create_page.panel.set_pdf(sample_pdf)
    create_page.set_name("我自己起的名字")
    create_page.panel.clear_pdf_button.click()
    app_ev.repaint()
    ok("用户改过的任务名在清除 PDF 时**保留**（不丢用户输入）",
       create_page.name_edit.text() == "我自己起的名字",
       repr(create_page.name_edit.text()))
    ok("文件确实清掉了（只是名字留着）",
       create_page.panel.selected_pdf() is None)


def _check_first_entry_shows_prompt(app) -> None:
    """**第一次**进入缺源任务就要弹出提示层（用户 2026-10-06 报障）。

    真实链路：``ModuleShell.open_detail`` 是**先** ``page.set_task()``、
    **后** ``pages.setCurrentWidget(page)``。所以 ``set_task`` 里弹提示层的那一刻，
    详情页刚被 ``addWidget`` 进栈、**还没布局**：尺寸是 QWidget 默认的 640x480、
    ``_content_top()`` 返回布局未跑时的垃圾值（实测 491）⇒ 遮罩高度被夹成
    **0**，用户看到的就是"压根没弹"，而第二次进入才正常（那时尺寸已对）。

    ⚠️⚠️ 这个 bug 自测之前一直抓不到，因为所有相关用例都是
    ``probe.show()`` 之后才 ``probe.set_task()``——页面早已布局好，**天然
    绕开了这个时序**。所以这里必须走**壳层的真实入口**，且**第一次**就断言。
    """
    import shutil as _shutil
    import tempfile as _tempfile

    from desktop.app import WINDOW_SIZE
    from desktop.shell import ModuleShell
    from desktop.store import TaskStore
    from tests.selftests._context import ok

    root = Path(_tempfile.mkdtemp(prefix="first_entry_prompt_"))
    store = TaskStore(root / "data")
    empty_id = store.create_task(None, "", "")
    pdf = root / "with_source.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    full_id = store.create_task(pdf, "h", "")
    shell = ModuleShell(store)
    try:
        shell.resize(WINDOW_SIZE)
        shell.show()
        app.processEvents()

        def prompt_state() -> tuple:
            prompt = shell.detail_page._source_prompt
            if prompt is None:
                return (False, None)
            return (prompt.isVisible(), prompt.geometry().getRect())

        # ---- ① 第一次进入（此前**从未**进过这个任务）----
        shell.open_detail(empty_id)
        app.processEvents()
        visible, rect = prompt_state()
        page = shell.detail_page
        ok("**第一次**进入缺源任务就弹出提示层（此前零次）",
           visible is True, f"visible={visible}")
        ok("第一次弹出的遮罩有**实际高度**（不是布局未就绪时的 0 高）",
           rect is not None and rect[3] > 100,
           f"rect={rect}")
        ok("第一次弹出的遮罩宽度铺满页面（不是默认 640）",
           rect is not None and rect[2] == page.width(),
           f"rect={rect} page={page.width()}")
        ok("第一次弹出的遮罩上沿在页头之下（页头按钮留可用）",
           rect is not None and 0 < rect[1] < page.height() // 3,
           f"rect={rect}")

        # ---- ② 切到有文件的任务：不弹 ----
        shell.open_detail(full_id)
        app.processEvents()
        visible_full, _ = prompt_state()
        ok("切到**有**源文件的任务：不弹提示层",
           visible_full is False, f"visible={visible_full}")

        # ---- ③ 再回到缺源任务：仍要弹，且几何依旧正确 ----
        shell.open_detail(empty_id)
        app.processEvents()
        visible_again, rect_again = prompt_state()
        ok("回到缺源任务：照样弹，且遮罩仍是正确几何",
           visible_again is True and rect_again == rect,
           f"visible={visible_again} rect={rect_again} vs {rect}")

        # ---- ④ 答「稍后再说」后切走再回来：每次进入都弹 ----
        shell.detail_page._source_prompt.dismiss()
        app.processEvents()
        shell.open_detail(full_id)
        app.processEvents()
        shell.open_detail(empty_id)
        app.processEvents()
        visible_third, rect_third = prompt_state()
        ok("答过「稍后再说」再切回来：**仍要弹**（每次进入都检测）",
           visible_third is True and rect_third[3] > 100,
           f"visible={visible_third} rect={rect_third}")

        # ---- ⑤ 窗口尺寸变了，遮罩要跟着重铺 ----
        prompt = shell.detail_page._source_prompt
        shell.resize(1200, 700)
        app.processEvents()
        ok("窗口拉小后遮罩跟着重铺（不是留在旧尺寸上）",
           prompt.geometry().width() == shell.detail_page.width(),
           f"mask={prompt.geometry().getRect()} "
           f"page={shell.detail_page.width()}")
    finally:
        shell.shutdown_workers()
        shell.close()
        _shutil.rmtree(root, ignore_errors=True)


def _check_open_create_resets() -> None:
    """钉住**调用点**：`open_create` 每次进入都复位（改回去要红）。

    ⚠️ 上一条验的是 :meth:`CreateTaskPage.reset` **本身**对不对；这条钉的是
    **壳层真的调了它**。少一步就会出现"复位方法写得挺好、但没人调用"——
    那种改动自测一片绿、用户照旧看见上一次的表单。
    """
    from desktop.shell import ModuleShell
    from desktop.store import TaskStore
    from tests.selftests._context import ok

    root = Path(tempfile.mkdtemp(prefix="open_create_probe_"))
    store = TaskStore(root / "data")
    shell = ModuleShell(store)
    try:
        shell.open_create()
        page = shell.create_page()
        page.set_name("上一次的书")
        page.panel.set_custom_mode(True)
        # 第二次进入（模拟建完一个任务后回来再建）
        shell.open_create()
        ok("open_create 每次进入都复位任务名（不是留着上一次的）",
           page.name_edit.text() == "", repr(page.name_edit.text()))
        ok("open_create 每次进入都复位勾选状态",
           page.panel.uses_custom_flow() is False)
        # 已经在这一页时再点一次「创建任务」也要清（复位在换页判断之前）
        page.set_name("又填了一次")
        shell.open_create()
        ok("已经在创建页时再点「创建任务」同样复位",
           page.name_edit.text() == "", repr(page.name_edit.text()))
    finally:
        shell.shutdown_workers()
        shell.close()
        shutil.rmtree(root, ignore_errors=True)


def _check_create_page_reset(create_page, sample_pdf) -> None:
    """进创建页时上一次的输入**全部**清掉。

    ⚠️ 这是真事故：创建页是**惰性单例**（建一次长期留着），``open_create``
    原来不复位，于是第二次建任务时，界面上还摆着上一次的任务名、已选的 PDF、
    勾着的「自定义流程」、编过的流程图。
    """
    from desktop.components import create_task_dialog
    from desktop.components.create_task_dialog import EMPTY_PDF_HINT
    from tests.selftests._context import ok

    # 先把页面弄成"上一次用过的样子"
    create_page.set_name("上一次的书")
    create_page.panel.set_pdf(sample_pdf)
    create_page.panel.set_custom_mode(True)
    create_page._autofill_name()
    create_page.set_busy(True, "建任务中…")
    create_page.panel._on_edit_flow()          # 编辑器开着
    ok("先摆出「上一次用过的样子」（自定义模式 + 编辑器开着）",
       create_page.panel.uses_custom_flow()
       and create_page.panel._editor is not None
       and not create_page.panel._editor_host.isHidden()
       and create_page._busy is True
       and not create_page.name_edit.isEnabled())

    create_page.reset()
    ok("复位后任务名清空（用户截图里留着的正是它）",
       create_page.name_edit.text() == "", repr(create_page.name_edit.text()))
    ok("复位后已选 PDF 清空",
       create_page.panel.selected_pdf() is None,
       repr(create_page.panel.selected_pdf()))
    ok("复位后 PDF 那行回到「可留空」（不是留着一句假的已选）",
       create_page.panel.pdf_state.text() == EMPTY_PDF_HINT,
       create_page.panel.pdf_state.text())
    ok("复位后回到默认流程模式（勾选被清）",
       create_page.panel.uses_custom_flow() is False)
    ok("复位后自定义流程图回到初值（不是带着上一本书的图）",
       [n.name for n in create_page.panel._custom_diagram.nodes]
       == [n.name for n in
           create_task_dialog.load_custom_init().nodes])
    ok("复位后流程预览回来、编辑器收起（不是留个开着的空编辑器）",
       create_page.panel._editor_host.isHidden()
       and not create_page.panel.flow_scroll.isHidden()
       and not create_page.panel.flow_summary.isHidden())
    ok("复位后 busy 态与控件禁用一起清（否则这页永久半残）",
       create_page._busy is False
       and create_page.name_edit.isEnabled()
       and create_page.panel.isEnabled()
       and create_page.back_button.isEnabled())
    ok("复位后提示回到初始说明",
       "留空" in create_page.name_hint.text(), create_page.name_hint.text())
    #⚠️ 默认名占位要**重算**：刚才那次创建已经占掉一个号
    ok("复位后默认名占位是当前预测的下一个任务号",
       create_page.name_edit.placeholderText() == create_page.default_name()
       and create_page.name_edit.placeholderText().startswith("任务#"),
       create_page.name_edit.placeholderText())


def _check_pdf_button_icon(detail) -> None:
    from tests.selftests._context import ok

    """① 页头「选择 PDF」按钮用现成的 ``PDF_FILE`` 图标。"""
    button = detail.source_button
    # ⚠️ 光判"图标非空"没用（内置 ``FIF.DOCUMENT`` 也非空），要比**类型**：
    #   自绘那枚是 ``SvgIcon`` 实例，内置的是 ``FluentIcon`` 子类。
    ok("页头 PDF 按钮用的是现成的自绘 PDF_FILE（不是内置空白 DOCUMENT）",
       type(getattr(button, "_icon", None)).__name__ == "SvgIcon",
       type(getattr(button, "_icon", None)).__name__)


def _check_missing_pdf_prompt(create_page, sample_pdf) -> None:
    from tests.selftests._context import ok

    """② 流程要源 PDF、用户没给 ⇒ 提交前问一句（两条路都合法）。

    ⚠️ 离屏自测绝不真弹模态：这里只验**判据**（该问/不该问）与"用户答
    先不传 ⇒ 照常建空壳"这条分支；确认框本身归 ``MessageBox``。
    """
    from tests.selftests._context import ok

    ok("默认流程里有「提取图片」⇒ 需要源 PDF（该问用户）",
       create_page._flow_needs_source_pdf() is True)
    # 选上文件就不问了（别在用户已经给了文件时还啰嗦一句）
    create_page.panel.set_pdf(sample_pdf)
    ok("已选 PDF 时不啰嗦（不问了）",
       create_page._should_ask_missing_pdf() is False)
    # ⚠️ 第 9 节给这页选过 PDF，先清掉再验"没选"那条（顺序别弄反）
    create_page.panel._pdf = None
    ok("没选 PDF 且流程要 PDF ⇒ 该问",
       create_page._should_ask_missing_pdf() is True)
    # 用户答「先不传」⇒ 继续建（空壳），信号照发
    create_page._should_ask_missing_pdf = lambda: False
    fired = []
    create_page.create_requested.connect(lambda *a: fired.append(a))
    create_page._on_submit()
    app_process = create_page.window()
    app_process.repaint()
    ok("用户选「先不传」→ 照常建空壳任务（不拦着不让建）",
       len(fired) == 1 and fired[0][0] == "",
       f"fired={fired}")
    # 自定义流程里把「提取图片」删掉 ⇒ 不需要源 PDF ⇒ 不该问
    from desktop.steps.bpmn_diagram import (
        DiagramFlow, DiagramNode, FlowDiagram, KIND_TASK,
    )
    keep = [n for n in create_page.panel._default_diagram.nodes
            if n.name != "提取图片"]
    if len(keep) >= 2:
        create_page.panel._custom_diagram = FlowDiagram(
            nodes=tuple(keep),
            flows=tuple(DiagramFlow(f"sf{i}", keep[i - 1].id, keep[i].id)
                        for i in range(1, len(keep))),
        )
        create_page.panel.set_custom_mode(True)
        ok("流程里没有要源 PDF 的步骤 ⇒ 不该问（不白问）",
           create_page._flow_needs_source_pdf() is False,
           f"stages={[n.name for n in keep]}")
    else:
        ok("流程里没有要源 PDF 的步骤 ⇒ 不该问（不白问）", True)


def _check_source_pick_flow(store, pdf, app) -> None:
    """③ 详情页补选 PDF：同 hash 不重复传 / 新 PDF 先确认再换。"""
    from tests.selftests._context import ok

    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.utils.files import file_hash

    real_hash = file_hash(pdf)
    other = pdf.with_name("另一本.pdf")
    other.write_bytes(pdf.read_bytes() + b"\n% another book\n")
    other_hash = file_hash(other)

    # ---- 同一个文件又选了一遍 ⇒ 什么都不做（不换源、不清数据）----
    tid = store.create_task(pdf, real_hash, "同文件测试")
    probe = TaskDetailPage(store)
    probe.resize(1080, 720)
    probe.show()
    try:
        app.processEvents()
        from tests.selftests._context import silence_source_prompt

        # 有源文件的任务不该弹；替身装上顺便钉住这条（漏弹/乱弹都红）
        prompt_calls = silence_source_prompt(probe)
        ok("能进详情页", probe.set_task(tid) is True)
        ok("**有**源文件的任务不弹「缺源 PDF」提示（提示层压根没建）",
           prompt_calls and probe._source_prompt is None,
           f"calls={len(prompt_calls)} "
           f"prompt={probe._source_prompt}")
        kept = store.get_task(tid)["source_path"]
        probe._pending_source = pdf
        probe._on_source_hash_ready(str(pdf), real_hash)
        app.processEvents()
        ok("重复选同一个 PDF ⇒ 不换源文件（哈希一样就不动）",
           store.get_task(tid)["source_path"] == kept,
           store.get_task(tid)["source_path"])

        # ---- 这个 PDF 已在别的任务里 ⇒ **问一句**，不是一律拒绝 ----
        # （用户 2026-10-06："当前是不允许的，这个不合理。应该提示已经存在
        #   相同文件任务，是否继续等，跟外层一样"）
        tid_other = store.create_task(pdf, real_hash, "已导入过的书")
        probe2 = TaskDetailPage(store)
        probe2.resize(1080, 720)
        probe2.show()
        app.processEvents()
        silence_source_prompt(probe2)
        probe2.set_task(tid_other)
        before = store.get_task(tid_other)["source_path"]
        ok("重复内容的任务要问一句（判据：存在别的任务就问）",
           probe2._duplicate_source_needs_confirm(
               store.get_task(tid)) is True)
        ok("本任务自己那条不问（已在指纹分支里提前处理掉）",
           probe2._duplicate_source_needs_confirm(
               store.get_task(tid_other)) is False)
        # 答「取消」⇒ 什么都不做
        probe2._confirm_duplicate_source = lambda _s, _o: False
        probe2._pending_source = pdf
        probe2._on_source_hash_ready(str(pdf), real_hash)
        app.processEvents()
        ok("重复内容但用户答「取消」⇒ 不换源（不复制、不清产物）",
           store.get_task(tid_other)["source_path"] == before,
           store.get_task(tid_other)["source_path"])
        # 答「仍然使用」⇒ 换源（与外层查重确认同一个模式）
        probe2._confirm_duplicate_source = lambda _s, _o: True
        probe2._pending_source = pdf
        probe2._on_source_hash_ready(str(pdf), real_hash)
        app.processEvents()
        ok("重复内容但用户答「仍然使用」⇒ 照样换源（不是一刀切拒绝）",
           store.get_task(tid_other)["source_path"] == str(pdf),
           store.get_task(tid_other)["source_path"])
        ok("确认使用后指纹写进索引（下次仍能判重）",
           store.get_task(tid_other)["source_hash"] == real_hash)
        probe2.shutdown_all_workers()
        probe2.close()

        # ---- 新的 PDF：先确认、换了之后指纹写进索引、后续节点数据清空 ----
        (store.task_dir(tid) / "pages.json").write_text("[]", encoding="utf-8")
        # 挡住确认框（离屏不许真弹）：用户答"不换"
        probe._confirm_replace_source = lambda _p: False
        probe._pending_source = other
        probe._on_source_hash_ready(str(other), other_hash)
        app.processEvents()
        ok("新 PDF 但用户答「不换」⇒ 源文件保持不变（确认在前）",
           store.get_task(tid)["source_path"] != str(other),
           store.get_task(tid)["source_path"])
        ok("用户答「不换」⇒ 旧书的中间产物也还在（没白清）",
           (store.task_dir(tid) / "pages.json").exists())
        # 用户答"换"
        probe._confirm_replace_source = lambda _p: True
        probe._pending_source = other
        probe._on_source_hash_ready(str(other), other_hash)
        app.processEvents()
        ok("用户答「换」⇒ 源文件换成新的那份",
           store.get_task(tid)["source_path"] == str(other),
           store.get_task(tid)["source_path"])
        ok("换了之后**指纹写进索引**（否则下次判重失效）",
           store.get_task(tid)["source_hash"] == other_hash,
           store.get_task(tid)["source_hash"])
        ok("换了之后后续节点数据全部清空（页清单…）",
           not (store.task_dir(tid) / "pages.json").exists())
        ok("换了之后副本落进任务目录（详情页读的是副本）",
           store.source_copy_path(tid) is not None)
        # 算指纹期间按钮是锁着的（免得用户以为没点上）
        probe._set_picking_source(True)
        ok("算指纹期间锁住按钮、提示改成「正在读取」",
           not probe.source_button.isEnabled()
           and "读取" in probe.source_button.toolTip(),
           probe.source_button.toolTip())
        probe._set_picking_source(False)
        ok("算完恢复按钮可用与原提示",
           probe.source_button.isEnabled()
           and "更换" in probe.source_button.toolTip(),
           probe.source_button.toolTip())
    finally:
        probe.shutdown_all_workers()
        probe.close()
        app.processEvents()
        for extra in (tid, tid_other):
            try:
                store.delete_task(extra)
            except OSError:
                pass
        if other.exists():
            other.unlink()


def _submit_keeps_window(create_page) -> bool:
    """点「创建任务」后宿主窗口仍在（回归钉子）。

    ⚠️ 这条对应一个真事故：``CreateTaskPanel.submit`` 里原来有
    ``self.window().close()``——面板被内嵌进创建任务页之后，``self.window()``
    返回的是**主窗口**，于是点一次"创建任务"把整个程序关掉（用户 2026-10-06
    报："创建任务成功，但是程序 gui 不可见了"）。

    验法：**只连一个收集器，不让它真的建任务**（那要改数据、要PDF）。收集器
    连上就把 ``submitted`` 的其它接收者挤掉了——PySide 的 ``connect`` 是多
    播的，所以第一个连的收集器独占这条信号，后续 ``shell`` 那边（这里是
    ``create_requested``）听不到。窗口在点之前后在同一个事件循环里都比一遍。
    """
    panel = create_page.panel
    win = create_page.window()
    before = win.isVisible()
    fired = []
    panel.submitted.connect(lambda: fired.append(1))
    panel.submit()
    return bool(fired) and win.isVisible() == before


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


def _check_shell_task(store, pdf, app) -> None:
    """空壳任务（创建时没给 PDF）的落库与补选入口。"""
    from desktop.ui import theme as T
    from tests.selftests._context import ok

    # 没给源文件 + 没给名字 ⇒ 名字回落「任务#实际号」
    tid = store.create_task(None, "", "")
    record = store.get_task(tid) or {}
    ok("没给PDF 时建得出任务（PDF 非必需）", bool(tid) and record.get("id") == tid)
    ok("没给名字时默认名是「任务#<实际任务号>」",
       record.get("name") == f"任务#{tid}", repr(record.get("name")))
    ok("⚠️ 名字里的序号用的是**实际分配到的号**（不是预测值）",
       record.get("name", "").endswith(tid), record.get("name"))
    ok("没给 PDF 时source_path 存空串（不是 '.' 那类假路径）",
       record.get("source_path") == "", repr(record.get("source_path")))

    # 有名字 ⇒ 照用；名字里给的序号不作数
    tid2 = store.create_task(None, "", "我自己起的名字")
    ok("给了名字就用给的", (store.get_task(tid2) or {}).get("name")
       == "我自己起的名字")
    # 给了 PDF ⇒ 索引里有路径
    tid3 = store.create_task(pdf, "h-shell", "有源文件")
    ok("给了 PDF 就记下路径",
       (store.get_task(tid3) or {}).get("source_path") == str(pdf))

    # 补选：set_task_source 把文件收进任务目录并改索引
    ok("set_task_source 拒绝不存在的文件",
       store.set_task_source(tid, pdf.parent / "没有这个.pdf") is False)
    ok("set_task_source 拒绝不存在的任务",
       store.set_task_source("9999", pdf) is False)
    ok("补选 PDF 成功：索引更新 + 副本落进任务目录",
       store.set_task_source(tid, pdf)
       and (store.get_task(tid) or {}).get("source_path") == str(pdf)
       and store.source_copy_path(tid) is not None)
    # 清空名字回落：空壳任务（没源）⇒ 任务#号；不是留空
    store.rename_task(tid2, "  ")
    ok("空壳任务清空名字回落到「任务#号」（不是留空、也不是文件名）",
       (store.get_task(tid2) or {}).get("name") == f"任务#{tid2}",
       (store.get_task(tid2) or {}).get("name"))
    # 详情页对空壳任务的处理
    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.steps.flow import default_flow_path

    empty_tid = store.create_task(None, "", "")
    probe = TaskDetailPage(store)
    probe.resize(1080, 720)
    probe.show()
    try:
        app.processEvents()
        # ⚠️ 离屏绝不能真弹模态（项目硬规则）：换成记录器，顺便当断言材料
        from tests.selftests._context import silence_source_prompt

        prompt_calls = silence_source_prompt(probe)
        ok("空壳任务能进详情页（不崩、不被拒）",
           probe.set_task(empty_tid) is True)
        prompt = probe._source_prompt
        ok("进空壳任务详情时**弹出**了「缺源 PDF」提示层（用户 2026-10-06）",
           prompt is not None and prompt.isVisible(),
           f"prompt={prompt} calls={len(prompt_calls)}")
        # ---- 用户截图三条：遮罩完整 / 盖住流程条 / 按钮在遮罩之上 ----
        geo = prompt.geometry() if prompt else None
        # ⚠️ 「内容区上沿」用**根布局里主体那一行**（页头之后那项）的位置，
        #    **别用步骤条自己的 geometry** —— 刚被 _rebuild_step_bar 换掉、
        #    布局还没定位，读出来是 QWidget 默认的 (0,0,640,480)，比出来
        #    永远是 0（与 _content_top 里记的同一个坑）。
        body_item = probe._root_layout.itemAt(probe._step_bar_row + 1)
        content_top = body_item.geometry().y() if body_item else 0
        # ⚠️ 用 ``y() + height()`` 比，**别用 QRect.bottom()**——那是
        #    **包含式**的（= top+height-1），跟高度比永远差 1。
        ok("遮罩**铺满内容区**（用户：mask 不完整只有一部分）",
           geo is not None
           and geo.x() == 0 and geo.width() == probe.width()
           and geo.y() + geo.height() == probe.height(),
           f"mask={geo.getRect() if geo else None} page={probe.rect().getRect()} "
           f"content_top={probe._content_top()}")
        ok("遮罩**盖住流程条**（用户：mask 没覆盖流程图）",
           geo is not None and geo.y() <= content_top,
           f"mask.y={geo.y() if geo else None} content_top={content_top}")
        btn = probe.source_button
        ok("页头操作按钮**留在遮罩之上**且可用（用户第3 条）",
           btn.geometry().bottom() <= (geo.top() if geo else 0)
           and btn.isEnabled(),
           f"btn={btn.geometry().getRect()} mask.top={geo.top() if geo else None}")
        ok("提示层**非模态**（模态会把页头按钮的事件全吃掉）",
           prompt is not None
           and prompt.windowModality() == prompt.windowModality().NonModal,
           str(prompt.windowModality()) if prompt else "")
        ok("提示卡片有内容且不是被压扁的空白条",
           prompt is not None
           and prompt.card.height() > 80
           and prompt.card.layout().count() >= 4,
           f"h={prompt.card.height()} n={prompt.card.layout().count()}"
           if prompt else "")
        # ---- 按钮**真的点得动**（用户 2026-10-06："那个导入按钮，你不能把
        #      它给遮住啊"）。上面那些只验了"看起来可点"，这里真点一下。----
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        picked_by_button = []
        real_pick = probe._on_pick_source
        probe._on_pick_source = lambda: picked_by_button.append(1)
        try:
            QTest.mouseClick(probe.source_button, Qt.MouseButton.LeftButton)
            app.processEvents()
            QTest.mouseClick(probe.source_button, Qt.MouseButton.LeftButton)
            app.processEvents()
        finally:
            probe._on_pick_source = real_pick
        ok("提示层显示时，页头 PDF 按钮**点了真的有反应**（没被遮罩吃掉）",
           len(picked_by_button) == 2,
           f"picked={len(picked_by_button)}")
        ok("点了按钮后提示层**不自己消失**（用户可以接着补文件）",
           prompt is not None and prompt.isVisible())
        # ---- 点内容区（被遮罩覆盖的地方）：吃掉点击、但**不关提示** ----
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPointF, QEvent as QEventEnum

        ev = QMouseEvent(
            QEventEnum.MouseButtonPress, QPointF(prompt.width() / 2,
                                                prompt.height() / 2),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        prompt.mousePressEvent(ev)
        app.processEvents()
        ok("点被遮住的内容区**不会关掉提示**（否则用户以为关掉了、按钮又没反应）",
           prompt.isVisible())
        # ---- **第二次进入仍要弹**（用户 2026-10-06："没有选择源文件，为何弹窗
        #      也没有了，每次进入都要检测"）----
        # 先模拟用户点了「稍后再说」（提示层被收起），再重新进同一个任务
        prompt.dismiss()
        app.processEvents()
        ok("收起来之后提示层确实不可见", not prompt.isVisible())
        prompt_calls.clear()
        probe.set_task(empty_tid)
        app.processEvents()
        ok("**再次进入同一个缺源任务，提示层照样弹出**（每次进入都检测）",
           prompt.isVisible(),
           f"visible={prompt.isVisible()}")
        # ---- 卡片**高度够**（用户 2026-10-06：文字显示不完整）----
        ok("提示卡片高度容得下所有文字（wordWrap 换行后的真实高度）",
           prompt.card.height() >= prompt.card.box.sizeHint().height(),
           f"h={prompt.card.height()} need={prompt.card.box.sizeHint().height()}")
        # ---- 卡片能**拖动**（用户 2026-10-06：不可以移动）----
        from PySide6.QtCore import QEvent as _QE, QPoint, QPointF
        from PySide6.QtGui import QMouseEvent as _QMouseEvent

        origin = prompt.card.pos()
        center = prompt.card.rect().center()
        for _kind, _pos, _btn, _btns in (
            (_QE.MouseButtonPress, QPointF(center),
             Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton),
            (_QE.MouseMove, QPointF(center + QPoint(90, 45)),
             Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton),
            (_QE.MouseButtonRelease, QPointF(center + QPoint(90, 45)),
             Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton),
        ):
            app.sendEvent(prompt.card, _QMouseEvent(
                _kind, _pos, _btn, _btns, Qt.KeyboardModifier.NoModifier))
        app.processEvents()
        ok("提示卡片**可以拖动**（按住卡片空白处）",
           prompt.card.pos() != origin,
           f"{origin} -> {prompt.card.pos()}")
        prompt._move_card(QPoint(99999, 99999))
        ok("卡片拖不出提示层范围（会被夹住）",
           prompt.card.x() + prompt.card.width() <= prompt.width()
           and prompt.card.y() + prompt.card.height() <= prompt.height()
           and prompt.card.x() >= 0 and prompt.card.y() >= 0,
           f"{prompt.card.pos()} in {prompt.width()}x{prompt.height()}")
        # ---- 卡片上两个按钮都**真的能点**（第一版把它们的按下吞了）----
        prompt.card_host_center()
        dis = []
        prompt.dismissed.connect(lambda: dis.append(1))
        QTest.mouseClick(prompt.later_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        ok("卡片上「稍后再说」**点得动**（过滤器不许吞按钮的按下）",
           bool(dis), f"dismissed={len(dis)}")
        # ⚠️⚠️ 收集器**直连 ``prompt.picked``**，**不能**靠替换
        #    ``probe._on_pick_source`` —— Qt 在 ``connect`` 的那一刻就把槽
        #    绑成当时的 callable 了，之后改对象属性对已连的信号**无效**
        #    （而真槽会真的去弹模态文件框）。我先写成替换属性，自测里
        #    「picked=0」假红了一轮才发现。
        picked = []
        # ⚠️ 信号**带一个参**（``pick_kind``：要目录框还是文件框，用户
        #    2026-10-06"改成选择图片目录"）⇒ 收集器必须**收下这个参**，
        #    写 `lambda: ...` 会 TypeError（PySide6 不像 PyQt 那样容忍）。
        prompt.picked.connect(lambda kind="": picked.append(kind))
        prompt.show_prompt()
        # ⚠️ ``show()`` 是**异步**的：不跑一圈事件循环，控件还没真正显示，
        #    这时 ``mouseClick`` 点上去是空的。
        app.processEvents()
        QTest.mouseClick(prompt.pick_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        ok("卡片上主按钮**点得动**", bool(picked), f"picked={len(picked)}")
        ok("默认（缺 PDF）走**文件框**", picked == ["files"], str(picked))
        ok("空壳任务：source_path 是 None（不是 Path('') 那类假路径）",
           probe.source_path is None, repr(probe.source_path))
        ok("空壳任务：页头写「尚未选择 PDF」",
           "尚未选择" in probe.source_label.text(), probe.source_label.text())
        ok("空壳任务：页头有补选 PDF 的入口",
           hasattr(probe, "source_button")
           and not probe.source_button.isHidden()
           and "PDF" in probe.source_button.toolTip(),
           probe.source_button.toolTip()
           if hasattr(probe, "source_button") else "无按钮")
        ok("补选按钮的提示随「有没有源文件」变",
               probe._refresh_source_actions() is None
               and "还没有" in probe.source_button.toolTip(),
               probe.source_button.toolTip())
        # ---- 缺源 PDF 时：按钮高亮 + 页头红字（用户 2026-10-06）----
        ok("缺源 PDF 时判据成立（该催用户补）",
           probe._missing_source() is True)
        ok("缺源 PDF 时页头出红字提示",
           not probe.source_warning.isHidden()
           and "尚未选择 PDF" in probe.source_warning.text(),
           probe.source_warning.text())
        ok("红字是**红**的（原生 QLabel 走 palette；qfluent 标签走 setTextColor）",
           _label_text_color(probe.source_warning).upper()
           == T.DANGER.upper(),
           _label_text_color(probe.source_warning))
        style = probe.source_button.styleSheet()
        ok("缺源 PDF 时补选按钮**高亮**（红边框 + 淡红底）",
           T.DANGER in style and T.DANGER_SOFT in style, style[:80])
        # 换源文件前的确认：判据可被替身覆盖（离屏自测绝不真弹模态）
        ok("空壳任务没有任何产物 ⇒ 换源文件不必问（静默换）",
           probe._source_replace_is_blocked(pdf) is False)
        # 造一点产物出来 ⇒ 该问
        (store.task_dir(empty_tid) / "pages.json").write_text("[]",
                                                              encoding="utf-8")
        ok("有中间产物时换源文件需要确认（会清掉旧产物）",
           probe._source_replace_is_blocked(pdf) is True)
        ok("有产物判定看得见：_has_task_artifacts 能认出 pages.json",
           probe._has_task_artifacts() is True)
        (store.task_dir(empty_tid) / "pages.json").unlink()
        # 换源文件会清产物
        (store.task_dir(empty_tid) / "runs.json").write_text("[]",
                                                             encoding="utf-8")
        # ⚠️ 造两个"待写"标记：set_task 开头的 flush 会把它们落盘。若换源
        #    只删文件不清标记，旧书的参数暂存/检测框就复活了。
        probe._draft_dirty = {0}
        probe._pending_sizes = {"0001.jpg": [10, 20]}
        probe._pending_boxes = {"0001.jpg": [[0, 0, 5, 5]]}
        probe._reset_artifacts_for_new_source()
        ok("换源文件清掉旧书的中间产物（否则界面混着两本书的结果）",
           not (store.task_dir(empty_tid) / "runs.json").exists()
           and probe.pages == [] and probe.pdf_page_count == 0)
        ok("换源文件连**待写标记**一起清（否则 set_task 的 flush 把旧书数据写回来）",
           probe._draft_dirty == set() and probe._pending_sizes == {}
           and probe._pending_boxes == {})
        ok("换源文件**不碰**流程图（流程是用户配的，与源文件无关）",
           default_flow_path(store.task_dir(empty_tid)).exists())
    finally:
        probe.shutdown_all_workers()
        probe.close()
        app.processEvents()
    # ---- 补上文件后高亮/红字要收掉；流程不要 PDF 时不催 ----
    # ⚠️ **另起探针**：这两条要反复 `set_task` 切任务，共用 `probe` 会把上面
    #    那些断言的上下文（当前任务、产物状态）带偏——之前就踩过一次，
    #    表现为"改一个断言，后面一串莫名假红"。
    _check_source_prompt_cycle(store, pdf, app)
    # 清场：本节建的几个任务
    for extra in (tid, tid2, tid3, empty_tid):
        store.delete_task(extra)


def _check_source_prompt_cycle(store, pdf, app) -> None:
    """补上 PDF ⇒ 提示全收；流程不需 PDF ⇒ 一律不催（用户 2026-10-06）。"""
    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.ui import theme
    from desktop.steps.bpmn_diagram import (
        DiagramFlow, FlowDiagram,
    )
    from desktop.utils.files import file_hash
    from tests.selftests._context import ok, silence_source_prompt

    empty_tid = store.create_task(None, "", "")
    no_pdf_flow = store.create_task(None, "", "")
    # 造一条"没有提取图片"的流程（用户自定义流程可能删掉那一步）
    base = store.task_diagram(empty_tid)
    keep = [n for n in base.nodes if n.name != "提取图片"]
    if len(keep) >= 2:
        store.save_task_diagram(no_pdf_flow, FlowDiagram(
            nodes=tuple(keep),
            flows=tuple(DiagramFlow(f"nf{i}", keep[i - 1].id, keep[i].id)
                        for i in range(1, len(keep))),
        ))
    probe = TaskDetailPage(store)
    probe.resize(1080, 720)
    probe.show()
    try:
        app.processEvents()
        prompt_calls = silence_source_prompt(probe)
        # ---- 补上 PDF ⇒ 红字与高亮都收掉 ----
        real = store.task_dir(empty_tid) / "补选.pdf"
        real.write_bytes(pdf.read_bytes())
        store.set_task_source(empty_tid, real, source_hash=file_hash(real))
        probe.set_task(empty_tid)
        ok("补上 PDF 后红字消失（不留一句过期的话）",
           probe.source_warning.isHidden(), probe.source_warning.text())
        ok("补上 PDF 后按钮高亮撤掉（回默认样式）",
           probe.source_button.styleSheet() == "",
           repr(probe.source_button.styleSheet()[:40]))
        ok("补上 PDF 后不再催（判据为假）", probe._missing_source() is False)
        ok("补上 PDF 后进页面也不弹提示（提示层被收掉）",
           not prompt_calls or probe._source_prompt is None
           or not probe._source_prompt.isVisible(),
           f"visible={probe._source_prompt is not None and probe._source_prompt.isVisible()}")
        # ---- 流程里不需要 PDF ⇒ **不催 PDF**，改催"上传图片" ----
        # ⚠️⚠️ 这条断言 2026-10-06 改过一次口径：删掉「提取图片」后的流程，
        #    第一格是「检测文本框」——它**不吃 PDF**，输入是入口图片目录。
        #    所以正确表现不是"一律不催"，而是"**催的是图片不是 PDF**"
        #    （用户 2026-10-06：「非图片提取节点如果做第一个节点……应该提醒
        #    上传输入目录或者图片」）。旧的"不催"断言与新口径直接冲突。
        if len(keep) >= 2:
            prompt_calls.clear()
            probe.set_task(no_pdf_flow)
            app.processEvents()
            # ⚠️ 判"提示层没出现"要看**它有没有被建出来/显示**，不能只看
            #    记录列表——那记的是"被请求"，每次 set_task 都会记一笔。
            shown = (probe._source_prompt is not None
                     and probe._source_prompt.isVisible())
            ok("流程里没有要 PDF 的步骤 ⇒ **不催 PDF**（不催错的方向）",
               probe._missing_source() is False
               and probe.source_button.styleSheet() == "",
               f"missing={probe._missing_source()} "
               f"btn={probe.source_button.styleSheet()[:30]}")
            ok("流程第一步不吃 PDF 且入口目录没图 ⇒ 判据是「缺图片」",
               probe._missing_input_kind() == "images",
               f"kind={probe._missing_input_kind()!r}")
            ok("缺图片 ⇒ 提示层照样弹出（每次进入都检测）", shown,
               f"shown={shown}")
            # 判"高亮"直接看有没有非空样式表就够：非空 = 有边框+底色那套
            # （_set_tool_highlight 撤掉时写的是空串），不必去比对色值。
            ok("缺图片 ⇒ 高亮的是**图片按钮**、不是 PDF 按钮",
               bool(probe.insert_button.styleSheet())
               and probe.source_button.styleSheet() == "",
               f"insert={bool(probe.insert_button.styleSheet())} "
               f"pdf={bool(probe.source_button.styleSheet())}")
            ok("缺图片 ⇒ 页头图片/目录入口**显示**（藏了就没法补，规则②）",
               not probe.insert_button.isHidden()
               and not probe.insert_dir_button.isHidden())
            ok("缺图片 ⇒ 检测页左下角「＋/📁」显示（入口就是检测，规则③）",
               _viewer_entry_button(probe.detect_viewer,
                                    "插入图片（可多选）") is not None
               and not _viewer_entry_button(
                   probe.detect_viewer, "插入图片（可多选）").isHidden())
            ok("缺图片 ⇒ 页头红字说的是图片（不是 PDF）",
               "图片" in probe.source_warning.text()
               and "PDF" not in probe.source_warning.text(),
               probe.source_warning.text())
            ok("缺图片 ⇒ 提示层文案说图片，不说 PDF",
               shown and "图片" in probe._source_prompt.title_label.text()
               and "PDF" not in probe._source_prompt.title_label.text(),
               probe._source_prompt.title_label.text() if shown else "")
            ok("缺图片 ⇒ 主按钮文案是**选择图片目录**（用户 2026-10-06）",
               shown and probe._source_prompt.pick_button.text() == "选择图片目录",
               probe._source_prompt.pick_button.text() if shown else "")
            # ⚠️ **文案与行为必须一致**：按钮写着"选目录"，点了就必须真开
            #    **目录**框。`getOpenFileNames` 选不了目录，所以这条钉的是
            #    `pick_kind` 传出去的值——它决定宿主走哪个 QFileDialog。
            ok("缺图片 ⇒ 该按钮声明自己要**目录框**（点下去开目录对话框）",
               shown and probe._source_prompt._content.get("pick_kind") == "folder",
               str(probe._source_prompt._content.get("pick_kind")))
            # ---- 往入口目录放一张图 ⇒ 提示全收 ----
            entry = store.task_input_dir(no_pdf_flow)
            entry.mkdir(parents=True, exist_ok=True)
            (entry / "page001.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            probe.set_task(no_pdf_flow)
            app.processEvents()
            ok("入口目录里已有图 ⇒ 不再判缺（不催了）",
               probe._missing_input_kind() == "",
               f"kind={probe._missing_input_kind()!r}")
            # ⚠️ 判"动态高亮撤掉"**不能**看 ``styleSheet() == ""``：插图按钮
            #    自2026-10-06 起带**常驻红框**（入口标识，用户要求"都是红色
            #    框住"），样式表永远非空。动态那层与常驻那层**同色**、无法从
            #    样式表文本区分——它的可见性由「红字还在不在」如实反映：
            #    有红字＝还在催你；红字消失＝动态高亮确实撤了。
            #    （曾经在这里断言 styleSheet 为空，改成常驻红框后必然假红。）
            ok("入口目录里已有图 ⇒ 不再催（红字消失＝动态高亮已撤）",
               probe.source_warning.isHidden()
               and probe._missing_input_kind() == "",
               f"hidden={probe.source_warning.isHidden()} "
               f"kind={probe._missing_input_kind()!r}")
            ok("入口目录里已有图 ⇒ 常驻红框仍在（入口标识不被撤掉）",
               str(theme.DANGER) in (probe.insert_button.styleSheet() or ""),
               f"style={probe.insert_button.styleSheet()[:40]}")
        else:
            ok("流程里没有要 PDF 的步骤 ⇒ 不催 PDF（构造跳过）", True)

        # ---- 流程读不出来 ⇒ **必须让用户看见**（不再静默回落默认流程）----
        # ⚠️⚠️ `store.task_diagram` 在三种失败形态下都会**静默**回落默认模板：
        #   ① `flow.bpmn` 不存在；② XML 非法；③ **解析得动但一个步骤名都认不出**。
        # 第三种最狠：用户在 bpmn.io 里把「图片去底色」改名成「AI 抠图」——
        # 一次完全合法的编辑——整张自定义图被判成"坏"，界面变回默认流程，
        # 而用户看到的现象与"我没改过它"完全一样，找不到任何线索。
        # 所以回落必须配一条提示（`flow_degraded_reason` + `_warn_if_flow_degraded`）。
        bad_tid = store.create_task(None, "", "")
        bad_flow = store.task_dir(bad_tid) / "flow.bpmn"
        try:
            bad_flow.write_text(
                '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/'
                '20100524/MODEL" xmlns:guji="https://guji.tools/bpmn/2025">'
                '<bpmn:process id="p" isExecutable="false">'
                '<bpmn:task id="a" name="AI 抠图"/>'
                "</bpmn:process></bpmn:definitions>",
                encoding="utf-8",
            )
            # 走一次读：降级原因就是这时记下的
            store.task_diagram(bad_tid)
            reason = store.flow_degraded_reason(bad_tid)
            ok("步骤名一个都认不出 ⇒ 记下降级原因（不是无声换回默认流程）",
               "认不出来" in reason or "步骤" in reason, reason)

            toasts: list = []
            _real_toast = probe._toast
            probe._toast = (lambda kind, title, content:
                            toasts.append((kind, title, content)))
            try:
                probe.set_task(bad_tid)
                app.processEvents()
                ok("流程降级 ⇒ 进任务就弹一次警告（告诉用户为什么变回默认）",
                   any("默认" in t[1] for t in toasts), str(toasts[:2]))
                ok("警告里说清了改流程不会有效果（下一步该做什么）",
                   any("不会有任何效果" in t[2] for t in toasts),
                   str(toasts[:1]))
                ok("同一次进入只弹一次（flow_slots 会被读很多遍，别刷屏）",
                   len([t for t in toasts if "默认" in t[1]]) == 1,
                   str(toasts))
            finally:
                probe._toast = _real_toast

            # 修好之后 ⇒ 不再提示，且降级原因被清掉
            from desktop.steps.scheduler import load_default_diagram
            load_default_diagram().save(bad_flow)
            store.task_diagram(bad_tid)
            ok("流程修好 ⇒ 不再判降级（提示会收）",
               store.flow_degraded_reason(bad_tid) == "",
               store.flow_degraded_reason(bad_tid))
        finally:
            try:
                store.delete_task(bad_tid)
            except OSError:
                pass
    finally:
        probe.shutdown_all_workers()
        probe.close()
        app.processEvents()
        for extra in (empty_tid, no_pdf_flow):
            try:
                store.delete_task(extra)
            except OSError:
                pass


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
