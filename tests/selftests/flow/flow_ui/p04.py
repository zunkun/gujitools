# -*- coding: utf-8 -*-
"""7 / 8 / 9 / 任务名输入框的外观（用户 2026-10-06：不好看/ 高度不够 / 太长） / 10 / 11 / 12 / 13 / 14 / 15 / 16 / 17 / 18 / 19"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any


def run(st: Any) -> None:
    from desktop.ui.widgets import CONTROL_HEIGHT
    from desktop.pages.createtask.page import CreateTaskPage
    from desktop.steps.bpmn_diagram import (
        KIND_END, KIND_EXCLUSIVE, KIND_START, KIND_TASK, DiagramFlow,
        DiagramNode, DiagramNote, FlowDiagram,
    )
    from pathlib import Path
    from desktop.shell import ROUTE_CREATE, ROUTE_FLOW
    from desktop.pages.taskflow.page import TaskFlowPage
    from desktop.store import TaskStore
    from desktop.steps.scheduler import (
        DONE, SKIPPED, Scheduler, default_template_path, load_default_diagram,
    )
    from tests.selftests._context import ok
    import shutil
    import tempfile
    from desktop.store import TaskStore

    root = Path(tempfile.mkdtemp(prefix="flow_store_"))
    try:
        store = TaskStore(root)
        pdf = root / "样例.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        tid = store.create_task(pdf, "h1", "自定义流程书", diagram=st.init)
        got = store.task_diagram(tid)
        ok("创建任务时把图落进 flow.bpmn（节点数一致）",
           len(got.nodes) == len(st.init.nodes),
           f"{len(got.nodes)} vs {len(st.init.nodes)}")
        ok("落盘后阶段顺序一致",
           got.stage_order() == st.init.stage_order(),
           f"{got.stage_order()} vs {st.init.stage_order()}")
        ok("落盘后网关/事件类型不丢（图形保真）",
           sorted(n.kind for n in got.nodes) == sorted(n.kind for n in st.init.nodes))

        # 改流程 → 落盘 → 立刻读得到（缓存必须失效）
        modified = FlowDiagram(
            nodes=tuple(n for n in got.nodes if n.stage != "print") + (
                DiagramNode("p2", KIND_TASK, "PDF排版", stage="print"),
            ),
            flows=got.flows, boxes=got.boxes, waypoints=got.waypoints,
        )
        store.save_task_diagram(tid, modified)
        ok("save_task_diagram 后 task_diagram 立刻读到新图（mtime 缓存已清）",
           store.task_diagram(tid).stage_order() == modified.stage_order(),
           str(store.task_diagram(tid).stage_order()))

        tid2 = store.create_task(pdf, "h2", "默认流程书")
        ok("下一个任务不受上一条自定义流程影响",
           store.task_diagram(tid2).stage_order() ==
           load_default_diagram().stage_order())
    finally:
        shutil.rmtree(root, ignore_errors=True)
    st.detail = st.ctx.d
    ok("详情页页头有「查看/编辑流程」入口",
       hasattr(st.detail, "flow_button") and "流程" in st.detail.flow_button.toolTip(),
       getattr(st.detail, "flow_button", None)
       and st.detail.flow_button.toolTip() or "")
    ok("详情页能读出本任务流程图（弹窗的数据源）",
       len(st.page.store.task_diagram(st.detail.task_id).nodes) > 0)
    ok("store.save_task_diagram 存在（改流程要能落盘）",
       callable(getattr(st.page.store, "save_task_diagram", None)))
    from desktop.pages.createtask.page import CreateTaskPage
    from desktop.pages.taskflow.page import TaskFlowPage
    from desktop.shell import ROUTE_CREATE, ROUTE_FLOW

    st.ctx_page = CreateTaskPage(st.page.store)
    st.ctx_page.show()
    st.app.processEvents()
    ok("壳层为这两个页面备了路由键（导航/反查靠它）",
       bool(ROUTE_CREATE) and bool(ROUTE_FLOW) and ROUTE_CREATE != ROUTE_FLOW)
    ok("创建任务是**页面**（不是弹窗）且有任务名输入框",
       hasattr(st.ctx_page, "name_edit") and hasattr(st.ctx_page, "back_button"))
    from desktop.ui.widgets import CONTROL_HEIGHT
    ok("任务名输入框高度与项目表单控件一致（不再是矮一截的原生框）",
       st.ctx_page.name_edit.height() == CONTROL_HEIGHT
       or st.ctx_page.name_edit.minimumHeight() == CONTROL_HEIGHT,
       f"h={st.ctx_page.name_edit.height()} "
       f"min={st.ctx_page.name_edit.minimumHeight()} "
       f"want={CONTROL_HEIGHT}")
    ok("任务名输入框**不占满整行**（有宽度上限 + 右侧留白）",
       st.ctx_page.name_edit.maximumWidth() > 0
       and st.ctx_page.name_edit.maximumWidth() <= 400,
       f"maxW={st.ctx_page.name_edit.maximumWidth()}")
    # 默认名「任务#XXXX」：占位提示（用户第 4 条）
    default_hint_text = st.ctx_page.name_edit.placeholderText()
    ok("默认任务名是「任务#XXXX」形式（序号=任务号，四位补零）",
       default_hint_text.startswith("任务#")
       and len(default_hint_text) == 7
       and default_hint_text[3:].isdigit(),
       default_hint_text)
    # 选 PDF → 自动填文件名（留空时的默认，用户第 5 条）
    st.ctx_page.panel.set_pdf(st.ctx.pdf)
    st.ctx_page._autofill_name()
    st.app.processEvents()
    ok("选了 PDF 自动把文件名填进任务名（可再改）",
       st.ctx_page.name_edit.text() == st.ctx.pdf.stem,
       repr(st.ctx_page.name_edit.text()))
    st.ctx_page.set_name("自定名")
    ok("任务名可改", st.ctx_page.task_name() == "自定名")
    ok("留空时提示说清会用哪个文件名",
       "留空" in st.ctx_page.name_hint.text()
       or "任务名将使用" in st.ctx_page.name_hint.text(),
       st.ctx_page.name_hint.text())
    # 选完再清空 → 提示改口成「默认名」（没 PDF 时的那一套，用户第 4 条）
    st.ctx_page.name_edit.clear()
    st.ctx_page._refresh_hint()
    ok("清空名字（有 PDF）后提示改说用文件名",
       st.ctx.pdf.stem in st.ctx_page.name_hint.text(),
       st.ctx_page.name_hint.text())
    _panel_layout = st.ctx_page.panel.layout()
    # ⚠️ 创建页外层是 QScrollArea（用户 2026-11-18：整页纵向滚动），页面的
    #    边距在**滚动内容**那一层的布局上——量 page.layout() 会拿到 0。
    _page_layout = st.ctx_page.content.layout()
    assert _panel_layout is not None and _page_layout is not None  # 布局必然已建
    ok("面板在页面内不带第二层边距（「创建任务」与「任务名称」左对齐）",
       _panel_layout.contentsMargins().left() == 0
       and _page_layout.contentsMargins().left() > 0,
       f"panel={_panel_layout.contentsMargins().left()} "
       f"page={_page_layout.contentsMargins().left()}")
    # 流程编辑器**默认就在本页上**（用户 2026-11-17：不再点「编辑流程」触发）
    ok("创建页默认就带着流程编辑器（BpmnEditorPanel 恒在）",
       st.ctx_page.panel.editor_panel is not None
       and st.ctx_page.panel.editor_panel.editor() is not None
       and not st.ctx_page.panel._editor_host.isHidden())
    ok("编辑器显示的是默认模板那张图（还没编辑过）",
       [n.name for n in st.ctx_page.panel.editor_panel.diagram().nodes]
       == [n.name for n in load_default_diagram().nodes])
    ok("底部「取消/创建任务」恒在（编辑器常驻后没有两态切换）",
       not st.ctx_page.panel._button_bar.isHidden()
       and not hasattr(st.ctx_page.panel, "edit_button"))
    # 删「上传文件/提取图片」⇒ 选了的文件**不进任务**（用户 2026-11-17：
    # 文件没意义了——行已隐藏，提交时也不能对一个看不见的文件弹查重）
    from desktop.steps.bpmn_diagram import KIND_START
    st.ctx_page.panel.set_pdf(st.ctx.pdf)
    _ed = st.ctx_page.panel.editor_panel.editor()
    _start = next(n.id for n in _ed.diagram().nodes if n.kind == KIND_START)
    _ed.set_selected(_start)
    _ed.remove_selected()
    _fired = []
    _collector = lambda *a: _fired.append(a)  # noqa: E731 - 收集器
    st.ctx_page.create_requested.connect(_collector)
    st.ctx_page._emit_create()
    ok("流程不吃源文件 ⇒ 选了的文件不传给建任务（不查重、不拷贝）",
       len(_fired) == 1 and _fired[0][0] == ""
       and st.ctx_page.panel._pdf_row.isHidden(),
       f"fired={_fired}")
    st.ctx_page.create_requested.disconnect(_collector)
    # ⚠️ 还原成默认流程：后面的 10~12 节还要在这页上验"默认流程要 PDF"等判据。
    # ⚠️ 文件要**重新选上**：section 10 的 `_submit_keeps_window` 会真走
    #    `_on_submit`——没文件 + 默认流程要 PDF ⇒ 真弹「缺源 PDF」MessageBox，
    #    离屏没人点它就是挂死（看门狗 600s 强杀的那次正是这么来的）。
    st.ctx_page.panel.reset()
    st.ctx_page.panel.set_pdf(st.ctx.pdf)
    st.app.processEvents()

    # 详情页「查看/编辑流程」→ 流程编辑**页面**
    ok("详情页发的是 flow_edit_requested（宿主切页，不再自己弹窗）",
       hasattr(st.detail, "flow_edit_requested"))
    flow_page = TaskFlowPage(st.page.store)
    flow_page.show()
    st.app.processEvents()
    ok("流程编辑页能打开本任务流程", flow_page.open_task(st.detail.task_id))
    ok("流程页标题带任务名（知道自己改的是哪条）",
       st.detail.task_id in flow_page.title.text()
       or st.page.store.get_task(st.detail.task_id)["name"] in flow_page.title.text(),
       flow_page.title.text())
    ok("流程页的编辑器不会去关整页（close_window=False）",
       flow_page._panel is not None
       and flow_page._panel._close_window_on_end is False)
    assert flow_page._panel is not None  # 上一条 ok 已断言面板已建
    # 保存 → 落盘
    before = len(st.page.store.task_diagram(st.detail.task_id).nodes)
    flow_page._panel.accept()
    st.app.processEvents()
    ok("流程页「保存流程」把图落回 flow.bpmn",
       len(st.page.store.task_diagram(st.detail.task_id).nodes) == before)
    flow_page.close()
    st.ctx_page.close()

    # 任务改名：非必需、可随时改
    st.store_ = st.page.store
    tid_ = st.detail.task_id
    old_name = st.store_.get_task(tid_)["name"]
    ok("store.rename_task 存在（任务名可随时修改）",
       callable(getattr(st.store_, "rename_task", None)))
    ok("改名生效", st.store_.rename_task(tid_, "改过的名字")
       and st.store_.get_task(tid_)["name"] == "改过的名字",
       st.store_.get_task(tid_)["name"])
    ok("改回原名（名字没变时返回 False，不做无谓写盘）",
       st.store_.rename_task(tid_, old_name)
       and st.store_.rename_task(tid_, old_name) is False,
       st.store_.get_task(tid_)["name"])
    # ⚠️ 先改成别的名字再清空：清空回落的就是文件名，若当前名**本来就是**
    #    文件名，rename_task 会正确地返回 False（无变化），断言就假红了。
    st.store_.rename_task(tid_, "临时名")
    ok("清空名字回落到源文件名（不留空名字）",
       st.store_.rename_task(tid_, "   ")
       and st.store_.get_task(tid_)["name"] == st.ctx.pdf.stem,
       st.store_.get_task(tid_)["name"])
    ok("改不存在的任务返回 False（不抛）",
       st.store_.rename_task("9999", "x") is False)
    # 行内编辑的守卫方向（isHidden 而非 isVisible，且方向别反）
    ok("行内改名：点开输入框、标题让位",
       (st.detail._begin_rename() or True)
       and not st.detail.rename_edit.isHidden() and st.detail.detail_title.isHidden())
    st.detail.rename_edit.setText("行内改的名字")
    st.detail._commit_rename()
    st.app.processEvents()
    ok("行内改名落盘并刷新标题",
       st.store_.get_task(tid_)["name"] == "行内改的名字"
       and st.detail.detail_title.text() == "行内改的名字",
       st.detail.detail_title.text())
    st.store_.rename_task(tid_, old_name)
