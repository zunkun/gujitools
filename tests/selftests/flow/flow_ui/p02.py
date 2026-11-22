# -*- coding: utf-8 -*-
"""6"""

from typing import Any


def run(st: Any) -> None:
    from desktop.components.create_task_dialog import CreateTaskDialog
    from desktop.components.flow_dialog import FlowDialog, FlowPanel
    from desktop.steps.bpmn_diagram import (
        KIND_END, KIND_EXCLUSIVE, KIND_START, KIND_TASK, DiagramFlow,
        DiagramNode, DiagramNote, FlowDiagram,
    )
    from PySide6.QtWidgets import QWidget
    from desktop.components import create_task_dialog
    from desktop.steps.scheduler import (
        DONE, SKIPPED, Scheduler, default_template_path, load_default_diagram,
    )
    from tests.selftests._context import ok
    from PySide6.QtWidgets import QWidget

    from desktop.components.create_task_dialog import CreateTaskDialog

    host = QWidget()
    shells = {}
    try:
        try:
            shells["创建任务"] = CreateTaskDialog(host)
            shells["查看/编辑流程"] = FlowDialog(st.init, host)
        except Exception as exc:  # noqa: BLE001 - 这就是被钉的故障
            ok("两个弹窗外壳都能构造（parent 非 None）", False,
               f"{type(exc).__name__}: {exc}")
        else:
            ok("两个弹窗外壳都能构造（parent 非 None）", True)
        for name, shell in shells.items():
            ok(f"「{name}」外壳是真 QDialog", shell.dialog.__class__.__name__ == "QDialog",
               shell.dialog.__class__.__name__)
        # 面板点关闭要能**关掉弹窗**（面板自己没窗口）
        shell = shells.get("查看/编辑流程")
        if shell is not None:
            shell.dialog.show()
            st.app.processEvents()
            shell.panel._close()
            st.app.processEvents()
            ok("面板点关闭能关掉弹窗（关的是所属窗口）",
               not shell.dialog.isVisible())
        # 创建任务面板：**编辑器恒在**（用户 2026-11-17：默认直接展示流程编辑
        # 功能，不再点「编辑流程」触发；复选框同日已撤）
        panel = create_task_dialog.CreateTaskPanel()
        panel.show()
        st.app.processEvents()
        try:
            ok("初始未编辑（uses_custom_flow 为 False）",
               not panel.uses_custom_flow())
            ok("面板里**没有**「使用自定义任务流程」复选框（用户 2026-11-17 撤）",
               not hasattr(panel, "custom_check"))
            ok("面板里**没有**「编辑流程」按钮（编辑器默认就在，无需触发）",
               not hasattr(panel, "edit_button"))
            # ⚠️ 这组断言就是用户反馈的那条："无论是否编辑，都要告诉用户当前
            #    流程长什么样"——现在承担者从只读预览换成了常驻编辑器。
            default_names = [n.name for n in load_default_diagram().nodes]
            ok("编辑器**默认就在页面上**且显示默认流程（不是空白/隐藏）",
               panel.editor_panel is not None
               and panel.editor_panel.editor() is not None
               and not panel._editor_host.isHidden()
               and [n.name for n in panel.editor_panel.diagram().nodes]
               == default_names,
               f"{[n.name for n in panel.editor_panel.diagram().nodes]}")
            ok("未编辑时提示写明用的是默认流程（「当前流程」标题行已删，"
               "由 mode_hint 承担告知）",
               "默认" in panel.mode_hint.text(), panel.mode_hint.text())
            ok("未编辑时不传图（走字节拷贝模板，保住 guji:port）",
               panel.result_diagram() is None)
            ok("有「恢复默认」入口（编辑器工具栏自带）",
               panel.reset_button is not None
               and "恢复默认" in panel.reset_button.text())
            ok("未编辑时也有选 PDF 的地方",
               panel.pick_button.isVisible() and panel.selected_pdf() is None)
            ok("摘要讲清了步数与顺序",
               "步" in panel.flow_summary.text(), panel.flow_summary.text())

            # ---- 直接在常驻编辑器里改图：改动**实时**算自定义 ----
            from desktop.steps.bpmn_diagram import KIND_END
            editor = panel.editor_panel.editor()
            end_id = next(n.id for n in editor.diagram().nodes
                          if n.kind == KIND_END)
            editor.add_node(name="随手加的步骤", connect_from=end_id)
            st.app.processEvents()
            ok("编辑器里加了节点 ⇒ 立刻标记已编辑（result_diagram 不是 None）",
               panel.uses_custom_flow()
               and panel.result_diagram() is not None
               and any(n.name == "随手加的步骤"
                       for n in panel.result_diagram().nodes))
            ok("编辑过后提示写明用的是自定义流程",
               "自定义" in panel.mode_hint.text(), panel.mode_hint.text())
            # ⚠️ 用户 2026-11-17：选文件行在说明行**上面**（两行对调）
            ok("选文件行在说明行上面（用户要求两行对调）",
               panel.layout().indexOf(panel._pdf_row)
               < panel.layout().indexOf(panel.mode_hint))
            # ⚠️ 用户 2026-11-17：先选了文件、再把「上传文件/提取图片」删掉
            #    ⇒ 这个文件就没有意义了，整行隐藏
            panel.set_pdf(st.ctx.pdf)
            st.app.processEvents()
            from desktop.steps.bpmn_diagram import KIND_START
            editor2 = panel.editor_panel.editor()
            start_id = next(n.id for n in editor2.diagram().nodes
                            if n.kind == KIND_START)
            editor2.set_selected(start_id)
            editor2.remove_selected()      # 成对删除：提取图片跟着没
            st.app.processEvents()
            ok("删「上传文件/提取图片」⇒ 选源文件整行隐藏（文件没意义了）",
               panel._pdf_row.isHidden())
            ok("成对删除没把整条流程删光（后面还有可跑的步骤）",
               panel.result_diagram() is not None
               and panel.result_diagram().stage_order())
            # ⚠️ PDF **非必需**（用户 2026-10-06：「PDF 输入不是必须的」
            #    ＋「创建任务按钮不必等上传 pdf 才可以点」）——这两条是钉子，
            #    别哪天又给改回"没选文件就灰着"。
            ok("未选 PDF 时**照样**能提交（PDF 非必需）",
               panel.can_submit())
            ok("未选 PDF 时「创建任务」按钮是可点的（不是灰的）",
               panel.confirm_button.isEnabled()
               and not panel.confirm_button.isHidden())
            # 恢复默认流程（点编辑器工具栏那颗）：标记跟着清，图换回默认
            panel.reset_button.click()
            st.app.processEvents()
            ok("恢复默认流程后不传图（回到字节拷贝语义）、编辑器换回默认流程、"
               "选文件行跟着回来",
               panel.result_diagram() is None
               and not panel.uses_custom_flow()
               and not panel._pdf_row.isHidden()
               and [n.name for n in panel.editor_panel.diagram().nodes]
               == default_names)
        finally:
            panel.close()
            st.app.processEvents()
    finally:
        for shell in shells.values():
            shell.dialog.deleteLater()
        host.deleteLater()
        st.app.processEvents()

