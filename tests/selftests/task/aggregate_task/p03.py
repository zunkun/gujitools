# -*- coding: utf-8 -*-
"""起始节点：checkbox 单选，候选来自**已完成**的任务节点 / 用户实证回归（2026-11-18）：三个子集进度不同步 / 0 成员占位行（用户 2026-11-18：子任务列表 0 条时给一行空白占位） / toast 同条去重（用户 2026-11-18：没选子任务报错「提示了多条」） / 4. 成员选择弹窗（不 exec）"""

from typing import Any


def run(st: Any) -> None:
    from desktop.components.aggregate_create_panel import (
        MEMBER_HEADER_HEIGHT,
        MEMBER_PAGE_SIZE,
        AggregateCreatePanel,
        AggregateMemberPicker,
        DEFAULT_START_STAGE,
    )
    from qfluentwidgets import BodyLabel, CheckBox, PushButton
    from qfluentwidgets import InfoBar
    from PySide6.QtWidgets import QLabel, QScrollArea
    from desktop.ui import theme as T
    from desktop.workers import TaskRowsWorker
    from PySide6.QtWidgets import QWidget as _QWidget
    from tests.selftests._context import ok, pump
    from desktop.ui.toast import show_toast
    ok(
        "面板：表格列 = 序号/任务名称/任务节点/操作",
        st.panel.MEMBER_COLUMNS == ["序号", "任务名称", "任务节点", "操作"],
        str(st.panel.MEMBER_COLUMNS),
    )
    # 任务节点列（只读）：tid_b 什么都没完成 ⇒ 灰字占位
    node_wrap = st.panel.member_table.cellWidget(0, 2)
    node_texts = [l.text() for l in node_wrap.findChildren(QLabel)]
    ok(
        "面板：没完成任何节点的子任务显示灰字占位",
        node_texts and "暂无已完成节点" in node_texts[0],
        str(node_texts),
    )
    # 操作列「详情」入口：点击冒 detail_requested(该子任务)
    seen_detail: list = []
    st.panel.detail_requested.connect(seen_detail.append)
    action_wrap = st.panel.member_table.cellWidget(0, 3)
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
        st.panel.member_table.columnWidth(3) >= 220,
        str(st.panel.member_table.columnWidth(3)),
    )
    ok(
        "面板：任务节点列不窄于下限（节点名要能显示全）",
        st.panel.member_table.columnWidth(2) >= st.panel._STAGE_WIDTH,
        str(st.panel.member_table.columnWidth(2)),
    )
    # 列宽是**按内容实测**的（用户 2026-11-17：「宽一些，能够显示完整节点」）
    _long_wrap = st.panel._node_widget(["detect", "rembg", "imposition", "print"])
    st.panel.member_table.setRowCount(st.panel.member_table.rowCount() + 1)
    st.panel.member_table.setCellWidget(
        st.panel.member_table.rowCount() - 1, 2, _long_wrap)
    st.panel._fit_stage_column()
    ok(
        "面板：任务节点列宽 ≥ 最长一行的实际所需（长节点串不裁字）",
        st.panel.member_table.columnWidth(2) >= _long_wrap.sizeHint().width(),
        f"{st.panel.member_table.columnWidth(2)} vs {_long_wrap.sizeHint().width()}",
    )
    st.panel._fill_members()          # 还原成真实成员的列宽与行数
    ok(
        "面板：选成员按钮文案是「选择子任务…」",
        st.panel.pick_button.text().startswith("选择子任务"),
        st.panel.pick_button.text(),
    )
    detail_btns[0].click()
    ok(
        "面板：点「详情」发 detail_requested(该子任务)",
        seen_detail == [st.tid_b],
        str(seen_detail),
    )
    ok(
        "面板：候选节点是 checkbox（列举出来，不是下拉框）",
        bool(st.panel._stage_boxes)
        and all(isinstance(b, CheckBox) for b in st.panel._stage_boxes.values()),
        str([type(b).__name__ for b in st.panel._stage_boxes.values()]),
    )
    # 此刻唯一的成员 tid_b 一个节点都没完成 ⇒ 并集为空 ⇒ 兜底列全集
    # （列表空着用户连"先选一个"都做不到），但提示要说真话
    ok(
        "面板：成员一个节点都没完成 ⇒ 兜底列全部候选（按拓扑序）",
        st.panel.start_candidates()
        == ("extract", "detect", "rembg", "imposition", "print"),
        str(st.panel.start_candidates()),
    )
    ok(
        "面板：兜底时提示里说明「都还没有完成任何节点」",
        "没有完成" in st.panel.stage_hint.text(),
        st.panel.stage_hint.text(),
    )
    ok(
        "面板：候选含「提取图片」（用户 2026-11-18：提取也能当起点）",
        "extract" in st.panel.start_candidates(),
        str(st.panel.start_candidates()),
    )
    ok(
        "面板：当前起始节点那一个勾着（其余不勾）",
        [k for k, b in st.panel._stage_boxes.items() if b.isChecked()]
        == [st.panel.current_stage()],
        str({k: b.isChecked() for k, b in st.panel._stage_boxes.items()}),
    )

    # 单选：勾另一个 ⇒ 只留一个；派生图跟着换
    st.panel._stage_boxes["detect"].setChecked(True)
    ok(
        "面板：勾「检测文本框」⇒ 单选（别的自动灭）+ 图从检测开始",
        st.panel.current_stage() == "detect"
        and [k for k, b in st.panel._stage_boxes.items() if b.isChecked()] == ["detect"]
        and st.panel.current_diagram().stage_order()
        == ("detect", "rembg", "imposition", "print"),
        f"{st.panel.current_stage()} / {st.panel.current_diagram().stage_order()}",
    )
    ok("面板：换节点后仍未标记「已编辑」", not st.panel.uses_custom_flow(), "")
    st.panel._stage_boxes["print"].setChecked(True)
    ok(
        "面板：勾「PDF排版」⇒ 流程只剩 PDF排版",
        st.panel.current_stage() == "print"
        and st.panel.current_diagram().stage_order() == ("print",),
        str(st.panel.current_diagram().stage_order()),
    )
    # 点掉当前唯一勾选**不生效**（不能出现"没有起始节点"）
    st.panel._stage_boxes["print"].setChecked(False)
    ok(
        "面板：点掉当前唯一勾选不生效（单选恒有一个）",
        st.panel.current_stage() == "print" and st.panel._stage_boxes["print"].isChecked(),
        str({k: b.isChecked() for k, b in st.panel._stage_boxes.items()}),
    )
    # 不在候选里的节点：设不上去（不偷偷改数据）
    st.panel.set_start_stage("nope")
    ok(
        "面板：垃圾节点设不上去（不在候选里）",
        st.panel.current_stage() == "print",
        st.panel.current_stage(),
    )
    # extract 现在**可以**设上（用户 2026-11-18）
    st.panel.set_start_stage("extract")
    ok(
        "面板：extract 能当起点（流程从提取开始，全部步骤都在）",
        st.panel.current_stage() == "extract"
        and st.panel.current_diagram().stage_order()
        == ("extract", "detect", "rembg", "imposition", "print"),
        f"{st.panel.current_stage()} / {st.panel.current_diagram().stage_order()}",
    )
    st.panel.set_start_stage("print")

    # 候选随成员变：并集口径——tid_a{提取,检测} + tid_b{PDF排版}
    run_id = st.repo.create_stage_run(st.tid_b, "print", {})
    st.repo.finish_stage(st.tid_b, run_id, "success")
    st.panel.set_members([st.tid_a, st.tid_b])
    ok(
        "面板：成员变了候选跟着变（并集：提取/检测/PDF排版）",
        st.panel.start_candidates() == ("extract", "detect", "print"),
        str(st.panel.start_candidates()),
    )
    st.panel.set_start_stage("detect")
    ok(
        "面板：换成员后起始节点是 detect",
        st.panel.current_stage() == "detect",
        st.panel.current_stage(),
    )
    # 任务节点列：tid_a 在第 0 行，显示它已完成的「检测文本框」
    node_texts_a = [
        l.text() for l in st.panel.member_table.cellWidget(0, 2).findChildren(QLabel)
    ]
    ok(
        "面板：任务节点列显示该子任务已完成的节点（tid_a：检测）",
        node_texts_a and "检测" in "".join(node_texts_a),
        str(node_texts_a),
    )
    st.panel.set_members([st.tid_b])
    ok(
        "面板：候选按已完成节点收窄（tid_b 只完成了 print）",
        st.panel.start_candidates() == ("print",),
        str(st.panel.start_candidates()),
    )
    ok(
        "面板：起始节点不在新候选里 ⇒ 自动落到候选第一个（图也跟着换）",
        st.panel.current_stage() == "print"
        and st.panel.current_diagram().stage_order() == ("print",),
        f"{st.panel.current_stage()} / {st.panel.current_diagram().stage_order()}",
    )
    ok(
        "面板：自动落位后勾选框也只勾那一个",
        [k for k, b in st.panel._stage_boxes.items() if b.isChecked()] == ["print"],
        str({k: b.isChecked() for k, b in st.panel._stage_boxes.items()}),
    )
    probe_done = st.repo.create_task(st.ctx.pdf, "agg-probe-done", "探针·检测")
    probe_rem = st.repo.create_task(st.ctx.big_pdf, "agg-probe-rem", "探针·去底")
    for tid, stages in (
        (probe_done, ("extract", "detect")),
        (probe_rem, ("extract", "rembg")),
    ):
        for stage in stages:
            rid = st.repo.create_stage_run(tid, stage, {})
            st.repo.finish_stage(tid, rid, "success")
    st.panel.set_members([probe_done, probe_rem])
    ok(
        "面板回归：候选 = 生效节点的并集（提取/检测/去底）",
        st.panel.start_candidates() == ("extract", "detect", "rembg"),
        str(st.panel.start_candidates()),
    )
    ok(
        "面板回归：谁都没跑过的节点不再出现（拼版/PDF排版）",
        not {"imposition", "print"} & set(st.panel.start_candidates()),
        str(st.panel.start_candidates()),
    )
    ok(
        "面板回归：勾选框跟着只列这三个（不再有拼版）",
        list(st.panel._stage_boxes) == ["extract", "detect", "rembg"],
        str(list(st.panel._stage_boxes)),
    )
    st.panel.set_start_stage("rembg")
    ok(
        "面板回归：提示点名没跑去底的那个子任务（别静默少册）",
        "探针·检测" in st.panel.stage_hint.text()
        and "探针·去底" not in st.panel.stage_hint.text(),
        st.panel.stage_hint.text(),
    )
    st.panel.set_start_stage("extract")
    ok(
        "面板回归：选提取 ⇒ 没有缺节点的子任务（提示里不再点名）",
        "未完成" not in st.panel.stage_hint.text(),
        st.panel.stage_hint.text(),
    )
    for tid in (probe_done, probe_rem):
        st.repo.delete_task(tid)

    # 编辑标记：编辑器内容变了 ⇒ result_diagram 交图
    st.panel._on_diagram_changed()
    ok(
        "面板：编辑器变更 ⇒ result_diagram 交图",
        st.panel.result_diagram() is st.panel.current_diagram(),
        "",
    )
    st.panel.reset()
    ok(
        "面板：reset 后成员清空、起始节点回默认、候选回全部节点",
        st.panel.members() == []
        and st.panel.member_stages() == []
        and st.panel.current_stage() == DEFAULT_START_STAGE
        and st.panel.start_candidates()
        == ("extract", "detect", "rembg", "imposition", "print"),
        f"{st.panel.members()} / {st.panel.current_stage()} / {st.panel.start_candidates()}",
    )
    ok("面板：reset 后「已编辑」标记清回", st.panel.result_diagram() is None, "")
    ok(
        "表格：0 个成员也有一行空白占位（不塌成只剩表头）",
        st.panel.member_table.rowCount() == 1
        and st.panel.member_table.cellWidget(0, 2) is None
        and st.panel.member_table.cellWidget(0, 3) is None
        and st.panel.member_table.item(0, 0) is None
        and st.panel.member_table.height()
        == MEMBER_HEADER_HEIGHT + st.panel.MEMBER_ROW_HEIGHT + 2,
        f"{st.panel.member_table.rowCount()} 行 / 高 {st.panel.member_table.height()}",
    )
    # 占位行是纯装饰：成员一旦选上，立刻恢复成真数据
    st.panel.set_members([st.tid_b])
    ok(
        "表格：占位行只在 0 成员时出现（选上成员回到真数据）",
        st.panel.member_table.rowCount() == 1
        and st.panel.member_table.cellWidget(0, 3) is not None,
        f"{st.panel.member_table.rowCount()} 行 / 操作列="
        f"{st.panel.member_table.cellWidget(0, 3) is not None}",
    )
    st.panel.deleteLater()
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
    pump(st.app, times=2)
    show_toast(host, "warning", "还没有选择子任务", "点「选择子任务…」至少选一个。")
    _bars3 = host.findChildren(InfoBar)
    ok(
        "toast：上一条关掉后，同样的话能再弹（新的一条）",
        len(_bars3) == 1 and _bars3[0] is not _bars1[0],
        str(len(_bars3)),
    )
    host.deleteLater()
    from desktop.workers import TaskRowsWorker

    worker = TaskRowsWorker(st.repo)
    rows: list = []
    worker.completed.connect(rows.extend)
    worker.run()
    ok(
        "弹窗前置：TaskRowsWorker 行里带了任务节点胶囊",
        all(isinstance(r.get("stages"), list) for r in rows),
        "",
    )

    st.picker = AggregateMemberPicker(rows, [], None)
    ok(
        "弹窗：候选不含聚合任务（不能嵌套聚合）",
        all(r.get("kind") != "aggregate" for r in st.picker._all_rows),
        str([r.get("id") for r in st.picker._all_rows]),
    )
    ok(
        "弹窗：表格列 = （空）/序号/任务名称/任务节点/创建时间（表头不放文字）",
        [
            st.picker.table.horizontalHeaderItem(i).text()
            for i in range(st.picker.table.columnCount())
        ]
        == st.picker.COLUMNS,
        str(
            [
                st.picker.table.horizontalHeaderItem(i).text()
                for i in range(st.picker.table.columnCount())
            ]
        ),
    )
    ok("弹窗：默认全不勾", st.picker.checked_ids() == [], str(st.picker.checked_ids()))
    # 倒序：新建的任务排在最前（用户 2026-11-18：「任务列表要倒序」）
    ids_desc = [str(r.get("id")) for r in st.picker._all_rows]
    ok(
        "弹窗：候选按任务号倒序（最新建的排第一页最上）",
        ids_desc == sorted(ids_desc, reverse=True),
        str(ids_desc),
    )
    ok(
        "弹窗：实际驱动本次用例的两个任务也按倒序（tid_b 在前）",
        ids_desc.index(st.tid_b) < ids_desc.index(st.tid_a),
        f"{st.tid_b} @{ids_desc.index(st.tid_b)} / {st.tid_a} @{ids_desc.index(st.tid_a)}",
    )
    # 预勾选回填：构造时传入的成员保持勾选
    picker2 = AggregateMemberPicker(rows, [st.tid_a], None)
    ok(
        "弹窗：构造传入的已选成员回填为勾选",
        picker2.checked_ids() == [st.tid_a],
        str(picker2.checked_ids()),
    )
    picker2.deleteLater()
    # 勾两个：checked_ids 按列表顺序（任务号倒序）返回，与勾的先后无关
    st.picker.set_checked(st.tid_a, True)
    st.picker.set_checked(st.tid_b, True)
    checked = st.picker.checked_ids()
    ok(
        "弹窗：勾选按任务号倒序返回（与勾的先后无关）",
        checked == sorted(checked, reverse=True)
        and st.tid_a in checked and st.tid_b in checked,
        str(checked),
    )
    # 取消勾选
    st.picker.set_checked(st.tid_b, False)
    ok(
        "弹窗：取消勾选真的会移除",
        st.picker.checked_ids() == [st.tid_a],
        str(st.picker.checked_ids()),
    )

    # 搜索：与列表页同一套匹配判据（任务名/源文件名子串，大小写不敏感）
    st.picker.search_edit.setText("上册")
    ok(
        "弹窗：搜索按关键词过滤（子集·上册命中）",
        [r["id"] for r in st.picker._filtered] == [st.tid_a],
        str([r["id"] for r in st.picker._filtered]),
    )
    ok(
        "弹窗：搜索后提示匹配数",
        "1" in st.picker.match_hint.text(),
        st.picker.match_hint.text(),
    )
    st.picker.search_edit.setText("")
    ok("弹窗：清空搜索恢复全量", len(st.picker._filtered) == len(st.picker._all_rows), "")

    # 分页：造 15 条合成行验证切片（不动 store，别给列表页添垃圾）
    # 勾选状态跨 set_rows 保留（设计行为：弹窗里换搜索词不丢勾），
    # 这里先清掉 tid_a 再验分页断言。
    st.picker.set_checked(st.tid_a, False)
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
    st.picker.set_rows(fake)
    ok(
        "弹窗：set_rows 整批替换候选并回第 1 页",
        st.picker.pagination.pager().total == 15
        and st.picker.pagination.pager().clamped_page == 1,
        f"{st.picker.pagination.pager().total}/{st.picker.pagination.pager().clamped_page}",
    )
    ok(
        "弹窗：第 1 页只有前 10 行（默认每页 10 条）",
        st.picker.table.rowCount() == 10,
        str(st.picker.table.rowCount()),
    )
    st.picker.set_checked("9001", True)
    st.picker._on_page_changed(2)
    ok(
        "弹窗：翻到第 2 页只剩 5 行",
        st.picker.table.rowCount() == 5,
        str(st.picker.table.rowCount()),
    )
    ok(
        "弹窗：跨页勾选不丢（翻页再翻回来还在）",
        st.picker.checked_ids() == ["9001"],
        str(st.picker.checked_ids()),
    )
    st.picker._on_page_changed(99)
    ok(
        "弹窗：越界页码钳制回末页",
        st.picker.pagination.pager().clamped_page == 2,
        str(st.picker.pagination.pager().clamped_page),
    )
    st.picker._on_page_size_changed(50)
    ok(
        "弹窗：换每页 50 条后一页装下全部",
        st.picker.table.rowCount() == 15,
        str(st.picker.table.rowCount()),
    )

