# -*- coding: utf-8 -*-
"""``flow_validate`` 第 5 章：两个保存入口的闸（面板 / 二级页）。"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from ._helpers import _chain


def run(st) -> None:
    _check_panel_gate(st.ctx, st.ok)
    _check_flow_page_gate(st.ctx, st.ok)


# ------------------------------------------ ⑤ 弹窗/内嵌编辑器的保存闸
def _check_panel_gate(ctx, ok) -> None:
    """``FlowPanel.accept`` 对不合法的图**不落盘、不结束**。"""
    from desktop.components.flow_dialog import FlowPanel

    app, w = ctx.app, ctx.w
    _ = w
    illegal = _chain("print", "rembg")
    panel = FlowPanel(illegal)
    panel.resize(1040, 720)
    panel.show()
    app.processEvents()
    try:
        panel.accept()
        app.processEvents()
        ok("不合法流程点「保存流程」被拒绝（不置 accepted）",
           not panel.edited() and panel.result_diagram() is None,
           str(panel.edited()))
        ok("拒绝时摘要行写明原因（点名「PDF排版」）",
           "PDF排版" in panel.summary.text(), panel.summary.text())

        # 换成合法的图：同一个面板、同一颗按钮，要能正常保存
        panel.editor_panel._canvas.set_diagram(_chain("detect", "rembg",
                                                      "print"))
        app.processEvents()
        panel.accept()
        app.processEvents()
        ok("换成合法流程后「保存流程」放行",
           panel.edited() and panel.result_diagram() is not None)
    finally:
        panel.close()
        app.processEvents()


# ---------------------------------------------- ⑥ 流程编辑二级页的保存闸
def _check_flow_page_gate(ctx, ok) -> None:
    """``TaskFlowPage._on_done`` 对不合法的图不落盘、不切页。"""
    from desktop.store import TaskStore
    from desktop.pages.taskflow.page import TaskFlowPage

    app = ctx.app
    root = Path(tempfile.mkdtemp(prefix="flow_validate_store_"))
    try:
        store = TaskStore(root)
        tid = store.create_task(ctx.pdf, "hash-validate", "校验样本")
        saved: list[str] = []
        page = TaskFlowPage(store)
        page.flow_saved.connect(saved.append)
        page.show()
        app.processEvents()
        try:
            ok("流程编辑页能打开任务", page.open_task(tid))

            # 把不合法的图写进任务，再走「保存流程」
            store.save_task_diagram(tid, _chain("print", "rembg"))
            page.open_task(tid)
            app.processEvents()
            flow_path = store.task_dir(tid) / "flow.bpmn"
            on_disk = flow_path.read_bytes()
            page._on_done(True)
            app.processEvents()
            ok("二级页保存不合法流程被拒绝（文件没被覆盖）",
               flow_path.read_bytes() == on_disk)
            ok("二级页保存被拒绝时不发 flow_saved（不切回详情页）",
               saved == [], str(saved))

            page.open_task(tid)
            app.processEvents()
            assert page._panel is not None
            page._panel.editor_panel._canvas.set_diagram(
                _chain("detect", "rembg", "print"))
            page._on_done(True)
            app.processEvents()
            ok("二级页保存合法流程正常落盘并发出 flow_saved",
               saved == [tid] and store.task_diagram(tid).stage_order()
               == ("detect", "rembg", "print"),
               f"saved={saved} order={store.task_diagram(tid).stage_order()}")

            # ---- 聚合任务：起始节点打头的保存闸（用户 2026-11-18）----
            member = store.create_task(ctx.pdf, "agg-member", "成员任务")
            agg = store.create_aggregate_task(
                [member], member_stage="imposition")
            try:
                ok("流程编辑页能打开聚合任务", page.open_task(agg))
                assert page._aggregate_panel is not None
                agg_flow = store.task_dir(agg) / "flow.bpmn"
                on_disk = agg_flow.read_bytes()

                # 反例：把「检测」挪到起始节点（拼版）前面——保存必须被拒
                page._aggregate_panel._editor_panel._canvas.set_diagram(
                    _chain("detect", "rembg", "imposition", "print"))
                app.processEvents()
                page._on_done(True)
                app.processEvents()
                ok("聚合流程不以起始节点打头 ⇒ 二级页拒绝保存（文件没动）",
                   agg_flow.read_bytes() == on_disk,
                   "flow.bpmn 被覆盖了")
                ok("聚合流程被拒时不发 flow_saved（不切回详情页）",
                   saved == [tid], str(saved))

                # 换回以起始节点打头的图：放行落盘
                page._aggregate_panel._editor_panel._canvas.set_diagram(
                    _chain("imposition", "print"))
                app.processEvents()
                page._on_done(True)
                app.processEvents()
                ok("聚合流程以拼版打头 ⇒ 正常落盘并发出 flow_saved",
                   saved == [tid, agg]
                   and store.task_diagram(agg).stage_order()
                   == ("imposition", "print"),
                   f"saved={saved} order={store.task_diagram(agg).stage_order()}")
            finally:
                store.delete_task(agg)
                store.delete_task(member)
        finally:
            page.close()
            app.processEvents()
            store.delete_task(tid)
    finally:
        shutil.rmtree(root, ignore_errors=True)
