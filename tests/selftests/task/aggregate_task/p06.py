# -*- coding: utf-8 -*-
"""起始节点可切换 + 保存时提示「历史数据作废」（用户 2026-11-18） / 8. 清场（删本模块建的任务）"""

from typing import Any


def run(st: Any) -> None:
    from desktop.shell import ModuleShell
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QPoint, Qt
    from pathlib import Path as _Path
    import io as _io
    from desktop.steps.aggregate import (
        AGGREGATE_START_LABEL,
        AGGREGATE_START_STAGES,
        aggregate_start_label,
        derive_aggregate_diagram,
    )
    from tests.selftests._context import ok, pump
    from desktop.steps.aggregate import aggregate_start_label, derive_aggregate_diagram

    others = [k for k in st.agg_panel._stage_boxes if k != "rembg"]
    ok("流程页：候选里还有别的起点可选（能真的切）", bool(others), str(list(st.agg_panel._stage_boxes)))
    new_stage = others[0]
    QTest.mouseClick(st.agg_panel._stage_boxes[new_stage], Qt.MouseButton.LeftButton)
    pump(st.app)
    ok(
        "流程页：点另一个起点 ⇒ 选中项跟着换（仍然是单选）",
        st.agg_panel.current_stage() == new_stage
        and [k for k, b in st.agg_panel._stage_boxes.items() if b.isChecked()] == [new_stage],
        str({k: b.isChecked() for k, b in st.agg_panel._stage_boxes.items()}),
    )
    ok(
        "流程页：改过起点 ⇒ stage_changed() 为真（落库值仍是去底色）",
        st.agg_panel.stage_changed() and st.agg_panel.record_stage() == "rembg",
        f"changed={st.agg_panel.stage_changed()} record={st.agg_panel.record_stage()}",
    )
    ok(
        "流程页：画布按新起点重建（起点之前的那步被丢掉）",
        st.agg_panel.current_diagram().stage_order()
        == derive_aggregate_diagram(new_stage).stage_order(),
        str(st.agg_panel.current_diagram().stage_order()),
    )
    # 提示框：构造与 exec() 分开（离屏绝不真弹模态）
    _warn = st.flow_page._build_start_change_dialog("rembg", new_stage)
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

    _flow_file = _Path(st.repo.task_dir(st.agg_final)) / "flow.bpmn"
    _before = _io.open(_flow_file, "rb").read()
    _saved: list = []
    _changed: list = []
    _closed: list = []
    st.flow_page.flow_saved.connect(_saved.append)
    st.flow_page.aggregate_start_changed.connect(_changed.append)
    st.flow_page.closed.connect(lambda: _closed.append(True))
    st.flow_page._confirm_start_change = lambda old, new: False     # 替身：用户点「取消」
    st.flow_page._on_done(True)
    pump(st.app)
    ok(
        "流程页：提示框点「取消」⇒ 流程没写盘、record 没改、页面没切走",
        _io.open(_flow_file, "rb").read() == _before
        and (st.repo.get_task(st.agg_final) or {}).get("member_stage") == "rembg"
        and not _saved and not _changed and not _closed,
        f"saved={_saved} changed={_changed} closed={_closed}",
    )
    ok(
        "流程页：取消后起点仍停在用户刚选的那个（可以改回去再存）",
        st.agg_panel.current_stage() == new_stage and st.agg_panel.stage_changed(),
        st.agg_panel.current_stage(),
    )
    # 确认：record 一起改 + 图按新起点落盘 + 发两条信号（先重取、后回详情页）
    st.flow_page._confirm_start_change = lambda old, new: True      # 替身：用户点「确认」
    order: list = []
    st.flow_page.aggregate_start_changed.connect(lambda _t: order.append("restart"))
    st.flow_page.flow_saved.connect(lambda _t: order.append("saved"))
    st.flow_page._on_done(True)
    pump(st.app)
    _record = st.repo.get_task(st.agg_final) or {}
    ok(
        "流程页：确认后 record 的起点一起改（member_stage/member_stages 同口径）",
        _record.get("member_stage") == new_stage
        and _record.get("member_stages") == [new_stage] * len(_record.get("members") or []),
        f"{_record.get('member_stage')} / {_record.get('member_stages')}",
    )
    ok(
        "流程页：确认后流程图按新起点落盘（详情页的起点节点能找到）",
        st.repo.task_diagram(st.agg_final).stage_order()
        == derive_aggregate_diagram(new_stage).stage_order(),
        str(st.repo.task_diagram(st.agg_final).stage_order()),
    )
    ok(
        "流程页：先发「按新起点重新汇集」再发「回详情页」（页面不会先说没输入）",
        order[-2:] == ["restart", "saved"] and _changed[-1] == st.agg_final,
        str(order),
    )
    ok(
        "流程页：落库后 stage_changed() 复归假（再点保存不会又弹一次框）",
        not st.agg_panel.stage_changed() and st.agg_panel.record_stage() == new_stage,
        f"changed={st.agg_panel.stage_changed()} record={st.agg_panel.record_stage()}",
    )
    # 壳层接线：收到 aggregate_start_changed ⇒ 让详情页按新起点重取
    from desktop.shell import ModuleShell

    _shell = ModuleShell(st.repo)
    _detail = _shell._ensure_detail_page()
    _detail.task_id = st.agg_final          # 假装详情页正停在这个任务上
    _restarted: list = []
    _detail.restart_aggregate_ingest = lambda tid: _restarted.append(tid) or True
    _shell._on_aggregate_start_changed(st.agg_final)
    ok(
        "壳层：聚合任务改起点后自动按新起点重新汇集（不用再点页头 ⟳）",
        _restarted == [st.agg_final],
        str(_restarted),
    )
    _shell.deleteLater()

    # 回归：普通任务照旧只有流程画布
    ok(
        "流程页：普通任务仍是原来的流程画布（没被聚合分支抢走）",
        st.flow_page.open_task(st.tid_a)
        and st.flow_page._panel is not None
        and st.flow_page._aggregate_panel is None
        and "任务流程" in st.flow_page.title.text()
        and "聚合" not in st.flow_page.title.text(),
        st.flow_page.title.text(),
    )
    st.flow_page.deleteLater()
    for tid in (st.agg_id, st.agg_id2, st.agg_id3, st.opened[-1] if st.opened else None, st.tid_a, st.tid_b):
        if tid and st.repo.get_task(tid):
            st.repo.delete_task(tid)
    st.w.list_page.refresh()
    pump(st.app, times=8)
    ok(
        "清场：本模块建的任务已删净",
        all(st.repo.get_task(t) is None for t in (st.agg_id, st.agg_id2, st.agg_id3, st.tid_a, st.tid_b)),
        "",
    )

