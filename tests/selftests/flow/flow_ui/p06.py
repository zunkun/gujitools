# -*- coding: utf-8 -*-
"""第 11 章：缺源 PDF 提示 + 补选入口。"""

from __future__ import annotations


def run(st) -> None:
    _check_pdf_button_icon(st.detail)
    _check_missing_pdf_prompt(st.ctx_page, st.ctx.pdf)
    _check_source_pick_flow(st.store_, st.ctx.pdf, st.app)


def _check_pdf_button_icon(detail) -> None:
    from tests.selftests._context import ok

    """① 页头「选择 PDF」按钮用现成的 ``PDF_FILE`` 图标。"""
    button = detail.source_button
    # ⚠️ 光判"图标非空"没用（内置 ``FIF.DOCUMENT`` 也非空），要比**类型**：
    #   自绘那枚是 ``SvgIcon`` 实例，内置的是 ``FluentIcon`` 子类。
    ok("页头 PDF 按钮用的是现成的自绘 PDF_FILE（不是内置空白 DOCUMENT）",
       type(getattr(button, "_icon", None)).__name__ == "SvgIcon",
       type(getattr(button, "_icon", None)).__name__)

def _check_missing_pdf_prompt(create_page, sample_pdf) -> None:
    from tests.selftests._context import ok

    """② 流程要源 PDF、用户没给 ⇒ 提交前问一句（两条路都合法）。

    ⚠️ 离屏自测绝不真弹模态：这里只验**判据**（该问/不该问）与"用户答
    先不传 ⇒ 照常建空壳"这条分支；确认框本身归 ``MessageBox``。
    """
    from tests.selftests._context import ok

    ok("默认流程里有「提取图片」⇒ 需要源 PDF（该问用户）",
       create_page._flow_needs_source_pdf() is True)
    # 选上文件就不问了（别在用户已经给了文件时还啰嗦一句）
    create_page.panel.set_pdf(sample_pdf)
    ok("已选 PDF 时不啰嗦（不问了）",
       create_page._should_ask_missing_pdf() is False)
    # ⚠️ 第 9 节给这页选过 PDF，先清掉再验"没选"那条（顺序别弄反）
    create_page.panel._pdf = None
    ok("没选 PDF 且流程要 PDF ⇒ 该问",
       create_page._should_ask_missing_pdf() is True)
    # 用户答「先不传」⇒ 继续建（空壳），信号照发
    create_page._should_ask_missing_pdf = lambda: False
    fired = []
    create_page.create_requested.connect(lambda *a: fired.append(a))
    create_page._on_submit()
    app_process = create_page.window()
    app_process.repaint()
    ok("用户选「先不传」→ 照常建空壳任务（不拦着不让建）",
       len(fired) == 1 and fired[0][0] == "",
       f"fired={fired}")
    # 自定义流程里把「提取图片」删掉 ⇒ 不需要源 PDF ⇒ 不该问
    from desktop.steps.bpmn_diagram import (
        DiagramFlow, DiagramNode, FlowDiagram, KIND_TASK,
    )
    keep = [n for n in create_page.panel._default_diagram.nodes
            if n.name != "提取图片"]
    if len(keep) >= 2:
        # ⚠️ 2026-11-17 起编辑器常驻：喂图走 set_custom_diagram（整张交给
        #    编辑器重建），不再直接戳 _custom_diagram
        create_page.panel.set_custom_diagram(FlowDiagram(
            nodes=tuple(keep),
            flows=tuple(DiagramFlow(f"sf{i}", keep[i - 1].id, keep[i].id)
                        for i in range(1, len(keep))),
        ))
        ok("流程里没有要源 PDF 的步骤 ⇒ 不该问（不白问）",
           create_page._flow_needs_source_pdf() is False,
           f"stages={[n.name for n in keep]}")
    else:
        ok("流程里没有要源 PDF 的步骤 ⇒ 不该问（不白问）", True)

def _check_source_pick_flow(store, pdf, app) -> None:
    """③ 详情页补选 PDF：同 hash 不重复传 / 新 PDF 先确认再换。"""
    from tests.selftests._context import ok

    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.utils.files import file_hash

    real_hash = file_hash(pdf)
    other = pdf.with_name("另一本.pdf")
    other.write_bytes(pdf.read_bytes() + b"\n% another book\n")
    other_hash = file_hash(other)

    # ---- 同一个文件又选了一遍 ⇒ 什么都不做（不换源、不清数据）----
    tid = store.create_task(pdf, real_hash, "同文件测试")
    probe = TaskDetailPage(store)
    probe.resize(1080, 720)
    probe.show()
    try:
        app.processEvents()
        from tests.selftests._context import silence_source_prompt

        # 有源文件的任务不该弹；替身装上顺便钉住这条（漏弹/乱弹都红）
        prompt_calls = silence_source_prompt(probe)
        ok("能进详情页", probe.set_task(tid) is True)
        ok("**有**源文件的任务不弹「缺源 PDF」提示（提示层压根没建）",
           bool(prompt_calls) and probe._source_prompt is None,
           f"calls={len(prompt_calls)} "
           f"prompt={probe._source_prompt}")
        kept = store.get_task(tid)["source_path"]
        probe._pending_source = pdf
        probe._on_source_hash_ready(str(pdf), real_hash)
        app.processEvents()
        ok("重复选同一个 PDF ⇒ 不换源文件（哈希一样就不动）",
           store.get_task(tid)["source_path"] == kept,
           store.get_task(tid)["source_path"])

        # ---- 这个 PDF 已在别的任务里 ⇒ **问一句**，不是一律拒绝 ----
        # （用户 2026-10-06："当前是不允许的，这个不合理。应该提示已经存在
        #   相同文件任务，是否继续等，跟外层一样"）
        tid_other = store.create_task(pdf, real_hash, "已导入过的书")
        probe2 = TaskDetailPage(store)
        probe2.resize(1080, 720)
        probe2.show()
        app.processEvents()
        silence_source_prompt(probe2)
        probe2.set_task(tid_other)
        before = store.get_task(tid_other)["source_path"]
        ok("重复内容的任务要问一句（判据：存在别的任务就问）",
           probe2._duplicate_source_needs_confirm(
               store.get_task(tid)) is True)
        ok("本任务自己那条不问（已在指纹分支里提前处理掉）",
           probe2._duplicate_source_needs_confirm(
               store.get_task(tid_other)) is False)
        # 答「取消」⇒ 什么都不做
        probe2._confirm_duplicate_source = lambda source, other: False
        probe2._pending_source = pdf
        probe2._on_source_hash_ready(str(pdf), real_hash)
        app.processEvents()
        ok("重复内容但用户答「取消」⇒ 不换源（不复制、不清产物）",
           store.get_task(tid_other)["source_path"] == before,
           store.get_task(tid_other)["source_path"])
        # 答「仍然使用」⇒ 换源（与外层查重确认同一个模式）
        probe2._confirm_duplicate_source = lambda source, other: True
        probe2._pending_source = pdf
        probe2._on_source_hash_ready(str(pdf), real_hash)
        app.processEvents()
        ok("重复内容但用户答「仍然使用」⇒ 照样换源（不是一刀切拒绝）",
           store.get_task(tid_other)["source_path"] == str(pdf),
           store.get_task(tid_other)["source_path"])
        ok("确认使用后指纹写进索引（下次仍能判重）",
           store.get_task(tid_other)["source_hash"] == real_hash)
        probe2.shutdown_all_workers()
        probe2.close()

        # ---- 新的 PDF：先确认、换了之后指纹写进索引、后续节点数据清空 ----
        (store.task_dir(tid) / "pages.json").write_text("[]", encoding="utf-8")
        # 挡住确认框（离屏不许真弹）：用户答"不换"
        probe._confirm_replace_source = lambda source: False
        probe._pending_source = other
        probe._on_source_hash_ready(str(other), other_hash)
        app.processEvents()
        ok("新 PDF 但用户答「不换」⇒ 源文件保持不变（确认在前）",
           store.get_task(tid)["source_path"] != str(other),
           store.get_task(tid)["source_path"])
        ok("用户答「不换」⇒ 旧书的中间产物也还在（没白清）",
           (store.task_dir(tid) / "pages.json").exists())
        # 用户答"换"
        probe._confirm_replace_source = lambda source: True
        probe._pending_source = other
        probe._on_source_hash_ready(str(other), other_hash)
        app.processEvents()
        ok("用户答「换」⇒ 源文件换成新的那份",
           store.get_task(tid)["source_path"] == str(other),
           store.get_task(tid)["source_path"])
        ok("换了之后**指纹写进索引**（否则下次判重失效）",
           store.get_task(tid)["source_hash"] == other_hash,
           store.get_task(tid)["source_hash"])
        ok("换了之后后续节点数据全部清空（页清单…）",
           not (store.task_dir(tid) / "pages.json").exists())
        ok("换了之后副本落进任务目录（详情页读的是副本）",
           store.source_copy_path(tid) is not None)
        # 算指纹期间按钮是锁着的（免得用户以为没点上）
        probe._set_picking_source(True)
        ok("算指纹期间锁住按钮、提示改成「正在读取」",
           not probe.source_button.isEnabled()
           and "读取" in probe.source_button.toolTip(),
           probe.source_button.toolTip())
        probe._set_picking_source(False)
        ok("算完恢复按钮可用与原提示",
           probe.source_button.isEnabled()
           and "更换" in probe.source_button.toolTip(),
           probe.source_button.toolTip())
    finally:
        probe.shutdown_all_workers()
        probe.close()
        app.processEvents()
        for extra in (tid, tid_other):
            try:
                store.delete_task(extra)
            except OSError:
                pass
        if other.exists():
            other.unlink()
