# -*- coding: utf-8 -*-
"""第 18 / 19 章：源PDF 成对删除 + 结束事件级联。"""

from __future__ import annotations

from pathlib import Path
import tempfile
import shutil

from ._helpers import _FLOW_DETECT_FIRST, _FLOW_PRINT_WITH_END, _FLOW_WITH_EXTRACT, _viewer_entry_button


def run(st) -> None:
    _check_source_pdf_pairing()
    _check_end_event_cascade()


def _check_source_pdf_pairing() -> None:
    """「上传 PDF」与「提取图片」成对；流程不吃 PDF 时**不摆PDF 图标**。

    用户 2026-10-06 两条一起提的：

    1. 不需要上传 pdf 的流程右侧不需 pdf 上传图标；
    2. 流程编辑中，如果删除了 上传pdf 或者 pdf图片提取中的一个，
       另外一个的存在没有意义，因此需要同步删除另外一个。

    钉五件事：①含 extract 时 PDF 按钮**照常显示**（别把补救入口一起藏了，
    空壳任务还要靠它补选）；②不含 extract 时**整颗藏起来**、插图按钮仍在；
    ③④正反两向删除都**成对**（删 extract→源PDF 也没了；删源PDF→extract
    也没了）；⑤**Delete 键那条路径同样成对**——它与工具栏「删除」是同一个
    动作的两条入口，只改一处，键盘删就会漏。
    """
    import shutil
    import tempfile

    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from desktop.components.bpmn_editor import BpmnEditor
    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.pages.taskflow.page import TaskFlowPage
    from desktop.shell import ModuleShell
    from desktop.store.store import TaskStore
    from desktop.ui import theme as theme
    from tests.selftests._context import ok, silence_source_prompt

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    tmp = Path(tempfile.mkdtemp(prefix="guji_pairing_"))
    orig_confirm = BpmnEditor._confirm_zh
    try:
        store = TaskStore(tmp / "data")
        shell = ModuleShell(store)
        shell.resize(1400, 900)
        shell.show()
        app.processEvents()
        page = shell.detail_page
        assert isinstance(page, TaskDetailPage)  # 壳层惰性建的详情页
        silence_source_prompt(page)

        with_pdf = store.create_task(source_path="", source_hash="",
                                     name="含提取")
        (store.task_dir(with_pdf) / "flow.bpmn").write_text(
            _FLOW_WITH_EXTRACT, encoding="utf-8")
        no_pdf = store.create_task(source_path="", source_hash="", name="无提取")
        (store.task_dir(no_pdf) / "flow.bpmn").write_text(
            _FLOW_DETECT_FIRST, encoding="utf-8")

        # ---- ① 含 extract ⇒ PDF 按钮照常显示 ----
        shell.open_detail(with_pdf)
        app.processEvents()
        ok("流程含「提取图片」⇒ PDF 上传图标**照常显示**（空壳任务要靠它补选）",
           not page.source_button.isHidden())
        # ---- ①b 输入按钮跟着**第一个节点**走（用户 2026-10-06 规则①）----
        # 「图片提取」打头 ⇒ 它的输入是源 PDF：页头只显示 PDF，图片/目录
        # 两个入口整对藏起来（摆着会让人以为这一步要喂图）。
        ok("「图片提取」打头 ⇒ 页头图片/目录入口**藏起来**（只显示 PDF，规则①）",
           page.insert_button.isHidden()
           and page.insert_dir_button.isHidden())
        ok("藏起来的入口红框仍在（常驻标识不随显隐丢）",
           str(theme.DANGER) in (page.insert_button.styleSheet() or ""))

        # ---- ② 不含 extract ⇒ PDF 按钮整颗藏起来 ----
        shell.open_detail(no_pdf)
        app.processEvents()
        ok("流程不含「提取图片」⇒ PDF 上传图标**藏起来**（用户 2026-10-06）",
           page.source_button.isHidden())
        ok("藏 PDF 图标不影响插图按钮（那才是这一步的输入入口）",
           not page.insert_button.isHidden())
        # ---- ②b 检测打头 ⇒ 图片 + 目录两个入口一起显示（规则②）----
        ok("「检测文本框」打头 ⇒ 页头只显示图片输入和文件输入（规则②）",
           not page.insert_dir_button.isHidden())
        ok("检测打头 ⇒ 检测页左下角「＋/📁」显示（入口要图片，规则③）",
           (_btn_img := _viewer_entry_button(
               page.detect_viewer, "插入图片（可多选）")) is not None
           and not _btn_img.isHidden()
           and (_btn_dir := _viewer_entry_button(
               page.detect_viewer, "把一个文件夹里的图片批量插入")) is not None
           and not _btn_dir.isHidden())

        # ---- ③④ 成对删除（正反两向）----
        # ⚠️ 确认框替成"是"：不替的话 ``ask_delete_selected`` 会挂住整个自测
        #    （离屏下真弹模态＝看门狗 os._exit(3)）。
        BpmnEditor._confirm_zh = lambda self, *a, **k: True  # type: ignore[reportAttributeAccessIssue]  # 测试替身：把确认框换成自动答「是」，离屏不许真弹模态

        def names_after_deleting(task_id: str, node_id: str) -> list[str]:
            """选中原生节点 → 走工具栏那条删除路径 → 剩下哪些节点名。"""
            from desktop.pages.taskflow.page import TaskFlowPage

            shell.open_detail(task_id)
            app.processEvents()
            shell.open_flow(task_id)
            app.processEvents()
            _flow_page = shell.flow_page()
            assert isinstance(_flow_page, TaskFlowPage)  # 壳层惰性建的流程页
            assert _flow_page._panel is not None  # 打开后面板必然已建
            editor = _flow_page._panel.editor_panel.editor()
            assert editor is not None  # 打开后编辑器必然已建
            editor.set_selected(node_id)
            editor.ask_delete_selected()
            app.processEvents()
            return sorted(n.name for n in editor.diagram().nodes)

        left = names_after_deleting(with_pdf, "ex")   # 删 extract
        ok("删「提取图片」⇒「源PDF」**跟着一起没了**（成对）",
           "源PDF" not in left, str(left))
        ok("  其余步骤**不受影响**（只删这一对）",
           "检测文本框" in left, str(left))

        left = names_after_deleting(with_pdf, "pdf")  # 删源 PDF
        ok("删「源PDF」⇒「提取图片」**跟着一起没了**（反向成对）",
           "提取图片" not in left, str(left))

        # ---- ⑤ Delete 键那条路径 ----
        shell.open_detail(with_pdf)
        app.processEvents()
        shell.open_flow(with_pdf)
        app.processEvents()
        _flow_page = shell.flow_page()
        assert isinstance(_flow_page, TaskFlowPage)  # 壳层惰性建的流程页
        assert _flow_page._panel is not None  # 打开后面板必然已建
        editor = _flow_page._panel.editor_panel.editor()
        assert editor is not None  # 打开后编辑器必然已建
        editor.set_selected("ex")
        editor.remove_selected()
        app.processEvents()
        left = sorted(n.name for n in editor.diagram().nodes)
        ok("Delete 键删除**同样成对**（它与工具栏是同一动作的两条入口）",
           "源PDF" not in left and "提取图片" not in left, str(left))

        shell.close()
    finally:
        BpmnEditor._confirm_zh = orig_confirm
        shutil.rmtree(tmp, ignore_errors=True)

def _check_end_event_cascade() -> None:
    """删「PDF排版」⇒ 附在后面的「生成PDF」结束事件**一定不存在**。

    用户 2026-10-07：

    > 流程图编辑中，生成PDF附在PDF排版，如果删除了PDF排版，
    > 那么生成PDF就一定不存在

    「生成PDF」是结束事件，不进拓扑序、没有运行语义——「PDF排版」删了
    它就一条入线不剩，留着就是句谎话。钉四件事：①工具栏删除路径联动；
    ②**Delete 键那条路径同样联动**（与成对删除同一纪律：它是同一个动作
    的两条入口）；③删上游（提取图片）**不**牵连结束事件——它的入线还在；
    ④确认框说明"会一起删除"（用户得知道删除面变大了）。

    判据本身（纯逻辑）由 ``step_ports`` 第 9b 节验。
    """
    import shutil
    import tempfile

    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from desktop.components.bpmn_editor import BpmnEditor
    from desktop.shell import ModuleShell
    from desktop.store.store import TaskStore
    from tests.selftests._context import ok, silence_source_prompt

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    tmp = Path(tempfile.mkdtemp(prefix="guji_end_event_"))
    orig_confirm = BpmnEditor._confirm_zh
    try:
        store = TaskStore(tmp / "data")
        shell = ModuleShell(store)
        shell.resize(1400, 900)
        shell.show()
        app.processEvents()
        silence_source_prompt(shell.detail_page)
        task_id = store.create_task(source_path="", source_hash="",
                                    name="带收尾")
        (store.task_dir(task_id) / "flow.bpmn").write_text(
            _FLOW_PRINT_WITH_END, encoding="utf-8")
        BpmnEditor._confirm_zh = lambda self, *a, **k: True  # type: ignore[reportAttributeAccessIssue]  # 测试替身：把确认框换成自动答「是」，离屏不许真弹模态

        def open_editor() -> BpmnEditor:
            from desktop.pages.taskflow.page import TaskFlowPage

            shell.open_detail(task_id)
            app.processEvents()
            shell.open_flow(task_id)
            app.processEvents()
            _flow_page = shell.flow_page()
            assert isinstance(_flow_page, TaskFlowPage)  # 壳层惰性建的流程页
            assert _flow_page._panel is not None  # 打开后面板必然已建
            editor = _flow_page._panel.editor_panel.editor()
            assert editor is not None  # 打开后编辑器必然已建
            return editor

        # ---- ① 工具栏删除路径：删「PDF排版」⇒「生成PDF」跟着没了 ----
        editor = open_editor()
        editor.set_selected("pr")
        editor.ask_delete_selected()
        app.processEvents()
        left = sorted(n.name for n in editor.diagram().nodes)
        ok("删「PDF排版」⇒「生成PDF」结束事件**跟着一起没了**",
           "生成PDF" not in left, str(left))
        ok("  上游步骤不受影响（只删这一支收尾）",
           "提取图片" in left and "源PDF" in left, str(left))

        # ---- ② Delete 键那条路径（重开一张新图）----
        (store.task_dir(task_id) / "flow.bpmn").write_text(
            _FLOW_PRINT_WITH_END, encoding="utf-8")
        editor = open_editor()
        editor.set_selected("pr")
        editor.remove_selected()
        app.processEvents()
        left = sorted(n.name for n in editor.diagram().nodes)
        ok("Delete 键删除**同样联动**（它与工具栏是同一动作的两条入口）",
           "生成PDF" not in left and "PDF排版" not in left, str(left))

        # ---- ③ 删上游不牵连：入线还剩「PDF排版」那条 ----
        (store.task_dir(task_id) / "flow.bpmn").write_text(
            _FLOW_PRINT_WITH_END, encoding="utf-8")
        editor = open_editor()
        editor.set_selected("ex")
        editor.remove_selected()
        app.processEvents()
        left = sorted(n.name for n in editor.diagram().nodes)
        ok("删「提取图片」⇒「生成PDF」**留在图上**（入线没断，别越界删）",
           "生成PDF" in left, str(left))

        # ---- ④ 确认框说明删除面变大了 ----
        (store.task_dir(task_id) / "flow.bpmn").write_text(
            _FLOW_PRINT_WITH_END, encoding="utf-8")
        editor = open_editor()
        seen: dict = {}

        def spy_confirm(self, title, text, **kwargs):
            seen["text"] = text
            return True

        BpmnEditor._confirm_zh = spy_confirm  # type: ignore[reportAttributeAccessIssue]  # 测试替身：换成记录确认框文案的探针，离屏不许真弹模态
        editor.set_selected("pr")
        editor.ask_delete_selected()
        app.processEvents()
        ok("确认框写明「生成PDF」会一起删除（用户得知道删除面变大）",
           "生成PDF" in seen.get("text", ""), str(seen.get("text", "")))

        shell.close()
    finally:
        BpmnEditor._confirm_zh = orig_confirm
        shutil.rmtree(tmp, ignore_errors=True)
