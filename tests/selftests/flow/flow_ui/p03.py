# -*- coding: utf-8 -*-
"""6b"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import _click_at, _stroke
    from desktop.components.bpmn_editor import BpmnEditor
    from desktop.steps.bpmn_diagram import (
        KIND_END, KIND_EXCLUSIVE, KIND_START, KIND_TASK, DiagramFlow,
        DiagramNode, DiagramNote, FlowDiagram,
    )
    from desktop.components.flow_dialog import FlowDialog, FlowPanel
    from qfluentwidgets import ListWidget
    from pathlib import Path
    from PySide6.QtCore import QEvent, QPointF, Qt
    from desktop.steps.scheduler import (
        DONE, SKIPPED, Scheduler, default_template_path, load_default_diagram,
    )
    from tests.selftests._context import ok
    from desktop.components.bpmn_palette import palette_steps
    from desktop.steps import ports
    import shutil
    import tempfile
    try:
        panel = FlowPanel(st.init)
        panel.resize(1040, 720)
        panel.show()
        st.app.processEvents()
        board = panel.editor_panel
        editor = board.editor()
        ok("流程弹窗打开就是编辑态（不用再点一次「编辑流程」）",
           editor is not None and isinstance(editor, BpmnEditor))
        assert editor is not None  # 上一条 ok 已断言编辑态必有编辑器
        ok("工具栏有全部编辑动作（「连线」「重命名」已撤，用户 2026-11-17）",
           board.toolbar is not None
           and [b.text() for b in (board.add_button, board.delete_button)]
           == ["添加步骤", "删除"],
           str(board.toolbar))
        ok("工具栏**没有**「连线」「重命名」按钮（连线拖连接点、改名双击节点）",
           not hasattr(board, "link_button")
           and not hasattr(board, "rename_button"))
        # ⚠️ 「添加判断」入口已撤（用户 2026-10-08："其实根本就没有判断这个
        #    组件，只有「是否拼版」这个特殊的判断组件……是否拼版依附拼版"）。
        #    网关只能随模板文件来，界面上**不该**再有加它的按钮。
        ok("工具栏**没有**「添加判断」（网关依附图片拼版，不是独立组件）",
           not hasattr(board, "gateway_button"), str(dir(board)))
        # 选择：点节点能选中，且状态行说清"选中了什么"
        node_ids = [n.id for n in editor.diagram().nodes if n.kind == KIND_TASK]
        target = node_ids[0]
        editor.set_selected(None)
        st.app.processEvents()
        ok("没选中时「删除」是灰的（选中才有意义）",
           not board.delete_button.isEnabled())
        rect = editor.rect_of(target)
        _click_at(editor, rect.center().x(), rect.center().y())
        st.app.processEvents()
        ok("点节点能选中", editor.selected() == target, str(editor.selected()))
        ok("选中后「删除」变可用", board.delete_button.isEnabled())
        _target_node = editor.diagram().node(target)
        assert _target_node is not None  # target 刚从图里挑出来，必然存在
        ok("状态行写出了选中的是哪个步骤与它的运行阶段",
           "已选中" in board.status.text()
           and _target_node.name in board.status.text(),
           board.status.text())
        # ⚠️ 用户 2026-11-18：状态行以前直接印阶段 key（「运行阶段：rembg」），
        #    界面上只剩英文；必须走 ports.stage_label 的中文名。
        from desktop.steps import ports

        assert _target_node.stage  # 刚挑的必然是 task 节点
        ok("状态行的运行阶段印中文名（不再是 rembg/extract 这种 key）",
           f"运行阶段：{ports.stage_label(_target_node.stage)}" in board.status.text()
           and _target_node.stage not in board.status.text(),
           board.status.text())

        # 动作按钮**真的接上了**编辑器（接不上就是死按钮——上一版的毛病）
        fired: list[str] = []
        editor.ask_add_node = lambda: fired.append("add")
        editor.ask_delete_selected = lambda: fired.append("delete")
        board.add_button.click()
        board.delete_button.click()
        ok("工具栏按钮都真的接到编辑器动作上（不是死按钮）",
           fired == ["add", "delete"], str(fired))
        # 撤掉落上的替身（实例属性会盖住类方法）——后面要用**真**方法验证行为。
        del editor.ask_add_node
        del editor.ask_delete_selected
        editor.set_link_mode(False)

        # 选中连线
        flow_ids = [f.id for f in editor.diagram().flows]
        editor.set_selected_flow(flow_ids[0])
        board._sync_status()
        ok("能选中**连线**（并清掉节点选中）",
           editor.selected_flow() == flow_ids[0] and not editor.selected())
        ok("状态行写出了选中的是哪条连线",
           "连线" in board.status.text(), board.status.text())

        # 「添加步骤」方块面板的**候选名单**（用户 2026-11-17：下拉改方块；
        # 「提交检测结果」与「其他（自定义名称）」都不在名单里）
        from desktop.components.bpmn_palette import palette_steps
        ok("「添加步骤」候选 = 固定步骤表"
           "（没有「提交检测结果」的 detect_submit，也没有自定义项）",
           "detect_submit" not in palette_steps()
           and len(palette_steps()) == 5, str(palette_steps()))

        # 元素添加：加一个能被运行时认出来的步骤
        before = len(editor.diagram().nodes)
        new_id = editor.add_node(KIND_TASK, "图片拼版")
        st.app.processEvents()
        ok("「添加步骤」能加节点", len(editor.diagram().nodes) == before + 1)
        _added = editor.diagram().node(new_id)
        assert _added is not None  # 刚加的节点必然还在图上
        ok("新加的节点按名字接上了运行阶段（否则加了也不跑）",
           _added.stage == "imposition",
           str(_added.stage))
        # ⚠️ 网关**不再是可加的组件**（用户 2026-10-08："其实根本就没有判断
        #    这个组件，只有「是否拼版」这个特殊的判断组件……是否拼版依附拼版"）。
        #    编辑器不再有"加网关"的入口；认不出的拖放 token 一律拒绝，
        #    不凭空造节点（凭空造的节点接不上任何运行阶段）。
        ok("编辑器不再提供「加网关」入口",
           not hasattr(editor, "add_gateway"), str(dir(editor)))
        ok("认不出的拖放 token 被拒绝（不凭空造节点）",
           editor.add_step("__gateway__") is None
           and editor.add_step("") is None)
        # 两个任务关联：连线（画布内部连线模式——工具栏按钮已撤，
        # 这里直接驱动画布验证连线动作本身仍在）
        ok("开始不在连线模式", not editor.link_mode())
        editor.set_link_mode(True)
        st.app.processEvents()
        ok("进入连线模式（程序化驱动，按钮已撤）", editor.link_mode())
        link_src = editor.diagram().nodes[1].id
        link_dst = new_id
        flows_before = len(editor.diagram().flows)
        _src_center = editor.rect_of(link_src).center()
        _dst_center = editor.rect_of(link_dst).center()
        _click_at(editor, _src_center.x(), _src_center.y())
        ok("连线模式：第一次点击记下起点",
           editor._link_from == link_src, str(editor._link_from))
        _click_at(editor, _dst_center.x(), _dst_center.y())
        st.app.processEvents()
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
        st.app.processEvents()
        ok("「删除」删掉了节点",
           editor.diagram().node(doomed) is None)
        ok("删节点时连线一起删（不留悬空线）",
           all(f.source != doomed and f.target != doomed
               for f in editor.diagram().flows))

        # ⚠️ 「是否拼版」网关**依附图片拼版**（用户 2026-10-08："其实根本
        #    就没有判断这个组件，只有「是否拼版」这个特殊的判断组件……是否
        #    拼版依附拼版"）：删掉最后一个「图片拼版」时它跟着删；图里还剩
        #    拼版节点就不动它（那只是删重复）。用一张**新图**验，免得把后面
        #    用例还要用的那张改掉。
        cascade = BpmnEditor(FlowDiagram.load(default_template_path()))
        gws = [n.id for n in cascade.diagram().nodes if n.is_gateway]
        imps = [n.id for n in cascade.diagram().nodes
                if n.stage == "imposition"]
        ok("默认图里有「是否拼版」网关与「图片拼版」（前提成立）",
           len(gws) == 1 and len(imps) == 1, f"{gws} {imps}")
        extra_imp = cascade.add_node(KIND_TASK, "图片拼版")
        cascade.set_selected(extra_imp)
        cascade.remove_selected()
        ok("删掉重复的「图片拼版」⇒ 网关**不**跟着删（还依附得起）",
           cascade.diagram().node(gws[0]) is not None
           and cascade.diagram().node(imps[0]) is not None)
        cascade.set_selected(imps[0])
        cascade.remove_selected()
        st.app.processEvents()
        ok("删掉最后一个「图片拼版」⇒ 依附它的「是否拼版」网关一起删",
           cascade.diagram().node(imps[0]) is None
           and cascade.diagram().node(gws[0]) is None,
           str([n.id for n in cascade.diagram().nodes]))
        ok("网关删掉后没有悬空连线（一起删干净）",
           all(f.source != gws[0] and f.target != gws[0]
               for f in cascade.diagram().flows))

        # 拖拽：坐标变了，且折点被清掉重算
        from PySide6.QtCore import QPointF

        mover = editor.diagram().nodes[1].id
        box = editor.diagram().node_box(mover)
        view0 = editor.rect_of(mover)
        editor._drag_id = mover
        editor._moved = True
        # 按 ``_on_press`` 的同一算法造出"鼠标相对左上角的位移"，
        # 再按**视图坐标**给一个 +80/+40 的落点（与真实拖拽同一条路径）
        editor._drag_offset = QPointF(view0.center().x() - view0.left(),
                                      view0.center().y() - view0.top())
        editor._move_node(QPointF(view0.center().x() + 80.0,
                                  view0.center().y() + 40.0))
        st.app.processEvents()
        moved = editor.diagram().node_box(mover)
        view1 = editor.rect_of(mover)
        ok("拖节点能改坐标", abs(moved[0] - box[0]) > 40)
        ok("拖动**跟着鼠标走**（视图位移 == 鼠标位移，不因画布偏移跳一截）",
           abs((view1.left() - view0.left()) - 80.0) < 1
           and abs((view1.top() - view0.top()) - 40.0) < 1,
           f"{view0} -> {view1}")
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

        # ---- 文字注释：跟着宿主节点走 + 自己能拖（用户 2026-10-08）----
        # 用户原话："流程图编辑注释无法变动，比如任务位置变动，注释也理当一起
        # 变动合适位置，另外注释也需要可以拖动"
        # ⚠️ 选**不在包围盒边缘**的宿主（视图坐标 = 文件坐标 + 画布偏移，
        #    偏移由整图最小 x/y 决定）：拖最左/最上的节点会连偏移一起搬，
        #    视图位移就不再等于鼠标位移——那不是 bug，是居中画布的定义。
        #    拿中间的节点断言，文件坐标与视图坐标两套都成立。
        candidates = [n.id for n in editor.diagram().nodes
                      if editor.diagram().notes_of(n.id)]
        ok("默认图里有挂在节点上的注释（前提成立）", bool(candidates))
        assert candidates  # 上一条 ok 已断言存在
        boxes_now = dict(editor.diagram().boxes)
        min_x = min((b[0] for b in boxes_now.values()), default=0.0)
        min_y = min((b[1] for b in boxes_now.values()), default=0.0)
        noted = max(
            candidates,
            key=lambda nid: min(
                (boxes_now.get(note.id, (min_x, min_y, 0, 0))[0] - min_x)
                + (boxes_now.get(note.id, (min_x, min_y, 0, 0))[1] - min_y)
                for note in editor.diagram().notes_of(nid)
            ),
        )
        note = editor.diagram().notes_of(noted)[0]
        note_view0 = editor.note_rect_of(note.id)
        host_view = editor.rect_of(noted)
        editor._drag_id = noted
        editor._moved = True
        # 与真实拖拽同一条路径：按 ``_on_press`` 的算法造位移，落点用**视图坐标**
        editor._drag_offset = QPointF(0.0, 0.0)
        editor._move_node(QPointF(host_view.left() + 120.0,
                                  host_view.top() + 60.0))
        st.app.processEvents()
        note_view1 = editor.note_rect_of(note.id)
        ok("拖动节点时**注释跟着一起走**（位移与节点一致，不用手动摆）",
           abs((note_view1.left() - note_view0.left()) - 120.0) < 1
           and abs((note_view1.top() - note_view0.top()) - 60.0) < 1,
           f"{note_view0} -> {note_view1}")
        ok("注释与宿主节点的**相对位置不变**（不是被重新挂到别处）",
           abs((note_view1.left() - editor.rect_of(noted).left())
               - (note_view0.left() - host_view.left())) < 1,
           f"note {note_view1} host {editor.rect_of(noted)}")
        editor._drag_id = None

        # 注释**自己能拖**：合成一次真实鼠标轨迹（按下 → 移动 → 松开）
        # ⚠️ ``_stroke`` 只把中间点当移动、最后一点当松开位置，所以落点要写
        #    两遍（移到终点，再在终点松开），否则停在倒数第二点上。
        nrect = editor.note_rect_of(note.id)
        _stroke(editor, [
            (nrect.center().x(), nrect.center().y()),
            (nrect.center().x() + 45.0, nrect.center().y() + 20.0),
            (nrect.center().x() + 90.0, nrect.center().y() + 40.0),
            (nrect.center().x() + 90.0, nrect.center().y() + 40.0),
        ])
        st.app.processEvents()
        nrect2 = editor.note_rect_of(note.id)
        ok("注释可以**单独拖动**（视图位移 == 鼠标位移）",
           abs((nrect2.left() - nrect.left()) - 90.0) < 1
           and abs((nrect2.top() - nrect.top()) - 40.0) < 1,
           f"{nrect} -> {nrect2}")
        ok("拖注释**不改挂接关系**（虚线仍连回原来那个节点）",
           editor.diagram().note_links.get(note.id) == noted,
           str(editor.diagram().note_links.get(note.id)))
        ok("拖注释不改尺寸（只挪位置）",
           abs(nrect2.width() - nrect.width()) < 0.01
           and abs(nrect2.height() - nrect.height()) < 0.01,
           f"{nrect} -> {nrect2}")
        # 点一下注释（不拖）不该被当成拖动：低于阈值的手抖不移动它
        _click_at(editor, nrect2.center().x(), nrect2.center().y())
        st.app.processEvents()
        ok("点注释（不拖）不移动它（拖动阈值挡住手抖）",
           editor.note_rect_of(note.id) == nrect2,
           f"{nrect2} -> {editor.note_rect_of(note.id)}")

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

        # ---- 左侧固定节点面板已撤（用户 2026-11-17："左側這塊區域不需要了"）
        #      ——加步骤统一走工具栏「添加步骤」方块弹窗 ----
        # ⚠️ 别用 hasattr(board, "palette")：``palette`` 是 QWidget 的**内置
        #    Qt 属性**（QPalette），恒为真，判不出我们的面板撤没撤。
        #    面板本体是 ListWidget，查子控件里还有没有它。
        from qfluentwidgets import ListWidget

        ok("编辑态**没有**左侧固定节点面板（区域已撤）",
           not board.findChildren(ListWidget))
        # 任务节点仍是"接在选中节点后面"：加一个任务节点验自动连线还在
        some = editor.diagram().nodes[0].id
        editor.set_selected(some)
        flows_before = len(editor.diagram().flows)
        linked = editor.add_node(KIND_TASK, "PDF排版", stage="print",
                                 connect_from=some)
        ok("任务节点加进来时若选中了节点，仍自动连上一条线",
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
        st.app.processEvents()
        ok("按住连接点拖到目标节点即连上（松手才连，途中松手不算）",
           len(editor.diagram().flows) == flows_before + 1,
           f"{flows_before} -> {len(editor.diagram().flows)}")

        # ---- 自动排版：分层铺开、连线重算、语义不变 ----
        order_before = editor.diagram().stage_order()
        editor.auto_layout()
        st.app.processEvents()
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
        readonly = FlowPanel(st.init, editable=False)
        ok("只读态没有工具栏（看流程的入口不该给编辑按钮）",
           readonly.editor_panel.toolbar is None)
        ok("只读态没有「保存流程」按钮",
           not readonly.confirm_button.isVisible())
        readonly.close()
        shutil.rmtree(tmp_file.parent, ignore_errors=True)
        panel.close()
        st.app.processEvents()
    except Exception as exc:  # noqa: BLE001
        ok("流程编辑器（工具栏/选择/连线/增删/落盘）整体可用", False,
           f"{type(exc).__name__}: {exc}")

