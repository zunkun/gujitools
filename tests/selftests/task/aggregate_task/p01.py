# -*- coding: utf-8 -*-
"""1. 流程派生（纯逻辑） / 注释（节点说明）：被丢弃节点的注释必须跟着丢 / 候选起始节点 = 成员**已完成**节点的并集（用户 2026-11-18） / 2. store 落库 / 已完成节点清单（起始节点候选的数据源） / 2b. 成员产物汇集（执行链路）"""

from typing import Any


def run(st: Any) -> None:
    from desktop.steps.aggregate import (
        AGGREGATE_START_LABEL,
        AGGREGATE_START_STAGES,
        aggregate_start_label,
        derive_aggregate_diagram,
    )
    from PIL import Image
    from pathlib import Path
    from desktop.services.aggregate_ingest import (
        aggregate_page_name,
        plan_ingest,
        run_ingest,
    )
    from desktop.steps.aggregate import any_member_stages, missing_members
    from desktop.steps.scheduler import default_template_path
    from desktop.utils.files import list_stage_images
    from utils.sort_utils import natural_sort_key
    from tests.selftests._context import ok, pump
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
    st.tid_a = st.repo.create_task(st.ctx.pdf, "agg-hash-1", "子集·上册")
    st.tid_b = st.repo.create_task(st.ctx.big_pdf, "agg-hash-2", "子集·下册")
    st.agg_id = st.repo.create_aggregate_task([st.tid_a, st.tid_b], "imposition", "合并本（上+下）")
    record = st.repo.get_task(st.agg_id)
    ok(
        "聚合任务：record 带 kind=aggregate",
        record.get("kind") == "aggregate",
        str(record.get("kind")),
    )
    ok(
        "聚合任务：members 按用户排序保存",
        record.get("members") == [st.tid_a, st.tid_b],
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
    flow = st.repo.task_diagram(st.agg_id)
    ok(
        "聚合任务：flow.bpmn 是派生图（拼版→PDF排版）",
        flow.stage_order() == ("imposition", "print"),
        str(flow.stage_order()),
    )
    # ⚠️ 绝不能是默认模板的字节拷贝（模板里有 extract，语义不对）
    from desktop.steps.scheduler import default_template_path

    template_bytes = default_template_path().read_bytes()
    task_flow_bytes = (st.repo.task_dir(st.agg_id) / "flow.bpmn").read_bytes()
    ok(
        "聚合任务：flow.bpmn 不是默认模板的字节拷贝",
        task_flow_bytes != template_bytes,
        "",
    )

    # 名字回落 + diagram 优先
    st.agg_id2 = st.repo.create_aggregate_task([st.tid_b], "detect", "")
    ok(
        "聚合任务：名字留空回落「任务#号」",
        st.repo.get_task(st.agg_id2)["name"] == f"任务#{st.agg_id2}",
        st.repo.get_task(st.agg_id2)["name"],
    )
    ok(
        "聚合任务：member_stage=detect ⇒ flow 从检测开始",
        st.repo.task_diagram(st.agg_id2).stage_order()
        == ("detect", "rembg", "imposition", "print"),
        str(st.repo.task_diagram(st.agg_id2).stage_order()),
    )

    # 每成员各自的节点（用户 2026-11-17 晚口径）
    st.agg_id3 = st.repo.create_aggregate_task(
        [st.tid_a, st.tid_b], member_stages=["detect", "print"], name="混搭"
    )
    rec3 = st.repo.get_task(st.agg_id3)
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
        st.repo.task_diagram(st.agg_id3).stage_order()[0] == "detect",
        str(st.repo.task_diagram(st.agg_id3).stage_order()),
    )

    # 非法输入
    for members, stage, label in (
        ([], "imposition", "空成员"),
        (["9999"], "imposition", "不存在的成员"),
        ([st.tid_a], "nope", "垃圾起始节点"),
    ):
        try:
            st.repo.create_aggregate_task(members, stage, "x")
            ok(f"聚合任务拒绝：{label}", False, "竟然没有抛 ValueError")
        except ValueError:
            ok(f"聚合任务拒绝：{label}", True, "")

    # 合法：extract 也能当起始节点（用户 2026-11-18）——流程从提取开始，
    # 汇集只搬成员的提取产物（见 2b 的 extract 段）
    st.agg_ext = st.repo.create_aggregate_task([st.tid_a], "extract", "从提取开始")
    ok(
        "聚合任务：extract 起始是合法的（流程含提取）",
        st.repo.task_diagram(st.agg_ext).stage_order()[0] == "extract",
        str(st.repo.task_diagram(st.agg_ext).stage_order()),
    )
    st.repo.delete_task(st.agg_ext)

    # 非法 member_stages
    for members, stages, label in (
        ([st.tid_a, st.tid_b], ["detect"], "节点数与成员数不一致"),
        ([st.tid_a], ["nope"], "垃圾成员节点"),
    ):
        try:
            st.repo.create_aggregate_task(members, member_stages=stages, name="x")
            ok(f"聚合任务拒绝：{label}", False, "竟然没有抛 ValueError")
        except ValueError:
            ok(f"聚合任务拒绝：{label}", True, "")
    for stage in ("extract", "detect"):
        run_id = st.repo.create_stage_run(st.tid_a, stage, {})
        st.repo.finish_stage(st.tid_a, run_id, "success")
    run_id = st.repo.create_stage_run(st.tid_a, "rembg", {})
    st.repo.finish_stage(st.tid_a, run_id, "failed")
    ok(
        "store：已完成节点 = 历史上成功过且在流程里（extract + detect）",
        st.repo.completed_aggregate_stages(st.tid_a) == ["extract", "detect"],
        str(st.repo.completed_aggregate_stages(st.tid_a)),
    )
    ok(
        "store：extract 完成后也在候选里（用户 2026-11-18 改口径）",
        "extract" in st.repo.completed_aggregate_stages(st.tid_a),
        str(st.repo.completed_aggregate_stages(st.tid_a)),
    )
    ok(
        "store：失败过的节点不算完成（rembg failed）",
        "rembg" not in st.repo.completed_aggregate_stages(st.tid_a),
        str(st.repo.completed_aggregate_stages(st.tid_a)),
    )
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
    st._make_images = _make_images

    ok(
        "页名规则：成员序号 3 位 + 原页名（001_1.jpg）",
        aggregate_page_name(1, "10-l.jpg") == "001_10-l.jpg",
        aggregate_page_name(1, "10-l.jpg"),
    )

    st.tid_c = st.repo.create_task(st.ctx.pdf, "agg-hash-c", "子集·上")
    st.tid_d = st.repo.create_task(st.ctx.big_pdf, "agg-hash-d", "子集·下")
    # tid_c 三页（含一张半幅 -l），tid_d 两页
    for tid, pages in (
        (st.tid_c, ["1.jpg", "2.jpg", "10-l.jpg"]),
        (st.tid_d, ["1.jpg", "2.jpg"]),
    ):
        root_dir = st.repo.task_dir(tid)
        st._make_images(root_dir / "stages" / "extract", pages)
        st._make_images(root_dir / "stages" / "detect", pages)
        st._make_images(
            root_dir / "stages" / "rembg",
            [p.replace(".jpg", ".png") for p in pages],
        )
        st.repo.save_image_sizes_batch(tid, {Path(p).stem: (40, 60) for p in pages})
        for stage in ("extract", "detect", "detect_submit", "rembg"):
            run_id = st.repo.create_stage_run(tid, stage, {})
            st.repo.finish_stage(tid, run_id, "success")

    # 成员顺序 [下, 上] —— 汇集必须**照这个顺序**排
    st.agg_ing = st.repo.create_aggregate_task([st.tid_d, st.tid_c], "rembg", "汇集·去底")
    plan = plan_ingest(st.repo, st.agg_ing)
    ok(
        "汇集计划：起点=去底色，输入落 stages/input、产出落 stages/rembg",
        plan is not None
        and plan.start_stage == "rembg"
        and plan.entry_dir == st.repo.task_dir(st.agg_ing) / "stages" / "input"
        and plan.output_dir == st.repo.task_dir(st.agg_ing) / "stages" / "rembg",
        f"{plan.start_stage if plan else None}",
    )
    ok(
        "汇集计划：输入=成员的裁图、产出=成员的成品图（都搬，按成员顺序）"
        "（2026-11-18 晚口径：x 的输入做起点输入、x 的输出做起点输出）",
        plan is not None
        and [c.target.name for c in plan.input_copies]
        == ["001_1.jpg", "001_2.jpg", "002_1.jpg", "002_2.jpg", "002_10-l.jpg"]
        and [c.target.name for c in plan.output_copies]
        == ["001_1.png", "001_2.png", "002_1.png", "002_2.png", "002_10-l.png"],
        str([c.target.name for c in plan.input_copies]) if plan else "",
    )
    ok(
        "汇集计划：页面清单按成员顺序编号 1..5",
        [p["label"] for p in plan.pages] == ["1", "2", "3", "4", "5"],
        str([p["label"] for p in plan.pages]),
    )

    result = run_ingest(st.repo, st.agg_ing)
    entry_dir = st.repo.task_dir(st.agg_ing) / "stages" / "input"
    out_dir = st.repo.task_dir(st.agg_ing) / "stages" / "rembg"
    entries = [p.name for p in list_stage_images(entry_dir)]
    ok(
        "汇集：入口目录躺着成员的裁图（= 去底色的输入，001=下、002=上）",
        entries == ["001_1.jpg", "001_2.jpg", "002_1.jpg", "002_2.jpg", "002_10-l.jpg"],
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
        "汇集：结果统计（5 页清单 / 10 个文件＝输入+产出）",
        (result.pages, result.copied) == (5, 10),
        f"{result.pages}/{result.copied}",
    )
    pages_json = st.repo.load_pages(st.agg_ing)
    ok(
        "汇集：pages.json 指向**起点输入**（stages/input 的裁图，2026-11-18 晚口径）",
        [p["label"] for p in pages_json] == ["1", "2", "3", "4", "5"]
        and all(Path(p["file"]).parent == entry_dir for p in pages_json),
        str(pages_json[:2]),
    )
    ok(
        "汇集：sizes.json 跟着新页名落地（框坐标有基准）",
        st.repo.image_size(st.agg_ing, "002_10-l") == (40, 60),
        str(st.repo.image_size(st.agg_ing, "002_10-l")),
    )
    ok(
        "汇集：起点（去底色）被记为已完成（否则第四步看不到产出）",
        st.repo.completed_aggregate_stages(st.agg_ing) == ["rembg"],
        str(st.repo.completed_aggregate_stages(st.agg_ing)),
    )
    ok(
        "汇集：第四步的上游（去底色）判定为已生效（能直接排版/生成PDF）",
        st.repo.stage_input_effective(st.agg_ing, "print", "pages"),
        "",
    )

    # 幂等 + 清陈旧：成员少了一页 ⇒ 旧页从聚合任务里消失，用户的图不动
    (st.repo.task_dir(st.tid_c) / "stages" / "detect" / "2.jpg").unlink()
    (st.repo.task_dir(st.tid_c) / "stages" / "rembg" / "2.png").unlink()
    stray = entry_dir / "用户自己放的图.png"
    Image.new("RGB", (10, 10), "white").save(stray)
    run_ingest(st.repo, st.agg_ing)
    names_now = [p.name for p in list_stage_images(out_dir)]
    ok(
        "汇集：重跑清掉不再需要的旧页（002_2 消失）",
        "002_2.png" not in names_now and len(names_now) == 4,
        str(names_now),
    )
    ok("汇集：重跑不删用户自己放进的图", stray.exists(), "")

    # 重新汇集/改起点的卫生守卫（任务 0026）：旧起点的合成 runs 记录与旧
    # 起点产物目录里的汇集产物都要清掉，否则下游拿旧记录当真、旧图冒充结果。
    fake_run = st.repo.create_stage_run(st.agg_ing, "extract", {"aggregate": True})
    st.repo.finish_stage(st.agg_ing, fake_run, "success")
    old_leftover = st.repo.task_dir(st.agg_ing) / "stages" / "extract" / "001_9.png"
    old_leftover.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (10, 10), "white").save(str(old_leftover))
    run_ingest(st.repo, st.agg_ing)
    extract_runs = st.repo.list_stage_runs(st.agg_ing, "extract")
    ok(
        "汇集：旧起点的合成 runs 记录被清掉（extract 的 aggregate 记录消失）",
        extract_runs == [],
        str(extract_runs),
    )
    ok(
        "汇集：起点自身的合成记录重新写好（rembg 仍是已完成）",
        st.repo.completed_aggregate_stages(st.agg_ing) == ["rembg"],
        str(st.repo.completed_aggregate_stages(st.agg_ing)),
    )
    ok(
        "汇集：旧起点产物目录里的 NNN_ 文件被清、用户图不碰",
        not old_leftover.exists() and stray.exists(),
        f"{old_leftover.exists()}",
    )

