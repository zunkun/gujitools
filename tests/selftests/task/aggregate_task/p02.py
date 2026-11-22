# -*- coding: utf-8 -*-
"""起点=检测：检测框按同一前缀搬过来 / 起点=提取：只搬提取产物（它没有输入源） / 起点=PDF排版：只搬成员的**印刷取图**当输入，输出不预填 / 3. 创建面板"""

from typing import Any


def run(st: Any) -> None:
    from desktop.components.aggregate_create_panel import (
        MEMBER_HEADER_HEIGHT,
        MEMBER_PAGE_SIZE,
        AggregateCreatePanel,
        AggregateMemberPicker,
        DEFAULT_START_STAGE,
    )
    from pathlib import Path
    from desktop.utils.files import list_stage_images
    from tests.selftests._context import ok, pump
    from desktop.services.aggregate_ingest import (
        aggregate_page_name,
        plan_ingest,
        run_ingest,
    )
    from desktop.services.print_plan import plan_print_entries
    st.tid_e = st.repo.create_task(st.ctx.pdf, "agg-hash-e", "子集·检测")
    root_e = st.repo.task_dir(st.tid_e)
    st._make_images(root_e / "stages" / "extract", ["1.jpg", "2.jpg"])
    st._make_images(root_e / "stages" / "detect", ["1.jpg", "2.jpg"])
    st.repo.save_image_sizes_batch(st.tid_e, {"1": (40, 60), "2": (40, 60)})
    st.repo.save_detect_boxes_batch(
        st.tid_e, {"1": [[0, 0, 10, 10]], "2": [[0, 0, 5, 5]]}
    )
    for stage in ("extract", "detect", "detect_submit"):
        run_id = st.repo.create_stage_run(st.tid_e, stage, {})
        st.repo.finish_stage(st.tid_e, run_id, "success")
    st.agg_det = st.repo.create_aggregate_task([st.tid_e], "detect", "汇集·检测")
    det_plan = plan_ingest(st.repo, st.agg_det)
    ok(
        "汇集[检测]：输入=成员的提取页图、产出=成员的检测裁图（都搬）",
        det_plan is not None
        and [c.target.name for c in det_plan.input_copies]
        == ["001_1.jpg", "001_2.jpg"]
        and [c.target.name for c in det_plan.output_copies]
        == ["001_1.jpg", "001_2.jpg"]
        and all(
            Path(p["file"]).parent == det_plan.entry_dir for p in det_plan.pages
        ),
        str([c.target.name for c in det_plan.input_copies]) if det_plan else "",
    )
    run_ingest(st.repo, st.agg_det)
    det_entry = [
        p.name
        for p in list_stage_images(st.repo.task_dir(st.agg_det) / "stages" / "input")
    ]
    ok(
        "汇集[检测]：入口目录躺着成员的提取页图（检测页显示整页图+框）",
        det_entry == ["001_1.jpg", "001_2.jpg"],
        str(det_entry),
    )
    ok(
        "汇集[检测]：框文件按新页名搬过来（001_1 / 001_2）",
        sorted(st.repo.detect_boxes_all(st.agg_det)) == ["001_1", "001_2"],
        str(sorted(st.repo.detect_boxes_all(st.agg_det))),
    )
    ok(
        "汇集[检测]：检测的**两个动作**都记为成功（提交不过期）",
        st.repo.node_action_executed(
            st.agg_det, st.repo.task_diagram(st.agg_det).node_ids_of("detect")[0], "detect"
        )
        and st.repo.node_action_executed(
            st.agg_det,
            st.repo.task_diagram(st.agg_det).node_ids_of("detect")[0],
            "detect_submit",
        )
        and st.repo.detect_submit_fresh(
            st.agg_det, st.repo.task_diagram(st.agg_det).node_ids_of("detect")[0]
        ),
        "",
    )
    st.agg_ext2 = st.repo.create_aggregate_task([st.tid_e, st.tid_c], "extract", "汇集·提取")
    ext_plan = plan_ingest(st.repo, st.agg_ext2)
    ok(
        "汇集[提取]：没有输入复制（提取没有上游），只有产出",
        ext_plan is not None
        and ext_plan.input_copies == ()
        and [c.target.name for c in ext_plan.output_copies]
        == ["001_1.jpg", "001_2.jpg", "002_1.jpg", "002_2.jpg", "002_10-l.jpg"],
        str([c.target.name for c in ext_plan.output_copies]) if ext_plan else "",
    )
    ext_result = run_ingest(st.repo, st.agg_ext2)
    ext_out = st.repo.task_dir(st.agg_ext2) / "stages" / "extract"
    ok(
        "汇集[提取]：提取产物落在 stages/extract，页清单按成员顺序",
        [p.name for p in list_stage_images(ext_out)]
        == ["001_1.jpg", "001_2.jpg", "002_1.jpg", "002_2.jpg", "002_10-l.jpg"]
        and [p["label"] for p in st.repo.load_pages(st.agg_ext2)] == ["1", "2", "3", "4", "5"],
        str([p.name for p in list_stage_images(ext_out)]),
    )
    ok(
        "汇集[提取]：起点记为已完成（检测可以直接跑）",
        st.repo.completed_aggregate_stages(st.agg_ext2) == ["extract"]
        and not ext_result.notes,
        f"{st.repo.completed_aggregate_stages(st.agg_ext2)} / {ext_result.notes}",
    )
    for tid in (st.tid_d, st.tid_e):
        st._make_images(
            st.repo.task_dir(tid) / "stages" / "rembg",
            ["1.png", "2.png"],
        )
    # 成员在第四步手工拖动过页序（print.json 持久化用户的顺序调整）：
    # 聚合任务要原样重现（2026-11-18 原则：子任务该节点显示什么，
    # 聚合起点就显示什么）。
    st.repo.save_print_doc(
        st.tid_d,
        {
            "rembg_snapshot": [],
            "pages": [
                {"file": str(st.repo.task_dir(st.tid_d) / "stages" / "rembg" / "2.png"),
                 "label": "2"},
                {"file": str(st.repo.task_dir(st.tid_d) / "stages" / "rembg" / "1.png"),
                 "label": "1"},
            ],
            "deleted_pages": [],
        },
    )
    agg_pdf = st.repo.create_aggregate_task([st.tid_d, st.tid_e], "print", "汇集·PDF")
    pdf_plan = plan_ingest(st.repo, agg_pdf)
    ok(
        "汇集[PDF排版]：输入=成员的印刷取图（拼版未生效 → 去底色成品），无产出复制",
        pdf_plan is not None
        and [c.target.name for c in pdf_plan.input_copies]
        == ["001_1.png", "001_2.png", "002_1.png", "002_2.png"]
        and pdf_plan.output_copies == ()
        and pdf_plan.output_dir == st.repo.scoped_stage_dir(agg_pdf, None, "print"),
        str([c.target.name for c in pdf_plan.input_copies]) if pdf_plan else "",
    )
    ok(
        "汇集[PDF排版]：成员手工拖过的页序按文件映射组合进 print.json"
        "（001 先 2 后 1，002 按目录序）",
        pdf_plan is not None
        and [Path(p["file"]).name for p in pdf_plan.print_doc["pages"]]
        == ["001_2.png", "001_1.png", "002_1.png", "002_2.png"],
        str([Path(p["file"]).name for p in pdf_plan.print_doc["pages"]])
        if pdf_plan else "",
    )
    pdf_result = run_ingest(st.repo, agg_pdf)
    pdf_entry = [
        p.name
        for p in list_stage_images(st.repo.task_dir(agg_pdf) / "stages" / "input")
    ]
    ok(
        "汇集[PDF排版]：入口目录躺着待印刷的成品图（待打印列表有内容）",
        pdf_entry == ["001_1.png", "001_2.png", "002_1.png", "002_2.png"]
        and [p["label"] for p in st.repo.load_pages(agg_pdf)] == ["1", "2", "3", "4"],
        str(pdf_entry),
    )
    ok(
        "汇集[PDF排版]：不合并成员 PDF（创建时没有输出）且起点未完成",
        not (st.repo.scoped_stage_dir(agg_pdf, None, "print") / "print.pdf").exists()
        and st.repo.completed_aggregate_stages(agg_pdf) == []
        and pdf_result.pages == 4,
        f"done={st.repo.completed_aggregate_stages(agg_pdf)} pages={pdf_result.pages}",
    )
    # 待打印列表真按成员保存的顺序来（plan_print_entries 的快照判断走通）
    from desktop.services.print_plan import plan_print_entries

    pdf_entries, _pdf_doc = plan_print_entries(
        list_stage_images(st.repo.task_dir(agg_pdf) / "stages" / "input"),
        st.repo.load_print_doc(agg_pdf),
    )
    ok(
        "汇集[PDF排版]：待打印列表按成员保存的顺序排列（001 先 2 后 1）",
        [Path(e["file"]).name for e in pdf_entries]
        == ["001_2.png", "001_1.png", "002_1.png", "002_2.png"],
        str([Path(e["file"]).name for e in pdf_entries]),
    )
    # 起点=PDF排版的聚合任务**不走**"只读图片清单"那条路：它有汇集来的输入、
    # 要现场执行（2026-11-18 晚口径），第四步照常显示待打印列表 + 执行按钮。
    d_pdf = st.ctx.d
    ok("详情页：聚合（起点=PDF排版）装得进去", d_pdf.set_task(agg_pdf) is True, "")
    pump(st.app, times=8)
    ok(
        "详情页：PDF排版起点不算「输入节点」且**能跑**（输出由本任务生成）",
        d_pdf.current_stage() == "print"
        and not d_pdf._is_aggregate_input_node()
        and d_pdf.run_button.isEnabled()
        and d_pdf._stage_inputs_ready(),
        f"{d_pdf.current_stage()} / {d_pdf._is_aggregate_input_node()}"
        f" / {d_pdf.run_button.isEnabled()} / ready={d_pdf._stage_inputs_ready()}",
    )

    # 清场本段建的任务
    for tid in (st.agg_ing, st.agg_det, st.agg_ext2, agg_pdf, st.tid_c, st.tid_d, st.tid_e):
        if st.repo.get_task(tid):
            st.repo.delete_task(tid)
    st.panel = AggregateCreatePanel(st.repo)
    ok(
        "面板：没成员时流程根回落默认「图片拼版」",
        st.panel.current_stage() == DEFAULT_START_STAGE == "imposition",
        st.panel.current_stage(),
    )
    ok("面板：没选成员不能提交", not st.panel.can_submit(), "")
    ok(
        "面板：没编辑过流程 ⇒ result_diagram 为 None（store 落派生图）",
        st.panel.result_diagram() is None,
        "",
    )

    st.panel.set_members([st.tid_b, st.tid_a])
    ok(
        "面板：成员按设置顺序回填",
        st.panel.members() == [st.tid_b, st.tid_a],
        str(st.panel.members()),
    )
    # tid_b 什么都没跑、tid_a 完成到检测 ⇒ 没有"人人都完成"的公共节点，
    # 默认落到并集里**最靠前**的那个（起点越早越不丢页）
    ok(
        "面板：默认落点 = 并集最早那个（缺页风险最小）",
        st.panel.current_stage() == "extract",
        st.panel.current_stage(),
    )
    ok(
        "面板：起始节点全体共用（各成员节点值相同）",
        st.panel.member_stages() == ["extract", "extract"],
        str(st.panel.member_stages()),
    )
    ok("面板：选了成员可以提交", st.panel.can_submit(), "")

    # 成员提交（信号负载：成员 + 各成员节点）
    got: list = []
    st.panel.submitted.connect(lambda m, s, d: got.append((m, s, d)))
    st.panel.submit()
    ok(
        "面板：submit 发出 (成员, 各成员节点, None)",
        got == [([st.tid_b, st.tid_a], ["extract", "extract"], None)],
        str(got),
    )

    # 排序交互：上移/下移/移除（行内按钮入口；⚠️ 移动后当前行跟随被移的那条）
    st.panel.member_table.selectRow(1)
    st.panel._on_move(-1)
    ok(
        "面板：上移真的会交换（[下册,上册]→[上册,下册]）",
        st.panel.members() == [st.tid_a, st.tid_b],
        str(st.panel.members()),
    )
    st.panel._on_move(1)  # 当前行 0，下移 → 还原
    ok(
        "面板：再下移回原位（顺序还原）",
        st.panel.members() == [st.tid_b, st.tid_a],
        str(st.panel.members()),
    )
    st.panel.member_table.selectRow(0)
    st.panel._on_move(-1)
    ok(
        "面板：第 0 条再上移不动（越界安全）",
        st.panel.members() == [st.tid_b, st.tid_a],
        str(st.panel.members()),
    )
    st.panel.member_table.selectRow(1)
    st.panel._on_move(1)
    ok(
        "面板：末条下移不动（越界安全）",
        st.panel.members() == [st.tid_b, st.tid_a],
        str(st.panel.members()),
    )
    st.panel.member_table.selectRow(0)
    st.panel._on_move(1)
    ok(
        "面板：下移把上册换到前面（顺序真的会变）",
        st.panel.members() == [st.tid_a, st.tid_b],
        str(st.panel.members()),
    )
    st.panel.member_table.selectRow(0)
    st.panel._on_remove()
    ok(
        "面板：移除后只剩一个成员",
        st.panel.members() == [st.tid_b] and st.panel.member_stages() == ["extract"],
        f"{st.panel.members()} / {st.panel.member_stages()}",
    )

