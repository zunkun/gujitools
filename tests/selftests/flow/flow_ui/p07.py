# -*- coding: utf-8 -*-
"""第 12 章：创建页重置 / 清空文件 / 首次进入提示。"""

from __future__ import annotations

from pathlib import Path
import tempfile
import shutil


def run(st) -> None:
    _check_create_page_reset(st.ctx_page, st.ctx.pdf)
    _check_open_create_resets()
    _check_first_entry_shows_prompt(st.app)
    _check_clear_pdf(st.ctx_page, st.ctx.pdf)


def _check_create_page_reset(create_page, sample_pdf) -> None:
    """进创建页时上一次的输入**全部**清掉。

    ⚠️ 这是真事故：创建页是**惰性单例**（建一次长期留着），``open_create``
    原来不复位，于是第二次建任务时，界面上还摆着上一次的任务名、已选的 PDF、
    勾着的「自定义流程」、编过的流程图。
    """
    from desktop.components import create_task_dialog
    from desktop.components.create_task_dialog import EMPTY_PDF_HINT
    from tests.selftests._context import ok

    # 先把页面弄成"上一次用过的样子"
    create_page.set_name("上一次的书")
    create_page.panel.set_pdf(sample_pdf)
    create_page._autofill_name()
    create_page.set_busy(True, "建任务中…")
    ok("先摆出「上一次用过的样子」（编辑器恒在 + busy）",
       create_page.panel.editor_panel is not None
       and not create_page.panel._editor_host.isHidden()
       and create_page._busy is True
       and not create_page.name_edit.isEnabled())

    create_page.reset()
    ok("复位后任务名清空（用户截图里留着的正是它）",
       create_page.name_edit.text() == "", repr(create_page.name_edit.text()))
    ok("复位后已选 PDF 清空",
       create_page.panel.selected_pdf() is None,
       repr(create_page.panel.selected_pdf()))
    ok("复位后 PDF 那行回到「可留空」（不是留着一句假的已选）",
       create_page.panel.pdf_state.text() == EMPTY_PDF_HINT,
       create_page.panel.pdf_state.text())
    ok("复位后回到默认流程（编辑标记被清）",
       create_page.panel.uses_custom_flow() is False)
    ok("复位后编辑器仍在页面上（常驻，不收起）",
       not create_page.panel._editor_host.isHidden()
       and create_page.panel.editor_panel.editor() is not None)
    ok("复位后编辑器内容回到初值（不是带着上一本书的图）",
       [n.name for n in create_page.panel.editor_panel.diagram().nodes]
       == [n.name for n in
           create_task_dialog.load_custom_init().nodes])
    ok("复位后 flow_summary 还在（摘要随编辑实时刷新）",
       not create_page.panel.flow_summary.isHidden())
    ok("复位后 busy 态与控件禁用一起清（否则这页永久半残）",
       create_page._busy is False
       and create_page.name_edit.isEnabled()
       and create_page.panel.isEnabled()
       and create_page.back_button.isEnabled())
    ok("复位后提示回到初始说明",
       "留空" in create_page.name_hint.text(), create_page.name_hint.text())
    #⚠️ 默认名占位要**重算**：刚才那次创建已经占掉一个号
    ok("复位后默认名占位是当前预测的下一个任务号",
       create_page.name_edit.placeholderText() == create_page.default_name()
       and create_page.name_edit.placeholderText().startswith("任务#"),
       create_page.name_edit.placeholderText())

    # ---- 2026-10-07 事故回归钉：编辑器复用会抱着上一次编的图 ----
    # 现象：编过一次自定义流程 → 建任务 → 再进创建页，编辑器里看到的还是
    # 上一本书的图，不是当前的初值。根因是编辑器面板被缓存复用（它又是原地
    # 改图的）。现在：复位**重建**编辑器，每次都从默认模板起步。
    editor = create_page.panel.editor_panel.editor()
    assert editor is not None  # 常驻编辑器必然已建
    # ⚠️ 2026-11-04 起孤立节点会被保存校验拒绝，必须挂到图上；
    #    挂在结束事件后面（它本来没有输出），不破坏既有步骤的连线。
    from desktop.steps.bpmn_diagram import KIND_END
    end_id = next(n.id for n in editor.diagram().nodes if n.kind == KIND_END)
    editor.add_node(name="上一本书才有的步骤", connect_from=end_id)
    # 信号是同线程直连：diagram_changed（⇒「已编辑」标记）同步到达，无需 flush
    ok("先摆出事故现场：编辑器里加过节点（实时生效，无需保存）",
       any(n.name == "上一本书才有的步骤"
           for n in create_page.panel._custom_diagram.nodes)
       and create_page.panel.uses_custom_flow())
    create_page.panel.reset()                  # 建完任务再进来（open_create 会调）
    editor_again = create_page.panel.editor_panel.editor()
    assert editor_again is not None  # 复位重建后编辑器必然已建
    ok("编过流程并复位后，编辑器显示的是当前初值（不是上一次编的图）",
       all(n.name != "上一本书才有的步骤"
           for n in editor_again.diagram().nodes),
       str([n.name for n in editor_again.diagram().nodes]))
    ok("复位后回到未编辑态（不把上一本书的图落盘）",
       create_page.panel.result_diagram() is None)

def _check_open_create_resets() -> None:
    """钉住**调用点**：`open_create` 每次进入都复位（改回去要红）。

    ⚠️ 上一条验的是 :meth:`CreateTaskPage.reset` **本身**对不对；这条钉的是
    **壳层真的调了它**。少一步就会出现"复位方法写得挺好、但没人调用"——
    那种改动自测一片绿、用户照旧看见上一次的表单。
    """
    from desktop.pages.createtask.page import CreateTaskPage
    from desktop.shell import ModuleShell
    from desktop.store import TaskStore
    from tests.selftests._context import ok

    root = Path(tempfile.mkdtemp(prefix="open_create_probe_"))
    store = TaskStore(root / "data")
    shell = ModuleShell(store)
    try:
        shell.open_create()
        page = shell.create_page()
        assert isinstance(page, CreateTaskPage)  # 壳层惰性建的创建页
        page.set_name("上一次的书")
        page.panel.set_custom_mode(True)
        # 第二次进入（模拟建完一个任务后回来再建）
        shell.open_create()
        ok("open_create 每次进入都复位任务名（不是留着上一次的）",
           page.name_edit.text() == "", repr(page.name_edit.text()))
        ok("open_create 每次进入都复位流程编辑标记（回到默认流程）",
           page.panel.uses_custom_flow() is False)
        # 已经在这一页时再点一次「创建任务」也要清（复位在换页判断之前）
        page.set_name("又填了一次")
        shell.open_create()
        ok("已经在创建页时再点「创建任务」同样复位",
           page.name_edit.text() == "", repr(page.name_edit.text()))
    finally:
        shell.shutdown_workers()
        shell.close()
        shutil.rmtree(root, ignore_errors=True)

def _check_first_entry_shows_prompt(app) -> None:
    """**第一次**进入缺源任务就要弹出提示层（用户 2026-10-06 报障）。

    真实链路：``ModuleShell.open_detail`` 是**先** ``page.set_task()``、
    **后** ``pages.setCurrentWidget(page)``。所以 ``set_task`` 里弹提示层的那一刻，
    详情页刚被 ``addWidget`` 进栈、**还没布局**：尺寸是 QWidget 默认的 640x480、
    ``_content_top()`` 返回布局未跑时的垃圾值（实测 491）⇒ 遮罩高度被夹成
    **0**，用户看到的就是"压根没弹"，而第二次进入才正常（那时尺寸已对）。

    ⚠️⚠️ 这个 bug 自测之前一直抓不到，因为所有相关用例都是
    ``probe.show()`` 之后才 ``probe.set_task()``——页面早已布局好，**天然
    绕开了这个时序**。所以这里必须走**壳层的真实入口**，且**第一次**就断言。
    """
    import shutil as _shutil
    import tempfile as _tempfile

    from desktop.app import WINDOW_SIZE
    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.shell import ModuleShell
    from desktop.store import TaskStore
    from tests.selftests._context import ok

    root = Path(_tempfile.mkdtemp(prefix="first_entry_prompt_"))
    store = TaskStore(root / "data")
    empty_id = store.create_task(None, "", "")
    pdf = root / "with_source.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    full_id = store.create_task(pdf, "h", "")
    shell = ModuleShell(store)
    try:
        shell.resize(WINDOW_SIZE)
        shell.show()
        app.processEvents()
        # ⚠️ **必须等 resize/show 之后再取**：``shell.detail_page`` 是**惰性构造**
        #    的（第一次访问才建），提前取会在壳层还是默认 640×480 时把详情页
        #    建出来，页头卡片按错尺寸布局 ⇒ 遮罩上沿差几像素（本用例的
        #    "第一次 vs 再进来几何一致" 当场就挂）。取到之后是同一个对象，
        #    后面反复用没问题。
        _page = shell.detail_page
        assert isinstance(_page, TaskDetailPage)  # 壳层惰性建的详情页

        def prompt_state() -> tuple:
            prompt = _page._source_prompt
            if prompt is None:
                return (False, None)
            return (prompt.isVisible(), prompt.geometry().getRect())

        # ---- ① 第一次进入（此前**从未**进过这个任务）----
        shell.open_detail(empty_id)
        app.processEvents()
        visible, rect = prompt_state()
        page = _page
        ok("**第一次**进入缺源任务就弹出提示层（此前零次）",
           visible is True, f"visible={visible}")
        ok("第一次弹出的遮罩有**实际高度**（不是布局未就绪时的 0 高）",
           rect is not None and rect[3] > 100,
           f"rect={rect}")
        ok("第一次弹出的遮罩宽度铺满页面（不是默认 640）",
           rect is not None and rect[2] == page.width(),
           f"rect={rect} page={page.width()}")
        ok("第一次弹出的遮罩上沿在页头之下（页头按钮留可用）",
           rect is not None and 0 < rect[1] < page.height() // 3,
           f"rect={rect}")

        # ---- ② 切到有文件的任务：不弹 ----
        shell.open_detail(full_id)
        app.processEvents()
        visible_full, _ = prompt_state()
        ok("切到**有**源文件的任务：不弹提示层",
           visible_full is False, f"visible={visible_full}")

        # ---- ③ 再回到缺源任务：仍要弹，且几何依旧正确 ----
        shell.open_detail(empty_id)
        app.processEvents()
        visible_again, rect_again = prompt_state()
        ok("回到缺源任务：照样弹，且遮罩仍是正确几何",
           visible_again is True and rect_again == rect,
           f"visible={visible_again} rect={rect_again} vs {rect}")

        # ---- ④ 答「稍后再说」后切走再回来：每次进入都弹 ----
        _prompt_now = _page._source_prompt
        assert _prompt_now is not None  # ③ 回到缺源任务后提示层必然还在
        _prompt_now.dismiss()
        app.processEvents()
        shell.open_detail(full_id)
        app.processEvents()
        shell.open_detail(empty_id)
        app.processEvents()
        visible_third, rect_third = prompt_state()
        ok("答过「稍后再说」再切回来：**仍要弹**（每次进入都检测）",
           visible_third is True and rect_third[3] > 100,
           f"visible={visible_third} rect={rect_third}")

        # ---- ⑤ 窗口尺寸变了，遮罩要跟着重铺 ----
        prompt = _page._source_prompt
        assert prompt is not None  # 提示层仍在（上面刚验证过每次进入都弹）
        shell.resize(1200, 700)
        app.processEvents()
        ok("窗口拉小后遮罩跟着重铺（不是留在旧尺寸上）",
           prompt.geometry().width() == _page.width(),
           f"mask={prompt.geometry().getRect()} "
           f"page={_page.width()}")
    finally:
        shell.shutdown_workers()
        shell.close()
        _shutil.rmtree(root, ignore_errors=True)

def _check_clear_pdf(create_page, sample_pdf) -> None:
    """选错文件能一键清掉（不必重开选择框再点取消）。"""
    from desktop.components.create_task_dialog import EMPTY_PDF_HINT
    from tests.selftests._context import ok

    create_page.reset()
    button = create_page.panel.clear_pdf_button
    ok("创建页有「清除已选 PDF」的入口",
       button is not None and "PDF" in button.toolTip(),
       button.toolTip() if button is not None else "无按钮")
    assert button is not None  # 上一条 ok 已断言按钮存在
    ok("没选文件时清除按钮不出现（没东西可清）",
       button.isHidden(), f"visible={button.isVisible()}")

    # 选上 ⇒ 按钮出现，文案变成"已选择：xxx"
    create_page.panel.set_pdf(sample_pdf)
    create_page._autofill_name()
    app_ev = create_page.window()
    app_ev.repaint()
    ok("选了 PDF 后清除按钮出现",
       not button.isHidden(), f"visible={button.isVisible()}")
    ok("选了 PDF 后那行显示文件名",
       sample_pdf.name in create_page.panel.pdf_state.text(),
       create_page.panel.pdf_state.text())
    ok("选 PDF 自动填进任务名（清除时要从这里回退）",
       create_page.name_edit.text() == sample_pdf.stem,
       repr(create_page.name_edit.text()))

    # 点清除
    create_page.panel.clear_pdf_button.click()
    app_ev.repaint()
    ok("点「清除」⇒ 已选 PDF 真的没了",
       create_page.panel.selected_pdf() is None,
       repr(create_page.panel.selected_pdf()))
    ok("点「清除」⇒ 那行回到「可留空」",
       create_page.panel.pdf_state.text() == EMPTY_PDF_HINT,
       create_page.panel.pdf_state.text())
    ok("点「清除」⇒ 清除按钮自己消失",
       button.isHidden(), f"visible={button.isVisible()}")
    ok("点「清除」⇒ 自动填的文件名一起回退（不留指向已清文件的名字）",
       create_page.name_edit.text() == "",
       repr(create_page.name_edit.text()))

    # 用户**自己改过**的名字不能被清掉（那是丢用户输入）
    create_page.panel.set_pdf(sample_pdf)
    create_page.set_name("我自己起的名字")
    create_page.panel.clear_pdf_button.click()
    app_ev.repaint()
    ok("用户改过的任务名在清除 PDF 时**保留**（不丢用户输入）",
       create_page.name_edit.text() == "我自己起的名字",
       repr(create_page.name_edit.text()))
    ok("文件确实清掉了（只是名字留着）",
       create_page.panel.selected_pdf() is None)
