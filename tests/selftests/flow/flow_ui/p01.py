# -*- coding: utf-8 -*-
"""1 / 2 / 3 / 4 / 5"""

from typing import Any


def run(st: Any) -> None:
    from desktop.components.bpmn_editor import BpmnEditor
    from desktop.components.bpmn_view import BpmnView
    from desktop.steps.scheduler import (
        DONE, SKIPPED, Scheduler, default_template_path, load_default_diagram,
    )
    from desktop.steps.bpmn_diagram import (
        KIND_END, KIND_EXCLUSIVE, KIND_START, KIND_TASK, DiagramFlow,
        DiagramNode, DiagramNote, FlowDiagram,
    )
    from pathlib import Path
    from PySide6.QtCore import QEvent, QPointF, Qt
    from desktop.components import create_task_dialog
    from tests.selftests._context import ok
    import shutil
    import tempfile
    header_texts = [b.text() for b in st.page.findChildren(type(st.page._import_button))]
    ok("页头主按钮是「创建任务」",
       any("创建任务" in t for t in header_texts), str(header_texts))
    ok("旧文案「导入 PDF」已消失",
       not any("导入 PDF" in t for t in header_texts), str(header_texts))
    st.init = create_task_dialog.load_custom_init()
    ok("默认模板 task_default.bpmn 能解析出节点", len(st.init.nodes) > 0,
       str(len(st.init.nodes)))
    kinds = {n.kind for n in st.init.nodes}
    ok("初值里有网关（写 bpmn.io 画的图带 exclusiveGateway）",
       KIND_EXCLUSIVE in kinds, str(sorted(kinds)))
    ok("初值里有起止事件",
       KIND_START in kinds and KIND_END in kinds, str(sorted(kinds)))
    ok("初值节点都带 DI 坐标（页面按文件坐标画）",
       all(n.id in st.init.boxes for n in st.init.nodes),
       str([n.id for n in st.init.nodes if n.id not in st.init.boxes]))
    ok("连线带折点（走文件里存的 di:waypoint）",
       all(f.id in st.init.waypoints for f in st.init.flows),
       str([f.id for f in st.init.flows if f.id not in st.init.waypoints]))

    view = BpmnView(st.init)
    ok("BpmnView 能按文件渲染（尺寸随内容）",
       view.width() > 0 and view.height() > 0,
       f"{view.width()}x{view.height()}")
    gw = next(n for n in st.init.nodes if n.is_gateway)
    ok("网关的命中测试按菱形判（不是外接矩形）",
       view.node_at(view.rect_of(gw.id).topRight() - __import__(
           "PySide6.QtCore", fromlist=["QPointF"]
       ).QPointF(4, 4)) != gw.id,
       "菱形四角不该被当成命中")
    order = st.init.stage_order()
    ok("阶段顺序是拓扑序（拼版排在 PDF排版 之前）",
       order.index("imposition") < order.index("print"), str(order))
    sched_on = Scheduler.from_diagram(st.init, {"imposition": True})
    sched_off = Scheduler.from_diagram(st.init, {"imposition": False})
    ok("状态机（开拼版）含拼版", "imposition" in sched_on.stages,
       str(sched_on.stages))
    ok("状态机（关拼版）剔除拼版", "imposition" not in sched_off.stages,
       str(sched_off.stages))
    ok("关拼版时拼版记 SKIPPED（界面能区分没有与跳过）",
       sched_off.state_of("imposition") == SKIPPED,
       sched_off.state_of("imposition"))
    ok("状态机顺序与图的拓扑序一致",
       tuple(s for s in sched_on.stages if s in st.init.stage_order())
       == tuple(s for s in st.init.stage_order() if s in sched_on.stages))
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
    editor = BpmnEditor(FlowDiagram.load(default_template_path()))
    n_before = len(editor.diagram().nodes)
    new_id = editor.add_node(name="新步骤")
    ok("加节点", len(editor.diagram().nodes) == n_before + 1)
    editor.rename_node(new_id, "改过的名字")
    _renamed = editor.diagram().node(new_id)
    assert _renamed is not None  # 刚加的节点必然还在图上
    ok("改名", _renamed.name == "改过的名字")
    # ⚠️⚠️ **改名不断绑**：阶段身份是节点的属性（落盘在 ``guji:stage``），
    # 名字只是显示标签。以前改名会**重算**阶段——「图片去底色」改成「AI 抠图」
    # 就接不回任何阶段，整张图被判"坏图"而回落默认流程（用户只改了个标签，
    # 流程却被换掉了）。现在：认得出的名字换绑，认不出的名字只改显示。
    _real_node = next(n.id for n in editor.diagram().nodes
                      if n.stage == "rembg")
    # 先把图对象取出来绑定好：``editor`` 在后面的用例里会被重新赋值（含 None），
    # 嵌套函数里读它 pyright 会当成 ``BpmnEditor | None``；绑成局部变量即可。
    _diagram = editor.diagram()

    def _stage_of(node_id: str):
        # ⚠️ ``rename_node`` 会**重建**节点（DiagramNode 是 frozen，只能换新
        #    对象），所以改名后旧节点对象就作废了。每次断言都必须从图上现取，
        #    不能把节点对象缓存下来——缓存了就会一直读到改名前的旧阶段。
        node = _diagram.node(node_id)
        assert node is not None  # 节点刚改过名，必然还在图上
        return node.stage

    editor.rename_node(_real_node, "AI 抠图")
    ok("改名成认不出的名字 ⇒ **保留原阶段**（只改显示，不断绑）",
       _stage_of(_real_node) == "rembg",
       str(_stage_of(_real_node)))
    # 改成另一个已知阶段名 ⇒ 换绑（"改名切换步骤类型"，有意保留）
    editor.rename_node(_real_node, "检测文本框")
    ok("改成已知阶段名 ⇒ 换绑到那个阶段",
       _stage_of(_real_node) == "detect",
       str(_stage_of(_real_node)))
    editor.rename_node(_real_node, "图片去底色")
    ok("改回原来的阶段名 ⇒ 换绑回来",
       _stage_of(_real_node) == "rembg",
       str(_stage_of(_real_node)))
    # 本来就没阶段的节点 ⇒ 改名不许凭空接上（随手一改多出运行步骤更糟）
    editor.rename_node(new_id, "还是认不出")
    ok("本来就没有阶段的节点改名 ⇒ 仍是 None（不凭空接上）",
       _stage_of(new_id) is None,
       str(_stage_of(new_id)))
    # 身份落盘往返：自定义名字存进 ``guji:stage``，重读不再靠名字猜
    editor.rename_node(_real_node, "AI 抠图")
    _roundtrip = Path(st.ctx.tmp) / "rename_roundtrip.bpmn"
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
    # ⚠️ 传的是**视图坐标**（鼠标点），``_move_node`` 负责换算成文件坐标。
    #    不换算的话写回去的坐标会带上画布偏移（``_offset()``，默认模板约
    #    126px）——现象是"鼠标一动节点先飞一截再跟着走"（2026-10-08 修）。
    _ox, _oy = editor._offset()
    editor._move_node(QPointF(777.0 + _ox, 555.0 + _oy))
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
                DiagramNode("p", KIND_TASK, "PDF排版", stage="print"),
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
                   DiagramNode("p", KIND_TASK, "PDF排版", stage="print")),
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

        # 多个来源**按方位分边**（用户 2026-10-07）：齐行的留横边中线，
        # 下方来的改走下边——不再挤同一条横边、把中线那条顶偏。
        multi = FlowDiagram(
            nodes=(DiagramNode("g", KIND_EXCLUSIVE, "是否拼版"),
                   DiagramNode("p", KIND_TASK, "PDF排版", stage="print"),
                   DiagramNode("i", KIND_TASK, "图片拼版", stage="imposition")),
            flows=(DiagramFlow("f_no", "g", "p", "否"),
                   DiagramFlow("f_yes", "g", "i", "是"),
                   DiagramFlow("f_imp", "i", "p")),
            boxes={"g": (1005.0, 67.0, 50.0, 50.0),
                   "p": (1424.0, 48.0, 116.0, 87.0),
                   "i": (1215.0, 205.0, 115.0, 85.0)},
        )
        no_pts = multi.route(multi.flows[0])
        p_mid = multi.node_box("p")[1] + multi.node_box("p")[3] / 2
        ok("「否」直达 PDF排版 **左边中线**（同行的独苗，直线对齐）",
           len(no_pts) == 2 and abs(no_pts[-1][1] - p_mid) < 0.6,
           str(no_pts))
        imp_pts = multi.route(multi.flows[2])
        p_box = multi.node_box("p")
        ok("「图片拼版 → PDF排版」从**下边中点**进（不从左边挤车）",
           abs(imp_pts[-1][1] - (p_box[1] + p_box[3])) < 0.6
           and abs(imp_pts[-1][0] - (p_box[0] + p_box[2] / 2)) < 0.6,
           str(imp_pts))
        yes_pts = multi.route(multi.flows[1])
        i_mid = multi.node_box("i")[1] + multi.node_box("i")[3] / 2
        ok("网关下顶点出来的线**先竖后横**、水平进入图片拼版左边中点",
           yes_pts[1][0] == yes_pts[0][0]
           and abs(yes_pts[-1][1] - i_mid) < 0.6,
           str(yes_pts))

        # 入口/出口**不共点**（用户 2026-10-07）：同一节点的入边锚点与
        # 出边锚点不许重合——往左回头的数据流里，"从左边进"和"往左边出"
        # 不能都占左边中点，后算的沿边让到四分点。
        loop = FlowDiagram(
            nodes=(DiagramNode("a", KIND_TASK, "甲", stage="extract"),
                   DiagramNode("b", KIND_TASK, "乙", stage="detect")),
            flows=(DiagramFlow("f1", "a", "b"), DiagramFlow("f2", "b", "a")),
            boxes={"a": (0.0, 0.0, 100.0, 80.0),
                   "b": (300.0, 0.0, 100.0, 80.0)},
        )
        loop_a = loop.route(loop.flows[0])
        loop_b = loop.route(loop.flows[1])
        ok("双向两条线的四个端点**互不重合**（入口/出口不共点）",
           len({loop_a[0], loop_a[-1], loop_b[0], loop_b[-1]}) == 4,
           f"{loop_a} vs {loop_b}")

        # 注释挂接线也要**避开连线的出入口**（同一规则覆盖注释）：
        # 图片拼版右缘中点已被出边占用，挂接线得沿边滑开。
        multi.notes = (DiagramNote("nt", "古籍图片拼版"),)
        multi.note_links = {"nt": "i"}
        multi.boxes["nt"] = (1360.0, 300.0, 102.0, 40.0)
        view = BpmnView(multi)
        note_anchor = view._anchor_point("i", view.note_rect_of("nt"))
        edge_pts = view._edge_anchor_points("i")
        ok("注释挂接线**避开连线的出入口**（不与实线共点）",
           all(abs(note_anchor.x() - q.x()) >= 2.0
               or abs(note_anchor.y() - q.y()) >= 2.0 for q in edge_pts),
           f"注释锚点 {note_anchor.x()},{note_anchor.y()} vs 连线 {edge_pts}")

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

