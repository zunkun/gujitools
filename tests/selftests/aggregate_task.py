# -*- coding: utf-8 -*-
"""聚合任务自测：流程派生、store 落库、创建面板、列表标记。

聚合任务（用户 2026-11-17）：选几个已有任务在同一节点上的产物作输入
（顺序有意义），流程从那个节点开始——前面的丢弃、后面的接上；本轮交付
创建与展示（选成员弹窗 / 排序 / 起始节点联动流程图 / 落库 / 列表标记），
执行链路下一轮接。
"""

NAME = "aggregate_task"
DEPENDS = ["tasklist"]
TITLE = "聚合任务"


def run(ctx) -> None:
    from desktop.components.aggregate_create_panel import (
        MEMBER_HEADER_HEIGHT,
        MEMBER_PAGE_SIZE,
        AggregateCreatePanel,
        AggregateMemberPicker,
        DEFAULT_START_STAGE,
    )
    from desktop.pages.createtask.page import (
        CreateTaskPage,
        ROUTE_CREATE,
        TAB_AGGREGATE,
        TAB_TASK,
    )
    from desktop.steps.aggregate import (
        AGGREGATE_START_LABEL,
        AGGREGATE_START_STAGES,
        aggregate_start_label,
        derive_aggregate_diagram,
    )
    from desktop.ui import theme as T
    from desktop.ui.widgets import SegmentedToggle, StatusChip
    from qfluentwidgets import BodyLabel, CheckBox, PushButton
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLabel, QScrollArea
    from tests.selftests._context import ok, pump

    app, repo, w = ctx.app, ctx.repo, ctx.w

    # ============================================== 1. 流程派生（纯逻辑）
    expect = {
        "extract": ("extract", "detect", "rembg", "imposition", "print"),
        "detect": ("detect", "rembg", "imposition", "print"),
        "rembg": ("rembg", "imposition", "print"),
        "imposition": ("imposition", "print"),
        "print": ("print",),
    }
    for stage, stages in expect.items():
        diagram = derive_aggregate_diagram(stage)
        ok(
            f"派生[{stage}]：起始节点之后的阶段齐全（前面丢弃）",
            diagram.stage_order() == stages,
            str(diagram.stage_order()),
        )
        starts = [n for n in diagram.nodes if n.kind == "startEvent"]
        ends = [n for n in diagram.nodes if n.kind == "endEvent"]
        ok(
            f"派生[{stage}]：开始事件叫「{AGGREGATE_START_LABEL}」且唯一",
            len(starts) == 1 and starts[0].name == AGGREGATE_START_LABEL,
            str([n.name for n in starts]),
        )
        ok(
            f"派生[{stage}]：结束事件「生成PDF」还在",
            len(ends) == 1 and ends[0].name == "生成PDF",
            str([n.name for n in ends]),
        )
        # 用户 2026-11-18：extract **可以**当起始节点（"提取只能使用其产生的
        # 结果，没有输入源"）；除它之外的起点前面都被裁掉，图里不该再有提取。
        ok(
            f"派生[{stage}]：{'保留' if stage == 'extract' else '没有'}「提取图片」",
            ("extract" in diagram.stage_order()) == (stage == "extract"),
            str(diagram.stage_order()),
        )
        gateways = [n for n in diagram.nodes if n.is_gateway]
        should_keep_gw = stage in ("extract", "detect", "rembg")
        ok(
            f"派生[{stage}]：「是否拼版」网关{'保留' if should_keep_gw else '丢弃'}",
            bool(gateways) == should_keep_gw,
            f"网关数 {len(gateways)}",
        )
        # 开始事件必须连到起始节点
        out = [f for f in diagram.flows if f.source == starts[0].id]
        first = diagram.node(out[0].target) if out else None
        ok(
            f"派生[{stage}]：开始事件 → 起始节点「{aggregate_start_label(stage)}」",
            first is not None and first.stage == stage,
            f"target={getattr(first, 'stage', None)}",
        )
        # 派生图已重排坐标（能直接 save，不依赖模板的 DI 段）
        ok(
            f"派生[{stage}]：每个节点都有坐标",
            all(n.id in diagram.boxes for n in diagram.nodes),
            "",
        )

    ok(
        "派生：垃圾 key 是空图（不抛异常）",
        not derive_aggregate_diagram("nope").nodes,
        "",
    )
    ok(
        "起始节点清单含 extract（用户 2026-11-18 改口径）",
        "extract" in AGGREGATE_START_STAGES,
        str(AGGREGATE_START_STAGES),
    )

    # ---- 注释（节点说明）：被丢弃节点的注释必须跟着丢 ----
    # 用户 2026-11-17 实测：起始节点选「图片拼版」后，图上还挂着
    # 「检测古籍文本框」「从文件提取图片」「用户上传PDF/DjVu文件」
    # 「古籍图片去底色」四条说明——节点没了、说明还在。
    notes_imposition = {n.text for n in derive_aggregate_diagram("imposition").notes}
    ok(
        "派生[imposition]：只留保留节点的注释（丢弃节点的说明一起丢）",
        notes_imposition == {"古籍图片拼版", "图片排版生成PDF页面"},
        str(notes_imposition),
    )
    notes_print = {n.text for n in derive_aggregate_diagram("print").notes}
    ok(
        "派生[print]：只剩「PDF排版」的注释",
        notes_print == {"图片排版生成PDF页面"},
        str(notes_print),
    )
    notes_detect = {n.text for n in derive_aggregate_diagram("detect").notes}
    ok(
        "派生[detect]：只剩检测之后的注释（上传/提取两条没了）",
        notes_detect
        == {"检测古籍文本框", "古籍图片拼版", "古籍图片去底色", "图片排版生成PDF页面"},
        str(notes_detect),
    )
    diagram_detect = derive_aggregate_diagram("detect")
    ok(
        "派生：留下的注释都有坐标（否则画在画布外=看着没显示）",
        all(n.id in diagram_detect.boxes for n in diagram_detect.notes),
        "",
    )
    ok(
        "派生：注释挂接关系指向的宿主节点都还在图上",
        all(
            diagram_detect.node(note_links_host) is not None
            for note_links_host in diagram_detect.note_links.values()
        ),
        str(diagram_detect.note_links),
    )

    # ---- 候选起始节点 = 成员**已完成**节点的并集（用户 2026-11-18）----
    from desktop.steps.aggregate import any_member_stages, missing_members

    # 用户实证：三个子集分别完成 {提取,检测} / {提取,检测} / {提取,去底}
    # ⇒ 交集只剩 extract（旧口径下被 extract 再过滤一次就成空集，列表退化成
    #    兜底全集：检测/去底/拼版/PDF排版——用户看到的正是这个 bug）。
    split_done = [
        ("extract", "detect"),
        ("extract", "detect"),
        ("extract", "rembg"),
    ]
    ok(
        "候选：取成员的**并集**（谁完成过就列谁，按拓扑序）",
        any_member_stages(split_done) == ("extract", "detect", "rembg"),
        str(any_member_stages(split_done)),
    )
    ok(
        "候选：没人完成过的节点（拼版/PDF排版）不出现",
        not {"imposition", "print"} & set(any_member_stages(split_done)),
        str(any_member_stages(split_done)),
    )
    ok(
        "候选：空输入返回空元组（调用方兜底，不在这里猜）",
        any_member_stages([]) == (),
        str(any_member_stages([])),
    )
    ok(
        "候选：缺这个节点的成员被点名（下标，按成员顺序）",
        missing_members("rembg", split_done) == (0, 1)
        and missing_members("extract", split_done) == (),
        f"{missing_members('rembg', split_done)} / {missing_members('extract', split_done)}",
    )
    ok(
        "候选：没选成员时不算「谁缺」（别报假警）",
        missing_members("rembg", []) == (),
        str(missing_members("rembg", [])),
    )

    # ============================================== 2. store 落库
    tid_a = repo.create_task(ctx.pdf, "agg-hash-1", "子集·上册")
    tid_b = repo.create_task(ctx.big_pdf, "agg-hash-2", "子集·下册")
    agg_id = repo.create_aggregate_task([tid_a, tid_b], "imposition", "合并本（上+下）")
    record = repo.get_task(agg_id)
    ok(
        "聚合任务：record 带 kind=aggregate",
        record.get("kind") == "aggregate",
        str(record.get("kind")),
    )
    ok(
        "聚合任务：members 按用户排序保存",
        record.get("members") == [tid_a, tid_b],
        str(record.get("members")),
    )
    ok(
        "聚合任务：member_stage 落库",
        record.get("member_stage") == "imposition",
        str(record.get("member_stage")),
    )
    ok(
        "聚合任务：不吃源文件（source_path 空串）",
        record.get("source_path") == "",
        str(record.get("source_path")),
    )
    flow = repo.task_diagram(agg_id)
    ok(
        "聚合任务：flow.bpmn 是派生图（拼版→PDF排版）",
        flow.stage_order() == ("imposition", "print"),
        str(flow.stage_order()),
    )
    # ⚠️ 绝不能是默认模板的字节拷贝（模板里有 extract，语义不对）
    from desktop.steps.scheduler import default_template_path

    template_bytes = default_template_path().read_bytes()
    task_flow_bytes = (repo.task_dir(agg_id) / "flow.bpmn").read_bytes()
    ok(
        "聚合任务：flow.bpmn 不是默认模板的字节拷贝",
        task_flow_bytes != template_bytes,
        "",
    )

    # 名字回落 + diagram 优先
    agg_id2 = repo.create_aggregate_task([tid_b], "detect", "")
    ok(
        "聚合任务：名字留空回落「任务#号」",
        repo.get_task(agg_id2)["name"] == f"任务#{agg_id2}",
        repo.get_task(agg_id2)["name"],
    )
    ok(
        "聚合任务：member_stage=detect ⇒ flow 从检测开始",
        repo.task_diagram(agg_id2).stage_order()
        == ("detect", "rembg", "imposition", "print"),
        str(repo.task_diagram(agg_id2).stage_order()),
    )

    # 每成员各自的节点（用户 2026-11-17 晚口径）
    agg_id3 = repo.create_aggregate_task(
        [tid_a, tid_b], member_stages=["detect", "print"], name="混搭"
    )
    rec3 = repo.get_task(agg_id3)
    ok(
        "聚合任务：member_stages 逐成员落库",
        rec3.get("member_stages") == ["detect", "print"],
        str(rec3.get("member_stages")),
    )
    ok(
        "聚合任务：member_stage 恒等于成员节点里最早的（detect）",
        rec3.get("member_stage") == "detect",
        str(rec3.get("member_stage")),
    )
    ok(
        "聚合任务：混搭节点 ⇒ 流程从最早的 detect 开始",
        repo.task_diagram(agg_id3).stage_order()[0] == "detect",
        str(repo.task_diagram(agg_id3).stage_order()),
    )

    # 非法输入
    for members, stage, label in (
        ([], "imposition", "空成员"),
        (["9999"], "imposition", "不存在的成员"),
        ([tid_a], "nope", "垃圾起始节点"),
    ):
        try:
            repo.create_aggregate_task(members, stage, "x")
            ok(f"聚合任务拒绝：{label}", False, "竟然没有抛 ValueError")
        except ValueError:
            ok(f"聚合任务拒绝：{label}", True, "")

    # 合法：extract 也能当起始节点（用户 2026-11-18）——流程从提取开始，
    # 汇集只搬成员的提取产物（见 2b 的 extract 段）
    agg_ext = repo.create_aggregate_task([tid_a], "extract", "从提取开始")
    ok(
        "聚合任务：extract 起始是合法的（流程含提取）",
        repo.task_diagram(agg_ext).stage_order()[0] == "extract",
        str(repo.task_diagram(agg_ext).stage_order()),
    )
    repo.delete_task(agg_ext)

    # 非法 member_stages
    for members, stages, label in (
        ([tid_a, tid_b], ["detect"], "节点数与成员数不一致"),
        ([tid_a], ["nope"], "垃圾成员节点"),
    ):
        try:
            repo.create_aggregate_task(members, member_stages=stages, name="x")
            ok(f"聚合任务拒绝：{label}", False, "竟然没有抛 ValueError")
        except ValueError:
            ok(f"聚合任务拒绝：{label}", True, "")

    # ---- 已完成节点清单（起始节点候选的数据源）----
    # tid_a：extract/detect 成功、rembg 失败 ⇒ 已完成 = extract + detect
    for stage in ("extract", "detect"):
        run_id = repo.create_stage_run(tid_a, stage, {})
        repo.finish_stage(tid_a, run_id, "success")
    run_id = repo.create_stage_run(tid_a, "rembg", {})
    repo.finish_stage(tid_a, run_id, "failed")
    ok(
        "store：已完成节点 = 历史上成功过且在流程里（extract + detect）",
        repo.completed_aggregate_stages(tid_a) == ["extract", "detect"],
        str(repo.completed_aggregate_stages(tid_a)),
    )
    ok(
        "store：extract 完成后也在候选里（用户 2026-11-18 改口径）",
        "extract" in repo.completed_aggregate_stages(tid_a),
        str(repo.completed_aggregate_stages(tid_a)),
    )
    ok(
        "store：失败过的节点不算完成（rembg failed）",
        "rembg" not in repo.completed_aggregate_stages(tid_a),
        str(repo.completed_aggregate_stages(tid_a)),
    )

    # ============================================== 2b. 成员产物汇集（执行链路）
    # 用户 2026-11-17（本轮）：「起始就是自定义任务流程，将选择的子任务的开始
    # 节点作为输入……两个子任务的去底输入作为新聚合任务的输入，去底产出也
    # 同样复制到新的聚合任务的产出中……注意子任务排序，输入的排序也要一致」。
    from pathlib import Path

    from PIL import Image

    from desktop.services.aggregate_ingest import (
        aggregate_page_name,
        plan_ingest,
        run_ingest,
    )
    from desktop.utils.files import list_stage_images
    from utils.sort_utils import natural_sort_key

    def _make_images(directory: Path, names, size=(40, 60)) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        for name in names:
            Image.new("RGB", size, "white").save(directory / name)

    ok(
        "页名规则：成员序号 3 位 + 原页名（001_1.jpg）",
        aggregate_page_name(1, "10-l.jpg") == "001_10-l.jpg",
        aggregate_page_name(1, "10-l.jpg"),
    )

    tid_c = repo.create_task(ctx.pdf, "agg-hash-c", "子集·上")
    tid_d = repo.create_task(ctx.big_pdf, "agg-hash-d", "子集·下")
    # tid_c 三页（含一张半幅 -l），tid_d 两页
    for tid, pages in (
        (tid_c, ["1.jpg", "2.jpg", "10-l.jpg"]),
        (tid_d, ["1.jpg", "2.jpg"]),
    ):
        root_dir = repo.task_dir(tid)
        _make_images(root_dir / "stages" / "extract", pages)
        _make_images(root_dir / "stages" / "detect", pages)
        _make_images(
            root_dir / "stages" / "rembg",
            [p.replace(".jpg", ".png") for p in pages],
        )
        repo.save_image_sizes_batch(tid, {Path(p).stem: (40, 60) for p in pages})
        for stage in ("extract", "detect", "detect_submit", "rembg"):
            run_id = repo.create_stage_run(tid, stage, {})
            repo.finish_stage(tid, run_id, "success")

    # 成员顺序 [下, 上] —— 汇集必须**照这个顺序**排
    agg_ing = repo.create_aggregate_task([tid_d, tid_c], "rembg", "汇集·去底")
    plan = plan_ingest(repo, agg_ing)
    ok(
        "汇集计划：起点=去底色，产出落在 stages/rembg",
        plan is not None
        and plan.start_stage == "rembg"
        and plan.entry_dir == repo.task_dir(agg_ing) / "stages" / "input"
        and plan.output_dir == repo.task_dir(agg_ing) / "stages" / "rembg",
        f"{plan.start_stage if plan else None}",
    )
    ok(
        "汇集计划：只搬产出（用户 2026-11-18「结果就是聚合任务的输入数据」）",
        plan is not None and plan.input_copies == (),
        str([c.target.name for c in plan.input_copies]) if plan else "",
    )
    ok(
        "汇集计划：产出按成员顺序（001=下、002=上）且成员内按页序",
        [c.target.name for c in plan.output_copies]
        == ["001_1.png", "001_2.png", "002_1.png", "002_2.png", "002_10-l.png"],
        str([c.target.name for c in plan.output_copies]),
    )
    ok(
        "汇集计划：页面清单按成员顺序编号 1..5",
        [p["label"] for p in plan.pages] == ["1", "2", "3", "4", "5"],
        str([p["label"] for p in plan.pages]),
    )

    result = run_ingest(repo, agg_ing)
    entry_dir = repo.task_dir(agg_ing) / "stages" / "input"
    out_dir = repo.task_dir(agg_ing) / "stages" / "rembg"
    entries = [p.name for p in list_stage_images(entry_dir)]
    ok(
        "汇集：入口目录不再留一份上游原图（只搬结果）",
        entries == [],
        str(entries),
    )
    ok(
        "汇集：产出目录按成员顺序拼好（自然序 = 成员顺序）",
        [p.name for p in list_stage_images(out_dir)]
        == ["001_1.png", "001_2.png", "002_1.png", "002_2.png", "002_10-l.png"]
        and [p.name for p in list_stage_images(out_dir)]
        == sorted(
            [p.name for p in list_stage_images(out_dir)], key=natural_sort_key
        ),
        str([p.name for p in list_stage_images(out_dir)]),
    )
    ok(
        "汇集：结果统计（5 页 / 5 个文件）",
        (result.pages, result.copied) == (5, 5),
        f"{result.pages}/{result.copied}",
    )
    pages_json = repo.load_pages(agg_ing)
    ok(
        "汇集：pages.json 指向聚合任务里那份**产出**（不是成员的、也不是原图）",
        [p["label"] for p in pages_json] == ["1", "2", "3", "4", "5"]
        and all(Path(p["file"]).parent == out_dir for p in pages_json),
        str(pages_json[:2]),
    )
    ok(
        "汇集：sizes.json 跟着新页名落地（框坐标有基准）",
        repo.image_size(agg_ing, "002_10-l") == (40, 60),
        str(repo.image_size(agg_ing, "002_10-l")),
    )
    ok(
        "汇集：起点（去底色）被记为已完成（否则第四步看不到产出）",
        repo.completed_aggregate_stages(agg_ing) == ["rembg"],
        str(repo.completed_aggregate_stages(agg_ing)),
    )
    ok(
        "汇集：第四步的上游（去底色）判定为已生效（能直接排版/生成PDF）",
        repo.stage_input_effective(agg_ing, "print", "pages"),
        "",
    )

    # 幂等 + 清陈旧：成员少了一页 ⇒ 旧页从聚合任务里消失，用户的图不动
    (repo.task_dir(tid_c) / "stages" / "detect" / "2.jpg").unlink()
    (repo.task_dir(tid_c) / "stages" / "rembg" / "2.png").unlink()
    stray = entry_dir / "用户自己放的图.png"
    Image.new("RGB", (10, 10), "white").save(stray)
    run_ingest(repo, agg_ing)
    names_now = [p.name for p in list_stage_images(out_dir)]
    ok(
        "汇集：重跑清掉不再需要的旧页（002_2 消失）",
        "002_2.png" not in names_now and len(names_now) == 4,
        str(names_now),
    )
    ok("汇集：重跑不删用户自己放进的图", stray.exists(), "")

    # ---- 起点=检测：检测框按同一前缀搬过来 ----
    tid_e = repo.create_task(ctx.pdf, "agg-hash-e", "子集·检测")
    root_e = repo.task_dir(tid_e)
    _make_images(root_e / "stages" / "extract", ["1.jpg", "2.jpg"])
    _make_images(root_e / "stages" / "detect", ["1.jpg", "2.jpg"])
    repo.save_image_sizes_batch(tid_e, {"1": (40, 60), "2": (40, 60)})
    repo.save_detect_boxes_batch(
        tid_e, {"1": [[0, 0, 10, 10]], "2": [[0, 0, 5, 5]]}
    )
    for stage in ("extract", "detect", "detect_submit"):
        run_id = repo.create_stage_run(tid_e, stage, {})
        repo.finish_stage(tid_e, run_id, "success")
    agg_det = repo.create_aggregate_task([tid_e], "detect", "汇集·检测")
    run_ingest(repo, agg_det)
    ok(
        "汇集[检测]：框文件按新页名搬过来（001_1 / 001_2）",
        sorted(repo.detect_boxes_all(agg_det)) == ["001_1", "001_2"],
        str(sorted(repo.detect_boxes_all(agg_det))),
    )
    ok(
        "汇集[检测]：检测的**两个动作**都记为成功（提交不过期）",
        repo.node_action_executed(
            agg_det, repo.task_diagram(agg_det).node_ids_of("detect")[0], "detect"
        )
        and repo.node_action_executed(
            agg_det,
            repo.task_diagram(agg_det).node_ids_of("detect")[0],
            "detect_submit",
        )
        and repo.detect_submit_fresh(
            agg_det, repo.task_diagram(agg_det).node_ids_of("detect")[0]
        ),
        "",
    )

    # ---- 起点=提取：只搬提取产物（它没有输入源）----
    # 用户 2026-11-18：「提取可选，但是提取只能使用其产生的结果，没有输入源」
    agg_ext2 = repo.create_aggregate_task([tid_e, tid_c], "extract", "汇集·提取")
    ext_plan = plan_ingest(repo, agg_ext2)
    ok(
        "汇集[提取]：没有输入复制（提取没有上游），只有产出",
        ext_plan is not None
        and ext_plan.input_copies == ()
        and [c.target.name for c in ext_plan.output_copies]
        == ["001_1.jpg", "001_2.jpg", "002_1.jpg", "002_2.jpg", "002_10-l.jpg"],
        str([c.target.name for c in ext_plan.output_copies]) if ext_plan else "",
    )
    ext_result = run_ingest(repo, agg_ext2)
    ext_out = repo.task_dir(agg_ext2) / "stages" / "extract"
    ok(
        "汇集[提取]：提取产物落在 stages/extract，页清单按成员顺序",
        [p.name for p in list_stage_images(ext_out)]
        == ["001_1.jpg", "001_2.jpg", "002_1.jpg", "002_2.jpg", "002_10-l.jpg"]
        and [p["label"] for p in repo.load_pages(agg_ext2)] == ["1", "2", "3", "4", "5"],
        str([p.name for p in list_stage_images(ext_out)]),
    )
    ok(
        "汇集[提取]：起点记为已完成（检测可以直接跑）",
        repo.completed_aggregate_stages(agg_ext2) == ["extract"]
        and not ext_result.notes,
        f"{repo.completed_aggregate_stages(agg_ext2)} / {ext_result.notes}",
    )

    # ---- 起点=PDF排版：成员的 PDF 按顺序合并成一本 ----
    try:
        import pymupdf as fitz
    except ImportError:  # 老版 PyMuPDF
        import fitz

    for tid, count in ((tid_d, 3), (tid_e, 2)):
        doc = fitz.open()
        for _ in range(count):
            doc.new_page()
        target = repo.task_dir(tid) / "stages" / "print" / "print.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(target))
        doc.close()
        run_id = repo.create_stage_run(tid, "print", {})
        repo.finish_stage(tid, run_id, "success", str(target))
    agg_pdf = repo.create_aggregate_task([tid_d, tid_e], "print", "汇集·PDF")
    pdf_result = run_ingest(repo, agg_pdf)
    merged = repo.task_dir(agg_pdf) / "stages" / "print" / "print.pdf"
    ok(
        "汇集[PDF排版]：成员的 PDF 按成员顺序合并成一本（3+2=5 页）",
        merged.is_file() and pdf_result.pdf_pages == 5,
        f"{pdf_result.pdf_pages}",
    )
    if merged.is_file():
        doc = fitz.open(str(merged))
        ok("汇集[PDF排版]：合并后的 PDF 真实页数也是 5", doc.page_count == 5, str(doc.page_count))
        doc.close()
    ok(
        "汇集[PDF排版]：产出 PDF 落在 print 的落点上（第四步能预览/下载）",
        merged.parent == repo.scoped_stage_dir(agg_pdf, None, "print"),
        str(merged.parent),
    )
    # 起点=PDF排版/拼版的聚合任务**不走**"只读图片清单"那条路：它们的产物
    # 不是图片批（一本 PDF / 一份版面），各自的查看器照旧显示（见
    # ``manifest._aggregate_start_output_dir`` 的 print/imposition 早退）。
    d_pdf = ctx.d
    ok("详情页：聚合（起点=PDF排版）装得进去", d_pdf.set_task(agg_pdf) is True, "")
    pump(app, times=8)
    ok(
        "详情页：PDF排版起点不算「输入节点」（PDF 预览/下载照旧）",
        d_pdf.current_stage() == "print"
        and not d_pdf._is_aggregate_input_node()
        and d_pdf.run_button.isEnabled(),
        f"{d_pdf.current_stage()} / {d_pdf._is_aggregate_input_node()}"
        f" / {d_pdf.run_button.isEnabled()}",
    )

    # 清场本段建的任务
    for tid in (agg_ing, agg_det, agg_ext2, agg_pdf, tid_c, tid_d, tid_e):
        if repo.get_task(tid):
            repo.delete_task(tid)

    # ============================================== 3. 创建面板
    panel = AggregateCreatePanel(repo)
    ok(
        "面板：没成员时流程根回落默认「图片拼版」",
        panel.current_stage() == DEFAULT_START_STAGE == "imposition",
        panel.current_stage(),
    )
    ok("面板：没选成员不能提交", not panel.can_submit(), "")
    ok(
        "面板：没编辑过流程 ⇒ result_diagram 为 None（store 落派生图）",
        panel.result_diagram() is None,
        "",
    )

    panel.set_members([tid_b, tid_a])
    ok(
        "面板：成员按设置顺序回填",
        panel.members() == [tid_b, tid_a],
        str(panel.members()),
    )
    # tid_b 什么都没跑、tid_a 完成到检测 ⇒ 没有"人人都完成"的公共节点，
    # 默认落到并集里**最靠前**的那个（起点越早越不丢页）
    ok(
        "面板：默认落点 = 并集最早那个（缺页风险最小）",
        panel.current_stage() == "extract",
        panel.current_stage(),
    )
    ok(
        "面板：起始节点全体共用（各成员节点值相同）",
        panel.member_stages() == ["extract", "extract"],
        str(panel.member_stages()),
    )
    ok("面板：选了成员可以提交", panel.can_submit(), "")

    # 成员提交（信号负载：成员 + 各成员节点）
    got: list = []
    panel.submitted.connect(lambda m, s, d: got.append((m, s, d)))
    panel.submit()
    ok(
        "面板：submit 发出 (成员, 各成员节点, None)",
        got == [([tid_b, tid_a], ["extract", "extract"], None)],
        str(got),
    )

    # 排序交互：上移/下移/移除（行内按钮入口；⚠️ 移动后当前行跟随被移的那条）
    panel.member_table.selectRow(1)
    panel._on_move(-1)
    ok(
        "面板：上移真的会交换（[下册,上册]→[上册,下册]）",
        panel.members() == [tid_a, tid_b],
        str(panel.members()),
    )
    panel._on_move(1)  # 当前行 0，下移 → 还原
    ok(
        "面板：再下移回原位（顺序还原）",
        panel.members() == [tid_b, tid_a],
        str(panel.members()),
    )
    panel.member_table.selectRow(0)
    panel._on_move(-1)
    ok(
        "面板：第 0 条再上移不动（越界安全）",
        panel.members() == [tid_b, tid_a],
        str(panel.members()),
    )
    panel.member_table.selectRow(1)
    panel._on_move(1)
    ok(
        "面板：末条下移不动（越界安全）",
        panel.members() == [tid_b, tid_a],
        str(panel.members()),
    )
    panel.member_table.selectRow(0)
    panel._on_move(1)
    ok(
        "面板：下移把上册换到前面（顺序真的会变）",
        panel.members() == [tid_a, tid_b],
        str(panel.members()),
    )
    panel.member_table.selectRow(0)
    panel._on_remove()
    ok(
        "面板：移除后只剩一个成员",
        panel.members() == [tid_b] and panel.member_stages() == ["extract"],
        f"{panel.members()} / {panel.member_stages()}",
    )

    # ===== 起始节点：checkbox 单选，候选来自**已完成**的任务节点 =====
    ok(
        "面板：表格列 = 序号/任务名称/任务节点/操作",
        panel.MEMBER_COLUMNS == ["序号", "任务名称", "任务节点", "操作"],
        str(panel.MEMBER_COLUMNS),
    )
    # 任务节点列（只读）：tid_b 什么都没完成 ⇒ 灰字占位
    node_wrap = panel.member_table.cellWidget(0, 2)
    node_texts = [l.text() for l in node_wrap.findChildren(QLabel)]
    ok(
        "面板：没完成任何节点的子任务显示灰字占位",
        node_texts and "暂无已完成节点" in node_texts[0],
        str(node_texts),
    )
    # 操作列「详情」入口：点击冒 detail_requested(该子任务)
    seen_detail: list = []
    panel.detail_requested.connect(seen_detail.append)
    action_wrap = panel.member_table.cellWidget(0, 3)
    detail_btns = action_wrap.findChildren(PushButton)
    ok(
        "面板：操作列有「详情」按钮",
        bool(detail_btns) and detail_btns[0].text() == "详情",
        str([b.text() for b in detail_btns]),
    )
    # 用户 2026-11-17：「移除按钮改成删除按钮」——要文字按钮，不是 × 图标
    ok(
        "面板：移除改成文字「删除」按钮（不再是一枚 × 图标）",
        any(b.text() == "删除" for b in detail_btns),
        str([b.text() for b in detail_btns]),
    )
    _del_btn = next((b for b in detail_btns if b.text() == "删除"), None)
    ok(
        "面板：删除按钮用共享危险色样式（与任务列表行内删除同款）",
        _del_btn is not None
        and _del_btn.styleSheet() == T.danger_button_qss(),
        "无删除按钮" if _del_btn is None else _del_btn.styleSheet()[:40],
    )
    # 同一条反馈：任务节点列 / 操作列都要宽一些
    ok(
        "面板：操作列加宽（容得下 详情+上移+下移+删除）",
        panel.member_table.columnWidth(3) >= 220,
        str(panel.member_table.columnWidth(3)),
    )
    ok(
        "面板：任务节点列不窄于下限（节点名要能显示全）",
        panel.member_table.columnWidth(2) >= panel._STAGE_WIDTH,
        str(panel.member_table.columnWidth(2)),
    )
    # 列宽是**按内容实测**的（用户 2026-11-17：「宽一些，能够显示完整节点」）
    _long_wrap = panel._node_widget(["detect", "rembg", "imposition", "print"])
    panel.member_table.setRowCount(panel.member_table.rowCount() + 1)
    panel.member_table.setCellWidget(
        panel.member_table.rowCount() - 1, 2, _long_wrap)
    panel._fit_stage_column()
    ok(
        "面板：任务节点列宽 ≥ 最长一行的实际所需（长节点串不裁字）",
        panel.member_table.columnWidth(2) >= _long_wrap.sizeHint().width(),
        f"{panel.member_table.columnWidth(2)} vs {_long_wrap.sizeHint().width()}",
    )
    panel._fill_members()          # 还原成真实成员的列宽与行数
    ok(
        "面板：选成员按钮文案是「选择子任务…」",
        panel.pick_button.text().startswith("选择子任务"),
        panel.pick_button.text(),
    )
    detail_btns[0].click()
    ok(
        "面板：点「详情」发 detail_requested(该子任务)",
        seen_detail == [tid_b],
        str(seen_detail),
    )
    ok(
        "面板：候选节点是 checkbox（列举出来，不是下拉框）",
        bool(panel._stage_boxes)
        and all(isinstance(b, CheckBox) for b in panel._stage_boxes.values()),
        str([type(b).__name__ for b in panel._stage_boxes.values()]),
    )
    # 此刻唯一的成员 tid_b 一个节点都没完成 ⇒ 并集为空 ⇒ 兜底列全集
    # （列表空着用户连"先选一个"都做不到），但提示要说真话
    ok(
        "面板：成员一个节点都没完成 ⇒ 兜底列全部候选（按拓扑序）",
        panel.start_candidates()
        == ("extract", "detect", "rembg", "imposition", "print"),
        str(panel.start_candidates()),
    )
    ok(
        "面板：兜底时提示里说明「都还没有完成任何节点」",
        "没有完成" in panel.stage_hint.text(),
        panel.stage_hint.text(),
    )
    ok(
        "面板：候选含「提取图片」（用户 2026-11-18：提取也能当起点）",
        "extract" in panel.start_candidates(),
        str(panel.start_candidates()),
    )
    ok(
        "面板：当前起始节点那一个勾着（其余不勾）",
        [k for k, b in panel._stage_boxes.items() if b.isChecked()]
        == [panel.current_stage()],
        str({k: b.isChecked() for k, b in panel._stage_boxes.items()}),
    )

    # 单选：勾另一个 ⇒ 只留一个；派生图跟着换
    panel._stage_boxes["detect"].setChecked(True)
    ok(
        "面板：勾「检测文本框」⇒ 单选（别的自动灭）+ 图从检测开始",
        panel.current_stage() == "detect"
        and [k for k, b in panel._stage_boxes.items() if b.isChecked()] == ["detect"]
        and panel.current_diagram().stage_order()
        == ("detect", "rembg", "imposition", "print"),
        f"{panel.current_stage()} / {panel.current_diagram().stage_order()}",
    )
    ok("面板：换节点后仍未标记「已编辑」", not panel.uses_custom_flow(), "")
    panel._stage_boxes["print"].setChecked(True)
    ok(
        "面板：勾「PDF排版」⇒ 流程只剩 PDF排版",
        panel.current_stage() == "print"
        and panel.current_diagram().stage_order() == ("print",),
        str(panel.current_diagram().stage_order()),
    )
    # 点掉当前唯一勾选**不生效**（不能出现"没有起始节点"）
    panel._stage_boxes["print"].setChecked(False)
    ok(
        "面板：点掉当前唯一勾选不生效（单选恒有一个）",
        panel.current_stage() == "print" and panel._stage_boxes["print"].isChecked(),
        str({k: b.isChecked() for k, b in panel._stage_boxes.items()}),
    )
    # 不在候选里的节点：设不上去（不偷偷改数据）
    panel.set_start_stage("nope")
    ok(
        "面板：垃圾节点设不上去（不在候选里）",
        panel.current_stage() == "print",
        panel.current_stage(),
    )
    # extract 现在**可以**设上（用户 2026-11-18）
    panel.set_start_stage("extract")
    ok(
        "面板：extract 能当起点（流程从提取开始，全部步骤都在）",
        panel.current_stage() == "extract"
        and panel.current_diagram().stage_order()
        == ("extract", "detect", "rembg", "imposition", "print"),
        f"{panel.current_stage()} / {panel.current_diagram().stage_order()}",
    )
    panel.set_start_stage("print")

    # 候选随成员变：并集口径——tid_a{提取,检测} + tid_b{PDF排版}
    run_id = repo.create_stage_run(tid_b, "print", {})
    repo.finish_stage(tid_b, run_id, "success")
    panel.set_members([tid_a, tid_b])
    ok(
        "面板：成员变了候选跟着变（并集：提取/检测/PDF排版）",
        panel.start_candidates() == ("extract", "detect", "print"),
        str(panel.start_candidates()),
    )
    panel.set_start_stage("detect")
    ok(
        "面板：换成员后起始节点是 detect",
        panel.current_stage() == "detect",
        panel.current_stage(),
    )
    # 任务节点列：tid_a 在第 0 行，显示它已完成的「检测文本框」
    node_texts_a = [
        l.text() for l in panel.member_table.cellWidget(0, 2).findChildren(QLabel)
    ]
    ok(
        "面板：任务节点列显示该子任务已完成的节点（tid_a：检测）",
        node_texts_a and "检测" in "".join(node_texts_a),
        str(node_texts_a),
    )
    panel.set_members([tid_b])
    ok(
        "面板：候选按已完成节点收窄（tid_b 只完成了 print）",
        panel.start_candidates() == ("print",),
        str(panel.start_candidates()),
    )
    ok(
        "面板：起始节点不在新候选里 ⇒ 自动落到候选第一个（图也跟着换）",
        panel.current_stage() == "print"
        and panel.current_diagram().stage_order() == ("print",),
        f"{panel.current_stage()} / {panel.current_diagram().stage_order()}",
    )
    ok(
        "面板：自动落位后勾选框也只勾那一个",
        [k for k, b in panel._stage_boxes.items() if b.isChecked()] == ["print"],
        str({k: b.isChecked() for k, b in panel._stage_boxes.items()}),
    )

    # ===== 用户实证回归（2026-11-18）：三个子集进度不同步 =====
    # 旧口径取**交集**（且去掉 extract）⇒ 三个子集分别完成 {提取,检测} /
    # {提取,检测} / {提取,去底} 时交集为空 ⇒ 兜底列出「检测/去底/拼版/PDF排版」
    # ——用户截图里正是这样：拼版谁都没跑过，却被默认勾上了。
    probe_done = repo.create_task(ctx.pdf, "agg-probe-done", "探针·检测")
    probe_rem = repo.create_task(ctx.big_pdf, "agg-probe-rem", "探针·去底")
    for tid, stages in (
        (probe_done, ("extract", "detect")),
        (probe_rem, ("extract", "rembg")),
    ):
        for stage in stages:
            rid = repo.create_stage_run(tid, stage, {})
            repo.finish_stage(tid, rid, "success")
    panel.set_members([probe_done, probe_rem])
    ok(
        "面板回归：候选 = 生效节点的并集（提取/检测/去底）",
        panel.start_candidates() == ("extract", "detect", "rembg"),
        str(panel.start_candidates()),
    )
    ok(
        "面板回归：谁都没跑过的节点不再出现（拼版/PDF排版）",
        not {"imposition", "print"} & set(panel.start_candidates()),
        str(panel.start_candidates()),
    )
    ok(
        "面板回归：勾选框跟着只列这三个（不再有拼版）",
        list(panel._stage_boxes) == ["extract", "detect", "rembg"],
        str(list(panel._stage_boxes)),
    )
    panel.set_start_stage("rembg")
    ok(
        "面板回归：提示点名没跑去底的那个子任务（别静默少册）",
        "探针·检测" in panel.stage_hint.text()
        and "探针·去底" not in panel.stage_hint.text(),
        panel.stage_hint.text(),
    )
    panel.set_start_stage("extract")
    ok(
        "面板回归：选提取 ⇒ 没有缺节点的子任务（提示里不再点名）",
        "未完成" not in panel.stage_hint.text(),
        panel.stage_hint.text(),
    )
    for tid in (probe_done, probe_rem):
        repo.delete_task(tid)

    # 编辑标记：编辑器内容变了 ⇒ result_diagram 交图
    panel._on_diagram_changed()
    ok(
        "面板：编辑器变更 ⇒ result_diagram 交图",
        panel.result_diagram() is panel.current_diagram(),
        "",
    )
    panel.reset()
    ok(
        "面板：reset 后成员清空、起始节点回默认、候选回全部节点",
        panel.members() == []
        and panel.member_stages() == []
        and panel.current_stage() == DEFAULT_START_STAGE
        and panel.start_candidates()
        == ("extract", "detect", "rembg", "imposition", "print"),
        f"{panel.members()} / {panel.current_stage()} / {panel.start_candidates()}",
    )
    ok("面板：reset 后「已编辑」标记清回", panel.result_diagram() is None, "")

    # ---- 0 成员占位行（用户 2026-11-18：子任务列表 0 条时给一行空白占位）----
    ok(
        "表格：0 个成员也有一行空白占位（不塌成只剩表头）",
        panel.member_table.rowCount() == 1
        and panel.member_table.cellWidget(0, 2) is None
        and panel.member_table.cellWidget(0, 3) is None
        and panel.member_table.item(0, 0) is None
        and panel.member_table.height()
        == MEMBER_HEADER_HEIGHT + panel.MEMBER_ROW_HEIGHT + 2,
        f"{panel.member_table.rowCount()} 行 / 高 {panel.member_table.height()}",
    )
    # 占位行是纯装饰：成员一旦选上，立刻恢复成真数据
    panel.set_members([tid_b])
    ok(
        "表格：占位行只在 0 成员时出现（选上成员回到真数据）",
        panel.member_table.rowCount() == 1
        and panel.member_table.cellWidget(0, 3) is not None,
        f"{panel.member_table.rowCount()} 行 / 操作列="
        f"{panel.member_table.cellWidget(0, 3) is not None}",
    )
    panel.deleteLater()

    # ---- toast 同条去重（用户 2026-11-18：没选子任务报错「提示了多条」）----
    from qfluentwidgets import InfoBar
    from PySide6.QtWidgets import QWidget as _QWidget

    from desktop.ui.toast import show_toast

    host = _QWidget()
    host.resize(400, 300)
    show_toast(host, "warning", "还没有选择子任务", "点「选择子任务…」至少选一个。")
    _bars1 = host.findChildren(InfoBar)
    show_toast(host, "warning", "还没有选择子任务", "点「选择子任务…」至少选一个。")
    _bars2 = host.findChildren(InfoBar)
    ok(
        "toast：同 parent 同标题同内容还挂着 ⇒ 不重复堆叠（只此一条）",
        len(_bars1) == 1 and len(_bars2) == 1 and _bars2[0] is _bars1[0],
        f"{len(_bars1)} / {len(_bars2)}",
    )
    _bars1[0].close()
    pump(app, times=2)
    show_toast(host, "warning", "还没有选择子任务", "点「选择子任务…」至少选一个。")
    _bars3 = host.findChildren(InfoBar)
    ok(
        "toast：上一条关掉后，同样的话能再弹（新的一条）",
        len(_bars3) == 1 and _bars3[0] is not _bars1[0],
        str(len(_bars3)),
    )
    host.deleteLater()

    # ============================================== 4. 成员选择弹窗（不 exec）
    # 行数据与任务管理列表同一来源（含任务节点胶囊），内联跑 worker
    from desktop.workers import TaskRowsWorker

    worker = TaskRowsWorker(repo)
    rows: list = []
    worker.completed.connect(rows.extend)
    worker.run()
    ok(
        "弹窗前置：TaskRowsWorker 行里带了任务节点胶囊",
        all(isinstance(r.get("stages"), list) for r in rows),
        "",
    )

    picker = AggregateMemberPicker(rows, [], None)
    ok(
        "弹窗：候选不含聚合任务（不能嵌套聚合）",
        all(r.get("kind") != "aggregate" for r in picker._all_rows),
        str([r.get("id") for r in picker._all_rows]),
    )
    ok(
        "弹窗：表格列 = （空）/序号/任务名称/任务节点/创建时间（表头不放文字）",
        [
            picker.table.horizontalHeaderItem(i).text()
            for i in range(picker.table.columnCount())
        ]
        == picker.COLUMNS,
        str(
            [
                picker.table.horizontalHeaderItem(i).text()
                for i in range(picker.table.columnCount())
            ]
        ),
    )
    ok("弹窗：默认全不勾", picker.checked_ids() == [], str(picker.checked_ids()))
    # 倒序：新建的任务排在最前（用户 2026-11-18：「任务列表要倒序」）
    ids_desc = [str(r.get("id")) for r in picker._all_rows]
    ok(
        "弹窗：候选按任务号倒序（最新建的排第一页最上）",
        ids_desc == sorted(ids_desc, reverse=True),
        str(ids_desc),
    )
    ok(
        "弹窗：实际驱动本次用例的两个任务也按倒序（tid_b 在前）",
        ids_desc.index(tid_b) < ids_desc.index(tid_a),
        f"{tid_b} @{ids_desc.index(tid_b)} / {tid_a} @{ids_desc.index(tid_a)}",
    )
    # 预勾选回填：构造时传入的成员保持勾选
    picker2 = AggregateMemberPicker(rows, [tid_a], None)
    ok(
        "弹窗：构造传入的已选成员回填为勾选",
        picker2.checked_ids() == [tid_a],
        str(picker2.checked_ids()),
    )
    picker2.deleteLater()
    # 勾两个：checked_ids 按列表顺序（任务号倒序）返回，与勾的先后无关
    picker.set_checked(tid_a, True)
    picker.set_checked(tid_b, True)
    checked = picker.checked_ids()
    ok(
        "弹窗：勾选按任务号倒序返回（与勾的先后无关）",
        checked == sorted(checked, reverse=True)
        and tid_a in checked and tid_b in checked,
        str(checked),
    )
    # 取消勾选
    picker.set_checked(tid_b, False)
    ok(
        "弹窗：取消勾选真的会移除",
        picker.checked_ids() == [tid_a],
        str(picker.checked_ids()),
    )

    # 搜索：与列表页同一套匹配判据（任务名/源文件名子串，大小写不敏感）
    picker.search_edit.setText("上册")
    ok(
        "弹窗：搜索按关键词过滤（子集·上册命中）",
        [r["id"] for r in picker._filtered] == [tid_a],
        str([r["id"] for r in picker._filtered]),
    )
    ok(
        "弹窗：搜索后提示匹配数",
        "1" in picker.match_hint.text(),
        picker.match_hint.text(),
    )
    picker.search_edit.setText("")
    ok("弹窗：清空搜索恢复全量", len(picker._filtered) == len(picker._all_rows), "")

    # 分页：造 15 条合成行验证切片（不动 store，别给列表页添垃圾）
    # 勾选状态跨 set_rows 保留（设计行为：弹窗里换搜索词不丢勾），
    # 这里先清掉 tid_a 再验分页断言。
    picker.set_checked(tid_a, False)
    fake = [
        {
            "id": f"90{i:02d}",
            "name": f"合成分页{i}",
            "kind": "",
            "source_path": "",
            "created_at": 0,
            "stages": [],
        }
        for i in range(1, 16)
    ]
    picker.set_rows(fake)
    ok(
        "弹窗：set_rows 整批替换候选并回第 1 页",
        picker.pagination.pager().total == 15
        and picker.pagination.pager().clamped_page == 1,
        f"{picker.pagination.pager().total}/{picker.pagination.pager().clamped_page}",
    )
    ok(
        "弹窗：第 1 页只有前 10 行（默认每页 10 条）",
        picker.table.rowCount() == 10,
        str(picker.table.rowCount()),
    )
    picker.set_checked("9001", True)
    picker._on_page_changed(2)
    ok(
        "弹窗：翻到第 2 页只剩 5 行",
        picker.table.rowCount() == 5,
        str(picker.table.rowCount()),
    )
    ok(
        "弹窗：跨页勾选不丢（翻页再翻回来还在）",
        picker.checked_ids() == ["9001"],
        str(picker.checked_ids()),
    )
    picker._on_page_changed(99)
    ok(
        "弹窗：越界页码钳制回末页",
        picker.pagination.pager().clamped_page == 2,
        str(picker.pagination.pager().clamped_page),
    )
    picker._on_page_size_changed(50)
    ok(
        "弹窗：换每页 50 条后一页装下全部",
        picker.table.rowCount() == 15,
        str(picker.table.rowCount()),
    )

    # ---- 分页条位置（用户 2026-11-18：分页应该在右边，不是挤在中间）----
    # 与任务管理列表同一布局：分页条占满整行，控件内部的 stretch 把
    # 「每页条数/翻页」顶到右沿。
    picker.resize(900, 600)
    picker.show()
    pump(app)
    _pg = picker.pagination
    _pg_right = _pg.mapTo(picker, QPoint(_pg.width(), 0)).x()
    ok(
        "弹窗：分页条占满整行、右沿顶到弹窗内容区右缘（翻页控件靠右）",
        _pg.x() <= 2
        and _pg.width() >= 860
        and abs(_pg_right - picker.width()) <= 4,
        f"x={_pg.x()} w={_pg.width()} 右沿={_pg_right} 弹窗宽={picker.width()}",
    )
    picker.hide()

    # ---- 勾 0 条不算错误（用户 2026-11-18）：落回空勾选 ⇒ 成员原样保留 ----
    # （落点逻辑在面板的 _apply_checked，见下面的面板段）

    # 表头「勾选」= 全选本页复选框（用户 2026-11-18：表头勾选要能一次勾选
    # 本页所有列表数据）。真 CheckBox 盖在表头第 0 列上，走 toggled 信号链。
    ok(
        "弹窗：表头复选框存在且盖在表头第 0 列内",
        picker.header_check.parent() is picker.table.horizontalHeader()
        and picker.header_check.x() >= 0
        and picker.header_check.x() + picker.header_check.width()
        <= picker.table.horizontalHeader().sectionSize(0),
        f"pos=({picker.header_check.x()},{picker.header_check.y()}) "
        f"size={picker.header_check.width()}x{picker.header_check.height()}",
    )
    ok(
        "弹窗：勾了一条 ⇒ 表头复选框不亮（全勾才亮）",
        not picker.header_check.isChecked(),
        str(picker.header_check.isChecked()),
    )
    picker.header_check.setChecked(True)  # 走真信号链（同手点）
    ok(
        "弹窗：表头勾选 ⇒ 本页全部行都进 _checked",
        picker.checked_ids() == [f"90{i:02d}" for i in range(15, 0, -1)],
        str(picker.checked_ids()),
    )
    row_boxes = [
        picker.table.cellWidget(r, 0).findChildren(CheckBox)[0].isChecked()
        for r in range(picker.table.rowCount())
    ]
    ok(
        "弹窗：表头勾选 ⇒ 每行的勾选框都亮",
        all(row_boxes),
        str(row_boxes),
    )
    ok(
        "弹窗：全勾后表头复选框保持亮",
        picker.header_check.isChecked(),
        str(picker.header_check.isChecked()),
    )
    picker.set_checked("9003", False)
    ok(
        "弹窗：单独点掉一行 ⇒ 表头复选框回灭",
        not picker.header_check.isChecked(),
        str(picker.header_check.isChecked()),
    )
    # ⚠️ 表头取消走的是 toggled 信号链：此刻表头已被回显成灭（回显走
    # blockSignals），先补回 9003 让它回亮，取消才有信号可发。
    picker.set_checked("9003", True)
    ok(
        "弹窗：补回单独点掉的那行 ⇒ 表头复选框回亮（全勾才亮）",
        picker.header_check.isChecked(),
        str(picker.header_check.isChecked()),
    )
    picker.header_check.setChecked(False)
    ok(
        "弹窗：表头取消 ⇒ 本页全部行的勾都清掉",
        picker.checked_ids() == [],
        str(picker.checked_ids()),
    )

    # 窗口功能（用户 2026-11-18）：「选择子任务弹窗要显示窗口功能，放大缩小」
    # ⚠️ 只建外壳不 show/exec —— 离屏下 exec() 会卡住
    _dlg = picker.build_dialog(None)
    ok(
        "弹窗外壳：标题栏带最小化/最大化按钮",
        bool(_dlg.windowFlags() & Qt.WindowType.WindowMinMaxButtonsHint),
        str(_dlg.windowFlags()),
    )
    ok(
        "弹窗外壳：最小尺寸小于开窗尺寸（小屏上缩得回来）",
        _dlg.minimumWidth() < 1040 and _dlg.minimumHeight() < 720,
        f"{_dlg.minimumWidth()}x{_dlg.minimumHeight()}",
    )
    ok(
        "弹窗外壳：仍是模态（放大缩小不能顺手漏掉模态）",
        _dlg.isModal(),
        str(_dlg.isModal()),
    )
    _dlg.deleteLater()
    picker.deleteLater()

    # ========== 成员表格：高度自适应 + 10 条/页分页（用户 2026-11-18）==========
    # 「最多能 10 条一页显示，多余 10 条分页显示，但是没有 10 条不能占用 10 条高度」
    _many = [repo.create_task(None, "", f"成员{i:02d}") for i in range(1, 13)]
    paged = AggregateCreatePanel(repo)
    _row_h = paged.MEMBER_ROW_HEIGHT
    _h = lambda rows: MEMBER_HEADER_HEIGHT + rows * _row_h + 2  # noqa: E731
    paged.set_members(_many)
    ok(
        "表格：12 个成员 ⇒ 第 1 页只画 10 行、出现分页条",
        paged.member_table.rowCount() == MEMBER_PAGE_SIZE == 10
        and not paged.member_pager.isHidden(),
        f"{paged.member_table.rowCount()} 行 / 分页条隐藏="
        f"{paged.member_pager.isHidden()}",
    )
    ok(
        "表格：高度 = 表头 + 当前页行数×行高（不是固定 10 行高）",
        paged.member_table.height() == _h(10),
        f"{paged.member_table.height()} vs {_h(10)}",
    )
    paged._on_member_page_changed(2)
    ok(
        "表格：翻到第 2 页只剩 2 行，表格跟着变矮",
        paged.member_table.rowCount() == 2
        and paged.member_table.height() == _h(2),
        f"{paged.member_table.rowCount()} 行 / {paged.member_table.height()}",
    )
    # 行内按钮带的是**成员下标**（跨页别错位：第 2 页第 1 行 = 第 11 个成员）
    _second_page_del = next(
        b for b in paged.member_table.cellWidget(0, 3).findChildren(PushButton)
        if b.text() == "删除"
    )
    _second_page_del.click()
    ok(
        "表格：第 2 页行内「删除」删的是第 11 个成员（下标没有错位）",
        len(paged.members()) == 11 and _many[10] not in paged.members(),
        f"{len(paged.members())} 个 / 删掉的是 {_many[10]} 还在?"
        f"{_many[10] in paged.members()}",
    )
    paged.set_members(_many[:3])
    ok(
        "表格：只有 3 个成员 ⇒ 只占 3 行高、分页条不出现",
        paged.member_table.rowCount() == 3
        and paged.member_table.height() == _h(3)
        and paged.member_pager.isHidden(),
        f"{paged.member_table.rowCount()} 行 / {paged.member_table.height()} / "
        f"隐藏={paged.member_pager.isHidden()}",
    )
    # 勾 0 条不算错误（用户 2026-11-18：选择子任务弹窗里勾 0 条不该报错）
    _before_members = paged.members()
    paged._apply_checked([])
    ok(
        "表格：弹窗勾 0 条 ⇒ 成员原样保留（不报错、不清空）",
        paged.members() == _before_members == _many[:3],
        str(paged.members()),
    )
    paged._apply_checked(list(reversed(_many[:3])))
    ok(
        "表格：弹窗落回勾选 ⇒ 已排好的顺序不被冲掉（保序保留）",
        paged.members() == _many[:3],
        str(paged.members()),
    )
    paged.deleteLater()

    # ============================================== 5. 创建页：任务类型 + 名称
    page = CreateTaskPage(repo)
    # ⚠️ 创建页外层是 QScrollArea（用户 2026-11-18：整页纵向滚动），只
    #    ``layout().activate()`` 不会布到滚动内容里 ⇒ 必须 show + pump 一次，
    #    否则下面量出来的 y 全是 0/1。
    page.resize(1400, 800)
    page.show()
    pump(app)
    page.layout().activate()
    _ts = page.type_selector
    _boxes = _ts._boxes
    ok(
        "创建页：任务类型是**复选框**（常规任务/聚合任务），不是胶囊",
        _ts.keys() == [TAB_TASK, TAB_AGGREGATE]
        and [_boxes[k].text() for k in (TAB_TASK, TAB_AGGREGATE)]
        == ["常规任务", "聚合任务"]
        and all(isinstance(b, CheckBox) for b in _boxes.values())
        and not isinstance(_ts, SegmentedToggle),
        f"{[b.text() for b in _boxes.values()]} / {type(_ts).__name__}",
    )
    ok(
        "创建页：默认选中「常规任务」且内容区是常规面板",
        page.current_tab() == TAB_TASK and page._stack.currentIndex() == 0,
        f"{page.current_tab()} / {page._stack.currentIndex()}",
    )
    # 用户 2026-11-17 指定顺序：**任务类型 → 任务名称 → 后续内容**
    _type_y = _ts.mapTo(page, QPoint(0, 0)).y()
    _name_y = page.name_edit.mapTo(page, QPoint(0, 0)).y()
    ok(
        "创建页：任务类型排在任务名称之上（顺序＝类型/名称/后续内容）",
        _type_y < _name_y,
        f"类型 y={_type_y} / 名称 y={_name_y}",
    )
    # 复选框一行只占自己文案的宽度，不许被拉成"跟页面一样宽"
    ok(
        "创建页：任务类型一行不被拉满整页",
        _ts.width() <= 320 and _ts.width() < page.width() // 3,
        f"{_ts.width()} / 页面 {page.width()}",
    )
    # 用户 2026-11-17：字段名（任务类型/任务名称/子任务/上传文件…）要加粗
    _wanted = ["任务类型：", "任务名称：", "上传文件：", "子任务：", "起始节点："]
    _found = {l.text(): l for l in page.findChildren(BodyLabel)}
    _not_bold = [t for t in _wanted if t in _found and not _found[t].font().bold()]
    ok(
        "创建页：字段名一律加粗（任务类型/任务名称/上传文件/子任务/起始节点）",
        all(t in _found for t in _wanted) and not _not_bold,
        f"缺={[t for t in _wanted if t not in _found]} 未加粗={_not_bold}",
    )
    # 用户 2026-11-18：整页纵向滚动；底部流程图**不再自带滚动条**，整张铺开
    ok(
        "创建页：整页外层是可纵向滚动的 QScrollArea",
        isinstance(page.scroll, QScrollArea) and page.scroll.widgetResizable(),
        str(type(getattr(page, "scroll", None)).__name__),
    )
    _ep = page.panel._editor_panel
    ok(
        "创建页：流程图不自带滚动条（画面交给页面滚，一次看全）",
        _ep is not None and _ep._scroll is None,
        f"panel={type(_ep).__name__ if _ep is not None else None}",
    )
    page.resize(1200, 520)
    pump(app)
    _vbar = page.scroll.verticalScrollBar()
    ok(
        "创建页：内容比窗口高时出现纵向滚动（滚轮能翻）",
        _vbar.maximum() > 0,
        f"最大滚动量={_vbar.maximum()}（页面高 {page.height()}）",
    )
    # ---- 单选语义 + 切类型换内容（用户 2026-11-17 第 3 条）----
    _switched: list[str] = []
    _ts.current_changed.connect(_switched.append)
    QTest.mouseClick(_boxes[TAB_AGGREGATE], Qt.MouseButton.LeftButton)
    ok(
        "创建页：勾「聚合任务」⇒ 常规任务自动灭（单选）+ 内容换到聚合面板",
        page.current_tab() == TAB_AGGREGATE
        and _boxes[TAB_TASK].isChecked() is False
        and page._stack.currentWidget() is page.aggregate_panel,
        f"{page.current_tab()} / {[b.isChecked() for b in _boxes.values()]}",
    )
    QTest.mouseClick(_boxes[TAB_AGGREGATE], Qt.MouseButton.LeftButton)
    ok(
        "创建页：点掉当前唯一勾选不生效（恒有一个类型被选中）",
        page.current_tab() == TAB_AGGREGATE and _boxes[TAB_AGGREGATE].isChecked(),
        f"{page.current_tab()} / {_boxes[TAB_AGGREGATE].isChecked()}",
    )
    ok(
        "创建页：用户点击才发 current_changed（每次切换一条）",
        _switched == [TAB_AGGREGATE],
        str(_switched),
    )
    # 程序化切：不发信号，但仍换内容区
    page.select_tab(TAB_TASK)
    ok(
        "创建页：程序化切回「常规任务」⇒ 内容区回常规面板且不发信号",
        page._stack.currentWidget() is page.panel and _switched == [TAB_AGGREGATE],
        f"{page._stack.currentIndex()} / {_switched}",
    )
    # 追一个类型：清单延长，界面自己多出一个复选框（"后续还可以加"）
    _ts.add_item("other", "其他任务")
    ok(
        "创建页：任务类型可扩展（加一项就多一个复选框）",
        _ts.keys() == [TAB_TASK, TAB_AGGREGATE, "other"]
        and _ts.box("other") is not None,
        str(_ts.keys()),
    )
    page.select_tab(TAB_TASK)
    # 聚合提交从页面冒出去（带上任务名）
    emitted: list = []
    page.aggregate_requested.connect(
        lambda m, s, n, d: emitted.append((list(m), s, n, d))
    )
    page.aggregate_panel.set_members([tid_a])
    page.set_name("全书合并")
    page._on_aggregate_submit([tid_a], ["imposition"], None)
    ok(
        "创建页：聚合提交带上任务名与各成员节点",
        emitted == [([tid_a], ["imposition"], "全书合并", None)],
        str(emitted),
    )
    # ---- 成员「详情」＝**非模态预览窗**（用户 2026-11-17：不跳转、不挡页面、
    #      不"当当当"）----
    page.aggregate_panel.detail_requested.emit(tid_a)      # 走真实信号链
    _dlg = page._previews.get(tid_a)
    ok(
        "创建页：点「详情」弹出任务详情窗（不再切走创建页）",
        _dlg is not None and _dlg.isVisible(),
        str(_dlg),
    )
    ok(
        "创建页：详情窗**非模态**（不挡创建页，也就不会「当当」响）",
        _dlg is not None and _dlg.isModal() is False,
        f"modal={getattr(_dlg, 'isModal', lambda: None)()}",
    )
    ok(
        "创建页：详情窗里是真任务详情页、且开得够宽",
        _dlg is not None
        and _dlg.page.task_id == tid_a
        and _dlg.width() >= 1000,
        f"{getattr(getattr(_dlg, 'page', None), 'task_id', None)} / "
        f"{getattr(_dlg, 'width', lambda: 0)()}",
    )
    ok(
        "创建页：同一子任务不重复开窗（再点只前置）",
        page.open_member_preview(tid_a) is _dlg and len(page._previews) == 1,
        str(len(page._previews)),
    )
    ok(
        "创建页：详情窗收起「查看/编辑流程」（预览窗没有壳层可跳）",
        _dlg is not None and _dlg.page.flow_button.isHidden(),
        "",
    )
    ok(
        "创建页：详情窗标题栏带最小化/最大化（用户 2026-11-18 要能放大缩小）",
        _dlg is not None
        and bool(_dlg.windowFlags() & Qt.WindowType.WindowMinMaxButtonsHint),
        str(getattr(_dlg, "windowFlags", lambda: None)()),
    )
    page.reset()
    ok(
        "创建页：reset 回「常规任务」、聚合面板清空、预览窗跟着收",
        page._stack.currentIndex() == 0
        and page.aggregate_panel.members() == []
        and page._previews == {},
        f"{page._stack.currentIndex()} / {len(page._previews)}",
    )
    page.deleteLater()

    # ============================================== 6. 列表页建聚合任务 + 标记
    # 造两个成员的去底色产物（起点选「去底色」：输入=检测提交后的裁图，
    # 产出=stages/rembg），好让后台汇集真的有东西可搬。
    for tid, names in ((tid_a, ["1.jpg", "2.jpg"]), (tid_b, ["1.jpg"])):
        _make_images(repo.task_dir(tid) / "stages" / "detect", names)
        _make_images(
            repo.task_dir(tid) / "stages" / "rembg",
            [n.replace(".jpg", ".png") for n in names],
        )
        run_id = repo.create_stage_run(tid, "rembg", {})
        repo.finish_stage(tid, run_id, "success")

    opened: list = []
    w.list_page.open_detail.connect(opened.append)
    w.list_page.start_create_aggregate(
        [tid_a, tid_b], ["rembg", "rembg"], "合并本", None
    )
    pump(app, times=8)
    ok("列表页：聚合创建后自动进详情", len(opened) >= 1, str(opened))
    agg_final = opened[-1]
    newest = repo.get_task(agg_final)
    ok(
        "列表页：聚合任务真的落库（含逐成员节点）",
        newest is not None
        and newest.get("kind") == "aggregate"
        and newest.get("members") == [tid_a, tid_b]
        and newest.get("member_stages") == ["rembg", "rembg"],
        str(newest),
    )
    ok(
        "列表页：详情页能打开聚合任务（set_task 不崩）",
        w.detail_page.task_id == agg_final,
        w.detail_page.task_id,
    )

    # ---- 后台汇集：成员产物按顺序拼进聚合任务，详情页自动重载 ----
    from tests.selftests._context import wait_until

    agg_out = repo.task_dir(agg_final) / "stages" / "rembg"
    agg_entry = repo.task_dir(agg_final) / "stages" / "input"

    def _out_names() -> list:
        return [p.name for p in list_stage_images(agg_out)]

    def _entry_names() -> list:
        return [p.name for p in list_stage_images(agg_entry)]

    ok(
        "后台汇集：成员**产出**按顺序落进聚合任务（001_1/001_2/002_1）",
        wait_until(
            app,
            lambda: _out_names() == ["001_1.png", "001_2.png", "002_1.png"],
            timeout=15.0,
        ),
        str(_out_names()),
    )
    ok(
        "后台汇集：不再复制一份上游原图到入口目录（结果即输入）",
        _entry_names() == [],
        str(_entry_names()),
    )
    ok(
        "后台汇集：起点（去底色）在步骤条上显示已完成",
        wait_until(app, lambda: repo.stage_states(agg_final)["rembg"]["completed"],
                   timeout=10.0),
        str(repo.stage_states(agg_final)["rembg"]),
    )
    ok(
        "后台汇集：详情页已重载出页面清单（不是空任务）",
        wait_until(app, lambda: len(getattr(w.detail_page, "pages", []) or []) == 3,
                   timeout=10.0),
        str(len(getattr(w.detail_page, "pages", []) or [])),
    )
    ok(
        "后台汇集：聚合任务不催用户上传输入（入口输入按钮全藏）",
        w.detail_page._entry_input_kind() == "",
        w.detail_page._entry_input_kind(),
    )
    ok(
        "后台汇集：完成后「正在汇集」标记已撤（能点执行）",
        not w.detail_page._aggregate_pending(),
        "",
    )

    # ---- 重新汇集（成员重跑之后）：页面上那个按钮走的就是这条链路 ----
    _make_images(repo.task_dir(tid_b) / "stages" / "detect", ["2.jpg"])
    _make_images(repo.task_dir(tid_b) / "stages" / "rembg", ["2.png"])
    w.detail_page._run_aggregate_refresh(agg_final)
    ok(
        "重新汇集：成员新增的页被搬进来（002_2 出现）",
        wait_until(
            app,
            lambda: _out_names()
            == ["001_1.png", "001_2.png", "002_1.png", "002_2.png"],
            timeout=15.0,
        ),
        str(_out_names()),
    )
    ok(
        "重新汇集：按钮对聚合任务可见（普通任务恒藏）",
        not w.detail_page.aggregate_refresh_button.isHidden(),
        str(w.detail_page.aggregate_refresh_button.isHidden()),
    )
    # ---- 起点=提取的聚合任务：那一步当**输入节点**显示图片清单 ----
    # 用户 2026-11-18（真实任务 0025）：「选择的开始节点是提取图片……进入任务
    # 详情里面，提取图片里面没有显示任何图片」「提取图片虽然是处理 PDF 的，
    # 但是此时作为输入节点，不需要 PDF，只需要图片列表显示出来」「右侧控制
    # 面板区域中「提取文档图片」按钮功能不生效」。
    for tid, names in ((tid_a, ["1.jpg"]), (tid_b, ["1.jpg", "2.jpg"])):
        _make_images(repo.task_dir(tid) / "stages" / "extract", names)
        run_id = repo.create_stage_run(tid, "extract", {})
        repo.finish_stage(tid, run_id, "success")
    agg_ext = repo.create_aggregate_task([tid_a, tid_b], "extract", "汇集·提取起点")
    run_ingest(repo, agg_ext)
    d = ctx.d
    ok("详情页：聚合（起点=提取）装得进去", d.set_task(agg_ext) is True, "")
    pump(app, times=10)
    ok(
        "详情页：extract 这一步被判成聚合任务的**输入节点**",
        d._is_aggregate_input_node() and d.current_stage() == "extract",
        f"{d._is_aggregate_input_node()} / {d.current_stage()}",
    )
    ok(
        "详情页：提取步骤换成只读图片清单（不是 PDF 查看器）",
        d.extract_viewer_host.currentWidget() is d.extract_input_viewer,
        type(d.extract_viewer_host.currentWidget()).__name__,
    )
    ok(
        "详情页：清单列出汇集来的 3 张图（1 + 2）",
        d.extract_input_viewer.strip.count() == 3 and len(d.pages or []) == 3,
        f"{d.extract_input_viewer.strip.count()} / {len(d.pages or [])}",
    )
    ok(
        "详情页：「提取文档图片」按钮置灰（作为输入节点不执行）",
        not d.run_button.isEnabled() and "输入节点" in d.run_button.toolTip(),
        f"{d.run_button.isEnabled()} / {d.run_button.toolTip()}",
    )
    ok(
        "详情页：状态行说明「无需执行」",
        "无需执行" in d.stage_status.text(),
        d.stage_status.text(),
    )
    # 快捷键/自动化绕过按钮直接触发也要拦住（否则会拿空源去起 worker）
    d.run_stage(resume=False)
    pump(app, times=4)
    ok(
        "详情页：硬触发执行也拦得住（不起 worker）",
        d.running_stage is None and getattr(d, "process", None) is None,
        f"{d.running_stage} / {getattr(d, 'process', None)}",
    )

    # ---- 起点=去底色 / 检测：同样要把汇集来的图列在第一步 ----
    # 用户 2026-11-18 任务 0026：「起始节点是去底色，但是聚合任务去底色节点
    # 没有显示任何图片……检查所有可以使用的节点作为第一个节点的时候，聚合
    # 数据来源需要显示在第一个节点中」。
    agg_rembg = repo.create_aggregate_task([tid_a, tid_b], "rembg", "汇集·去底起点")
    run_ingest(repo, agg_rembg)
    ok("详情页：聚合（起点=去底色）装得进去", d.set_task(agg_rembg) is True, "")
    pump(app, times=10)
    ok(
        "详情页：去底色起点判成输入节点、当前步就是它",
        d._is_aggregate_input_node() and d.current_stage() == "rembg",
        f"{d._is_aggregate_input_node()} / {d.current_stage()}",
    )
    ok(
        "详情页：去底色起点换成只读图片清单（不是原图/结果对比）",
        d.rembg_viewer_host.currentWidget() is d.rembg_input_viewer,
        type(d.rembg_viewer_host.currentWidget()).__name__,
    )
    ok(
        "详情页：去底色清单把汇集来的图全列出来（与页清单同数）",
        d.rembg_input_viewer.strip.count() == len(d.pages or []) > 0,
        f"{d.rembg_input_viewer.strip.count()} / {len(d.pages or [])}",
    )
    ok(
        "详情页：去底色起点的执行按钮也置灰",
        not d.run_button.isEnabled(),
        str(d.run_button.isEnabled()),
    )

    agg_det2 = repo.create_aggregate_task([tid_a, tid_b], "detect", "汇集·检测起点")
    run_ingest(repo, agg_det2)
    ok("详情页：聚合（起点=检测）装得进去", d.set_task(agg_det2) is True, "")
    pump(app, times=10)
    ok(
        "详情页：检测起点也把图列出来（与页清单同数）且按钮置灰",
        d._is_aggregate_input_node()
        and d.current_stage() == "detect"
        and d.detect_viewer.strip.count() == len(d.pages or []) > 0
        and not d.run_button.isEnabled(),
        f"{d.current_stage()} / {d.detect_viewer.strip.count()}"
        f" / {len(d.pages or [])} / {d.run_button.isEnabled()}",
    )
    for tid in (agg_rembg, agg_det2):
        repo.delete_task(tid)

    # ---- 汇集期间的**分批显示**（用户 2026-11-18：「如果时间长，是否可以
    # 分批导入，分批显示」）——后台复制逐文件进行，清单跟着复制进度长 ----
    from desktop.services.aggregate_ingest import set_pending_marker

    agg_poll = repo.create_aggregate_task([tid_a, tid_b], "rembg", "汇集·分批")
    set_pending_marker(repo.task_dir(agg_poll), on=True)   # 模拟"还在复制"
    ok("详情页：汇集中的聚合任务装得进去", d.set_task(agg_poll) is True, "")
    d._select_stage(0)
    pump(app, times=6)
    ok(
        "详情页：还在汇集 ⇒ 清单为空但**轮询已启动**",
        d.current_stage() == "rembg"
        and d.rembg_input_viewer._paths == []
        and d._input_node_poll.isActive(),
        f"{len(d.rembg_input_viewer._paths)} / {d._input_node_poll.isActive()}",
    )
    # 模拟第一批文件复制落盘 → 轮询到点就该把它们列出来
    _make_images(repo.task_dir(agg_poll) / "stages" / "rembg", ["001_1.png"])
    d._on_input_node_poll()
    pump(app, times=6)
    ok(
        "详情页：落一批显示一批（1 张就先显示 1 张）",
        d.rembg_input_viewer.strip.count() == 1
        and "正在汇集" in d.stage_status.text(),
        f"{d.rembg_input_viewer.strip.count()} / {d.stage_status.text()}",
    )
    ok(
        "详情页：还在汇集 ⇒ 轮询继续排下一轮",
        d._input_node_poll.isActive(),
        str(d._input_node_poll.isActive()),
    )
    # 汇集结束（标记撤掉）⇒ 轮询停表，改由 aggregate_ready 整页重载收尾
    set_pending_marker(repo.task_dir(agg_poll), on=False)
    d._on_input_node_poll()
    pump(app, times=4)
    ok(
        "详情页：汇集结束 ⇒ 轮询停表",
        not d._input_node_poll.isActive(),
        str(d._input_node_poll.isActive()),
    )
    repo.delete_task(agg_poll)

    # 普通任务不能被这条判据带偏：同一个「提取图片」步骤仍是 PDF 查看器 + 可执行
    ok("详情页：普通任务切回自己不受影响", d.set_task(tid_a) is True, "")
    pump(app, times=6)
    ok(
        "详情页：普通任务的提取步骤仍是 PDF 查看器、按钮可点",
        d.extract_viewer_host.currentWidget() is d.extract_result_viewer
        and d.run_button.isEnabled()
        and not d._is_aggregate_input_node(),
        f"{type(d.extract_viewer_host.currentWidget()).__name__}"
        f" / {d.run_button.isEnabled()}",
    )
    repo.delete_task(agg_ext)

    # 回列表，看「聚合」标记（列表刷新是后台线程，必须等它回来）
    w.shell.back_to_list()

    from tests.selftests._context import wait_until

    def _aggregate_chip_visible() -> bool:
        table = w.list_page.table.table
        for row in range(table.rowCount()):
            cell = table.cellWidget(row, 1)
            if cell is None:
                continue
            for chip in cell.findChildren(StatusChip):
                if chip._text == "聚合":
                    return True
        return False

    ok(
        "列表页：聚合任务的名称旁有「聚合」标记",
        wait_until(app, _aggregate_chip_visible, timeout=10.0),
        "",
    )

    # ============================================== 7. 详情页「流程」入口（用户 2026-11-18）
    # 用户原话：「聚合任务 0025，详情页面右上角有个详情流程入口，进入流程入口，
    # 现在显示的是常规任务流程，应当显示聚合任务的子任务相关信息，跟创建聚合
    # 任务时候一样」。
    from desktop.pages.taskflow.page import TaskFlowPage

    flow_page = TaskFlowPage(repo)
    flow_page.resize(1200, 900)
    flow_page.show()
    pump(app)
    ok(
        "流程页：聚合任务打开的是聚合一整套（不是光一张流程图）",
        flow_page.open_task(agg_final)
        and flow_page._aggregate_panel is not None
        and flow_page._panel is None,
        f"agg={flow_page._aggregate_panel is not None} "
        f"flow={flow_page._panel is not None}",
    )
    agg_panel = flow_page._aggregate_panel
    ok(
        "流程页：标题点明是聚合任务流程",
        flow_page.title.text().startswith("聚合任务流程")
        and flow_page._task_id == agg_final,
        flow_page.title.text(),
    )
    ok(
        "流程页：子任务按落库顺序回填（两行）",
        agg_panel.members() == [tid_a, tid_b]
        and agg_panel.member_table.rowCount() == 2,
        f"{agg_panel.members()} / {agg_panel.member_table.rowCount()} 行",
    )
    ok(
        "流程页：起始节点回填成落库的那个（去底色）",
        agg_panel.current_stage() == "rembg",
        agg_panel.current_stage(),
    )
    ok(
        "流程页：画布就是磁盘上那张 flow.bpmn（不是另派生的）",
        agg_panel.current_diagram().stage_order()
        == repo.task_diagram(agg_final).stage_order(),
        str(agg_panel.current_diagram().stage_order()),
    )
    ok(
        "流程页：查看模式不给改成员（「选择子任务…」与底部按钮行收起）",
        agg_panel.pick_button.isHidden() and agg_panel._button_bar.isHidden(),
        f"选择按钮隐藏={agg_panel.pick_button.isHidden()} / "
        f"按钮行隐藏={agg_panel._button_bar.isHidden()}",
    )
    ok(
        "流程页：起始节点勾选框**可切换**（勾着落库那个，且都能点）",
        all(b.isEnabled() for b in agg_panel._stage_boxes.values())
        and [k for k, b in agg_panel._stage_boxes.items() if b.isChecked()] == ["rembg"],
        str({k: (b.isChecked(), b.isEnabled()) for k, b in agg_panel._stage_boxes.items()}),
    )
    ok(
        "流程页：行内操作只剩「详情」（没有上移/下移/删除）",
        [b.text() for b in agg_panel.member_table.cellWidget(0, 3).findChildren(PushButton)]
        == ["详情"],
        str([
            b.text()
            for b in agg_panel.member_table.cellWidget(0, 3).findChildren(PushButton)
        ]),
    )
    # 保存：落盘 + 通知宿主回详情页（与普通任务同一条链路）
    saved: list = []
    flow_page.flow_saved.connect(saved.append)
    flow_page._on_done(True)
    ok(
        "流程页：保存流程落盘并通知宿主（聚合任务同一条路径）",
        saved == [agg_final]
        and bool(repo.task_diagram(agg_final).stage_order()),
        f"{saved} / {repo.task_diagram(agg_final).stage_order()}",
    )
    # 成员「详情」：非模态预览窗（和创建页同一个实现）
    agg_panel.detail_requested.emit(tid_a)
    _pdlg = flow_page._previews.get(tid_a)
    ok(
        "流程页：子任务「详情」弹非模态预览窗（不跳走、不「当当」）",
        _pdlg is not None and _pdlg.isVisible() and _pdlg.isModal() is False,
        f"{_pdlg is not None} / modal={getattr(_pdlg, 'isModal', lambda: None)()}",
    )
    flow_page._close_previews()
    ok("流程页：离开本页时预览窗一起收", flow_page._previews == {}, "")

    # ---------------- 起始节点可切换 + 保存时提示「历史数据作废」（用户 2026-11-18）
    # 用户原话：「起始节点可以切换变更，如果变更了保存流程的时候，提示起始节点
    # 丢失，聚合任务之前历史处理数据都丢失」。
    from desktop.steps.aggregate import aggregate_start_label, derive_aggregate_diagram

    others = [k for k in agg_panel._stage_boxes if k != "rembg"]
    ok("流程页：候选里还有别的起点可选（能真的切）", bool(others), str(list(agg_panel._stage_boxes)))
    new_stage = others[0]
    QTest.mouseClick(agg_panel._stage_boxes[new_stage], Qt.MouseButton.LeftButton)
    pump(app)
    ok(
        "流程页：点另一个起点 ⇒ 选中项跟着换（仍然是单选）",
        agg_panel.current_stage() == new_stage
        and [k for k, b in agg_panel._stage_boxes.items() if b.isChecked()] == [new_stage],
        str({k: b.isChecked() for k, b in agg_panel._stage_boxes.items()}),
    )
    ok(
        "流程页：改过起点 ⇒ stage_changed() 为真（落库值仍是去底色）",
        agg_panel.stage_changed() and agg_panel.record_stage() == "rembg",
        f"changed={agg_panel.stage_changed()} record={agg_panel.record_stage()}",
    )
    ok(
        "流程页：画布按新起点重建（起点之前的那步被丢掉）",
        agg_panel.current_diagram().stage_order()
        == derive_aggregate_diagram(new_stage).stage_order(),
        str(agg_panel.current_diagram().stage_order()),
    )
    # 提示框：构造与 exec() 分开（离屏绝不真弹模态）
    _warn = flow_page._build_start_change_dialog("rembg", new_stage)
    _warn_text = _warn.content_label.text()
    ok(
        "流程页：保存前的提示把「起点变了 + 历史数据作废」都说清",
        _warn.title_label.text() == "起始节点已变更"
        and aggregate_start_label("rembg") in _warn_text
        and aggregate_start_label(new_stage) in _warn_text
        and "作废" in _warn_text and "丢失" in _warn_text,
        _warn_text,
    )
    ok(
        "流程页：提示框是真模态窗、宽度钉死（不会随任务名撑宽）",
        _warn.isModal() and _warn.width() == 440,
        f"modal={_warn.isModal()} w={_warn.width()}",
    )
    _warn.deleteLater()
    # 取消：不落盘、不改 record、不发信号、留在本页
    import io as _io
    from pathlib import Path as _Path

    _flow_file = _Path(repo.task_dir(agg_final)) / "flow.bpmn"
    _before = _io.open(_flow_file, "rb").read()
    _saved: list = []
    _changed: list = []
    _closed: list = []
    flow_page.flow_saved.connect(_saved.append)
    flow_page.aggregate_start_changed.connect(_changed.append)
    flow_page.closed.connect(lambda: _closed.append(True))
    flow_page._confirm_start_change = lambda old, new: False     # 替身：用户点「取消」
    flow_page._on_done(True)
    pump(app)
    ok(
        "流程页：提示框点「取消」⇒ 流程没写盘、record 没改、页面没切走",
        _io.open(_flow_file, "rb").read() == _before
        and (repo.get_task(agg_final) or {}).get("member_stage") == "rembg"
        and not _saved and not _changed and not _closed,
        f"saved={_saved} changed={_changed} closed={_closed}",
    )
    ok(
        "流程页：取消后起点仍停在用户刚选的那个（可以改回去再存）",
        agg_panel.current_stage() == new_stage and agg_panel.stage_changed(),
        agg_panel.current_stage(),
    )
    # 确认：record 一起改 + 图按新起点落盘 + 发两条信号（先重取、后回详情页）
    flow_page._confirm_start_change = lambda old, new: True      # 替身：用户点「确认」
    order: list = []
    flow_page.aggregate_start_changed.connect(lambda _t: order.append("restart"))
    flow_page.flow_saved.connect(lambda _t: order.append("saved"))
    flow_page._on_done(True)
    pump(app)
    _record = repo.get_task(agg_final) or {}
    ok(
        "流程页：确认后 record 的起点一起改（member_stage/member_stages 同口径）",
        _record.get("member_stage") == new_stage
        and _record.get("member_stages") == [new_stage] * len(_record.get("members") or []),
        f"{_record.get('member_stage')} / {_record.get('member_stages')}",
    )
    ok(
        "流程页：确认后流程图按新起点落盘（详情页的起点节点能找到）",
        repo.task_diagram(agg_final).stage_order()
        == derive_aggregate_diagram(new_stage).stage_order(),
        str(repo.task_diagram(agg_final).stage_order()),
    )
    ok(
        "流程页：先发「按新起点重新汇集」再发「回详情页」（页面不会先说没输入）",
        order[-2:] == ["restart", "saved"] and _changed[-1] == agg_final,
        str(order),
    )
    ok(
        "流程页：落库后 stage_changed() 复归假（再点保存不会又弹一次框）",
        not agg_panel.stage_changed() and agg_panel.record_stage() == new_stage,
        f"changed={agg_panel.stage_changed()} record={agg_panel.record_stage()}",
    )
    # 壳层接线：收到 aggregate_start_changed ⇒ 让详情页按新起点重取
    from desktop.shell import ModuleShell

    _shell = ModuleShell(repo)
    _detail = _shell._ensure_detail_page()
    _detail.task_id = agg_final          # 假装详情页正停在这个任务上
    _restarted: list = []
    _detail.restart_aggregate_ingest = lambda tid: _restarted.append(tid) or True
    _shell._on_aggregate_start_changed(agg_final)
    ok(
        "壳层：聚合任务改起点后自动按新起点重新汇集（不用再点页头 ⟳）",
        _restarted == [agg_final],
        str(_restarted),
    )
    _shell.deleteLater()

    # 回归：普通任务照旧只有流程画布
    ok(
        "流程页：普通任务仍是原来的流程画布（没被聚合分支抢走）",
        flow_page.open_task(tid_a)
        and flow_page._panel is not None
        and flow_page._aggregate_panel is None
        and "任务流程" in flow_page.title.text()
        and "聚合" not in flow_page.title.text(),
        flow_page.title.text(),
    )
    flow_page.deleteLater()

    # ============================================== 8. 清场（删本模块建的任务）
    for tid in (agg_id, agg_id2, agg_id3, opened[-1] if opened else None, tid_a, tid_b):
        if tid and repo.get_task(tid):
            repo.delete_task(tid)
    w.list_page.refresh()
    pump(app, times=8)
    ok(
        "清场：本模块建的任务已删净",
        all(repo.get_task(t) is None for t in (agg_id, agg_id2, agg_id3, tid_a, tid_b)),
        "",
    )
