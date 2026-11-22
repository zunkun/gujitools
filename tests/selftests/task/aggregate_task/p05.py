# -*- coding: utf-8 -*-
"""起点=提取的聚合任务：那一步当**输入节点**显示图片清单 / 起点=去底色 / 检测：同样要把汇集来的图列在第一步 / 汇集期间的**分批显示**（用户 2026-11-18：「如果时间长，是否可以 / 7. 详情页「流程」入口（用户 2026-11-18）"""

from typing import Any


def run(st: Any) -> None:
    from qfluentwidgets import BodyLabel, CheckBox, PushButton
    from desktop.ui.widgets import SegmentedToggle, StatusChip
    from desktop.pages.taskflow.page import TaskFlowPage
    from tests.selftests._context import ok, pump
    from desktop.services.aggregate_ingest import (
        aggregate_page_name,
        plan_ingest,
        run_ingest,
    )
    from desktop.services.aggregate_ingest import set_pending_marker
    from tests.selftests._context import wait_until
    for tid, names in ((st.tid_a, ["1.jpg"]), (st.tid_b, ["1.jpg", "2.jpg"])):
        st._make_images(st.repo.task_dir(tid) / "stages" / "extract", names)
        run_id = st.repo.create_stage_run(tid, "extract", {})
        st.repo.finish_stage(tid, run_id, "success")
    st.agg_ext = st.repo.create_aggregate_task([st.tid_a, st.tid_b], "extract", "汇集·提取起点")
    run_ingest(st.repo, st.agg_ext)
    st.d = st.ctx.d
    ok("详情页：聚合（起点=提取）装得进去", st.d.set_task(st.agg_ext) is True, "")
    pump(st.app, times=10)
    ok(
        "详情页：extract 这一步被判成聚合任务的**输入节点**",
        st.d._is_aggregate_input_node() and st.d.current_stage() == "extract",
        f"{st.d._is_aggregate_input_node()} / {st.d.current_stage()}",
    )
    ok(
        "详情页：提取步骤换成只读图片清单（不是 PDF 查看器）",
        st.d.extract_viewer_host.currentWidget() is st.d.extract_input_viewer,
        type(st.d.extract_viewer_host.currentWidget()).__name__,
    )
    ok(
        "详情页：清单列出汇集来的 3 张图（1 + 2）",
        st.d.extract_input_viewer.strip.count() == 3 and len(st.d.pages or []) == 3,
        f"{st.d.extract_input_viewer.strip.count()} / {len(st.d.pages or [])}",
    )
    ok(
        "详情页：「提取文档图片」按钮置灰（作为输入节点不执行）",
        not st.d.run_button.isEnabled() and "输入节点" in st.d.run_button.toolTip(),
        f"{st.d.run_button.isEnabled()} / {st.d.run_button.toolTip()}",
    )
    ok(
        "详情页：状态行说明「无需执行」",
        "无需执行" in st.d.stage_status.text(),
        st.d.stage_status.text(),
    )
    # 快捷键/自动化绕过按钮直接触发也要拦住（否则会拿空源去起 worker）
    st.d.run_stage(resume=False)
    pump(st.app, times=4)
    ok(
        "详情页：硬触发执行也拦得住（不起 worker）",
        st.d.running_stage is None and getattr(st.d, "process", None) is None,
        f"{st.d.running_stage} / {getattr(st.d, 'process', None)}",
    )
    agg_rembg = st.repo.create_aggregate_task([st.tid_a, st.tid_b], "rembg", "汇集·去底起点")
    run_ingest(st.repo, agg_rembg)
    ok("详情页：聚合（起点=去底色）装得进去", st.d.set_task(agg_rembg) is True, "")
    pump(st.app, times=10)
    ok(
        "详情页：去底色起点**不算**纯展示起点、当前步就是它"
        "（2026-11-18 晚口径：保留完整操作能力，可重跑）",
        not st.d._is_aggregate_input_node() and st.d.current_stage() == "rembg",
        f"{st.d._is_aggregate_input_node()} / {st.d.current_stage()}",
    )
    ok(
        "详情页：去底色起点用**原图/成品对比**查看器（输入=汇集来的裁图，"
        "产出=成员的成品图，2026-11-18 晚口径）",
        st.d.rembg_viewer_host.currentWidget() is st.d.rembg_viewer,
        type(st.d.rembg_viewer_host.currentWidget()).__name__,
    )
    ok(
        "详情页：对比查看器把汇集来的输入图全列出来（与页清单同数）",
        len(st.d.rembg_viewer._paths) == len(st.d.pages or []) > 0,
        f"{len(st.d.rembg_viewer._paths)} / {len(st.d.pages or [])}",
    )
    ok(
        "详情页：去底色起点**可以再次执行**（输入齐、按钮可点，2026-11-18 晚口径）",
        st.d.run_button.isEnabled() and st.d._stage_inputs_ready(),
        f"enabled={st.d.run_button.isEnabled()} ready={st.d._stage_inputs_ready()}",
    )

    agg_det2 = st.repo.create_aggregate_task([st.tid_a, st.tid_b], "detect", "汇集·检测起点")
    run_ingest(st.repo, agg_det2)
    ok("详情页：聚合（起点=检测）装得进去", st.d.set_task(agg_det2) is True, "")
    pump(st.app, times=10)
    ok(
        "详情页：检测起点把图列出来（与页清单同数）且**可以再次检测/操作**"
        "（2026-11-18 晚口径：不再是纯展示）",
        not st.d._is_aggregate_input_node()
        and st.d.current_stage() == "detect"
        and st.d.detect_viewer.strip.count() == len(st.d.pages or []) > 0
        and st.d.run_button.isEnabled()
        and st.d._stage_inputs_ready(),
        f"{st.d.current_stage()} / {st.d.detect_viewer.strip.count()}"
        f" / {len(st.d.pages or [])} / enabled={st.d.run_button.isEnabled()}"
        f" ready={st.d._stage_inputs_ready()}",
    )
    for tid in (agg_rembg, agg_det2):
        st.repo.delete_task(tid)
    from desktop.services.aggregate_ingest import set_pending_marker

    agg_poll = st.repo.create_aggregate_task([st.tid_a, st.tid_b], "rembg", "汇集·分批")
    set_pending_marker(st.repo.task_dir(agg_poll), on=True)   # 模拟"还在复制"
    ok("详情页：汇集中的聚合任务装得进去", st.d.set_task(agg_poll) is True, "")
    st.d._select_stage(0)
    pump(st.app, times=6)
    ok(
        "详情页：还在汇集 ⇒ 清单为空但**轮询已启动**",
        st.d.current_stage() == "rembg"
        and st.d.rembg_viewer._paths == []
        and st.d._aggregate_start_poll.isActive(),
        f"{len(st.d.rembg_viewer._paths)} / {st.d._aggregate_start_poll.isActive()}",
    )
    # 模拟第一批文件复制落盘（输入先进入口目录）→ 轮询到点就该把它们列出来
    st._make_images(st.repo.task_dir(agg_poll) / "stages" / "input", ["001_1.png"])
    st.d._on_aggregate_start_poll()
    pump(st.app, times=6)
    ok(
        "详情页：落一批显示一批（1 张就先显示 1 张）",
        len(st.d.rembg_viewer._paths) == 1
        and "正在汇集" in st.d.stage_status.text(),
        f"{len(st.d.rembg_viewer._paths)} / {st.d.stage_status.text()}",
    )
    ok(
        "详情页：还在汇集 ⇒ 轮询继续排下一轮",
        st.d._aggregate_start_poll.isActive(),
        str(st.d._aggregate_start_poll.isActive()),
    )
    # 汇集结束（标记撤掉）⇒ 轮询停表，改由 aggregate_ready 整页重载收尾
    set_pending_marker(st.repo.task_dir(agg_poll), on=False)
    st.d._on_aggregate_start_poll()
    pump(st.app, times=4)
    ok(
        "详情页：汇集结束 ⇒ 轮询停表",
        not st.d._aggregate_start_poll.isActive(),
        str(st.d._aggregate_start_poll.isActive()),
    )
    st.repo.delete_task(agg_poll)

    # 普通任务不能被这条判据带偏：同一个「提取图片」步骤仍是 PDF 查看器 + 可执行
    ok("详情页：普通任务切回自己不受影响", st.d.set_task(st.tid_a) is True, "")
    pump(st.app, times=6)
    ok(
        "详情页：普通任务的提取步骤仍是 PDF 查看器、按钮可点",
        st.d.extract_viewer_host.currentWidget() is st.d.extract_result_viewer
        and st.d.run_button.isEnabled()
        and not st.d._is_aggregate_input_node(),
        f"{type(st.d.extract_viewer_host.currentWidget()).__name__}"
        f" / {st.d.run_button.isEnabled()}",
    )
    st.repo.delete_task(st.agg_ext)

    # 回列表，看「聚合」标记（列表刷新是后台线程，必须等它回来）
    st.w.shell.back_to_list()

    from tests.selftests._context import wait_until

    def _aggregate_chip_visible() -> bool:
        table = st.w.list_page.table.table
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
        wait_until(st.app, _aggregate_chip_visible, timeout=10.0),
        "",
    )
    from desktop.pages.taskflow.page import TaskFlowPage

    st.flow_page = TaskFlowPage(st.repo)
    st.flow_page.resize(1200, 900)
    st.flow_page.show()
    pump(st.app)
    ok(
        "流程页：聚合任务打开的是聚合一整套（不是光一张流程图）",
        st.flow_page.open_task(st.agg_final)
        and st.flow_page._aggregate_panel is not None
        and st.flow_page._panel is None,
        f"agg={st.flow_page._aggregate_panel is not None} "
        f"flow={st.flow_page._panel is not None}",
    )
    st.agg_panel = st.flow_page._aggregate_panel
    ok(
        "流程页：标题点明是聚合任务流程",
        st.flow_page.title.text().startswith("聚合任务流程")
        and st.flow_page._task_id == st.agg_final,
        st.flow_page.title.text(),
    )
    ok(
        "流程页：子任务按落库顺序回填（两行）",
        st.agg_panel.members() == [st.tid_a, st.tid_b]
        and st.agg_panel.member_table.rowCount() == 2,
        f"{st.agg_panel.members()} / {st.agg_panel.member_table.rowCount()} 行",
    )
    ok(
        "流程页：起始节点回填成落库的那个（去底色）",
        st.agg_panel.current_stage() == "rembg",
        st.agg_panel.current_stage(),
    )
    ok(
        "流程页：画布就是磁盘上那张 flow.bpmn（不是另派生的）",
        st.agg_panel.current_diagram().stage_order()
        == st.repo.task_diagram(st.agg_final).stage_order(),
        str(st.agg_panel.current_diagram().stage_order()),
    )
    ok(
        "流程页：查看模式不给改成员（「选择子任务…」与底部按钮行收起）",
        st.agg_panel.pick_button.isHidden() and st.agg_panel._button_bar.isHidden(),
        f"选择按钮隐藏={st.agg_panel.pick_button.isHidden()} / "
        f"按钮行隐藏={st.agg_panel._button_bar.isHidden()}",
    )
    ok(
        "流程页：起始节点勾选框**可切换**（勾着落库那个，且都能点）",
        all(b.isEnabled() for b in st.agg_panel._stage_boxes.values())
        and [k for k, b in st.agg_panel._stage_boxes.items() if b.isChecked()] == ["rembg"],
        str({k: (b.isChecked(), b.isEnabled()) for k, b in st.agg_panel._stage_boxes.items()}),
    )
    ok(
        "流程页：行内操作只剩「详情」（没有上移/下移/删除）",
        [b.text() for b in st.agg_panel.member_table.cellWidget(0, 3).findChildren(PushButton)]
        == ["详情"],
        str([
            b.text()
            for b in st.agg_panel.member_table.cellWidget(0, 3).findChildren(PushButton)
        ]),
    )
    # 保存：落盘 + 通知宿主回详情页（与普通任务同一条链路）
    saved: list = []
    st.flow_page.flow_saved.connect(saved.append)
    st.flow_page._on_done(True)
    ok(
        "流程页：保存流程落盘并通知宿主（聚合任务同一条路径）",
        saved == [st.agg_final]
        and bool(st.repo.task_diagram(st.agg_final).stage_order()),
        f"{saved} / {st.repo.task_diagram(st.agg_final).stage_order()}",
    )
    # 成员「详情」：非模态预览窗（和创建页同一个实现）
    st.agg_panel.detail_requested.emit(st.tid_a)
    _pdlg = st.flow_page._previews.get(st.tid_a)
    ok(
        "流程页：子任务「详情」弹非模态预览窗（不跳走、不「当当」）",
        _pdlg is not None and _pdlg.isVisible() and _pdlg.isModal() is False,
        f"{_pdlg is not None} / modal={getattr(_pdlg, 'isModal', lambda: None)()}",
    )
    st.flow_page._close_previews()
    ok("流程页：离开本页时预览窗一起收", st.flow_page._previews == {}, "")

