# -*- coding: utf-8 -*-
"""**同类型多节点**自测（B 方案，2026-10-17）。

用户口径：图片拼版 / 检测文本框 / 图片去底色 / PDF排版 这几个节点在流程里
**可以有多个**，它们彼此独立、可以互相连接（输入输出接口已定义好），并且
**任务详情要体现这种流程**。

本模块钉死三件事：

1. **零迁移**：同一步骤恰好一个节点时（=所有现存任务与默认流程），产物目录、
   参数暂存、页清单、检测框的路径与改造前**逐字节相同**（主节点沿用旧路径）；
2. **按节点隔离**：同一阶段出现第二个节点时，它的产物落到
   ``stages/<阶段>~<节点>``、暂存落到 ``drafts/<阶段>~<节点>.json``、
   检测框落到 ``boxes~<节点>.json``、页清单落到 ``pages~<节点>.json``、
   运行状态各记各的（``node_states``）；
3. **界面如实体现在流程里**：步骤条上同一步骤**各占一格**、标题带序号可区分，
   "上次停留"精确到节点，执行端（``_output_path_for``）按节点落点。

⚠️ 本模块自建任务（自定义流程图 + 任务目录），结束时清掉，避免把
``stages/extract~*`` 之类的副本目录与暂存留给后面的模块。
"""

NAME = "multi_node"
DEPENDS: list[str] = ["tasklist"]
TITLE = "同类型多节点（各自产物/参数/状态）"


def _two_chain_diagram():
    """两条**独立平行链**，四条链上的节点各两个（同类型多节点）。

    ``start → ex1 → de1 → rb1 → pr1 → end``
    ``start → ex2 → de2 → rb2 → pr2 → end``

    ⚠️ 刻意做成两条**平行**链而不是一条长链：平行链里每个节点"最近的上游
    产出方"都在自己的链上（串成一条时 de1 的最近提取上游会是 ex2，
    那是合法但反直觉的连线，测出来的东西不好解释）。
    """
    from desktop.steps.bpmn_diagram import (
        KIND_END, KIND_START, KIND_TASK, DiagramFlow, DiagramNode, FlowDiagram,
    )

    nodes = [DiagramNode("start", KIND_START, "源PDF")]
    flows: list = []
    for suffix, name in (("1", ""), ("2", "2")):
        nodes += [
            DiagramNode(f"ex{suffix}", KIND_TASK, f"提取图片{name}",
                        stage="extract"),
            DiagramNode(f"de{suffix}", KIND_TASK, f"检测文本框{name}",
                        stage="detect"),
            DiagramNode(f"rb{suffix}", KIND_TASK, f"图片去底色{name}",
                        stage="rembg"),
            DiagramNode(f"pr{suffix}", KIND_TASK, f"PDF排版{name}",
                        stage="print"),
        ]
        flows += [
            DiagramFlow(f"fe{suffix}", "start", f"ex{suffix}"),
            DiagramFlow(f"fd{suffix}", f"ex{suffix}", f"de{suffix}"),
            DiagramFlow(f"fr{suffix}", f"de{suffix}", f"rb{suffix}"),
            DiagramFlow(f"fp{suffix}", f"rb{suffix}", f"pr{suffix}"),
            DiagramFlow(f"fx{suffix}", f"pr{suffix}", "end"),
        ]
    nodes.append(DiagramNode("end", KIND_END, "完成"))
    return FlowDiagram(nodes=tuple(nodes), flows=tuple(flows))


def run(ctx) -> None:
    from tests.selftests._context import ok, pump

    from desktop.components.panels.print_panel import PrintPanel
    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.pages.taskdetail.view import LazyPanelHost

    app, repo = ctx.app, ctx.repo

    def _bar(node_id: str) -> int:
        """节点 → 它在步骤条上的格序（本模块里必命中；断言代替 None 收窄）。"""
        index = page.bar_index_of_node(node_id)
        assert index is not None, node_id
        return index

    # ------------------------------------------------- ① 零迁移（默认流程）
    plain = repo.create_task(ctx.pdf, "hash-multi-node-plain", "单节点样本")
    page = TaskDetailPage(repo)
    try:
        page.set_task(plain)
        pump(app, times=6)
        task_dir = repo.task_dir(plain)
        slots = page.flow_slots()
        ok("默认流程：每个已接入步骤恰好一格",
           all(s.node_id for s in slots if s.mapped and not s.optional),
           str([(s.step, s.node_id) for s in slots]))
        ok("默认流程：步骤条标题**不带**序号（与改造前逐字相同）",
           not any("（" in t for t in page._bar_step_titles()),
           str(page._bar_step_titles()))
        primary_ex = repo.task_diagram(plain).primary_of("extract")
        ok("主节点沿用旧产物路径（零迁移）",
           repo.node_output(plain, primary_ex, "pages")
           == task_dir / "stages" / "extract",
           str(repo.node_output(plain, primary_ex, "pages")))
        ok("主节点沿用旧暂存路径",
           repo.draft_path(plain, "print") == task_dir / "drafts" / "print.json",
           str(repo.draft_path(plain, "print")))
        ok("主节点沿用旧检测框/页清单路径",
           repo.boxes_path(plain) == task_dir / "boxes.json"
           and repo.pages_path(plain) == task_dir / "pages.json")
    finally:
        page.shutdown_all_workers()
        page.deleteLater()
        repo.delete_task(plain)
        ok("零迁移样本任务已清理", repo.get_task(plain) is None)

    # ------------------------------------------------- ② 按节点隔离（两条链）
    tid = repo.create_task(ctx.pdf, "hash-multi-node", "多节点样本")
    repo.save_task_diagram(tid, _two_chain_diagram())
    task_dir = repo.task_dir(tid)
    page = TaskDetailPage(repo)
    try:
        page.set_task(tid)
        pump(app, times=6)
        slots = [s for s in page.flow_slots() if s.mapped and not s.optional]
        by_step: dict[str, list] = {}
        for slot in slots:
            by_step.setdefault(slot.step, []).append(slot)
        ok("四个步骤各有**两格**（同类型多节点各占一格）",
           {k: len(v) for k, v in by_step.items()}
           == {"extract": 2, "detect": 2, "rembg": 2, "print": 2},
           str({k: len(v) for k, v in by_step.items()}))
        ok("每格挂的是**不同的节点 id**",
           len({s.node_id for s in slots}) == len(slots) == 8,
           str([s.node_id for s in slots]))

        # ---- 标题可区分（任务详情"体现这种流程"）----
        titles = page._bar_step_titles()
        ok("同一步骤的两格标题带序号，能区分",
           "提取图片（1）" in titles and "提取图片（2）" in titles,
           str(titles))
        ok("不同步骤的序号各自从 1 数（不是全局第几格）",
           "PDF排版（1）" in titles and "PDF排版（2）" in titles, str(titles))

        # ---- 产物目录按节点 ----
        ok("主节点 ex1 落 stages/extract，副本 ex2 落 stages/extract~ex2",
           repo.node_output(tid, "ex1", "pages") == task_dir / "stages" / "extract"
           and repo.node_output(tid, "ex2", "pages")
           == task_dir / "stages" / "extract~ex2",
           f"{repo.node_output(tid, 'ex1', 'pages')} / "
           f"{repo.node_output(tid, 'ex2', 'pages')}")
        ok("rembg 预览目录按节点分",
           repo.node_output(tid, "rb1", "pages")
           == task_dir / "stages" / "rembgpreview"
           and repo.node_output(tid, "rb2", "pages")
           == task_dir / "stages" / "rembgpreview~rb2")
        ok("PDF排版的输出目录按节点分",
           repo.scoped_stage_dir(tid, "pr1", "print")
           == task_dir / "stages" / "print"
           and repo.scoped_stage_dir(tid, "pr2", "print")
           == task_dir / "stages" / "print~pr2")
        ok("执行端按节点取落点（_output_path_for）",
           page._output_path_for("extract", "ex2")
           == str(task_dir / "stages" / "extract~ex2")
           and page._output_path_for("print", "pr2")
           == str(task_dir / "stages" / "print~pr2"),
           f"{page._output_path_for('extract', 'ex2')} / "
           f"{page._output_path_for('print', 'pr2')}")

        # ---- 暂存 / 页清单 / 检测框按节点 ----
        ok("暂存文件按节点分",
           repo.draft_path(tid, "print", "pr2", "pr1")
           == task_dir / "drafts" / "print~pr2.json",
           str(repo.draft_path(tid, "print", "pr2", "pr1")))
        ok("页清单按节点分",
           repo.pages_path(tid, "ex2", "ex1")
           == task_dir / "pages~ex2.json",
           str(repo.pages_path(tid, "ex2", "ex1")))
        ok("检测框按节点分（主节点仍是 boxes.json）",
           repo.boxes_path(tid, "de2", "de1")
           == task_dir / "boxes~de2.json"
           and repo.boxes_path(tid, "de1", "de1") == task_dir / "boxes.json",
           f"{repo.boxes_path(tid, 'de2', 'de1')}")
        repo.save_detect_boxes(tid, "0001", [[1, 2, 3, 4], None],
                               node_id="de2", primary_id="de1")
        ok("副本节点的框写进自己的文件，主节点那份不受影响",
           repo.detect_boxes_entry(tid, "0001", "de2", "de1") is not None
           and repo.detect_boxes_entry(tid, "0001") is None,
           str(repo.boxes_path(tid, "de2", "de1")))

        # ---- 消费方按连线读**上游那个节点**的框 ----
        page._select_stage(_bar("rb2"))
        pump(app, times=6)
        read_path = page._boxes_read_path()
        ok("rb2 读的是连线上喂它的 de2 的框文件",
           read_path == repo.boxes_path(tid, "de2", "de1"),
           str(read_path))

        # ---- 运行状态按节点 ----
        repo.create_stage_run(tid, "extract", {}, node_id="ex2")
        runs = repo.list_stage_runs(tid, "extract")
        repo.finish_stage(tid, runs[0]["run_id"], "success")
        states = repo.node_states(tid)
        ok("node_states 记在**跑的节点**上",
           states.get("ex2", {}).get("status") == "success"
           and states["ex2"]["completed"] is True,
           str(states.get("ex2")))
        ok("没跑过的同阶段节点仍是 pending（借不到兄弟节点的成功）",
           states.get("ex1", {}).get("status", "pending") == "pending",
           str(states.get("ex1")))
        ok("阶段状态保持兼容（最新一条仍能按阶段读到）",
           repo.stage_states(tid)["extract"]["status"] == "success",
           str(repo.stage_states(tid)["extract"]["status"]))

        # ---- 界面按节点取状态（同一步骤两格不同状态）----
        page._refresh_stage_views()
        ex1_slot = page._slot_at_index(_bar("ex1"))
        ex2_slot = page._slot_at_index(_bar("ex2"))
        assert ex1_slot is not None and ex2_slot is not None
        stage_states = repo.stage_states(tid)
        ok("步骤条上两格的状态互不串味",
           ex1_slot.node_id == "ex1"
           and ex2_slot.node_id == "ex2"
           and page._slot_state(ex2_slot, states, stage_states)["completed"] is True
           and page._slot_state(ex1_slot, states, stage_states)["completed"] is False)

        # ---- "上次停留"精确到节点 ----
        pr2_bar = _bar("pr2")
        page._select_stage(pr2_bar)
        pump(app, times=6)
        ok("当前格记住了节点 id", page.current_node() == "pr2",
           str(page.current_node()))
        ok("ui.json 里记的是节点（不只步骤）",
           repo.load_last_node(tid) == "pr2" and repo.load_last_stage(tid) == "print",
           f"{repo.load_last_stage(tid)} / {repo.load_last_node(tid)}")
        ok("重进任务回到**同一个节点**那一格",
           page._initial_stage_index() == pr2_bar,
           f"{page._initial_stage_index()} != {pr2_bar}")

        # ---- 参数暂存真的按节点落盘 ----
        host = page.control_stack.widget(page.stack_index_of(pr2_bar))
        assert isinstance(host, LazyPanelHost)
        panel = host.panel
        assert isinstance(panel, PrintPanel)
        panel.page_margins.setText("30,40")
        page._flush_param_drafts()
        ok("在副本节点上改参数 → 写副本那一份暂存",
           (repo.load_draft(tid, "print", "pr2", "pr1") or {})
           .get("page_margins") == [30.0, 40.0, 30.0, 40.0],
           str(repo.load_draft(tid, "print", "pr2", "pr1")))
        ok("主节点的暂存没被写脏（两个节点互不影响）",
           repo.load_draft(tid, "print") is None,
           str(repo.load_draft(tid, "print")))

        # 切回主节点：面板回填的是**主节点**那份（这里是内置默认，不是 30,40）
        page._select_stage(_bar("pr1"))
        pump(app, times=6)
        ok("切回主节点不回填副本节点的参数",
           panel.page_margins.text() != "30,40",
           panel.page_margins.text())
    finally:
        try:
            page.shutdown_all_workers()
        except Exception:  # noqa: BLE001 — 收尾失败不该让整个模块报错
            pass
        page.deleteLater()
        repo.delete_task(tid)
        ok("多节点样本任务已清理", repo.get_task(tid) is None)

    # ------------------------------- ③ 用户实测流程图（2026-10-17 两条报障）
    #  图片拼版(入口) → 检测文本框 → 图片去底色 → 是否拼版 →(是) 图片拼版 → PDF排版
    #
    #  用户报的两条：
    #  ① 第二个「图片拼版」在任务详情里**不显示**（流程条只画了一个可选节点）；
    #  ② 「图片拼版」做第一个节点时**没有任何输入入口**（三颗输入按钮全藏）。
    _check_entry_optional_flow(ctx, repo)


def _check_entry_optional_flow(ctx, repo) -> None:
    """③ 用户的流程图：两个「图片拼版」+ 拼版做入口。"""
    from tests.selftests._context import ok, pump

    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.steps import ports
    from desktop.steps.bpmn_diagram import (
        KIND_END, KIND_EXCLUSIVE, KIND_TASK, DiagramFlow, DiagramNode, FlowDiagram,
    )

    app = ctx.app
    uid = repo.create_task(ctx.pdf, "hash-multi-node-entry", "拼版做入口")
    # ⚠️ 节点**声明顺序**刻意让「网关分支里那个拼版」在前（与用户 2026-10-17 的
    #    文件一致）：这样入口那个拼版是**副本**（序号（2）、文件带 ~ 后缀），
    #    正好覆盖"版面写进副本、却从主节点读"那条 bug。
    diagram = FlowDiagram(
        nodes=(
            DiagramNode("imp2", KIND_TASK, "图片拼版", stage="imposition"),
            DiagramNode("imp1", KIND_TASK, "图片拼版", stage="imposition"),
            DiagramNode("det", KIND_TASK, "检测文本框", stage="detect"),
            DiagramNode("rb", KIND_TASK, "图片去底色", stage="rembg"),
            DiagramNode("gw", KIND_EXCLUSIVE, "是否拼版"),
            DiagramNode("pr", KIND_TASK, "PDF排版", stage="print"),
            DiagramNode("end", KIND_END, "生成PDF"),
        ),
        flows=(
            DiagramFlow("f1", "imp1", "det"),
            DiagramFlow("f2", "det", "rb"),
            DiagramFlow("f3", "rb", "gw"),
            DiagramFlow("f4", "gw", "pr", "否"),
            DiagramFlow("f5", "gw", "imp2", "是"),
            DiagramFlow("f6", "imp2", "pr"),
            DiagramFlow("f7", "pr", "end"),
        ),
    )
    repo.save_task_diagram(uid, diagram)
    page = TaskDetailPage(repo)
    try:
        # ---- 判据层：入口是**节点**（不能因为第二个同类节点有上游就判成"没有入口"）----
        ok("入口节点 = 第一个「图片拼版」（不是按阶段判出来的空答案）",
           ports.flow_entry_node(diagram) == "imp1",
           str(ports.flow_entry_node(diagram)))
        ok("入口要用户提供**图片**（不是 PDF）",
           ports.flow_entry_input_kind(diagram) == "images",
           ports.flow_entry_input_kind(diagram))

        page.set_task(uid)
        pump(app, times=8)
        bar = page.step_bar
        ok("流程条上**两个**「图片拼版」各占一格（不是只画一个）",
           len(bar.optional_nodes) == 2
           and bar.optional_bar_indices == [0, 3],
           str(bar.optional_bar_indices))
        ok("两个可选节点都显示（图里有这一格）",
           all(not node.isHidden() for node in bar.optional_nodes),
           str([node.isHidden() for node in bar.optional_nodes]))
        ok("标题带序号可区分（序号按**流程条先后**，不是文件声明顺序）",
           [n.title_label.text() for n in bar.optional_nodes]
           == ["图片拼版（1）", "图片拼版（2）"],
           str([n.title_label.text() for n in bar.optional_nodes]))
        ok("点第二个「图片拼版」切到**它自己**那一格",
           _click_optional(bar, page, app, 1) == 3,
           str(page.step_bar._current))
        ok("切过去后节点上下文就是网关分支那个拼版节点",
           page.current_node() == "imp2", str(page.current_node()))
        # 切回入口那个拼版节点（后面的输入/版面断言都按它算）
        _click_optional(bar, page, app, 0)
        ok("点回入口拼版节点", page.current_node() == "imp1",
           str(page.current_node()))

        # ---- 输入入口：拼版做第一个节点也要有图片入口 ----
        ok("页头显示**图片/文件夹**入口、藏起 PDF 按钮",
           not page.insert_button.isHidden()
           and not page.insert_dir_button.isHidden()
           and page.source_button.isHidden())
        ok("缺输入时红字提示指向「放图」而不是「选 PDF」",
           bool(page.source_warning.text()) and "图片" in page.source_warning.text(),
           page.source_warning.text())

        # ---- 入口节点的输入 = 入口图片目录（不是下游的 stages/rembg）----
        task_dir = repo.task_dir(uid)
        ok("入口节点（imp1）的 pages 输入回落到 stages/input",
           repo.node_input(uid, "imp1", "pages")
           == repo.task_input_dir(uid),
           str(repo.node_input(uid, "imp1", "pages")))
        ok("第二个拼版节点（imp2）的输入来自连线上游 stages/rembg",
           repo.node_input(uid, "imp2", "pages")
           == task_dir / "stages" / "rembg",
           str(repo.node_input(uid, "imp2", "pages")))

        from PySide6.QtGui import QImage

        entry = repo.task_input_dir(uid)
        entry.mkdir(parents=True, exist_ok=True)
        img = QImage(40, 60, QImage.Format.Format_RGB32)
        img.fill(0xFFFFFF)
        img.save(str(entry / "0001.png"))
        page._select_stage(0)
        pump(app, times=6)
        ok("入口节点能选到用户放进 stages/input 的图",
           [p.name for p in page.imposition_source_files()] == ["0001.png"],
           str([p.name for p in page.imposition_source_files()]))
        ok("放进图后红字收起（提示不残留）",
           not page.source_warning.isVisible()
           or not page._missing_entry_images(),
           page.source_warning.text())

        # ---- 拼版版面：**写读必须同一个文件**（否则选完页窗口里一张也不显示）----
        # 用户 2026-10-17 实测：拼版做第一个节点时，选 122 页 + 开始拼版后
        # 左侧还是"还没有拼版页"——写进了 `drafts/imposition~<节点>.json`，
        # 读的却是主节点那份 `drafts/imposition.json`。
        ok("当前拼版节点是**副本**（主节点是文件声明里的第一个）",
           page._imposition_scope()["node_id"] == page.current_node()
           and page._imposition_scope()["node_id"]
           != page._imposition_flag_scope()["node_id"],
           f"{page._imposition_scope()} vs {page._imposition_flag_scope()}")
        seed = dict(page._imposition_doc())
        # ⚠️ 页里必须有**真实条目**：``normalize_doc`` 会丢掉没有 items 的空页
        #    （那是"半截数据"，不是一页版面），拿空页测这条会假红。
        seed["pages"] = [{
            "items": [{
                "file": str(entry / "0001.png"),
                "rect": [0.0, 0.0, 40.0, 60.0],
                "rotation": 0.0,
            }],
        }]
        repo.save_imposition_doc(uid, seed, **page._imposition_scope())
        ok("_imposition_doc 读的就是刚才写进去的那份（版面写读同路径）",
           len(page._imposition_pages()) == 1,
           f"pages={len(page._imposition_pages())} path="
           f"{repo.imposition_doc_path(uid, **page._imposition_scope()).name}")
        ok("版面文件落在副本节点的 drafts/imposition~<节点>.json",
           repo.imposition_doc_path(uid, **page._imposition_scope()).name
           == f"imposition~{page.current_node()}.json",
           repo.imposition_doc_path(uid, **page._imposition_scope()).name)
        # 视图也要真的拿到页清单（左列/画布不再"空纸 + 还没有拼版页"）
        page._refresh_imposition_view()
        pump(app, times=4)
        ok("拼版视图（左列/画布）拿到了本节点的页清单",
           len(page.imposition_view.pages()) == 1,
           str(len(page.imposition_view.pages())))

        # ---- 「上一个节点的输出 = 下一个节点的输入」（用户 2026-10-17 第 3 条）----
        # 检测文本框的上游是拼版 ⇒ 它的输入目录必须是**拼版成品目录**；页清单
        # 也必须跟着这份产物走（不是入口图片、也不是提取的 pages.json）。
        composed = repo.node_or_stage_output(uid, "imp1", "imposition")
        composed.mkdir(parents=True, exist_ok=True)
        shot = QImage(120, 180, QImage.Format.Format_RGB32)
        shot.fill(0xFFFFFF)
        shot.save(str(composed / "0001.png"))
        ok("检测文本框的 pages 输入 = 拼版成品目录（图上是这么连的）",
           repo.node_input(uid, "det", "pages") == composed,
           f"{repo.node_input(uid, 'det', 'pages')} != {composed}")

        page._select_stage(_step_bar_index(page, "detect"))
        pump(app, times=8)
        ok("第二步的页清单跟着**上游产物**走（不是入口图片、不是旧清单）",
           [p.name for p in page._manifest_paths()] == ["0001.png"],
           str([p.name for p in page._manifest_paths()]))
        ok("清单是**任务级**一份（不按步骤分文件——否则在第二步删掉的页会在"
           "第三步复活）",
           repo.pages_path(uid, **page._node_scope()).name == "pages.json",
           repo.pages_path(uid, **page._node_scope()).name)
        ok("入口图片（stages/input）不在第二步的清单里",
           all("input" not in str(p).replace("\\", "/").split("/")[-2:]
               for p in page._manifest_paths()),
           str([str(p) for p in page._manifest_paths()]))
    finally:
        try:
            page.shutdown_all_workers()
        except Exception:  # noqa: BLE001
            pass
        page.deleteLater()
        repo.delete_task(uid)
        ok("用户流程图样本任务已清理", repo.get_task(uid) is None)


def _step_bar_index(page, step: str) -> int:
    """界面步骤 key → 格序（本模块里必命中；断言代替 None 收窄）。"""
    index = page.bar_index_of_step(step)
    assert index is not None, step
    return index


def _click_optional(bar, page, app, order: int) -> int:
    """点第 ``order`` 个可选节点，返回切换后的格序（跑一遍真实信号链）。"""
    from tests.selftests._context import pump

    bar.optional_nodes[order].clicked.emit()
    pump(app, times=6)
    return int(page.step_bar._current)
