# -*- coding: utf-8 -*-
"""**流程合法性校验**（``desktop/steps/validate.py``）自测。

对应 ``docs/tasks/bpm测试.md``：BPM 可以任意组合，但并非所有组合都合法；
**不合法的流程在创建或编辑保存时就判出来、拒绝保存**。

本模块钉死四件事：

1. **文档里的 10 条合法组合全部放行**——包括"没有提取"的入口流程
   （detect/rembg/imposition 任意顺序任意个数）、单步流程（只留一个
   PDF排版）；
2. **反例全部拒绝**——``print → rembg``（用户给的原例）、拼版排在
   PDF排版 之后、只摆起止事件没有可执行步骤的空流程；
3. **警告只提示不拦**——缺判断节点、extract 不在第一位、同一阶段
   多个节点、未接入运行的节点，``ok`` 仍为真；
4. **保存入口真的拦**——``FlowPanel.accept``（弹窗/创建页内嵌编辑器）
   与 ``TaskFlowPage._on_done``（流程编辑二级页）对不合法的图都
   **不落盘、不切页**。

纯逻辑部分不建窗口；第 4 条建离屏控件（不弹模态）。
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from typing import TYPE_CHECKING

from desktop.steps import ports

if TYPE_CHECKING:
    # _chain 里是函数内延迟导入（保持自测启动轻），但返回注解引它 —— 类型侧声明。
    from desktop.steps.bpmn_diagram import FlowDiagram

NAME = "flow_validate"
DEPENDS: list[str] = ["flow_bpm"]
TITLE = "BPM 流程合法性校验（保存时拒绝不合法流程）"


def _chain(*stages: str, gateway: bool = False, source: bool = True,
           end: bool = True) -> "FlowDiagram":
    """按阶段 key 串一条链（带可选的源PDF事件 / 网关 / 结束事件）。

    ⚠️ 节点带显式 ``stage``：:func:`stage_of_name` 只在 ``load`` 解析时调用，
    手造节点必须自己接上阶段，否则 ``stage_order()`` 是空的、断言假红。
    """
    from desktop.steps.bpmn_diagram import (
        KIND_END, KIND_EXCLUSIVE, KIND_START, KIND_TASK,
        DiagramFlow, DiagramNode, FlowDiagram,
    )

    nodes: list[DiagramNode] = []
    flows: list[DiagramFlow] = []
    if source:
        nodes.append(DiagramNode("src", KIND_START, "源PDF"))
    previous = "src" if source else None
    for index, stage in enumerate(stages):
        node_id = f"n{index}"
        nodes.append(DiagramNode(node_id, KIND_TASK, ports.stage_label(stage),
                                 stage=stage))
        if previous is not None:
            flows.append(DiagramFlow(f"f{len(flows)}", previous, node_id))
        previous = node_id
        if gateway and stage == "rembg":
            nodes.append(DiagramNode("gw", KIND_EXCLUSIVE, "是否拼版"))
            flows.append(DiagramFlow(f"f{len(flows)}", node_id, "gw"))
            previous = "gw"
    if end and previous is not None:
        nodes.append(DiagramNode("end", KIND_END, "完成"))
        flows.append(DiagramFlow(f"f{len(flows)}", previous, "end"))
    return FlowDiagram(nodes=tuple(nodes), flows=tuple(flows))


def run(ctx) -> None:
    from tests.selftests._context import ok

    _check_legal_combos(ok)
    _check_illegal_combos(ok)
    _check_warnings(ok)
    _check_templates_clean(ok)
    _check_data_chain(ctx, ok)
    _check_panel_gate(ctx, ok)
    _check_flow_page_gate(ctx, ok)


# ------------------------------------------------------- ① 文档的合法组合
def _check_legal_combos(ok) -> None:
    """``docs/tasks/bpm测试.md`` 的 10 条组合（映射到运行阶段）必须全部放行。"""
    from desktop.steps.validate import validate_flow

    legal = [
        # 1. upload → extract → detect → rembg →(imposition) → print
        ("extract", "detect", "rembg", "imposition", "print"),
        # 2. detect → rembg →(imposition) → print
        ("detect", "rembg", "imposition", "print"),
        # 3. rembg →(imposition) → print
        ("rembg", "imposition", "print"),
        # 4. imposition → print
        ("imposition", "print"),
        # 5. print
        ("print",),
        # 6. extract
        ("extract",),
        # 7. detect
        ("detect",),
        # 8. rembg
        ("rembg",),
        # 9. imposition
        ("imposition",),
        # 10. detect/rembg/imposition 任意顺序任意个数（+print 收尾）
        ("rembg", "detect", "print"),
        ("detect", "print"),
        ("imposition", "detect", "rembg"),
        ("detect", "rembg"),
    ]
    for stages in legal:
        result = validate_flow(_chain(*stages))
        ok(f"合法组合 {' → '.join(stages)} 放行",
           result.ok, f"errors={result.errors}")

    # 带「提交去底色结果」显式节点的图同样合法（它与 rembg 同格折叠）
    from desktop.steps.bpmn_diagram import (
        KIND_TASK, DiagramFlow, DiagramNode, FlowDiagram, stage_of_name,
    )

    diagram = FlowDiagram(
        nodes=(DiagramNode("a", KIND_TASK, "图片去底色",
                           stage=stage_of_name("图片去底色")),
               DiagramNode("b", KIND_TASK, "提交去底色结果",
                           stage=stage_of_name("提交去底色结果")),
               DiagramNode("c", KIND_TASK, "PDF排版",
                           stage=stage_of_name("PDF排版"))),
        flows=(DiagramFlow("f1", "a", "b"), DiagramFlow("f2", "b", "c")),
    )
    result = validate_flow(diagram)
    ok("「去底色+提交」同格两个动作的图合法（不误判重复）",
       result.ok and not result.warnings,
       f"errors={result.errors} warnings={result.warnings}")


# --------------------------------------------------------------- ② 反例
def _check_illegal_combos(ok) -> None:
    """反例必须给出硬错误（保存时拒绝）。"""
    from desktop.steps.validate import validate_flow

    illegal = [
        # 用户原例：PDF排版 后面还有去底色
        ("print", "rembg"),
        # 拼版排在 PDF排版 之后（PDF排版 不是最后）
        ("print", "imposition"),
        # PDF排版 夹在中间
        ("rembg", "print", "detect"),
        # PDF排版 后又回到提取
        ("print", "extract"),
        ("extract", "print", "detect"),
    ]
    for stages in illegal:
        result = validate_flow(_chain(*stages))
        ok(f"不合法组合 {' → '.join(stages)} 被拒绝",
           not result.ok and any("PDF排版" in e for e in result.errors),
           f"errors={result.errors}")

    # 空流程：只有起止事件，没有可执行步骤
    result = validate_flow(_chain())
    ok("空流程（无可执行步骤）被拒绝",
       not result.ok and any("没有可执行" in e for e in result.errors),
       f"errors={result.errors}")
    result = validate_flow(None)
    ok("None 图被拒绝", not result.ok)

    # 错误信息要点名问题步骤（用户得知道改哪儿）
    result = validate_flow(_chain("print", "rembg"))
    ok("错误信息点名「PDF排版」与其后的步骤",
       any("PDF排版" in e and "去底色" in e for e in result.errors),
       str(result.errors))


# --------------------------------------------------------------- ③ 警告
def _check_warnings(ok) -> None:
    """与习惯不符但跑得通的组合：只给警告，``ok`` 仍为真。"""
    from desktop.steps.validate import validate_flow

    # 拼版在但没有判断节点
    result = validate_flow(_chain("imposition", "print"))
    ok("有拼版没判断节点 ⇒ 警告且不拦",
       result.ok and any("判断" in w for w in result.warnings),
       f"warnings={result.warnings}")

    # extract 不在第一位
    result = validate_flow(_chain("detect", "extract", "print"))
    ok("extract 不在第一位 ⇒ 警告且不拦",
       result.ok and any("提取" in w for w in result.warnings),
       f"warnings={result.warnings}")

    # extract 在但没有「源PDF」入口节点
    result = validate_flow(_chain("extract", "print", source=False))
    ok("有 extract 没有「源PDF」入口 ⇒ 警告且不拦",
       result.ok and any("源PDF" in w for w in result.warnings),
       f"warnings={result.warnings}")

    # 同一阶段两个节点（两个「PDF排版」）
    from desktop.steps.bpmn_diagram import (
        KIND_TASK, DiagramFlow, DiagramNode, FlowDiagram, stage_of_name,
    )

    diagram = FlowDiagram(
        nodes=(DiagramNode("a", KIND_TASK, "PDF排版",
                           stage=stage_of_name("PDF排版")),
               DiagramNode("b", KIND_TASK, "PDF排版2",
                           stage=stage_of_name("PDF排版"))),
        flows=(DiagramFlow("f1", "a", "b"),),
    )
    result = validate_flow(diagram)
    ok("同一阶段两个节点 ⇒ 警告且不拦",
       result.ok and any("2 个节点" in w for w in result.warnings),
       f"warnings={result.warnings}")

    # 未接入运行的节点（随手画的「OCR 识别」）
    diagram = FlowDiagram(
        nodes=(DiagramNode("a", KIND_TASK, "检测文本框",
                           stage=stage_of_name("检测文本框")),
               DiagramNode("b", KIND_TASK, "OCR 识别")),
        flows=(DiagramFlow("f1", "a", "b"),),
    )
    result = validate_flow(diagram)
    ok("未接入运行的节点 ⇒ 警告且不拦",
       result.ok and any("OCR 识别" in w for w in result.warnings),
       f"warnings={result.warnings}")

    # 合法且干净的图：零警告（别让警告变噪声）
    result = validate_flow(_chain("extract", "detect", "rembg",
                                  "imposition", "print", gateway=True))
    ok("完整默认流程零警告", result.ok and not result.warnings,
       f"warnings={result.warnings}")


# ------------------------------------------------- ④ 模板必须干净通过
def _check_templates_clean(ok) -> None:
    """默认模板与自定义初值模板都必须**零错误零警告**——模板是用户起点，
    一打开编辑器就被警告轰炸等于告诉用户"程序自己给的东西不合法"。"""
    from desktop.steps.scheduler import load_default_diagram
    from desktop.steps.validate import validate_flow

    from desktop.components.create_task_dialog import load_custom_init

    for name, diagram in (("task_default", load_default_diagram()),
                          ("task_detail", load_custom_init())):
        result = validate_flow(diagram)
        ok(f"模板 {name}.bpmn 零错误零警告",
           result.ok and not result.warnings,
           f"errors={result.errors} warnings={result.warnings}")


# ---------------------------------------------- ④b 数据链：每步都有输入
def _check_data_chain(ctx, ok) -> None:
    """**第一个节点有输入 ⇒ 链上每一步的输入端口都解析得出**（数据不断链）。

    用户口径（2026-10-07）：除了页面能渲染，数据层要成立——比如
    ``rembg → imposition → print``：rembg 引入图片目录，处理后传给
    imposition，处理后再传给 print。判据：任意合法组合里，每个可运行
    阶段的**阻塞输入**（``required_stage_inputs``）都能经
    ``store.stage_input`` 解析出具体路径（上游产物目录或入口图片目录），
    不能有"到中间某步断链、解析出 None"的组合。
    """
    from desktop.steps import ports
    from desktop.steps.scheduler import Scheduler
    from desktop.store import TaskStore

    repo = TaskStore(ctx.tmp / "chain_store")
    combos = [
        ("extract", "detect", "rembg", "imposition", "print"),
        ("detect", "rembg", "imposition", "print"),
        ("rembg", "imposition", "print"),
        ("detect", "rembg", "print"),
        ("rembg", "print"),
        ("detect", "print"),
        ("extract", "print"),
        ("imposition", "print"),
        ("print",),
        ("rembg", "detect", "imposition", "print"),   # 乱序也算合法
    ]
    for index, stages in enumerate(combos):
        diagram = _chain(*stages)
        tid = repo.create_task(ctx.pdf, f"chain-{index}", "数据链",
                               diagram=diagram)
        try:
            for active in (False, True):
                label = f"{'→'.join(stages)}（拼版{'开' if active else '关'}）"
                sched = Scheduler.from_diagram(diagram, {"imposition": active})
                for stage in sched.stages:
                    for port in repo.required_stage_inputs(tid, stage, active):
                        path = repo.stage_input(tid, stage, port, active)
                        ok(f"{label}: {stage}.{port} 解析得出输入",
                           path is not None, f"{stage}.{port} -> {path}")
        finally:
            repo.delete_task(tid)

    # ---- 用户举例的链路逐跳核对（rembg → imposition → print）----
    diagram = _chain("rembg", "imposition", "print")
    tid = repo.create_task(ctx.pdf, "chain-user", "用户链", diagram=diagram)
    try:
        task_dir = repo.task_dir(tid)
        ok("rembg 是入口 ⇒ 吃入口图片目录",
           repo.stage_input(tid, "rembg", "pages") == repo.task_input_dir(tid),
           str(repo.stage_input(tid, "rembg", "pages")))
        ok("rembg 提交的成品传给 imposition",
           repo.stage_input(tid, "imposition", "pages")
           == ports.artifact_path(task_dir, "rembg_submit", "pages"),
           str(repo.stage_input(tid, "imposition", "pages")))
        ok("imposition 的产物传给 print（开拼版）",
           repo.stage_input(tid, "print", "pages", True)
           == ports.artifact_path(task_dir, "imposition", "pages"),
           str(repo.stage_input(tid, "print", "pages", True)))
        ok("不开拼版时 print 回退吃提交成品（不断链）",
           repo.stage_input(tid, "print", "pages", False)
           == ports.artifact_path(task_dir, "rembg_submit", "pages"),
           str(repo.stage_input(tid, "print", "pages", False)))

    # ---- 无上游时入口回落、有上游时不许吃入口（两方向都钉） ----
        diagram2 = _chain("detect", "rembg", "print")
        tid2 = repo.create_task(ctx.pdf, "chain-entry", "入口回落",
                                diagram=diagram2)
        try:
            ok("detect 是入口 ⇒ 吃入口图片目录",
               repo.stage_input(tid2, "detect", "pages")
               == repo.task_input_dir(tid2),
               str(repo.stage_input(tid2, "detect", "pages")))
            ok("rembg 跟在 detect 后但 detect 不产 pages ⇒ 仍回落入口目录",
               repo.stage_input(tid2, "rembg", "pages")
               == repo.task_input_dir(tid2),
               str(repo.stage_input(tid2, "rembg", "pages")))
            ok("rembg 的检测框来自本流程的 detect（不回落）",
               repo.stage_input(tid2, "rembg", "boxes")
               == ports.artifact_path(repo.task_dir(tid2), "detect", "boxes"),
               str(repo.stage_input(tid2, "rembg", "boxes")))
            ok("print 吃 rembg 提交的成品",
               repo.stage_input(tid2, "print", "pages")
               == ports.artifact_path(repo.task_dir(tid2), "rembg_submit",
                                      "pages"),
               str(repo.stage_input(tid2, "print", "pages")))
        finally:
            repo.delete_task(tid2)
    finally:
        repo.delete_task(tid)


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
        finally:
            page.close()
            app.processEvents()
            store.delete_task(tid)
    finally:
        shutil.rmtree(root, ignore_errors=True)


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
